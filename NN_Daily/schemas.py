from typing import List, Optional
from pydantic import BaseModel


class TodoItem(BaseModel):
    id: str
    text: str
    done: bool = False


class StandupGenerated(BaseModel):
    simple: str = ""
    detailed: str = ""
    ideal: str = ""


class StandupData(BaseModel):
    assigned: str = ""
    completed: str = ""
    missed: str = ""
    extra: str = ""
    focus: str = ""
    generated: StandupGenerated = StandupGenerated()


class PracticeData(BaseModel):
    done: bool = False
    note: str = ""


class ReflectionData(BaseModel):
    done: str = ""
    missed: str = ""
    assigned: str = ""
    backlog: str = ""
    learned: str = ""
    better: str = ""


class DayRecord(BaseModel):
    date: str
    todos: List[TodoItem] = []
    standup: StandupData = StandupData()
    practice: PracticeData = PracticeData()
    reflection: ReflectionData = ReflectionData()
    completed_day: bool = False
    archived: bool = False
    is_workday: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DayUpdate(BaseModel):
    """Partial update — only fields provided are merged into the stored record."""
    todos: Optional[List[TodoItem]] = None
    standup: Optional[StandupData] = None
    practice: Optional[PracticeData] = None
    reflection: Optional[ReflectionData] = None


class StandupGenerateRequest(BaseModel):
    assigned: str = ""
    completed: str = ""
    missed: str = ""
    extra: str = ""
    focus: str = ""
    today_todos: List[TodoItem] = []


class ArchiveRequest(BaseModel):
    cutoff_date: str  # 'YYYY-MM-DD' — archive all entries strictly before this date
