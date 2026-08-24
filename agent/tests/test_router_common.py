# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from __future__ import annotations

from types import SimpleNamespace

from nexus.router_common import apply_tool_call_policy, repair_tool_call_ids

_TOOLS = [{"type": "function", "function": {"name": "send_gmail"}}]


def test_policy_noop_without_tools() -> None:
    assert apply_tool_call_policy({}, None) == {}
    assert apply_tool_call_policy({}, []) == {}


def test_policy_pins_single_tool_call_when_tools_present() -> None:
    result = apply_tool_call_policy({"temperature": 0.2}, _TOOLS)
    assert result["parallel_tool_calls"] is False
    assert result["temperature"] == 0.2


def test_policy_respects_explicit_caller_override() -> None:
    result = apply_tool_call_policy({"parallel_tool_calls": True}, _TOOLS)
    assert result["parallel_tool_calls"] is True


def test_policy_does_not_mutate_input() -> None:
    original = {"temperature": 0.1}
    apply_tool_call_policy(original, _TOOLS)
    assert "parallel_tool_calls" not in original


def _response_with_ids(ids: list[str]):
    tool_calls = [SimpleNamespace(id=i, function=SimpleNamespace(name="send_gmail")) for i in ids]
    message = SimpleNamespace(tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_repair_assigns_unique_ids_for_duplicates() -> None:
    response = _response_with_ids(["dup", "dup", "dup"])
    repair_tool_call_ids(response)
    ids = [c.id for c in response.choices[0].message.tool_calls]
    assert len(set(ids)) == 3, ids
    assert ids[0] == "dup"  # first occurrence preserved


def test_repair_fills_missing_ids() -> None:
    response = _response_with_ids(["", ""])
    repair_tool_call_ids(response)
    ids = [c.id for c in response.choices[0].message.tool_calls]
    assert all(i for i in ids)
    assert len(set(ids)) == 2


def test_repair_handles_dict_shaped_messages() -> None:
    response = {
        "choices": [
            {"message": {"tool_calls": [{"id": "x"}, {"id": "x"}]}}
        ]
    }
    repair_tool_call_ids(response)
    calls = response["choices"][0]["message"]["tool_calls"]
    assert calls[0]["id"] == "x"
    assert calls[1]["id"] != "x"


def test_repair_is_safe_on_non_response_objects() -> None:
    # Streaming wrappers / unexpected shapes must not raise.
    assert repair_tool_call_ids(None) is None
    assert repair_tool_call_ids("stream") == "stream"
    assert repair_tool_call_ids(SimpleNamespace(choices=None)) is not None
