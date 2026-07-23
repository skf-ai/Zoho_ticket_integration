"""The accountability engine: nudges, escalation, and both auto-close paths.

This is the part of the system that replaces the thing that was failing before --
a human remembering to chase the LMS admin and to follow up with the student.
It is deliberately pure decision logic: `decide()` takes state and a clock and
returns what should happen. All side effects live in sweeper.py, so the schedule
can be tested exhaustively without AWS, WhatsApp, or Zoho.

## The schedule

A ticket is raised. The student is told: resolved within 3 working days.

  Admin side, while status is `open`:
    +1 working day   nudge the admin on WhatsApp
    +2 working days  nudge again
    +3 working days  SLA reached -> auto-close, tell the student it can be
                     reopened, and leave a note on the ticket so the miss is
                     visible in Zoho rather than silently disappearing

  Student side, once the admin marks the work done (`awaiting_verification`):
    immediately       ask the student whether it is actually fixed
    +1 working day    remind them once
    +3 working days   auto-close as assumed-resolved

Nudges land at 09:00 IST on a working day -- never on a Sunday, a holiday, or at
night. The client's rule "if either side is inactive, close after 3 working days"
is implemented as the two `auto_close_*` branches; nothing else closes a ticket
except the student explicitly confirming.
"""

from datetime import timedelta

from . import workdays

SLA_WORKING_DAYS = 3
MAX_ADMIN_NUDGES = 2
STUDENT_REMINDERS = 1

# How long a half-finished operation may sit before we treat it as abandoned.
#
# Both are "the Lambda died mid-operation" recovery windows, and both must be
# comfortably longer than the Lambda timeout so we never declare a still-running
# request stuck. They are short in wall-clock terms because a student is blocked
# from raising any ticket for the whole window.
STUCK_CREATION_MINUTES = 15   # reserved a ticket, never heard back from Zoho
STUCK_PROMPT_MINUTES = 5      # reserved the resolve callback, never sent the prompt


def _at_nine(dt):
    """09:00 IST on the next working day at or after `dt`."""
    return workdays.next_working_day_start(dt)


def first_nudge_at(created_at):
    """When to first chase the admin: 09:00 on the next working day."""
    return _at_nine(created_at)


def decide(state, now=None):
    """Return the action due for this conversation, and when to look again.

    Result: {"action": <name>, "next_at": datetime|None, "reason": str}

    Actions:
      nudge_admin          -- remind the LMS admin, ticket still open
      auto_close_admin     -- SLA reached with no resolution; close and inform
      remind_student       -- chase the student for their confirmation
      auto_close_student   -- student never confirmed; close as assumed resolved
      none                 -- nothing due
    """
    now = now or workdays.now_utc()
    status = state.get("ticket_status", "none")

    if status == "open":
        return _decide_open(state, now)
    if status == "awaiting_verification":
        return _decide_awaiting(state, now)
    if status == "creating":
        return _decide_creating(state, now)
    if status == "verification_prompting":
        return _decide_prompting(state, now)
    return {"action": "none", "next_at": None, "reason": f"status={status}"}


def _decide_creating(state, now):
    """A ticket reservation that has not completed.

    Normally this lasts milliseconds: reserve, call Zoho, write the ticket id.
    It only persists if the Lambda died in between. Until the window expires we
    say nothing -- the request may still be in flight, and declaring it stuck
    would let a second message create a duplicate Zoho ticket.

    After the window we must act, because the student is blocked from raising
    ANY ticket while this sits here. We cannot safely retry (Zoho may have
    created the ticket immediately before the timeout), so we release the block
    and ask a human to check Zoho for an orphan.
    """
    started = _parse(state.get("ticket_creation_started_at"))
    if started is None:
        # No timestamp to reason about; treat as stuck rather than leaving the
        # student blocked forever.
        return {"action": "recover_stuck_creation", "next_at": None,
                "reason": "creating with no start time"}

    age = now - started
    if age < timedelta(minutes=STUCK_CREATION_MINUTES):
        return {
            "action": "none",
            "next_at": started + timedelta(minutes=STUCK_CREATION_MINUTES),
            "reason": f"ticket creation in progress ({int(age.total_seconds())}s)",
        }

    return {
        "action": "recover_stuck_creation",
        "next_at": None,
        "reason": f"ticket creation abandoned after {int(age.total_seconds())}s",
    }


def _decide_prompting(state, now):
    """A resolve callback that reserved the conversation but never sent.

    Safe to recover automatically: nothing was created in Zoho, we simply failed
    to deliver the "is it fixed?" message. Putting the ticket back to `open`
    resumes the normal admin chase, and Zoho's own retry (or the next resolve)
    will prompt the student again.
    """
    started = _parse(state.get("verification_prompting_at"))
    if started is None:
        return {"action": "recover_stuck_verification", "next_at": None,
                "reason": "prompting with no start time"}

    age = now - started
    if age < timedelta(minutes=STUCK_PROMPT_MINUTES):
        return {
            "action": "none",
            "next_at": started + timedelta(minutes=STUCK_PROMPT_MINUTES),
            "reason": f"verification prompt in progress ({int(age.total_seconds())}s)",
        }

    return {
        "action": "recover_stuck_verification",
        "next_at": None,
        "reason": f"verification prompt abandoned after {int(age.total_seconds())}s",
    }


def _decide_open(state, now):
    created = _parse(state.get("ticket_created_at"))
    if created is None:
        return {"action": "none", "next_at": None,
                "reason": "missing ticket_created_at"}

    # Compare against the deadline we STORED and PROMISED the student, not a
    # freshly recalculated day count. Those two disagree: working_days_between()
    # ticks over at midnight, but the promised deadline is 18:00 IST. Counting
    # days here closed tickets up to nine hours before the deadline the student
    # was given -- the accountability engine breaking the one promise it exists
    # to keep.
    deadline = _parse(state.get("sla_due_at")) or workdays.add_working_days(
        created, SLA_WORKING_DAYS
    )

    if now >= deadline:
        return {
            "action": "auto_close_admin",
            "next_at": None,
            "reason": f"SLA deadline {workdays.iso(deadline)} passed, no resolution",
        }

    elapsed = workdays.working_days_between(created, now)
    nudges = int(state.get("admin_nudges", 0))

    if nudges >= MAX_ADMIN_NUDGES:
        # Already chased twice; wait out the remaining time, then auto-close.
        return {
            "action": "none",
            "next_at": deadline,
            "reason": "nudge quota spent, waiting for SLA deadline",
        }

    return {
        "action": "nudge_admin",
        "next_at": _at_nine(now),
        "reason": f"nudge {nudges + 1} of {MAX_ADMIN_NUDGES}, "
                  f"{elapsed} working days elapsed",
    }


def _decide_awaiting(state, now):
    prompted = _parse(state.get("verification_prompted_at"))
    if prompted is None:
        return {"action": "none", "next_at": None,
                "reason": "missing verification_prompted_at"}

    deadline = verification_deadline(prompted)

    # Student side has gone inactive.
    if now >= deadline:
        return {
            "action": "auto_close_student",
            "next_at": None,
            "reason": f"no confirmation by {workdays.iso(deadline)}",
        }

    reminders = int(state.get("student_reminders", 0))
    if reminders >= STUDENT_REMINDERS:
        return {
            "action": "none",
            "next_at": deadline,
            "reason": "reminder sent, waiting for auto-close",
        }

    # Only chase once a full working day has passed -- otherwise the reminder
    # would land minutes after the original question and read as nagging.
    if workdays.working_days_between(prompted, now) < 1:
        return {
            "action": "none",
            "next_at": reminder_due_at(prompted),
            "reason": "waiting a working day before reminding the student",
        }

    return {
        "action": "remind_student",
        "next_at": deadline,
        "reason": f"reminder {reminders + 1} of {STUDENT_REMINDERS}",
    }


def reminder_due_at(prompted_at):
    """When to remind a student who has not answered: next working day, 09:00.

    state_store.await_verification schedules the sweeper's next wake-up for this
    moment. It previously scheduled it for the auto-close deadline instead, which
    meant the sweeper never looked at the ticket until it was already too late --
    the reminder branch above was unreachable and students who missed a single
    WhatsApp lost their ticket with no second chance.
    """
    return _at_nine(prompted_at)


def next_after_nudge(now=None):
    """When to act again after nudging the admin: 09:00 the next working day."""
    return _at_nine(now or workdays.now_utc())


def verification_deadline(prompted_at):
    """When an unconfirmed ticket auto-closes."""
    return workdays.add_working_days(prompted_at, SLA_WORKING_DAYS)


def _parse(value):
    if not value:
        return None
    try:
        return workdays.parse(value)
    except (ValueError, TypeError):
        return None
