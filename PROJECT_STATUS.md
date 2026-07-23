# Project Status and Handoff

**Updated:** 2026-07-23

The production-hardening implementation is present in the working tree and has
passed local automated and simulator verification. It has not yet been deployed
or tested against live Meta, Zoho, DynamoDB or Anthropic services.

## Implemented

- Grounded Claude support agent with structurally constrained ticket tools
- Atomic DynamoDB ticket-creation reservation
- Meta HMAC verification that fails closed
- Authenticated Zoho callback with concurrent-callback reservation and recovery
- Retry-safe inbound message claims and HTTP 5xx on transient processing failure
- Checked WhatsApp/Zoho results before lifecycle state advances
- Deterministic three-working-day SLA and student-confirmation lifecycle
- Hourly sweeper, GSIs, TTL, point-in-time recovery and encryption in SAM
- Safe v2 DynamoDB table replacement; legacy table retained because both GSIs
  cannot be added to an existing table in one AWS update
- EventBridge retry/dead-letter configuration
- Optional SNS operations alarms and 30-day log retention
- Masked student identifiers in application logs
- 90-day inactive conversation TTL (configurable)
- Pinned production/dev dependencies
- Corrected local mock confirmation and escalation behavior
- Deployment documentation and operations runbook

## Verified locally

- `python -m pytest -q`: 40 passed
- Python bytecode compilation: passed
- Scripted login -> ticket -> resolved -> student says still broken -> reopen: passed
- `git diff --check`: passed

AWS SAM CLI is not installed on the current workstation, so final SAM transform
validation is delegated to the GitHub Deploy workflow (`sam validate` and
`sam build`) before CloudFormation can change infrastructure.

## Required from the project owner before deployment

1. Replace `<LMS_URL>` and `<SUPPORT_EMAIL>` in every knowledge file.
2. Confirm the LMS administrator WhatsApp number.
3. Add/verify every Secrets Manager field listed in `README.md`.
4. Rotate the WhatsApp verify token because an earlier value appeared in tracked
   documentation and therefore must be considered exposed.
5. Submit/approve all four Meta WhatsApp templates.
6. Configure Zoho's Resolved workflow with `X-Webhook-Secret`.
7. Confirm the GitHub OIDC deployment role is scoped and not AdministratorAccess.
8. Run the manual deployment, confirm the SNS email subscription, then execute
   the controlled live test in `RUNBOOK.md`.

## Deliberately not done

- No credentials were requested in chat, printed, or committed.
- No live AWS, Meta, Zoho or Anthropic calls were made.
- Existing user-owned edit to the simulator administrator number was preserved.
- No repository commit or deployment was performed.
