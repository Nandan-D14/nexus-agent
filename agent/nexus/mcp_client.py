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

logger = logging.getLogger(__name__)

SECRET_KEY_RE = re.compile(r"(authorization|token|secret|password|api[_-]?key)", re.I)
RISKY_TOOL_RE = re.compile(r"(create|update|delete|write|drop|deploy|send|upload|insert|execute|run)", re.I)

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
    ) -> None:
        self.url = url
        self.bearer_token = bearer_token
        self.headers = dict(headers or {})
        self.timeout_seconds = timeout_seconds
        self.read_timeout_seconds = read_timeout_seconds

    def _headers(self) -> dict[str, str]:
        headers = dict(self.headers)
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return headers

    async def discover(self) -> McpTestResult:
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(
                headers=self._headers(),
                timeout=httpx.Timeout(self.timeout_seconds, read=self.read_timeout_seconds),
                follow_redirects=True,
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
        async with httpx.AsyncClient(
            headers=self._headers(),
            timeout=httpx.Timeout(self.timeout_seconds, read=self.read_timeout_seconds),
            follow_redirects=True,
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

            async def _call_mcp_tool(
                arguments: dict[str, Any] | None = None,
                *,
                _url: str = url,
                _token: str = bearer_token,
                _tool_name: str = remote_tool_name,
                _connection_id: str = connection.connection_id,
                _connection_name: str = connection.name,
            ) -> dict[str, Any]:
                """Call a configured remote MCP tool with JSON arguments."""
                if RISKY_TOOL_RE.search(_tool_name):
                    try:
                        from nexus.tools._context import get_bg_task_manager

                        manager = get_bg_task_manager()
                    except Exception:
                        manager = None
                    if manager is not None:
                        task_id, approved = await manager.request_permission(
                            description=f"Allow MCP tool {_connection_name}.{_tool_name}",
                            estimated_seconds=30,
                            agent="mcp",
                        )
                        if not approved:
                            return {
                                "status": "cancelled",
                                "error": "User denied MCP tool permission.",
                                "task_id": task_id,
                                "connection_id": _connection_id,
                                "connector": _connection_name,
                                "tool": _tool_name,
                                "arguments": redact_sensitive(arguments or {}),
                            }
                client = McpRemoteClient(url=_url, bearer_token=_token)
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
            adk_tools.append(_call_mcp_tool)

    return adk_tools
