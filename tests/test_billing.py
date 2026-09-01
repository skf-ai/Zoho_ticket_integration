"""Billing sources: graceful degradation and correct parsing, no real network."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src import admin_dashboard, billing

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


@patch("src.billing.config.get", return_value="")
def test_openai_unavailable_without_admin_key(_get):
    result = billing.fetch_openai(NOW)
    assert result["source"] == "unavailable"
    assert "admin" in result["detail"].lower() or "key" in result["detail"].lower()


@patch("src.billing.config.get", return_value="sk-admin-test")
@patch("src.billing.requests.get")
def test_openai_admin_key_rejected_reports_why(mock_get, _cfg):
    mock_get.return_value = MagicMock(status_code=403)
    result = billing.fetch_openai(NOW)
    assert result["source"] == "unavailable"
    assert "ADMIN key" in result["detail"]


@patch("src.billing.config.get", return_value="sk-admin-test")
@patch("src.billing.requests.get")
def test_openai_sums_month_buckets(mock_get, _cfg):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"data": [
            {"results": [{"amount": {"value": 1.25}}]},
            {"results": [{"amount": {"value": 0.75}}, {"amount": {"value": 0.5}}]},
        ]},
    )
    result = billing.fetch_openai(NOW)
    assert result["source"] == "live"
    assert result["amount"] == 2.5
    assert result["currency"] == "USD"


@patch("src.billing.requests.get")
def test_meta_parses_conversation_cost(mock_get):
    with patch("src.billing.config.get",
               side_effect=lambda k: {"whatsapp_token": "tok",
                                      "whatsapp_waba_id": "991"}.get(k, "")):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"conversation_analytics": {"data": [
                {"data_points": [{"cost": 12.5, "conversation": 40},
                                 {"cost": 2.5, "conversation": 10}]},
            ]}},
        )
        result = billing.fetch_meta(NOW)
    assert result["source"] == "live"
    assert result["amount"] == 15.0
    assert result["currency"] == "INR"
    assert "50" in result["detail"]


def test_render_badges_live_and_estimate():
    metrics = admin_dashboard.aggregate([], now=NOW)
    live = {"openai": {"source": "live", "amount": 2.5, "currency": "USD",
                       "detail": "month to date"},
            "meta": {"source": "unavailable", "amount": None, "currency": "",
                     "detail": "needs whatsapp_waba_id"},
            "aws": {"source": "live", "amount": 3.1, "currency": "USD",
                    "detail": "Lambda $1.10"}}
    page = admin_dashboard.render(metrics, live)
    assert page.count("badge live") >= 3          # 2 live cards + legend
    assert "$2.50" in page and "$3.10" in page
    assert "needs whatsapp_waba_id" in page       # honest failure reason shown


def test_render_all_estimates_without_billing():
    page = admin_dashboard.render(admin_dashboard.aggregate([], now=NOW))
    assert page.count("badge est") >= 3   # all three provider cards fall back
    assert "ESTIMATE" in page
