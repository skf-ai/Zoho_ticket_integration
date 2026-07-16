# Roadmap — WhatsApp → Zoho Desk Support Bot

A WhatsApp helper bot (Meta Cloud API) that answers common student FAQs, and
escalates unresolved queries into Zoho Desk tickets. When support resolves the
ticket, the user is asked on WhatsApp whether it's fixed; "Yes" closes the ticket.

## Architecture

```
Meta WhatsApp Cloud API
        │  inbound webhook (already wired to API Gateway)
        ▼
┌─────────────────────────────────────┐
│  Ingress Lambda                      │
│  1. parse Meta payload (wa_id, text) │
│  2. load conversation state (Dynamo) │
│  3. bot logic: menu / FAQ / escalate │
│  4. send reply to WhatsApp           │
│  5. save state                       │
└───────────┬─────────────────┬────────┘
            │                 │
        DynamoDB          Zoho Desk API
     (state + ticket→    (create / close ticket)
      wa_id mapping)

        ── resolve/close loop ──
Zoho ticket Resolved → Zoho Workflow webhook
   → Lambda sends WhatsApp template "Issue resolved? [Yes][No]"
   → Yes → close ticket via Zoho API
     No  → keep open + add comment
```

## Conversation flow (from architecture diagram)

1. User sends `Hi` → bot presents categories:
   - Login Issue
   - Login Credentials Not Received
   - Other FAQ Categories
   - Others
2. Category selected:
   - **Login Issue / Login Credentials / Other FAQ** → bot sends FAQ answer → "Issue solved? Yes/No"
     - Yes → End
     - No → auto-create Zoho ticket
   - **Others** → user types query → auto-create Zoho ticket
3. Ticket created (username, message, category) → assigned to Support Team (LMS)
4. Support resolves → Zoho sends WhatsApp "Has your issue been resolved?"
5. User feedback: Resolved ✅ → ticket closed | Unresolved ❌ → stays open

## 8-Day Build Timeline (~6 hrs/day)

| Day | Focus | Done when |
|-----|-------|-----------|
| 1 | Foundation + secrets + WhatsApp template submit | Clean repo runs; secrets in Secrets Manager; template submitted to Meta |
| 2 | DynamoDB + outbound WhatsApp sender | Can send buttons+text to a phone; state read/write works |
| 3 | Bot logic: menu + FAQ + "Solved?" | "Hi" returns categories; picking one returns FAQ + Yes/No |
| 4 | Ticket creation wiring + "Others" flow | No/Others creates Zoho ticket w/ category; ticket_id saved to user |
| 5 | Resolve/close loop | Zoho workflow → "resolved?" template; Yes closes, No keeps open |
| 6 | Deploy to AWS (SAM) + re-point Meta | Runs in real Lambda; Meta webhook verified |
| 7 | End-to-end testing on real WhatsApp | Full flow works from a real phone |
| 8 | Buffer: edge cases, monitoring, go-live | Handles bad input/timeouts; live |

## External dependency — start Day 1
The "Has your issue been resolved?" message is sent hours/days later, **outside
WhatsApp's 24-hour window**, so it must be a **pre-approved Meta message template**.
Submit it on Day 1 so it's approved before Day 5.

## Tech decisions
- **Language:** Python 3.12 (matches existing Zoho code; ingress Lambda's Node stub is replaced)
- **Secrets:** AWS Secrets Manager (not `config.json`)
- **State store:** DynamoDB (`wa_id` → step, category, ticket_id)
- **Region:** ap-south-1 · **Account:** 417311687123 · **Zoho DC:** `.in`
- **Reuse the existing ingress Lambda** so Meta's webhook URL doesn't change

## Progress log
- [x] Day 1 — repo restructure + config/secrets layout (in progress)
