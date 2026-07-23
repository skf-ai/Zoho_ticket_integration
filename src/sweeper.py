"""Scheduled worker that executes whatever the accountability engine says is due.

Runs on an EventBridge schedule (hourly). Each run queries the
`due-index` for conversations whose `next_action_at` has passed, asks sla.decide()
what to do, and does it.

## Why a sweeper rather than a timer per ticket

One scheduled Lambda costs pennies a month regardless of how many tickets are
open. The alternatives -- an EventBridge Scheduler entry per ticket, or a Step
Functions execution per ticket -- add per-ticket cost, per-ticket cleanup, and a
second place where state can drift out of sync with DynamoDB. At hundreds of open
tickets, a single indexed query every hour is both cheaper and simpler to
reason about. Hourly granularity is sufficient when deadlines are
measured in working days.

## Why every outbound message here is a template

These messages are sent hours or days after the student last wrote. That is
outside WhatsApp's 24-hour free-form window, so only Meta-approved templates can
be delivered. The exact template bodies are in deployment/whatsapp-templates.md
and must be approved before this worker can do anything useful.

The sweeper is idempotent per action: state is advanced immediately after each
action, so a retried or overlapping run cannot double-send.
"""

import os

from . import config, sla, state_store, whatsapp_client, workdays, zoho_client

# WhatsApp number of the LMS administrator who receives nudges (E.164, no '+').
ADMIN_WA_ID_KEY = "lms_admin_wa_id"

BATCH_LIMIT = int(os.environ.get("SWEEP_BATCH_LIMIT", "200"))

TPL_ADMIN_NUDGE = "ticket_pending_admin"
TPL_STUDENT_VERIFY = "issue_resolved_check"
TPL_STUDENT_REMIND = "ticket_reminder_student"
TPL_STUDENT_CLOSED = "ticket_auto_closed"


def lambda_handler(event, context):
    """EventBridge entry point."""
    processed = run_once()
    return {"statusCode": 200, "processed": processed}


def run_once():
    """Process one batch of due conversations. Returns a per-action count."""
    due = state_store.due_now(limit=BATCH_LIMIT)
    counts = {}
    failures = 0

    for item in due:
        wa_id = item.get("wa_id")
        decision = sla.decide(item)
        action = decision["action"]
        counts[action] = counts.get(action, 0) + 1

        print(f"[sweeper] *{str(wa_id)[-4:]} ticket={item.get('ticket_id')} "
              f"action={action} reason={decision['reason']}")

        try:
            _perform(action, item, decision)
        except Exception as e:  # noqa: BLE001 - one bad item must not stop the batch
            failures += 1
            print(f"[sweeper] FAILED {action} for *{str(wa_id)[-4:]}: "
                  f"{type(e).__name__}")

    if counts:
        print(f"[sweeper] batch complete: {counts}")
    if failures:
        # Preserve per-item isolation, but fail the invocation after the batch so
        # EventBridge retries and the CloudWatch error alarm becomes meaningful.
        raise RuntimeError(f"{failures} scheduled action(s) failed")
    return counts


def _perform(action, item, decision):
    wa_id = item["wa_id"]
    ticket_id = item.get("ticket_id")

    if action == "nudge_admin":
        # Only count the nudge if the message actually left. Counting an unsent
        # nudge burns the quota and lets the ticket auto-close having never
        # reached a human -- the precise failure this system exists to prevent.
        if _nudge_admin(item):
            state_store.record_nudge(wa_id, sla.next_after_nudge())
        else:
            print(f"[sweeper] admin nudge NOT sent for ticket {ticket_id}; "
                  f"will retry next working day")
            state_store.set_next_action(wa_id, sla.next_after_nudge())

    elif action == "auto_close_admin":
        _auto_close_admin(item)

    elif action == "remind_student":
        sent = whatsapp_client.send_template(
            wa_id, TPL_STUDENT_REMIND,
            components=_body_params([str(ticket_id)]),
        )
        if sent:
            state_store.record_student_reminder(
                wa_id, decision.get("next_at") or workdays.now_utc()
            )
        else:
            print(f"[sweeper] student reminder NOT sent for ticket {ticket_id}")
            state_store.set_next_action(wa_id, sla.next_after_nudge())

    elif action == "auto_close_student":
        _auto_close_student(item)

    elif action == "alert_stuck_creation":
        # Zoho may have created the ticket immediately before a timeout. A blind
        # retry could duplicate it, so require an operator to reconcile safely.
        raise RuntimeError(
            f"ticket creation for *{str(wa_id)[-4:]} is stuck; reconcile Zoho "
            "before releasing the DynamoDB reservation"
        )

    elif action == "none":
        # Nothing due yet; move the wake-up forward WITHOUT counting a nudge.
        if decision.get("next_at"):
            state_store.set_next_action(wa_id, decision["next_at"])
        else:
            # No next action and nothing to do: the item would otherwise be
            # re-read on every sweep forever. Log it and check again tomorrow.
            print(f"[sweeper] {wa_id} stuck with no next action "
                  f"({decision['reason']}) -- deferring 1 working day")
            state_store.set_next_action(wa_id, sla.next_after_nudge())


# --- individual actions --------------------------------------------------------

def _nudge_admin(item):
    """Remind the LMS admin that a ticket is waiting on them.

    Returns True only if WhatsApp accepted the message. The caller must not
    count a nudge that did not send.
    """
    admin = config.get(ADMIN_WA_ID_KEY)
    if not admin:
        print("[sweeper] ALERT: no lms_admin_wa_id configured -- the admin is "
              "not being chased at all. Add it to the secret store.")
        return False

    ticket_id = str(item.get("ticket_id"))
    due = _friendly(item.get("sla_due_at"))
    nudge_no = int(item.get("admin_nudges", 0)) + 1

    sent = whatsapp_client.send_template(
        admin, TPL_ADMIN_NUDGE,
        components=_body_params([ticket_id, item.get("category", "general"), due]),
    )
    if sent:
        print(f"[sweeper] nudge {nudge_no} sent to admin for ticket {ticket_id}")
    return bool(sent)


def _auto_close_admin(item):
    """SLA reached with no resolution. Close, inform the student, record why.

    The note on the Zoho ticket matters: an auto-close that leaves no trace would
    hide exactly the failure this system exists to surface.
    """
    wa_id = item["wa_id"]
    ticket_id = item.get("ticket_id")

    commented = zoho_client.add_comment(
        ticket_id,
        "Auto-closed by the WhatsApp support system: the 3 working day service "
        "level was reached without the ticket being resolved. The student has "
        "been told they can reopen it by messaging again.",
    )
    if not commented:
        raise RuntimeError(f"could not add audit comment to Zoho ticket {ticket_id}")
    if not zoho_client.close_ticket(ticket_id):
        raise RuntimeError(f"Zoho did not close ticket {ticket_id}")

    sent = whatsapp_client.send_template(
        wa_id, TPL_STUDENT_CLOSED, components=_body_params([str(ticket_id)]),
    )
    if not sent:
        raise RuntimeError(f"could not notify student that ticket {ticket_id} closed")
    state_store.close_ticket(wa_id, reason="sla_expired_no_resolution")


def _auto_close_student(item):
    """Student never confirmed. Close as assumed resolved."""
    wa_id = item["wa_id"]
    ticket_id = item.get("ticket_id")

    commented = zoho_client.add_comment(
        ticket_id,
        "Auto-closed by the WhatsApp support system: the student did not confirm "
        "within 3 working days of being asked. Assumed resolved.",
    )
    if not commented:
        raise RuntimeError(f"could not add audit comment to Zoho ticket {ticket_id}")
    if not zoho_client.close_ticket(ticket_id):
        raise RuntimeError(f"Zoho did not close ticket {ticket_id}")

    sent = whatsapp_client.send_template(
        wa_id, TPL_STUDENT_CLOSED, components=_body_params([str(ticket_id)]),
    )
    if not sent:
        raise RuntimeError(f"could not notify student that ticket {ticket_id} closed")
    state_store.close_ticket(wa_id, reason="student_no_confirmation")


# --- helpers -------------------------------------------------------------------

def _body_params(values):
    """Build WhatsApp template body parameters in positional order."""
    return [{
        "type": "body",
        "parameters": [{"type": "text", "text": str(v)} for v in values],
    }]


def _friendly(iso_ts):
    if not iso_ts:
        return "shortly"
    try:
        return workdays.to_ist(workdays.parse(iso_ts)).strftime("%A %d %B")
    except (ValueError, TypeError):
        return "shortly"
