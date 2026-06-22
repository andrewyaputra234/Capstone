"""Regression tests for the oral-guidance threshold."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent / "src"))

from crew_orchestrator import EducationCrew


class _NeedsMoreElaborationLlm:
    def invoke(self, _prompt: str) -> SimpleNamespace:
        return SimpleNamespace(
            content=(
                '{"accepted": false, "status": "needs_prompt", '
                '"examiner_reply": "Can you add another detail?", '
                '"reason": "The response needs more elaboration and connection to the visual stimulus.", '
                '"rubric_focus": ["Idea Development"]}'
            )
        )


class OralGuidanceThresholdTests(unittest.TestCase):
    def test_evaluator_accepts_a_relevant_answer_when_only_elaboration_is_missing(self) -> None:
        crew = object.__new__(EducationCrew)
        crew.subject = "test"
        crew.rubric_name = "test"
        crew.session_id = None
        crew.dialogue_manager = None
        crew.session_manager = None
        crew.llm = _NeedsMoreElaborationLlm()
        crew._rubric_summary = lambda: ""  # type: ignore[method-assign]

        with patch("crew_orchestrator._retrieve_vector_context", return_value=""):
            decision = crew.evaluate_oral_turn(
                question="What is the person doing in the picture?",
                student_response="I think the person went grocery shopping.",
            )

        self.assertTrue(decision["accepted"])
        self.assertEqual(decision["status"], "accepted")
        self.assertEqual(decision["examiner_reply"], "Thank you, let's move on to the next question.")

    def test_brief_relevant_answer_does_not_need_a_follow_up(self) -> None:
        self.assertFalse(
            EducationCrew._follow_up_is_allowed(
                "I think the person went grocery shopping.",
                "The response needs more elaboration and connection to the visual stimulus.",
            )
        )

    def test_unrelated_answer_can_receive_one_follow_up(self) -> None:
        self.assertTrue(
            EducationCrew._follow_up_is_allowed(
                "I like ice cream.",
                "The answer is unrelated to the image.",
            )
        )

    def test_contradictory_visible_detail_can_receive_one_follow_up(self) -> None:
        self.assertTrue(
            EducationCrew._follow_up_is_allowed(
                "There are no people in the picture.",
                "The response contradicts an important visual fact.",
            )
        )


if __name__ == "__main__":
    unittest.main()
