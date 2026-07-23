"""Outbound WhatsApp messaging via the Meta Cloud API (Graph API).

Sends plain text and pre-approved template messages.

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
