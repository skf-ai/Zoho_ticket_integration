"""Conversation logic: the 'brain' between WhatsApp and Zoho.

Implements the architecture-diagram flow:
  Hi -> categories -> FAQ answer -> Solved? -> (No/Others) create ticket.

Fully wired on Days 3-4. Each handler updates DynamoDB state so the next inbound
message from the same user continues where they left off.
"""

from . import faq, state_store, whatsapp_client, zoho_client

GREETINGS = {"hi", "hello", "hey", "start", "menu"}


def handle_inbound(wa_id, username, message):
    """Route one inbound WhatsApp message.

    `message` is a normalized dict from the ingress handler:
        {"type": "text"|"button", "text": <str>, "id": <button/list id or None>}
    """
    state = state_store.get_state(wa_id)
    step = state.get("step", state_store.STEP_IDLE)
    text = (message.get("text") or "").strip()
    choice = message.get("id")  # button/list-row id when the user tapped one

    # A greeting always (re)starts the flow.
    if text.lower() in GREETINGS:
        return _present_categories(wa_id)

    if step == state_store.STEP_AWAITING_CATEGORY:
        return _handle_category_choice(wa_id, choice or text)

    if step == state_store.STEP_AWAITING_SOLVED:
        return _handle_solved(wa_id, username, choice or text, state)

    if step == state_store.STEP_AWAITING_QUERY:
        return _handle_free_query(wa_id, username, text, state)

    # Default: greet + show menu.
    return _present_categories(wa_id)


def _present_categories(wa_id):
    whatsapp_client.send_category_list(wa_id, faq.CATEGORIES)
    state_store.set_state(wa_id, state_store.STEP_AWAITING_CATEGORY)


def _handle_category_choice(wa_id, choice):
    category = faq.BY_ID.get(choice)
    if not category:
        whatsapp_client.send_text(
            wa_id, "Sorry, I didn't get that. Please pick a category."
        )
        return _present_categories(wa_id)

    # "Others" -> collect a free-text query, skip the FAQ answer.
    if category["id"] == "others":
        whatsapp_client.send_text(
            wa_id, "Please describe your issue and we'll raise a ticket."
        )
        state_store.set_state(wa_id, state_store.STEP_AWAITING_QUERY,
                              category=category["id"])
        return

    # FAQ path: send the answer, then ask if it solved the problem.
    answer = faq.category_answer(category["id"]) or "Here's some help."
    whatsapp_client.send_text(wa_id, answer)
    whatsapp_client.send_yes_no(wa_id, "Did this solve your issue?")
    state_store.set_state(wa_id, state_store.STEP_AWAITING_SOLVED,
                          category=category["id"])


def _handle_solved(wa_id, username, answer, state):
    if _is_yes(answer):
        whatsapp_client.send_text(wa_id, "Great! Glad we could help. \U0001F44D")
        state_store.clear_state(wa_id)
        return
    # "No" -> escalate to a ticket using the category context.
    category_id = state.get("category")
    _escalate(wa_id, username, category_id,
              description=f"User reported the FAQ for '{faq.category_title(category_id)}'"
                          " did not resolve their issue.")


def _handle_free_query(wa_id, username, text, state):
    if not text:
        whatsapp_client.send_text(wa_id, "Please type your question.")
        return
    _escalate(wa_id, username, state.get("category"), description=text)


def _escalate(wa_id, username, category_id, description):
    """Create a Zoho ticket and remember it against this user."""
    category_title = faq.category_title(category_id) if category_id else "General"
    subject = f"[{category_title}] WhatsApp query from {username or wa_id}"

    # NOTE: Zoho create_ticket needs a contactId. Mapping wa_id -> Zoho contact
    # is finalized on Day 4 (find-or-create contact by phone/username).
    ticket = zoho_client.create_ticket(
        subject=subject,
        description=f"From WhatsApp {wa_id} ({username}).\n\n{description}",
        contact_id=_resolve_contact_id(wa_id, username),
        category=category_title,
    )

    if ticket and ticket.get("id"):
        state_store.set_state(wa_id, state_store.STEP_IDLE,
                              category=category_id, ticket_id=str(ticket["id"]))
        whatsapp_client.send_text(
            wa_id,
            "We've raised a support ticket for you. Our team will get back to "
            "you shortly.",
        )
    else:
        whatsapp_client.send_text(
            wa_id, "Sorry, we couldn't raise a ticket right now. Please try again."
        )


def _resolve_contact_id(wa_id, username):
    """Placeholder — Day 4 will find-or-create a Zoho contact by phone number.

    For now returns empty; Day 4 implements the Zoho contacts lookup/create."""
    return ""


def _is_yes(answer):
    a = (answer or "").strip().lower()
    return a in {"yes", "y", "resolved"}
