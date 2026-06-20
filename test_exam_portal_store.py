"""Regression checks for the persisted examiner/student portal workflow."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import exam_portal_store as store


class ExamPortalStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.assignments_path = Path(self.temp_dir.name) / "assignments.json"
        self.users_path = Path(self.temp_dir.name) / "users.json"
        self.original_assignments_path = store.ASSIGNMENTS_PATH
        self.original_users_path = store.USERS_PATH
        store.ASSIGNMENTS_PATH = self.assignments_path
        store.USERS_PATH = self.users_path
        self.users_path.write_text(
            json.dumps(
                {
                    "students": [{"id": "s1", "name": "Ada Student"}],
                    "examiners": [{"id": "e1", "name": "Evan Examiner"}],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        store.ASSIGNMENTS_PATH = self.original_assignments_path
        store.USERS_PATH = self.original_users_path
        self.temp_dir.cleanup()

    def test_registered_users_can_be_listed_and_authenticated(self) -> None:
        self.assertEqual(store.list_students(), [{"id": "s1", "name": "Ada Student"}])
        self.assertEqual(store.authenticate("student", "s1"), {"id": "s1", "name": "Ada Student"})
        self.assertEqual(store.authenticate("examiner", "e1"), {"id": "e1", "name": "Evan Examiner"})
        self.assertIsNone(store.authenticate("student", "unknown"))

    def test_legacy_assignment_map_remains_readable(self) -> None:
        self.assignments_path.write_text(
            json.dumps({"s1": {"subject": "old_subject", "rubric": "old_rubric"}}), encoding="utf-8"
        )
        assignment = store.get_active_assignment("s1")
        self.assertIsNotNone(assignment)
        self.assertEqual(assignment["assignment_id"], "legacy-s1")
        self.assertEqual(assignment["rubric"], "old_rubric")

    def test_ai_grade_is_preserved_when_examiner_adjusts_final_grade(self) -> None:
        assignment = store.create_assignment(
            student={"id": "s1", "name": "Ada Student"},
            title="Picture discussion",
            subject="assignment_s1_test",
            rubric="psle_oral_english",
            visual={"name": "picture.png", "path": "data/picture.png"},
            questions=[{"id": "q1", "text": "What do you see?"}],
            reading=None,
            examiner_id="e1",
        )
        grading = {
            "scores": [
                {"criterion": "Relevance", "score": 4, "max_score": 8},
                {"criterion": "Reading delivery", "score": 0, "max_score": 0},
            ],
            "total_score": 4,
            "max_score": 8,
            "percentage": 50.0,
        }
        result = store.add_assessment_result(
            assignment["assignment_id"],
            question={"id": "q1", "text": "What do you see?"},
            student_response="I see children playing.",
            grading_result=grading,
            session_id="session1",
        )
        updated = store.apply_examiner_review(
            assignment["assignment_id"],
            result["result_id"],
            {"Relevance": 7},
            "More detail was provided than the AI credited.",
            "e1",
        )
        saved_result = updated["results"][0]
        self.assertEqual(saved_result["ai_grading"]["total_score"], 4)
        self.assertEqual(saved_result["final_grading"]["total_score"], 7)
        self.assertEqual(saved_result["final_grading"]["percentage"], 87.5)
        self.assertEqual(saved_result["examiner_review"]["reviewed_by"], "e1")

    def test_completed_assignment_is_not_returned_as_active(self) -> None:
        assignment = store.create_assignment(
            student={"id": "s1", "name": "Ada Student"},
            title="Picture discussion",
            subject="assignment_s1_test",
            rubric="psle_oral_english",
            visual={},
            questions=[{"id": "q1", "text": "What do you see?"}],
            reading=None,
            examiner_id="e1",
        )
        store.mark_assignment_status(assignment["assignment_id"], "completed")
        self.assertIsNone(store.get_active_assignment("s1"))


if __name__ == "__main__":
    unittest.main()
