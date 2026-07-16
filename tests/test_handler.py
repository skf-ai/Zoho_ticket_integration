"""Day 1 smoke tests: routing, Meta verification, and payload parsing.

These need no secrets or network — deeper flow tests come on Days 3-5.
"""

import os
import unittest

# Ensure config uses env-var fallback (no Secrets Manager) during tests.
os.environ.pop("SECRET_NAME", None)
os.environ["WHATSAPP_VERIFY_TOKEN"] = "test-verify-token"

from src import handler  # noqa: E402


class TestVerification(unittest.TestCase):
    def test_challenge_returned_with_valid_token(self):
        event = {
            "requestContext": {"http": {"method": "GET", "path": "/whatsapp"}},
            "queryStringParameters": {
                "hub.verify_token": "test-verify-token",
                "hub.challenge": "12345",
            },
        }
        resp = handler.lambda_handler(event, {})
        self.assertEqual(resp["statusCode"], 200)
        self.assertEqual(resp["body"], "12345")

    def test_bad_token_rejected(self):
        event = {
            "requestContext": {"http": {"method": "GET", "path": "/whatsapp"}},
            "queryStringParameters": {
                "hub.verify_token": "wrong",
                "hub.challenge": "12345",
            },
        }
        resp = handler.lambda_handler(event, {})
        self.assertEqual(resp["statusCode"], 403)


class TestPayloadParsing(unittest.TestCase):
    def test_extract_text_message(self):
        body = {
            "entry": [{
                "changes": [{
                    "value": {
                        "contacts": [{"profile": {"name": "Akash"}}],
                        "messages": [{
                            "from": "919999999999",
                            "type": "text",
                            "text": {"body": "Hi"},
                        }],
                    }
                }]
            }]
        }
        results = list(handler._extract_messages(body))
        self.assertEqual(len(results), 1)
        wa_id, username, msg = results[0]
        self.assertEqual(wa_id, "919999999999")
        self.assertEqual(username, "Akash")
        self.assertEqual(msg["text"], "Hi")

    def test_extract_list_reply(self):
        msg = {
            "type": "interactive",
            "interactive": {
                "type": "list_reply",
                "list_reply": {"id": "login_issue", "title": "Login Issue"},
            },
        }
        norm = handler._normalize_message(msg)
        self.assertEqual(norm["id"], "login_issue")
        self.assertEqual(norm["type"], "button")


if __name__ == "__main__":
    unittest.main()
