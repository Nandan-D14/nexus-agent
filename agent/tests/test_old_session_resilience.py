import unittest
from unittest.mock import MagicMock, patch

from nexus.agent import extract_answer_from_reasoning
from nexus.control_loop import (
    _CAPABILITY_GROUPS,
    _same_capability_group,
    looks_like_slide_code_dump,
)
from nexus.orchestrator import is_short_followup, is_task_inquiry, outstanding_user_task


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


if __name__ == "__main__":
    unittest.main()

