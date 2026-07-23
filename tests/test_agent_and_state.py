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
