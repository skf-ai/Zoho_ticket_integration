# Project Status and Handoff

**Updated:** 2026-10-23

## Current stage

**PRODUCTION-READY. All 10 go-live steps complete, including Meta business
verification.** The WhatsApp support line (+91 89259 93784) has been
answering real students since 2026-08-25, and every account-side blocker
(billing, business verification, webhook wiring, admin contact details) is
now closed as of 2026-10-07.

**What's genuinely still open, in order of what blocks wide circulation:**

1. **AWS billing alarm + OpenAI spend limit not yet set.** `COSTS.md` says to
   do this "on day one" — still outstanding as of this update. Five minutes
   each: AWS Console → Billing → Budgets (monthly, $20); platform.openai.com
   → Settings → Limits.
2. **The number has not been circulated to all students yet.** Per the
   project's own recommendation, start with one class/group, watch the admin
   dashboard and Naidu ji's nudges for a few days, then expand — not an
   all-students blast on day one.
3. **Decide the first launch batch** (one class/group, not everyone at once).

Everything else — code, infrastructure, Zoho configuration, admin tooling,
Meta/WABA setup, business verification, documentation — is done.

## What was proven in production this cycle (2026-09-01 → 2026-09-28)

- **Admin panel**, `GET /admin?key=...` (404 without a valid key): Overview +
  Reports, real LIVE-badged spend from AWS Cost Explorer (scoped to this
  project's own services, not the whole shared AWS account), OpenAI org
  costs, and Meta conversation analytics, with honest ESTIMATE fallbacks and
  reasons when a billing API isn't reachable. Manual refresh only (no
  auto-poll, to keep AWS query costs near zero). Ticket timeline with
  per-ticket nudge counts and admin-response stats.
- **Per-person admin panel access** (2026-09-25): distinct keys per role —
  Kalyani and Naidu ji get the full dashboard; **Archana gets a completely
  different, minimal page** (one number: tickets overdue right now, green/red,
  one instruction sentence) matching her role as a daily oversight glance, not
  an operator. Not real login (no passwords/sessions) — a stopgap until the
  separate SKF Admin Console project's Cognito-based login is ready; documented
  as such so nobody mistakes it for more security than it is.
- **Abuse/cost brakes** (2026-09-02): per-number hourly rate limit (30
  messages/hour) and a global daily AI-call budget (~₹85/day hard ceiling),
  fail-open so a broken brake never silences real students. Load-tested live:
  a 35-message flood from one number was cut off exactly at message 31, at
  ₹0 cost for the remainder.
- **Load/concurrency tested in production**: health burst, multi-student
  burst, single-conversation hammer, and a duplicate-delivery storm (Meta
  redelivering the same message id 8× produced exactly one processed reply).
  Found and fixed: the AWS account's default Lambda concurrency (10) was too
  low for real traffic; a quota increase to 1,000 was requested and approved
  the same day.
- **The full accountability loop ran unattended over real days**, not just in
  the simulator: ticket `#...840001` (2026-09-03) got an admin nudge same day,
  a second nudge the next working day, and auto-closed exactly on the 3-working-day
  SLA deadline with the "closed, message us to reopen" notice — proving the
  sweeper, the SLA clock, and paid template delivery all work correctly with
  zero human intervention.
- **Two real gaps found and fixed by exercising the live system, not by
  reading the code:**
  - *Zoho notification leak:* the built-in "notify all department agents on
    new ticket" broadcast was emailing two people who shouldn't have been
    getting it. Fixed with a custom function + Deluge `sendmail` sending to
    exactly one address, and the built-in broadcast turned off. See
    `RUNBOOK.md` if this needs extending to more recipients later.
  - *Zoho Blueprint gap (2026-09-25):* the department's default ticket
    Blueprint had its "Resolve" button wired to go **straight to Closed**,
    completely bypassing the Resolved status our Zoho→system webhook listens
    for. Any agent clicking the normal "Resolve" button would have silently
    skipped the entire student-confirmation loop. Fixed by adding "Resolved"
    as a real state in the Blueprint and rerouting "Resolve" to land there;
    verified live (ticket `#116`: Resolve → Resolved → phone confirmation →
    Yes → Closed). **This is the reason `RUNBOOK.md`'s "set Resolved, never
    Closed" rule matters — it was one click away from being unenforceable.**
- **Agent prompt fix:** the escalation intake question could be asked
  repeatedly instead of raising the ticket after one round — fixed to ask
  once, then proceed with "not provided" for anything unanswered.
- **Ticket descriptions render as labelled lines** in Zoho (HTML line breaks,
  not one paragraph), verified readable.
- Full regression suite: **85 automated tests, all passing.**

## What shipped this cycle (2026-09-29 → 2026-10-23)

- **Account-side go-live blockers closed:** WABA billing added (card on
  `1714263309803387`), stack deployed, Meta webhook repointed at the live API
  Gateway URL, **Meta business verification completed** (2026-10-07, after
  one rejected attempt — resubmitted with a corrected legal name match), and
  a full live ticket cycle (`#127`) confirmed end to end on the real number.
- **Permanent 90-day conversation archive**, separate from the DynamoDB
  working-memory table (which still trims to 20 messages for LLM cost): every
  inbound/outbound message, text and image, is written to a new S3 bucket
  (`MediaBucket`, 90-day lifecycle rule, `src/media_store.py`). Exists purely
  for audit/reporting — the agent never reads from it.
- **Student screenshots now attach to the Zoho ticket**, not just get
  acknowledged: downloaded via the WhatsApp Media API, archived to S3, and
  attached to the ticket immediately if one is already open, or held and
  flushed onto the ticket the moment `raise_ticket` creates one
  (`src/agent.py::_handle_image`, `src/tools.py::_flush_pending_attachments`).
  **Found and fixed a real production bug** (2026-10-05/07): every upload was
  silently failing with a bare `HTTPClientError` from a botocore >=1.36
  default-on checksum-trailer behavior that broke in this Lambda's network
  path; fixed by forcing `request_checksum_calculation="when_required"` on
  the S3 client. Confirmed working live after the fix.
- **Ticket description readability fixed:** every line now renders as its own
  margined block instead of being jammed flush together; emails in the
  description are clickable `mailto:` links; key fields (registered email,
  department, course name, institution, registration ID) are bolded.
- **Two new ticket fields:** institution/college name (strongly requested,
  not a hard block — a stuck student is worse than one ticket gap) and
  student registration/ID number (best-effort). Both bolded in the ticket.
- **Short ticket numbers** (`ticketNumber`, e.g. "#127") shown to students and
  admins everywhere, instead of Zoho's long internal id — the long id is kept
  internally for every API call.
- **Bot tone rewritten to sound human**, not like a form: contractions,
  reacts to what the student said before moving on, light WhatsApp `*bold*`
  and emoji where it genuinely helps — never a checklist unless it's
  literally numbered steps.
- **Knowledge base and intake flow updated** from real usage feedback:
  Gmail-SSO-first login guidance (the ~90% path), course-status-filter tip
  for "course not showing," old/new email capture for email-correction
  requests.
- **Admin panel font-size bug fixed** (root `<html>` size was never set, so
  `rem`-based sizing had nothing to scale from).
- **New-ticket notification email switched** off the old leaked address to
  the real admin inbox (`siksha@srisiddhanta.org`), via the
  `NotifyMeOnNewTicket` Deluge function.
- `lms_admin_wa_id` updated to Naidu ji's real WhatsApp number
  (confirmed set).
- Full regression suite grew to **93 automated tests, all passing**, covering
  every change above (image handling, pending-attachment flush, ticket
  description formatting, webhook message normalization for images).

## Documentation and demo materials produced this cycle

- `TESTING.md` — 5-phase pre-live test script + a production-ready sign-off
  checklist, cost ~₹25–30 per full pass.
- `loadtest.py` — signed-webhook burst/hammer/duplicate-storm harness against
  the real deployed system.
- Three presentation artifacts (private; share from each page's Share menu
  before sending a link to anyone who isn't the owner):
  - **Architecture + workflow sheet** (technical, with price tags on every
    point money moves) — printable A3.
  - **"For Everyone" leadership deck** — plain-language, no jargon, the
    six-step journey as an illustrated flow, for directors.
  - **Live-demo slide deck** — a self-contained illustrated story (a named
    example student, phone-mockup screens for both the student's and the
    admin's side of the conversation) built to present without switching to
    a live phone or live Zoho.
  - A printable, checkbox-style **end-to-end simulation script** for a solo
    rehearsal before presenting to anyone.

## Meta / WhatsApp — completed 2026-08-20/21

- Old office number removed from the WABA (was Unverified; nothing lost).
- Support number **+91 89259 93784** added to WABA `991209477079437` (later
  corrected to the number's real WABA id `1714263309803387` — the July-era
  WABA id in early docs was stale), OTP-verified, **registered on the Cloud
  API** — status **Connected**, quality **High**. Phone Number ID
  `1181089108432432`.
- Two-way messaging verified from the API Setup test page (inbound + template).
- Permanent access token generated (rotated once after a screenshot exposure)
  and stored in Secrets Manager.
- All four Utility templates **approved** in plain English (`en`), names
  matching the code exactly: `ticket_pending_admin`, `issue_resolved_check`,
  `ticket_reminder_student`, `ticket_auto_closed`.
- **WABA payment method added** (2026-09-02) — confirmed active by real
  evidence: a paid template delivered outside any free 24h window (the
  `#...840001` auto-close notice, four days after the student's last message).
- Secrets Manager `siddhanta/whatsapp-zoho` fully populated, including
  `whatsapp_app_secret`, rotated `whatsapp_verify_token`,
  `zoho_webhook_secret`, `llm_api_key`, `lms_admin_wa_id`,
  `admin_dashboard_key`, `whatsapp_waba_id`, `openai_admin_key`.
- Knowledge files verified free of `<LMS_URL>`/`<SUPPORT_EMAIL>` placeholders.

The full click-by-click record is
[`deployment/meta-whatsapp-setup.md`](deployment/meta-whatsapp-setup.md).

## Implemented

- Grounded AI support agent (OpenAI GPT-5 mini by default, provider-swappable)
  with structurally constrained ticket tools; collects registered email,
  error text, and urgency before raising a ticket, asked once, never re-asked
- Atomic DynamoDB ticket-creation reservation; per-number and global AI-call
  rate limits (fail-open)
- Meta HMAC verification that fails closed
- Authenticated Zoho callback with concurrent-callback reservation and recovery
- Retry-safe inbound message claims and HTTP 5xx on transient processing failure
- Checked WhatsApp/Zoho results before lifecycle state advances
- Deterministic three-working-day SLA and student-confirmation lifecycle;
  reopen-on-"No" both internally and visibly in Zoho's own status field
- Hourly sweeper, GSIs, TTL, point-in-time recovery and encryption in SAM
- EventBridge retry/dead-letter configuration; optional SNS operations alarms
  and 30-day log retention
- Masked student identifiers in application logs
- 90-day inactive conversation TTL on the DynamoDB working-memory table
  (configurable) -- separate from the permanent S3 conversation archive below
- **Permanent 90-day S3 archive** of every message (text + images), for
  audit/reporting -- never read by the agent itself
- **Student screenshots attached to Zoho tickets** automatically (immediately
  if a ticket is open, held and flushed onto one the moment it's raised)
- Institution name and registration ID collected and bolded on every ticket
- Admin panel with real per-service billing and per-person, role-appropriate
  views
- Auto-deploy on every push to `main` (tests gate it; concurrency-guarded)
- Deployment documentation, operations runbook, Meta go-live guide, pre-live
  test script, load-test harness, and three audience-appropriate presentation
  artifacts

## Verified

- `python -m pytest -q`: **93 passed**
- Load/concurrency/duplicate-storm tests against the live deployed system: passed
- Full lifecycle proven unattended over real elapsed days in production
  (not just the simulator)
- Zoho Blueprint fixed and live-verified (ticket #116)
- Notification routing fixed and verified (single recipient, correct link)
- Live ticket cycle re-verified post-cycle (ticket #127, 2026-10-05):
  raise → image attach (after the S3 checksum fix) → resolve → confirm → close

## History

- 2026-07-23 — production-hardening implementation verified locally (40 tests).
- 2026-08-19/24 — number onboarded to the WABA, registered, templates approved.
- 2026-08-25 — deployed; bot answering real messages after fixing the
  WABA-level "Subscribe webhooks" toggle (the actual missing link).
- 2026-08-26/27 — full ticket lifecycle verified live; auto-deploy enabled.
- 2026-09-01/02 — admin panel shipped with real billing; WABA payment added;
  abuse brakes shipped and load-tested live; AWS Lambda concurrency quota
  raised; sweeper's full 3-day cycle proven unattended in production.
- 2026-09-17 — related project (SKF Admin Console) scoped for a future
  unified, Cognito-based login across all managed systems; deliberately not
  merged into this project to avoid building two login systems.
- 2026-09-24/25 — admin panel got per-person role-based views; Zoho
  notification broadcast leak found and fixed; Zoho Blueprint "Resolve"
  gap found and fixed, verified live end to end.
- 2026-09-29/30 — WABA billing added on the correct account
  (`1714263309803387`); knowledge base and intake flow updated from real
  Naidu ji feedback; ticket description bolding/mailto-links added; short
  ticket numbers threaded through every student/admin-facing message;
  admin panel font-size bug fixed; new-ticket email switched off the leaked
  address.
- 2026-10-05/07 — permanent 90-day S3 conversation/image archive shipped;
  image-attachment-to-ticket feature shipped, then found broken in
  production (botocore checksum-trailer `HTTPClientError`) and fixed, then
  re-verified live; ticket description spacing fixed; **Meta business
  verification completed** after one rejected resubmission; `lms_admin_wa_id`
  updated to Naidu ji's real number; bot tone rewritten to sound human;
  institution name + registration ID added as ticket fields.

## Deliberately not done

- No credentials were ever requested in chat, printed, or committed; any
  value that did appear in chat (an admin key, a Zoho refresh token, an
  OpenAI admin key) was rotated/revoked the same session.
- Real login (passwords/sessions) for the admin panel was deliberately not
  built here a second time — see the SKF Admin Console note above.
- Institution name is strongly requested on every ticket, not a hard block --
  a student stuck unable to raise a ticket over one missing field is a worse
  outcome than a ticket with "Institution: not provided" the admin can chase.
- AWS billing alarm and OpenAI spend limit are organisation account actions,
  not engineering work -- still outstanding, see "What's genuinely still
  open" above.
