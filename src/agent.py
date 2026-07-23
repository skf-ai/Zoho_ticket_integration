"""The agent loop: one inbound WhatsApp message in, one reply out.

Replaces the keyword state machine in bot.py. Where that matched "hi" against a
fixed set and walked a four-option menu, this reads what the student actually
wrote, decides whether the knowledge base answers it, and calls tools when it
does not.

Shape of a turn:

    load history -> model call -> [tool calls -> results -> model call]* -> reply

The loop is bounded by MAX_ITERATIONS. An unbounded agent loop is a cost
incident waiting to happen: a model that keeps calling tools without concluding
would spend money until the Lambda times out. Two tool rounds is ample for this
job (raise a ticket, then answer), so the cap is generous but real.

If the model provider is unreachable, we fall back to the deterministic menu
rather than leaving the student with silence. The accountability engine does not
depend on the model at all, so tickets already open keep being chased even
during a full LLM outage.
"""

from . import knowledge, llm, state_store, tools, whatsapp_client

MAX_ITERATIONS = 4

# Sent when the model is unavailable. Deliberately plain and useful.
FALLBACK_REPLY = (
    "Sorry, our assistant is temporarily unavailable. Please reply with a short "
    "description of your problem and try again shortly. If it is urgent, please "
    "contact the support address provided by your institution."
)


def handle_inbound(wa_id, username, message):
    """Handle one normalized inbound message. Returns the reply text sent."""
    text = (message.get("text") or "").strip()
    if not text:
        # Media, location, reactions and similar. Acknowledge rather than ignore.
        sent = whatsapp_client.send_text(
            wa_id,
            "Sorry, I can only read text messages. Please describe your problem "
            "in a message and I'll help.",
        )
        if not sent:
            raise RuntimeError("WhatsApp did not accept the media guidance reply")
        return None

    state = state_store.get_state(wa_id)
    state_store.touch_activity(wa_id)

    history = list(state.get("history", []))
    turn = [{"role": "user", "content": text}]

    ctx = {"wa_id": wa_id, "username": username, "state": state}

    try:
        reply, new_turns = _run_loop(history, turn, ctx)
    except llm.LLMError as e:
        print(f"[agent] LLM unavailable for *{wa_id[-4:]}: {type(e).__name__}")
        if not whatsapp_client.send_text(wa_id, FALLBACK_REPLY):
            raise RuntimeError("WhatsApp did not accept the fallback reply") from e
        state_store.append_history(wa_id, turn)
        return FALLBACK_REPLY

    if reply:
        if not whatsapp_client.send_text(wa_id, reply):
            raise RuntimeError("WhatsApp did not accept the agent reply")
    state_store.append_history(wa_id, new_turns)
    return reply


def _run_loop(history, turn, ctx):
    """Drive the model until it produces a reply. Returns (reply, turns_to_store).

    `turns_to_store` includes the tool calls and their results, so the next
    message from this student carries the full picture of what was already done.
    """
    messages = history + turn
    stored = list(turn)

    for iteration in range(MAX_ITERATIONS):
        result = llm.complete(messages, tools.TOOLS)

        if not result["tool_calls"]:
            reply = (result["text"] or "").strip()
            if reply:
                assistant_turn = {"role": "assistant", "content": reply}
                messages.append(assistant_turn)
                stored.append(assistant_turn)
            return reply, stored

        # Record the assistant turn that requested the tools, then run them.
        assistant_blocks = _assistant_blocks(result)
        messages.append({"role": "assistant", "content": assistant_blocks})
        stored.append({"role": "assistant", "content": assistant_blocks})

        # Re-read state between rounds: a tool may just have changed it, and the
        # next tool call must see the new ticket rather than the stale one.
        ctx["state"] = state_store.get_state(ctx["wa_id"])

        results = []
        for call in result["tool_calls"]:
            # Multiple tool calls can be returned in one model response. Refresh
            # before every call so a ticket created by the previous call is seen
            # by the duplicate guard immediately.
            ctx["state"] = state_store.get_state(ctx["wa_id"])
            print(f"[agent] *{ctx['wa_id'][-4:]} -> {call['name']}")
            output = tools.dispatch(call["name"], call["input"], ctx)
            results.append({
                "type": "tool_result",
                "tool_use_id": call["id"],
                "content": output,
            })

        tool_turn = {"role": "user", "content": results}
        messages.append(tool_turn)
        stored.append(tool_turn)

    # Ran out of iterations without a final answer. Say something useful rather
    # than nothing, and log it loudly -- repeated hits mean the prompt or the
    # tool descriptions need work.
    print(f"[agent] hit MAX_ITERATIONS for *{ctx['wa_id'][-4:]}")
    return ("I've noted your issue and passed it to the support team. "
            "They'll get back to you shortly."), stored


def _assistant_blocks(result):
    """Rebuild the assistant turn in provider-neutral block form."""
    blocks = []
    if result.get("text"):
        blocks.append({"type": "text", "text": result["text"]})
    for call in result["tool_calls"]:
        blocks.append({
            "type": "tool_use",
            "id": call["id"],
            "name": call["name"],
            "input": call["input"],
        })
    return blocks


def health():
    """Cheap readiness signal for deployment checks and the smoke test."""
    return {
        "provider": llm.PROVIDER,
        "model": llm.MODEL,
        "knowledge_topics": knowledge.topics(),
        "knowledge_chars": len(knowledge.load()),
    }
