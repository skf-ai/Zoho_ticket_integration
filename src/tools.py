"""Tool definitions and dispatch for the support agent.

## Security model

The agent holds tools that mutate real tickets, and every input it sees is
untrusted text written by a student. The defences are structural, not just
prompt instructions, because prompt instructions can be argued with:

  * No tool takes a ticket id. The ticket a tool acts on is looked up server-side
    from the conversation state of the WhatsApp number that sent the message. A
    student therefore cannot reference, read, or close another student's ticket
    no matter what they type.
  * `confirm_resolution` is rejected unless that conversation is genuinely
    awaiting verification. A student cannot talk the agent into closing a ticket
    the admin has not marked resolved.
  * `raise_ticket` is idempotent per conversation: if an open ticket already
    exists, it is returned rather than creating a duplicate. Protects against
    both model retries and Meta's webhook redeliveries.

Every tool returns a short plain-text result for the model, and never raises --
an exception inside a tool would abort the webhook and lose the student's
message.
"""

from . import state_store, workdays, zoho_client

SLA_WORKING_DAYS = 3

TOOLS = [
    {
        "name": "raise_ticket",
        "description": (
            "Raise a support ticket for the LMS administrator when you cannot "
            "resolve the student's problem from the knowledge base, or when the "
            "fix requires administrator access. Use this once per problem; if the "
            "student already has an open ticket it will be returned instead of "
            "creating a second one."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "One short line naming the problem, for the "
                                   "ticket list. E.g. 'Cannot log in - password "
                                   "reset email not arriving'.",
                },
                "description": {
                    "type": "string",
                    "description": "Written for the LMS administrator who will do "
                                   "the work. State what the student reported, what "
                                   "they have already tried, and what you believe "
                                   "needs to be done.",
                },
                "category": {
                    "type": "string",
                    "enum": ["login", "credentials", "course_access",
                             "content", "grades", "other"],
                    "description": "Best-fit category for routing and reporting.",
                },
                "urgency": {
                    "type": "string",
                    "enum": ["normal", "urgent"],
                    "description": "Use 'urgent' only when the student is blocked "
                                   "from an exam or has lost submitted work.",
                },
            },
            "required": ["subject", "description", "category"],
        },
    },
    {
        "name": "check_ticket_status",
        "description": (
            "Look up the status of this student's current support ticket. Use it "
            "when they ask what is happening with their issue, or whether anyone "
            "has looked at it yet."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "confirm_resolution",
        "description": (
            "Record the student's answer after they have been asked whether their "
            "issue is now fixed. Call this ONLY when the student is explicitly "
            "responding to that question. Set resolved to true only when they "
            "clearly confirm it is working."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "resolved": {
                    "type": "boolean",
                    "description": "True only if the student clearly confirms the "
                                   "problem is fixed. If they are unclear, or say "
                                   "it is partly working, use false.",
                },
                "note": {
                    "type": "string",
                    "description": "What the student said, in their own words, for "
                                   "the ticket record.",
                },
            },
            "required": ["resolved"],
        },
    },
]


def dispatch(name, tool_input, ctx):
    """Execute a tool call. `ctx` carries wa_id, username, and current state.

    Returns a short string result for the model. Never raises.
    """
    try:
        if name == "raise_ticket":
            return _raise_ticket(tool_input, ctx)
        if name == "check_ticket_status":
            return _check_ticket_status(ctx)
        if name == "confirm_resolution":
            return _confirm_resolution(tool_input, ctx)
        return f"Unknown tool '{name}'. Do not try to call it again."
    except Exception as e:  # noqa: BLE001 - a tool failure must not kill the turn
        wa_id = str(ctx.get("wa_id") or "")
        print(f"[tools] {name} failed for *{wa_id[-4:]}: {type(e).__name__}")
        return ("That action failed because of a system error. Apologise to the "
                "student, tell them the team has been notified, and do not retry "
                "the same action.")


# --- individual tools ----------------------------------------------------------

def _raise_ticket(args, ctx):
    wa_id = ctx["wa_id"]
    state = ctx["state"]
    subject_input = str(args.get("subject") or "").strip()
    description_input = str(args.get("description") or "").strip()
    category = args.get("category")
    allowed_categories = {"login", "credentials", "course_access", "content",
                          "grades", "other"}
    if not subject_input or not description_input or category not in allowed_categories:
        return ("The ticket details were incomplete or invalid. Do not retry the "
                "tool in this turn; apologise and ask the student to try again.")

    # Idempotency: one open ticket per student per problem. Guards against model
    # retries and Meta redelivering the same webhook.
    existing = state.get("ticket_id")
    if existing and state.get("ticket_status") in ("open", "awaiting_verification"):
        due = state.get("sla_due_at", "")
        return (f"This student already has open ticket #{existing}. Do not raise "
                f"another. Tell them it is already with the team, due by "
                f"{_friendly(due)}.")

    if not state_store.reserve_ticket_creation(wa_id):
        current = state_store.get_state(wa_id)
        current_id = current.get("ticket_id")
        if current_id:
            return (f"This student already has open ticket #{current_id}. Do not "
                    "raise another; tell them it is already with the team.")
        return ("A ticket is already being created for this student. Do not retry "
                "or create another; tell them the request is being processed.")

    try:
        contact_id = zoho_client.find_or_create_contact(
            phone=wa_id, name=ctx.get("username") or wa_id
        )
    except Exception:
        state_store.release_ticket_creation(wa_id)
        raise
    if not contact_id:
        state_store.release_ticket_creation(wa_id)
        return ("Could not reach the ticket system. Tell the student we could not "
                "raise the ticket right now and ask them to message again shortly.")

    urgency = "urgent" if args.get("urgency") == "urgent" else "normal"
    subject = subject_input[:200]
    if urgency == "urgent":
        subject = f"[URGENT] {subject}"

    description = (
        f"{description_input}\n\n"
        f"---\n"
        f"Raised automatically from WhatsApp.\n"
        f"Student: {ctx.get('username') or 'unknown'} ({wa_id})\n"
        f"Category: {category} | Urgency: {urgency}"
    )

    try:
        ticket = zoho_client.create_ticket(
            subject=subject,
            description=description,
            contact_id=contact_id,
            category=category,
        )
    except Exception:
        state_store.release_ticket_creation(wa_id)
        raise
    if not ticket or not ticket.get("id"):
        state_store.release_ticket_creation(wa_id)
        return ("Could not create the ticket. Tell the student we could not raise "
                "it right now and ask them to message again shortly.")

    ticket_id = str(ticket["id"])
    now = workdays.now_utc()
    due = workdays.add_working_days(now, SLA_WORKING_DAYS)

    state_store.open_ticket(
        wa_id=wa_id,
        ticket_id=ticket_id,
        category=category,
        created_at=now,
        sla_due_at=due,
    )

    return (f"Ticket #{ticket_id} raised. It is due by {_friendly(workdays.iso(due))}. "
            f"Tell the student it is raised and will be resolved within a maximum "
            f"of 3 working days.")


def _check_ticket_status(ctx):
    state = ctx["state"]
    ticket_id = state.get("ticket_id")
    status = state.get("ticket_status")

    if not ticket_id or status not in ("open", "awaiting_verification"):
        return ("This student has no open ticket. If they are describing a new "
                "problem, help them or raise a ticket.")

    due = _friendly(state.get("sla_due_at", ""))
    if status == "awaiting_verification":
        return (f"Ticket #{ticket_id} has been marked resolved by the "
                f"administrator and is waiting for the student to confirm it is "
                f"actually fixed. Ask them whether it is working now.")

    nudges = state.get("admin_nudges", 0)
    chased = "The administrator has been reminded." if nudges else ""
    return (f"Ticket #{ticket_id} is open with the LMS administrator, due by "
            f"{due}. {chased} Tell the student it is in progress.")


def _confirm_resolution(args, ctx):
    state = ctx["state"]
    ticket_id = state.get("ticket_id")

    # Structural guard: this is the only path that can close a ticket, and it is
    # only reachable when the admin has already marked the work done. No amount
    # of persuasion in the student's message can bypass this.
    if state.get("ticket_status") != "awaiting_verification":
        return ("There is nothing awaiting confirmation for this student right "
                "now, so this action was not performed. Continue helping with "
                "their question normally.")

    note = (args.get("note") or "").strip()[:500]

    if args.get("resolved"):
        ok = zoho_client.close_ticket(
            ticket_id,
            comment=f"Student confirmed resolved via WhatsApp. {note}".strip(),
        )
        if not ok:
            return ("Could not close the ticket because the ticket system did not "
                    "respond. Thank the student anyway and tell them it is noted.")
        state_store.close_ticket(ctx["wa_id"], reason="student_confirmed")
        return (f"Ticket #{ticket_id} closed. Thank the student warmly and let them "
                f"know they can message again any time.")

    # Not fixed: reopen, tell the admin, restart the clock.
    zoho_client.add_comment(
        ticket_id,
        f"Student says the issue is NOT resolved. {note}".strip(),
    )
    state_store.reopen_ticket(ctx["wa_id"], workdays.now_utc())
    return (f"Ticket #{ticket_id} reopened and the administrator has been told it "
            f"is still not working. Tell the student it has gone back to the team, "
            f"and ask for any extra detail that might help.")


def _friendly(iso_ts):
    """Render a stored UTC timestamp as a date a student would recognise."""
    if not iso_ts:
        return "shortly"
    try:
        return workdays.to_ist(workdays.parse(iso_ts)).strftime("%A %d %B")
    except (ValueError, TypeError):
        return "shortly"
