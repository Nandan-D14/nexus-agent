from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus import runtime_config as runtime_config_module


class RuntimeConfigModelSelectionTests(TestCase):
    def test_vertex_sessions_keep_default_task_model_and_gain_fallback_chain(self) -> None:
        user_settings = {
            "byok": {
                "e2bApiKeyEncrypted": "enc-e2b",
                "geminiProvider": "vertex",
                "sharedAccessCodeHash": "stored-hash",
            }
        }

        def fake_decrypt(value: object) -> str:
            if value == "enc-e2b":
                return "e2b-key"
            return ""

        with (
            patch.object(runtime_config_module, "_decrypt_or_empty", side_effect=fake_decrypt),
            patch.object(runtime_config_module, "_shared_access_enabled", return_value=True),
            patch.object(runtime_config_module, "server_e2b_configured", return_value=True),
            patch.object(runtime_config_module, "server_vertex_configured", return_value=True),
            patch.object(runtime_config_module.settings, "google_project_id", "vertex-project"),
            patch.object(runtime_config_module.settings, "gemini_agent_model", "vertex-default-model"),
            patch.object(runtime_config_module.settings, "gemini_api_key_agent_model", "api-key-primary"),
            patch.object(runtime_config_module.settings, "gemini_api_key_agent_fallback_models", "api-fallback-a,api-fallback-b"),
            patch.object(runtime_config_module.settings, "gemini_light_model", "light-model"),
            patch.object(runtime_config_module.settings, "gemini_live_model", "live-model"),
            patch.object(runtime_config_module.settings, "gemini_live_region", "us-central1"),
            patch.object(runtime_config_module.settings, "gemini_vision_model", "vision-model"),
            patch.object(runtime_config_module.settings, "gemini_vision_fallback_models", "vision-model,vision-fallback"),
        ):
            config = runtime_config_module.resolve_session_runtime_config(user_settings)

        self.assertEqual(config.gemini_provider, "vertex")
        self.assertEqual(config.google_project_id, "vertex-project")
        self.assertEqual(config.gemini_agent_model, "vertex-default-model")
        self.assertEqual(
            config.gemini_agent_fallback_models,
            ("api-fallback-a", "api-fallback-b"),
        )
        self.assertEqual(config.gemini_live_model, "live-model")
        self.assertEqual(config.gemini_vision_model, "vision-model")
        self.assertEqual(config.gemini_vision_fallback_models, ("vision-fallback",))

    def test_api_key_sessions_use_provider_specific_task_chain(self) -> None:
        user_settings = {
            "byok": {
                "e2bApiKeyEncrypted": "enc-e2b",
                "geminiApiKeyEncrypted": "enc-gemini",
                "geminiProvider": "apiKey",
            }
        }

        def fake_decrypt(value: object) -> str:
            if value == "enc-e2b":
                return "e2b-key"
            if value == "enc-gemini":
                return "gemini-key"
            return ""

        with (
            patch.object(runtime_config_module, "_decrypt_or_empty", side_effect=fake_decrypt),
            patch.object(runtime_config_module.settings, "gemini_agent_model", "vertex-default-model"),
            patch.object(runtime_config_module.settings, "gemini_api_key_agent_model", "gemini-3.1-pro-preview"),
            patch.object(
                runtime_config_module.settings,
                "gemini_api_key_agent_fallback_models",
                "gemini-3-flash-preview, gemini-3.1-flash-lite-preview, gemini-2.5-pro, gemini-2.5-flash",
            ),
            patch.object(runtime_config_module.settings, "gemini_light_model", "light-model"),
            patch.object(runtime_config_module.settings, "gemini_live_model", "live-model"),
            patch.object(runtime_config_module.settings, "gemini_live_region", "us-central1"),
            patch.object(runtime_config_module.settings, "gemini_vision_model", "vision-model"),
            patch.object(runtime_config_module.settings, "gemini_vision_fallback_models", "vision-model,vision-fallback"),
        ):
            config = runtime_config_module.resolve_session_runtime_config(user_settings)

        self.assertEqual(config.gemini_provider, "apiKey")
        self.assertEqual(config.gemini_api_key, "gemini-key")
        self.assertEqual(config.gemini_agent_model, "gemini-3.1-pro-preview")
        self.assertEqual(
            config.gemini_agent_fallback_models,
            (
                "gemini-3-flash-preview",
                "gemini-3.1-flash-lite-preview",
                "gemini-2.5-pro",
                "gemini-2.5-flash",
            ),
        )
        self.assertEqual(config.gemini_live_model, "live-model")
        self.assertEqual(config.gemini_vision_model, "vision-model")
        self.assertEqual(config.gemini_vision_fallback_models, ("vision-fallback",))

    def test_vertex_selection_falls_back_to_api_key_when_vertex_not_configured(self) -> None:
        user_settings = {
            "byok": {
                "e2bApiKeyEncrypted": "enc-e2b",
                "geminiApiKeyEncrypted": "enc-gemini",
                "geminiProvider": "vertex",
            }
        }

        def fake_decrypt(value: object) -> str:
            if value == "enc-e2b":
                return "e2b-key"
            if value == "enc-gemini":
                return "gemini-key"
            return ""

        with (
            patch.object(runtime_config_module, "_decrypt_or_empty", side_effect=fake_decrypt),
            patch.object(runtime_config_module, "_shared_access_enabled", return_value=False),
            patch.object(runtime_config_module, "server_e2b_configured", return_value=True),
            patch.object(runtime_config_module, "server_vertex_configured", return_value=False),
            patch.object(runtime_config_module.settings, "require_byok", True),
            patch.object(runtime_config_module.settings, "gemini_agent_model", "vertex-default-model"),
            patch.object(runtime_config_module.settings, "gemini_api_key_agent_model", "api-key-primary"),
            patch.object(runtime_config_module.settings, "gemini_api_key_agent_fallback_models", "api-fallback-a,api-fallback-b"),
            patch.object(runtime_config_module.settings, "gemini_light_model", "light-model"),
            patch.object(runtime_config_module.settings, "gemini_live_model", "live-model"),
            patch.object(runtime_config_module.settings, "gemini_live_region", "us-central1"),
            patch.object(runtime_config_module.settings, "gemini_vision_model", "vision-model"),
            patch.object(runtime_config_module.settings, "gemini_vision_fallback_models", "vision-model,vision-fallback"),
        ):
            status = runtime_config_module.get_byok_status(user_settings)
            runtime_config_module.ensure_selected_gemini_provider_available(user_settings)
            config = runtime_config_module.resolve_session_runtime_config(user_settings)

        self.assertTrue(status.configured)
        self.assertEqual(status.missing, ())
        self.assertEqual(config.gemini_provider, "apiKey")
        self.assertEqual(config.gemini_api_key, "gemini-key")
