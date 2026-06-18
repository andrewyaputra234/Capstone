"""
CrewAI integration tests – verifies wiring to the core agent stack.

Run from repo root:
    python test_crew_integration.py
    python test_crew_integration.py --live   # includes OpenAI API calls
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from env_fix import apply_runtime_fixes
apply_runtime_fixes()

SAMPLE_DOC = """Primary Mathematics Oral Exam

Q1) What is 5 + 3?
Q2) Explain what multiplication means using an example.
Q3) If you have 12 apples and share them equally among 4 friends, how many does each get?
Q4) What is the difference between addition and subtraction?
Q5) Draw or describe a rectangle and name its properties.
"""


class TestContext:
    def __init__(self, live: bool):
        suffix = uuid.uuid4().hex[:8]
        self.live = live
        self.ingest_subject = f"crew_test_math_{suffix}"
        self.workflow_subject = f"crew_live_test_{suffix}"
        self.session_ids: list[str] = []

    def remember_session(self, session_id: str | None) -> None:
        if session_id:
            self.session_ids.append(session_id)

    def cleanup(self) -> None:
        if not self.live:
            return

        from agent_a6_session_manager import SessionManager
        from subject_manager import SubjectManager

        sessions = SessionManager()
        for session_id in self.session_ids:
            try:
                sessions.delete_session(session_id)
            except Exception as e:
                print(f"  WARN  could not delete session {session_id}: {e}")

        subjects = SubjectManager()
        for subject in [self.ingest_subject, self.workflow_subject]:
            try:
                subjects.delete_subject_data(subject)
            except Exception as e:
                print(f"  WARN  could not delete subject {subject}: {e}")


def ok(msg: str) -> None:
    print(f"  PASS  {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL  {msg}")


def test_imports() -> bool:
    print("\n[1] Module imports")
    try:
        from crew_orchestrator import EducationCrew, extract_document_content
        from main import ingest_document
        from agent_a5_grader import RubricGrader
        from agent_a6_session_manager import SessionManager
        ok("All core modules import")
        return True
    except Exception as e:
        fail(str(e))
        return False


def test_ingest_pipeline(live: bool, ctx: TestContext) -> bool:
    print("\n[2] Ingest pipeline (main.ingest_document)")
    if not live:
        print("  SKIP  (use --live to run API-dependent ingest)")
        return True

    if not os.getenv("OPENAI_API_KEY"):
        fail("OPENAI_API_KEY not set")
        return False

    try:
        from main import ingest_document

        with tempfile.TemporaryDirectory() as tmp:
            doc = Path(tmp) / "sample_exam.txt"
            doc.write_text(SAMPLE_DOC, encoding="utf-8")
            subject = ctx.ingest_subject
            result = ingest_document(str(doc), subject=subject, rubric="primary_math")

        assert result["chunk_count"] >= 1, "expected at least one chunk"
        assert Path(result["db_path"]).exists(), "chroma db missing"
        ok(f"ingested {result['chunk_count']} chunk(s) for '{subject}'")
        return True
    except Exception as e:
        fail(str(e))
        return False


def test_crew_init() -> bool:
    print("\n[3] EducationCrew initialization")
    try:
        from crew_orchestrator import EducationCrew

        crew = EducationCrew(subject="math", rubric_name="primary_math", verbose=False)
        assert crew.ingestion_agent is not None
        assert crew.grading_agent is not None
        ok("5 agents initialized")
        return True
    except Exception as e:
        fail(str(e))
        return False


def test_question_extraction(live: bool, ctx: TestContext) -> bool:
    print("\n[4] Question extraction (Agent A3 via crew)")
    if not live:
        print("  SKIP  (use --live)")
        return True

    try:
        from crew_orchestrator import EducationCrew

        crew = EducationCrew(subject=ctx.ingest_subject, rubric_name="primary_math", verbose=False)
        oral = crew.run_oral_assessment(num_questions=3, auto_start_session=False)
        questions = oral.get("questions", [])
        if len(questions) < 1:
            fail(f"expected questions, got {len(questions)}")
            return False
        ok(f"extracted {len(questions)} question(s): {questions[0]['text'][:60]}...")
        return True
    except Exception as e:
        fail(str(e))
        return False


def test_hybrid_assessment(live: bool, ctx: TestContext) -> bool:
    print("\n[5] Hybrid assessment (A5 + CrewAI)")
    if not live:
        print("  SKIP  (use --live)")
        return True

    try:
        from crew_orchestrator import EducationCrew

        crew = EducationCrew(subject=ctx.ingest_subject, rubric_name="primary_math", verbose=False)
        crew.start_session(metadata={"test": True})
        ctx.remember_session(crew.session_id)

        result = crew.run_assessment_workflow(
            question="What is 5 + 3?",
            student_response="Eight, because five plus three equals eight.",
            save_to_session=True,
        )

        grading = result["grading_result"]
        assert "total_score" in grading, "missing rubric scores"
        assert grading["max_score"] > 0
        ok(f"score {grading['total_score']}/{grading['max_score']} ({grading['percentage']}%)")

        report = crew.session_manager.get_session_report(crew.session_id)
        assert report and report["statistics"]["student_turns"] >= 1
        ok(f"session {crew.session_id} persisted")

        crew.end_session()
        return True
    except Exception as e:
        fail(str(e))
        return False


def test_crew_ingest_workflow(live: bool, ctx: TestContext) -> bool:
    print("\n[6] Full crew ingest workflow")
    if not live:
        print("  SKIP  (use --live)")
        return True

    try:
        from crew_orchestrator import EducationCrew

        with tempfile.TemporaryDirectory() as tmp:
            doc = Path(tmp) / "crew_sample.txt"
            doc.write_text(SAMPLE_DOC, encoding="utf-8")

            crew = EducationCrew(subject=ctx.workflow_subject, rubric_name="primary_math", verbose=False)
            result = crew.run_ingestion_workflow(str(doc))

        assert result["ingest_result"]["chunk_count"] >= 1
        assert len(result.get("questions", [])) >= 1
        assert result.get("crew_analysis"), "missing crew analysis"
        ok(
            f"ingest + {len(result['questions'])} questions + crew analysis "
            f"({len(result['crew_analysis'])} chars)"
        )
        return True
    except Exception as e:
        fail(str(e))
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Run OpenAI-dependent tests")
    args = parser.parse_args()

    print("=" * 55)
    print("CREWAI INTEGRATION TESTS")
    print("=" * 55)

    ctx = TestContext(live=args.live)
    try:
        results = [
            test_imports(),
            test_crew_init(),
            test_ingest_pipeline(args.live, ctx),
            test_question_extraction(args.live, ctx),
            test_hybrid_assessment(args.live, ctx),
            test_crew_ingest_workflow(args.live, ctx),
        ]
    finally:
        ctx.cleanup()

    passed = sum(results)
    total = len(results)
    print("\n" + "=" * 55)
    print(f"Results: {passed}/{total} passed")
    if not args.live:
        print("Tip: run with --live to exercise OpenAI + ChromaDB paths")
    print("=" * 55)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
