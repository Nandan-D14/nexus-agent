# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

import sys
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus import runtime_config as runtime_config_module
from nexus.llm_providers import e2b_setup_public, public_provider_catalog
from nexus.model_select import create_model, model_candidates, model_name_for_role
from nexus.runtime_config import SessionRuntimeConfig
from nexus.user_llm_router import UserLlmClient
from nexus.vision_provider import create_vision_provider


def _decrypt_map(mapping: dict[str, str]):
    def fake_decrypt(value: object) -> str:
        if not isinstance(value, str):
            return ""
        return mapping.get(value, "")

    return fake_decrypt


def _user_runtime(**overrides: object) -> SessionRuntimeConfig:
    payload: dict[str, object] = {
        "e2b_api_key": "e2b-user",
        "gemini_provider": "apiKey",
        "gemini_api_key": "",
        "google_project_id": "",
        "google_cloud_region": "global",
        "gemini_agent_model": "x",
        "gemini_agent_fallback_models": (),
        "gemini_light_model": "x",
        "gemini_live_model": "x",
        "gemini_live_region": "us-central1",
        "gemini_vision_model": "x",
        "gemini_vision_fallback_models": (),
        "use_kilo": False,
        "kilo_api_key": "",
        "kilo_model_id": "",
        "kilo_gateway_url": "",
        "llm_provider": "openai",
        "llm_api_key": "sk-user",
        "llm_api_base": "https://api.openai.com/v1",
        "llm_model": "gpt-4.1",
        "llm_vision_model": "gpt-4.1",
    }
    payload.update(overrides)
    return SessionRuntimeConfig(**payload)  # type: ignore[arg-type]


class LlmProviderCatalogTests(TestCase):
    def test_catalog_includes_presets_custom_and_e2b_links(self) -> None:
        ids = [item["id"] for item in public_provider_catalog()]
        self.assertIn("openai", ids)
        self.assertIn("orcarouter", ids)
        self.assertIn("custom", ids)
        orca = next(item for item in public_provider_catalog() if item["id"] == "orcarouter")
        self.assertEqual(orca["apiBase"], "https://api.orcarouter.ai/v1")
        self.assertEqual(orca["defaultModel"], "orcarouter/auto")
        self.assertTrue(orca["logoUrl"].endswith("orcarouter.svg"))
        openai = next(item for item in public_provider_catalog() if item["id"] == "openai")
        self.assertTrue(openai["logoUrl"].endswith("openai.svg"))
        custom = next(item for item in public_provider_catalog() if item["id"] == "custom")
        self.assertTrue(custom["custom"])
        e2b = e2b_setup_public()
        self.assertIn("e2b.dev/dashboard", e2b["keyUrl"])
        self.assertTrue(e2b["steps"])
        self.assertTrue(str(e2b["logoUrl"]).endswith("e2b.svg"))

    def test_orac_alias_normalizes_to_orcarouter(self) -> None:
        from nexus.llm_providers import get_provider, normalize_llm_provider

        self.assertEqual(normalize_llm_provider("orac"), "orcarouter")
        self.assertEqual(normalize_llm_provider("Orca Router"), "orcarouter")
        spec = get_provider("orac")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.id, "orcarouter")


class ByokLlmGateTests(TestCase):
    def setUp(self) -> None:
        vertex = patch.object(runtime_config_module, "server_vertex_configured", return_value=False)
        vertex.start()
        self.addCleanup(vertex.stop)

    def test_missing_e2b_even_when_server_key_exists(self) -> None:
        user_settings = {
            "byok": {
                "llmProvider": "openai",
                "llmApiKeyEncrypted": "enc-llm",
                "llmModel": "gpt-4.1",
            }
        }
        with (
            patch.object(runtime_config_module, "_decrypt_or_empty", side_effect=_decrypt_map({"enc-llm": "sk-llm"})),
            patch.object(runtime_config_module, "server_e2b_configured", return_value=True),
            patch.object(runtime_config_module.settings, "e2b_api_key", "server-e2b"),
        ):
            status = runtime_config_module.get_byok_status(user_settings)
        self.assertIn("e2b", status.missing)
        self.assertNotIn("llm", status.missing)

    def test_missing_llm_when_only_e2b_is_set(self) -> None:
        user_settings = {"byok": {"e2bApiKeyEncrypted": "enc-e2b"}}
        with patch.object(
            runtime_config_module,
            "_decrypt_or_empty",
            side_effect=_decrypt_map({"enc-e2b": "e2b-key"}),
        ):
            status = runtime_config_module.get_byok_status(user_settings)
        self.assertIn("llm", status.missing)
        self.assertNotIn("e2b", status.missing)

    def test_custom_provider_requires_base_and_model(self) -> None:
        user_settings = {
            "byok": {
                "e2bApiKeyEncrypted": "enc-e2b",
                "llmProvider": "custom",
                "llmApiKeyEncrypted": "enc-llm",
            }
        }
        with patch.object(
            runtime_config_module,
            "_decrypt_or_empty",
            side_effect=_decrypt_map({"enc-e2b": "e2b-key", "enc-llm": "sk-llm"}),
        ):
            status = runtime_config_module.get_byok_status(user_settings)
        self.assertIn("llm", status.missing)

        user_settings["byok"]["llmModel"] = "my-model"
        user_settings["byok"]["llmApiBase"] = "https://router.example.com/v1"
        with patch.object(
            runtime_config_module,
            "_decrypt_or_empty",
            side_effect=_decrypt_map({"enc-e2b": "e2b-key", "enc-llm": "sk-llm"}),
        ):
            status = runtime_config_module.get_byok_status(user_settings)
        self.assertEqual(status.missing, ())
        self.assertTrue(status.configured)

    def test_gemini_key_migrates_to_llm_provider(self) -> None:
        user_settings = {
            "byok": {
                "e2bApiKeyEncrypted": "enc-e2b",
                "geminiApiKeyEncrypted": "enc-gemini",
                "geminiProvider": "apiKey",
            }
        }
        with patch.object(
            runtime_config_module,
            "_decrypt_or_empty",
            side_effect=_decrypt_map({"enc-e2b": "e2b-key", "enc-gemini": "gemini-key"}),
        ):
            status = runtime_config_module.get_byok_status(user_settings)
            config = runtime_config_module.resolve_session_runtime_config(user_settings)
        self.assertEqual(status.llm_provider, "gemini")
        self.assertTrue(status.llm_key_set)
        self.assertEqual(status.missing, ())
        self.assertEqual(config.llm_api_key, "gemini-key")
        self.assertIn("generativelanguage.googleapis.com", config.llm_api_base)
        self.assertTrue(config.user_llm_configured)

    def test_qwen_mode_does_not_skip_byok(self) -> None:
        with (
            patch.object(runtime_config_module.settings, "model_provider", "qwen"),
            patch.object(runtime_config_module.settings, "require_byok", True),
        ):
            public = runtime_config_module.build_public_user_settings({})
        self.assertTrue(public["requireByok"])
        self.assertIn("e2b", public["byok"]["missing"])
        self.assertIn("llm", public["byok"]["missing"])
        self.assertTrue(public["llmProviders"])
        self.assertIn("e2b.dev", public["e2bSetup"]["keyUrl"])

    def test_unknown_provider_and_invalid_custom_base_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            runtime_config_module.build_byok_storage_update({}, {"llmProvider": "not-a-provider"})
        with self.assertRaises(ValueError):
            runtime_config_module.build_byok_storage_update(
                {},
                {"llmProvider": "custom", "llmApiBase": "not-a-url"},
            )

    def test_gemini_api_key_update_copies_into_llm_fields(self) -> None:
        with patch.object(runtime_config_module, "_encrypt_or_clear", side_effect=lambda value: f"enc-{value}"):
            payload = runtime_config_module.build_byok_storage_update(
                {},
                {"geminiApiKey": "gemini-secret"},
            )
        self.assertEqual(payload["llmProvider"], "gemini")
        self.assertEqual(payload["llmApiKeyEncrypted"], "enc-gemini-secret")
        self.assertEqual(payload["geminiApiKeyEncrypted"], "enc-gemini-secret")


class UserLlmRuntimeTests(TestCase):
    def test_create_model_uses_user_credentials_not_server_qwen(self) -> None:
        runtime = _user_runtime()
        with patch(
            "nexus.bynara_router.create_bynara_model",
            side_effect=AssertionError("server Bynara must not be used"),
        ):
            model = create_model("planner", runtime)
        self.assertIsInstance(model.llm_client, UserLlmClient)
        self.assertEqual(model.llm_client.api_key, "sk-user")
        self.assertEqual(model.llm_client.api_base, "https://api.openai.com/v1")
        self.assertEqual(model_name_for_role("planner", runtime), "gpt-4.1")
        self.assertEqual(model_candidates("planner", runtime), ("gpt-4.1",))

    def test_visual_role_uses_vision_model(self) -> None:
        runtime = _user_runtime(llm_vision_model="gpt-4o")
        self.assertEqual(model_name_for_role("worker_visual", runtime), "gpt-4o")
        self.assertEqual(model_name_for_role("worker", runtime), "gpt-4.1")

    def test_vision_provider_uses_user_credentials(self) -> None:
        runtime = _user_runtime(llm_vision_model="gpt-4o")
        with patch(
            "nexus.vision_provider.settings.bynara_api_key",
            "server-bynara-key",
        ):
            provider = create_vision_provider(runtime_config=runtime)
        self.assertEqual(provider.models[0], "gpt-4o")
        self.assertEqual(provider._client.api_key, "sk-user")
        self.assertIn("api.openai.com", str(provider._client.base_url))

    def test_user_llm_clients_are_not_shared(self) -> None:
        first = create_model("planner", _user_runtime(llm_api_key="sk-one"))
        second = create_model("planner", _user_runtime(llm_api_key="sk-two"))
        self.assertIsNot(first.llm_client, second.llm_client)
        self.assertEqual(first.llm_client.api_key, "sk-one")
        self.assertEqual(second.llm_client.api_key, "sk-two")


class ListUserLlmModelsTests(IsolatedAsyncioTestCase):
    async def test_lists_and_sorts_model_ids(self) -> None:
        class FakeResponse:
            status_code = 200

            def json(self) -> dict[str, object]:
                return {
                    "data": [
                        {"id": "gpt-4o"},
                        {"id": "orcarouter/auto"},
                        {"id": "gpt-4o"},
                    ]
                }

            def raise_for_status(self) -> None:
                return None

        class FakeClient:
            def __init__(self, *args: object, **kwargs: object) -> None:
                return None

            async def __aenter__(self) -> "FakeClient":
                return self

            async def __aexit__(self, *args: object) -> bool:
                return False

            async def get(self, url: str, headers: object = None) -> FakeResponse:
                return FakeResponse()

        with patch("httpx.AsyncClient", FakeClient):
            from nexus.user_llm_router import list_user_llm_models

            ids = await list_user_llm_models(
                api_key="sk-orca-test",
                api_base="https://api.orcarouter.ai/v1/",
            )
        self.assertEqual(ids[0], "orcarouter/auto")
        self.assertEqual(ids, ["orcarouter/auto", "gpt-4o"])

    async def test_requires_key_and_base(self) -> None:
        from nexus.user_llm_router import list_user_llm_models

        with self.assertRaises(ValueError):
            await list_user_llm_models(api_key="", api_base="https://api.orcarouter.ai/v1")
        with self.assertRaises(ValueError):
            await list_user_llm_models(api_key="sk-test", api_base="")

    async def test_strips_google_models_prefix(self) -> None:
        class FakeResponse:
            status_code = 200

            def json(self) -> dict[str, object]:
                return {"models": [{"name": "models/gemini-2.5-flash"}, {"id": "gemini-2.5-pro"}]}

            def raise_for_status(self) -> None:
                return None

        class FakeClient:
            def __init__(self, *args: object, **kwargs: object) -> None:
                return None

            async def __aenter__(self) -> "FakeClient":
                return self

            async def __aexit__(self, *args: object) -> bool:
                return False

            async def get(self, url: str, headers: object = None) -> FakeResponse:
                return FakeResponse()

        with patch("httpx.AsyncClient", FakeClient):
            from nexus.user_llm_router import list_user_llm_models

            ids = await list_user_llm_models(
                api_key="sk-test",
                api_base="https://generativelanguage.googleapis.com/v1beta/openai",
            )
        self.assertEqual(ids, ["gemini-2.5-flash", "gemini-2.5-pro"])


class FlattenByokFirestoreTests(TestCase):
    def test_nested_byok_becomes_dotted_fields(self) -> None:
        from firebase_admin import firestore

        from nexus._firestore_base import FirestoreRepoBase

        out = FirestoreRepoBase._flatten_byok_updates(
            {
                "byok": {
                    "llmApiKeyEncrypted": "enc-llm",
                    "llmProvider": "openrouter",
                    "geminiApiKeyEncrypted": None,
                },
                "updatedAt": "now",
            }
        )
        self.assertEqual(out["byok.llmApiKeyEncrypted"], "enc-llm")
        self.assertEqual(out["byok.llmProvider"], "openrouter")
        self.assertIs(out["byok.geminiApiKeyEncrypted"], firestore.DELETE_FIELD)
        self.assertEqual(out["updatedAt"], "now")
        self.assertNotIn("byok", out)


