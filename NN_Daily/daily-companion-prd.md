# PRD: Daily Engineer Companion

**Author:** (you) via Claude
**Status:** Draft — ready for build
**Intended builder:** Claude Code

## 1. Problem statement

I'm a software engineer who wants a single daily habit-loop tool that:
- Turns messy, unstructured notes ("what I did / missed / am focused on") into a clean, speakable standup update
- Tracks a simple daily to-do list and keeps a streak/history so I can see momentum over time
- Gives me a lightweight end-of-day journal (done / missed / learned / better) so reflection becomes a habit, not an afterthought
- Optionally tracks whether I did my daily DSA/practice grind

**Primary motivation (confirmed):** the single most acute pain point is that writing the daily standup update is a scramble — messy notes with no clean, fast way to turn them into something presentable. This is why standup generation is P0 and gets built first. The secondary motivation is momentum/accountability: seeing a visible streak and contribution-style history is what keeps the habit going day to day, so the streak/history mechanic (8.2, 8.3) is treated as nearly as important as the standup generator itself, not an afterthought.

**No prototype exists yet.** An earlier version of this idea was described as a Claude.ai artifact (single-file HTML with a built-in storage API and in-artifact Claude API call), but that file was never retrieved/saved — it does not exist anywhere on disk. This PRD and the build that follows are **from scratch**: the visual language in section 5 (dark terminal aesthetic, git-log history, contribution graph) is a design spec to build new, not something to port from an existing file. Exact page layout/navigation (single dashboard vs. separate views) is intentionally left open — decide it during the build based on what fits best, per section 6.

## 2. User & scope

- **Single user** (me), personal use only. No multi-tenancy, no accounts.
- **Runs on my own Windows laptop only** — no remote access, no phone access, no hosting needed. This significantly simplifies the build: no auth system, no PWA/offline requirement, no deployment story to design for.
- Not building for a team or public release. Keep scope tight — this is a personal tool, not a product.

## 3. Prerequisite: Gemini API key

**Revised from the original Anthropic-based plan (confirmed change):** the standup-generation feature calls the Google Gemini API instead, specifically to use Google AI Studio's free tier rather than a paid API — the user's usage volume (1-2 calls/day, short prompts) is cheap on either provider, but the explicit preference was zero ongoing cost over marginally better output quality. Before development starts:

1. Go to Google AI Studio (aistudio.google.com) and sign in with a Google account.
2. Create an API key (no billing/credit card required for the free tier).
3. Store it in a local `.env` file in the project root as `GEMINI_API_KEY=...` — never commit this file to version control (add it to `.gitignore`).

Free tier comes with real rate limits (requests/minute and requests/day caps) — fine for this app's volume, but worth knowing if generation ever fails with a 429.

Claude Code should scaffold the project assuming this key will be supplied via `.env` and loaded server-side only (e.g. via `python-dotenv`). It must never be exposed to the frontend/browser.

## 4. Recommended architecture

Given the constraints confirmed for this build — **Windows laptop only, no remote access, no offline requirement, no login/auth needed, no data export needed** — the right-sized architecture is intentionally minimal:

- **Backend:** **Python + FastAPI**, run via `uvicorn`. Two jobs only: (1) proxy standup-generation requests to the Anthropic API using the server-side `.env` API key, and (2) serve as a small CRUD API for day entries, backed by SQLite. FastAPI is chosen over Flask for its built-in request validation (Pydantic models) and clean async support, which fits the external API call well.
- **Frontend:** Plain HTML/CSS/JS single-page app, built fresh against the design tokens/aesthetic in section 5 (there is no existing prototype file to port — see section 1). No React/Next.js needed — there's no PWA, no offline sync, no remote access requirement to justify that complexity. FastAPI can serve the static frontend directly (`StaticFiles` mount), so this is a single app to run. Exact page/navigation structure (single dashboard vs. tabs vs. separate routes) is decided during the build, per section 6.
- **Storage:** SQLite via Python's built-in `sqlite3` module (or `SQLAlchemy` if Claude Code prefers an ORM layer — either is fine given the low complexity). One file (e.g. `data/companion.db`), zero infra, trivial to back up by copying the file.
- **Auth:** **None.** No login screen, no passcode. It's a local-only tool on a personal machine.
- **Run model (Windows):**
  ```powershell
  python -m venv venv
  venv\Scripts\activate
  pip install -r requirements.txt
  uvicorn main:app --reload
  ```
  Then open `http://localhost:8000` in a browser. No deployment, no hosting, no domain needed.

## 5. Design system to build

There is no existing prototype to carry over (see section 1) — this is the target aesthetic to design and build fresh: a dark, terminal/git-log-inspired look. Key tokens to use directly:

```css
--ink: #191510;        /* page background */
--panel: #221d17;      /* card background */
--panel-2: #2a241c;    /* input/textarea background */
--line: #3d352a;       /* borders */
--paper: #eee7db;      /* primary text */
--dim: #97897a;        /* muted text */
--amber: #e2a63f;      /* accent (buttons, active states, streak badge) */
--moss: #7fa876;       /* success/completed */
--rust: #c1666b;       /* delete/danger */
--slate: #6f97b0;      /* info labels */
```

- **Typography:** monospace for all UI chrome (nav, labels, buttons, todo list) — signals "terminal/dev tool." A warm serif, italicized, is used specifically for anything the user writes by hand (journal reflections, standup notes) — the interface stepping back into a human voice when you're actually writing. Keep this contrast; it's the one deliberate signature element of the design.
- **Signature elements to design in:** the git-commit-style history log (pseudo commit hash + date + one-line summary, expandable), and the small GitHub-style contribution graph for the streak — these are the two visual anchors of the whole app, since streak/history visibility is confirmed as a core motivator (section 1), not a nice-to-have.
- Page/navigation structure (single scrolling dashboard, tabs, or separate routed views) is not locked in — choose whichever best serves the "everything for today visible, history one click away" feel, and confirm the direction once a rough layout exists before polishing it further.

## 6. Feature priority vs. build order

Two separate orderings apply here, and they are deliberately different:

**Feature priority** (what matters most to the user, most → least important):
1. **AI standup script generation** (P0)
2. **To-do list + streak/history tracking** (P0)
3. **EOD journal & reflection** (P1)
4. **Daily practice (DSA/LeetCode) tracking** (P2 — nice to have, cut if time-constrained)

**Build/implementation order** (confirmed preference — data layer and screens before the AI integration):
1. **Data layer + CRUD API first:** SQLite schema (section 7), FastAPI CRUD endpoints for day entries, `.env`/key scaffolding present but unused yet.
2. **All screens/UI, end to end, wired to the CRUD API:** to-do list, streak/history graph, EOD journal + wrap-up/locking, practice checkbox, history/log view — every feature in section 8 except the actual `POST /api/standup/generate` call. Standup fields (8.1) should exist in the UI and persist to the DB, but the "Generate" button can initially hit a stub/mock response.
3. **Anthropic API integration last:** wire the real `POST /api/standup/generate` call once the rest of the app is functional end-to-end — this isolates the one paid, external-network-dependent piece of the app to the final step, so most of the build can be tested purely locally without burning API calls.

Rationale for building this way: it lets the whole non-AI app (which is most of the surface area) be verified working before introducing the one component with external dependencies and cost — de-risks the build and keeps early iteration free.

## 7. Data model

One record per calendar day, keyed by date (`YYYY-MM-DD`):

```sql
CREATE TABLE days (
  date TEXT PRIMARY KEY,               -- 'YYYY-MM-DD'
  todos TEXT NOT NULL DEFAULT '[]',    -- JSON array: [{id, text, done}]
  standup TEXT NOT NULL DEFAULT '{}',  -- JSON: {assigned, completed, missed, extra, focus, generated:{simple,detailed,ideal}}
  practice TEXT NOT NULL DEFAULT '{}', -- JSON: {done: bool, note: string}
  reflection TEXT NOT NULL DEFAULT '{}', -- JSON: {done, missed, assigned, backlog, learned, better}
  completed_day INTEGER NOT NULL DEFAULT 0, -- 0/1, set true when EOD is "wrapped" — permanent once set (see 8.3)
  archived INTEGER NOT NULL DEFAULT 0, -- 0/1, see section 9 (archiving)
  is_workday INTEGER NOT NULL DEFAULT 1, -- 0/1, defaults to 0 for Sat/Sun — see 8.2
  created_at TEXT,
  updated_at TEXT
);
```

Rationale: JSON columns keep this close to the working prototype's data shape (fast to port), while `date`, `completed_day`, `archived`, and `is_workday` stay as real columns since they're needed for streak/graph/history queries and filtering.

## 8. Feature specs

### 8.1 AI standup script generator (P0)

**Inputs (user-entered, plain messy English is expected — no grammar requirement):**
1. What was assigned to you yesterday — "yesterday" here means the **last working day**, not necessarily the previous calendar day (see 8.2). Pre-filled as a suggestion from that day's to-do list, editable.
2. What you completed (pre-filled from that day's checked-off todos, editable)
3. What you missed (pre-filled from that day's unchecked todos, editable)
4. Anything else to mention (blockers, context — free text)
5. Focus areas for today (free text — the 1-3 things that actually matter today)

**Output: three versions, regenerated on demand via a "Generate" button (not on every keystroke — avoid excessive API calls):**
- **Simple** — short bullet list, `- ` prefixed lines under Yesterday / Missed (if any) / Today headings
- **Detailed** — 2-4 full sentences, professional prose
- **Ideal** — a 3-5 sentence spoken-out-loud script, first person, confident tone

All three outputs must be **user-editable after generation** (plain textareas, not read-only), and edits autosave.

**Language & tone quality bar (explicit requirement):** the whole point of this feature is that the user can type broken English, sentence fragments, or a poorly-explained description of a task, and the model must still understand the intent and produce a script that sounds like a genuine, competent engineer speaking in a real office standup — not a literal cleanup of their grammar. Concretely, the output must:
- Use correct, natural professional vocabulary — not overly casual, not stiff/robotic
- Preserve and correctly use technical terms (framework names, ticket IDs, system/service names) exactly as given, even if surrounded by broken grammar
- Be understandable to a mixed audience (both technical teammates and a non-technical manager/PM in the room), avoiding unexplained jargon where a plain-English phrase would do
- Be concise and to the point — no padding, no restating the obvious, no corporate filler phrases
- Sound like something a real person would actually say out loud, not like a written report read aloud
This quality bar applies most strongly to the "Ideal" script, but "Simple" and "Detailed" should also read as competently written English regardless of how rough the input was.

**Backend contract:**
- `POST /api/standup/generate` — body: `{ assigned, completed, missed, extra, focus, today_todos }` → calls the Google Gemini API server-side with the `.env` `GEMINI_API_KEY`, model `gemini-3.5-flash` (free tier via Google AI Studio — confirm this is still current, Google renames/retires model ids periodically; `gemini-2.5-flash` was already retired for new users as of mid-2026), `max_output_tokens: 1000`. Per section 6's build order, this endpoint is the last thing wired up — earlier in the build it can return a stubbed/mock response so the UI can be built and tested without live API calls.
- **Important lesson from the prototype:** do NOT ask the model to return JSON when the output contains multi-line bullet content — literal newlines inside JSON string values break strict JSON parsing. Use a plain delimited format instead:
  ```
  ===SIMPLE===
  ...
  ===DETAILED===
  ...
  ===IDEAL===
  ...
  ```
  and parse by locating the markers, not by JSON-parsing.
- On failure, return a real error message (not swallowed) so the frontend can show the user *why* it failed (HTTP status, rate limit, empty response, etc.) rather than a generic "something went wrong."
- Regeneration should be an explicit button press, not automatic — this is a real paid API call, no need to trigger it on every keystroke.

### 8.2 Weekend-aware streak & "yesterday" logic (P0 — core logic detail)

- Weekends (Saturday/Sunday) don't count as workdays by default (`is_workday = 0`), and don't break the streak or require a wrap-up to keep it alive.
- **"Yesterday" for the standup generator** resolves to the most recent day with `is_workday = 1` — e.g. on a Monday, it pulls from the prior Friday's to-do list and reflection, not literally Sunday.
- **Streak calculation** walks backward from today counting consecutive *workdays* with `completed_day = 1`, simply skipping over weekend rows without breaking the chain.
- Since the user described irregular... no — user confirmed a standard weekend-off pattern, so default `is_workday` to `false` for Saturday/Sunday and `true` otherwise. No need for a custom per-day workday toggle in v1 (could be a future setting if the user's schedule changes).

### 8.3 To-do list + streak/history tracking (P0)

- Simple add/check-off/delete to-do list per day, persisted immediately (each mutation writes to SQLite — cheap, local DB, no rate-limit concern like the artifact prototype had).
- **History graph:** the existing contribution-graph-style visual (last ~35 days), colored by activity level (none / some activity / day wrapped with low completion / day wrapped with high completion). Weekend squares can render as a distinct neutral "off day" style rather than "no activity," since they're expected to be empty.
- **Performance lesson from the prototype:** don't refetch the full history range from storage on every UI interaction. Load it once per page load (e.g. `SELECT * FROM days WHERE date >= ? AND archived = 0`), cache in memory, and only update the in-memory cache for today's own record as it changes.

### 8.4 EOD journal & reflection, and permanent day-locking (P1)

Four free-text fields, filled at end of day:
- What did you get done?
- What did you miss?
- What did you learn?
- What could be better tomorrow?

Plus two fields that feed the next working day's standup generator:
- What was given to you today? (new work/requests assigned)
- Backlog / carried-over items (not finished, still pending)

A **"Wrap up day"** action sets `completed_day = 1`. **This is permanent** — once wrapped, the day's todos, standup notes, and reflection fields are locked and read-only forever. There is no "Edit" unlock affordance (this is a deliberate change from the prototype, per explicit user preference — the point is an honest, unaltered daily record). Make sure the UI communicates this clearly before the user confirms wrap-up (e.g. a confirmation step: "This locks today's entry permanently. Continue?").

### 8.5 Daily practice tracking (P2)

- A single checkbox: "did today's practice" + an optional free-text note (problem/topic/link).
- A rolling 7-day count ("Practiced X/7 days this week"), counting workdays and weekends alike (practice tracking is not tied to the workday/streak logic in 8.2).
- Lowest priority — build only after 8.1–8.4 are solid, or cut for v1 if time-constrained.

### 8.6 History / log view

- A reverse-chronological list of all past days (git-commit-log style: pseudo hash + date + one-line summary, expandable to show full detail).
- Backed by `SELECT * FROM days WHERE archived = 0 ORDER BY date DESC`, with simple pagination if the list grows long.
- Entries are read-only in this view (see 8.4 — locking is permanent).

## 9. Archiving old entries (P2/P3)

Storage will grow indefinitely otherwise, so add a lightweight maintenance action rather than automatic deletion:

- A settings/maintenance view lets the user archive entries older than a chosen cutoff (e.g. "archive everything older than 6 months").
- Archiving sets `archived = 1` rather than deleting the row outright — keeps the option to permanently delete later without losing data by accident. A separate explicit "permanently delete archived entries" action can hard-delete rows with `archived = 1`.
- Archived entries are excluded from the default history view, streak calculation, and contribution graph, but can still be viewed via a "show archived" toggle in the log view.
- No automatic/scheduled archiving in v1 — this is a manual, user-triggered action only.

## 10. Non-functional requirements

- **Local-first & simple.** No unnecessary infrastructure. SQLite over Postgres. No auth system. No multi-user support. No hosting/deployment concerns.
- **Resilient to API failures.** The standup generator calls a real paid API — errors must be visible and actionable, not silent.
- **Low storage-call volume.** Avoid re-fetching large ranges of historical data on every keystroke or UI interaction (this caused real rate-limit failures in the prototype). Cache in memory during a session; only write on meaningful changes, debounced to a single coalesced write rather than one write per field.
- **Editable AI output (before locking).** Users must always be able to hand-edit generated standup text before the day is wrapped — the AI is a first draft, not a final answer. After wrap-up, the entire day's record (including generated scripts) becomes read-only per 8.4.
- **Visual continuity.** Reuse the prototype's existing design tokens and layout rather than redesigning (see section 5).

## 11. Explicit non-goals for v1

- No multi-user accounts, teams, or sharing features.
- No login/passcode/auth of any kind.
- No offline mode or service worker — always assumed online, running locally.
- No remote/phone access, no PWA install requirement, no hosting or deployment.
- No data export feature (the SQLite file itself is the de facto backup).
- No AI-generated coding puzzles (practice tracking is manual, per user's earlier explicit preference).
- No notifications/reminders in v1.
- No automatic/scheduled archiving — archiving old entries is a manual, on-demand action only.
- No editing of wrapped/locked past days — this is intentional, not a gap.

## 12. Open questions for future iterations (not blocking v1)

- If remote/phone access ever becomes desired later, revisit hosting + auth as a v2 concern — explicitly deferred, not designed for now.
- Would a weekly rollup ("what I learned this week across 5 daily entries") be worth adding once daily data accumulates?
- What's a sensible default archive cutoff (e.g. 6 months vs 1 year) — can be a simple configurable setting rather than hardcoded.
- If the user's work schedule ever becomes irregular (not standard Mon-Fri), the `is_workday` column could become user-editable per day rather than auto-derived from weekday — not needed for v1.
