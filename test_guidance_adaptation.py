"""Regression checks for adaptive examiner guiding questions."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from crew_orchestrator import EducationCrew


class GuidanceAdaptationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.crew = object.__new__(EducationCrew)

    def test_follow_up_references_short_student_answer(self) -> None:
        reply = self.crew._adaptive_follow_up_question(
            "Visual stimulus facts: A nurse is helping an elderly man eat in a hospital room.\n\n"
            "Question: Why is it important to care for elderly people?",
            "It is good.",
            "The response connects to the picture but needs stronger explanation before it is ready to grade without guidance.",
        )

        self.assertIn('"It is good."', reply)
        self.assertTrue(any(marker in reply.lower() for marker in ("reason", "picture", "why", "supports")))

    def test_follow_up_asks_for_personal_link_when_prompt_needs_experience(self) -> None:
        reply = self.crew._adaptive_follow_up_question(
            "Visual stimulus facts: Children are washing their hands at a sink.\n\n"
            "Question: Have you done something similar before?",
            "They are washing hands before eating lunch.",
            "The response needs a personal response.",
        )

        self.assertIn('"They are washing hands', reply)
        self.assertTrue(any(marker in reply.lower() for marker in ("your own", "you experienced", "personal")))

    def test_follow_up_asks_for_picture_detail_when_response_has_no_visual_anchor(self) -> None:
        reply = self.crew._adaptive_follow_up_question(
            "Visual stimulus facts: A child is wearing a helmet while riding a bicycle near a park.\n\n"
            "Question: Why is safety important in this picture?",
            "Safety is very important because people can get hurt.",
            "The response needs a connection to the visual stimulus.",
        )

        self.assertIn('"Safety is very important', reply)
        self.assertTrue(any(marker in reply.lower() for marker in ("visible detail", "picture", "scene")))


if __name__ == "__main__":
    unittest.main()
