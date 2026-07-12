import os
import re

from dotenv import load_dotenv
from google import genai
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

Produce exactly three versions, using this exact delimited format and nothing else — no preamble, no closing remarks, and no markdown formatting (no bold, no headers, no code fences) inside any section:

===SIMPLE===
A scannable bullet list, for someone skimming at a glance:
Yesterday:
- <one bullet per completed item, "- " prefixed, one line each>
Missed:
- <one bullet per missed item — omit this "Missed:" heading and its bullets entirely if nothing was missed; never write "Missed: none">
Today:
- <one bullet per focus item>

===DETAILED===
2-4 full sentences of plain professional prose — no bullets, no headings. Written to be read async (e.g. posted in a Slack standup channel), covering what got done yesterday, what was missed (only if relevant), and today's focus, as flowing sentences rather than a list.

===IDEAL===
A 3-5 sentence script meant to be read aloud in a live standup — first person, confident, natural spoken cadence. No headings, no bullets, no "Yesterday:" / "Today:" labels of any kind — it should sound like a person talking through their day, not a report being recited.
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
        interaction = client.interactions.create(
            model=MODEL,
            input=_build_user_message(req),
            system_instruction=SYSTEM_PROMPT,
            generation_config={
                # This is straightforward text rewriting, not multi-step reasoning —
                # keep thinking minimal so the token budget goes to visible output.
                "thinking_level": "minimal",
                "max_output_tokens": 1500,
            },
        )
    except APIError as e:
        status = getattr(e, "code", 502) or 502
        if status == 429:
            raise StandupGenerationError(f"Rate limited by Gemini API: {e.message}", status_code=429) from e
        raise StandupGenerationError(f"Gemini API error (HTTP {status}): {e.message}", status_code=502) from e
    except Exception as e:
        raise StandupGenerationError(f"Could not reach Gemini API: {e}", status_code=502) from e

    if interaction.status in ("incomplete", "budget_exceeded"):
        raise StandupGenerationError(
            f"Gemini response was cut off (status: {interaction.status}) before finishing — "
            "try again, or this may need a higher max_output_tokens.",
            status_code=502,
        )
    if interaction.status == "failed":
        raise StandupGenerationError("Gemini API request failed.", status_code=502)

    text = interaction.output_text
    if not text or not text.strip():
        raise StandupGenerationError("Gemini API returned an empty response.", status_code=502)

    return _parse_delimited(text)
