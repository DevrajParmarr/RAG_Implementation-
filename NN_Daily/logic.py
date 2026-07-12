from datetime import date, timedelta


def is_workday_for_date(d: date) -> bool:
    """Mon-Fri = workday, Sat/Sun = not. See PRD section 8.2."""
    return d.weekday() < 5


def resolve_last_workday(as_of: date) -> date:
    """Most recent workday strictly before `as_of` (e.g. Monday -> prior Friday)."""
    d = as_of - timedelta(days=1)
    while not is_workday_for_date(d):
        d -= timedelta(days=1)
    return d
