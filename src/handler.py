"""AWS Lambda entry point.

Routes four kinds of request (API Gateway HTTP API / proxy integration):

  GET  /whatsapp      -> Meta webhook verification (hub.challenge handshake)
  POST /whatsapp      -> inbound WhatsApp message -> agent.handle_inbound
  POST /zoho-webhook  -> Zoho fires when a ticket is Resolved -> ask the student
  GET  /health        -> readiness probe for deployment checks

Two rules govern everything here:

  * Always return 200 to Meta. A non-200 makes Meta retry, and repeated failures
    degrade the number's quality rating and can get the webhook disabled. Errors
    are logged and swallowed, never surfaced as a status code.
  * Never process the same message twice. Meta redelivers; state_store's
    conditional claim makes that safe.
"""

import hashlib
import hmac
import json

from . import agent, config, sla, state_store, whatsapp_client, workdays

TPL_STUDENT_VERIFY = "issue_resolved_check"


def lambda_handler(event, context):
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

    if method == "GET":
        if "health" in path:
            return _resp(200, json.dumps(agent.health()))
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


# --- POST: inbound WhatsApp message --------------------------------------------

def _handle_whatsapp_inbound(event):
    raw = event.get("body") or ""

    if not _signature_ok(event, raw):
        # Someone posted to our endpoint without Meta's signature. Do not process
        # it, but still answer 200 so we reveal nothing about what we accept.
        print("[handler] rejected inbound with bad or missing signature")
        return _resp(200, "ok")

    try:
        body = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return _resp(200, "ok")

    for wa_id, username, message in _extract_messages(body):
        message_id = message.get("message_id")
        if message_id and not state_store.mark_processed(message_id):
            print(f"[handler] duplicate delivery of {message_id}, skipping")
            continue
        try:
            agent.handle_inbound(wa_id, username, message)
        except Exception as e:  # noqa: BLE001 - never fail Meta's webhook
            print(f"[handler] agent error for {wa_id}: {e}")

    return _resp(200, "ok")


def _signature_ok(event, raw_body):
    """Verify Meta's X-Hub-Signature-256 over the raw request body.

    Without this, anyone who learns the endpoint URL can post fabricated messages
    and make the agent raise tickets or reply to arbitrary numbers. The secret is
    the Meta app secret; if it is not configured we log loudly and allow through,
    so the system still works before that secret is filled in -- but the
    deployment checklist treats an unset app secret as a go-live blocker.
    """
    app_secret = config.get("whatsapp_app_secret")
    if not app_secret:
        print("[handler] WARNING: whatsapp_app_secret unset, signature not verified")
        return True

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    provided = headers.get("x-hub-signature-256", "")
    if not provided.startswith("sha256="):
        return False

    expected = "sha256=" + hmac.new(
        app_secret.encode("utf-8"),
        raw_body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, provided)


def _extract_messages(body):
    """Yield (wa_id, username, normalized_message) from a Meta webhook payload."""
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            contacts = value.get("contacts", [])
            username = ""
            if contacts:
                username = contacts[0].get("profile", {}).get("name", "")
            for msg in value.get("messages", []):
                yield msg.get("from"), username, _normalize_message(msg)


def _normalize_message(msg):
    """Flatten Meta's message shapes into {type, text, id, message_id}.

    Button and list replies are converted to their visible title text, so the
    agent reads a tap the same way it reads someone typing the same words.
    """
    base = {"message_id": msg.get("id")}
    mtype = msg.get("type")

    if mtype == "text":
        return {**base, "type": "text",
                "text": msg.get("text", {}).get("body", ""), "id": None}

    if mtype == "interactive":
        inter = msg.get("interactive", {})
        reply = inter.get("list_reply") or inter.get("button_reply") or {}
        return {**base, "type": "button",
                "text": reply.get("title", ""), "id": reply.get("id")}

    if mtype == "button":  # template quick-reply
        b = msg.get("button", {})
        return {**base, "type": "button",
                "text": b.get("text", ""), "id": b.get("payload")}

    return {**base, "type": mtype or "unknown", "text": "", "id": None}


# --- POST: Zoho resolve webhook ------------------------------------------------

def _handle_zoho_webhook(event):
    """Zoho fires this when a ticket is set to Resolved.

    Resolved is not Closed. We ask the student whether it is genuinely fixed and
    move the ticket to awaiting_verification; only their confirmation closes it.
    """
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _resp(400, "Bad JSON")

    ticket_id = str(body.get("ticketId") or body.get("id") or "")
    if not ticket_id:
        return _resp(400, "Missing ticketId")

    item = state_store.find_by_ticket(ticket_id)
    if not item:
        # A ticket raised outside WhatsApp, or one we have already closed.
        print(f"[zoho-webhook] no conversation mapped to ticket {ticket_id}")
        return _resp(200, "no mapping")

    wa_id = item["wa_id"]
    if item.get("ticket_status") == "awaiting_verification":
        print(f"[zoho-webhook] {ticket_id} already awaiting verification")
        return _resp(200, "already prompted")

    now = workdays.now_utc()
    whatsapp_client.send_template(
        wa_id, TPL_STUDENT_VERIFY,
        components=[{
            "type": "body",
            "parameters": [{"type": "text", "text": ticket_id}],
        }],
    )
    state_store.await_verification(
        wa_id, prompted_at=now, auto_close_at=sla.verification_deadline(now)
    )
    print(f"[zoho-webhook] asked {wa_id} to confirm ticket {ticket_id}")
    return _resp(200, "prompt sent")


def _resp(status, body):
    return {"statusCode": status, "body": body}
