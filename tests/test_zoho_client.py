"""Zoho client tests with mocked HTTP (no real Zoho calls, no real secrets)."""

import os
import unittest
from unittest.mock import patch, MagicMock

# Provide fake creds via env so config.require() succeeds.
os.environ.pop("SECRET_NAME", None)
for k in ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN",
          "ZOHO_ORG_ID", "ZOHO_DEPARTMENT_ID"):
    os.environ[k] = "test"

from src import zoho_client  # noqa: E402


class TestZohoClient(unittest.TestCase):
    def setUp(self):
        # Each test owns its mocked token exchange; do not share the production
        # warm-container token cache across test cases.
        zoho_client._access_token = None
        zoho_client._access_token_expires_at = 0.0

    @patch("src.zoho_client.requests.post")
    def test_create_ticket(self, mock_post):
        # First call = token refresh, second = ticket creation.
        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"access_token": "abc"}
        ticket_resp = MagicMock(status_code=200)
        ticket_resp.json.return_value = {"id": "ticket123"}
        mock_post.side_effect = [token_resp, ticket_resp]

        ticket = zoho_client.create_ticket("Subj", "Desc", "c1", category="Login Issue")

        self.assertIsNotNone(ticket)
        self.assertEqual(ticket["id"], "ticket123")

    @patch("src.zoho_client.requests.patch")
    @patch("src.zoho_client.requests.post")
    def test_close_ticket(self, mock_post, mock_patch):
        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"access_token": "abc"}
        mock_post.return_value = token_resp
        mock_patch.return_value = MagicMock(status_code=200)

        self.assertTrue(zoho_client.close_ticket("ticket123"))


if __name__ == "__main__":
    unittest.main()
