# Zoho Desk Ticket Creation Lambda

This project provides an AWS Lambda function, deployable via the AWS Serverless Application Model (SAM), that creates tickets in Zoho Desk. It exposes an API Gateway endpoint that accepts ticket details and uses the Zoho Desk API to create a new ticket.

## Prerequisites

Before you begin, ensure you have the following installed:
*   AWS CLI
*   AWS SAM CLI
*   Python 3.9+
*   An active Zoho Desk account with API access.

## Configuration

All necessary credentials and IDs must be placed in the `config.json` file in the project root.

> **Security Warning**: This file contains sensitive credentials. Do not commit it to public version control. For production environments, it is highly recommended to store these secrets in AWS Secrets Manager and modify the Lambda function to retrieve them at runtime.

### 1. `zoho_client_id` & `zoho_client_secret`

1.  Navigate to the Zoho API Console.
2.  Create a new **Self Client**.
3.  From the **Client Secret** tab, copy the **Client ID** and **Client Secret** and paste them into `config.json`.

### 2. `zoho_refresh_token`

This is a long-lived token used to generate temporary access tokens. It must be generated once manually.

1.  In the API Console for your Self Client, go to the **Generate Code** tab.
2.  Enter the scope: `ZohoDesk.tickets.ALL`.
3.  Set the duration to 10 minutes and click **Create**.
4.  Copy the new **Grant Token**.
5.  Immediately run the following `curl` command in your terminal, replacing the placeholders with your values. This exchanges the temporary grant token for a permanent refresh token.

    ```bash
    curl -X POST "https://accounts.zoho.in/oauth/v2/token" \
      -d "grant_type=authorization_code" \
      -d "client_id=YOUR_CLIENT_ID" \
      -d "client_secret=YOUR_CLIENT_SECRET" \
      -d "code=YOUR_GRANT_TOKEN"
    ```
6.  Copy the `refresh_token` value from the JSON response and paste it into `config.json`.

### 3. `zoho_org_id`

1.  Log in to your Zoho Desk account.
2.  Go to **Setup (⚙️) > Company Details**.
3.  The URL will be `https://desk.zoho.in/support/orgid/YOUR_ORG_ID/setup/companydetails`.
4.  Copy the `YOUR_ORG_ID` number and paste it into `config.json`.

### 4. `zoho_department_id`

1.  In Zoho Desk, go to **Setup (⚙️) > Departments**.
2.  Click on the department where you want to create tickets.
3.  The URL will be `https://desk.zoho.in/support/.../Department/View/YOUR_DEPT_ID`.
4.  Copy the `YOUR_DEPT_ID` number and paste it into `config.json`.

---

## Local Development and Testing

1.  **Create a virtual environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows, use `.venv\Scripts\activate`
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run the local test:**
    The `src/handler.py` file contains a test block. You can modify the `test_event` dictionary with valid data (especially the `contact_id`) to test the functionality.
    ```bash
    python -m src.handler
    ```
    A successful run will print the JSON response from the Zoho API confirming the ticket was created.

## Deployment to AWS

This project is configured for deployment using the AWS SAM CLI.

1.  **Build the SAM application:**
    This command compiles the code and prepares the deployment package.
    ```bash
    sam build
    ```

2.  **Deploy to AWS:**
    This command will package and deploy the application to your AWS account. The `--guided` flag will prompt you for deployment parameters.
    ```bash
    sam deploy --guided
    ```
    After deployment, SAM will output the API Gateway endpoint URL for your function.

## Usage (Post-Deployment)

Once deployed, you can create a Zoho Desk ticket by sending a `POST` request to the API Gateway endpoint provided by the `sam deploy` command.

**Example `curl` command:**
```bash
curl -X POST \
  'YOUR_API_GATEWAY_ENDPOINT_URL/ticket' \
  -H 'Content-Type: application/json' \
  -d '{
        "subject": "Ticket from API",
        "description": "This is a new ticket created via the Lambda function.",
        "contact_id": "146318000000235208"
      }'
```

A successful request will return a `200 OK` status code with the created ticket's details in the response body.
