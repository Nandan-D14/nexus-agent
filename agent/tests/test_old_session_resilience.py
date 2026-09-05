import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from nexus.agent import extract_answer_from_reasoning
from nexus.control_loop import (
    _CAPABILITY_GROUPS,
    _same_capability_group,
    looks_like_empty_summary,
    looks_like_slide_code_dump,
    looks_like_unverified_success_claim,
)
from nexus.orchestrator import (
    NexusOrchestrator,
    is_error_inquiry,
    is_short_followup,
    is_task_inquiry,
    outstanding_user_task,
)
from nexus.tools.base import classify_exception_message, root_error_message


class OldSessionResilienceTests(unittest.TestCase):
    def test_task_inquiry_detection(self) -> None:
        self.assertTrue(is_task_inquiry("first tell me what was my task ?"))
        self.assertTrue(is_task_inquiry("what was my task ?"))
        self.assertTrue(is_task_inquiry("what is my task"))
        self.assertTrue(is_task_inquiry("what are we doing"))
        self.assertTrue(is_task_inquiry("remind me what was the task"))
        self.assertFalse(is_task_inquiry("build a React Vite landing page"))
        self.assertFalse(is_task_inquiry("create it"))
        self.assertFalse(is_task_inquiry("continue"))

    def test_outstanding_user_task_ignores_inquiries(self) -> None:
        messages = [
            {"role": "user", "text": "build a React Vite landing page for Tembo AI"},
            {"role": "assistant", "text": "Sure, I will set up the workspace."},
            {"role": "user", "text": "first tell me what was my task ?"},
        ]
        task = outstanding_user_task(messages, "first tell me what was my task ?")
        self.assertEqual(task, "build a React Vite landing page for Tembo AI")

    def test_capability_groups_cover_terminal_and_files(self) -> None:
        self.assertTrue(_same_capability_group("terminal_worker", "run_command"))
        self.assertTrue(_same_capability_group("run_command", "bash"))
        self.assertTrue(_same_capability_group("write_workspace_file", "prepare_task_workspace"))
        self.assertTrue(_same_capability_group("read_workspace_file", "write_workspace_file"))

    def test_extract_answer_from_reasoning(self) -> None:
        thought_with_tags = "<think>The user wants to know about Tembo. I should summarize.</think>Tembo AI is an AI engineering platform."
        self.assertEqual(extract_answer_from_reasoning(thought_with_tags), "Tembo AI is an AI engineering platform.")

        thought_paragraphs = (
            "Let's think about this.\n\n"
            "I need to check the dependencies.\n\n"
            "The landing page for Tembo AI has been scaffolded and the preview is live on port 5173."
        )
        self.assertEqual(
            extract_answer_from_reasoning(thought_paragraphs),
            "The landing page for Tembo AI has been scaffolded and the preview is live on port 5173.",
        )

    def test_artifact_request_matches_websites(self) -> None:
        from nexus.control_loop import _ARTIFACT_REQUEST
        self.assertTrue(bool(_ARTIFACT_REQUEST.search("Create a modern marketing website for my product")))
        self.assertTrue(bool(_ARTIFACT_REQUEST.search("Build a landing page with hero and pricing")))
        self.assertTrue(bool(_ARTIFACT_REQUEST.search("Make a React Vite web prototype")))
        self.assertTrue(bool(_ARTIFACT_REQUEST.search("Design a dashboard application")))
        self.assertTrue(bool(_ARTIFACT_REQUEST.search("Create a premium 8-slide presentation")))
        self.assertTrue(bool(_ARTIFACT_REQUEST.search("Generate the PPTX deck")))
        self.assertTrue(bool(_ARTIFACT_REQUEST.search("Where is my PPT or slide deck?")))
        self.assertTrue(bool(_ARTIFACT_REQUEST.search("continue and give ppt")))
        self.assertTrue(bool(_ARTIFACT_REQUEST.search("give ppt")))

    def test_verify_completion_requires_artifact_for_website(self) -> None:
        from nexus.control_loop import ActionLedger, ActionObservation, verify_completion
        ledger = ActionLedger()
        # Suppose agent only read the frontend-design skill and then answered with CSS rules
        obs = ActionObservation.from_tool_result(
            action_id="act-1",
            tool_name="read_skill",
            result={"status": "success", "summary": "Loaded skill frontend-design."},
        )
        ledger.finish(obs)

        verification = verify_completion(
            request="Create a modern marketing website for my product with a hero, features, pricing, and a contact section.",
            final_response="CSS: custom properties, reset, sections, bento grid.",
            ledger=ledger,
        )
        self.assertFalse(verification.verified)
        self.assertEqual(verification.error_code, "MISSING_ARTIFACT")

    def test_verify_completion_requires_artifact_for_presentation(self) -> None:
        from nexus.control_loop import ActionLedger, verify_completion

        verification = verify_completion(
            request="Create a modern premium 8-slide startup presentation",
            final_response="Slide 1 coordinates and visual design details are ready.",
            ledger=ActionLedger(),
        )

        self.assertFalse(verification.verified)
        self.assertEqual(verification.error_code, "MISSING_ARTIFACT")

    def test_verify_completion_requires_artifact_for_give_ppt(self) -> None:
        from nexus.control_loop import ActionLedger, verify_completion

        verification = verify_completion(
            request="continue and give ppt",
            final_response="def kicker(slide, text, x=0.9, y=1.28):",
            ledger=ActionLedger(),
        )

        self.assertFalse(verification.verified)
        self.assertEqual(verification.error_code, "MISSING_ARTIFACT")

    def test_verify_completion_uses_outstanding_task_for_bare_continue(self) -> None:
        from nexus.control_loop import ActionLedger, verify_completion

        # Bare "continue" names no deliverable itself, but the outstanding
        # task still owes the deck: zero tool calls must not verify.
        verification = verify_completion(
            request="continue",
            final_response="Working on it, almost done.",
            ledger=ActionLedger(),
            outstanding_task="Create a modern premium 8-slide startup presentation",
        )

        self.assertFalse(verification.verified)
        self.assertEqual(verification.error_code, "MISSING_ARTIFACT")

    def test_verify_completion_bare_continue_without_task_still_passes(self) -> None:
        from nexus.control_loop import ActionLedger, verify_completion

        # No outstanding deliverable: pure chat resumption must not veto.
        verification = verify_completion(
            request="continue",
            final_response="Here is the summary you asked for.",
            ledger=ActionLedger(),
        )

        self.assertTrue(verification.verified)

    def test_slide_code_dump_is_rejected_as_answer(self) -> None:
        from nexus.control_loop import ActionLedger, verify_completion

        kicker_dump = (
            "def kicker(slide, text, x=0.9, y=1.28):\n"
            "box w=8 h=0.3; run: text.upper(), 11pt, bold, TEAL, spc 300.\n"
            "Plus a small teal bar before it? E.g., a 0.28in x 0.03in teal"
        )
        self.assertTrue(looks_like_slide_code_dump(kicker_dump))

        # With an owed deck it maps to the deliverable nudge...
        artifact = verify_completion(
            request="Create a modern premium 8-slide startup presentation",
            final_response=kicker_dump,
            ledger=ActionLedger(),
        )
        self.assertFalse(artifact.verified)
        self.assertEqual(artifact.error_code, "MISSING_ARTIFACT")

        # ...and without one it is still not a valid final response.
        no_task = verify_completion(
            request="what is a kicker in slide design?",
            final_response=kicker_dump,
            ledger=ActionLedger(),
        )
        self.assertFalse(no_task.verified)
        self.assertEqual(no_task.error_code, "MISSING_FINAL_RESPONSE")

    def test_slide_code_dump_does_not_match_prose(self) -> None:
        self.assertFalse(
            looks_like_slide_code_dump("Your 8-slide deck is ready: deck.pptx")
        )
        self.assertFalse(looks_like_slide_code_dump(""))
        self.assertFalse(looks_like_slide_code_dump(None))

    def test_long_continue_prefix_is_a_new_request(self) -> None:
        self.assertTrue(is_short_followup("continue and give ppt"))
        self.assertFalse(
            is_short_followup(
                "continue building the checkout flow with Stripe webhooks, "
                "retry logic, and an admin dashboard for refunds"
            )
        )

    def test_unverified_success_claim_requires_artifact(self) -> None:
        from nexus.control_loop import ActionLedger, verify_completion

        claim = (
            "All todos are complete. The deliverable is done and verified. "
            "Here is my comprehensive final response.\n\n---\n"
        )
        # Claim + deliverable noun, no artifact, no link: must not verify.
        self.assertTrue(
            looks_like_unverified_success_claim(claim, has_artifacts=False)
        )
        verification = verify_completion(
            request="research internships and flag urgent deadlines",
            final_response=claim,
            ledger=ActionLedger(),
        )
        self.assertFalse(verification.verified)
        self.assertEqual(verification.error_code, "MISSING_ARTIFACT")

    def test_success_claim_passes_with_artifact_or_link(self) -> None:
        from nexus.control_loop import (
            ActionLedger,
            ActionObservation,
            verify_completion,
        )

        claim = "The spreadsheet is done and verified: SWE_Internships.xlsx"
        linked = claim + " https://example.com/files/SWE_Internships.xlsx"
        self.assertFalse(
            looks_like_unverified_success_claim(linked, has_artifacts=False)
        )

        ledger = ActionLedger()
        ledger.finish(
            ActionObservation.from_tool_result(
                action_id="act-1",
                tool_name="save_as_artifact",
                result={
                    "status": "success",
                    "summary": "Saved.",
                    "artifacts": [{"path": "outputs/SWE_Internships.xlsx"}],
                },
            )
        )
        verification = verify_completion(
            request="research internships",
            final_response=claim,
            ledger=ledger,
        )
        self.assertTrue(verification.verified)

    def test_empty_summary_guard(self) -> None:
        self.assertTrue(looks_like_empty_summary("Let me write a concise summary again."))
        self.assertTrue(
            looks_like_empty_summary("Here is my comprehensive final response:\n\n---\n")
        )
        self.assertTrue(looks_like_empty_summary("All todos are complete."))
        # Legitimate short answers must never trip the guard.
        self.assertFalse(looks_like_empty_summary("Submitted."))
        self.assertFalse(looks_like_empty_summary("Done."))
        self.assertFalse(looks_like_empty_summary("It is warm."))
        self.assertFalse(
            looks_like_empty_summary(
                "Your 8-slide deck is ready: https://example.com/deck.pptx"
            )
        )
        self.assertFalse(looks_like_empty_summary(""))
        self.assertFalse(looks_like_empty_summary(None))

    def test_empty_summary_is_missing_final_response(self) -> None:
        from nexus.control_loop import ActionLedger, verify_completion

        verification = verify_completion(
            request="summarize my emails",
            final_response="Let me write a concise summary again.",
            ledger=ActionLedger(),
        )
        self.assertFalse(verification.verified)
        self.assertEqual(verification.error_code, "MISSING_FINAL_RESPONSE")

    def test_exception_group_unwrap(self) -> None:
        group = ExceptionGroup(
            "unhandled errors in a TaskGroup",
            [TimeoutError("timed out while saving the page")],
        )
        self.assertEqual(
            root_error_message(group), "timed out while saving the page"
        )
        code, retryable = classify_exception_message(root_error_message(group))
        self.assertEqual(code, "TIMEOUT")
        self.assertTrue(retryable)

        nested = ExceptionGroup("outer", [ExceptionGroup("inner", [ValueError("boom")])])
        self.assertEqual(root_error_message(nested), "boom")

    def test_classify_exception_message(self) -> None:
        self.assertEqual(classify_exception_message("429 too many requests")[0], "RATE_LIMIT")
        self.assertEqual(classify_exception_message("401 unauthorized")[0], "AUTH_REQUIRED")
        self.assertEqual(classify_exception_message("connection reset by peer")[0], "HTTP_ERROR")
        self.assertEqual(classify_exception_message("weird novel failure")[0], "TOOL_EXCEPTION")

    def test_tpm_is_rate_limit_but_overflow_is_not(self) -> None:
        tpm = ValueError("TPM limit exceeded: requested 9000, limit 8000")
        self.assertTrue(NexusOrchestrator._is_tpm_limit_error(None, tpm))
        self.assertTrue(NexusOrchestrator._is_request_too_large_error(None, tpm))
        self.assertTrue(NexusOrchestrator._should_fallback_task_model(None, tpm))

        overflow = ValueError("input exceeds the model context limit")
        self.assertFalse(NexusOrchestrator._is_tpm_limit_error(None, overflow))
        self.assertTrue(NexusOrchestrator._is_context_overflow_error(None, overflow))
        self.assertFalse(NexusOrchestrator._should_fallback_task_model(None, overflow))

    def test_compact_retry_scope_caps_budget(self) -> None:
        from nexus.context_window import _input_token_budget, compact_retry_scope

        _, normal = _input_token_budget(None)
        self.assertGreater(normal, 32000)
        with compact_retry_scope(32000):
            _, compact = _input_token_budget(None)
            self.assertEqual(compact, 32000)
        _, restored = _input_token_budget(None)
        self.assertEqual(restored, normal)

    def test_is_error_inquiry(self) -> None:
        self.assertTrue(is_error_inquiry("what is the error you getting?"))
        self.assertTrue(is_error_inquiry("what was the error?"))
        self.assertTrue(is_error_inquiry("what went wrong"))
        self.assertTrue(is_error_inquiry("why did it fail"))
        self.assertFalse(is_error_inquiry("what is the weather"))
        self.assertFalse(is_error_inquiry("summarize my emails"))
        self.assertFalse(is_error_inquiry("continue"))


class ErrorInquiryDirectReplyTests(unittest.IsolatedAsyncioTestCase):
    async def test_error_inquiry_answered_without_agent_turn(self) -> None:
        fake = SimpleNamespace(
            _send_json=AsyncMock(),
            _persist_message=AsyncMock(),
            _last_turn_error="input exceeds the model context limit",
            _last_turn_error_code="AGENT_ERROR",
        )
        # No _run_agent_tracked on the fake: reaching it would raise.
        await NexusOrchestrator.handle_text_input(
            fake, "what is the error you getting?"
        )
        agent_texts = [
            call.kwargs.get("text", "")
            for call in fake._persist_message.call_args_list
            if call.kwargs.get("role") == "agent"
        ]
        self.assertTrue(agent_texts, "expected a direct agent reply")
        self.assertIn("input exceeds", agent_texts[0])
        self.assertIn("AGENT_ERROR", agent_texts[0])

    async def test_error_inquiry_without_recorded_error_runs_agent(self) -> None:
        ran = {}

        async def _tracked(*args, **kwargs) -> None:
            ran["called"] = True

        fake = SimpleNamespace(
            session=SimpleNamespace(id="s1"),
            history_repository=None,
            _send_json=AsyncMock(),
            _persist_message=AsyncMock(),
            _build_turn_input=AsyncMock(return_value="TURN_INPUT"),
            _run_agent_tracked=_tracked,
            _seed_context="",
            _last_turn_error="",
            _last_turn_error_code="",
            _outstanding_task="",
        )
        await NexusOrchestrator.handle_text_input(
            fake, "what was the error?"
        )
        self.assertTrue(ran.get("called"), "agent turn should run normally")


if __name__ == "__main__":
    unittest.main()

