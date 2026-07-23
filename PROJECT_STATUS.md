# Project Status & Handoff

**Last updated:** 2026-07-23

Single source of truth for where this project stands. If you are picking this up
cold — read this, then [COSTS.md](COSTS.md) for the money and accounts.

> ⚠️ **[README.md](README.md) and [ROADMAP.md](ROADMAP.md) describe the OLD
> menu-based bot and are now out of date.** They have not yet been rewritten.
> Trust this file.

---

## What this project is

A WhatsApp support assistant for LMS (Moodle) students, for an educational
non-profit in India.

Two flows:

1. **Student message → AI → answer or ticket.** A student messages the WhatsApp
   number. An AI assistant reads what they wrote, answers from an approved
   knowledge base if it can, and raises a Zoho Desk ticket for the LMS
   administrator if it can't.
2. **Hourly timer → SLA check → nudge.** A scheduled job chases the LMS admin
   until the ticket is done, asks the student to confirm it's actually fixed, and
   auto-closes after 3 working days if either side goes quiet.

**The second flow is the point of the project.** The original problem was not bad
answers — it was that queries got missed, the admin forgot to act or forgot to
report, and nothing chased either side.

### Rules confirmed with the client
- English only
- LMS admin is nudged on **WhatsApp**, at their own number
- Working days are **Monday–Saturday**; Sunday and listed holidays are off
- SLA promised to students: **resolved within 3 working days**
- Closure is **student-verified** — the admin marking it done is not closure
- If either side goes inactive, auto-close after 3 working days
- **No Moodle write access** — every LMS fix is done by a human

---

## Phase 1 (original build) — complete and verified live

| Item | Status |
|---|---|
| Clean Python codebase, config/secrets layout | ✅ Done |
| DynamoDB state + outbound WhatsApp sender | ✅ Verified live |
| Zoho contact find-or-create + ticket creation | ✅ Verified live (ticket #105) |
| CI/CD pipelines (GitHub Actions + OIDC) | ✅ In repo |

---

## Phase 2 (agentic rebuild) — code written, not yet deployed

### Done ✅

| File | What it does | Verified |
|---|---|---|
| `src/workdays.py` | Mon–Sat working-day clock, IST, editable holiday list | ✅ 17 tests |
| `knowledge/*.md` | 4 markdown files staff can edit — policy, login, credentials, courses | — |
| `src/knowledge.py` | Loads the knowledge base as the AI's grounding text | — |
| `src/llm.py` | Model client + system prompt. Claude Haiku (cheapest tier) | — |
| `src/tools.py` | 3 AI tools: raise ticket, check status, confirm resolution | — |
| `src/agent.py` | The AI loop (max 4 steps per message), fallback if AI is down | ✅ Simulated |
| `src/sla.py` | Nudge ladder + both auto-close paths (pure logic, no AWS needed) | ✅ Simulated |
| `src/sweeper.py` | Scheduled worker that fires nudges and closes stale tickets | ✅ Simulated |
| `src/state_store.py` | Conversation memory, ticket lifecycle, 2 indexes, duplicate guard | — |
| `src/handler.py` | Lambda entry + Meta signature check + Zoho webhook | ✅ 6 tests |
| `simulate.py` | **Local test harness — run the whole flow on a laptop, free** | ✅ Working |
| `deployment/whatsapp-templates.md` | The 4 Meta templates to submit | — |
| `COSTS.md` | Every bill, account, credential, and what breaks if one lapses | — |

**Test it yourself, no AWS or cost:**
```bash
python simulate.py --mock          # scripted answers, no API key
python simulate.py                 # real AI (needs ANTHROPIC_API_KEY, ~1 cent)
```
Commands inside: `/resolve` `/sweep` `/jump 1` `/status` `/tickets` `/quit`

### Reviewed and fixed ✅

A 4-reviewer adversarial code review found 60 issues, 25 serious. Three
critical bugs in the accountability engine were found **and fixed**:

1. **Tickets closed ~9 hours early** — the SLA enforcer was breaking the SLA.
2. **Student reminder could never fire** — a student who missed one message lost
   their ticket silently. The code existed but was unreachable.
3. **Nudges counted without being sent** — if the admin's number was unset, the
   ticket auto-closed having contacted nobody.

---

## What still has to be done

### Group A — blocks go-live

| # | Task | Where | Effort |
|---|---|---|---|
| A1 | **Finish `deployment/template.yaml`** — 2 DynamoDB indexes, TTL on processed-message rows, the sweeper Lambda + hourly schedule, IAM permissions, new env vars. **Nothing new runs until this is done.** | `deployment/` | half day |
| A2 | **Check WhatsApp send results** before advancing ticket state. Token expires daily; today the system would close tickets while sending nothing, logs looking healthy. | `sweeper.py` | 1 hr |
| A3 | **Fix Lambda timeouts** — Lambda 20s but AI call allowed 30s. On timeout the message is marked handled, so Meta's retry is discarded and the student gets silence. Set web 25s / AI 12s / sweeper 120s, and release the duplicate-claim on failure. | `template.yaml`, `llm.py`, `handler.py` | 1 hr |
| A4 | **Replace `<LMS_URL>` and `<SUPPORT_EMAIL>`** in all 4 knowledge files, and add a startup check that refuses to run if placeholders remain. | `knowledge/`, `knowledge.py` | 15 min |
| A5 | **Close two security holes** — signature check passes when the app secret is blank; the Zoho callback URL has no authentication at all (anyone who finds it can trigger billable messages and push tickets into a closeable state). | `handler.py` | 1 hr |
| A6 | **Write `tests/test_sla.py`** — would have caught 3 of the 4 worst bugs. Needs no AWS account. | `tests/` | half day |

### Group B — week one

| # | Task | Effort |
|---|---|---|
| B1 | Delete ~320 lines of dead code: `src/bot.py`, `src/faq.py`, the unused OpenAI adapter in `llm.py`, `send_category_list`/`send_yes_no`, `deployment/build.sh` | 1 hr |
| B2 | Switch API Gateway REST (v1) → HTTP API — ~70% cheaper per request | 1 hr |
| B3 | Add 3 alarms to one email: any error; sweeper silent for 2 hrs; >3 admin-ignored auto-closes in a day (that last one is the real business signal) | 1 hr |
| B4 | Pin library versions in `requirements.txt`; move `pytest` out of the deployed package | 15 min |
| B5 | Fix conversation-history trimming edge case (can cause intermittent total silence) | 15 min |
| B6 | Rewrite `README.md`; mark `ROADMAP.md` historical | 1 hr |
| B7 | Write `RUNBOOK.md` — rotate the WhatsApp token, "bot stopped replying", "admin got no nudge", unstick a ticket, redeploy/rollback | half day |
| B8 | Auto-deploy on `knowledge/*.md` changes so staff can edit content without a developer | 1 hr |

### Group C — external, start now (longest lead time)

| # | Task | Owner | Lead time |
|---|---|---|---|
| C1 | **Submit the 4 WhatsApp templates to Meta** — copy from `deployment/whatsapp-templates.md` | Client | hours–days |
| C2 | **Confirm the Zoho Desk plan** supports a Workflow Rule with an outbound webhook. If not, we build a polling fallback instead of upgrading. | Client | — |
| C3 | **Provide the LMS admin's WhatsApp number** → add as `lms_admin_wa_id` in the secret | Client | — |
| C4 | **Add an Anthropic API key** as `llm_api_key` in the secret | Client | — |
| C5 | **Replace the temporary WhatsApp token** with a permanent System User token. It currently expires ~daily. | Client | 30 min |
| C6 | **Fill in `whatsapp_app_secret`** — currently empty, so message signatures are unverified | Client | 15 min |
| C7 | Meta Business Verification, payment method on the WABA, real business phone number | Client | days–weeks |

---

## Live infrastructure (identifiers, not secrets)

| Thing | Value |
|---|---|
| AWS account / region | 417311687123 / ap-south-1 |
| Secrets Manager secret | `siddhanta/whatsapp-zoho` |
| DynamoDB table | `whatsapp_conversation_state` (key `wa_id`) |
| Zoho org / department | 60037340249 / 146318000000010772 |
| Zoho data centre | `.in` |
| Meta app / business | 1389405936369712 / 4612082319081221 |
| WhatsApp phone number id | 1121518577721735 (**Meta test number** — not live) |
| WhatsApp WABA id | 991209477079437 |
| Webhook verify token | stored in the secret, not printed here |
| GitHub repo | github.com/skf-ai/Zoho_ticket_integration |

---

## Resume on a new machine

```bash
git clone https://github.com/skf-ai/Zoho_ticket_integration.git
cd Zoho_ticket_integration
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements.txt
python -m pytest                                    # 23 tests should pass
python simulate.py --mock                           # try the whole flow, free
```

---

## Decisions on record

- **Reuse infrastructure, rebuild the bot fresh.** The Zoho/WhatsApp/AWS clients
  were already proven live; only the conversation logic was replaced.
- **AI for conversation, plain code for accountability.** The working-day clock,
  nudge ladder and closure rules are deterministic on purpose — they must be
  exact, auditable, and must keep running when the AI provider is down.
- **The AI can never name a ticket ID.** It only ever acts on the ticket
  belonging to the phone number that messaged. Enforced in code, not by prompt.
  **Keep it that way permanently.**
- **Claude Haiku, the cheapest tier.** Correct for this job. Do not upgrade
  without evidence of a real quality problem.
- **One scheduled sweeper, not per-ticket timers.** Cheapest and simplest.
  Do not let a future developer "upgrade" this.
- **No framework (LangChain etc.).** The AI loop is ~50 lines; a framework would
  add dependency churn for no gain.
- **Deployment is user-triggered** from GitHub Actions, never from a developer's
  shell.
