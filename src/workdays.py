"""Working-day arithmetic for the SLA clock.

Every deadline in this system is expressed in *working days*, not calendar days:
the SLA we promise the student ("resolved within 3 working days"), the admin
nudge schedule, and both auto-close timers.

Rules, confirmed with the client:
  * Working days are Monday-Saturday. Sunday is off.
  * Holidays in HOLIDAYS below are also off.
  * All business logic happens in Asia/Kolkata; all timestamps are *stored* in
    UTC. Convert at the boundary, never in the middle.

Counting convention: `add_working_days(t, 3)` advances 3 working days from the
calendar date of `t`, then lands at END_OF_BUSINESS on that day. A ticket raised
Saturday 18:00 IST is therefore due Wednesday 18:00 IST (Sunday skipped) --
never earlier than a full 3 working days later, which is what we promised.

Editing the holiday list is deliberately a one-line change so non-engineers can
maintain it; see HOLIDAYS.
"""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# Sunday only. (Python: Monday=0 ... Sunday=6)
WEEKLY_OFF = {6}

# End of the support day in IST. Deadlines land here so a ticket is never
# declared overdue at midnight while the admin is asleep.
END_OF_BUSINESS = time(18, 0)

# Non-working holidays, ISO dates in IST. Keep this list current -- an out-of-date
# calendar silently shortens the SLA and auto-closes tickets a day early.
# Add or remove a line and redeploy; no other change is needed.
HOLIDAYS = {
    # --- 2026 ---
    "2026-08-15",  # Independence Day
    "2026-10-02",  # Gandhi Jayanti
    "2026-11-08",  # Diwali
    "2026-12-25",  # Christmas
    # --- 2027 ---
    "2027-01-26",  # Republic Day
    "2027-08-15",  # Independence Day
    "2027-10-02",  # Gandhi Jayanti
}


def is_working_day(d):
    """True if `d` (a date, interpreted in IST) is a working day."""
    if d.weekday() in WEEKLY_OFF:
        return False
    return d.isoformat() not in HOLIDAYS


def to_ist(dt):
    """Convert an aware datetime to IST. Naive input is assumed to be UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)


def to_utc(dt):
    """Convert an aware datetime to UTC. Naive input is assumed to be IST."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(timezone.utc)


def add_working_days(start, days):
    """Return the UTC deadline `days` working days after `start`.

    `start` may be naive (treated as UTC) or aware. The result is an aware UTC
    datetime at END_OF_BUSINESS IST, so callers can compare it directly against
    `datetime.now(timezone.utc)` without further conversion.
    """
    cursor = to_ist(start).date()
    remaining = days
    while remaining > 0:
        cursor += timedelta(days=1)
        if is_working_day(cursor):
            remaining -= 1
    deadline_ist = datetime.combine(cursor, END_OF_BUSINESS, tzinfo=IST)
    return deadline_ist.astimezone(timezone.utc)


def working_days_between(start, end):
    """Count whole working days elapsed from `start` to `end` (exclusive/inclusive).

    Used to decide how far into the SLA a ticket is, which drives the admin
    nudge ladder. Returns 0 if `end` is not after `start`.
    """
    start_d = to_ist(start).date()
    end_d = to_ist(end).date()
    if end_d <= start_d:
        return 0
    count = 0
    cursor = start_d
    while cursor < end_d:
        cursor += timedelta(days=1)
        if is_working_day(cursor):
            count += 1
    return count


def next_working_day_start(dt):
    """The next working day's 09:00 IST, as UTC.

    Used to defer a nudge that would otherwise fire on a Sunday or a holiday --
    we don't message the LMS admin on their day off.
    """
    cursor = to_ist(dt).date()
    while True:
        cursor += timedelta(days=1)
        if is_working_day(cursor):
            break
    return datetime.combine(cursor, time(9, 0), tzinfo=IST).astimezone(timezone.utc)


def now_utc():
    """Current time as an aware UTC datetime. Single source of 'now' so tests
    can monkeypatch one function instead of hunting datetime.now() call sites."""
    return datetime.now(timezone.utc)


def iso(dt):
    """Serialize an aware datetime to a sortable ISO-8601 UTC string.

    This is the on-disk format for every timestamp in DynamoDB; because it sorts
    lexicographically, the sweeper can range-query due items on a GSI.
    """
    return to_utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(value):
    """Parse a timestamp written by `iso()` back to an aware UTC datetime."""
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
