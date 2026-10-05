"""Phase A (response redesign): part classification, answer selection,
tool-free finalization pass, sanitizer and markup rules."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from nexus.config import settings
from nexus.control_loop import is_fenced_help_answer, looks_like_slide_code_dump
from nexus.output_normalization import sanitize_stream_text
from nexus.turn_heuristics import should_hide_markup
from nexus.turn_output import (
    TurnOutput,
    classify_text_part,
    finalization_blocked_result,
    finalization_pass,
    finalization_pass_active,
    looks_like_generic_stub,
    make_finalization_guard,
    select_answer,
)


def _part(text=None, *, thought=False, function_call=None, function_response=None):
    return SimpleNamespace(
        text=text,
        thought=thought,
        function_call=function_call,
        function_response=function_response,
    )


class _Event:
    def __init__(self, parts, final=False):
        self.content = SimpleNamespace(parts=parts)
        self._final = final

    def is_final_response(self):
        return self._final


def _call(name="terminal_worker", args=None):
    return SimpleNamespace(name=name, args=args or {})


def _ok(text):
    return bool(text and text.strip())


# ── classification ─────────────────────────────────────────────


def test_final_text_is_answer_even_with_heuristic_on():
    assert classify_text_part(
        _part("Hi"), is_final=True, has_function_calls=False, reasoning_is_text=True
    ) == "answer"


def test_thought_part_stays_reasoning_on_final_event():
    assert classify_text_part(
        _part("plan", thought=True), is_final=True, has_function_calls=False
    ) == "reasoning"


def test_text_with_tool_calls_is_narration():
    assert classify_text_part(
        _part("Checking files"), is_final=False, has_function_calls=True
    ) == "narration"


def test_heuristic_applies_only_to_non_final_text():
    assert classify_text_part(
        _part("x"), is_final=False, has_function_calls=False, reasoning_is_text=True
    ) == "reasoning"
    assert classify_text_part(
        _part("x"), is_final=False, has_function_calls=False, reasoning_is_text=False
    ) == "answer"


def test_reasoning_is_text_is_off_by_default():
    assert settings.reasoning_is_text is False


# ── answer selection ───────────────────────────────────────────


def test_final_text_joins_all_answer_parts():
    out = TurnOutput()
    out.observe(_Event([_part("Part one. "), _part("Part two.")], final=True))
    assert out.answer == "Part one. Part two."


def test_last_batch_narration_beats_stub():
    out = TurnOutput()
    out.observe(_Event([_part("Starting research.", function_call=_call())]))
    out.observe(_Event([_part(function_response=object())]))
    out.observe(_Event([
        _part("Report saved to outputs/report.pdf with 3 sections.", function_call=_call("report_completion")),
    ]))
    out.observe(_Event([_part(function_response=object())]))
    out.observe(_Event([_part("Done.")], final=True))
    assert select_answer(out, promotable=_ok) == "Report saved to outputs/report.pdf with 3 sections."


def test_progress_narration_before_later_tools_is_not_the_answer():
    out = TurnOutput()
    out.observe(_Event([_part("Let me look at the repo first.", function_call=_call())]))
    out.observe(_Event([_part(function_response=object())]))
    out.observe(_Event([_part(function_call=_call())]))  # later batch, no narration
    out.observe(_Event([_part(function_response=object())], final=True))
    assert select_answer(out, promotable=_ok) is None


def test_report_completion_summary_is_used_when_no_text():
    out = TurnOutput()
    out.observe(_Event([
        _part(function_call=_call("report_completion", {"status": "done", "summary": "Built the deck: deck.pptx"})),
    ]))
    out.observe(_Event([_part(function_response=object())], final=True))
    assert select_answer(out, promotable=_ok) == "Built the deck: deck.pptx"


def test_stub_is_still_returned_when_nothing_better():
    out = TurnOutput()
    out.observe(_Event([_part("Done.")], final=True))
    assert select_answer(out, promotable=_ok) == "Done."


def test_generic_stub_detection():
    assert looks_like_generic_stub("Done!")
    assert looks_like_generic_stub("All set.")
    assert not looks_like_generic_stub("Done: https://example.com/deck")
    assert not looks_like_generic_stub("Paris is the capital of France.")


# ── finalization pass ──────────────────────────────────────────


def test_finalization_pass_context_is_scoped():
    assert not finalization_pass_active()
    with finalization_pass():
        assert finalization_pass_active()
    assert not finalization_pass_active()


def test_gateway_blocks_tools_during_finalization():
    from nexus.tool_gateway import gated_tool

    calls = []

    async def write_workspace_file(path: str) -> dict:
        calls.append(path)
        return {"status": "success"}

    wrapped = gated_tool(write_workspace_file)

    async def _run():
        with finalization_pass():
            return await wrapped(path="a.txt")

    result = asyncio.run(_run())
    assert result["error_code"] == "FINALIZATION_PASS"
    assert calls == []


def test_finalization_guard_appends_note_only_when_active():
    guard = make_finalization_guard()
    req = SimpleNamespace(contents=[])
    guard(None, req)
    assert req.contents == []
    with finalization_pass():
        guard(None, req)
    assert len(req.contents) == 1
    assert "Tools are disabled" in req.contents[0].parts[0].text


def test_finalization_guard_sets_tool_choice_none():
    from google.genai import types

    guard = make_finalization_guard()
    config = types.GenerateContentConfig(
        tools=[types.Tool(function_declarations=[types.FunctionDeclaration(name="run_command")])]
    )
    req = SimpleNamespace(contents=[], config=config)
    with finalization_pass():
        guard(None, req)
    mode = req.config.tool_config.function_calling_config.mode
    assert mode == types.FunctionCallingConfigMode.NONE
    # Declarations stay so history tool calls remain valid.
    assert req.config.tools


def test_blocked_result_shape():
    result = finalization_blocked_result("run_command")
    assert result["status"] == "blocked"
    assert result["error_code"] == "FINALIZATION_PASS"


def test_run_agent_turn_runs_one_tool_free_pass():
    from nexus.agent import run_agent_turn

    seen_flags = []

    class Runner:
        calls = 0

        async def run_async(self, *, user_id, session_id, new_message):
            Runner.calls += 1
            seen_flags.append(finalization_pass_active())
            if Runner.calls == 1:
                yield _Event([_part(function_call=_call())])
                yield _Event([_part(function_response=object())], final=True)
            else:
                yield _Event([_part("Here is the summary.")], final=True)

    session_service = SimpleNamespace(
        get_session=AsyncMock(return_value=object()), create_session=AsyncMock()
    )

    async def _run():
        with patch("nexus.agent.get_agent_usage_source", return_value=("agent", "m")), \
             patch("nexus.agent.extract_token_usage_records", return_value=[]), \
             patch.object(settings, "force_final_synthesis", True):
            return await run_agent_turn(
                runner=Runner(),
                session_service=session_service,
                session_id="s",
                user_id="u",
                message="summarize",
                runtime_config=SimpleNamespace(),
                max_turns=10,
            )

    result = asyncio.run(_run())
    assert result.response == "Here is the summary."
    assert result.finalization_pass_used is True
    assert seen_flags == [False, True]


# ── sanitizer and markup rules ─────────────────────────────────


def test_sanitizer_keeps_undefined_and_nan_in_prose_and_code():
    text = "If x is undefined, JS returns NaN.\n```js\nlet a = undefined;\n```"
    assert sanitize_stream_text(text) == text


def test_sanitizer_strips_coercion_artifacts_and_sentinel_lines():
    assert "[object Object]" not in sanitize_stream_text("Result: [object Object] ok")
    assert sanitize_stream_text("Answer\nundefined\nmore") == "Answer\nmore"


def test_css_help_answer_is_not_hidden():
    answer = (
        "To center the card, use flexbox on the parent:\n"
        "```css\n.wrap { display: flex; justify-content: center; align-items: center; }\n```"
    )
    assert not should_hide_markup(answer, "how do I center a div with css?")


def test_raw_markup_dump_is_hidden_for_website_request():
    dump = "<section class='hero'><h1>Acme</h1></section>"
    assert should_hide_markup(dump, "build a landing page for Acme")


def test_bare_markup_is_hidden_without_request_context():
    assert should_hide_markup("<!doctype html><html><body>x</body></html>", "")


def test_fenced_pptx_help_answer_is_not_slide_dump():
    answer = (
        "You can add a text box with python-pptx like this, then set the font size:\n"
        "```python\nfrom pptx import Presentation\nslide.shapes.add_textbox(0, 0, 100, 50)\n```"
    )
    assert is_fenced_help_answer(answer)
    assert not looks_like_slide_code_dump(answer)
