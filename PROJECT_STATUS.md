# Project Status & Handoff

**Last updated:** 2026-07-17

This is the single source of truth for where the project stands. If you switch
machines, clone the repo and read this file + [ROADMAP.md](ROADMAP.md) — everything
you need to resume is here. Secret *values* are NOT in this file (they live in AWS
Secrets Manager); only non-sensitive identifiers are listed.

---

## What this project is
WhatsApp (Meta Cloud API) support bot for LMS/Moodle students. Answers FAQs, and
escalates unresolved queries to Zoho Desk tickets. On resolve, asks the user on
WhatsApp if it's fixed; "Yes" closes the ticket. Full flow in [ROADMAP.md](ROADMAP.md).

---

## Progress checklist

| Day | Item | Status |
|-----|------|--------|
| 1 | Clean Python codebase, config/secrets layout | ✅ Done |
| 2 | DynamoDB state table + outbound WhatsApp sender | ✅ Done, verified live |
| 3 | Bot logic: menu → FAQ → "Solved?" | ✅ Done, verified (simulated) |
| 4 | Zoho contact find-or-create + ticket creation | ✅ Done, verified live (ticket #105) |
| — | CI/CD pipelines (GitHub Actions) + DEPLOYMENT.md | ✅ Written, **not yet pushed to GitHub** |
| 5 | Resolve/close loop | 🟡 Code done; needs Meta template + Zoho workflow (see below) |
| 6 | Deploy via CI/CD + point Meta webhook | ⬜ Pending |
| 7 | End-to-end test on real WhatsApp | ⬜ Pending |
| 8 | Edge cases, permanent token, go-live | ⬜ Pending |

---

## Verified working (tested against live services)
- Secret loads from AWS Secrets Manager ✅
- Zoho access-token refresh with real credentials ✅
- DynamoDB conversation state write/read/clear ✅
- Outbound WhatsApp message sent from our code (HTTP 200) ✅
- Full escalation: created Zoho contact + Ticket **#105** from bot code ✅
- Simulated conversation: Hi → menu → Login Issue → FAQ → Yes → ends ✅
- Unit tests: 6/6 passing (`python -m pytest`)

---

## Live infrastructure (identifiers, not secrets)

| Thing | Value |
|-------|-------|
| AWS account | 417311687123 |
| AWS region | ap-south-1 |
| Secrets Manager secret name | `siddhanta/whatsapp-zoho` |
| DynamoDB table | `whatsapp_conversation_state` (key: `wa_id`) |
| Zoho org id | 60037340249 |
| Zoho department id | 146318000000010772 |
| Zoho data center | `.in` |
| Meta app name / id | SKF Zoho Ticketing System / 1389405936369712 |
| Meta business id | 4612082319081221 |
| WhatsApp phone number id | 1121518577721735 (Meta **test** number for now) |
| WhatsApp WABA id | 991209477079437 |
| Webhook verify token | `skf-whatsapp-verify-2026` |
| GitHub repo | github.com/skf-ai/Zoho_ticket_integration |

Secrets stored in `siddhanta/whatsapp-zoho`: all 5 Zoho keys, `whatsapp_token`
(temporary — expires ~24h, regenerate from Meta API Setup), `whatsapp_phone_number_id`,
`whatsapp_waba_id`, `whatsapp_verify_token`. **Still empty / TODO:** `whatsapp_app_secret`.

---

## Resume on a new machine
```bash
git clone https://github.com/skf-ai/Zoho_ticket_integration.git
cd Zoho_ticket_integration
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements.txt
python -m pytest                                     # should pass 6/6

# to run code against live AWS/Zoho/WhatsApp:
setx SECRET_NAME siddhanta/whatsapp-zoho             # or set per-session
setx AWS_REGION ap-south-1
# (AWS credentials for user akash_dev must be configured: aws configure)
```

---

## What's LEFT — exact next actions

### A. Push to GitHub (activates CI/CD) — needs decision
Commit everything to a branch and push, then open a PR. CI runs tests automatically.

### B. Day 5 — resolve/close loop (needs Meta + Zoho console work)
1. **Meta:** submit message template `issue_resolved_check` (Utility, English), body
   "Hi! Our support team has resolved your ticket. Has your issue been resolved?",
   with two Quick-Reply buttons: **Yes** / **No**.
2. **Zoho Desk:** create a Workflow Rule — on ticket status → *Resolved*, fire a
   webhook POST to our `/zoho-webhook` endpoint with the ticket id. (Endpoint URL
   exists after Day 6 deploy.) Handler code already written in `src/handler.py`.

### C. Day 6 — deploy (CI/CD, user-triggered)
Follow [DEPLOYMENT.md](DEPLOYMENT.md): one-time OIDC role setup → click "Run
workflow" in GitHub Actions → copy `ApiBaseUrl` → set Meta webhook to
`<ApiBaseUrl>/whatsapp` with verify token `skf-whatsapp-verify-2026` → subscribe
to `messages` field.

### D. Production hardening (Days 6–8) — Meta/business side
- Business Verification (long lead — start early; needs org registration + PAN + address proof)
- Add payment method to WABA (template messages are billed)
- Add & verify real business phone number (not the test number)
- Display name approval + business profile (logo/description)
- Create permanent System User token → update `whatsapp_token` in the secret
- Publish the Meta app (Development → Live)
- Add `whatsapp_app_secret` to the secret + enable webhook signature verification

### E. Content
- Replace `<LMS_URL>` and `<SUPPORT_EMAIL>` placeholders in `src/faq.py` with real values.

---

## Key decisions on record
- **Reuse infrastructure, rebuild code fresh** (old repo was a stub + manual script).
- **Python 3.12** everywhere (old ingress Lambda was a Node stub — replaced).
- **Serverless**: Lambda + API Gateway + DynamoDB + Secrets Manager.
- **CI/CD via GitHub Actions with OIDC** (no AWS keys stored in GitHub).
- **Deployment is user-triggered** (button in GitHub Actions), never run from the
  assistant's shell.
