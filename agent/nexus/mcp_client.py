# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Remote MCP client support for user-configured Streamable HTTP servers."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

import httpx

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from nexus.config import settings
from nexus.tracing import (
    monotonic_ms,
    safe_origin,
    safe_trace_value,
    trace_headers,
    trace_metadata,
)

logger = logging.getLogger(__name__)

SECRET_KEY_RE = re.compile(r"(authorization|token|secret|password|api[_-]?key)", re.I)

if TYPE_CHECKING:
    from nexus.history_repository import StoredIntegrationConnection


@dataclass
class McpDiscoveredTool:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class McpTestResult:
    ok: bool
    tools: list[McpDiscoveredTool]
    resources: list[dict[str, Any]]
    error: str = ""
    latency_ms: int = 0


def slugify_tool_part(value: str, *, fallback: str = "tool") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()
    if not cleaned:
        cleaned = fallback
    if cleaned[0].isdigit():
        cleaned = f"_{cleaned}"
    return cleaned[:64]


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, raw in value.items():
            if SECRET_KEY_RE.search(str(key)):
                redacted[str(key)] = "[redacted]"
            else:
                redacted[str(key)] = redact_sensitive(raw)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value


async def _emit_mcp_trace(event_type: str, **payload: Any) -> None:
    event = {
        "type": event_type,
        **trace_metadata(),
        **safe_trace_value(payload),
    }
    logger.info(
        "MCP trace type=%s trace=%s operation=%s status=%s",
        event_type,
        event.get("trace_id", ""),
        event.get("operation", ""),
        event.get("status_code", ""),
    )
    try:
        from nexus.tools._context import get_send_json

        send_json = get_send_json()
        if send_json is not None:
            await send_json(event)
    except Exception:
        logger.debug("Unable to emit MCP trace event", exc_info=True)


def normalize_tool_result(result: Any) -> dict[str, Any]:
    content = getattr(result, "content", None) or []
    text_parts: list[str] = []
    blocks: list[dict[str, Any]] = []
    for block in content:
        block_type = getattr(block, "type", None) or (
            block.get("type") if isinstance(block, dict) else None
        )
        text = getattr(block, "text", None) or (
            block.get("text") if isinstance(block, dict) else None
        )
        if isinstance(text, str) and text:
            text_parts.append(text)
        payload = {}
        if hasattr(block, "model_dump"):
            try:
                payload = block.model_dump(mode="json")
            except TypeError:
                payload = block.model_dump()
        elif isinstance(block, dict):
            payload = block
        else:
            payload = {"type": block_type or type(block).__name__, "text": text}
        blocks.append(payload)

    structured = (
        getattr(result, "structuredContent", None)
        or getattr(result, "structured_content", None)
    )
    is_error = bool(getattr(result, "isError", False) or getattr(result, "is_error", False))
    return {
        "status": "error" if is_error else "success",
        "text": "\n".join(text_parts).strip(),
        "content": blocks,
        "structured": structured if structured is not None else {},
    }


def _tool_to_dict(tool: Any) -> McpDiscoveredTool:
    schema = (
        getattr(tool, "inputSchema", None)
        or getattr(tool, "input_schema", None)
        or {}
    )
    if hasattr(schema, "model_dump"):
        schema = schema.model_dump(mode="json")
    if not isinstance(schema, dict):
        schema = {}
    return McpDiscoveredTool(
        name=str(getattr(tool, "name", "")),
        description=str(getattr(tool, "description", "") or ""),
        input_schema=schema,
    )


def _resource_to_dict(resource: Any) -> dict[str, Any]:
    if hasattr(resource, "model_dump"):
        try:
            return resource.model_dump(mode="json")
        except TypeError:
            return resource.model_dump()
    if isinstance(resource, dict):
        return resource
    return {
        "uri": str(getattr(resource, "uri", "")),
        "name": str(getattr(resource, "name", "") or ""),
        "description": str(getattr(resource, "description", "") or ""),
    }


class McpRemoteClient:
    """Short-lived client for remote Streamable HTTP MCP servers."""

    def __init__(
        self,
        *,
        url: str,
        bearer_token: str = "",
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 30.0,
        read_timeout_seconds: float = 120.0,
        connect_timeout_seconds: float | None = None,
    ) -> None:
        self.url = url
        self.bearer_token = bearer_token
        self.headers = dict(headers or {})
        self.timeout_seconds = timeout_seconds
        self.read_timeout_seconds = read_timeout_seconds
        # A server that is simply down should not spend the connect budget of a
        # server that is merely slow: the planner runs one tool per step, so a
        # dead connector otherwise eats a large slice of the turn.
        self.connect_timeout_seconds = (
            float(settings.mcp_connect_timeout_seconds)
            if connect_timeout_seconds is None
            else float(connect_timeout_seconds)
        )

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            self.timeout_seconds,
            connect=min(self.connect_timeout_seconds, self.timeout_seconds),
            read=self.read_timeout_seconds,
        )

    def _headers(self) -> dict[str, str]:
        headers = dict(self.headers)
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        headers.update(trace_headers())
        return headers

    def _event_hooks(
        self,
        *,
        operation: str,
        tool_name: str = "",
    ) -> dict[str, list[Callable[..., Awaitable[None]]]]:
        async def on_request(request: httpx.Request) -> None:
            request.extensions["nexus_trace_started_ms"] = monotonic_ms()
            await _emit_mcp_trace(
                "mcp_http_request",
                operation=operation,
                tool=tool_name,
                method=request.method,
                server=safe_origin(str(request.url)),
            )

        async def on_response(response: httpx.Response) -> None:
            started = int(response.request.extensions.get("nexus_trace_started_ms") or monotonic_ms())
            await _emit_mcp_trace(
                "mcp_http_response",
                operation=operation,
                tool=tool_name,
                method=response.request.method,
                server=safe_origin(str(response.request.url)),
                status_code=response.status_code,
                latency_ms=max(0, monotonic_ms() - started),
            )

        return {"request": [on_request], "response": [on_response]}

    async def discover(self) -> McpTestResult:
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(
                headers=self._headers(),
                timeout=self._timeout(),
                follow_redirects=True,
                event_hooks=self._event_hooks(operation="discover"),
            ) as http_client:
                async with streamable_http_client(self.url, http_client=http_client) as streams:
                    read_stream, write_stream = streams[0], streams[1]
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        tools_result = await session.list_tools()
                        tools = [
                            _tool_to_dict(tool)
                            for tool in getattr(tools_result, "tools", [])
                            if getattr(tool, "name", "")
                        ]
                        resources: list[dict[str, Any]] = []
                        try:
                            resources_result = await session.list_resources()
                            resources = [
                                _resource_to_dict(resource)
                                for resource in getattr(resources_result, "resources", [])
                            ]
                        except Exception:
                            logger.debug("MCP resource discovery failed for %s", self.url, exc_info=True)
                        return McpTestResult(
                            ok=True,
                            tools=tools,
                            resources=resources,
                            latency_ms=int((time.monotonic() - started) * 1000),
                        )
        except Exception as exc:
            await _emit_mcp_trace(
                "mcp_http_error",
                operation="discover",
                server=safe_origin(self.url),
                error_type=type(exc).__name__,
                error=str(exc)[:500],
                latency_ms=int((time.monotonic() - started) * 1000),
            )
            return McpTestResult(
                ok=False,
                tools=[],
                resources=[],
                error=str(exc)[:500] or "MCP connection failed",
                latency_ms=int((time.monotonic() - started) * 1000),
            )

    async def call_tool(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        progress_callback: Callable[[float, float | None, str | None], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(
                headers=self._headers(),
                timeout=self._timeout(),
                follow_redirects=True,
                event_hooks=self._event_hooks(operation="call_tool", tool_name=tool_name),
            ) as http_client:
                async with streamable_http_client(self.url, http_client=http_client) as streams:
                    read_stream, write_stream = streams[0], streams[1]
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        result = await session.call_tool(
                            tool_name,
                            arguments=arguments or {},
                            progress_callback=progress_callback,
                            read_timeout_seconds=self.read_timeout_seconds,
                        )
                        payload = normalize_tool_result(result)
                        payload["latency_ms"] = int((time.monotonic() - started) * 1000)
                        payload["tool"] = tool_name
                        return payload
        except Exception as exc:
            await _emit_mcp_trace(
                "mcp_http_error",
                operation="call_tool",
                tool=tool_name,
                server=safe_origin(self.url),
                error_type=type(exc).__name__,
                error=str(exc)[:500],
                latency_ms=int((time.monotonic() - started) * 1000),
            )
            raise


def discovered_tools_payload(tools: list[McpDiscoveredTool]) -> list[dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
        for tool in tools
    ]


def pretty_json(value: Any, limit: int = 2000) -> str:
    try:
        text = json.dumps(redact_sensitive(value), ensure_ascii=True, indent=2)
    except Exception:
        text = str(value)
    return text[:limit]


_MAX_SCHEMA_DESCRIPTION_CHARS = 900


def _describe_mcp_arguments(description: str, input_schema: Any) -> str:
    """Append the remote tool's argument contract to its description.

    Every MCP tool reaches ADK with the same opaque ``arguments: dict``
    signature, so the schema is the only thing that tells the model which keys
    to send. Rendered compactly to stay affordable across many connectors.
    """
    if not isinstance(input_schema, dict):
        return description
    properties = input_schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        return description

    required = input_schema.get("required")
    required_set = {str(item) for item in required} if isinstance(required, list) else set()

    fields: list[str] = []
    for key, spec in properties.items():
        spec = spec if isinstance(spec, dict) else {}
        field_type = str(spec.get("type") or "any")
        detail = f"{key} ({field_type}"
        detail += ", required)" if str(key) in required_set else ")"
        summary = str(spec.get("description") or "").strip()
        if summary:
            detail += f": {summary}"
        fields.append(detail)

    rendered = "; ".join(fields)
    if len(rendered) > _MAX_SCHEMA_DESCRIPTION_CHARS:
        rendered = rendered[: _MAX_SCHEMA_DESCRIPTION_CHARS - 1].rstrip() + "…"
    return f"{description}\n\nArguments (pass as the `arguments` object): {rendered}"


def build_mcp_adk_tools(
    connections: list["StoredIntegrationConnection"],
) -> list[Callable[..., Awaitable[dict[str, Any]]]]:
    """Build ADK-callable async functions for enabled MCP tools."""
    adk_tools: list[Callable[..., Awaitable[dict[str, Any]]]] = []
    used_names: set[str] = set()

    for connection in connections:
        if connection.connector_type != "mcp_remote_http":
            continue
        url = str(connection.private.get("url") or "")
        if not url:
            continue
        bearer_token = str(connection.private.get("bearerToken") or "")
        extra_headers = {
            str(key).strip(): str(value).strip()
            for key, value in (connection.private.get("extraHeaders") or {}).items()
            if str(key).strip() and str(value).strip()
        }
        auth_type = str(connection.private.get("authType") or "")
        owner_id = str(getattr(connection, "owner_id", "") or "")
        provider = str(getattr(connection, "provider", "") or "")
        server_slug = slugify_tool_part(connection.name or connection.connection_id, fallback="mcp")
        tools = connection.private.get("tools")
        if not isinstance(tools, list):
            tools = []

        for raw_tool in tools:
            if not isinstance(raw_tool, dict) or not raw_tool.get("name"):
                continue
            remote_tool_name = str(raw_tool["name"])
            base_name = f"mcp__{server_slug}__{slugify_tool_part(remote_tool_name)}"
            public_name = base_name
            suffix = 2
            while public_name in used_names:
                public_name = f"{base_name}_{suffix}"
                suffix += 1
            used_names.add(public_name)
            description = str(raw_tool.get("description") or "Call a remote MCP tool.")
            # ADK derives the schema from the Python signature, which is only
            # `arguments: dict`. Without the remote schema the model has to guess
            # field names, so fold it into the description where it can see it.
            description = _describe_mcp_arguments(description, raw_tool.get("input_schema"))

            async def _call_mcp_tool(
                arguments: dict[str, Any] | None = None,
                *,
                _url: str = url,
                _token: str = bearer_token,
                _headers: dict[str, str] = extra_headers,
                _tool_name: str = remote_tool_name,
                _connection_id: str = connection.connection_id,
                _connection_name: str = connection.name,
                _owner_id: str = owner_id,
                _provider: str = provider,
                _auth_type: str = auth_type,
            ) -> dict[str, Any]:
                """Call a configured remote MCP tool with JSON arguments."""
                from nexus.exa_oauth import ensure_exa_access_token, is_unauthorized_mcp_error
                from nexus.mcp_oauth import MCP_OAUTH_SPECS, ensure_mcp_oauth_access_token
                from nexus.slack_oauth import ensure_slack_access_token
                from nexus.treg_oauth import ensure_treg_access_token

                token = _token
                if _auth_type == "oauth" and _owner_id:
                    if _provider == "exa":
                        token = await ensure_exa_access_token(_owner_id) or _token
                    elif _provider == "treg":
                        token = await ensure_treg_access_token(_owner_id) or _token
                    elif _provider == "slack":
                        token = await ensure_slack_access_token(_owner_id) or _token
                    elif _provider in MCP_OAUTH_SPECS:
                        spec = MCP_OAUTH_SPECS.get(_provider)
                        token = await ensure_mcp_oauth_access_token(
                            _owner_id,
                            _provider,
                            resource=spec.mcp_origin if spec else "",
                        ) or _token
                client = McpRemoteClient(url=_url, bearer_token=token, headers=_headers)
                try:
                    result = await client.call_tool(
                        tool_name=_tool_name,
                        arguments=arguments or {},
                    )
                    return {
                        **result,
                        "connection_id": _connection_id,
                        "connector": _connection_name,
                        "arguments": redact_sensitive(arguments or {}),
                    }
                except Exception as exc:
                    if (
                        _provider in {"exa", "treg", "slack", *MCP_OAUTH_SPECS}
                        and _owner_id
                        and is_unauthorized_mcp_error(exc)
                    ):
                        if _provider == "treg":
                            retry_token = await ensure_treg_access_token(_owner_id, force=True)
                        elif _provider == "exa":
                            retry_token = await ensure_exa_access_token(_owner_id, force=True)
                        elif _provider == "slack":
                            retry_token = await ensure_slack_access_token(_owner_id, force=True)
                        else:
                            spec = MCP_OAUTH_SPECS.get(_provider)
                            retry_token = await ensure_mcp_oauth_access_token(
                                _owner_id,
                                _provider,
                                force=True,
                                resource=spec.mcp_origin if spec else "",
                            )
                        if retry_token and retry_token != token:
                            try:
                                retry_client = McpRemoteClient(
                                    url=_url, bearer_token=retry_token, headers=_headers
                                )
                                result = await retry_client.call_tool(
                                    tool_name=_tool_name,
                                    arguments=arguments or {},
                                )
                                return {
                                    **result,
                                    "connection_id": _connection_id,
                                    "connector": _connection_name,
                                    "arguments": redact_sensitive(arguments or {}),
                                }
                            except Exception as retry_exc:
                                exc = retry_exc
                    return {
                        "status": "error",
                        "error": str(exc)[:500] or "MCP tool call failed",
                        "connection_id": _connection_id,
                        "connector": _connection_name,
                        "tool": _tool_name,
                        "arguments": redact_sensitive(arguments or {}),
                    }

            _call_mcp_tool.__name__ = public_name
            _call_mcp_tool.__qualname__ = public_name
            _call_mcp_tool.__doc__ = (
                f"{description}\n\n"
                "Args:\n"
                "    arguments: JSON object matching the remote MCP tool input schema.\n\n"
                "Returns:\n"
                "    dict with status, text/content/structured result, latency_ms, connector, and error when failed."
            )
            # Tagged so per-turn allowlists can resolve MCP tools by connection.
            setattr(_call_mcp_tool, "_connection_id", connection.connection_id)
            adk_tools.append(_call_mcp_tool)

    return adk_tools
