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


def _archive(wa_id, text):
    """Best-effort write to the 90-day audit archive. Must never block sending."""
    try:
        from . import media_store

        media_store.log_text(wa_id, "out", text)
    except Exception as e:  # noqa: BLE001
        print(f"[whatsapp] archive failed: {type(e).__name__}")


def send_text(to, text):
    """Send a plain text message to a WhatsApp number (E.164, no '+')."""
    ok = _send({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    })
    if ok:
        _archive(to, text)
    return ok


def send_template(to, template_name, language="en", components=None):
    """Send a pre-approved template message (used for the >24h resolve prompt)."""
    template = {"name": template_name, "language": {"code": language}}
    if components:
        template["components"] = components
    ok = _send({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": template,
    })
    if ok:
        _archive(to, f"[template:{template_name}]")
    return ok


def get_media_url(media_id):
    """Resolve a WhatsApp media id to a short-lived download URL."""
    resp = requests.get(
        f"https://graph.facebook.com/{config.GRAPH_API_VERSION}/{media_id}",
        headers={"Authorization": f"Bearer {config.require('whatsapp_token')}"},
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"WhatsApp media lookup error ({resp.status_code}): {resp.text}")
        return None
    return resp.json().get("url")


def download_media(media_id):
    """Download a WhatsApp media object (e.g. a student's screenshot).

    Returns (content_bytes, content_type), or None on any failure. Meta's media
    URLs are short-lived and themselves require the same bearer token to fetch --
    a plain GET without it 401s.
    """
    url = get_media_url(media_id)
    if not url:
        return None
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {config.require('whatsapp_token')}"},
        timeout=20,
    )
    if resp.status_code != 200:
        print(f"WhatsApp media download error ({resp.status_code})")
        return None
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
