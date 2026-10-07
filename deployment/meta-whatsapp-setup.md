# Meta / WhatsApp Business Platform setup — go-live guide

**Updated:** 2026-10-07

## Progress record

| Step | Status |
|---|---|
| 0 — Free the number from the consumer app | ✅ 2026-08-19 |
| 1 — Add number to WABA (OTP verified, then registered via guided setup; Phone Number ID `1181089108432432`) | ✅ 2026-08-20 — **Connected**, quality High |
| 2 — Phone Number ID in Secrets Manager | ✅ 2026-08-20 |
| 3 — Permanent token (via Meta guided setup "Generate token"; no manual System User needed) | ✅ 2026-08-20 (rotated once after a screenshot exposure) |
| 4 — App secret + fresh verify token | ✅ 2026-08-21 |
| 5 — Billing on the WABA | ✅ 2026-09-30 — Visa •••1007 added to WABA `1714263309803387` |
| 6 — Four templates submitted | ✅ approved 2026-08-21/24, plain English (`en`) |
| 7 — Remaining secret keys | ✅ 2026-08-21 |
| 8 — Deploy + wire webhook | ✅ 2026-09-30 — webhook pointed at `https://1msg3v5m48.execute-api.ap-south-1.amazonaws.com/Prod/whatsapp`, `/health` returns `ready: true` |
| 9 — Controlled live test | ✅ 2026-10-05 — ticket raise/resolve/close cycle confirmed live (ticket #127) |
| 10 — Business verification + circulate number | ✅ verified 2026-10-07 — **number not yet circulated to students**, see below |

This is the complete, ordered checklist to take the system from "code done" to
live on the real support number. Work top to bottom; each step tells you where
to click and what to store.

**The support number:** `8925993784` (E.164: `918925993784`). Plan: onboard it
to the WhatsApp Business Platform, run the controlled live test, and only then
circulate it to students as the official support line.

**What already exists** (do not recreate):

| Asset | Value |
|---|---|
| Meta WABA (WhatsApp Business Account) | `1714263309803387` (⚠️ superseded the earlier `991209477079437` referenced in older notes below — always check `whatsapp_waba_id` in Secrets Manager for the live value) |
| Currently configured number | Meta's **test** number (`1121518577721735`) — to be replaced |
| AWS Secrets Manager secret | `siddhanta/whatsapp-zoho`, region `ap-south-1` |

---

## Step 0 — Free the number from the normal WhatsApp app

Meta refuses to onboard a number that is actively registered on the consumer
WhatsApp (or WhatsApp Business) app.

1. If the number is currently signed in to the WhatsApp app on any phone:
   WhatsApp → **Settings → Account → Delete account**. (Old chats are lost —
   already accepted.)
2. Wait ~5 minutes before Step 2.
3. Keep the SIM in a phone that can **receive SMS or a voice call** — that is
   all the physical phone is needed for. After onboarding, the number lives in
   Meta's cloud; the phone/SIM only matters again if you ever re-verify.

> Once onboarded to the Cloud API, this number **cannot** simultaneously be
> used in the normal WhatsApp app. All conversations happen through the bot.

## Step 1 — Add the number to the WABA

1. Go to [developers.facebook.com](https://developers.facebook.com) → your app
   → **WhatsApp → API Setup**.
2. Under **Send and receive messages → From**, choose **Add phone number**.
3. Enter `+91 8925993784`, choose the **display name** students will see (e.g.
   the organisation/LMS support name — Meta reviews it; avoid generic words
   like just "Support"), pick category and timezone.
4. Verify with the **SMS or voice OTP** sent to the SIM.
5. When it appears in the number list, copy its new **Phone Number ID** —
   this replaces the test number's ID everywhere.

## Step 2 — Update Secrets Manager

AWS Console → Secrets Manager (`ap-south-1`) → `siddhanta/whatsapp-zoho`:

- `whatsapp_phone_number_id` → the new Phone Number ID from Step 1.
- `whatsapp_waba_id` stays `1714263309803387` (confirm against the live value in Secrets Manager — see note above).

(If the stack is already deployed when you change any secret, redeploy so
Lambda containers pick up the new value — see `RUNBOOK.md` → Rotate credentials.)

## Step 3 — Permanent System User token (replaces the ~24h token)

The temporary token from API Setup dies daily. Production needs a System User
token that never expires:

1. [business.facebook.com](https://business.facebook.com) → **Settings →
   Users → System users → Add**. Name it e.g. `whatsapp-bot`, role **Admin**.
2. On the system user → **Add assets**: assign **the app** (full control) and
   **the WABA** (full control).
3. **Generate new token** → select the app → expiration **Never** →
   permissions: `whatsapp_business_messaging` + `whatsapp_business_management`.
4. Store it as `whatsapp_token` in Secrets Manager. Never paste it in chat,
   commits, or tickets.

## Step 4 — App secret and verify token

1. App dashboard → **Settings → Basic → App secret → Show** → store as
   `whatsapp_app_secret`. (Without it the webhook rejects everything — it
   fails closed.)
2. Invent a fresh long random string for `whatsapp_verify_token` (the old one
   appeared in tracked docs and is considered exposed — do not reuse it).

## Step 5 — Billing on the WABA

WhatsApp Manager → **Overview / Payment settings** → add a payment method
(card) against the WABA. Template messages silently fail on an unfunded
account. Expected spend is small (see `COSTS.md`).

## Step 6 — Submit the four message templates

Follow [`deployment/whatsapp-templates.md`](whatsapp-templates.md) exactly
(names must match the code). Templates belong to the **WABA**, not the number,
so anything already approved carries over to the new number automatically.
Approval is usually hours, sometimes days — submit early.

## Step 7 — Fill the rest of the secret

Confirm every key in `README.md` → Production configuration is present:
Zoho keys, `zoho_webhook_secret` (invent one; same value goes in the Zoho
workflow header), `llm_api_key` (OpenAI), and `lms_admin_wa_id` (the LMS
administrator's WhatsApp number, digits only with country code).

## Step 8 — Deploy and wire the webhook

1. Deploy via GitHub Actions (`DEPLOYMENT.md`): Actions → **Deploy** →
   Run workflow. Copy the `ApiBaseUrl` output.
2. App dashboard → WhatsApp → **Configuration → Webhook**: callback URL
   `<ApiBaseUrl>/whatsapp`, verify token = `whatsapp_verify_token`, then
   **Verify and save**, and subscribe to the **messages** field.
3. Configure the Zoho Desk "Resolved" workflow with `X-Webhook-Secret`
   (`DEPLOYMENT.md`).
4. Open `<ApiBaseUrl>/health` — require HTTP 200 and `"ready": true`.

## Step 9 — Controlled live test

Run the full script in `RUNBOOK.md` → Controlled live test, messaging
`8925993784` **from a different phone** (your personal number acts as the
student). Unlike the Meta test number, a real number has **no 5-recipient
allowlist** — any phone can message it — so keep the number private until the
test passes.

## Step 10 — Before circulating the number to students

- [ ] Live test passed end to end (ticket create → resolve → verify → close).
- [ ] Token is the permanent System User token (Step 3), not a temporary one.
- [ ] Display name approved by Meta (visible in WhatsApp Manager).
- [ ] Billing active; templates all show **Approved**.
- [ ] SNS alert email subscription confirmed (if `AlertEmail` was set).
- [ ] **Business verification** (Business Settings → Security Centre):
      an unverified business is capped at **250 business-initiated
      conversations per 24h** — fine for testing, tight for production.
      Complete verification to raise the limit (1,000+, scaling with quality).
      Student-initiated replies inside the 24h window are not limited.

Then publish `8925993784` to students as the LMS support WhatsApp number.

---

## If something fails during onboarding

- **OTP never arrives:** try the voice-call option; ensure the SIM has signal
  and can receive international-originated SMS.
- **"Number is already in use on WhatsApp":** Step 0 was skipped or the
  deletion hasn't propagated — delete the account in the app and wait.
- **Display name rejected:** WhatsApp Manager shows the reason; resubmit with
  the organisation's real, verifiable name.
- **Messages send but nothing arrives:** check billing (Step 5), then the
  recipient hasn't blocked the number, then `RUNBOOK.md` → Bot stopped replying.
