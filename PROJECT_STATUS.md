# Project Status and Handoff

**Updated:** 2026-08-25

## Current stage

**DEPLOYED AND LIVE.** The stack deployed successfully via the GitHub Deploy
workflow on 2026-08-25 (stack `whatsapp-zoho-bot`, ap-south-1; same
`ApiBaseUrl` as the earlier deployment, so Meta's webhook needed no URL
change). `/health` returns `"ready": true` with all checks green. After
enabling the WABA-level **Subscribe webhooks** toggle in Meta's Production
setup (the missing link — app-level `messages` subscription alone is not
enough), the bot now answers real WhatsApp messages on **+91 89259 93784**
from the knowledge base, live-verified end to end.

Alert email `AlertEmail` was set during deploy; the SNS subscription
confirmation email must be accepted for alarms to deliver.

**2026-09-01 progress:** Admin panel shipped at `GET /admin` (key-protected,
404 without): overview + reports views, hover detail, manual refresh, ticket
timeline with nudge accountability, and spend cards pulling REAL provider
bills (AWS Cost Explorer scoped to this project's services, OpenAI org costs,
Meta conversation analytics) with LIVE/ESTIMATE badges — verified in
production, all three sources live. New secret keys: `admin_dashboard_key`,
`whatsapp_waba_id`, `openai_admin_key`. Pre-live test suite added:
`TESTING.md` (5 phases + production-ready sign-off, ~₹25–30 per full pass)
and `loadtest.py` (signed-webhook burst, single-conversation hammer,
duplicate-storm dedupe test). 71 automated tests green.

**2026-08-27 progress:** full ticket lifecycle verified on the live number —
escalation with pre-ticket intake (registered email, error text, urgency),
urgent ticket #107 created and closed via the student's "Yes" tap. Agent now
formats ticket descriptions as labelled lines and Zoho renders real line
breaks; a student "No" now visibly returns the ticket to Open in Zoho (plus
internal comment). Auto-deploy on push to `main` enabled with a concurrency
guard and a hardened empty-AlertEmail path; `ALERT_EMAIL` repo variable
carries the ops email for automatic runs. Runbook now documents the Zoho
admin rules (set Resolved, never Closed).

**2026-08-26 progress:** Zoho ticket creation works live (scope-fixed refresh
token; old token revoked). Ticket #106 created from a real WhatsApp escalation.
Zoho Desk changes: custom ticket status **Resolved** added (Open group; admins
must set Resolved, never Closed — the bot owns Closed), workflow rule
"Notify support bot on Resolved" wired via custom function
`NotifyBotOnResolved` posting to `/zoho-webhook` with `X-Webhook-Secret`;
verified end to end — marking #106 Resolved delivered the
`issue_resolved_check` template with Yes/No buttons to the student's phone
(sent free inside the open 24h window). New-ticket email notification enabled
in Zoho. Remaining test: the student "Yes" tap closing the ticket, and
out-of-window template sends (blocked on WABA payment).

What remains before wide circulation, in order:

1. **Confirm the rotated verify token is saved in Meta's webhook config**
   (Verify and save with the new `whatsapp_verify_token` value).
2. **Configure the Zoho Desk Resolved workflow** with `X-Webhook-Secret`
   posting to the stack's `ZohoWebhookUrl`.
3. **WABA payment method** — awaiting finance approval (template sends fail
   silently without it; ~₹100–200/month expected).
4. **Controlled live test** per `RUNBOOK.md` (needs payment for the
   reminder/verification templates).
5. **Meta business verification** (org documents) — raises the messaging limit
   from 250 business-initiated conversations/day; required before circulating
   the number widely.
6. **Circulate +91 89259 93784 to students in batches** as the official
   support number.

## Meta / WhatsApp — completed 2026-08-20/21

- Old office number removed from the WABA (was Unverified; nothing lost).
- Support number **+91 89259 93784** added to WABA `991209477079437`,
  OTP-verified, **registered on the Cloud API** — status **Connected**,
  quality **High**. Phone Number ID `1181089108432432`.
- Two-way messaging verified from the API Setup test page (inbound + template).
- Permanent access token generated (rotated once after a screenshot exposure)
  and stored in Secrets Manager.
- All four Utility templates **approved** in plain English (`en`), names
  matching the code exactly: `ticket_pending_admin`, `issue_resolved_check`,
  `ticket_reminder_student`, `ticket_auto_closed`.
- Secrets Manager `siddhanta/whatsapp-zoho` fully populated, including
  `whatsapp_app_secret`, rotated `whatsapp_verify_token`,
  `zoho_webhook_secret`, `llm_api_key`, and `lms_admin_wa_id`.
- Knowledge files verified free of `<LMS_URL>`/`<SUPPORT_EMAIL>` placeholders.

The full click-by-click record is
[`deployment/meta-whatsapp-setup.md`](deployment/meta-whatsapp-setup.md).

## Implemented

- Grounded AI support agent (OpenAI GPT-5 mini by default, provider-swappable)
  with structurally constrained ticket tools
- Atomic DynamoDB ticket-creation reservation
- Meta HMAC verification that fails closed
- Authenticated Zoho callback with concurrent-callback reservation and recovery
- Retry-safe inbound message claims and HTTP 5xx on transient processing failure
- Checked WhatsApp/Zoho results before lifecycle state advances
- Deterministic three-working-day SLA and student-confirmation lifecycle
- Verification-in-history reopen fix and student self-close handling
- Hourly sweeper, GSIs, TTL, point-in-time recovery and encryption in SAM
- Safe v2 DynamoDB table replacement; legacy table retained because both GSIs
  cannot be added to an existing table in one AWS update
- EventBridge retry/dead-letter configuration
- Optional SNS operations alarms and 30-day log retention
- Masked student identifiers in application logs
- 90-day inactive conversation TTL (configurable)
- Pinned production/dev dependencies
- Deployment documentation, operations runbook, and Meta go-live guide

## Verified locally

- `python -m pytest -q`: 59 passed
- Python bytecode compilation: passed
- Scripted login -> ticket -> resolved -> student says still broken -> reopen: passed
- `git diff --check`: passed

AWS SAM CLI is not installed on the current workstation, so final SAM transform
validation is delegated to the GitHub Deploy workflow (`sam validate` and
`sam build`) before CloudFormation can change infrastructure.

## History

- 2026-07-23 — production-hardening implementation verified locally (40 tests).
- Hardening continued: stuck-state recovery, timeout budget, silent-nudge
  fixes; default model switched to GPT-5 mini with Zoho dual-auth; reasoning
  cap, verification-in-history reopen fix, student self-close (59 tests).
- 2026-08-19 — office number removed from the WABA; decision to onboard spare
  number 8925993784; Meta go-live guide added.
- 2026-08-20 — number added, registered, Connected; permanent token stored;
  Phone Number ID in Secrets Manager; two-way test messages verified.
- 2026-08-21 — all four templates submitted; Secrets Manager completed.
- 2026-08-24 — templates confirmed approved. Remaining: deploy pipeline,
  deployment, WABA payment, Zoho workflow, live test, business verification.

## Deliberately not done

- No credentials were requested in chat, printed, or committed.
- No deployment has been performed yet.
- WABA payment method and Meta business verification are pending on the
  organisation (finance approval and registration documents respectively).
