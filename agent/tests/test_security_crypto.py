# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

import base64
import pytest
from cryptography.fernet import Fernet
from nexus.crypto import encrypt_secret, decrypt_secret, get_byok_fernet
from nexus.config import settings

def test_crypto_roundtrip():
    """Verify that a secret can be encrypted and then decrypted back to its original value."""
    # Ensure a valid key is set for testing
    settings.byok_encryption_key = Fernet.generate_key().decode()
    get_byok_fernet.cache_clear()
    
    original = "my-super-secret-key-123"
    encrypted = encrypt_secret(original)
    assert encrypted != original
    
    decrypted = decrypt_secret(encrypted)
    assert decrypted == original

def test_crypto_production_hard_fail(monkeypatch):
    """Verify that get_byok_fernet hard-fails if key is missing in production."""
    # Mock production environment
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "byok_encryption_key", "")
    monkeypatch.setattr(settings, "frontend_url", "https://app.cocoming.com")
    get_byok_fernet.cache_clear()
    
    with pytest.raises(RuntimeError, match="BYOK_ENCRYPTION_KEY is not configured"):
        get_byok_fernet()

def test_crypto_local_dev_fallback(monkeypatch):
    """Verify that a deterministic key is used in local development if no key is set."""
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "byok_encryption_key", "")
    monkeypatch.setattr(settings, "frontend_url", "http://localhost:3000")
    get_byok_fernet.cache_clear()
    
    # This should not raise
    f = get_byok_fernet()
    assert isinstance(f, Fernet)
