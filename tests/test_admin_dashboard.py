"""Admin dashboard: aggregation correctness and route protection."""

from datetime import datetime, timezone
from unittest.mock import patch

from src import admin_dashboard, handler

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _items():
    return [
        {   # closed quickly, no nudges -- the good case
            "wa_id": "919500089638",
            "ticket_status": "closed",
            "category": "login",
            "ticket_created_at": "2026-08-25T10:00:00Z",
            "closed_at": "2026-08-26T10:00:00Z",
            "closed_reason": "student_confirmed",
            "admin_nudges": 0,
            "history": ["a", "b", "c", "d"],
        },
        {   # open and overdue, already nudged twice
            "wa_id": "918888877777",
            "ticket_id": "1054",
            "ticket_status": "open",
            "category": "login",
            "ticket_created_at": "2026-08-20T10:00:00Z",
            "sla_due_at": "2026-08-25T10:00:00Z",
            "due_bucket": "DUE",
            "next_action_at": "2026-08-27T10:00:00Z",
            "admin_nudges": 2,
            "history": ["a", "b"],
        },
        {   # awaiting the student's yes/no
            "wa_id": "917777766666",
            "ticket_id": "1055",
            "ticket_status": "awaiting_verification",
            "category": "grades",
            "ticket_created_at": "2026-08-27T10:00:00Z",
            "verification_prompted_at": "2026-08-28T09:00:00Z",
            "student_reminders": 1,
            "history": [],
        },
        {   # pure Q&A conversation, never a ticket
            "wa_id": "916666655555",
            "ticket_status": "none",
            "history": ["a", "b"],
        },
    ]


def test_aggregate_counts_and_categories():
    m = admin_dashboard.aggregate(_items(), now=NOW)
    assert m["conversations"] == 4
    assert m["tickets_total"] == 3
    assert m["open"] == 1 and m["waiting"] == 1 and m["closed"] == 1
    assert m["overdue"] == 1
    assert m["by_category"] == {"login": 2, "grades": 1}
    assert m["avg_days_to_close"] == 1.0
    assert m["pct_closed_without_nudge"] == 100.0


def test_aggregate_cost_estimates():
    m = admin_dashboard.aggregate(_items(), now=NOW)
    # 2 nudges + 1 reminder + 1 verification prompt + 1 close notice = 5 sends
    assert m["template_sends"] == 5
    assert m["ai_turns"] == 4  # 8 history messages -> 4 turns
    assert abs(m["meta_cost_inr"] - 5 * admin_dashboard.TEMPLATE_INR) < 1e-6


def test_render_masks_numbers_and_shows_states():
    html_page = admin_dashboard.render(admin_dashboard.aggregate(_items(), now=NOW))
    assert "919500089638" not in html_page          # full numbers never rendered
    assert "*9638" in html_page
    assert "awaiting student" in html_page
    assert "overdue" in html_page


def test_render_zoho_archive_section():
    metrics = admin_dashboard.aggregate(_items(), now=NOW)
    archive = [
        {"number": "107", "subject": "[URGENT] Cannot log in", "status": "Closed",
         "category": "login", "created": "2026-08-27"},
        {"number": "110", "subject": "Grades missing", "status": "Open",
         "category": "grades", "created": "2026-09-02"},
    ]
    page = admin_dashboard.render(metrics, None, archive)
    assert "#107" in page and "Grades missing" in page
    assert "full Zoho Desk archive" in page
    # archive categories drive the Reports category bars
    assert "grades" in page

    unreachable = admin_dashboard.render(metrics, None, None)
    assert "archive unreachable" in unreachable


def _event(key):
    qs = {"key": key} if key is not None else None
    return {"requestContext": {"http": {"method": "GET", "path": "/admin"}},
            "queryStringParameters": qs}


@patch("src.handler.config.get")
def test_admin_route_404_when_key_unset(mock_get):
    mock_get.return_value = ""
    assert handler.lambda_handler(_event("anything"), None)["statusCode"] == 404


@patch("src.handler.config.get")
def test_admin_route_404_on_wrong_key(mock_get):
    mock_get.return_value = "correct-key"
    assert handler.lambda_handler(_event("wrong"), None)["statusCode"] == 404
    assert handler.lambda_handler(_event(None), None)["statusCode"] == 404


@patch("src.zoho_client.list_tickets", return_value=[])
@patch("src.billing.fetch_all", return_value=None)
@patch("src.handler.state_store.scan_conversations", return_value=[])
@patch("src.handler.config.get")
def test_admin_route_serves_html_on_correct_key(mock_get, _scan, _billing, _zoho):
    mock_get.return_value = "correct-key"
    resp = handler.lambda_handler(_event("correct-key"), None)
    assert resp["statusCode"] == 200
    assert "text/html" in resp["headers"]["Content-Type"]
    assert "Admin Panel" in resp["body"]
