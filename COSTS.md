# Costs, accounts, and credentials — read this first

**Purpose:** every place this system spends money, every account it depends on,
and what breaks if one of them lapses. Written so that someone who has never seen
this project can pick it up and keep it running.

**Last updated:** 2026-08-24

> If you are taking this project over: read this file, then [README.md](README.md)
> for what the system does, then [PROJECT_STATUS.md](PROJECT_STATUS.md) for where
> the build had got to.

---

## 1. The short version

| What | Who bills you | Roughly | Paid how |
|---|---|---|---|
| AI model (GPT-5 mini) | OpenAI | $5–10 / month | Per use, card on file |
| AWS hosting | Amazon | $2–4 / month | Per use, card on file |
| WhatsApp messages | Meta | ₹100–200 / month | Per message, card on WABA |
| Zoho Desk | Zoho | Existing subscription (Zoho One) | Per agent, per month |

**New spend created by this project: roughly $10–20 / month (₹850–1,700).**
Zoho was already being paid for before this project started.

Everything is usage-based except Zoho. Nothing here has a minimum commitment or a
lock-in contract.

---

## 2. Each cost in detail

### 2.1 The AI model — OpenAI (GPT-5 mini)

**What it's for:** reading student messages and deciding how to answer.

**How billing works:** per unit of text processed. No subscription, no minimum.

- Model in use: `gpt-5-mini` — chosen after comparing OpenAI, Google and Anthropic
- Rate: about **$0.13 per million input tokens, $1.00 per million output**
- Roughly **$0.002 per student conversation**
- A heavy exam day of 500 conversations costs well under **$1**
- Typical month: **$5–10**

**⚠️ Correction to an earlier version of this file.** A first draft said
"~$10–20/month on Claude Haiku, with prompt caching cutting the bill ~10×." That
was wrong on two counts: Haiku costs $1/$5 per million (≈7× GPT-5 mini for this
workload), and its caching does **not** activate below a 4,096-token prompt while
our knowledge base is ~2,600 tokens — so on Haiku the KB resent every turn was
billed at full price. GPT-5 mini is cheaper per token **and** caches at our size
(OpenAI caches automatically above ~1,024 tokens), so the repeated KB is billed
at a steep discount. Net: GPT-5 mini is the value winner here.

**Why this model** (chosen neutrally — this project was built with Claude tooling,
but Claude is *not* the pick): at your volume every option is cheap in rupees, so
the decision was made on **tool-calling reliability first** (a bad tool call = a
ticket never created), then **longevity** (won't be retired soon), then cost.
GPT-5 mini wins that combination. Google Gemini Flash-Lite is marginally cheaper
but retires Oct 2026 (a forced change) and is less proven at strict tool-calling.
Claude Haiku is reliable but ~7× the cost here with no caching benefit.

**Not locked in.** The code talks to models through `src/llm.py`, provider-neutral.
Switching to Gemini, Claude, or a self-hosted model is a change of the
`LLM_PROVIDER`, `LLM_BASE_URL` and `LLM_MODEL` environment variables plus the key
— not a rewrite. Re-check prices yearly.

**Where to see spend:** platform.openai.com → Usage.
**Set a monthly spend limit** (Settings → Limits). Do this on day one.

---

### 2.2 AWS hosting

**Account:** 417311687123 · **Region:** ap-south-1 (Mumbai)

| Service | What it does | Cost |
|---|---|---|
| Lambda | Runs the code | ~$0 (inside free tier at this volume) |
| API Gateway | The web address Meta and Zoho send messages to | ~$0.05 / month |
| DynamoDB | Remembers conversations and tickets | <$1 / month |
| Secrets Manager | Stores passwords and API keys | $0.40 / month per secret |
| CloudWatch Logs | Records what happened, for debugging | ~$1 / month |

**Total: $2–4 / month.** This will not grow much — the volume is small by AWS
standards.

**Cost trap to avoid:** CloudWatch logs are the one line that can creep upward,
because they accumulate forever by default. Set log retention to 30 days.

**Where to see spend:** AWS Console → Billing → Cost Explorer.
**Set a billing alarm at $20/month.** Do this on day one.

---

### 2.3 WhatsApp messages — Meta

**This is the one people misunderstand, so read it carefully.**

Meta charges **per message**, but only for some messages:

| Message | Cost | When it happens here |
|---|---|---|
| Any reply while the student is actively chatting | **FREE** | Almost every message the bot sends |
| Utility template, sent while the student is actively chatting | **FREE** | Occasionally |
| Utility template, sent later (outside the 24-hour window) | **~₹0.115** | Admin nudges, "is it fixed?" prompts, close notices |
| Marketing template | ~₹0.863 | **We never send these** |

The "24-hour window" means: once a student messages you, everything you send back
for the next 24 hours is free. That covers virtually all normal conversation.

**So what actually costs money:** only the delayed messages — chasing the LMS
admin, asking the student days later whether their issue is fixed, and telling
them a ticket closed.

- Typical ticket: about **₹0.23** (one admin nudge + one verification prompt)
- Worst case ticket: about **₹0.58** (two nudges, a reminder, a close notice)
- Conversations the bot resolves without a ticket: **₹0**
- At ~300 tickets a month: **₹70–170 (about $1–2)**

18% GST applies on Meta's charges.

**A saving you already have:** this connects directly to Meta's Cloud API using
your own app and WhatsApp Business Account. Most Indian organisations go through a
reseller (AiSensy, Wati, Interakt) and pay ₹2,000–3,000/month in platform fees
plus a 10–30% markup on every message. **You pay neither. Do not switch to a
reseller — it would multiply this cost for no benefit.**

**Critical:** a payment method must be attached to the WhatsApp Business Account
before any template message will send. Without it, admin nudges silently fail —
the system looks healthy while doing nothing.

**Where to see spend:** business.facebook.com → WhatsApp Manager → Insights.

---

### 2.4 Zoho Desk

**What it's for:** the ticket system the LMS admin actually works in.

**This was already being paid for before this project.** The API this system uses
costs nothing extra — API access is included in the subscription, subject to daily
limits.

**Plan: Zoho One** (confirmed 2026-07-24). This includes Zoho Desk well above the
Standard tier, so **Workflow Rules with a webhook/custom-function action are
available.** The "student verified it's fixed" loop uses that native path: a
workflow fires our `/zoho-webhook` when a ticket is set to Resolved. No extra
Zoho cost, and no code workaround needed.

The workflow authenticates to us with a shared secret (`zoho_webhook_secret` in
the AWS secret), sent either as an `X-Webhook-Secret` header (Custom Function) or
a `webhook_secret` query parameter (native webhook) — the code accepts both. See
DEPLOYMENT.md for the exact setup.

**Where to see spend:** zoho.com → Subscriptions.

---

### 2.5 One-off and non-money costs

| Item | Cost | Notes |
|---|---|---|
| Meta Business Verification | Free | Needs org registration, PAN, address proof. **Long lead time — start early.** |
| WhatsApp business phone number | Cost of a SIM | Must be a number not already on WhatsApp |
| Display name approval | Free | Meta reviews the name shown to students |
| Publishing the Meta app | Free | Development → Live |

---

## 3. Credentials — what exists, and what expires

All secrets live in **AWS Secrets Manager**, secret name `siddhanta/whatsapp-zoho`,
region ap-south-1. Nothing is stored in the code or in GitHub.

| Key | What it is | Risk |
|---|---|---|
| `zoho_client_id` / `zoho_client_secret` | Zoho app identity | Stable |
| `zoho_refresh_token` | Long-lived Zoho login | Breaks if revoked in Zoho console |
| `zoho_org_id` | 60037340249 | Stable |
| `zoho_department_id` | 146318000000010772 | Stable |
| `zoho_webhook_secret` | Shared secret the Zoho resolved-ticket workflow sends back to prove the callback is genuinely from Zoho | Added 2026-08-21. ⚠️ The same value must go into the Zoho workflow when it is configured |
| `whatsapp_token` | Meta access token | **Permanent** (generated 2026-08-20 via Meta's guided setup; rotated once after a screenshot exposure). Stable |
| `whatsapp_phone_number_id` | 1181089108432432 | The real support number **+91 89259 93784** — Connected, quality High |
| `whatsapp_waba_id` | 991209477079437 | Stable |
| `whatsapp_verify_token` | Proves webhook-verification calls come from us | Rotated 2026-08-21 (old value had appeared in tracked docs). ⚠️ Meta's webhook config still holds the old value — update it when repointing the webhook after deployment |
| `whatsapp_app_secret` | Verifies messages truly come from Meta | Added 2026-08-21 |
| `llm_api_key` | OpenAI API key (for GPT-5 mini) | Added 2026-08-21. Set a spend limit at platform.openai.com |
| `lms_admin_wa_id` | Admin's WhatsApp number for nudges | Added 2026-08-21 |

### Credential status (2026-08-24)

The three go-live blockers from the previous version of this file are **all
fixed**: the token is permanent, the app secret is set, and the real support
number +91 89259 93784 is registered and Connected with all four message
templates approved. What still stands between here and go-live is **not**
credentials:

1. **WABA payment method** (finance approval) — template messages fail silently
   without it.
2. **Deployment** — run the GitHub Deploy workflow, then repoint Meta's webhook
   at the new URL with the rotated verify token.
3. **Meta business verification** (org documents) — raises the 250/day
   business-initiated conversation cap before wide circulation.

---

## 4. What breaks if a bill goes unpaid

Ranked by how bad it is, and how obvious it would be.

| If this lapses | What happens | Would you notice? |
|---|---|---|
| **Meta WhatsApp payment** | Admin nudges and verification prompts stop. Students still get answered. **Tickets silently stop being chased — the exact problem this system was built to fix.** | ❌ **No — this fails invisibly.** Watch for it. |
| **OpenAI / AI provider** | The bot cannot answer. Falls back to a plain "we're unavailable" message. Ticket chasing keeps working. | ✅ Yes, immediately |
| **AWS account** | Everything stops. | ✅ Yes, immediately |
| **Zoho Desk** | No tickets can be created or closed. | ✅ Yes, immediately |
| **`whatsapp_token` expires** | All outbound WhatsApp stops. Students get silence. | ⚠️ Only if someone is watching logs |

**The lesson:** the AI failing is loud and safe. WhatsApp billing failing is quiet
and dangerous. Set a billing alert on the Meta account specifically.

---

## 5. Cutting costs safely

**Safe to do:**

- **Set spend caps** on OpenAI (Settings → Limits) and an AWS billing alarm. Costs
  nothing, prevents a surprise.
- **Set CloudWatch log retention to 30 days.** Logs otherwise accumulate forever.
- **Keep the chosen model.** `LLM_MODEL=gpt-5-mini`. Only change it if testing
  shows real failures — and remember it's a one-env-var switch either way.
- **Keep the knowledge base good.** Every question it answers without a ticket
  saves a paid nudge and the admin's time. Improving `knowledge/*.md` is the
  highest-return, zero-cost work available.
- **Apply for non-profit credits.** Google, AWS, and Microsoft all run non-profit
  programmes. AWS credits alone could cover hosting entirely.

**Do NOT cut these:**

- **Do not reduce admin nudges to zero.** They cost ₹0.115 each and they are the
  entire point of the system.
- **Keep the prompt sending its stable part first.** With GPT-5 mini, OpenAI
  caches the repeated prefix (system prompt + knowledge base, ~3,000 tokens)
  **automatically** above ~1,024 tokens — no code to configure, and it is working
  today, discounting the biggest recurring cost. The one rule: never put a
  timestamp, student name, or ticket number ahead of the knowledge base in
  `src/llm.py`, because that changes the prefix every call and silently switches
  caching off with no error. (On Claude Haiku this caching would *not* apply —
  its 4,096-token minimum is above our ~2,600-token knowledge base — which was
  part of why GPT-5 mini won on cost.)
- **Do not switch to a WhatsApp reseller** to "simplify". It adds ₹2,000–3,000 a
  month for something you already have direct.
- **Do not self-host the AI model.** A GPU server costs more per month idle than
  this entire system costs running. Self-hosting only makes sense at far higher
  volume.

---

## 6. Who to contact

Fill this in and keep it current — this is the part that matters most if the
original team is gone.

| Thing | Who owns it | Login / contact |
|---|---|---|
| AWS account 417311687123 | | |
| Meta Business / WhatsApp | | |
| Zoho Desk | | |
| OpenAI API | | |
| GitHub repo | skf-ai/Zoho_ticket_integration | |
| LMS admin (receives nudges) | | |

---

## 7. Monthly checklist

Five minutes, once a month:

- [ ] Check OpenAI usage is in the expected range
- [ ] Check the AWS bill has no surprises
- [ ] Check the Meta WhatsApp account still has a valid payment method
- [ ] Check tickets are actually being closed, not just piling up
- [ ] Check the holiday list in `src/workdays.py` is still correct for the year
      ahead — a stale list closes tickets a day early
