"""Regression test for preserving a usable, clearly marked result during AI outages."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from agent_a5_grader import RubricGrader
from rubric_engine import RubricEngine, RubricScore


class GradingResilienceTests(unittest.TestCase):
    def test_reading_step_scores_only_selected_reading_criterion(self) -> None:
        engine = RubricEngine()
        engine.current_rubric = {
            "criteria": [
                {"name": "Reading Aloud Delivery", "description": "Fluency and pronunciation", "max_score": 10, "levels": {}},
                {"name": "Picture Discussion", "description": "Relevant ideas about the image", "max_score": 20, "levels": {}},
            ]
        }
        engine._evaluate_criterion = lambda **kwargs: {
            "score": 7,
            "feedback": "Clear delivery overall.",
            "evidence": "Submitted recording",
        }

        scores = engine.score_answer(
            question="Reading-aloud submission.",
            answer="The student transcript.",
            criterion_names=["Reading Aloud Delivery"],
            visual_context="Audio evidence: submitted recording and delivery indicators.",
        )

        self.assertEqual([score.criterion_name for score in scores], ["Reading Aloud Delivery"])
        self.assertEqual(scores[0].max_score, 10)

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
