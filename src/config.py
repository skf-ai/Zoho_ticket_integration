"""Central configuration and secret loading.

In AWS Lambda, secrets are read once from AWS Secrets Manager (secret name in the
SECRET_NAME env var) and cached for the life of the execution environment.

For local development, if Secrets Manager is unavailable or SECRET_NAME is unset,
values fall back to environment variables (see .env.example). This lets you run
and test locally without AWS access.

Required keys (whether in the secret JSON or as env vars):
    zoho_client_id, zoho_client_secret, zoho_refresh_token,
    zoho_org_id, zoho_department_id,
    whatsapp_token, whatsapp_phone_number_id,
    whatsapp_verify_token, whatsapp_app_secret
"""

import json
import os
import functools

# --- Static, non-secret config -------------------------------------------------

AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")

# DynamoDB table holding per-user conversation state.
STATE_TABLE = os.environ.get("STATE_TABLE", "whatsapp_conversation_state")

# Zoho .in data-center endpoints.
ZOHO_TOKEN_URL = "https://accounts.zoho.in/oauth/v2/token"
ZOHO_API_BASE = "https://desk.zoho.in/api/v1"

# Meta WhatsApp Cloud API (Graph API version).
GRAPH_API_VERSION = os.environ.get("GRAPH_API_VERSION", "v21.0")

# Name of the AWS Secrets Manager secret holding the JSON credential blob.
SECRET_NAME = os.environ.get("SECRET_NAME")

_SECRET_KEYS = (
    "zoho_client_id",
    "zoho_client_secret",
    "zoho_refresh_token",
    "zoho_org_id",
    "zoho_department_id",
    "whatsapp_token",
    "whatsapp_phone_number_id",
    "whatsapp_verify_token",
    "whatsapp_app_secret",
)


@functools.lru_cache(maxsize=1)
def _load_secrets():
    """Load the secret blob once, cached for the container's lifetime."""
    if SECRET_NAME:
        try:
            import boto3

            client = boto3.client("secretsmanager", region_name=AWS_REGION)
            resp = client.get_secret_value(SecretId=SECRET_NAME)
            return json.loads(resp["SecretString"])
        except Exception as e:  # noqa: BLE001 - fall back to env vars locally
            print(f"[config] Secrets Manager unavailable ({e}); using env vars.")

    # Local fallback: read each key from the environment (upper-cased).
    return {key: os.environ.get(key.upper(), "") for key in _SECRET_KEYS}


def get(key):
    """Return a single secret value by key (see _SECRET_KEYS)."""
    return _load_secrets().get(key, "")


def require(key):
    """Return a secret value, raising if it is missing/empty."""
    value = get(key)
    if not value:
        raise RuntimeError(
            f"Missing required config '{key}'. Set it in Secrets Manager "
            f"('{SECRET_NAME}') or as the env var '{key.upper()}'."
        )
    return value
