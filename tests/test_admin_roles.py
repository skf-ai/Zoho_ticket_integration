"""Per-person admin-panel keys: role matching and Archana's minimal view."""

from unittest.mock import patch

from src import admin_dashboard, handler


def _secrets(**overrides):
    values = {"admin_dashboard_key": "owner-key",
              "admin_key_kalyani": "kalyani-key",
              "admin_key_naidu": "naidu-key",
              "admin_key_archana": "archana-key"}
    values.update(overrides)
    return lambda k: values.get(k, "")


@patch("src.handler.config.get")
def test_owner_key_matches_owner(mock_get):
    mock_get.side_effect = _secrets()
    assert handler._match_admin_key("owner-key") == "owner"


@patch("src.handler.config.get")
def test_each_named_key_matches_its_role(mock_get):
    mock_get.side_effect = _secrets()
    assert handler._match_admin_key("kalyani-key") == "kalyani"
    assert handler._match_admin_key("naidu-key") == "naidu"
    assert handler._match_admin_key("archana-key") == "archana"


@patch("src.handler.config.get")
def test_wrong_or_empty_key_matches_nothing(mock_get):
    mock_get.side_effect = _secrets()
    assert handler._match_admin_key("not-a-real-key") is None
    assert handler._match_admin_key("") is None


@patch("src.handler.config.get")
def test_unset_role_key_never_matches(mock_get):
    # archana's key is blank/unset -- an empty supplied value must not match
    mock_get.side_effect = _secrets(admin_key_archana="")
    assert handler._match_admin_key("") is None


def test_archana_view_all_clear():
    metrics = admin_dashboard.aggregate([])
    page = admin_dashboard.render_overdue_only(metrics)
    assert ">0<" in page
    assert "All clear" in page
    assert "Naidu ji" not in page  # no instruction text when nothing is due


def test_archana_view_flags_overdue_with_instruction():
    items = [{
        "wa_id": "919000000001", "ticket_id": "1", "ticket_status": "open",
        "category": "login", "ticket_created_at": "2026-09-01T00:00:00Z",
        "due_bucket": "DUE", "next_action_at": "2020-01-01T00:00:00Z",
    }]
    metrics = admin_dashboard.aggregate(items)
    page = admin_dashboard.render_overdue_only(metrics)
    assert ">1<" in page
    assert "Something needs attention" in page
    assert "Naidu ji" in page and "Kalyani" in page


def _event(key):
    return {"requestContext": {"http": {"method": "GET", "path": "/admin"}},
            "queryStringParameters": {"key": key} if key is not None else None}


@patch("src.handler.state_store.scan_conversations", return_value=[])
@patch("src.handler.config.get")
def test_archana_route_serves_minimal_page(mock_get, _scan):
    mock_get.side_effect = _secrets()
    resp = handler.lambda_handler(_event("archana-key"), None)
    assert resp["statusCode"] == 200
    assert "Daily Check" in resp["body"]
    assert "Reports" not in resp["body"]  # not the full dashboard nav


@patch("src.zoho_client.list_tickets", return_value=[])
@patch("src.billing.fetch_all", return_value=None)
@patch("src.handler.state_store.scan_conversations", return_value=[])
@patch("src.handler.config.get")
def test_kalyani_route_serves_full_dashboard(mock_get, _scan, _billing, _zoho):
    mock_get.side_effect = _secrets()
    resp = handler.lambda_handler(_event("kalyani-key"), None)
    assert resp["statusCode"] == 200
    assert "Admin Panel" in resp["body"]


@patch("src.handler.config.get")
def test_bogus_key_still_404s(mock_get):
    mock_get.side_effect = _secrets()
    resp = handler.lambda_handler(_event("nonsense"), None)
    assert resp["statusCode"] == 404
