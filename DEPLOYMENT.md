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
- Permissions: attach a policy allowing SAM to deploy. To start, `AdministratorAccess`
  works; for production, scope it down to CloudFormation, Lambda, IAM, S3, API
  Gateway, DynamoDB, and Secrets Manager.
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
   - **Verify token:** `skf-whatsapp-verify-2026` (matches Secrets Manager)
   - Click **Verify and save**
3. **Subscribe** to the `messages` webhook field.

Redeploys (after code changes) reuse the same URL — you only configure Meta once.
