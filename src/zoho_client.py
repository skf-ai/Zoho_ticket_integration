"""Zoho Desk API client: token refresh, create ticket, close ticket.

Credentials come from src/config.py (Secrets Manager in AWS, env vars locally).
"""

import html
import re
import requests
import time

from . import config

_access_token = None
_access_token_expires_at = 0.0

# Fields the admin needs to act, in a request -- bolded in the rendered ticket
# so they stand out from the surrounding prose rather than blending into it.
_HIGHLIGHT_LABELS = (
    "Registered email", "Old email", "New email", "Department",
    "Course name", "Student",
)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _format_description(description):
    """Escape, linkify emails, bold the fields the admin needs most, and give
    every line real paragraph spacing -- Zoho renders the description as HTML,
    so plain "\\n" collapses lines flush against each other with zero gap
    otherwise (a single <br> adds no visual space at all).

    Bolding/linking is done here in code, not left to the model, so the
    formatting is reliable regardless of exact wording variations.
    """
    text = html.escape(description)
    text = _EMAIL_RE.sub(lambda m: f'<a href="mailto:{m.group(0)}">{m.group(0)}</a>', text)
    for label in _HIGHLIGHT_LABELS:
        text = re.sub(rf"(?m)^{re.escape(label)}:", f"<b>{label}:</b>", text)
    # Each line becomes its own block with bottom margin, so labelled fields
    # read as a clean list instead of a wall stuck together. A blank line
    # (from "\n\n" in the source, e.g. between the description and the "---"
    # footer) becomes its own empty, margined block too, which reads as a
    # clear paragraph break rather than just a slightly bigger gap.
    lines = text.split("\n")
    return "".join(f'<div style="margin:0 0 10px 0;">{line or "&nbsp;"}</div>' for line in lines)


def get_access_token():
    """Exchange the long-lived refresh token for a short-lived access token."""
    global _access_token, _access_token_expires_at
    if _access_token and time.monotonic() < _access_token_expires_at:
        return _access_token
    print("Refreshing Zoho access token...")
    payload = {
        "refresh_token": config.require("zoho_refresh_token"),
        "client_id": config.require("zoho_client_id"),
        "client_secret": config.require("zoho_client_secret"),
        "grant_type": "refresh_token",
    }
    resp = requests.post(config.ZOHO_TOKEN_URL, data=payload, timeout=15)
    resp.raise_for_status()
    token_data = resp.json()
    if "access_token" not in token_data:
        print(f"Error in token response: {token_data}")
        return None
    print("Successfully refreshed access token.")
    _access_token = token_data["access_token"]
    # Zoho normally returns expires_in=3600. Refresh one minute early and use a
    # conservative fallback if the field is absent.
    lifetime = max(int(token_data.get("expires_in", 3600)) - 60, 60)
    _access_token_expires_at = time.monotonic() + lifetime
    return _access_token


def _headers(access_token):
    return {
        "Authorization": f"Zoho-oauthtoken {access_token}",
        "orgId": config.require("zoho_org_id"),
        "Content-Type": "application/json",
    }


def find_contact_by_phone(phone, access_token):
    """Return an existing Zoho contact id matching this phone, or None."""
    resp = requests.get(
        f"{config.ZOHO_API_BASE}/contacts/search",
        headers=_headers(access_token),
        params={"phone": phone},
        timeout=15,
    )
    if resp.status_code == 200:
        data = resp.json().get("data", [])
        if data:
            return data[0]["id"]
        return None
    resp.raise_for_status()


def create_contact(name, phone, access_token):
    """Create a Zoho contact (lastName is mandatory in Zoho Desk)."""
    resp = requests.post(
        f"{config.ZOHO_API_BASE}/contacts",
        headers=_headers(access_token),
        json={"lastName": name or phone, "phone": phone},
        timeout=15,
    )
    if resp.status_code == 200:
        return resp.json().get("id")
    print(f"Error creating contact ({resp.status_code}): {resp.text}")
    return None


def find_or_create_contact(phone, name, access_token=None):
    """Find a contact by phone, or create one. Returns the contact id."""
    access_token = access_token or get_access_token()
    if not access_token:
        return None
    return (find_contact_by_phone(phone, access_token)
            or create_contact(name, phone, access_token))


def create_ticket(subject, description, contact_id, category=None):
    """Create a Zoho Desk ticket. Returns the ticket dict, or None on failure.

    `category` (e.g. "Login Issue") is stored on the ticket so support and
    reporting can see which FAQ path the user came from.
    """
    access_token = get_access_token()
    if not access_token:
        print("Could not create ticket: access token missing.")
        return None

    data = {
        "subject": subject,
        "description": _format_description(description),
        "contactId": contact_id,
        "departmentId": config.require("zoho_department_id"),
    }
    if category:
        data["category"] = category

    resp = requests.post(
        f"{config.ZOHO_API_BASE}/tickets",
        headers=_headers(access_token),
        json=data,
        timeout=15,
    )
    # Zoho Desk returns 200 on ticket creation.
    if resp.status_code == 200:
        print("Ticket created successfully!")
        return resp.json()
    print(f"Error creating ticket ({resp.status_code}): {resp.text}")
    return None


def list_tickets(limit=60):
    """Newest tickets from the Zoho Desk archive, for the admin Reports view.

    The dashboard's own store keeps only one live record per student; Zoho is
    the permanent per-ticket history. Returns a list of plain dicts, or None
    when Zoho is unreachable (the dashboard then says so instead of lying).
    """
    access_token = get_access_token()
    if not access_token:
        return None
    resp = requests.get(
        f"{config.ZOHO_API_BASE}/tickets",
        headers=_headers(access_token),
        params={"limit": min(limit, 100), "sortBy": "-createdTime"},
        timeout=15,
    )
    if resp.status_code == 204:
        return []
    if resp.status_code != 200:
        print(f"Error listing tickets ({resp.status_code}): {resp.text[:200]}")
        return None
    out = []
    for t in resp.json().get("data", []):
        out.append({
            "number": str(t.get("ticketNumber") or t.get("id") or "-"),
            "subject": str(t.get("subject") or "")[:80],
            "status": str(t.get("status") or "-"),
            "category": str(t.get("category") or "-"),
            "created": str(t.get("createdTime") or "")[:10],
        })
    return out


def close_ticket(ticket_id, comment=None):
    """Set a ticket's status to Closed. Returns True on success.

    Used when the user replies "Yes, resolved" to the feedback prompt.
    """
    access_token = get_access_token()
    if not access_token:
        return False

    resp = requests.patch(
        f"{config.ZOHO_API_BASE}/tickets/{ticket_id}",
        headers=_headers(access_token),
        json={"status": "Closed"},
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"Error closing ticket {ticket_id} ({resp.status_code}): {resp.text}")
        return False

    if comment:
        add_comment(ticket_id, comment, access_token)
    print(f"Ticket {ticket_id} closed.")
    return True


def reopen_ticket(ticket_id):
    """Set a ticket's status back to Open (student said it is still broken).

    Without this the ticket keeps showing the admin's "Resolved" status in the
    Zoho UI even though the system has reopened it internally.
    """
    access_token = get_access_token()
    if not access_token:
        return False
    resp = requests.patch(
        f"{config.ZOHO_API_BASE}/tickets/{ticket_id}",
        headers=_headers(access_token),
        json={"status": "Open"},
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"Error reopening ticket {ticket_id} ({resp.status_code}): {resp.text}")
        return False
    print(f"Ticket {ticket_id} set back to Open.")
    return True


def add_attachment(ticket_id, filename, content, content_type=None):
    """Upload a file (e.g. a student's WhatsApp screenshot) onto a ticket.

    Multipart upload, so no `Content-Type: application/json` header here --
    `requests` sets the correct multipart boundary itself from `files=`.
    """
    access_token = get_access_token()
    if not access_token:
        return False
    headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}",
        "orgId": config.require("zoho_org_id"),
    }
    files = {"file": (filename, content, content_type or "application/octet-stream")}
    resp = requests.post(
        f"{config.ZOHO_API_BASE}/tickets/{ticket_id}/attachments",
        headers=headers,
        files=files,
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        print(f"Error attaching file to {ticket_id} ({resp.status_code}): {resp.text[:200]}")
        return False
    return True


def add_comment(ticket_id, content, access_token=None):
    """Add a comment to a ticket (used when the user says 'not resolved')."""
    access_token = access_token or get_access_token()
    if not access_token:
        return False
    resp = requests.post(
        f"{config.ZOHO_API_BASE}/tickets/{ticket_id}/comments",
        headers=_headers(access_token),
        json={"content": content, "isPublic": False},
        timeout=15,
    )
    if resp.status_code not in (200, 201):
        print(f"Error commenting on {ticket_id} ({resp.status_code}): {resp.text}")
        return False
    return True
