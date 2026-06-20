"""Regression test for preserving a usable, clearly marked result during AI outages."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from agent_a5_grader import RubricGrader
from rubric_engine import RubricScore


class GradingResilienceTests(unittest.TestCase):
    def test_feedback_outage_returns_marked_provisional_grade(self) -> None:
        grader = RubricGrader(rubric_name="psle_oral_english")
        grader.rubric_engine.score_answer = lambda *args, **kwargs: [
            RubricScore(
                criterion_name="Idea Development",
                score=4,
                max_score=8,
                feedback="The answer needs one supporting detail.",
                evidence="A short answer",
                source="fallback",
            )
        ]
        grader._get_llm = lambda: (_ for _ in ()).throw(RuntimeError("service unavailable"))

        result = grader.generate_tutoring_feedback("Describe the picture.", "A short answer")

        self.assertEqual(result["scoring_source"], "fallback")
        self.assertIn("live AI coaching message was unavailable", result["tutoring_feedback"])
        self.assertEqual(result["scores"][0]["source"], "fallback")


if __name__ == "__main__":
    unittest.main()
