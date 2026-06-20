"""Small, file-backed store for examiner assignments and reviewed results.

The Streamlit application is deliberately deployed as a local prototype, so a
JSON store is enough for the current single-machine workflow. Keeping this
logic outside the UI makes the assignment and review lifecycle testable and
keeps student records separate from subject-level ingestion data.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ASSIGNMENTS_PATH = DATA_DIR / "student_assignments.json"
USERS_PATH = DATA_DIR / "users.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(
    path: Path,
    fallback: dict[str, Any],
    *,
    fail_on_invalid: bool = False,
) -> dict[str, Any]:
    if not path.exists():
        return copy.deepcopy(fallback)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        if fail_on_invalid:
            raise ValueError(f"Could not read {path.name}; the file was not changed.") from error
        return copy.deepcopy(fallback)
    return value if isinstance(value, dict) else copy.deepcopy(fallback)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    """Atomically replace a data file so a restart cannot leave partial JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink(missing_ok=True)


def _legacy_assignment(student_id: str, details: dict[str, Any]) -> dict[str, Any]:
    """Make the earlier {student_id: {subject, rubric}} file readable."""
    return {
        "assignment_id": f"legacy-{student_id}",
        "student_id": student_id,
        "student_name": f"Student {student_id}",
        "title": details.get("subject", "Untitled assessment"),
        "subject": details.get("subject", ""),
        "rubric": details.get("rubric", ""),
        "status": "assigned",
        "created_at": None,
        "updated_at": None,
        "visual": {},
        "reading": None,
        "questions": [],
        "reading_completed_at": None,
        "results": [],
    }


def load_assignments() -> dict[str, Any]:
    """Return the v2 assignment store, converting the earlier simple map in memory."""
    raw = _read_json(
        ASSIGNMENTS_PATH,
        {"version": 2, "assignments": {}},
        fail_on_invalid=True,
    )
    if raw.get("version") == 2 and isinstance(raw.get("assignments"), dict):
        return raw

    assignments: dict[str, dict[str, Any]] = {}
    for student_id, details in raw.items():
        if isinstance(details, dict) and "subject" in details and "rubric" in details:
            record = _legacy_assignment(str(student_id), details)
            assignments[record["assignment_id"]] = record
    return {"version": 2, "assignments": assignments}


def save_assignments(store: dict[str, Any]) -> None:
    _write_json(ASSIGNMENTS_PATH, store)


def load_users() -> dict[str, list[dict[str, str]]]:
    users = _read_json(USERS_PATH, {"students": [], "examiners": []})
    students = users.get("students") if isinstance(users.get("students"), list) else []
    examiners = users.get("examiners") if isinstance(users.get("examiners"), list) else []
    return {"students": students, "examiners": examiners}


def list_students() -> list[dict[str, str]]:
    students = []
    for user in load_users()["students"]:
        user_id = str(user.get("id", "")).strip()
        if user_id:
            students.append({"id": user_id, "name": str(user.get("name") or user_id)})
    return sorted(students, key=lambda student: (student["name"].lower(), student["id"]))


def authenticate(role: str, user_id: str) -> dict[str, str] | None:
    group = "examiners" if role.lower() == "examiner" else "students"
    normalized_id = user_id.strip()
    for user in load_users()[group]:
        if str(user.get("id", "")).strip() == normalized_id:
            return {"id": normalized_id, "name": str(user.get("name") or normalized_id)}
    return None


def create_assignment(
    *,
    student: dict[str, str],
    title: str,
    subject: str,
    rubric: str,
    visual: dict[str, Any],
    questions: list[dict[str, Any]],
    reading: dict[str, Any] | None,
    examiner_id: str,
) -> dict[str, Any]:
    assignment_id = uuid.uuid4().hex[:12]
    timestamp = _now()
    record = {
        "assignment_id": assignment_id,
        "student_id": student["id"],
        "student_name": student["name"],
        "title": title.strip() or "Untitled assessment",
        "subject": subject,
        "rubric": rubric,
        "status": "assigned",
        "created_at": timestamp,
        "updated_at": timestamp,
        "assigned_by": examiner_id,
        "visual": copy.deepcopy(visual),
        "reading": copy.deepcopy(reading) if reading else None,
        "questions": copy.deepcopy(questions[:3]),
        "reading_completed_at": None,
        "results": [],
    }
    store = load_assignments()
    store["assignments"][assignment_id] = record
    save_assignments(store)
    return record


def get_assignment(assignment_id: str) -> dict[str, Any] | None:
    return load_assignments()["assignments"].get(assignment_id)


def list_assignments(student_id: str | None = None) -> list[dict[str, Any]]:
    records = list(load_assignments()["assignments"].values())
    if student_id is not None:
        records = [record for record in records if record.get("student_id") == student_id]
    return sorted(records, key=lambda record: record.get("created_at") or "", reverse=True)


def get_active_assignment(student_id: str) -> dict[str, Any] | None:
    records = [
        record
        for record in list_assignments(student_id)
        if record.get("status") in {"assigned", "in_progress"}
    ]
    return records[0] if records else None


def _update_assignment(assignment_id: str, callback) -> dict[str, Any]:
    store = load_assignments()
    record = store["assignments"].get(assignment_id)
    if not record:
        raise KeyError(f"Assignment {assignment_id} was not found")
    callback(record)
    record["updated_at"] = _now()
    save_assignments(store)
    return copy.deepcopy(record)


def mark_assignment_status(assignment_id: str, status: str) -> dict[str, Any]:
    if status not in {"assigned", "in_progress", "completed", "archived"}:
        raise ValueError("Invalid assignment status")
    return _update_assignment(assignment_id, lambda record: record.update({"status": status}))


def mark_reading_completed(assignment_id: str) -> dict[str, Any]:
    return _update_assignment(
        assignment_id,
        lambda record: record.update({"reading_completed_at": record.get("reading_completed_at") or _now()}),
    )


def add_assessment_result(
    assignment_id: str,
    *,
    question: dict[str, Any],
    student_response: str,
    grading_result: dict[str, Any],
    session_id: str | None,
    crew_analysis: str = "",
    skipped: bool = False,
) -> dict[str, Any]:
    result = {
        "result_id": uuid.uuid4().hex[:12],
        "question_id": question.get("id"),
        "question": question.get("text", ""),
        "visual_context": question.get("visual_context"),
        "student_response": student_response,
        "session_id": session_id,
        "created_at": _now(),
        "skipped": skipped,
        "ai_grading": copy.deepcopy(grading_result),
        "final_grading": copy.deepcopy(grading_result),
        "examiner_review": None,
        "crew_analysis": crew_analysis,
    }

    def append_result(record: dict[str, Any]) -> None:
        record.setdefault("results", []).append(result)
        if record.get("status") == "assigned":
            record["status"] = "in_progress"

    _update_assignment(assignment_id, append_result)
    return result


def apply_examiner_review(
    assignment_id: str,
    result_id: str,
    scores: dict[str, int],
    note: str,
    examiner_id: str,
) -> dict[str, Any]:
    """Save criterion-level score changes while preserving the original AI grade."""
    def update_result(record: dict[str, Any]) -> None:
        for result in record.get("results", []):
            if result.get("result_id") != result_id:
                continue
            final_grading = copy.deepcopy(result.get("final_grading") or result.get("ai_grading") or {})
            total = 0
            maximum = 0
            for criterion in final_grading.get("scores", []):
                max_score = int(criterion.get("max_score", 0))
                name = str(criterion.get("criterion", ""))
                if name in scores:
                    requested = int(scores[name])
                    criterion["score"] = max(0, min(requested, max_score))
                total += int(criterion.get("score", 0))
                maximum += max_score
            final_grading["total_score"] = total
            final_grading["max_score"] = maximum
            final_grading["percentage"] = round(total / maximum * 100, 1) if maximum else 0
            result["final_grading"] = final_grading
            result["examiner_review"] = {
                "reviewed_at": _now(),
                "reviewed_by": examiner_id,
                "note": note.strip(),
                "score_changes": copy.deepcopy(scores),
            }
            return
        raise KeyError(f"Result {result_id} was not found")

    return _update_assignment(assignment_id, update_result)
