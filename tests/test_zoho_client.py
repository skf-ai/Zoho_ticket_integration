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

    def test_format_description_spaces_out_lines(self):
        out = zoho_client._format_description(
            "Problem: cannot log in\nError message: none shown\n\n---\nStudent: Rahul (919999999999)"
        )
        # Each line is its own margined block -- no bare "<br>" anywhere, and a
        # blank source line still renders as a visible paragraph gap.
        self.assertNotIn("<br>", out)
        self.assertIn('<div style="margin:0 0 10px 0;">Problem: cannot log in</div>', out)
        self.assertIn('<div style="margin:0 0 10px 0;"><b>Student:</b> Rahul (919999999999)</div>', out)
        self.assertIn('<div style="margin:0 0 10px 0;">&nbsp;</div>', out)

    def test_format_description_bolds_and_links(self):
        out = zoho_client._format_description("Registered email: a@b.com")
        self.assertIn("<b>Registered email:</b>", out)
        self.assertIn('<a href="mailto:a@b.com">a@b.com</a>', out)


if __name__ == "__main__":
    unittest.main()
