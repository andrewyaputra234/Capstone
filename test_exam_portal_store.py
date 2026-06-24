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
        self.rubrics_dir = Path(self.temp_dir.name) / "rubrics"
        self.original_assignments_path = store.ASSIGNMENTS_PATH
        self.original_users_path = store.USERS_PATH
        self.original_rubrics_dir = store.RUBRICS_DIR
        store.ASSIGNMENTS_PATH = self.assignments_path
        store.USERS_PATH = self.users_path
        store.RUBRICS_DIR = self.rubrics_dir
        self.rubrics_dir.mkdir()
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
        store.RUBRICS_DIR = self.original_rubrics_dir
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

    def test_assignment_preserves_examiner_approved_question_text(self) -> None:
        assignment = store.create_assignment(
            student={"id": "s1", "name": "Ada Student"},
            title="Picture discussion",
            subject="assignment_s1_test",
            rubric="psle_oral_english",
            visual={},
            questions=[
                {
                    "id": "q1",
                    "text": "What groceries is the person carrying, and why?",
                    "generated_text": "Describe the picture.",
                    "edited_by_examiner": True,
                }
            ],
            reading=None,
            examiner_id="e1",
        )

        question = assignment["questions"][0]
        self.assertEqual(question["text"], "What groceries is the person carrying, and why?")
        self.assertEqual(question["generated_text"], "Describe the picture.")
        self.assertTrue(question["edited_by_examiner"])

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

    def test_results_are_released_only_after_every_grade_is_examiner_verified(self) -> None:
        assignment = store.create_assignment(
            student={"id": "s1", "name": "Ada Student"},
            title="Complete oral assessment",
            subject="assignment_s1_test",
            rubric="psle_oral_english",
            visual={},
            questions=[{"id": "q1", "text": "What do you see?"}],
            reading={"name": "passage.txt", "text": "A short passage."},
            examiner_id="e1",
        )
        grading = {
            "scores": [{"criterion": "Delivery", "score": 6, "max_score": 10}],
            "total_score": 6,
            "max_score": 10,
            "percentage": 60,
        }
        store.save_reading_submission(
            assignment["assignment_id"], transcript="A short passage.", response_mode="voice", grading_result=grading
        )
        result = store.add_assessment_result(
            assignment["assignment_id"],
            question={"id": "q1", "text": "What do you see?"},
            student_response="I see a family at the park.",
            grading_result=grading,
            session_id="session1",
        )
        store.mark_assignment_status(assignment["assignment_id"], "completed")

        with self.assertRaises(ValueError):
            store.release_final_results(assignment["assignment_id"], "e1")

        store.apply_reading_examiner_review(assignment["assignment_id"], {"Delivery": 7}, "Clearer on replay.", "e1")
        store.apply_examiner_review(assignment["assignment_id"], result["result_id"], {"Delivery": 8}, "Relevant response.", "e1")
        released = store.release_final_results(assignment["assignment_id"], "e1")

        self.assertIsNotNone(released["results_released_at"])
        self.assertEqual(released["results_released_by"], "e1")
        self.assertEqual(released["reading_submission"]["final_grading"]["total_score"], 7)
        self.assertEqual(released["results"][0]["final_grading"]["total_score"], 8)

    def test_student_cannot_submit_a_question_or_reading_twice(self) -> None:
        assignment = store.create_assignment(
            student={"id": "s1", "name": "Ada Student"},
            title="Single attempt",
            subject="assignment_s1_test",
            rubric="psle_oral_english",
            visual={},
            questions=[{"id": "q1", "text": "What do you see?"}],
            reading={"name": "passage.txt", "text": "A short passage."},
            examiner_id="e1",
        )
        store.save_reading_submission(assignment["assignment_id"], transcript="A short passage.", response_mode="text")
        with self.assertRaises(ValueError):
            store.save_reading_submission(assignment["assignment_id"], transcript="A replacement.", response_mode="text")

        result_args = {
            "question": {"id": "q1", "text": "What do you see?"},
            "student_response": "I see a park.",
            "grading_result": {"scores": [], "total_score": 0, "max_score": 0, "percentage": 0},
            "session_id": "session1",
        }
        store.add_assessment_result(assignment["assignment_id"], **result_args)
        with self.assertRaises(ValueError):
            store.add_assessment_result(assignment["assignment_id"], **result_args)

    def test_one_guidance_prompt_is_preserved_with_the_final_result(self) -> None:
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
        question = {"id": "q1", "text": "What do you see?"}
        store.save_guidance_attempt(
            assignment["assignment_id"],
            question=question,
            original_response="I like ice cream.",
            follow_up_question="What can you see in the picture?",
            reason="The first response was unrelated to the image.",
            response_mode="voice",
            audio_path="data/sessions/first.wav",
            transcription_path="data/sessions/first.json",
            delivery_indicators={"status": "available", "words_per_minute": 90},
        )
        with self.assertRaises(ValueError):
            store.save_guidance_attempt(
                assignment["assignment_id"],
                question=question,
                original_response="Another attempt",
                follow_up_question="A second prompt is not allowed.",
            )

        store.add_assessment_result(
            assignment["assignment_id"],
            question=question,
            student_response="First response: I like ice cream.\n\nResponse after examiner follow-up: I can see children playing.",
            grading_result={"scores": [], "total_score": 0, "max_score": 0, "percentage": 0},
            session_id="session1",
            follow_up_response="I can see children playing.",
        )
        saved = store.get_assignment(assignment["assignment_id"])
        self.assertEqual(saved["guidance_attempts"], {})
        guidance = saved["results"][0]["guided_attempt"]
        self.assertEqual(guidance["original_response"], "I like ice cream.")
        self.assertEqual(guidance["follow_up_response"], "I can see children playing.")
        self.assertEqual(guidance["original_audio_path"], "data/sessions/first.wav")
        self.assertEqual(guidance["original_delivery_indicators"]["words_per_minute"], 90)

    def test_reading_submission_saves_voice_evidence_and_provisional_grade(self) -> None:
        assignment = store.create_assignment(
            student={"id": "s1", "name": "Ada Student"},
            title="Picture discussion",
            subject="assignment_s1_test",
            rubric="psle_oral_english",
            visual={},
            questions=[{"id": "q1", "text": "What do you see?"}],
            reading={"name": "passage.txt", "text": "A short passage."},
            examiner_id="e1",
        )
        saved = store.save_reading_submission(
            assignment["assignment_id"],
            transcript="A short passage.",
            response_mode="voice",
            audio_path="data/sessions/reading.wav",
            transcription_path="data/sessions/reading.json",
            delivery_indicators={"status": "available", "words_per_minute": 100},
            grading_result={"total_score": 8, "max_score": 10, "percentage": 80, "scores": []},
            crew_analysis="Recorded reading feedback.",
        )
        submission = saved["reading_submission"]
        self.assertEqual(submission["transcript"], "A short passage.")
        self.assertEqual(submission["audio_path"], "data/sessions/reading.wav")
        self.assertEqual(submission["final_grading"]["total_score"], 8)
        self.assertEqual(saved["results"], [])

    def test_only_psle_oral_and_valid_custom_oral_rubrics_are_listed(self) -> None:
        custom_rubric = {
            "name": "School English Oral Rubric",
            "criteria": [
                {
                    "name": "Response relevance",
                    "max_points": "5",
                    "rubric_levels": [
                        {"level": "Strong", "points": "5", "description": "Direct and relevant"},
                        {"level": "Developing", "points": 2, "description": "Partly relevant"},
                        {"level": "No evidence", "points": 0, "description": "No relevant response"},
                    ],
                }
            ],
        }
        saved_name = store.save_english_oral_rubric(
            "School Oral 2026.json", json.dumps(custom_rubric).encode("utf-8")
        )
        self.assertEqual(saved_name, "examiner_psle_oral_school_oral_2026")
        self.assertEqual(
            store.list_english_oral_rubrics(),
            ["psle_oral_english", "examiner_psle_oral_school_oral_2026"],
        )
        self.assertEqual(store.rubric_display_name(saved_name), "School English Oral Rubric")
        saved_data = json.loads((self.rubrics_dir / f"{saved_name}.json").read_text(encoding="utf-8"))
        self.assertEqual(saved_data["criteria"][0]["max_points"], 5)
        self.assertEqual(saved_data["criteria"][0]["rubric_levels"][0]["points"], 5)
        self.assertEqual(
            store.save_english_oral_rubric("School Oral 2026.json", json.dumps(custom_rubric).encode("utf-8")),
            "examiner_psle_oral_school_oral_2026_2",
        )
        with self.assertRaises(ValueError):
            store.save_english_oral_rubric("invalid.json", b'{"criteria": []}')

    def test_common_wrapped_rubric_schema_is_normalised(self) -> None:
        exported_rubric = {
            "title": "School Oral Conversation Rubric",
            "rubric": {
                "assessment_criteria": [
                    {
                        "title": "Visual relevance",
                        "weight": "6",
                        "performance_levels": [
                            {"level": "Strong", "value": "6", "description": "Accurate picture details"},
                            {"level": "Beginning", "value": 0, "description": "No relevant detail"},
                        ],
                    }
                ]
            },
        }
        name = store.save_english_oral_rubric("exported rubric.json", json.dumps(exported_rubric).encode("utf-8"))
        saved = json.loads((self.rubrics_dir / f"{name}.json").read_text(encoding="utf-8"))
        criterion = saved["criteria"][0]
        self.assertEqual(saved["name"], "School Oral Conversation Rubric")
        self.assertEqual(criterion["name"], "Visual relevance")
        self.assertEqual(criterion["max_points"], 6)
        self.assertEqual(criterion["rubric_levels"][0]["points"], 6)

    def test_psle_component_and_band_rubric_is_normalised(self) -> None:
        psle_rubric = {
            "exam": "Primary School Leaving Examination (PSLE)",
            "subject": "English Language",
            "component": "Oral Communication (Paper 4)",
            "rubric": {
                "reading_aloud": {
                    "component_weight": 10,
                    "assessment_criteria": [{"criterion": "Pronunciation", "focus": "Clear sounds"}],
                    "bands": [
                        {"marks": "9-10", "performance_level": "Excellent", "descriptors": ["Clear reading"]},
                        {"marks": "1-2", "performance_level": "Very Weak", "descriptors": ["Unclear reading"]},
                    ],
                },
                "stimulus_based_conversation": {
                    "component_weight": 20,
                    "assessment_criteria": [{"criterion": "Personal Response", "focus": "Relevant ideas"}],
                    "bands": [
                        {"marks": "17-20", "performance_level": "Excellent", "descriptors": ["Relevant ideas"]},
                        {"marks": "1-4", "performance_level": "Very Weak", "descriptors": ["No relevant idea"]},
                    ],
                },
            },
        }
        name = store.save_english_oral_rubric("PSLE band rubric.json", json.dumps(psle_rubric).encode("utf-8"))
        saved = json.loads((self.rubrics_dir / f"{name}.json").read_text(encoding="utf-8"))
        self.assertEqual(
            [(criterion["name"], criterion["max_points"]) for criterion in saved["criteria"]],
            [("Reading Aloud Delivery", 10), ("Stimulus-Based Conversation", 20)],
        )
        self.assertEqual(saved["criteria"][1]["rubric_levels"][0]["points"], 20)


if __name__ == "__main__":
    unittest.main()
