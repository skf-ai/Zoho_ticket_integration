"""The OpenAI-compatible backend (the active provider) against a fake HTTP server.

We just switched the default model to OpenAI GPT-5 mini, and that request path had
never actually executed. These tests exercise it with a mocked endpoint -- no key,
no cost, no network -- so a wrong field name or a parsing bug is caught here rather
than during the first paid live call.

The single most important assertion: the payload must send
`max_completion_tokens`, NOT `max_tokens`. GPT-5 rejects the latter, so getting
this wrong would fail every real request.
"""

import os
import unittest

import requests_mock

from src import llm

OPENAI_URL = "https://api.openai.com/v1/chat/completions"

# A tool in our internal (Anthropic-shaped) format; the backend must translate it
# to OpenAI's {type: function, function: {name, description, parameters}} shape.
TOOL = {
    "name": "raise_ticket",
    "description": "Raise a support ticket.",
    "input_schema": {
        "type": "object",
        "properties": {"subject": {"type": "string"}},
        "required": ["subject"],
    },
}


class TestOpenAIBackend(unittest.TestCase):
    def setUp(self):
        # The backend resolves the key from config OR the LLM_API_KEY env var.
        os.environ["LLM_API_KEY"] = "test-key-not-real"

    def test_payload_uses_max_completion_tokens_not_max_tokens(self):
        captured = {}

        def handler(request, context):
            captured["json"] = request.json()
            captured["auth"] = request.headers.get("Authorization")
            context.status_code = 200
            return {"choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 2}}

        with requests_mock.Mocker() as m:
            m.post(OPENAI_URL, json=handler)
            llm._call_openai_compatible([{"role": "user", "content": "hi"}], [TOOL])

        body = captured["json"]
        self.assertIn("max_completion_tokens", body,
                      "GPT-5 requires max_completion_tokens")
        self.assertNotIn("max_tokens", body,
                         "max_tokens is rejected by GPT-5 -- must not be sent")
        self.assertEqual(captured["auth"], "Bearer test-key-not-real")
        # The reasoning cap keeps this reasoning model fast enough for the
        # synchronous webhook; losing it reintroduces the ReadTimeout.
        self.assertEqual(body.get("reasoning_effort"), "low")

    def test_tools_are_translated_to_openai_function_shape(self):
        captured = {}

        def handler(request, context):
            captured["json"] = request.json()
            context.status_code = 200
            return {"choices": [{"message": {"content": "ok"}}], "usage": {}}

        with requests_mock.Mocker() as m:
            m.post(OPENAI_URL, json=handler)
            llm._call_openai_compatible([{"role": "user", "content": "hi"}], [TOOL])

        tool = captured["json"]["tools"][0]
        self.assertEqual(tool["type"], "function")
        self.assertEqual(tool["function"]["name"], "raise_ticket")
        # input_schema on our side becomes parameters on OpenAI's side.
        self.assertEqual(tool["function"]["parameters"]["required"], ["subject"])

    def test_tool_call_response_is_parsed(self):
        with requests_mock.Mocker() as m:
            m.post(OPENAI_URL, json={
                "choices": [{"message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "raise_ticket",
                            "arguments": '{"subject": "cannot log in"}',
                        },
                    }],
                }}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 8},
            })
            result = llm._call_openai_compatible(
                [{"role": "user", "content": "help"}], [TOOL])

        self.assertEqual(result["stop_reason"], "tool_use")
        self.assertEqual(len(result["tool_calls"]), 1)
        call = result["tool_calls"][0]
        self.assertEqual(call["name"], "raise_ticket")
        self.assertEqual(call["id"], "call_1")
        # arguments arrive as a JSON string and must be parsed to a dict.
        self.assertEqual(call["input"], {"subject": "cannot log in"})

    def test_plain_text_response_is_parsed(self):
        with requests_mock.Mocker() as m:
            m.post(OPENAI_URL, json={
                "choices": [{"message": {"content": "Try resetting your password."}}],
                "usage": {"prompt_tokens": 90, "completion_tokens": 6},
            })
            result = llm._call_openai_compatible(
                [{"role": "user", "content": "help"}], [TOOL])

        self.assertEqual(result["text"], "Try resetting your password.")
        self.assertEqual(result["stop_reason"], "end_turn")
        self.assertEqual(result["tool_calls"], [])

    def test_malformed_tool_arguments_do_not_crash(self):
        # A weaker model can emit invalid JSON in the arguments. The backend must
        # degrade to an empty input, not throw and kill the whole webhook turn.
        with requests_mock.Mocker() as m:
            m.post(OPENAI_URL, json={
                "choices": [{"message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call_2",
                        "type": "function",
                        "function": {"name": "raise_ticket",
                                     "arguments": "{not valid json"},
                    }],
                }}],
                "usage": {},
            })
            result = llm._call_openai_compatible(
                [{"role": "user", "content": "help"}], [TOOL])

        self.assertEqual(result["tool_calls"][0]["input"], {})

    def test_cached_tokens_are_read_from_usage(self):
        # Confirms the field we rely on to SEE that OpenAI caching is working.
        with requests_mock.Mocker() as m:
            m.post(OPENAI_URL, json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 3000, "completion_tokens": 5,
                          "prompt_tokens_details": {"cached_tokens": 2600}},
            })
            result = llm._call_openai_compatible(
                [{"role": "user", "content": "hi"}], [TOOL])

        self.assertEqual(result["usage"]["cache_read"], 2600)

    def test_http_error_raises_llmerror(self):
        with requests_mock.Mocker() as m:
            m.post(OPENAI_URL, status_code=401, text="bad key")
            with self.assertRaises(llm.LLMError):
                llm._call_openai_compatible(
                    [{"role": "user", "content": "hi"}], [TOOL])


if __name__ == "__main__":
    unittest.main()
