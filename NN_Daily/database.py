import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

from logic import is_workday_for_date, resolve_last_workday
from schemas import DayRecord, DayUpdate, PracticeData, ReflectionData, StandupData

DB_DIR = Path(__file__).parent / "data"
DB_PATH = DB_DIR / "companion.db"


class DayLockedError(Exception):
    """Raised when attempting to modify a wrapped (completed_day=1) day."""


class DayAlreadyWrappedError(Exception):
    """Raised when attempting to wrap a day that is already wrapped."""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS days (
                date TEXT PRIMARY KEY,
                todos TEXT NOT NULL DEFAULT '[]',
                standup TEXT NOT NULL DEFAULT '{}',
                practice TEXT NOT NULL DEFAULT '{}',
                reflection TEXT NOT NULL DEFAULT '{}',
                completed_day INTEGER NOT NULL DEFAULT 0,
                archived INTEGER NOT NULL DEFAULT 0,
                is_workday INTEGER NOT NULL DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _row_to_day_record(row: sqlite3.Row) -> DayRecord:
    return DayRecord(
        date=row["date"],
        todos=json.loads(row["todos"]),
        standup=StandupData(**json.loads(row["standup"])),
        practice=PracticeData(**json.loads(row["practice"])),
        reflection=ReflectionData(**json.loads(row["reflection"])),
        completed_day=bool(row["completed_day"]),
        archived=bool(row["archived"]),
        is_workday=bool(row["is_workday"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def get_day(date_str: str) -> Optional[DayRecord]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM days WHERE date = ?", (date_str,)).fetchone()
        return _row_to_day_record(row) if row else None
    finally:
        conn.close()


def get_or_create_day(date_str: str) -> DayRecord:
    existing = get_day(date_str)
    if existing:
        return existing

    d = date.fromisoformat(date_str)
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO days (date, todos, standup, practice, reflection,
                               completed_day, archived, is_workday, created_at, updated_at)
            VALUES (?, '[]', '{}', '{}', '{}', 0, 0, ?, ?, ?)
            """,
            (date_str, int(is_workday_for_date(d)), now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return get_day(date_str)


def upsert_day_fields(date_str: str, update: DayUpdate) -> DayRecord:
    current = get_or_create_day(date_str)
    if current.completed_day:
        raise DayLockedError(f"Day {date_str} is wrapped and read-only")

    todos = update.todos if update.todos is not None else current.todos
    standup = update.standup if update.standup is not None else current.standup
    practice = update.practice if update.practice is not None else current.practice
    reflection = update.reflection if update.reflection is not None else current.reflection
    now = datetime.now().isoformat(timespec="seconds")

    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE days
            SET todos = ?, standup = ?, practice = ?, reflection = ?, updated_at = ?
            WHERE date = ?
            """,
            (
                json.dumps([t.model_dump() for t in todos]),
                json.dumps(standup.model_dump()),
                json.dumps(practice.model_dump()),
                json.dumps(reflection.model_dump()),
                now,
                date_str,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return get_day(date_str)


def wrap_day(date_str: str) -> DayRecord:
    current = get_or_create_day(date_str)
    if current.completed_day:
        raise DayAlreadyWrappedError(f"Day {date_str} is already wrapped")

    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE days SET completed_day = 1, updated_at = ? WHERE date = ?",
            (now, date_str),
        )
        conn.commit()
    finally:
        conn.close()
    return get_day(date_str)


def list_days_range(start_date: str, end_date: str, include_archived: bool = False) -> List[DayRecord]:
    conn = get_connection()
    try:
        query = "SELECT * FROM days WHERE date >= ? AND date <= ?"
        params: list = [start_date, end_date]
        if not include_archived:
            query += " AND archived = 0"
        query += " ORDER BY date ASC"
        rows = conn.execute(query, params).fetchall()
        return [_row_to_day_record(r) for r in rows]
    finally:
        conn.close()


def list_history(limit: int = 50, offset: int = 0, include_archived: bool = False) -> List[DayRecord]:
    conn = get_connection()
    try:
        query = "SELECT * FROM days"
        if not include_archived:
            query += " WHERE archived = 0"
        query += " ORDER BY date DESC LIMIT ? OFFSET ?"
        rows = conn.execute(query, (limit, offset)).fetchall()
        return [_row_to_day_record(r) for r in rows]
    finally:
        conn.close()


def get_standup_context(date_str: str) -> dict:
    """Resolve the 'yesterday' (last workday) prefill data for the standup generator. See PRD 8.2."""
    d = date.fromisoformat(date_str)
    last_workday = resolve_last_workday(d)
    last_workday_str = last_workday.isoformat()
    day_record = get_day(last_workday_str)

    if day_record is None:
        return {
            "last_workday": last_workday_str,
            "completed": [],
            "missed": [],
            "backlog": "",
            "assigned_today": "",
        }

    return {
        "last_workday": last_workday_str,
        "completed": [t.text for t in day_record.todos if t.done],
        "missed": [t.text for t in day_record.todos if not t.done],
        "backlog": day_record.reflection.backlog,
        "assigned_today": day_record.reflection.assigned,
    }


def compute_streak(as_of_date: str, lookback_days: int = 400) -> int:
    """Walk backward from the day before `as_of_date`, counting consecutive
    completed workdays. Weekend/off-days are skipped without breaking the chain.
    A workday with no row (never visited) counts as incomplete and ends the streak."""
    as_of = date.fromisoformat(as_of_date)
    window_start = (as_of - timedelta(days=lookback_days)).isoformat()
    rows = list_days_range(window_start, as_of_date, include_archived=False)
    by_date = {r.date: r for r in rows}

    streak = 0
    cursor = as_of - timedelta(days=1)
    for _ in range(lookback_days):
        cursor_str = cursor.isoformat()
        record = by_date.get(cursor_str)
        workday = record.is_workday if record else is_workday_for_date(cursor)
        if not workday:
            cursor -= timedelta(days=1)
            continue
        if record and record.completed_day:
            streak += 1
            cursor -= timedelta(days=1)
        else:
            break
    return streak


def get_rolling_practice(as_of_date: str, days: int = 7) -> int:
    as_of = date.fromisoformat(as_of_date)
    window_start = (as_of - timedelta(days=days - 1)).isoformat()
    rows = list_days_range(window_start, as_of_date, include_archived=False)
    return sum(1 for r in rows if r.practice.done)


def archive_older_than(cutoff_date: str) -> int:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE days SET archived = 1 WHERE date < ? AND archived = 0",
            (cutoff_date,),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def delete_archived() -> int:
    conn = get_connection()
    try:
        cursor = conn.execute("DELETE FROM days WHERE archived = 1")
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()
