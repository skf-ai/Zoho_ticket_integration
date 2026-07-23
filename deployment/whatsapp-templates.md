# WhatsApp message templates to submit to Meta

**Submit these first — they are the longest lead time in the project.** Meta
review is typically hours but can take days, and the accountability engine cannot
send anything until they are approved.

All four are **Utility** category, English (`en`). Utility templates cost roughly
**₹0.115 per message** in India, and are **free** when sent inside an open
24-hour customer service window.

Submit at: Meta Business Suite → WhatsApp Manager → Message templates → Create.

---

## 1. `ticket_pending_admin`

Sent to the **LMS administrator**, chasing an unactioned ticket. This is the one
that fixes the "admin forgets" problem.

- **Category:** Utility
- **Language:** English

**Body:**
```
Reminder: LMS support ticket #{{1}} is still open and waiting for you.

Category: {{2}}
Due by: {{3}}

Please resolve it in Moodle and mark the ticket Resolved in Zoho Desk. The student is told we resolve within 3 working days.
```

**Variables:** `{{1}}` ticket id · `{{2}}` category · `{{3}}` due date

**Sample values for review:** `1054`, `login`, `Wednesday 29 July`

---

## 2. `issue_resolved_check`

Sent to the **student** once the admin marks the ticket Resolved. Nothing closes
without the student's answer to this.

- **Category:** Utility
- **Language:** English
- **Buttons:** Quick Reply × 2 — **Yes** and **No**

**Body:**
```
Hi! Our support team has worked on your ticket #{{1}}.

Is your issue now resolved?
```

**Variables:** `{{1}}` ticket id

**Sample values for review:** `1054`

---

## 3. `ticket_reminder_student`

One gentle reminder when the student has not answered the question above.

- **Category:** Utility
- **Language:** English
- **Buttons:** Quick Reply × 2 — **Yes** and **No**

**Body:**
```
Just checking in on ticket #{{1}}. Is everything working now?

If we don't hear back, we'll close the ticket in a couple of working days. You can reopen it any time by messaging us.
```

**Variables:** `{{1}}` ticket id

**Sample values for review:** `1054`

---

## 4. `ticket_auto_closed`

Sent when a ticket closes automatically — either the service level was reached
without resolution, or the student never confirmed.

- **Category:** Utility
- **Language:** English

**Body:**
```
Your support ticket #{{1}} has been closed.

If your issue is still not resolved, just send us a message and we'll reopen it straight away.
```

**Variables:** `{{1}}` ticket id

**Sample values for review:** `1054`

---

## Notes for whoever submits these

- Template names must match **exactly** — the code references them by name in
  `src/sweeper.py` and `src/handler.py`. A typo means silent send failures.
- Do not add marketing language ("check out our courses"). That gets a Utility
  template reclassified as Marketing, which costs roughly 7× more per message
  and can be rejected.
- Quick Reply buttons on templates 2 and 3 arrive back as a `button` message
  type with the button text — the agent reads a tap the same way it reads the
  student typing "yes".
- If a template is rejected, the rejection reason appears in WhatsApp Manager.
  The usual causes are variables at the very start or end of the body, or
  placeholder sample values that look like real personal data.
- **Billing must be set up on the WABA before any template will send.** Template
  messages are paid, so an unfunded account fails silently at this step.
