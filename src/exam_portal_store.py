"""Small, file-backed store for examiner assignments and reviewed results.

The Streamlit application is deliberately deployed as a local prototype, so a
JSON store is enough for the current single-machine workflow. Keeping this
logic outside the UI makes the assignment and review lifecycle testable and
keeps student records separate from subject-level ingestion data.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ASSIGNMENTS_PATH = DATA_DIR / "student_assignments.json"
USERS_PATH = DATA_DIR / "users.json"
RUBRICS_DIR = DATA_DIR / "rubrics"
PSLE_ORAL_RUBRIC = "psle_oral_english"
CUSTOM_ORAL_RUBRIC_PREFIX = "examiner_psle_oral_"


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
        "reading_submission": None,
        "questions": [],
        "reading_completed_at": None,
        "guidance_attempts": {},
        "results": [],
        "results_released_at": None,
        "results_released_by": None,
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


def _hash_password(password: str, salt: str | None = None) -> dict[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000)
    return {
        "password_hash": digest.hex(),
        "password_salt": salt,
        "password_algorithm": "pbkdf2_sha256",
    }


def _password_matches(user: dict[str, Any], supplied_password: str) -> bool:
    password_hash = str(user.get("password_hash", ""))
    password_salt = str(user.get("password_salt", ""))
    if password_hash and password_salt:
        candidate = _hash_password(supplied_password, password_salt)["password_hash"]
        return hmac.compare_digest(password_hash, candidate)

    # Legacy compatibility for the original local demo register.
    registered_password = str(user.get("password", ""))
    return bool(registered_password) and hmac.compare_digest(registered_password, supplied_password)


def register_student(student_id: str, password: str, name: str = "") -> dict[str, str]:
    """Create a local student account in the prototype user register."""
    normalized_id = student_id.strip()
    normalized_name = name.strip() or f"Student {normalized_id}"
    normalized_password = password.strip()

    if not normalized_id:
        raise ValueError("Student ID is required.")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,40}", normalized_id):
        raise ValueError("Student ID can use letters, numbers, dots, underscores, or hyphens only.")
    if not normalized_password:
        raise ValueError("Password is required.")
    if len(normalized_password) < 3:
        raise ValueError("Password must be at least 3 characters.")

    users = _read_json(USERS_PATH, {"students": [], "examiners": []}, fail_on_invalid=True)
    students = users.get("students") if isinstance(users.get("students"), list) else []
    examiners = users.get("examiners") if isinstance(users.get("examiners"), list) else []

    for user in students:
        if str(user.get("id", "")).strip().lower() == normalized_id.lower():
            raise ValueError("A student with this ID already exists.")

    record = {
        "id": normalized_id,
        "name": normalized_name,
        "registered_at": _now(),
        **_hash_password(normalized_password),
    }
    users["students"] = [*students, record]
    users["examiners"] = examiners
    _write_json(USERS_PATH, users)
    return {"id": normalized_id, "name": normalized_name}


def authenticate(role: str, user_id: str, password: str) -> dict[str, str] | None:
    """Authenticate a local portal user against the role-specific register.

    This is deliberately small-scale prototype authentication. Passwords are kept
    in the local development register and must be replaced by hashed credentials
    before any public deployment.
    """
    group = "examiners" if role.lower() == "examiner" else "students"
    normalized_id = user_id.strip()
    supplied_password = password.strip()
    for user in load_users()[group]:
        if (
            str(user.get("id", "")).strip() == normalized_id
            and _password_matches(user, supplied_password)
        ):
            return {"id": normalized_id, "name": str(user.get("name") or normalized_id)}
    return None


def list_english_oral_rubrics() -> list[str]:
    """Return only the built-in PSLE oral rubric and examiner-added oral rubrics."""
    custom_rubrics = []
    if RUBRICS_DIR.exists():
        custom_rubrics = [
            path.stem
            for path in RUBRICS_DIR.glob(f"{CUSTOM_ORAL_RUBRIC_PREFIX}*.json")
        ]
    return [PSLE_ORAL_RUBRIC, *sorted(custom_rubrics)]


def rubric_display_name(rubric_name: str) -> str:
    if rubric_name == PSLE_ORAL_RUBRIC:
        return "PSLE English Oral (built-in)"
    data = _read_json(RUBRICS_DIR / f"{rubric_name}.json", {})
    return str(data.get("name") or rubric_name.replace("_", " ").title())


def _mark_band_score(value: Any, maximum: int) -> int:
    """Convert a band label such as '17-20' into its rubric score ceiling."""
    numbers = [int(number) for number in re.findall(r"\d+", str(value))]
    return min(max(numbers), maximum) if numbers else 0


def _normalise_component_rubric(data: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    """Convert PSLE-style component/band rubrics into RubricEngine criteria."""
    criteria = []
    for component_key, component in components.items():
        if not isinstance(component, dict):
            continue
        raw_weight = component.get("component_weight", component.get("max_points", component.get("max_score")))
        try:
            maximum = int(raw_weight)
        except (TypeError, ValueError):
            continue
        if maximum <= 0 or not isinstance(component.get("bands"), list):
            continue

        focus_lines = []
        for focus in component.get("assessment_criteria", []):
            if isinstance(focus, dict):
                title = str(focus.get("criterion") or focus.get("name") or "").strip()
                detail = str(focus.get("focus") or focus.get("description") or "").strip()
                focus_lines.append(": ".join(part for part in (title, detail) if part))
        levels = []
        for band in component["bands"]:
            if not isinstance(band, dict):
                continue
            score = _mark_band_score(band.get("marks", band.get("score", band.get("points"))), maximum)
            descriptors = band.get("descriptors", [])
            description = " ".join(str(item).strip() for item in descriptors if str(item).strip())
            levels.append(
                {
                    "level": str(band.get("performance_level") or band.get("level") or f"{score} points"),
                    "points": score,
                    "description": description,
                }
            )
        if not levels:
            continue
        display_name = component_key.replace("_", " ").title()
        if component_key == "reading_aloud":
            display_name = "Reading Aloud Delivery"
        elif component_key == "stimulus_based_conversation":
            display_name = "Stimulus-Based Conversation"
        description = str(component.get("description") or "").strip()
        if focus_lines:
            description = f"{description} Assessment focus: {'; '.join(focus_lines)}".strip()
        criteria.append(
            {
                "name": display_name,
                "description": description,
                "max_points": maximum,
                "rubric_levels": levels,
            }
        )

    return {
        "name": data.get("name") or f"{data.get('exam', 'PSLE')} {data.get('subject', 'English')} Oral Rubric",
        "level": data.get("level") or "Primary 6",
        "subject": data.get("subject") or "English",
        "assessment_type": data.get("component") or "English oral",
        "criteria": criteria,
    }


def _normalise_uploaded_rubric(data: Any) -> dict[str, Any]:
    """Accept common exported-rubric wrappers and convert them to our JSON schema."""
    if isinstance(data, list):
        return {"criteria": copy.deepcopy(data)}
    if not isinstance(data, dict):
        raise ValueError("The rubric file must contain a JSON object or a list of criteria.")

    normalized = copy.deepcopy(data)
    if not normalized.get("criteria"):
        component_rubric = normalized.get("rubric")
        if isinstance(component_rubric, dict) and any(
            isinstance(value, dict) and "component_weight" in value and "bands" in value
            for value in component_rubric.values()
        ):
            return _normalise_component_rubric(normalized, component_rubric)
        for wrapper_key in ("rubric", "rubric_data", "rubricData", "assessment_rubric", "assessmentRubric"):
            wrapped = normalized.get(wrapper_key)
            if isinstance(wrapped, (dict, list)):
                name = normalized.get("name") or normalized.get("title")
                normalized = _normalise_uploaded_rubric(wrapped)
                if name and not normalized.get("name"):
                    normalized["name"] = name
                break

    if not normalized.get("criteria"):
        for alternative_key in (
            "assessment_criteria", "assessmentCriteria", "grading_criteria", "gradingCriteria", "categories", "dimensions"
        ):
            alternative = normalized.get(alternative_key)
            if isinstance(alternative, (list, dict)):
                normalized["criteria"] = alternative
                break

    criteria = normalized.get("criteria")
    if isinstance(criteria, dict):
        normalized["criteria"] = [
            {"name": name, **details} if isinstance(details, dict) else {"name": name, "description": str(details)}
            for name, details in criteria.items()
        ]
    return normalized


def _normalise_criterion(criterion: dict[str, Any]) -> None:
    if not criterion.get("name"):
        criterion["name"] = criterion.get("criterion") or criterion.get("title") or criterion.get("category")
    if not criterion.get("description"):
        criterion["description"] = criterion.get("details") or criterion.get("descriptor") or ""

    if "rubricLevels" in criterion and "rubric_levels" not in criterion:
        criterion["rubric_levels"] = criterion["rubricLevels"]
    if "performanceLevels" in criterion and "performance_levels" not in criterion:
        criterion["performance_levels"] = criterion["performanceLevels"]
    if "rubric_levels" not in criterion and "levels" not in criterion:
        for alternative_key in ("performance_levels", "descriptors", "scale"):
            if alternative_key in criterion:
                criterion["rubric_levels"] = criterion[alternative_key]
                break
    levels = criterion.get("rubric_levels", criterion.get("levels"))
    if isinstance(levels, list):
        for level in levels:
            if isinstance(level, dict) and "points" not in level:
                points = level.get("score", level.get("value"))
                if points is not None:
                    level["points"] = points
    if "maxPoints" in criterion and "max_points" not in criterion:
        criterion["max_points"] = criterion["maxPoints"]
    if "maxScore" in criterion and "max_score" not in criterion:
        criterion["max_score"] = criterion["maxScore"]
    if "max_points" not in criterion and "max_score" not in criterion:
        for alternative_key in ("maximum", "max", "weight", "points"):
            if alternative_key in criterion:
                criterion["max_points"] = criterion[alternative_key]
                break
    if "max_points" not in criterion and "max_score" not in criterion:
        possible_scores = []
        if isinstance(levels, list):
            possible_scores = [level.get("points") for level in levels if isinstance(level, dict)]
        elif isinstance(levels, dict):
            possible_scores = list(levels.keys())
        try:
            criterion["max_points"] = max(int(score) for score in possible_scores if score is not None)
        except (TypeError, ValueError):
            pass


def _rubric_max_score(criterion: dict[str, Any]) -> int:
    raw_value = criterion.get("max_points", criterion.get("max_score"))
    try:
        maximum = int(raw_value)
    except (TypeError, ValueError) as error:
        raise ValueError("Each criterion needs a positive max_points or max_score value.") from error
    if maximum <= 0:
        raise ValueError("Each criterion needs a positive max_points or max_score value.")
    return maximum


def validate_english_oral_rubric(data: Any) -> dict[str, Any]:
    """Validate the rubric shape supported by RubricEngine before saving it."""
    normalized = _normalise_uploaded_rubric(data)
    criteria = normalized.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        raise ValueError(
            "No criteria were found. Use 'criteria', 'assessment_criteria', 'grading_criteria', "
            "'categories', or a supported rubric wrapper."
        )

    for index, criterion in enumerate(criteria, start=1):
        if not isinstance(criterion, dict):
            raise ValueError(f"Criterion {index} must be a JSON object.")
        _normalise_criterion(criterion)
        if not str(criterion.get("name", "")).strip():
            raise ValueError(f"Criterion {index} needs a name.")
        maximum = _rubric_max_score(criterion)
        if "max_points" in criterion:
            criterion["max_points"] = maximum
        else:
            criterion["max_score"] = maximum
        levels = criterion.get("rubric_levels", criterion.get("levels"))
        if not isinstance(levels, (list, dict)) or not levels:
            raise ValueError(f"Criterion '{criterion['name']}' needs scoring levels.")
        if isinstance(levels, list):
            for level in levels:
                if not isinstance(level, dict):
                    raise ValueError(f"Criterion '{criterion['name']}' has an invalid scoring level.")
                try:
                    points = int(level.get("points"))
                except (TypeError, ValueError) as error:
                    raise ValueError(f"Criterion '{criterion['name']}' has a level without numeric points.") from error
                if points < 0 or points > maximum:
                    raise ValueError(f"Criterion '{criterion['name']}' has level points outside 0-{maximum}.")
                level["points"] = points
        else:
            for points in levels:
                try:
                    value = int(points)
                except (TypeError, ValueError) as error:
                    raise ValueError(f"Criterion '{criterion['name']}' has non-numeric level points.") from error
                if value < 0 or value > maximum:
                    raise ValueError(f"Criterion '{criterion['name']}' has level points outside 0-{maximum}.")
    return normalized


def save_english_oral_rubric(filename: str, contents: bytes) -> str:
    """Save an examiner's validated English oral rubric under a portal-only name."""
    try:
        data = json.loads(contents.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Upload a UTF-8 JSON rubric file.") from error
    rubric = validate_english_oral_rubric(data)
    supplied_stem = Path(filename).stem
    safe_stem = re.sub(r"[^a-z0-9]+", "_", supplied_stem.lower()).strip("_") or "custom_rubric"
    base_name = f"{CUSTOM_ORAL_RUBRIC_PREFIX}{safe_stem}"
    rubric_name = base_name
    version = 2
    while (RUBRICS_DIR / f"{rubric_name}.json").exists():
        rubric_name = f"{base_name}_{version}"
        version += 1
    rubric["name"] = str(rubric.get("name") or supplied_stem or "Custom PSLE English Oral rubric").strip()
    rubric["portal_scope"] = "psle_english_oral"
    _write_json(RUBRICS_DIR / f"{rubric_name}.json", rubric)
    return rubric_name


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
        "reading_submission": None,
        "questions": copy.deepcopy(questions[:3]),
        "reading_completed_at": None,
        "guidance_attempts": {},
        "results": [],
        "results_released_at": None,
        "results_released_by": None,
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


def save_reading_submission(
    assignment_id: str,
    *,
    transcript: str,
    response_mode: str,
    audio_path: str | None = None,
    transcription_path: str | None = None,
    delivery_indicators: dict[str, Any] | None = None,
    grading_result: dict[str, Any] | None = None,
    crew_analysis: str = "",
) -> dict[str, Any]:
    """Save one reading-aloud submission and its provisional AI grade."""
    def save_submission(record: dict[str, Any]) -> None:
        if not record.get("reading"):
            raise ValueError("This assessment has no reading passage.")
        if record.get("reading_submission"):
            raise ValueError("The reading-aloud response has already been submitted.")
        record["reading_submission"] = {
            "transcript": transcript,
            "response_mode": response_mode,
            "audio_path": audio_path,
            "transcription_path": transcription_path,
            "delivery_indicators": copy.deepcopy(delivery_indicators) if delivery_indicators else None,
            "ai_grading": copy.deepcopy(grading_result) if grading_result else None,
            "final_grading": copy.deepcopy(grading_result) if grading_result else None,
            "examiner_review": None,
            "crew_analysis": crew_analysis,
            "submitted_at": _now(),
        }
        record["reading_completed_at"] = _now()

    return _update_assignment(assignment_id, save_submission)


def save_guidance_attempt(
    assignment_id: str,
    *,
    question: dict[str, Any],
    original_response: str,
    follow_up_question: str,
    reason: str = "",
    response_mode: str = "text",
    audio_path: str | None = None,
    transcription_path: str | None = None,
    delivery_indicators: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist the one allowed examiner guidance prompt for a question."""
    question_id = str(question.get("id", ""))
    if not question_id:
        raise ValueError("A question ID is required to save guidance")

    def add_guidance(record: dict[str, Any]) -> None:
        attempts = record.setdefault("guidance_attempts", {})
        if question_id in attempts:
            raise ValueError("A guidance prompt has already been used for this question")
        attempts[question_id] = {
            "original_response": original_response,
            "original_response_mode": response_mode,
            "original_audio_path": audio_path,
            "original_transcription_path": transcription_path,
            "original_delivery_indicators": copy.deepcopy(delivery_indicators) if delivery_indicators else None,
            "follow_up_question": follow_up_question,
            "reason": reason,
            "created_at": _now(),
        }

    return _update_assignment(assignment_id, add_guidance)


def add_assessment_result(
    assignment_id: str,
    *,
    question: dict[str, Any],
    student_response: str,
    grading_result: dict[str, Any],
    session_id: str | None,
    crew_analysis: str = "",
    skipped: bool = False,
    follow_up_response: str | None = None,
    response_mode: str = "text",
    audio_path: str | None = None,
    transcription_path: str | None = None,
    delivery_indicators: dict[str, Any] | None = None,
) -> dict[str, Any]:
    question_id = str(question.get("id", ""))
    result = {
        "result_id": uuid.uuid4().hex[:12],
        "question_id": question.get("id"),
        "question": question.get("text", ""),
        "visual_context": question.get("visual_context"),
        "student_response": student_response,
        "response_mode": response_mode,
        "audio_path": audio_path,
        "transcription_path": transcription_path,
        "delivery_indicators": copy.deepcopy(delivery_indicators) if delivery_indicators else None,
        "session_id": session_id,
        "created_at": _now(),
        "skipped": skipped,
        "ai_grading": copy.deepcopy(grading_result),
        "final_grading": copy.deepcopy(grading_result),
        "examiner_review": None,
        "crew_analysis": crew_analysis,
    }

    def append_result(record: dict[str, Any]) -> None:
        if any(str(item.get("question_id")) == question_id for item in record.get("results", [])):
            raise ValueError("This question has already been submitted.")
        guidance = record.setdefault("guidance_attempts", {}).pop(question_id, None)
        if guidance:
            guidance["follow_up_response"] = follow_up_response or student_response
            result["guided_attempt"] = guidance
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


def apply_reading_examiner_review(
    assignment_id: str,
    scores: dict[str, int],
    note: str,
    examiner_id: str,
) -> dict[str, Any]:
    """Save the examiner's final reading-aloud grade while retaining the AI grade."""
    def update_reading(record: dict[str, Any]) -> None:
        submission = record.get("reading_submission")
        if not submission:
            raise ValueError("The student has not submitted the reading-aloud response.")
        final_grading = copy.deepcopy(submission.get("final_grading") or submission.get("ai_grading") or {})
        total = 0
        maximum = 0
        for criterion in final_grading.get("scores", []):
            max_score = int(criterion.get("max_score", 0))
            name = str(criterion.get("criterion", ""))
            if name in scores:
                criterion["score"] = max(0, min(int(scores[name]), max_score))
            total += int(criterion.get("score", 0))
            maximum += max_score
        final_grading["total_score"] = total
        final_grading["max_score"] = maximum
        final_grading["percentage"] = round(total / maximum * 100, 1) if maximum else 0
        submission["final_grading"] = final_grading
        submission["examiner_review"] = {
            "reviewed_at": _now(),
            "reviewed_by": examiner_id,
            "note": note.strip(),
            "score_changes": copy.deepcopy(scores),
        }

    return _update_assignment(assignment_id, update_reading)


def release_final_results(assignment_id: str, examiner_id: str) -> dict[str, Any]:
    """Release results only after the examiner has verified every required component."""
    def release(record: dict[str, Any]) -> None:
        if record.get("status") != "completed":
            raise ValueError("The student must complete the assessment before results can be released.")
        if record.get("reading"):
            submission = record.get("reading_submission")
            if not submission or not submission.get("examiner_review"):
                raise ValueError("Verify the reading-aloud grade before releasing results.")

        expected_ids = {str(question.get("id")) for question in record.get("questions", [])}
        submitted = {str(result.get("question_id")): result for result in record.get("results", [])}
        missing = expected_ids - set(submitted)
        if missing:
            raise ValueError("The student has not submitted every image question.")
        unreviewed = [question_id for question_id in expected_ids if not submitted[question_id].get("examiner_review")]
        if unreviewed:
            raise ValueError("Verify every image-question grade before releasing results.")
        record["results_released_at"] = _now()
        record["results_released_by"] = examiner_id

    return _update_assignment(assignment_id, release)


def delete_assignment(assignment_id: str, examiner_id: str) -> dict[str, Any]:
    """Permanently remove an assessment, its submissions, sessions, and unique materials."""
    store = load_assignments()
    record = store["assignments"].get(assignment_id)
    if not record:
        raise KeyError(f"Assignment {assignment_id} was not found")

    artifact_paths: set[str] = set()
    session_ids: set[str] = set()

    def collect_artifacts(item: dict[str, Any], keys: tuple[str, ...]) -> None:
        for key in keys:
            value = item.get(key)
            if value:
                artifact_paths.add(str(value))

    reading_submission = record.get("reading_submission") or {}
    collect_artifacts(reading_submission, ("audio_path", "transcription_path"))
    for guidance in (record.get("guidance_attempts") or {}).values():
        collect_artifacts(guidance, ("original_audio_path", "original_transcription_path"))
    for result in record.get("results", []):
        collect_artifacts(result, ("audio_path", "transcription_path"))
        if result.get("session_id"):
            session_ids.add(str(result["session_id"]))
        guided_attempt = result.get("guided_attempt") or {}
        collect_artifacts(guided_attempt, ("original_audio_path", "original_transcription_path"))
    for question in record.get("questions", []):
        avatar_video = question.get("avatar_video") or {}
        collect_artifacts(avatar_video, ("path",))

    errors: list[str] = []
    deleted_sessions: list[str] = []
    try:
        from agent_a6_session_manager import SessionManager

        sessions = SessionManager()
        for session_id in sessions.list_sessions():
            session = sessions.get_session(session_id)
            if session and (session.metadata or {}).get("assignment_id") == assignment_id:
                session_ids.add(session_id)
        for session_id in session_ids:
            if sessions.delete_session(session_id, include_artifacts=True):
                deleted_sessions.append(session_id)
    except Exception as error:
        errors.append(f"session cleanup: {error}")

    sessions_dir = (DATA_DIR / "sessions").resolve()
    avatar_dir = (DATA_DIR / "avatar_videos").resolve()
    deleted_artifacts: list[str] = []
    for value in artifact_paths:
        try:
            path = Path(value).resolve()
            if not _is_relative_to(path, sessions_dir) and not _is_relative_to(path, avatar_dir):
                raise ValueError("path is outside managed artifact directories")
            if path.is_file():
                path.unlink()
                deleted_artifacts.append(str(path))
        except (OSError, ValueError) as error:
            errors.append(f"artifact cleanup ({value}): {error}")

    subject = str(record.get("subject") or "")
    if subject.startswith("assignment_"):
        try:
            from subject_manager import SubjectManager

            SubjectManager().delete_subject_data(subject)
        except Exception as error:
            errors.append(f"material cleanup: {error}")

    del store["assignments"][assignment_id]
    save_assignments(store)
    return {
        "assignment_id": assignment_id,
        "deleted_by": examiner_id,
        "deleted_sessions": deleted_sessions,
        "deleted_artifacts": deleted_artifacts,
        "errors": errors,
    }


def reset_assignment_results(assignment_id: str, examiner_id: str) -> dict[str, Any]:
    """Clear a student's attempt while retaining the assigned questions and materials."""
    record = get_assignment(assignment_id)
    if not record:
        raise KeyError(f"Assignment {assignment_id} was not found")

    artifact_paths: set[str] = set()
    session_ids: set[str] = set()

    def collect_artifacts(item: dict[str, Any], keys: tuple[str, ...]) -> None:
        for key in keys:
            value = item.get(key)
            if value:
                artifact_paths.add(str(value))

    collect_artifacts(record.get("reading_submission") or {}, ("audio_path", "transcription_path"))
    for guidance in (record.get("guidance_attempts") or {}).values():
        collect_artifacts(guidance, ("original_audio_path", "original_transcription_path"))
    for result in record.get("results", []):
        collect_artifacts(result, ("audio_path", "transcription_path"))
        if result.get("session_id"):
            session_ids.add(str(result["session_id"]))
        collect_artifacts(result.get("guided_attempt") or {}, ("original_audio_path", "original_transcription_path"))
    for guidance in (record.get("guidance_attempts") or {}).values():
        avatar_video = guidance.get("avatar_video") or {}
        collect_artifacts(avatar_video, ("path",))

    errors: list[str] = []
    deleted_sessions: list[str] = []
    try:
        from agent_a6_session_manager import SessionManager

        sessions = SessionManager()
        for session_id in sessions.list_sessions():
            session = sessions.get_session(session_id)
            if session and (session.metadata or {}).get("assignment_id") == assignment_id:
                session_ids.add(session_id)
        for session_id in session_ids:
            if sessions.delete_session(session_id, include_artifacts=True):
                deleted_sessions.append(session_id)
    except Exception as error:
        errors.append(f"session cleanup: {error}")

    sessions_dir = (DATA_DIR / "sessions").resolve()
    avatar_dir = (DATA_DIR / "avatar_videos").resolve()
    deleted_artifacts: list[str] = []
    for value in artifact_paths:
        try:
            path = Path(value).resolve()
            if not _is_relative_to(path, sessions_dir) and not _is_relative_to(path, avatar_dir):
                raise ValueError("path is outside managed artifact directories")
            if path.is_file():
                path.unlink()
                deleted_artifacts.append(str(path))
        except (OSError, ValueError) as error:
            errors.append(f"artifact cleanup ({value}): {error}")

    def clear_attempt(target: dict[str, Any]) -> None:
        target["status"] = "assigned"
        target["reading_submission"] = None
        target["reading_completed_at"] = None
        target["guidance_attempts"] = {}
        target["results"] = []
        target["results_released_at"] = None
        target["results_released_by"] = None

    _update_assignment(assignment_id, clear_attempt)
    return {
        "assignment_id": assignment_id,
        "reset_by": examiner_id,
        "deleted_sessions": deleted_sessions,
        "deleted_artifacts": deleted_artifacts,
        "errors": errors,
    }


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
