# WhatsApp LMS Support and Accountability Bot

A low-cost support system for an educational non-profit. Students message a Meta
WhatsApp number; a grounded Claude assistant answers from `knowledge/*.md` or
creates a Zoho Desk ticket. A deterministic hourly worker reminds the LMS admin,
asks the student to verify completed work, and applies the agreed three-working-
day inactivity rules.

## Architecture

- API Gateway + Lambda: authenticated Meta and Zoho webhooks
- Claude Haiku: grounded conversation and tool selection
- Zoho Desk: contacts, tickets, internal audit comments, closure
- DynamoDB: conversation memory, lifecycle state, deduplication, due-action GSIs
- EventBridge + Lambda: hourly SLA sweeper
- CloudWatch + optional SNS email: errors and missing sweeper runs

AI never controls the clock or chooses arbitrary ticket IDs. SLA decisions are
plain Python, and tools can act only on the ticket mapped to the sender's number.

## Local verification

Use Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest -q
python simulate.py --mock
```

`--mock` uses fake AI, Zoho, WhatsApp, DynamoDB and clock. To evaluate real AI
quality while keeping every external system fake:

```powershell
$env:ANTHROPIC_API_KEY="temporary-local-key"
python simulate.py
```

The simulator never creates tickets in the real Zoho account.

## Production configuration

AWS Secrets Manager secret `siddhanta/whatsapp-zoho` must contain:

```json
{
  "zoho_client_id": "...",
  "zoho_client_secret": "...",
  "zoho_refresh_token": "...",
  "zoho_org_id": "...",
  "zoho_department_id": "...",
  "whatsapp_token": "...",
  "whatsapp_phone_number_id": "...",
  "whatsapp_verify_token": "...",
  "whatsapp_app_secret": "...",
  "zoho_webhook_secret": "generate-a-long-random-value",
  "llm_api_key": "...",
  "lms_admin_wa_id": "919999999999"
}
```

Never commit this JSON. Replace `<LMS_URL>` and `<SUPPORT_EMAIL>` in every
knowledge file before deployment. `/health` returns HTTP 503 until required
configuration and knowledge content are ready.

See [DEPLOYMENT.md](DEPLOYMENT.md) for deployment and [RUNBOOK.md](RUNBOOK.md)
for live testing, incidents and rollback.
