from datetime import date

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import database
from schemas import (
    ArchiveRequest,
    DayRecord,
    DayUpdate,
    StandupGenerateRequest,
    StandupGenerated,
)

app = FastAPI(title="Daily Engineer Companion")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    database.init_db()


def _validate_date(date_str: str) -> None:
    try:
        date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date '{date_str}', expected YYYY-MM-DD")


@app.get("/api/days/{date_str}", response_model=DayRecord)
def read_day(date_str: str):
    _validate_date(date_str)
    return database.get_or_create_day(date_str)


@app.put("/api/days/{date_str}", response_model=DayRecord)
def update_day(date_str: str, update: DayUpdate):
    _validate_date(date_str)
    try:
        return database.upsert_day_fields(date_str, update)
    except database.DayLockedError as e:
        raise HTTPException(status_code=423, detail=str(e))


@app.post("/api/days/{date_str}/wrap", response_model=DayRecord)
def wrap_day(date_str: str):
    _validate_date(date_str)
    try:
        return database.wrap_day(date_str)
    except database.DayAlreadyWrappedError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/api/days", response_model=list[DayRecord])
def list_days(
    start: str = Query(...),
    end: str = Query(...),
    include_archived: bool = Query(False),
):
    _validate_date(start)
    _validate_date(end)
    return database.list_days_range(start, end, include_archived)


@app.get("/api/history", response_model=list[DayRecord])
def history(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    include_archived: bool = Query(False),
):
    return database.list_history(limit, offset, include_archived)


@app.get("/api/days/{date_str}/context")
def standup_context(date_str: str):
    _validate_date(date_str)
    return database.get_standup_context(date_str)


@app.get("/api/streak")
def streak(as_of: str = Query(default=None)):
    as_of_date = as_of or date.today().isoformat()
    _validate_date(as_of_date)
    return {"streak": database.compute_streak(as_of_date)}


@app.get("/api/practice/rolling")
def practice_rolling(as_of: str = Query(default=None)):
    as_of_date = as_of or date.today().isoformat()
    _validate_date(as_of_date)
    return {"count": database.get_rolling_practice(as_of_date), "days": 7}


@app.post("/api/maintenance/archive")
def archive_old_entries(req: ArchiveRequest):
    _validate_date(req.cutoff_date)
    return {"archived_count": database.archive_older_than(req.cutoff_date)}


@app.delete("/api/maintenance/archived")
def delete_archived_entries():
    return {"deleted_count": database.delete_archived()}


@app.post("/api/standup/generate")
def generate_standup(req: StandupGenerateRequest):
    """
    STUB — per PRD section 6, the real Anthropic API call is wired up last (build step 3).
    This returns a mock response in the same delimited format the real endpoint will use,
    so the frontend (build step 2) can be built and tested without live API calls.
    """
    mock = StandupGenerated(
        simple=f"- Yesterday: {req.completed or '(nothing recorded)'}\n"
        f"- Missed: {req.missed or 'none'}\n"
        f"- Today: {req.focus or '(no focus set)'}",
        detailed="[stub] Detailed standup script will be generated here once the "
        "Anthropic API integration is wired up in build step 3.",
        ideal="[stub] This is a placeholder for the spoken-out-loud standup script. "
        "Real generation is not implemented yet.",
    )
    return mock


# Mounted last so it never shadows the /api routes registered above.
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")
