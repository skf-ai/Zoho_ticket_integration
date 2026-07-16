"""Outbound WhatsApp messaging via the Meta Cloud API (Graph API).

Sends: plain text, an interactive category list, quick-reply buttons (Yes/No),
and pre-approved template messages (for the >24h "issue resolved?" prompt).

Tested on Day 2.
"""

import requests

from . import config


def _url():
    phone_id = config.require("whatsapp_phone_number_id")
    return f"https://graph.facebook.com/{config.GRAPH_API_VERSION}/{phone_id}/messages"


def _headers():
    return {
        "Authorization": f"Bearer {config.require('whatsapp_token')}",
        "Content-Type": "application/json",
    }


def _send(payload):
    resp = requests.post(_url(), headers=_headers(), json=payload, timeout=15)
    if resp.status_code not in (200, 201):
        print(f"WhatsApp send error ({resp.status_code}): {resp.text}")
        return False
    return True


def send_text(to, text):
    """Send a plain text message to a WhatsApp number (E.164, no '+')."""
    return _send({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    })


def send_category_list(to, categories, header="How can we help?",
                       body="Please choose a category:"):
    """Send an interactive list message with the FAQ categories.

    `categories` is a list of dicts with 'id' and 'title' (see faq.CATEGORIES).
    A list message is used because WhatsApp buttons max out at 3 and we have 4.
    """
    rows = [{"id": c["id"], "title": c["title"][:24]} for c in categories]
    return _send({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": header},
            "body": {"text": body},
            "action": {
                "button": "Choose",
                "sections": [{"title": "Categories", "rows": rows}],
            },
        },
    })


def send_yes_no(to, body, yes_id="yes", no_id="no"):
    """Send a quick-reply Yes/No button message (e.g. 'Issue solved?')."""
    return _send({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": yes_id, "title": "Yes"}},
                    {"type": "reply", "reply": {"id": no_id, "title": "No"}},
                ]
            },
        },
    })


def send_template(to, template_name, language="en", components=None):
    """Send a pre-approved template message (used for the >24h resolve prompt)."""
    template = {"name": template_name, "language": {"code": language}}
    if components:
        template["components"] = components
    return _send({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": template,
    })
