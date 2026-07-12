import os
import re

import anthropic
from dotenv import load_dotenv

from schemas import StandupGenerateRequest, StandupGenerated

load_dotenv()

MODEL = "claude-sonnet-5"

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
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise StandupGenerationError(
            "ANTHROPIC_API_KEY is not set. Add it to a .env file in the project root "
            "(see .env.example) and restart the server.",
            status_code=500,
        )

    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_message(req)}],
        )
    except anthropic.RateLimitError as e:
        raise StandupGenerationError(f"Rate limited by Anthropic API: {e}", status_code=429) from e
    except anthropic.APIStatusError as e:
        raise StandupGenerationError(
            f"Anthropic API error (HTTP {e.status_code}): {e.message}", status_code=502
        ) from e
    except anthropic.APIConnectionError as e:
        raise StandupGenerationError(f"Could not connect to Anthropic API: {e}", status_code=502) from e

    if not response.content or not response.content[0].text.strip():
        raise StandupGenerationError("Anthropic API returned an empty response.", status_code=502)

    return _parse_delimited(response.content[0].text)
