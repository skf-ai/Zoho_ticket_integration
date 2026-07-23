"""Local test harness -- run the whole support flow on your laptop.

Nothing here touches AWS, Zoho, or WhatsApp. DynamoDB, the Zoho API and the
WhatsApp API are replaced with in-memory fakes that print what they would have
done. The agent, the SLA engine, the working-day calendar and the sweeper are
the REAL code -- so what you see here is what will happen in production.

There is also a fake clock, so you can jump forward three working days and watch
the admin nudges and the auto-close fire, instead of waiting three days.

## Run it

    python simulate.py --mock     # no API key needed, scripted answers
    python simulate.py            # real model (needs ANTHROPIC_API_KEY), costs ~1 cent

## Commands, once it is running

    <anything>    talk to the bot as a student
    /resolve      pretend the LMS admin marked the ticket Resolved in Zoho
    /sweep        run the scheduled worker now (nudges, reminders, auto-close)
    /jump 1       move the clock forward 1 working day
    /status       show ticket state and what the system plans to do next
    /tickets      show the fake Zoho ticket list
    /reset        start over
    /quit
"""

import argparse
import sys
from datetime import timedelta

from src import agent, llm, sla, sweeper, whatsapp_client, workdays

STUDENT = "919999000001"
STUDENT_NAME = "Test Student"
ADMIN = "919500089638"

C_BOT, C_YOU, C_SYS, C_ADMIN, C_OFF = (
    "\033[96m", "\033[93m", "\033[90m", "\033[95m", "\033[0m"
)


# --- fake clock ----------------------------------------------------------------

class Clock:
    """Real time plus an offset you can push forward with /jump."""

    def __init__(self):
        self.offset = timedelta()
        self._real_now = workdays.now_utc

    def now(self):
        return self._real_now() + self.offset

    def jump_working_days(self, n):
        target = workdays.add_working_days(self.now(), n)
        self.offset += target - self.now()
        return self.now()


CLOCK = Clock()


# --- fake DynamoDB -------------------------------------------------------------

class FakeStore:
    """In-memory stand-in with the same public surface as src/state_store.py."""

    def __init__(self):
        self.items = {}
        self.seen_messages = set()

    def get_state(self, wa_id):
        item = self.items.get(wa_id)
        if not item:
            return {"wa_id": wa_id, "history": [], "ticket_status": "none"}
        item.setdefault("history", [])
        item.setdefault("ticket_status", "none")
        return dict(item)

    def _item(self, wa_id):
        return self.items.setdefault(
            wa_id, {"wa_id": wa_id, "history": [], "ticket_status": "none"}
        )

    def append_history(self, wa_id, messages):
        item = self._item(wa_id)
        item["history"] = (item.get("history", []) + list(messages))[-20:]
        item["last_activity_at"] = workdays.iso(CLOCK.now())
        return item["history"]

    def touch_activity(self, wa_id):
        self._item(wa_id)["last_activity_at"] = workdays.iso(CLOCK.now())

    def open_ticket(self, wa_id, ticket_id, category, created_at, sla_due_at):
        item = self._item(wa_id)
        item.update({
            "ticket_id": str(ticket_id),
            "ticket_status": "open",
            "category": category,
            "ticket_created_at": workdays.iso(created_at),
            "sla_due_at": workdays.iso(sla_due_at),
            "admin_nudges": 0,
            "student_reminders": 0,
            "due_bucket": "DUE",
            "next_action_at": workdays.iso(sla.first_nudge_at(created_at)),
        })

    def reserve_ticket_creation(self, wa_id):
        item = self._item(wa_id)
        if item.get("ticket_status", "none") not in ("none", "closed"):
            return False
        item["ticket_status"] = "creating"
        # Production records this so the sweeper can tell an in-flight creation
        # from an abandoned one. Mirror it, or /sweep behaves differently here
        # than it will in AWS.
        item["ticket_creation_started_at"] = workdays.iso(CLOCK.now())
        return True

    def release_ticket_creation(self, wa_id):
        item = self._item(wa_id)
        if item.get("ticket_status") == "creating":
            item["ticket_status"] = "none"
            item.pop("ticket_creation_started_at", None)

    def begin_verification(self, wa_id):
        item = self._item(wa_id)
        if item.get("ticket_status") != "open":
            return False
        item["ticket_status"] = "verification_prompting"
        item["verification_prompting_at"] = workdays.iso(CLOCK.now())
        return True

    def release_verification(self, wa_id):
        item = self._item(wa_id)
        if item.get("ticket_status") == "verification_prompting":
            item["ticket_status"] = "open"
            item.pop("verification_prompting_at", None)

    def record_nudge(self, wa_id, next_action_at):
        item = self._item(wa_id)
        item["admin_nudges"] = int(item.get("admin_nudges", 0)) + 1
        item["last_nudge_at"] = workdays.iso(CLOCK.now())
        item["next_action_at"] = workdays.iso(next_action_at)

    def record_student_reminder(self, wa_id, next_action_at):
        item = self._item(wa_id)
        item["student_reminders"] = int(item.get("student_reminders", 0)) + 1
        item["next_action_at"] = workdays.iso(next_action_at)

    def set_next_action(self, wa_id, next_action_at):
        self._item(wa_id)["next_action_at"] = workdays.iso(next_action_at)

    def await_verification(self, wa_id, prompted_at, auto_close_at=None):
        item = self._item(wa_id)
        item.update({
            "ticket_status": "awaiting_verification",
            "verification_prompted_at": workdays.iso(prompted_at),
            "student_reminders": 0,
            "due_bucket": "DUE",
            "next_action_at": workdays.iso(sla.reminder_due_at(prompted_at)),
        })

    def reopen_ticket(self, wa_id, reopened_at):
        item = self._item(wa_id)
        item.update({
            "ticket_status": "open",
            "admin_nudges": 0,
            "sla_due_at": workdays.iso(workdays.add_working_days(reopened_at, 3)),
            "due_bucket": "DUE",
            "next_action_at": workdays.iso(sla.first_nudge_at(reopened_at)),
        })
        item.pop("verification_prompted_at", None)

    def close_ticket(self, wa_id, reason):
        item = self._item(wa_id)
        item.update({
            "ticket_status": "closed",
            "closed_at": workdays.iso(CLOCK.now()),
            "closed_reason": reason,
        })
        for k in ("ticket_id", "due_bucket", "next_action_at"):
            item.pop(k, None)

    def find_by_ticket(self, ticket_id):
        for item in self.items.values():
            if item.get("ticket_id") == str(ticket_id):
                return dict(item)
        return None

    def due_now(self, limit=100):
        now = workdays.iso(CLOCK.now())
        return [dict(i) for i in self.items.values()
                if i.get("due_bucket") == "DUE"
                and i.get("next_action_at", "9999") <= now][:limit]

    def mark_processed(self, message_id):
        if message_id in self.seen_messages:
            return False
        self.seen_messages.add(message_id)
        return True

    def clear_history(self, wa_id):
        self._item(wa_id)["history"] = []


STORE = FakeStore()


# --- fake Zoho -----------------------------------------------------------------

class FakeZoho:
    def __init__(self):
        self.tickets = {}
        self.next_id = 1001

    def find_or_create_contact(self, phone, name, access_token=None):
        return f"contact_{phone}"

    def create_ticket(self, subject, description, contact_id, category=None):
        tid = str(self.next_id)
        self.next_id += 1
        self.tickets[tid] = {
            "id": tid, "subject": subject, "description": description,
            "status": "Open", "category": category, "comments": [],
        }
        print(f"{C_SYS}   [zoho] ticket #{tid} created: {subject}{C_OFF}")
        return self.tickets[tid]

    def close_ticket(self, ticket_id, comment=None):
        t = self.tickets.get(str(ticket_id))
        if not t:
            return False
        t["status"] = "Closed"
        if comment:
            t["comments"].append(comment)
        print(f"{C_SYS}   [zoho] ticket #{ticket_id} CLOSED{C_OFF}")
        return True

    def add_comment(self, ticket_id, content, access_token=None):
        t = self.tickets.get(str(ticket_id))
        if t:
            t["comments"].append(content)
            print(f"{C_SYS}   [zoho] note on #{ticket_id}: {content[:70]}...{C_OFF}")
        return True


ZOHO = FakeZoho()


# --- fake WhatsApp -------------------------------------------------------------

def fake_send_text(to, text):
    who = "STUDENT" if to == STUDENT else "ADMIN"
    colour = C_BOT if to == STUDENT else C_ADMIN
    print(f"\n{colour}[to {who}] {text}{C_OFF}\n")
    return True


def fake_send_template(to, template_name, language="en", components=None):
    params = []
    for c in components or []:
        params += [p.get("text", "") for p in c.get("parameters", [])]
    who = "STUDENT" if to == STUDENT else "ADMIN"
    colour = C_BOT if to == STUDENT else C_ADMIN
    print(f"\n{colour}[template -> {who}] {template_name}({', '.join(params)}){C_OFF}")
    print(f"{C_SYS}   (a paid WhatsApp template message, ~Rs 0.115){C_OFF}\n")
    return True


# --- scripted model, for --mock ------------------------------------------------

_mock_counter = {"n": 0}


def mock_complete(messages, tools_):
    """A crude stand-in so the plumbing can be demonstrated without an API key.

    This is NOT the agent's real intelligence -- it is a few if-statements. Run
    without --mock to see the actual model reason.
    """
    last = ""
    for m in reversed(messages):
        if m["role"] == "user" and isinstance(m.get("content"), str):
            last = m["content"].lower()
            break
        if m["role"] == "user" and isinstance(m.get("content"), list):
            results = [b for b in m["content"] if b.get("type") == "tool_result"]
            if results:
                result_text = results[0].get("content") or "That action is complete."
                # Tool results are instructions written for the real model. Make
                # the scripted demonstration student-facing instead of echoing
                # phrases such as "Tell the student..." verbatim.
                result_text = result_text.split("Tell the student")[0].strip()
                result_text = result_text.replace("This student", "You")
                return {"text": result_text,
                        "tool_calls": [], "stop_reason": "end_turn",
                        "raw_content": None, "usage": {}}

    state = STORE.get_state(STUDENT)

    if state.get("ticket_status") == "awaiting_verification":
        negative = ("no", "not fixed", "not working", "still broken",
                    "still not working", "didn't work", "did not work")
        positive = ("yes", "it works", "working now", "fixed now",
                    "resolved", "solved")
        resolved = (not any(p in last for p in negative)
                    and any(p in last for p in positive))
        return {"text": "", "stop_reason": "tool_use", "raw_content": None,
                "usage": {}, "tool_calls": [{
                    "id": f"mock_{_mock_counter['n']}", "name": "confirm_resolution",
                    "input": {"resolved": resolved, "note": last}}]}

    escalate = (last.strip() == "no" or any(w in last for w in
                   ("still", "not work", "didn't", "didnt", "tried",
                    "raise a ticket", "create a ticket", "escalate"))
               )
    if escalate:
        _mock_counter["n"] += 1
        return {"text": "", "stop_reason": "tool_use", "raw_content": None,
                "usage": {}, "tool_calls": [{
                    "id": f"mock_{_mock_counter['n']}", "name": "raise_ticket",
                    "input": {
                        "subject": "Student cannot log in after trying reset",
                        "description": f"Student reports: {last}. Already tried the "
                                       f"knowledge-base steps.",
                        "category": "login", "urgency": "normal"}}]}

    return {
        "text": ("Sorry you're having trouble logging in. Please try:\n"
                 "1. Check your username matches the welcome email exactly.\n"
                 "2. Passwords are case-sensitive - check Caps Lock.\n"
                 "3. Tap 'Forgot password' on the login page.\n\n"
                 "Did that help?"),
        "tool_calls": [], "stop_reason": "end_turn", "raw_content": None, "usage": {},
    }


# --- wiring --------------------------------------------------------------------

def install_fakes(mock_llm):
    import src.state_store as ss
    import src.zoho_client as zc

    for name in ("get_state", "append_history", "touch_activity", "open_ticket",
                 "reserve_ticket_creation", "release_ticket_creation",
                 "begin_verification", "release_verification",
                 "record_nudge", "record_student_reminder", "await_verification",
                 "reopen_ticket", "close_ticket", "find_by_ticket", "due_now",
                 "mark_processed", "clear_history", "set_next_action"):
        setattr(ss, name, getattr(STORE, name))

    for name in ("find_or_create_contact", "create_ticket",
                 "close_ticket", "add_comment"):
        setattr(zc, name, getattr(ZOHO, name))

    whatsapp_client.send_text = fake_send_text
    whatsapp_client.send_template = fake_send_template
    workdays.now_utc = CLOCK.now

    import src.config as cfg
    _real_get = cfg.get
    cfg.get = lambda k: ADMIN if k == "lms_admin_wa_id" else _real_get(k)

    if mock_llm:
        llm.complete = mock_complete


# --- commands ------------------------------------------------------------------

def cmd_status():
    s = STORE.get_state(STUDENT)
    print(f"\n{C_SYS}{'-' * 62}")
    print(f" clock         {workdays.to_ist(CLOCK.now()):%a %d %b %Y %H:%M} IST")
    print(f" ticket        #{s.get('ticket_id', '-')}  status={s.get('ticket_status')}")
    print(f" admin nudges  {s.get('admin_nudges', 0)}")
    print(f" student pings {s.get('student_reminders', 0)}")
    if s.get("sla_due_at"):
        due = workdays.to_ist(workdays.parse(s["sla_due_at"]))
        print(f" SLA due       {due:%a %d %b %H:%M} IST")
    if s.get("next_action_at"):
        nxt = workdays.to_ist(workdays.parse(s["next_action_at"]))
        print(f" next action   {nxt:%a %d %b %H:%M} IST")
    d = sla.decide(s, CLOCK.now())
    print(f" engine says   {d['action']}  ({d['reason']})")
    print(f"{'-' * 62}{C_OFF}\n")


def cmd_resolve():
    s = STORE.get_state(STUDENT)
    tid = s.get("ticket_id")
    if not tid:
        print(f"{C_SYS}No open ticket to resolve.{C_OFF}")
        return
    ZOHO.tickets[tid]["status"] = "Resolved"
    print(f"{C_SYS}   [zoho] admin marked #{tid} Resolved -> webhook fires{C_OFF}")
    now = CLOCK.now()
    whatsapp_client.send_template(
        STUDENT, "issue_resolved_check",
        components=[{"type": "body", "parameters": [{"type": "text", "text": tid}]}])
    STORE.await_verification(STUDENT, now, sla.verification_deadline(now))


def cmd_tickets():
    if not ZOHO.tickets:
        print(f"{C_SYS}No tickets yet.{C_OFF}")
        return
    print()
    for t in ZOHO.tickets.values():
        print(f"{C_SYS} #{t['id']}  [{t['status']:<8}] {t['subject']}{C_OFF}")
        for c in t["comments"]:
            print(f"{C_SYS}          - {c[:80]}{C_OFF}")
    print()


HELP = f"""{C_SYS}
  <text>      talk to the bot as a student
  /resolve    admin marks the ticket Resolved in Zoho
  /sweep      run the scheduled worker now
  /jump N     move the clock forward N working days
  /status     ticket state and what the engine will do next
  /tickets    the fake Zoho ticket list
  /reset      start over
  /quit
{C_OFF}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true",
                    help="use scripted answers instead of a real model (no API key)")
    args = ap.parse_args()

    install_fakes(args.mock)

    print(f"\n{C_SYS}{'=' * 62}")
    print(" WhatsApp LMS support -- local simulator")
    print(f" model: {'SCRIPTED MOCK (not real AI)' if args.mock else llm.MODEL}")
    print(f" clock: {workdays.to_ist(CLOCK.now()):%A %d %B %Y %H:%M} IST")
    print(f"{'=' * 62}{C_OFF}")
    print(HELP)

    turn = 0
    while True:
        try:
            raw = input(f"{C_YOU}student> {C_OFF}").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not raw:
            continue
        if raw in ("/quit", "/exit"):
            return
        if raw == "/help":
            print(HELP)
            continue
        if raw == "/status":
            cmd_status()
            continue
        if raw == "/tickets":
            cmd_tickets()
            continue
        if raw == "/resolve":
            cmd_resolve()
            continue
        if raw == "/sweep":
            print(f"{C_SYS}   [sweeper] running...{C_OFF}")
            counts = sweeper.run_once()
            print(f"{C_SYS}   [sweeper] {counts or 'nothing due'}{C_OFF}")
            continue
        if raw.startswith("/jump"):
            parts = raw.split()
            n = int(parts[1]) if len(parts) > 1 else 1
            CLOCK.jump_working_days(n)
            print(f"{C_SYS}   clock -> "
                  f"{workdays.to_ist(CLOCK.now()):%A %d %b %H:%M} IST{C_OFF}")
            continue
        if raw == "/reset":
            STORE.__init__()
            ZOHO.__init__()
            CLOCK.offset = timedelta()
            print(f"{C_SYS}   reset.{C_OFF}")
            continue

        turn += 1
        agent.handle_inbound(
            STUDENT, STUDENT_NAME,
            {"type": "text", "text": raw, "id": None, "message_id": f"sim{turn}"},
        )


if __name__ == "__main__":
    sys.exit(main())
