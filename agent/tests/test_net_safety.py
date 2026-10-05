"""Regression tests for the SSRF guard, at-rest secret sealing and OAuth state."""

import httpx
import pytest

from nexus import net_safety
from nexus.net_safety import UnsafeUrlError, assert_public_url, check_url_syntax, guarded_async_client
from nexus.secret_fields import SEALED_PREFIX, open_private, seal_private


@pytest.fixture
def production(monkeypatch):
    monkeypatch.setattr(net_safety, "_relaxed", lambda: False)


@pytest.mark.parametrize(
    "url",
    [
        "https://169.254.169.254/latest/meta-data",
        "https://[fd00::1]/",
        "https://10.0.0.5/",
        "https://127.0.0.1/",
        "https://localhost/",
        "http://example.com/",
        "ftp://example.com/",
    ],
)
def test_syntax_check_blocks_internal_targets_in_production(production, url) -> None:
    with pytest.raises(UnsafeUrlError):
        check_url_syntax(url)


def test_metadata_ip_blocked_even_in_development(monkeypatch) -> None:
    monkeypatch.setattr(net_safety, "_relaxed", lambda: True)
    with pytest.raises(UnsafeUrlError):
        check_url_syntax("http://169.254.169.254/")
    assert check_url_syntax("http://localhost:11434/v1") == "http://localhost:11434/v1"


@pytest.mark.asyncio
async def test_hostname_resolving_to_private_ip_is_blocked(production, monkeypatch) -> None:
    import asyncio

    async def fake_getaddrinfo(host, port, **kwargs):
        return [(None, None, None, "", ("10.1.2.3", port))]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeUrlError):
        await assert_public_url("https://evil.example.com/")


@pytest.mark.asyncio
async def test_redirect_to_metadata_service_is_blocked(production, monkeypatch) -> None:
    import asyncio

    async def fake_getaddrinfo(host, port, **kwargs):
        return [(None, None, None, "", ("93.184.216.34", port))]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fake_getaddrinfo)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://169.254.169.254/token"})

    async with guarded_async_client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        with pytest.raises(UnsafeUrlError):
            await client.get("https://public.example.com/")


@pytest.mark.asyncio
async def test_fetch_limited_caps_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 2048)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(UnsafeUrlError):
            await net_safety.fetch_limited(client, "GET", "https://a.example/", max_bytes=1024)
        ok = await net_safety.fetch_limited(client, "GET", "https://a.example/", max_bytes=4096)
    assert len(ok.content) == 2048


def test_integration_secrets_are_sealed_and_round_trip() -> None:
    plain = {
        "name": "GitHub",
        "token": "ghp_secret",
        "bearerToken": "bearer-secret",
        "extraHeaders": {"x-api-key": "k"},
    }
    sealed = seal_private(plain)
    assert sealed["name"] == "GitHub"
    assert sealed["token"].startswith(SEALED_PREFIX)
    assert sealed["extraHeaders"]["x-api-key"].startswith(SEALED_PREFIX)
    assert "ghp_secret" not in str(sealed)
    # Idempotent: re-sealing an already sealed doc changes nothing.
    assert seal_private(sealed) == sealed
    assert open_private(sealed) == plain
    # Legacy plaintext docs still read correctly.
    assert open_private(plain) == plain


def test_oauth_state_is_opaque_and_verified() -> None:
    from nexus.routers.auth import _decode_oauth_state, _encode_oauth_state

    state = _encode_oauth_state({"uid": "u1", "purpose": "p", "cv": "verifier-123", "cs": "client-secret"})
    assert "verifier-123" not in state
    import base64

    padded = state + "=" * (-len(state) % 4)
    assert b"verifier-123" not in base64.urlsafe_b64decode(padded)
    assert _decode_oauth_state(state)["cv"] == "verifier-123"
    with pytest.raises(ValueError):
        _decode_oauth_state(state[:-4] + "AAAA")
