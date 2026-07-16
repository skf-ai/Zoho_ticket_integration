# WhatsApp → Zoho Desk Support Bot

A WhatsApp helper bot (Meta Cloud API) that answers common student FAQs and, when
it can't, raises a Zoho Desk ticket. When support resolves the ticket, the user is
asked on WhatsApp whether it's fixed — "Yes" closes the ticket.

See **[ROADMAP.md](ROADMAP.md)** for the architecture and the 8-day build plan.

## Project layout

```
src/
  handler.py         Lambda entry: routes Meta verify / inbound / Zoho webhook
  bot.py             Conversation logic (menu -> FAQ -> Solved? -> escalate)
  faq.py             FAQ categories + answers (EDIT THE ANSWERS HERE)
  whatsapp_client.py Outbound Meta Cloud API (text, list, Yes/No, template)
  zoho_client.py     Zoho Desk API (create / close ticket, comments)
  state_store.py     DynamoDB per-user conversation state
  config.py          Secrets Manager (AWS) / env-var (local) config
deployment/
  template.yaml      SAM: Lambda + API Gateway + DynamoDB
tests/               Unit tests (run: python -m pytest)
```

## Config & secrets

- **AWS (production):** credentials live in AWS Secrets Manager under the name in
  the `SECRET_NAME` env var (default `siddhanta/whatsapp-zoho`).
- **Local dev:** set the env vars from [.env.example](.env.example); leave
  `SECRET_NAME` unset to use them.

Required keys: Zoho (`client_id`, `client_secret`, `refresh_token`, `org_id`,
`department_id`) and WhatsApp (`token`, `phone_number_id`, `verify_token`,
`app_secret`). See ROADMAP for how to obtain each.

## Local development

```bash
python -m venv .venv
.venv\Scripts\activate         # Windows
pip install -r requirements.txt
python -m pytest               # run tests
```

## Deploy (Day 6)

Requires the AWS SAM CLI.

```bash
cd deployment
sam build
sam deploy --guided
```

The output `ApiBaseUrl` is where Meta's webhook should point (`/whatsapp`).
