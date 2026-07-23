# Deployment (CI/CD via GitHub Actions)

Deployment is automated. You never run deploy commands by hand — you click
**"Run workflow"** in GitHub and Actions builds, tests, and deploys to AWS.

There are two pipelines:
- **CI** (`.github/workflows/ci.yml`) — runs tests on every push/PR. Automatic.
- **Deploy** (`.github/workflows/deploy.yml`) — builds + deploys to AWS. Manual trigger.

---

## One-time setup (do this once)

GitHub needs permission to deploy into your AWS account. We use **OIDC** (GitHub
assumes a short-lived AWS role — no permanent AWS keys stored in GitHub). This is
the secure, production-standard approach.

### Step 1 — Create the GitHub OIDC identity provider in AWS
AWS Console → **IAM → Identity providers → Add provider**:
- Provider type: **OpenID Connect**
- Provider URL: `https://token.actions.githubusercontent.com`
- Audience: `sts.amazonaws.com`
- Click **Add provider**

### Step 2 — Create the deploy role
AWS Console → **IAM → Roles → Create role**:
- Trusted entity: **Web identity**
- Identity provider: the one from Step 1
- Audience: `sts.amazonaws.com`
- Add a condition so only THIS repo can assume it — edit the trust policy to:
  ```json
  "StringLike": {
    "token.actions.githubusercontent.com:sub": "repo:skf-ai/Zoho_ticket_integration:*"
  }
  ```
- Permissions: use a deployment policy scoped to this stack's CloudFormation,
  Lambda, IAM, S3, API Gateway, DynamoDB, EventBridge, SQS, SNS, CloudWatch and
  Logs resources. Do not leave `AdministratorAccess` on the GitHub role.
- Name it e.g. `github-deploy-whatsapp-zoho`
- **Copy the Role ARN** (looks like `arn:aws:iam::417311687123:role/github-deploy-whatsapp-zoho`)

### Step 3 — Add the Role ARN as a GitHub secret
GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**:
- Name: `AWS_DEPLOY_ROLE_ARN`
- Value: the Role ARN from Step 2

---

## Deploying

1. GitHub repo → **Actions** tab
2. Select the **Deploy** workflow (left side)
3. Click **Run workflow** → **Run workflow**
4. Watch it build, test, and deploy. When it finishes, open the workflow log and
   find the **`ApiBaseUrl`** output — that's your bot's public URL.

---

## After the first deploy — point Meta's webhook at it

1. Take the `ApiBaseUrl` and append `/whatsapp` → e.g.
   `https://abc123.execute-api.ap-south-1.amazonaws.com/Prod/whatsapp`
2. Meta app → WhatsApp → Configuration → **Webhook**:
   - **Callback URL:** the URL above
   - **Verify token:** the `whatsapp_verify_token` value in Secrets Manager
   - Click **Verify and save**
3. **Subscribe** to the `messages` webhook field.

## Configure the Zoho resolution workflow

Create a Zoho Desk workflow that runs when a ticket changes to `Resolved` and
POSTs JSON containing `ticketId` to the stack's `ZohoWebhookUrl` output. Add the
HTTP header `X-Webhook-Secret` with the same value stored as
`zoho_webhook_secret`. Requests without this value receive HTTP 401.

## Alerts

Set the optional CloudFormation `AlertEmail` parameter during deployment to
create webhook-error, sweeper-error and sweeper-silent alarms. AWS sends an SNS
confirmation message; monitoring does not activate until the recipient confirms.

## Required post-deploy checks

Open `<ApiBaseUrl>/health`. Deployment is ready only when it returns HTTP 200 and
`"ready": true`. Then follow the controlled live test in `RUNBOOK.md`.

The hardened release creates `whatsapp_conversation_state_v2` because DynamoDB
permits only one new GSI per update and this version requires two. CloudFormation
retains the legacy table rather than deleting it. Resolve or manually account for
any active legacy ticket before directing Meta to the new deployment; delete the
old table only after the agreed retention period and an explicit backup decision.

Redeploys (after code changes) reuse the same URL — you only configure Meta once.
