from unittest.mock import MagicMock, patch

import pytest

import simulate
from src import agent, llm, state_store


def test_llm_outage_sends_deterministic_fallback_and_keeps_message():
    message = {"type": "text", "text": "help", "message_id": "m1"}
    with (
        patch("src.agent.state_store.get_state",
              return_value={"history": [], "ticket_status": "none"}),
        patch("src.agent.state_store.touch_activity"),
        patch("src.agent._run_loop", side_effect=llm.LLMError("down")),
        patch("src.agent.whatsapp_client.send_text", return_value=True) as send,
        patch("src.agent.state_store.append_history") as append,
    ):
        reply = agent.handle_inbound("9199", "Student", message)
    assert reply == agent.FALLBACK_REPLY
    send.assert_called_once_with("9199", agent.FALLBACK_REPLY)
    append.assert_called_once()


def test_image_gets_screenshot_specific_reply():
    message = {"type": "image", "text": "", "message_id": "m1", "id": "media123"}
    with (
        patch("src.agent.whatsapp_client.send_text", return_value=True) as send,
        patch("src.agent.whatsapp_client.download_media", return_value=None),
    ):
        agent.handle_inbound("9199", "Student", message)
    reply = send.call_args[0][1]
    assert "screenshot" in reply.lower()
    assert "describe" in reply.lower()


def test_image_with_open_ticket_attaches_immediately():
    message = {"type": "image", "text": "", "message_id": "m1", "id": "media123"}
    with (
        patch("src.agent.whatsapp_client.send_text", return_value=True),
        patch("src.agent.whatsapp_client.download_media",
              return_value=(b"fake-bytes", "image/jpeg")),
        patch("src.agent.state_store.get_state",
              return_value={"history": [], "ticket_status": "open",
                             "ticket_id": "555"}),
        patch("src.agent.media_store.store_image", return_value="conversations/9199/1-media123.jpg"),
        patch("src.agent.zoho_client.add_attachment", return_value=True) as attach,
        patch("src.agent.state_store.add_pending_attachment") as pending,
    ):
        agent.handle_inbound("9199", "Student", message)
    attach.assert_called_once()
    assert attach.call_args[0][0] == "555"
    pending.assert_not_called()


def test_image_with_no_ticket_holds_pending_attachment():
    message = {"type": "image", "text": "", "message_id": "m1", "id": "media123"}
    with (
        patch("src.agent.whatsapp_client.send_text", return_value=True),
        patch("src.agent.whatsapp_client.download_media",
              return_value=(b"fake-bytes", "image/jpeg")),
        patch("src.agent.state_store.get_state",
              return_value={"history": [], "ticket_status": "none"}),
        patch("src.agent.media_store.store_image", return_value="conversations/9199/1-media123.jpg"),
        patch("src.agent.zoho_client.add_attachment") as attach,
        patch("src.agent.state_store.add_pending_attachment") as pending,
    ):
        agent.handle_inbound("9199", "Student", message)
    attach.assert_not_called()
    pending.assert_called_once_with(
        "9199", "conversations/9199/1-media123.jpg", "whatsapp-media123.jpeg", "image/jpeg"
    )


def test_other_media_gets_generic_text_only_reply():
    message = {"type": "audio", "text": "", "message_id": "m1"}
    with patch("src.agent.whatsapp_client.send_text", return_value=True) as send:
        agent.handle_inbound("9199", "Student", message)
    reply = send.call_args[0][1]
    assert "only read text" in reply.lower()


def test_failed_whatsapp_reply_raises_for_webhook_retry():
    message = {"type": "text", "text": "help", "message_id": "m1"}
    with (
        patch("src.agent.state_store.get_state",
              return_value={"history": [], "ticket_status": "none"}),
        patch("src.agent.state_store.touch_activity"),
        patch("src.agent._run_loop", return_value=("reply", [])),
        patch("src.agent.whatsapp_client.send_text", return_value=False),
    ):
        with pytest.raises(RuntimeError):
            agent.handle_inbound("9199", "Student", message)


def test_history_trimming_always_starts_with_user_turn():
    old = [{"role": "assistant", "content": "old"}]
    old += [{"role": "user", "content": f"message {i}"} for i in range(20)]
    table = MagicMock()
    table.get_item.return_value = {
        "Item": {"wa_id": "9199", "history": old, "ticket_status": "none"}
    }
    with patch("src.state_store._t", return_value=table):
        history = state_store.append_history(
            "9199", [{"role": "assistant", "content": "reply"}]
        )
    assert history
    assert history[0]["role"] == "user"
    assert len(history) <= state_store.MAX_HISTORY_MESSAGES


def test_scripted_mock_does_not_close_when_student_says_broken():
    simulate.STORE.items.clear()
    simulate.STORE.items[simulate.STUDENT] = {
        "wa_id": simulate.STUDENT,
        "history": [],
        "ticket_id": "1001",
        "ticket_status": "awaiting_verification",
    }
    result = simulate.mock_complete(
        [{"role": "user", "content": "no it is still broken"}], []
    )
    assert result["tool_calls"][0]["name"] == "confirm_resolution"
    assert result["tool_calls"][0]["input"]["resolved"] is False
