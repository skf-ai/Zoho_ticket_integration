"""Per-user conversation state, stored in DynamoDB.

WhatsApp webhooks are stateless, so the bot needs to remember where each user is
in the flow (which category they picked, whether we're waiting for a free-text
query, which ticket is theirs). One item per WhatsApp number.

Table: config.STATE_TABLE
  partition key: wa_id (string)  -- the user's WhatsApp number
  attributes:    step, category, ticket_id, updated_at

Also supports reverse lookup (ticket_id -> wa_id) for the resolve loop, via a
scan fallback; a GSI on ticket_id can be added later if volume grows.

Tested on Day 2.
"""

import boto3

from . import config

# Conversation steps.
STEP_IDLE = "idle"                # nothing in progress / start
STEP_AWAITING_CATEGORY = "awaiting_category"
STEP_AWAITING_SOLVED = "awaiting_solved"      # sent FAQ, waiting Yes/No
STEP_AWAITING_QUERY = "awaiting_query"        # "Others", waiting free text
STEP_AWAITING_FEEDBACK = "awaiting_feedback"  # ticket resolved, waiting Yes/No

_table = None


def _get_table():
    global _table
    if _table is None:
        _table = boto3.resource(
            "dynamodb", region_name=config.AWS_REGION
        ).Table(config.STATE_TABLE)
    return _table


def get_state(wa_id):
    """Return the state dict for a user, or a fresh idle state."""
    resp = _get_table().get_item(Key={"wa_id": wa_id})
    return resp.get("Item") or {"wa_id": wa_id, "step": STEP_IDLE}


def set_state(wa_id, step, category=None, ticket_id=None):
    """Create/replace a user's state. `updated_at` is passed by the caller-free
    design as a server timestamp would require it; we store step/category/ticket
    only and rely on DynamoDB item overwrite semantics."""
    item = {"wa_id": wa_id, "step": step}
    if category is not None:
        item["category"] = category
    if ticket_id is not None:
        item["ticket_id"] = ticket_id
    _get_table().put_item(Item=item)
    return item


def clear_state(wa_id):
    """Reset a user back to idle (end of a completed flow)."""
    _get_table().put_item(Item={"wa_id": wa_id, "step": STEP_IDLE})


def find_wa_id_by_ticket(ticket_id):
    """Reverse lookup used by the resolve loop. Scans for the matching ticket.

    Fine for low volume; add a GSI on ticket_id if this table grows large.
    """
    resp = _get_table().scan(
        FilterExpression="ticket_id = :t",
        ExpressionAttributeValues={":t": str(ticket_id)},
    )
    items = resp.get("Items", [])
    return items[0]["wa_id"] if items else None
