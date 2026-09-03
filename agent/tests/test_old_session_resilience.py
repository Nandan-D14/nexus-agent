import unittest
from unittest.mock import MagicMock, patch

from nexus.agent import extract_answer_from_reasoning
from nexus.control_loop import _CAPABILITY_GROUPS, _same_capability_group
from nexus.orchestrator import is_task_inquiry, outstanding_user_task


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


if __name__ == "__main__":
    unittest.main()

