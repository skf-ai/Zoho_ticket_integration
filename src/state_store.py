"""Per-conversation state in DynamoDB.

One item per WhatsApp number. The item holds three things:

  1. Conversation memory -- the recent message history the agent reasons over.
  2. Ticket lifecycle -- which ticket this student has open and what stage it is at.
  3. The next scheduled action -- when the accountability engine should next
     nudge, prompt, or auto-close.

## Table shape

    Table: whatsapp_conversation_state
      PK: wa_id (S)

    GSI "ticket-index"
      PK: ticket_id (S)
      -- lets the Zoho webhook map a resolved ticket back to a student in one
         lookup. The previous implementation did a full table Scan for this,
         which gets slower and more expensive with every student ever served.

    GSI "due-index"
      PK: due_bucket (S)   -- always the literal "DUE"
      SK: next_action_at (S, ISO-8601 UTC, lexicographically sortable)
      -- the sweeper queries this one index for everything now due. A single
         partition is fine at this volume (hundreds of open tickets, not
         millions) and keeps the query to one cheap call per sweep.

Both indexes are *sparse*: when a ticket closes we delete `ticket_id`,
`due_bucket`, and `next_action_at`, so finished conversations fall out of the
indexes entirely and cost nothing to query around.

Ticket status values: none | open | awaiting_verification | closed
"""

import os
from datetime import timedelta

import boto3
from boto3.dynamodb.conditions import Key

from . import config, workdays

DUE_BUCKET = "DUE"

# How many messages of history to keep. Long enough for a support conversation
# to stay coherent, short enough to bound the token cost of every turn.
MAX_HISTORY_MESSAGES = 20
STATE_RETENTION_DAYS = int(os.environ.get("STATE_RETENTION_DAYS", "90"))

_table = None


def _t():
    global _table
    if _table is None:
        _table = boto3.resource(
            "dynamodb", region_name=config.AWS_REGION
        ).Table(config.STATE_TABLE)
    return _table


# --- reads ---------------------------------------------------------------------

def get_state(wa_id):
    """Return this student's state, or a fresh empty one."""
    item = _t().get_item(Key={"wa_id": wa_id}).get("Item")
    if not item:
        return {"wa_id": wa_id, "history": [], "ticket_status": "none"}
    item.setdefault("history", [])
    item.setdefault("ticket_status", "none")
    return item


def find_by_ticket(ticket_id):
    """Map a ticket id back to a conversation. Used by the Zoho webhook."""
    resp = _t().query(
        IndexName="ticket-index",
        KeyConditionExpression=Key("ticket_id").eq(str(ticket_id)),
        Limit=1,
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def due_now(limit=100):
    """Conversations whose next scheduled action is due. Drives the sweeper."""
    items = []
    start_key = None
    cutoff = workdays.iso(workdays.now_utc())
    while len(items) < limit:
        kwargs = {
            "IndexName": "due-index",
            "KeyConditionExpression": (
                Key("due_bucket").eq(DUE_BUCKET)
                & Key("next_action_at").lte(cutoff)
            ),
            "Limit": limit - len(items),
        }
        if start_key:
            kwargs["ExclusiveStartKey"] = start_key
        resp = _t().query(**kwargs)
        items.extend(resp.get("Items", []))
        start_key = resp.get("LastEvaluatedKey")
        if not start_key:
            break
    return items


# --- conversation memory -------------------------------------------------------

def append_history(wa_id, messages):
    """Append turns to the conversation and trim to the retention window.

    Trimming keeps the *most recent* messages. We drop from the front rather than
    summarising: support conversations are short, and a summarisation step would
    add cost and a failure mode for little gain.
    """
    state = get_state(wa_id)
    history = list(state.get("history", [])) + list(messages)

    if len(history) > MAX_HISTORY_MESSAGES:
        history = history[-MAX_HISTORY_MESSAGES:]
        # Never start the window with a tool result -- it would reference a
        # tool_use block that has been trimmed away, which providers reject.
        while history and _is_orphan_tool_result(history[0]):
            history.pop(0)
        # Provider conversations must begin with a user turn. A raw count can
        # otherwise cut immediately before an assistant tool-use block.
        while history and history[0].get("role") != "user":
            history.pop(0)
        while history and _is_orphan_tool_result(history[0]):
            history.pop(0)

    _t().update_item(
        Key={"wa_id": wa_id},
        UpdateExpression="SET history = :h, last_activity_at = :now, expires_at = :ttl",
        ExpressionAttributeValues={
            ":h": history,
            ":now": workdays.iso(workdays.now_utc()),
            ":ttl": _retention_epoch(),
        },
    )
    return history


def _is_orphan_tool_result(message):
    content = message.get("content")
    if not isinstance(content, list):
        return False
    return any(b.get("type") == "tool_result" for b in content)


def clear_history(wa_id):
    """Drop conversation memory but keep ticket state. Used on '/reset'."""
    _t().update_item(
        Key={"wa_id": wa_id},
        UpdateExpression="SET history = :empty",
        ExpressionAttributeValues={":empty": []},
    )


# --- ticket lifecycle ----------------------------------------------------------

def reserve_ticket_creation(wa_id):
    """Atomically reserve the right to create this student's next ticket.

    This closes the race where two different inbound message IDs both read an
    empty state and create separate Zoho tickets before either writes DynamoDB.
    """
    from botocore.exceptions import ClientError

    now = workdays.now_utc()
    review_at = now + timedelta(minutes=10)
    try:
        _t().update_item(
            Key={"wa_id": wa_id},
            UpdateExpression=(
                "SET ticket_status = :creating, ticket_creation_started_at = :now, "
                "due_bucket = :bucket, next_action_at = :review"
            ),
            ConditionExpression=(
                "attribute_not_exists(ticket_status) OR "
                "ticket_status IN (:none, :closed)"
            ),
            ExpressionAttributeValues={
                ":creating": "creating",
                ":none": "none",
                ":closed": "closed",
                ":now": workdays.iso(now),
                ":bucket": DUE_BUCKET,
                ":review": workdays.iso(review_at),
            },
        )
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def release_ticket_creation(wa_id):
    """Release a reservation when Zoho definitely did not create a ticket."""
    _t().update_item(
        Key={"wa_id": wa_id},
        UpdateExpression=("SET ticket_status = :none REMOVE "
                          "ticket_creation_started_at, due_bucket, next_action_at"),
        ConditionExpression="ticket_status = :creating",
        ExpressionAttributeValues={":none": "none", ":creating": "creating"},
    )

def open_ticket(wa_id, ticket_id, category, created_at, sla_due_at):
    """Record a newly raised ticket and schedule the first admin nudge."""
    from . import sla  # imported here to avoid a circular import at module load

    first_nudge = sla.first_nudge_at(created_at)
    _t().update_item(
        Key={"wa_id": wa_id},
        UpdateExpression=(
            "SET ticket_id = :tid, ticket_status = :st, category = :cat, "
            "ticket_created_at = :created, sla_due_at = :due, "
            "admin_nudges = :zero, due_bucket = :bucket, next_action_at = :next "
            "REMOVE ticket_creation_started_at"
        ),
        ConditionExpression="ticket_status = :creating",
        ExpressionAttributeValues={
            ":tid": str(ticket_id),
            ":st": "open",
            ":creating": "creating",
            ":cat": category,
            ":created": workdays.iso(created_at),
            ":due": workdays.iso(sla_due_at),
            ":zero": 0,
            ":bucket": DUE_BUCKET,
            ":next": workdays.iso(first_nudge),
        },
    )


def record_nudge(wa_id, next_action_at):
    """Increment the admin nudge counter and schedule the following action."""
    _t().update_item(
        Key={"wa_id": wa_id},
        UpdateExpression=(
            "SET admin_nudges = if_not_exists(admin_nudges, :zero) + :one, "
            "last_nudge_at = :now, next_action_at = :next"
        ),
        ExpressionAttributeValues={
            ":zero": 0,
            ":one": 1,
            ":now": workdays.iso(workdays.now_utc()),
            ":next": workdays.iso(next_action_at),
        },
    )


def begin_verification(wa_id):
    """Atomically reserve the resolve webhook so concurrent callbacks send once."""
    from botocore.exceptions import ClientError

    now = workdays.now_utc()
    stale_before = now - timedelta(minutes=5)
    try:
        _t().update_item(
            Key={"wa_id": wa_id},
            UpdateExpression=("SET ticket_status = :prompting, "
                              "verification_prompting_at = :now"),
            ConditionExpression=(
                "ticket_status = :open OR (ticket_status = :prompting AND "
                "verification_prompting_at < :stale)"
            ),
            ExpressionAttributeValues={":prompting": "verification_prompting",
                                       ":open": "open",
                                       ":now": workdays.iso(now),
                                       ":stale": workdays.iso(stale_before)},
        )
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def release_verification(wa_id):
    """Return to open when Meta rejects the verification template."""
    _t().update_item(
        Key={"wa_id": wa_id},
        UpdateExpression="SET ticket_status = :open REMOVE verification_prompting_at",
        ConditionExpression="ticket_status = :prompting",
        ExpressionAttributeValues={":open": "open",
                                   ":prompting": "verification_prompting"},
    )


def await_verification(wa_id, prompted_at, auto_close_at=None):
    """Admin marked the work done; we have asked the student to confirm.

    The next wake-up is the *reminder* time, not the auto-close time. Waking at
    the auto-close time skipped the reminder entirely, so a student who missed
    one message lost their ticket without ever being chased. `auto_close_at` is
    accepted for backwards compatibility and ignored -- sla.decide() derives the
    deadline from verification_prompted_at.
    """
    from . import sla

    _t().update_item(
        Key={"wa_id": wa_id},
        UpdateExpression=(
            "SET ticket_status = :st, verification_prompted_at = :now, "
            "student_reminders = :zero, "
            "due_bucket = :bucket, next_action_at = :next "
            "REMOVE verification_prompting_at"
        ),
        ConditionExpression="ticket_status = :prompting",
        ExpressionAttributeValues={
            ":st": "awaiting_verification",
            ":prompting": "verification_prompting",
            ":now": workdays.iso(prompted_at),
            ":zero": 0,
            ":bucket": DUE_BUCKET,
            ":next": workdays.iso(sla.reminder_due_at(prompted_at)),
        },
    )


def set_next_action(wa_id, next_action_at):
    """Move a conversation's wake-up time without counting a nudge.

    Kept separate from record_nudge() on purpose: the sweeper previously used
    record_nudge() for the 'nothing due yet' case, which incremented the
    admin-reminder counter for reminders that were never sent. The ticket then
    hit its nudge quota early, the admin was chased fewer times than designed,
    and the ticket auto-closed with nobody having been contacted.
    """
    _t().update_item(
        Key={"wa_id": wa_id},
        UpdateExpression="SET next_action_at = :next",
        ExpressionAttributeValues={":next": workdays.iso(next_action_at)},
    )


def reopen_ticket(wa_id, reopened_at):
    """Student said it is still broken. Back to open, clock restarted."""
    from . import sla

    _t().update_item(
        Key={"wa_id": wa_id},
        UpdateExpression=(
            "SET ticket_status = :st, admin_nudges = :zero, "
            "sla_due_at = :due, due_bucket = :bucket, next_action_at = :next "
            "REMOVE verification_prompted_at"
        ),
        ExpressionAttributeValues={
            ":st": "open",
            ":zero": 0,
            ":due": workdays.iso(workdays.add_working_days(reopened_at, 3)),
            ":bucket": DUE_BUCKET,
            ":next": workdays.iso(sla.first_nudge_at(reopened_at)),
        },
    )


def close_ticket(wa_id, reason):
    """Close out a ticket and drop the item from both sparse indexes.

    Removing ticket_id, due_bucket and next_action_at is what takes this
    conversation out of the sweeper's queue -- without it, a closed ticket would
    be re-processed on every sweep forever.
    """
    _t().update_item(
        Key={"wa_id": wa_id},
        UpdateExpression=(
            "SET ticket_status = :st, closed_at = :now, closed_reason = :reason, "
            "expires_at = :ttl "
            "REMOVE ticket_id, due_bucket, next_action_at"
        ),
        ExpressionAttributeValues={
            ":st": "closed",
            ":now": workdays.iso(workdays.now_utc()),
            ":reason": reason,
            ":ttl": _retention_epoch(),
        },
    )


def record_student_reminder(wa_id, next_action_at):
    """Count a reminder sent to the student and set the next wake-up."""
    _t().update_item(
        Key={"wa_id": wa_id},
        UpdateExpression=(
            "SET student_reminders = if_not_exists(student_reminders, :z) + :one, "
            "next_action_at = :next"
        ),
        ExpressionAttributeValues={
            ":z": 0,
            ":one": 1,
            ":next": workdays.iso(next_action_at),
        },
    )


def mark_processed(message_id):
    """Claim a WhatsApp message id. Returns False if it was already handled.

    Meta retries a webhook whenever we do not answer 200 fast enough, and can
    redeliver the same message more than once regardless. Without this claim, a
    retry would run the agent twice and could raise two tickets for one problem.

    The claim is a conditional write on a reserved key in the same table, with a
    TTL so these rows clean themselves up. Conditional-write semantics make the
    check atomic even when two Lambdas process the redelivery concurrently.
    """
    from botocore.exceptions import ClientError

    now = workdays.now_utc()
    try:
        _t().put_item(
            Item={
                "wa_id": f"msg#{message_id}",
                "processed_at": workdays.iso(now),
                # DynamoDB TTL expects epoch seconds. 24h is far longer than
                # Meta's retry window.
                "expires_at": int(now.timestamp()) + 86400,
            },
            ConditionExpression="attribute_not_exists(wa_id)",
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def complete_processed(message_id):
    """Mark a claimed message complete while retaining the deduplication row."""
    _t().update_item(
        Key={"wa_id": f"msg#{message_id}"},
        UpdateExpression="SET processing_status = :done, completed_at = :now",
        ExpressionAttributeValues={
            ":done": "completed",
            ":now": workdays.iso(workdays.now_utc()),
        },
    )


def release_processed(message_id):
    """Release a claim after failure so a provider retry can process it again."""
    _t().delete_item(Key={"wa_id": f"msg#{message_id}"})


def touch_activity(wa_id):
    """Record that the student just said something. Inactivity timers read this."""
    _t().update_item(
        Key={"wa_id": wa_id},
        UpdateExpression="SET last_activity_at = :now, expires_at = :ttl",
        ExpressionAttributeValues={
            ":now": workdays.iso(workdays.now_utc()),
            ":ttl": _retention_epoch(),
        },
    )


def _retention_epoch():
    """DynamoDB TTL for inactive conversation data (processed rows use 24h)."""
    return int(workdays.now_utc().timestamp()) + STATE_RETENTION_DAYS * 86400
