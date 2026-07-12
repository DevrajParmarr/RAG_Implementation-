import os
import re

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError

from schemas import StandupGenerateRequest, StandupGenerated

load_dotenv()

# Free-tier Gemini model via Google AI Studio. Verify this is still current at
# https://aistudio.google.com if generation starts failing with a 404 — Google
# renames/retires model ids periodically (gemini-2.5-flash was retired for new
# users as of mid-2026; gemini-3.5-flash is the current flagship Flash-tier model).
MODEL = "gemini-3.5-flash"

SYSTEM_PROMPT = """You are helping a software engineer turn messy, informal notes into a spoken daily standup update.

The engineer's input may be broken English, sentence fragments, or poorly explained \
— your job is to understand the intent, not to literally clean up grammar. Produce output that:
- uses correct, natural professional vocabulary (not overly casual, not stiff or robotic)
- preserves technical terms exactly as given (framework names, ticket IDs, system/service names), even if surrounded by broken grammar
- is understandable to a mixed audience (technical teammates and a non-technical manager/PM in the room), avoiding unexplained jargon where a plain phrase would do
- is concise — no padding, no restating the obvious, no corporate filler phrases
- sounds like something a real person would actually say out loud, not a written report read aloud

Produce exactly three versions, using this exact delimited format and nothing else (no preamble, no extra commentary, no markdown code fences):

===SIMPLE===
<a short bullet list, "- " prefixed lines, under Yesterday / Missed (only if there's something missed) / Today headings>
===DETAILED===
<2-4 full sentences of professional prose>
===IDEAL===
<a 3-5 sentence spoken-out-loud script, first person, confident tone>
"""


class StandupGenerationError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _build_user_message(req: StandupGenerateRequest) -> str:
    todos_text = (
        "\n".join(f"- [{'x' if t.done else ' '}] {t.text}" for t in req.today_todos) or "(none)"
    )
    return f"""Assigned yesterday: {req.assigned or '(nothing recorded)'}
Completed: {req.completed or '(nothing recorded)'}
Missed: {req.missed or '(nothing recorded)'}
Anything else (blockers/context): {req.extra or '(none)'}
Focus areas for today: {req.focus or '(not specified)'}

Today's to-do list so far:
{todos_text}"""


def _parse_delimited(text: str) -> StandupGenerated:
    pattern = r"===SIMPLE===\s*(.*?)\s*===DETAILED===\s*(.*?)\s*===IDEAL===\s*(.*)"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        raise StandupGenerationError(
            f"Model response didn't match the expected ===SIMPLE===/===DETAILED===/===IDEAL=== "
            f"format. Raw response (truncated): {text[:500]!r}",
            status_code=502,
        )
    simple, detailed, ideal = (g.strip() for g in match.groups())
    return StandupGenerated(simple=simple, detailed=detailed, ideal=ideal)


def generate_standup(req: StandupGenerateRequest) -> StandupGenerated:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise StandupGenerationError(
            "GEMINI_API_KEY is not set. Add it to a .env file in the project root "
            "(see .env.example) and restart the server.",
            status_code=500,
        )

    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=_build_user_message(req),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=1000,
            ),
        )
    except APIError as e:
        status = getattr(e, "code", 502) or 502
        if status == 429:
            raise StandupGenerationError(f"Rate limited by Gemini API: {e.message}", status_code=429) from e
        raise StandupGenerationError(f"Gemini API error (HTTP {status}): {e.message}", status_code=502) from e
    except Exception as e:
        raise StandupGenerationError(f"Could not reach Gemini API: {e}", status_code=502) from e

    text = response.text
    if not text or not text.strip():
        raise StandupGenerationError("Gemini API returned an empty response.", status_code=502)

    return _parse_delimited(text)
