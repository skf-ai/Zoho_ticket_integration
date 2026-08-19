# Project Status and Handoff

**Updated:** 2026-08-19

## Current stage

**Code complete and locally verified (59 tests passing); not yet deployed or
tested against live Meta, Zoho, DynamoDB or OpenAI services.** The remaining
work is entirely account setup and deployment, not programming.

The active workstream is onboarding the real support number to the WhatsApp
Business Platform. The office business number was removed from the WABA; the
spare number **8925993784** (now on a new phone/SIM) will be onboarded for
testing and — once the controlled live test passes — circulated to students as
the production support number. The system is still configured with Meta's
**test** phone number until then.

**Next actions, in order:** follow
[`deployment/meta-whatsapp-setup.md`](deployment/meta-whatsapp-setup.md)
top to bottom. It covers freeing the number from the consumer WhatsApp app,
adding it to WABA `991209477079437`, the permanent System User token, app
secret, billing, template submission, Secrets Manager, first deployment,
webhook wiring, the controlled live test, and the go-live checklist.

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

## Required from the project owner before deployment

Everything below is walked through step by step in
[`deployment/meta-whatsapp-setup.md`](deployment/meta-whatsapp-setup.md).

1. Onboard `8925993784` to the WABA (delete its consumer WhatsApp account
   first) and put its new Phone Number ID in Secrets Manager.
2. Replace the temporary WhatsApp token with a permanent System User token.
3. Fill `whatsapp_app_secret`; rotate `whatsapp_verify_token` because an
   earlier value appeared in tracked documentation and must be considered
   exposed.
4. Add billing to the WABA and submit/approve all four Meta WhatsApp templates.
5. Replace `<LMS_URL>` and `<SUPPORT_EMAIL>` in every knowledge file.
6. Add the OpenAI key (`llm_api_key`) and confirm the LMS administrator
   WhatsApp number (`lms_admin_wa_id`) in Secrets Manager.
7. Configure Zoho's Resolved workflow with `X-Webhook-Secret`.
8. Confirm the GitHub OIDC deployment role is scoped and not AdministratorAccess.
9. Run the manual deployment, confirm the SNS email subscription, then execute
   the controlled live test in `RUNBOOK.md`.
10. Only after the live test passes: complete Meta business verification and
    circulate `8925993784` to students.

## History

- 2026-07-23 — production-hardening implementation verified locally (40 tests).
- Later hardening: stuck-state recovery, timeout budget, silent-nudge fixes;
  default model switched to GPT-5 mini with Zoho dual-auth; reasoning cap,
  verification-in-history reopen fix, student self-close (59 tests).
- 2026-08-19 — office business number removed from the WABA; decision to
  onboard spare number `8925993784` for testing and production; Meta go-live
  guide added.

## Deliberately not done

- No credentials were requested in chat, printed, or committed.
- No live AWS, Meta, Zoho or OpenAI calls were made.
- No deployment was performed.
