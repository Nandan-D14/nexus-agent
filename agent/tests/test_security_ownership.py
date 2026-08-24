# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

import pytest
from nexus.session import SessionManager
from nexus.runtime_config import SessionRuntimeConfig

def create_mock_runtime_config():
    return SessionRuntimeConfig(
        e2b_api_key="fake-key",
        gemini_provider="apiKey",
        gemini_api_key="fake-gemini-key",
        google_project_id="fake-project",
        google_cloud_region="us-central1",
        gemini_agent_model="gemini-3.1-pro-preview",
        gemini_agent_fallback_models=("gemini-3-flash-preview",),
        gemini_light_model="gemini-3.1-flash-lite-preview",
        gemini_live_model="gemini-live-2.5-flash-native-audio",
        gemini_live_region="us-central1",
        gemini_vision_model="gemini-3-flash-preview",
        gemini_vision_fallback_models=("gemini-3.1-flash-lite-preview",),
        use_kilo=False,
        kilo_api_key="fake-kilo-key",
        kilo_model_id="minimax",
        kilo_gateway_url="https://api.kilo.ai"
    )

@pytest.mark.asyncio
async def test_session_ownership_isolation():
    """Verify that user A cannot access or modify user B's session."""
    manager = SessionManager()
    
    # Setup: User B creates a session
    user_b_id = "user-beta"
    config = create_mock_runtime_config()
    session_b = await manager.create_session(owner_id=user_b_id, runtime_config=config)
    
    # Test: User A attempts to destroy User B's session
    user_a_id = "user-alpha"
    with pytest.raises(PermissionError, match="Not the session owner"):
        await manager.destroy_if_owned(session_id=session_b.id, owner_id=user_a_id)
        
    # Test: User A attempts to continue User B's session
    with pytest.raises(PermissionError, match="Not the session owner"):
        await manager.continue_session(
            session_id=session_b.id,
            owner_id=user_a_id,
            runtime_config=config,
            created_at=session_b.created_at,
            resume_mode="fresh",
            seed_context="",
            initial_title="Stolen Session"
        )
