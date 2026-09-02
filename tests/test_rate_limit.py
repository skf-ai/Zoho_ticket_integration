"""Abuse brakes: per-student hourly limit and global daily AI budget."""

from unittest.mock import patch

from src import handler, state_store


def _event():
    return {"requestContext": {"http": {"method": "POST", "path": "/whatsapp"}},
            "body": "{}"}


def _run(user_count, day_count):
    """Drive one inbound message with the counters forced to given values."""
    calls = {"agent": 0, "texts": []}
    with patch.object(handler, "_signature_ok", return_value=True), \
         patch.object(handler.knowledge, "unresolved_placeholders", return_value=[]), \
         patch.object(handler, "_extract_messages",
                      return_value=[("919000001111", "T", {"message_id": "m1"})]), \
         patch.object(handler.state_store, "mark_processed", return_value=True), \
         patch.object(handler.state_store, "complete_processed") as done, \
         patch.object(handler.state_store, "bump_rate", return_value=user_count), \
         patch.object(handler.state_store, "bump_ai_budget", return_value=day_count), \
         patch.object(handler.agent, "handle_inbound",
                      side_effect=lambda *a: calls.__setitem__("agent", calls["agent"] + 1)), \
         patch.object(handler.whatsapp_client, "send_text",
                      side_effect=lambda to, text: calls["texts"].append(text)):
        resp = handler.lambda_handler(_event(), None)
    calls["status"] = resp["statusCode"]
    calls["completed"] = done.called
    return calls


def test_under_limits_processes_normally():
    out = _run(user_count=3, day_count=40)
    assert out["agent"] == 1
    assert out["texts"] == []
    assert out["status"] == 200


def test_over_user_limit_blocks_ai_and_notifies_once():
    limit = state_store.RATE_LIMIT_PER_HOUR
    first_over = _run(user_count=limit + 1, day_count=40)
    assert first_over["agent"] == 0          # the model is never called
    assert len(first_over["texts"]) == 1     # one polite notice
    assert "pausing" in first_over["texts"][0]
    assert first_over["status"] == 200       # never ask Meta to redeliver spam
    assert first_over["completed"]           # claim completed, not released

    deep_over = _run(user_count=limit + 7, day_count=40)
    assert deep_over["agent"] == 0
    assert deep_over["texts"] == []          # then silence


def test_over_daily_budget_blocks_everyone():
    budget = state_store.DAILY_AI_BUDGET
    out = _run(user_count=2, day_count=budget + 5)
    assert out["agent"] == 0
    assert out["status"] == 200


def test_broken_brake_fails_open():
    with patch.object(handler.state_store, "bump_rate", side_effect=RuntimeError):
        assert handler._over_rate_limit("919000001111", None) is False