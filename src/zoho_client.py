"""Zoho Desk API client: token refresh, create ticket, close ticket.

Credentials come from src/config.py (Secrets Manager in AWS, env vars locally).
"""

import requests

from . import config


def get_access_token():
    """Exchange the long-lived refresh token for a short-lived access token."""
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
    return token_data["access_token"]


def _headers(access_token):
    return {
        "Authorization": f"Zoho-oauthtoken {access_token}",
        "orgId": config.require("zoho_org_id"),
        "Content-Type": "application/json",
    }


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
        "description": description,
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
