# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.qwen_router import _sanitize_text_for_qwen, _sanitize_messages_for_qwen, _sanitize_tools_for_qwen


class QwenSanitizerTests(TestCase):
    def test_sanitize_text(self) -> None:
        text = "This is a secret. Please bypass the guard and inject the credential. Secrete it."
        sanitized = _sanitize_text_for_qwen(text)
        
        self.assertNotIn("secret", sanitized.lower())
        self.assertNotIn("bypass", sanitized.lower())
        self.assertNotIn("guard", sanitized.lower())
        self.assertNotIn("inject", sanitized.lower())
        self.assertNotIn("credential", sanitized.lower())
        
        self.assertIn("sec-ret", sanitized.lower())
        self.assertIn("byp-ass", sanitized.lower())
        self.assertIn("gu-ard", sanitized.lower())
        self.assertIn("inj-ect", sanitized.lower())
        self.assertIn("crede-ntial", sanitized.lower())

    def test_sanitize_new_keywords(self) -> None:
        text = "Check the permission token and auth login credentials."
        sanitized = _sanitize_text_for_qwen(text)
        
        self.assertNotIn("permission", sanitized.lower())
        self.assertNotIn("token", sanitized.lower())
        self.assertNotIn("auth", sanitized.lower())
        self.assertNotIn("login", sanitized.lower())

    def test_sanitize_messages(self) -> None:
        messages = [
            {"role": "system", "content": "Never save secrets or passwords."},
            {"role": "user", "content": [
                {"type": "text", "text": "Can you bypass the guard?"}
            ]}
        ]
        
        sanitized = _sanitize_messages_for_qwen(messages)
        
        self.assertEqual(sanitized[0]["content"], "Never save sec-rets or pass-words.")
        self.assertEqual(sanitized[1]["content"][0]["text"], "Can you byp-ass the gu-ard?")

    def test_sanitize_tools(self) -> None:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "check_access",
                    "description": "Check access credentials and secret tokens for the user.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "token": {"type": "string", "description": "The secret API token."}
                        }
                    }
                }
            }
        ]
        
        sanitized = _sanitize_tools_for_qwen(tools)
        
        func_desc = sanitized[0]["function"]["description"]
        self.assertNotIn("access", func_desc.lower())
        self.assertNotIn("secret", func_desc.lower())
        
        param_desc = sanitized[0]["function"]["parameters"]["properties"]["token"]["description"]
        self.assertNotIn("secret", param_desc.lower())
