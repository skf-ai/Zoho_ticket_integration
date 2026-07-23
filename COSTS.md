# Costs, accounts, and credentials — read this first

**Purpose:** every place this system spends money, every account it depends on,
and what breaks if one of them lapses. Written so that someone who has never seen
this project can pick it up and keep it running.

**Last updated:** 2026-07-23

> If you are taking this project over: read this file, then [README.md](README.md)
> for what the system does, then [PROJECT_STATUS.md](PROJECT_STATUS.md) for where
> the build had got to.

---

## 1. The short version

| What | Who bills you | Roughly | Paid how |
|---|---|---|---|
| AI model (Claude Haiku) | Anthropic | $10–20 / month | Per use, card on file |
| AWS hosting | Amazon | $2–4 / month | Per use, card on file |
| WhatsApp messages | Meta | ₹100–200 / month | Per message, card on WABA |
| Zoho Desk | Zoho | Existing subscription | Per agent, per month |

**New spend created by this project: roughly $15–25 / month (₹1,300–2,200).**
Zoho was already being paid for before this project started.

Everything is usage-based except Zoho. Nothing here has a minimum commitment or a
lock-in contract.

---

## 2. Each cost in detail

### 2.1 The AI model — Anthropic

**What it's for:** reading student messages and deciding how to answer.

**How billing works:** per unit of text processed. No subscription, no minimum.

- Model in use: `claude-haiku-4-5` (deliberately the cheap tier — see below)
- Roughly **$0.006 per student conversation** (about half a rupee)
- A heavy exam day of 500 conversations costs about **$3**
- Typical month: **$10–20**

**Why the cheap model:** the job is matching a student's problem to a known FAQ
and deciding whether a human is needed. That sits well inside Haiku's ability. A
frontier model would cost 5× more for no benefit here. If quality testing later
shows it missing real cases, raise `LLM_MODEL` — see §5.

**Not locked in.** The code talks to models through `src/llm.py`, which is
provider-neutral. Switching to OpenAI, Google, Groq, or a self-hosted model is a
change of two environment variables, not a rewrite. Prices at this tier move every
few months; re-check yearly.

**Where to see spend:** console.anthropic.com → Usage.
**Set a monthly spend limit there.** Do this on day one.

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

**One thing to verify:** the "student verified it's fixed" loop needs a Zoho
**Workflow Rule that calls a webhook** when a ticket becomes Resolved. Not every
plan includes workflow rules — the free tier (3 agents) does not.

- If your plan supports it: no extra cost.
- If it does not: either upgrade, **or** use the polling fallback (the scheduled
  worker checks Zoho for resolved tickets instead of Zoho notifying us). The
  fallback costs nothing and avoids the upgrade.

**Record your plan here when you check it:** ______________________

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
| `whatsapp_token` | Meta access token | ⚠️ **Currently temporary — expires in ~24h** |
| `whatsapp_phone_number_id` | 1121518577721735 | ⚠️ Currently Meta's **test** number |
| `whatsapp_waba_id` | 991209477079437 | Stable |
| `whatsapp_verify_token` | stored in Secrets Manager; rotate if previously exposed | Chosen by us |
| `whatsapp_app_secret` | Verifies messages truly come from Meta | ⚠️ **Currently empty** |
| `llm_api_key` | Anthropic API key | Not yet added |
| `lms_admin_wa_id` | Admin's WhatsApp number for nudges | Not yet added |

### The three that need fixing before go-live

1. **`whatsapp_token` is temporary.** It expires roughly daily. Replace it with a
   permanent **System User token** from Meta Business Settings. Until then the
   system stops sending messages every day without warning.
2. **`whatsapp_app_secret` is empty.** Without it, anyone who discovers the web
   address can send fake student messages and make the system create tickets. Fill
   it in from the Meta app dashboard.
3. **The phone number is Meta's test number.** Real students cannot use it. Add
   and verify the real business number.

---

## 4. What breaks if a bill goes unpaid

Ranked by how bad it is, and how obvious it would be.

| If this lapses | What happens | Would you notice? |
|---|---|---|
| **Meta WhatsApp payment** | Admin nudges and verification prompts stop. Students still get answered. **Tickets silently stop being chased — the exact problem this system was built to fix.** | ❌ **No — this fails invisibly.** Watch for it. |
| **Anthropic / AI provider** | The bot cannot answer. Falls back to a plain "we're unavailable" message. Ticket chasing keeps working. | ✅ Yes, immediately |
| **AWS account** | Everything stops. | ✅ Yes, immediately |
| **Zoho Desk** | No tickets can be created or closed. | ✅ Yes, immediately |
| **`whatsapp_token` expires** | All outbound WhatsApp stops. Students get silence. | ⚠️ Only if someone is watching logs |

**The lesson:** the AI failing is loud and safe. WhatsApp billing failing is quiet
and dangerous. Set a billing alert on the Meta account specifically.

---

## 5. Cutting costs safely

**Safe to do:**

- **Set spend caps** on Anthropic and an AWS billing alarm. Costs nothing, prevents
  a surprise.
- **Set CloudWatch log retention to 30 days.** Logs otherwise accumulate forever.
- **Keep the cheap model.** `LLM_MODEL=claude-haiku-4-5`. Only raise it if
  testing shows real failures.
- **Keep the knowledge base good.** Every question it answers without a ticket
  saves a paid nudge and the admin's time. Improving `knowledge/*.md` is the
  highest-return, zero-cost work available.
- **Apply for non-profit credits.** Google, AWS, and Microsoft all run non-profit
  programmes. AWS credits alone could cover hosting entirely.

**Do NOT cut these:**

- **Do not reduce admin nudges to zero.** They cost ₹0.115 each and they are the
  entire point of the system.
- **Leave the prompt-caching line in `src/llm.py` alone.** ⚠️ **Correction:** an
  earlier version of this document claimed caching cuts the AI bill ~10×. That
  was wrong. Caching only activates once the fixed part of the prompt exceeds
  **4,096 tokens**, and the knowledge base is currently around **2,600** — so
  caching is *inactive today and saving nothing*. The line costs nothing to keep
  and switches on by itself if the knowledge files grow past that size, which is
  likely as you add topics. When it does activate, never put a timestamp, name,
  or ticket number above the cache marker in that file — that silently disables
  it again with no error.
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
| Anthropic API | | |
| GitHub repo | skf-ai/Zoho_ticket_integration | |
| LMS admin (receives nudges) | | |

---

## 7. Monthly checklist

Five minutes, once a month:

- [ ] Check Anthropic usage is in the expected range
- [ ] Check the AWS bill has no surprises
- [ ] Check the Meta WhatsApp account still has a valid payment method
- [ ] Check tickets are actually being closed, not just piling up
- [ ] Check the holiday list in `src/workdays.py` is still correct for the year
      ahead — a stale list closes tickets a day early
