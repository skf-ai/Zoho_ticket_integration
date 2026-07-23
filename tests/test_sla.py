from datetime import datetime

from src import sla, workdays


def ist(y, m, d, hour=0, minute=0):
    return datetime(y, m, d, hour, minute, tzinfo=workdays.IST)


def open_state(created):
    due = workdays.add_working_days(created, 3)
    return {
        "ticket_status": "open",
        "ticket_created_at": workdays.iso(created),
        "sla_due_at": workdays.iso(due),
        "admin_nudges": 0,
    }, due


def test_open_ticket_never_closes_before_promised_time():
    state, due = open_state(ist(2026, 7, 23, 14))
    just_before = due.replace(microsecond=0) - workdays.timedelta(seconds=1)
    assert sla.decide(state, just_before)["action"] != "auto_close_admin"
    assert sla.decide(state, due)["action"] == "auto_close_admin"


def test_two_admin_nudges_wait_until_deadline():
    state, due = open_state(ist(2026, 7, 23, 14))
    state["admin_nudges"] = 2
    decision = sla.decide(state, ist(2026, 7, 25, 10))
    assert decision["action"] == "none"
    assert decision["next_at"] == due


def test_student_reminder_is_reachable_after_one_working_day():
    prompted = ist(2026, 7, 23, 14)
    state = {
        "ticket_status": "awaiting_verification",
        "verification_prompted_at": workdays.iso(prompted),
        "student_reminders": 0,
    }
    assert sla.decide(state, ist(2026, 7, 24, 9))["action"] == "remind_student"


def test_student_auto_close_only_at_three_day_deadline():
    prompted = ist(2026, 7, 23, 14)
    deadline = sla.verification_deadline(prompted)
    state = {
        "ticket_status": "awaiting_verification",
        "verification_prompted_at": workdays.iso(prompted),
        "student_reminders": 1,
    }
    assert sla.decide(state, deadline - workdays.timedelta(seconds=1))["action"] == "none"
    assert sla.decide(state, deadline)["action"] == "auto_close_student"
