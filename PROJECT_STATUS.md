# Project Status and Handoff

**Updated:** 2026-08-24

## Current stage

**Code complete and locally verified (59 tests passing). Meta/WhatsApp setup is
DONE: the real support number is live on the Cloud API and all four message
templates are approved.** The system is not yet deployed to AWS; deployment is
the next milestone.

What remains before students can use it, in order:

1. **Deploy role + GitHub secret** — confirm/create the IAM role
   `github-deploy-whatsapp-zoho` trusting `repo:skf-ai/Zoho_ticket_integration`
   (the GitHub OIDC identity provider already exists in account 417311687123
   from another project) and store its ARN as the `AWS_DEPLOY_ROLE_ARN`
   repository secret.
2. **Run the Deploy workflow** (GitHub Actions) and confirm `/health` returns
   `"ready": true`.
3. **Repoint Meta's webhook** to the new `ApiBaseUrl` with the rotated verify
   token, and subscribe the `messages` field.
4. **Configure the Zoho Desk Resolved workflow** with `X-Webhook-Secret`.
5. **WABA payment method** — awaiting finance approval (template sends fail
   silently without it; ~₹100–200/month expected).
6. **Controlled live test** per `RUNBOOK.md`.
7. **Meta business verification** (org documents) — raises the messaging limit
   from 250 business-initiated conversations/day; required before circulating
   the number widely.
8. **Circulate +91 89259 93784 to students** as the official support number.

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
