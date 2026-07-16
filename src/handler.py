"""AWS Lambda entry point.

Routes three kinds of request (API Gateway HTTP API / proxy integration):

  GET  /whatsapp      -> Meta webhook verification (hub.challenge handshake)
  POST /whatsapp      -> inbound WhatsApp message  -> bot.handle_inbound
  POST /zoho-webhook  -> Zoho Desk 'ticket resolved' -> send feedback prompt

The verification logic mirrors the original ingress Lambda (Node) stub, ported
to Python. Signature verification (X-Hub-Signature-256) is added on Day 6/7.
"""

import json

from . import bot, config, faq, state_store, whatsapp_client, zoho_client


def lambda_handler(event, context):
    print(f"Event: {json.dumps(event)[:2000]}")

    method = (
        event.get("requestContext", {}).get("http", {}).get("method")
        or event.get("httpMethod")
    )
    path = (
        event.get("requestContext", {}).get("http", {}).get("path")
        or event.get("rawPath")
        or event.get("path")
        or ""
    )

    # --- Meta webhook verification handshake --------------------------------
    if method == "GET":
        return _verify_webhook(event)

    if method == "POST":
        if "zoho" in path:
            return _handle_zoho_webhook(event)
        return _handle_whatsapp_inbound(event)

    return _resp(405, "Method not allowed")


# --- GET: Meta verification ----------------------------------------------------

def _verify_webhook(event):
    qp = event.get("queryStringParameters") or {}
    verify_token = config.get("whatsapp_verify_token")
    if verify_token and qp.get("hub.verify_token") != verify_token:
        return _resp(403, "Bad verify token")
    challenge = qp.get("hub.challenge")
    if challenge:
        return _resp(200, challenge)
    return _resp(400, "Missing challenge")


# --- POST: inbound WhatsApp message -------------------------------------------

def _handle_whatsapp_inbound(event):
    body = event.get("body")
    if isinstance(body, str):
        try:
            body = json.loads(body or "{}")
        except json.JSONDecodeError:
            body = {}

    for wa_id, username, message in _extract_messages(body):
        try:
            bot.handle_inbound(wa_id, username, message)
        except Exception as e:  # noqa: BLE001 - never fail Meta's webhook
            print(f"[handler] bot error for {wa_id}: {e}")

    # Always 200 so Meta doesn't retry/disable the webhook.
    return _resp(200, "ok")


def _extract_messages(body):
    """Yield (wa_id, username, normalized_message) from a Meta webhook payload.

    Normalized message: {"type": "text"|"button", "text": str, "id": str|None}
    """
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            contacts = value.get("contacts", [])
            username = ""
            if contacts:
                username = contacts[0].get("profile", {}).get("name", "")
            for msg in value.get("messages", []):
                wa_id = msg.get("from")
                yield wa_id, username, _normalize_message(msg)


def _normalize_message(msg):
    mtype = msg.get("type")
    if mtype == "text":
        return {"type": "text", "text": msg.get("text", {}).get("body", ""), "id": None}
    if mtype == "interactive":
        inter = msg.get("interactive", {})
        if inter.get("type") == "list_reply":
            r = inter["list_reply"]
            return {"type": "button", "text": r.get("title", ""), "id": r.get("id")}
        if inter.get("type") == "button_reply":
            r = inter["button_reply"]
            return {"type": "button", "text": r.get("title", ""), "id": r.get("id")}
    if mtype == "button":  # template quick-reply
        b = msg.get("button", {})
        return {"type": "button", "text": b.get("text", ""), "id": b.get("payload")}
    return {"type": mtype or "unknown", "text": "", "id": None}


# --- POST: Zoho resolve webhook (Day 5) ---------------------------------------

def _handle_zoho_webhook(event):
    """Zoho fires this when a ticket is Resolved. Send the feedback prompt.

    Wired fully on Day 5 (needs the Zoho Workflow Rule configured to POST here
    with the ticket id). For now it demonstrates the intended handling.
    """
    body = event.get("body")
    if isinstance(body, str):
        try:
            body = json.loads(body or "{}")
        except json.JSONDecodeError:
            body = {}

    ticket_id = str(body.get("ticketId") or body.get("id") or "")
    if not ticket_id:
        return _resp(400, "Missing ticketId")

    wa_id = state_store.find_wa_id_by_ticket(ticket_id)
    if not wa_id:
        print(f"[zoho-webhook] no user mapped to ticket {ticket_id}")
        return _resp(200, "no mapping")

    # >24h window => must be a pre-approved template (submitted Day 1).
    whatsapp_client.send_template(wa_id, template_name="issue_resolved_check")
    state_store.set_state(wa_id, state_store.STEP_AWAITING_FEEDBACK,
                          ticket_id=ticket_id)
    return _resp(200, "prompt sent")


def _resp(status, body):
    return {"statusCode": status, "body": body}
