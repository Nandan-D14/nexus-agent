# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Outbound-request safety: block SSRF to internal / metadata addresses.

Every server-side fetch of a user-supplied URL (MCP servers, custom LLM bases,
skill imports) must go through :func:`assert_public_url` or a client built by
:func:`guarded_async_client`. The client's request hook runs for every hop of a
redirect chain, so a public URL cannot bounce the server to ``169.254.169.254``.

Known limit: the hook resolves DNS before httpx connects, so a rebinding DNS
server can still race the check. Pinning the resolved IP needs a custom
transport and is out of scope here.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

from nexus.config import settings

DEFAULT_MAX_REDIRECTS = 5


class UnsafeUrlError(ValueError):
    """Raised when a URL targets a non-public network address."""


def _relaxed() -> bool:
    # Local development legitimately talks to localhost / LAN services
    # (Ollama, a dev MCP server). Production never does.
    return not settings.is_production


def _ip_allowed(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, *, relaxed: bool) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    # Link-local covers the cloud metadata service; never allowed.
    if ip.is_link_local or ip.is_multicast or ip.is_unspecified:
        return False
    if ip.is_global:
        return True
    return relaxed and (ip.is_loopback or ip.is_private)


def _check_parsed(url: str, *, allow_http: bool) -> tuple[str, int]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrlError("URL must be an absolute http(s) URL.")
    if parsed.scheme == "http" and not (allow_http or _relaxed()):
        raise UnsafeUrlError("URL must use HTTPS.")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeUrlError("URL has an invalid port.") from exc
    return parsed.hostname.lower(), port


def _check_addresses(host: str, infos: list[Any], *, relaxed: bool) -> None:
    if not infos:
        raise UnsafeUrlError(f"Could not resolve host {host!r}.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%", 1)[0])
        if not _ip_allowed(ip, relaxed=relaxed):
            raise UnsafeUrlError(f"Host {host!r} resolves to a non-public address.")


def _literal_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None


def check_url_syntax(url: str, *, allow_http: bool = False) -> str:
    """Cheap, DNS-free validation for save-time checks. Returns the cleaned URL."""
    cleaned = (url or "").strip()
    host, _ = _check_parsed(cleaned, allow_http=allow_http)
    relaxed = _relaxed()
    if host == "localhost" and not relaxed:
        raise UnsafeUrlError("URL must not target localhost.")
    ip = _literal_ip(host)
    if ip is not None and not _ip_allowed(ip, relaxed=relaxed):
        raise UnsafeUrlError("URL must not target a non-public address.")
    return cleaned


async def assert_public_url(url: str, *, allow_http: bool = False) -> str:
    """Resolve the URL's host off the event loop and reject non-public targets."""
    cleaned = check_url_syntax(url, allow_http=allow_http)
    host, port = _check_parsed(cleaned, allow_http=allow_http)
    relaxed = _relaxed()
    ip = _literal_ip(host)
    if ip is not None:
        return cleaned
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise UnsafeUrlError(f"Could not resolve host {host!r}.") from exc
    _check_addresses(host, list(infos), relaxed=relaxed)
    return cleaned


async def _guard_request(request: httpx.Request) -> None:
    await assert_public_url(str(request.url), allow_http=False)


async def _guard_request_allow_http(request: httpx.Request) -> None:
    await assert_public_url(str(request.url), allow_http=True)


def guard_event_hooks(
    event_hooks: dict[str, list[Any]] | None = None,
    *,
    allow_http: bool = False,
) -> dict[str, list[Any]]:
    """Return ``event_hooks`` with the SSRF guard added to the request list.

    Every request hook runs before the request is sent, so position does not
    matter: a raising guard aborts the send either way. ``allow_http`` is for
    public-web fetches (scraping) where plain-HTTP origins are legitimate; the
    address checks still apply to every hop.
    """
    guard = _guard_request_allow_http if allow_http else _guard_request
    hooks = {key: list(value) for key, value in (event_hooks or {}).items()}
    hooks["request"] = [*hooks.get("request", []), guard]
    return hooks


def guarded_async_client(**kwargs: Any) -> httpx.AsyncClient:
    """httpx client that validates every request, including redirect hops."""
    kwargs["event_hooks"] = guard_event_hooks(kwargs.get("event_hooks"))
    kwargs.setdefault("max_redirects", DEFAULT_MAX_REDIRECTS)
    return httpx.AsyncClient(**kwargs)


async def fetch_limited(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_bytes: int,
    **kwargs: Any,
) -> httpx.Response:
    """Send a request and buffer at most ``max_bytes`` of body.

    Raises :class:`UnsafeUrlError` when the body exceeds the cap so callers do
    not buffer arbitrarily large responses into memory.
    """
    async with client.stream(method, url, **kwargs) as response:
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > max_bytes:
                raise UnsafeUrlError(f"Response body exceeds {max_bytes} bytes.")
            chunks.append(chunk)
        # aiter_bytes() already decoded the body; drop encoding headers so the
        # rebuilt response is not decoded a second time.
        headers = [
            (key, value)
            for key, value in response.headers.multi_items()
            if key.lower() not in {"content-encoding", "content-length", "transfer-encoding"}
        ]
        return httpx.Response(
            response.status_code,
            headers=headers,
            content=b"".join(chunks),
            request=response.request,
        )
