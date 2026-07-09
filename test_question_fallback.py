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


class _GenericUnrelatedFollowUpLlm:
    def __init__(self) -> None:
        self.prompt = ""

    def invoke(self, prompt: str) -> SimpleNamespace:
        self.prompt = prompt
        return SimpleNamespace(
            content=(
                '{"accepted": false, "status": "needs_prompt", '
                '"examiner_reply": "Can you add another detail?", '
                '"reason": "The answer is unrelated to the image.", '
                '"rubric_focus": ["Stimulus Response Relevance"]}'
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

    def test_minimal_poor_answer_still_gets_a_guiding_question(self) -> None:
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
                question="Why is washing hands important?",
                student_response="Because it is clean.",
            )

        self.assertFalse(decision["accepted"])
        self.assertEqual(decision["status"], "needs_prompt")
        self.assertIn("Because it is clean", decision["examiner_reply"])

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

    def test_generic_follow_up_is_rewritten_to_reference_student_response(self) -> None:
        crew = object.__new__(EducationCrew)
        crew.subject = "test"
        crew.rubric_name = "test"
        crew.session_id = None
        crew.dialogue_manager = None
        crew.session_manager = None
        crew.llm = _GenericUnrelatedFollowUpLlm()
        crew._rubric_summary = lambda: ""  # type: ignore[method-assign]

        with patch("crew_orchestrator._retrieve_vector_context", return_value=""):
            decision = crew.evaluate_oral_turn(
                question="What are the children doing in the picture?",
                student_response="I like ice cream.",
            )

        self.assertFalse(decision["accepted"])
        self.assertIn("I like ice cream", decision["examiner_reply"])
        self.assertTrue(
            any(
                marker in decision["examiner_reply"].lower()
                for marker in ("connect to the situation", "bring your answer back", "answer more directly")
            )
        )
        self.assertNotEqual(decision["examiner_reply"], "Can you add another detail?")

    def test_fast_guiding_question_for_partial_action_is_not_generic(self) -> None:
        crew = object.__new__(EducationCrew)
        reply = crew._adaptive_follow_up_question(
            question="Can you describe what the children in the picture are doing and why it might be important?",
            response="washing head",
            reason="The response is short and may need one more reason, example, or visible detail.",
        )

        self.assertIn("washing head", reply)
        self.assertNotIn("Can you add one reason, example, or visible detail", reply)
        self.assertTrue(
            any(marker in reply.lower() for marker in ("exactly", "visible detail", "correct or complete"))
        )

    def test_reason_question_gets_reason_specific_guidance(self) -> None:
        crew = object.__new__(EducationCrew)
        reply = crew._adaptive_follow_up_question(
            question="Why is it important for the children to wash their hands?",
            response="clean",
            reason="The response is short.",
        )

        self.assertIn("clean", reply)
        self.assertNotIn("Can you add one reason, example, or visible detail", reply)
        self.assertNotIn("What could happen if the people in the picture did not do this properly", reply)
        self.assertTrue(
            any(
                marker in reply.lower()
                for marker in ("important", "visible clue", "why it matters", "explain why")
            )
        )

    def test_fast_evaluator_rejects_long_answer_unrelated_to_visual_context(self) -> None:
        crew = object.__new__(EducationCrew)
        decision = crew._fast_oral_turn_decision(
            question=(
                "Visual stimulus facts: Children are washing their hands at a sink before eating.\n\n"
                "Question: Why is this action important?"
            ),
            response="I like ice cream because it is sweet and cold.",
            attempt_number=1,
            max_attempts=2,
        )

        self.assertFalse(decision["accepted"])
        self.assertTrue(
            any(
                marker in decision["examiner_reply"].lower()
                for marker in ("situation", "question", "scene")
            )
        )

    def test_fast_evaluator_guides_brief_answer_related_to_visual_context(self) -> None:
        crew = object.__new__(EducationCrew)
        decision = crew._fast_oral_turn_decision(
            question=(
                "Visual stimulus facts: Children are washing their hands at a sink before eating.\n\n"
                "Question: Why is this action important?"
            ),
            response="They are washing their hands to stay clean before eating.",
            attempt_number=1,
            max_attempts=2,
        )

        self.assertFalse(decision["accepted"])
        self.assertTrue(
            any(
                marker in decision["examiner_reply"].lower()
                for marker in ("action you mean", "explain why", "what exactly")
            )
        )

    def test_fast_evaluator_accepts_strong_answer_related_to_visual_context(self) -> None:
        crew = object.__new__(EducationCrew)
        decision = crew._fast_oral_turn_decision(
            question=(
                "Visual stimulus facts: Children are washing their hands at a sink before eating.\n\n"
                "Question: Why is this action important?"
            ),
            response=(
                "They are washing their hands at the sink before eating because it keeps "
                "germs away and helps everyone stay healthy."
            ),
            attempt_number=1,
            max_attempts=2,
        )

        self.assertTrue(decision["accepted"])

    def test_guidance_prompt_instructs_examiner_to_adapt_to_student_response(self) -> None:
        crew = object.__new__(EducationCrew)
        crew.subject = "test"
        crew.rubric_name = "test"
        crew.session_id = None
        crew.dialogue_manager = None
        crew.session_manager = None
        crew.llm = _GenericUnrelatedFollowUpLlm()
        crew._rubric_summary = lambda: ""  # type: ignore[method-assign]

        with patch("crew_orchestrator._retrieve_vector_context", return_value=""):
            crew.evaluate_oral_turn(
                question="Why is washing hands important?",
                student_response="Because it is clean.",
            )

        self.assertIn("Make it adaptive to the student's first response", crew.llm.prompt)
        self.assertIn("briefly refer to what the student said", crew.llm.prompt)


if __name__ == "__main__":
    unittest.main()
