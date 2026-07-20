# Proprietary and non-commercial use only.

"""Collaborators extracted from the NexusOrchestrator god object.

- :class:`OrchestratorComponent` — base bound to the owning orchestrator; it
  forwards any attribute it does not define (orchestrator state and methods)
  to the owner. Components only *read* orchestrator state and call owner
  methods, so read-through forwarding is sufficient.
- :class:`WsMessenger` — the WebSocket / event-sink send layer.

The :class:`~nexus.orchestrator.NexusOrchestrator` composes these and delegates
to them via ``__getattr__``, so its own methods keep calling ``self._send_json``
etc. unchanged.
"""

from __future__ import annotations

import logging
from typing import Any

from starlette.websockets import WebSocketState

from nexus.debug_trace import emit_debug_trace
from nexus.event_sink import prepare_correlated_event

logger = logging.getLogger("nexus.orchestrator")


class OrchestratorComponent:
    """A concern extracted from NexusOrchestrator, bound to the owning instance."""

    def __init__(self, owner) -> None:
        self._owner = owner

    def __getattr__(self, name: str):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        owner = self.__dict__.get("_owner")
        if owner is None:
            raise AttributeError(name)
        return getattr(owner, name)


class WsMessenger(OrchestratorComponent):
    """WebSocket / event-sink delivery for the orchestrator."""

    def _ws_is_open(self) -> bool:
        ws = getattr(self, "ws", None)
        if ws is None:
            return False

        client_state = getattr(ws, "client_state", WebSocketState.CONNECTED)
        application_state = getattr(ws, "application_state", WebSocketState.CONNECTED)
        return (
            getattr(self, "_ws_connected", True)
            and client_state == WebSocketState.CONNECTED
            and application_state == WebSocketState.CONNECTED
        )

    async def _send_bytes(self, data: bytes) -> None:
        try:
            async with self._ws_send_lock:
                if not self._ws_is_open():
                    logger.debug("Skipping WS audio frame — connection not open")
                    return
                await self.ws.send_bytes(data)
        except RuntimeError as exc:
            if "websocket.close" in str(exc) or "response already completed" in str(exc):
                logger.debug("Skipping WS audio frame — connection closed")
                self.mark_ws_disconnected()
            else:
                logger.warning("Failed to send WS audio frame", exc_info=True)
        except Exception:
            if not self._ws_is_open():
                logger.debug("Skipping WS audio frame — connection closed")
                self.mark_ws_disconnected()
                return
            logger.warning("Failed to send WS audio frame", exc_info=True)

    async def _send_json(self, data: dict) -> None:
        """Emit an orchestrator event through the configured sinks."""
        context = getattr(self, "_trace_context", None)
        data = prepare_correlated_event(data, context)
        event_sink = getattr(self, "_event_sink", None)
        if event_sink is None:
            await self._send_json_to_ws(data)
            return
        await event_sink.send(data)

    async def _send_json_to_ws(self, data: dict) -> None:
        """Send JSON message to the frontend WebSocket."""
        message_type = data.get("type")

        def trace_delivery(outcome: str, error_type: str = "") -> None:
            if message_type not in {
                "agent_tool_call",
                "agent_tool_result",
                "agent_complete",
                "error",
                "run_status",
            }:
                return
            # region agent log
            emit_debug_trace(
                run_id=self._debug_run_id(),
                hypothesis_id="H4",
                location="orchestrator.py:2282",
                message="websocket_event_delivery",
                data={
                    "message_type": message_type,
                    "outcome": outcome,
                    "error_type": error_type,
                    "websocket_open": self._ws_is_open(),
                    "durable_run_bound": bool(getattr(self, "_durable_task_id", None)),
                },
            )
            # endregion agent log

        try:
            async with self._ws_send_lock:
                if not self._ws_is_open():
                    logger.debug("Skipping WS message %s — connection not open", message_type)
                    trace_delivery("skipped_closed")
                    return
                await self.ws.send_json(data)
                trace_delivery("sent")
        except RuntimeError as exc:
            if "websocket.close" in str(exc) or "response already completed" in str(exc):
                logger.debug("Skipping WS message %s — connection closed", message_type)
                self.mark_ws_disconnected()
                trace_delivery("closed_runtime_error", type(exc).__name__)
            else:
                logger.warning(
                    "Failed to send WS message: %s",
                    message_type,
                    exc_info=True,
                )
                trace_delivery("runtime_error", type(exc).__name__)
        except Exception:
            if not self._ws_is_open():
                logger.debug("Skipping WS message %s — connection closed", message_type)
                self.mark_ws_disconnected()
                trace_delivery("closed_exception")
                return
            logger.warning(
                "Failed to send WS message: %s",
                message_type,
                exc_info=True,
            )
            trace_delivery("exception")

    @staticmethod
    def _quota_update_payload(quota: dict[str, Any]) -> dict[str, Any]:
        payload = {"type": "quota_update"}
        payload.update(quota)
        return payload

    async def _emit_budget_warning(
        self,
        *,
        state: str,
        action: str,
        message: str,
        projected_total_tokens: int | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "type": "budget_warning",
            "state": state,
            "action": action,
            "message": message,
            "soft_limit": self._RESUME_PACKET_SOFT_TOKENS,
            "hard_limit": self._RESUME_PACKET_HARD_TOKENS,
        }
        if projected_total_tokens is not None:
            payload["projected_total_tokens"] = projected_total_tokens
        await self._send_json(payload)

    async def _send_artifact_created(self, artifact_payload: dict[str, Any]) -> None:
        try:
            self.session.artifact_count += 1
        except Exception:
            pass
        await self._send_json({
            "type": "artifact_created",
            "artifact": artifact_payload,
        })
