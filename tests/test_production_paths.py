import json
from unittest.mock import patch

from src import handler, llm, sweeper, tools


def test_whatsapp_signature_fails_closed_without_secret():
    with patch("src.handler.config.get", return_value=""):
        assert handler._signature_ok({"headers": {}}, "{}") is False


def test_zoho_webhook_rejects_missing_shared_secret():
    event = {"body": json.dumps({"ticketId": "123"}), "headers": {}}
    with patch("src.handler.config.get", return_value="configured-secret"):
        response = handler._handle_zoho_webhook(event)
    assert response["statusCode"] == 401


def test_zoho_webhook_does_not_advance_when_whatsapp_fails():
    event = {
        "body": json.dumps({"ticketId": "123"}),
        "headers": {"X-Webhook-Secret": "secret"},
    }
    item = {"wa_id": "919999999999", "ticket_status": "open"}
    with (
        patch("src.handler.config.get", return_value="secret"),
        patch("src.handler.state_store.find_by_ticket", return_value=item),
        patch("src.handler.state_store.begin_verification", return_value=True),
        patch("src.handler.whatsapp_client.send_template", return_value=False),
        patch("src.handler.state_store.release_verification") as release,
        patch("src.handler.state_store.await_verification") as advance,
    ):
        response = handler._handle_zoho_webhook(event)
    assert response["statusCode"] == 503
    advance.assert_not_called()
    release.assert_called_once_with("919999999999")


def test_llm_sdk_exception_is_normalized():
    with (
        patch.object(llm, "PROVIDER", "anthropic"),
        patch("src.llm._call_anthropic", side_effect=TimeoutError("slow")),
    ):
        try:
            llm.complete([], [])
            assert False, "expected LLMError"
        except llm.LLMError:
            pass


def test_failed_inbound_is_released_and_requests_retry():
    body = {
        "entry": [{"changes": [{"value": {
            "contacts": [{"profile": {"name": "Student"}}],
            "messages": [{"id": "wamid.1", "from": "9199", "type": "text",
                          "text": {"body": "help"}}],
        }}]}]
    }
    with (
        patch("src.handler._signature_ok", return_value=True),
        patch("src.handler.knowledge.unresolved_placeholders", return_value=[]),
        patch("src.handler.state_store.mark_processed", return_value=True),
        patch("src.handler.agent.handle_inbound", side_effect=RuntimeError("down")),
        patch("src.handler.state_store.release_processed") as release,
    ):
        response = handler._handle_whatsapp_inbound({"body": json.dumps(body)})
    assert response["statusCode"] == 500
    release.assert_called_once_with("wamid.1")


def test_auto_close_keeps_state_when_zoho_close_fails():
    item = {"wa_id": "9199", "ticket_id": "123"}
    with (
        patch("src.sweeper.zoho_client.add_comment", return_value=True),
        patch("src.sweeper.zoho_client.close_ticket", return_value=False),
        patch("src.sweeper.state_store.close_ticket") as local_close,
    ):
        try:
            sweeper._auto_close_admin(item)
            assert False, "expected failure"
        except RuntimeError:
            pass
    local_close.assert_not_called()


def test_auto_close_keeps_state_when_student_notification_fails():
    item = {"wa_id": "9199", "ticket_id": "123"}
    with (
        patch("src.sweeper.zoho_client.add_comment", return_value=True),
        patch("src.sweeper.zoho_client.close_ticket", return_value=True),
        patch("src.sweeper.whatsapp_client.send_template", return_value=False),
        patch("src.sweeper.state_store.close_ticket") as local_close,
    ):
        try:
            sweeper._auto_close_student(item)
            assert False, "expected failure"
        except RuntimeError:
            pass
    local_close.assert_not_called()


def test_ticket_creation_reservation_prevents_external_duplicate():
    ctx = {"wa_id": "9199", "username": "Student",
           "state": {"ticket_status": "none"}}
    args = {"subject": "Login problem", "description": "Cannot sign in",
            "category": "login"}
    with (
        patch("src.tools.state_store.reserve_ticket_creation", return_value=False),
        patch("src.tools.state_store.get_state",
              return_value={"ticket_status": "creating"}),
        patch("src.tools.zoho_client.create_ticket") as create,
    ):
        result = tools._raise_ticket(args, ctx)
    assert "already being created" in result
    create.assert_not_called()


def test_ticket_reservation_released_when_zoho_is_unreachable():
    ctx = {"wa_id": "9199", "username": "Student",
           "state": {"ticket_status": "none"}}
    args = {"subject": "Login problem", "description": "Cannot sign in",
            "category": "login"}
    with (
        patch("src.tools.state_store.reserve_ticket_creation", return_value=True),
        patch("src.tools.zoho_client.find_or_create_contact", return_value=None),
        patch("src.tools.state_store.release_ticket_creation") as release,
    ):
        tools._raise_ticket(args, ctx)
    release.assert_called_once_with("9199")
