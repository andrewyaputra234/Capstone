"""Local Streamlit portal for assigning and reviewing oral assessments.

Run with: ``streamlit run streamlit_app.py``
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent / "src"))

from env_fix import apply_runtime_fixes

apply_runtime_fixes()

from exam_portal_store import (
    add_assessment_result,
    apply_examiner_review,
    apply_reading_examiner_review,
    authenticate,
    create_assignment,
    delete_assignment,
    list_assignments,
    list_english_oral_rubrics,
    list_students,
    mark_assignment_status,
    register_student,
    rubric_display_name,
    release_final_results,
    save_guidance_attempt,
    save_english_oral_rubric,
    save_reading_ai_grading,
    save_reading_ai_grading_error,
    save_reading_submission,
    reset_assignment_results,
)
from subject_manager import SubjectManager
from voice_assessment import analyse_delivery, transcribe_streamlit_audio

load_dotenv()

# Keep the portal shell fast. The CrewAI stack imports PyTorch and LangChain, so
# it is loaded only when a student begins an assessment or an examiner generates
# a new one.
DEFAULT_PSLE_RUBRIC = "psle_oral_english"
IMAGE_QUESTION_COUNT = 3

st.set_page_config(
    page_title="Examination Portal",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)


for key, default in [
    ("authenticated", False),
    ("user_role", None),
    ("user_id", ""),
    ("user_name", ""),
    ("crew", None),
    ("crew_subject", None),
    ("crew_rubric", None),
    ("crew_student_id", None),
    ("session_id", None),
    ("active_assignment_id", None),
    ("assignment_draft", None),
    ("assignment_generation_request", None),
    ("simli_avatar_cache", {}),
    ("simli_avatar_errors", {}),
    ("simli_avatar_futures", {}),
    ("simli_avatar_future_meta", {}),
    ("reading_ai_grading_futures", {}),
    ("preparation_deadline", None),
    ("preparation_timer_assignment_id", None),
    ("preparation_complete", False),
    ("student_portal_stage", "selection"),
    ("student_selected_assignment_id", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


def list_rubrics() -> list[str]:
    """The portal deliberately exposes only PSLE English Oral rubrics."""
    return list_english_oral_rubrics()


def reset_runtime_state() -> None:
    st.session_state.crew = None
    st.session_state.crew_subject = None
    st.session_state.crew_rubric = None
    st.session_state.crew_student_id = None
    st.session_state.session_id = None
    st.session_state.active_assignment_id = None


def logout() -> None:
    reset_runtime_state()
    st.session_state.preparation_deadline = None
    st.session_state.preparation_timer_assignment_id = None
    st.session_state.preparation_complete = False
    st.session_state.student_portal_stage = "selection"
    st.session_state.student_selected_assignment_id = None
    st.session_state.authenticated = False
    st.session_state.user_role = None
    st.session_state.user_id = ""
    st.session_state.user_name = ""
    st.rerun()


def init_crew(subject: str, rubric: str, student_id: str) -> EducationCrew:
    from crew_orchestrator import EducationCrew

    return EducationCrew(
        subject=subject,
        rubric_name=rubric,
        verbose=False,
        student_id=student_id,
    )


def ensure_assignment_crew(assignment: dict) -> EducationCrew:
    if (
        st.session_state.crew is None
        or st.session_state.crew_subject != assignment["subject"]
        or st.session_state.crew_rubric != assignment["rubric"]
        or st.session_state.crew_student_id != assignment["student_id"]
    ):
        st.session_state.crew = init_crew(
            assignment["subject"], assignment["rubric"], assignment["student_id"]
        )
        st.session_state.crew_subject = assignment["subject"]
        st.session_state.crew_rubric = assignment["rubric"]
        st.session_state.crew_student_id = assignment["student_id"]
        st.session_state.session_id = None
    return st.session_state.crew


def restore_assignment_session(crew: EducationCrew, assignment_id: str) -> bool:
    """Recover an active session after a Streamlit rerun loses browser state."""
    session = crew.session_manager.find_active_session_for_assignment(assignment_id)
    if not session:
        return False
    crew.session_id = session.session_id
    st.session_state.session_id = session.session_id
    return True


def render_grading_result(grading: dict, *, heading: str | None = None) -> None:
    if heading:
        st.markdown(f"#### {heading}")
    if grading.get("skipped"):
        st.warning("Question skipped. Assessed criteria were recorded as 0.")
    if grading.get("scoring_source") == "fallback":
        st.warning("AI scoring was unavailable for part of this result. Verify the provisional rubric scores before relying on them.")

    total, maximum, percentage = (
        grading.get("total_score", 0),
        grading.get("max_score", 0),
        grading.get("percentage", 0),
    )
    col1, col2, col3 = st.columns(3)
    col1.metric("Score", f"{total}/{maximum}")
    col2.metric("Percentage", f"{percentage}%")
    col3.metric(
        "Status",
        "Excellent" if percentage >= 80 else "Good" if percentage >= 70 else "Fair" if percentage >= 60 else "Needs improvement",
    )

    for criterion in grading.get("scores", []):
        label = criterion.get("criterion", "Criterion")
        max_score = criterion.get("max_score", 0)
        if max_score:
            st.write(f"**{label}:** {criterion.get('score', 0)}/{max_score}")
        else:
            st.write(f"**{label}:** not assessed")
        if criterion.get("feedback"):
            st.markdown(
                f'<div class="ai-grading-comment">{html_escape(str(criterion["feedback"]))}</div>',
                unsafe_allow_html=True,
            )
        if criterion.get("evidence"):
            st.markdown(
                f'<div class="ai-grading-comment ai-grading-evidence"><strong>Evidence:</strong> {html_escape(str(criterion["evidence"]))}</div>',
                unsafe_allow_html=True,
            )

    if grading.get("tutoring_feedback"):
        st.markdown(
            f'<div class="ai-grading-summary">{html_escape(str(grading["tutoring_feedback"]))}</div>',
            unsafe_allow_html=True,
        )


def grading_score_label(grading: dict) -> str:
    total = int((grading or {}).get("total_score", 0))
    maximum = int((grading or {}).get("max_score", 0))
    return f"{total}/{maximum}" if maximum else "Pending"


def grading_score_delta(ai_grading: dict, final_grading: dict) -> str:
    ai_total = int((ai_grading or {}).get("total_score", 0))
    final_total = int((final_grading or {}).get("total_score", 0))
    delta = final_total - ai_total
    if delta > 0:
        return f"+{delta}"
    return str(delta)


def render_review_summary(
    *,
    ai_grading: dict,
    final_grading: dict,
    reviewed_at: str | None,
    released_at: str | None = None,
    has_audio: bool = False,
    guidance_used: bool = False,
    skipped: bool = False,
) -> None:
    columns = st.columns(5)
    columns[0].metric("AI score", grading_score_label(ai_grading))
    columns[1].metric("Final score", grading_score_label(final_grading))
    columns[2].metric("Adjustment", grading_score_delta(ai_grading, final_grading))
    columns[3].metric("Review", "Verified" if reviewed_at else "Pending")
    columns[4].metric("Release", "Released" if released_at else "Not released")

    evidence = []
    evidence.append("audio available" if has_audio else "no audio evidence")
    evidence.append("guided response used" if guidance_used else "no guiding question used")
    if skipped:
        evidence.append("student skipped")
    st.caption("Evidence status: " + " | ".join(evidence))
    if reviewed_at:
        st.success(f"Examiner verified this item on {reviewed_at}.")
    else:
        st.warning("Pending examiner verification.")


def render_reading_review_summary(reading_submission: dict, assignment: dict) -> None:
    grade = reading_submission.get("final_grading") or reading_submission.get("ai_grading") or {}
    reviewed_at = (reading_submission.get("examiner_review") or {}).get("reviewed_at")
    ai_status = "Failed" if reading_submission.get("ai_grading_error") else (
        "Ready" if reading_submission.get("ai_graded_at") else "Pending"
    )
    columns = st.columns(5)
    columns[0].metric("Recording", "Submitted" if reading_submission.get("audio_path") else "Missing")
    columns[1].metric("AI reading grade", ai_status)
    columns[2].metric("Examiner review", "Verified" if reviewed_at else "Pending")
    columns[3].metric("Final score", grading_score_label(grade))
    columns[4].metric("Release", "Released" if assignment.get("results_released_at") else "Not released")
    if reviewed_at:
        st.success(f"Reading-aloud grade verified on {reviewed_at}.")
    else:
        st.warning("Reading-aloud grade still needs examiner verification before release.")


def save_queued_upload(upload: dict, directory: Path) -> Path:
    """Save an upload captured in session state under a controlled temporary directory."""
    safe_name = Path(str(upload.get("name") or "uploaded-material")).name
    path = directory / safe_name
    path.write_bytes(upload.get("bytes") or b"")
    return path


def save_reading_material_for_assignment(subject: str, source_path: str | Path) -> dict:
    """Store reading material without running the slower chunk/vector ingestion path."""
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"Reading passage not found: {source}")

    subject_manager = SubjectManager()
    input_dir = subject_manager.get_subject_input_path(subject)
    input_dir.mkdir(parents=True, exist_ok=True)
    dest = input_dir / source.name
    if source.resolve() != dest.resolve():
        shutil.copy2(source, dest)

    subject_manager.set_subject_material_path(subject, "reading", str(dest))
    return {
        "file_path": str(dest),
        "text": extract_reading_passage(dest),
    }


def extract_reading_passage(file_path: str | Path, max_chars: int = 6000) -> str:
    from main import load_document

    documents = load_document(Path(file_path))
    text = "\n\n".join(document.page_content.strip() for document in documents if document.page_content.strip())
    return text.strip()[:max_chars]


def assignment_subject(student_id: str) -> str:
    clean_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", student_id).strip("-") or "student"
    return f"assignment_{clean_id}_{uuid.uuid4().hex[:8]}"


def visual_path(assignment: dict) -> str | None:
    path = assignment.get("visual", {}).get("path")
    return path if path and Path(path).exists() else None


def assessment_question_with_visual_context(question: dict) -> str:
    """Give the turn evaluator the visual facts it needs to catch irrelevant answers."""
    visual_context = question.get("visual_context")
    if not visual_context:
        return question.get("text", "")
    return f"Visual stimulus facts: {visual_context}\n\nQuestion: {question.get('text', '')}"


def active_avatar_provider() -> str:
    provider = os.getenv("AVATAR_PROVIDER", "").strip().lower()
    if provider:
        return provider
    if bool_env("ENABLE_ANAM_AVATAR", False):
        return "anam"
    if bool_env("ENABLE_SIMLI_AVATAR", False):
        return "simli"
    return "none"


def simli_avatar_requested() -> bool:
    return active_avatar_provider() == "simli"


def anam_avatar_requested() -> bool:
    return active_avatar_provider() == "anam"


def avatar_requested() -> bool:
    return active_avatar_provider() in {"simli", "anam"}


def html_escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def avatar_cache_key_for(text: str, cache_key: str) -> tuple[str, str]:
    clean_text = " ".join((text or "").split())
    text_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()[:16]
    return clean_text, f"{active_avatar_provider()}_v2:{cache_key}:{text_hash}"


def prepare_examiner_avatar(text: str, *, cache_key: str) -> str | None:
    """Generate and cache the examiner avatar video without rendering it."""
    if not simli_avatar_requested():
        return None

    try:
        from simli_avatar import create_avatar_video_url, load_config
    except Exception as error:
        st.session_state.setdefault("simli_avatar_errors", {})[f"import:{cache_key}"] = str(error)
        return None

    if not load_config():
        return None

    clean_text, avatar_cache_key = avatar_cache_key_for(text, cache_key)
    if not clean_text:
        return None

    cache = st.session_state.setdefault("simli_avatar_cache", {})
    if cache.get(avatar_cache_key):
        return cache[avatar_cache_key]

    errors = st.session_state.setdefault("simli_avatar_errors", {})
    if avatar_cache_key in errors:
        return None

    try:
        url = create_avatar_video_url(clean_text)
    except Exception as error:
        errors[avatar_cache_key] = str(error)
        return None

    cache[avatar_cache_key] = url
    return url


@st.cache_resource
def avatar_preload_executor() -> ThreadPoolExecutor:
    """Shared worker for preparing avatar videos without blocking the prep page."""
    return ThreadPoolExecutor(max_workers=1, thread_name_prefix="examiner-avatar-preload")


@st.cache_resource
def reading_ai_grading_executor() -> ThreadPoolExecutor:
    """Shared worker for deferred reading-aloud AI grading."""
    return ThreadPoolExecutor(max_workers=1, thread_name_prefix="reading-ai-grading")


def create_avatar_video_in_background(text: str) -> str:
    """Worker-safe avatar generation. Do not access Streamlit state in this function."""
    from simli_avatar import create_avatar_video_url

    return create_avatar_video_url(text)


def reading_completion_evidence(passage: str, transcript: str) -> dict:
    passage_words = re.findall(r"[a-z0-9']+", (passage or "").lower())
    transcript_words = re.findall(r"[a-z0-9']+", (transcript or "").lower())
    if not passage_words:
        return {
            "status": "unavailable",
            "reason": "No source passage was provided.",
        }
    if not transcript_words:
        return {
            "status": "available",
            "passage_words": len(passage_words),
            "transcript_words": 0,
            "estimated_passage_coverage_percent": 0,
            "estimated_sequence_match_percent": 0,
            "notes": ["No transcript words were detected."],
        }

    import difflib

    matcher = difflib.SequenceMatcher(None, passage_words, transcript_words, autojunk=False)
    matched_words = sum(block.size for block in matcher.get_matching_blocks())
    coverage = round(matched_words / len(passage_words) * 100, 1)
    sequence_match = round(matcher.ratio() * 100, 1)
    notes = []
    if coverage < 70:
        notes.append("Transcript appears to miss a sizeable part of the passage; check for skipped lines or unclear reading.")
    elif coverage < 90:
        notes.append("Most of the passage appears present, but the examiner should check for omissions or substitutions.")
    else:
        notes.append("Transcript appears broadly complete against the source passage.")
    return {
        "status": "available",
        "passage_words": len(passage_words),
        "transcript_words": len(transcript_words),
        "estimated_passage_coverage_percent": coverage,
        "estimated_sequence_match_percent": sequence_match,
        "notes": notes,
    }


def reading_grading_evidence(passage: str, transcript: str, delivery_indicators: dict | None) -> dict:
    return {
        "audio_evidence": "A student reading-aloud recording was submitted for examiner review.",
        "source_passage": passage,
        "transcript": transcript,
        "completion_check": reading_completion_evidence(passage, transcript),
        "delivery_indicators": delivery_indicators,
        "limitation": (
            "Automated grading uses transcript completeness and broad delivery indicators. "
            "It cannot reliably score phoneme-level pronunciation, accent, or expression without examiner review."
        ),
    }


def grade_reading_submission_in_background(payload: dict) -> dict:
    """Grade a saved reading submission and persist the provisional result."""
    assignment_id = payload["assignment_id"]
    try:
        delivery = payload.get("delivery_indicators") or {}
        audio_path = payload.get("audio_path")
        transcript = payload.get("transcript", "")
        if audio_path and delivery.get("status") != "available":
            delivery = analyse_delivery(audio_path, transcript)

        evidence = reading_grading_evidence(payload.get("passage", ""), transcript, delivery)
        visual_context = f"Reading-aloud evidence: {json.dumps(evidence, indent=2)}"
        question = (
            "Reading-aloud submission. Assess only the selected reading-delivery rubric criteria. "
            "Use the source passage, transcript completeness check, and advisory delivery indicators."
        )

        crew = init_crew(payload["subject"], payload["rubric"], payload["student_id"])
        grading_result = crew.grade_response(
            question,
            transcript,
            visual_context=visual_context,
            criterion_names=payload.get("reading_criteria"),
        )
        grading_result["scoring_source"] = "deferred_ai_reading"
        save_reading_ai_grading(
            assignment_id,
            grading_result=grading_result,
            crew_analysis=(
                "Deferred AI reading-aloud grading used the transcript, a source-passage "
                "completion check, and advisory delivery indicators. Examiner verification is still required."
            ),
            delivery_indicators=delivery,
        )
        return {"status": "saved", "assignment_id": assignment_id}
    except Exception as error:
        try:
            save_reading_ai_grading_error(assignment_id, str(error))
        finally:
            return {"status": "error", "assignment_id": assignment_id, "error": str(error)}


def queue_deferred_reading_ai_grading(
    assignment: dict,
    *,
    transcript: str,
    audio_path: str | None,
    transcription_path: str | None,
    delivery_indicators: dict | None,
    reading_criteria: list[str],
) -> None:
    if not bool_env("DEFERRED_READING_AI_GRADING", True):
        return
    assignment_id = assignment["assignment_id"]
    futures: dict[str, Future] = st.session_state.setdefault("reading_ai_grading_futures", {})
    future = futures.get(assignment_id)
    if future and not future.done():
        return

    payload = {
        "assignment_id": assignment_id,
        "subject": assignment["subject"],
        "rubric": assignment["rubric"],
        "student_id": assignment["student_id"],
        "passage": (assignment.get("reading") or {}).get("text", ""),
        "transcript": transcript,
        "audio_path": audio_path,
        "transcription_path": transcription_path,
        "delivery_indicators": delivery_indicators,
        "reading_criteria": reading_criteria,
    }
    futures[assignment_id] = reading_ai_grading_executor().submit(grade_reading_submission_in_background, payload)


def collect_deferred_reading_ai_grading() -> None:
    futures: dict[str, Future] = st.session_state.setdefault("reading_ai_grading_futures", {})
    for assignment_id, future in list(futures.items()):
        if future.done():
            future.result()
            futures.pop(assignment_id, None)


def avatar_terminal_log(message: str) -> None:
    """Print avatar preload progress only to the Streamlit terminal."""
    enabled = os.getenv("AVATAR_PRELOAD_TERMINAL_LOG", "true").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        return
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] [avatar-preload] {message}", flush=True)


def float_env(name: str, default: float, *, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except ValueError:
        return max(minimum, default)


def bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def preparation_duration_seconds() -> int:
    return int(float_env("PREPARATION_MINUTES", 10.0, minimum=1.0) * 60)


def supported_visual_image_path(path: str | Path) -> bool:
    try:
        from agent_image_extractor import is_supported_image_file

        return is_supported_image_file(str(path))
    except Exception:
        return Path(path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}


def avatar_generation_backoff_seconds(attempt: int) -> float:
    """Exponential backoff after failed Simli generation attempts."""
    base = float_env("SIMLI_RETRY_BACKOFF_BASE_SECONDS", 5.0)
    multiplier = float_env("SIMLI_RETRY_BACKOFF_MULTIPLIER", 3.0, minimum=1.0)
    maximum = float_env("SIMLI_RETRY_BACKOFF_MAX_SECONDS", 60.0)
    return min(maximum, base * (multiplier ** max(attempt - 1, 0)))


def simli_request_spacing_seconds() -> float:
    """Small queue delay before new Simli creation requests."""
    return float_env("SIMLI_REQUEST_SPACING_SECONDS", 1.0)


def avatar_asset_cache_enabled() -> bool:
    return bool_env("AVATAR_ASSET_CACHE_ENABLED", True)


def avatar_asset_cache_path() -> Path:
    return Path("data/avatar_asset_cache.json")


def avatar_asset_cache_key(text: str, config) -> str:
    clean_text = " ".join((text or "").split())
    identity = "|".join(
        [
            "simli-static-audio-v1",
            getattr(config, "face_id", ""),
            getattr(config, "tts_model", ""),
            getattr(config, "tts_voice", ""),
            clean_text,
        ]
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def load_avatar_asset_cache() -> dict:
    if not avatar_asset_cache_enabled():
        return {}
    path = avatar_asset_cache_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_avatar_asset_cache(cache: dict) -> None:
    if not avatar_asset_cache_enabled():
        return
    try:
        path = avatar_asset_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except OSError:
        return


def get_cached_avatar_asset(text: str, config) -> dict:
    cache = load_avatar_asset_cache()
    cache_key = avatar_asset_cache_key(text, config)
    cached = cache.get(cache_key)
    if not isinstance(cached, dict):
        return {}
    avatar_video = refresh_avatar_video_reference(cached.get("avatar_video") or {})
    if not avatar_video.get("source_url"):
        return {}
    if avatar_video.get("terminal_file_not_found"):
        return {}
    cache[cache_key] = {
        **cached,
        "avatar_video": avatar_video,
        "last_used_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    save_avatar_asset_cache(cache)
    return dict(avatar_video)


def store_cached_avatar_asset(text: str, config, avatar_video: dict) -> None:
    if not avatar_video.get("source_url"):
        return
    cache = load_avatar_asset_cache()
    cache[avatar_asset_cache_key(text, config)] = {
        "text_hash": hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()[:16],
        "avatar_video": avatar_video,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "last_used_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    save_avatar_asset_cache(cache)


def collect_avatar_preload_results() -> None:
    """Move completed background avatar jobs into the normal Streamlit cache."""
    futures: dict[str, Future] = st.session_state.setdefault("simli_avatar_futures", {})
    if not futures:
        return

    cache = st.session_state.setdefault("simli_avatar_cache", {})
    errors = st.session_state.setdefault("simli_avatar_errors", {})
    meta: dict[str, dict] = st.session_state.setdefault("simli_avatar_future_meta", {})
    completed_keys = []
    for avatar_cache_key, future in list(futures.items()):
        if not future.done():
            continue
        completed_keys.append(avatar_cache_key)
        details = meta.get(avatar_cache_key, {})
        started_at = details.get("started_at")
        elapsed = f" in {time.monotonic() - started_at:.1f}s" if started_at else ""
        label = details.get("label") or avatar_cache_key
        try:
            cache[avatar_cache_key] = future.result()
            errors.pop(avatar_cache_key, None)
            avatar_terminal_log(f"ready {label}{elapsed}")
        except Exception as error:
            errors[avatar_cache_key] = str(error)
            avatar_terminal_log(f"failed {label}{elapsed}: {error}")

    for avatar_cache_key in completed_keys:
        futures.pop(avatar_cache_key, None)
        meta.pop(avatar_cache_key, None)


def queue_examiner_avatar_preload(text: str, *, cache_key: str) -> None:
    """Queue avatar generation so student preparation stays readable and responsive."""
    if not simli_avatar_requested():
        return

    try:
        from simli_avatar import load_config
    except Exception as error:
        st.session_state.setdefault("simli_avatar_errors", {})[f"import:{cache_key}"] = str(error)
        return

    if not load_config():
        return

    clean_text, avatar_cache_key = avatar_cache_key_for(text, cache_key)
    if not clean_text:
        return

    collect_avatar_preload_results()
    cache = st.session_state.setdefault("simli_avatar_cache", {})
    errors = st.session_state.setdefault("simli_avatar_errors", {})
    futures: dict[str, Future] = st.session_state.setdefault("simli_avatar_futures", {})
    if cache.get(avatar_cache_key) or avatar_cache_key in errors:
        return
    if avatar_cache_key in futures and not futures[avatar_cache_key].done():
        return

    futures[avatar_cache_key] = avatar_preload_executor().submit(create_avatar_video_in_background, clean_text)
    st.session_state.setdefault("simli_avatar_future_meta", {})[avatar_cache_key] = {
        "started_at": time.monotonic(),
        "label": cache_key,
        "preview": clean_text[:90],
    }
    avatar_terminal_log(f"queued {cache_key}: {clean_text[:90]}")


def avatar_auto_play_once(cache_key: str, text: str, *, enabled: bool = True) -> bool:
    """Allow an examiner prompt to auto-speak once across Streamlit reruns."""
    if not enabled:
        return False
    clean_text = " ".join((text or "").split())
    if not clean_text:
        return False
    prompt_key = f"{cache_key}:{hashlib.sha256(clean_text.encode('utf-8')).hexdigest()[:16]}"
    spoken_prompts = st.session_state.setdefault("examiner_avatar_spoken_prompts", {})
    if prompt_key in spoken_prompts:
        return False
    spoken_prompts[prompt_key] = True
    return True


def render_anam_examiner_avatar(text: str, *, cache_key: str, auto_play: bool = False) -> None:
    """Render an Anam live avatar and ask it to speak the selected examiner text."""
    try:
        from anam_avatar import create_session_token, load_config
    except Exception as error:
        st.caption(f"Examiner avatar unavailable: {error}")
        return

    if not load_config():
        st.info(
            "Anam avatar is enabled, but ANAM_API_KEY plus ANAM_PERSONA_ID "
            "or ANAM_AVATAR_ID/ANAM_VOICE_ID/ANAM_LLM_ID are not set."
        )
        st.markdown(f"**Examiner says:** {' '.join((text or '').split())}")
        return

    clean_text = " ".join((text or "").split())
    if not clean_text:
        return

    try:
        session_token = create_session_token()
    except Exception as error:
        st.warning(f"Anam examiner avatar could not start: {error}")
        st.markdown(f"**Examiner says:** {clean_text}")
        return

    safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", f"anam_{cache_key}_{hashlib.sha256(clean_text.encode('utf-8')).hexdigest()[:10]}")
    video_id = f"{safe_id}_video"
    status_id = f"{safe_id}_status"
    detail_id = f"{safe_id}_detail"
    start_id = f"{safe_id}_start"
    button_id = f"{safe_id}_replay"
    token_json = json.dumps(session_token)
    text_json = json.dumps(clean_text)
    video_id_json = json.dumps(video_id)
    status_id_json = json.dumps(status_id)
    detail_id_json = json.dumps(detail_id)
    start_id_json = json.dumps(start_id)
    button_id_json = json.dumps(button_id)
    auto_play_json = json.dumps(auto_play)
    close_after_talk_json = json.dumps(bool_env("ANAM_CLOSE_SESSION_AFTER_TALK", True))
    close_delay_ms_json = json.dumps(int(float_env("ANAM_CLOSE_SESSION_DELAY_SECONDS", 10.0) * 1000))
    subtitle_html = html_escape(clean_text)

    st.markdown("#### AI examiner")
    components.html(
        f"""
        <style>
          .anam-card {{
            max-width: 620px;
            margin: 0.75rem auto 1rem;
            border: 1px solid #cfe3d5;
            border-radius: 18px;
            overflow: hidden;
            background: #fbfffc;
            box-shadow: 0 16px 34px rgba(37, 72, 53, 0.12);
            font-family: Aptos, Segoe UI, sans-serif;
          }}
          .anam-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 0.75rem;
            padding: 0.75rem 0.95rem;
            background: linear-gradient(135deg, #effbf3, #dff2e7);
            color: #203b36;
            font-weight: 750;
          }}
          .anam-status {{
            color: #5b9d73;
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            text-align: right;
          }}
          .anam-video {{
            width: 100%;
            aspect-ratio: 3 / 2;
            display: block;
            background: #13201b;
            object-fit: contain;
          }}
          .anam-body {{
            padding: 0.9rem 1rem;
            border-top: 1px solid #cfe3d5;
            color: #203b36;
            line-height: 1.5;
            font-size: 1.08rem;
          }}
          .anam-actions {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 0.75rem;
            padding: 0 1rem 0.9rem;
            color: #587267;
            font-size: 0.95rem;
          }}
          .anam-button {{
            border: 1px solid #8bc59f;
            background: #f7fff9;
            color: #203b36;
            border-radius: 8px;
            padding: 0.45rem 0.7rem;
            font-weight: 700;
            cursor: pointer;
          }}
          .anam-button:disabled {{
            opacity: 0.6;
            cursor: wait;
          }}
          .anam-detail {{
            padding: 0 1rem 0.65rem;
            color: #7b5b3f;
            font-size: 0.92rem;
            line-height: 1.35;
            min-height: 1rem;
          }}
        </style>
        <div class="anam-card">
          <div class="anam-header">
            <span>AI Examiner</span>
            <span id="{status_id}" class="anam-status">{'Starting' if auto_play else 'Ready'}</span>
          </div>
          <video id="{video_id}" class="anam-video" autoplay playsinline></video>
          <div class="anam-body"><strong>Subtitles:</strong> {subtitle_html}</div>
          <div id="{detail_id}" class="anam-detail"></div>
          <div class="anam-actions">
            <span>{'Start the examiner if the video does not appear automatically.' if auto_play else 'The examiner has already asked this prompt. Press Play only if you need to hear it again.'}</span>
            <div>
              <button id="{start_id}" class="anam-button" type="button">Play</button>
              <button id="{button_id}" class="anam-button" type="button" disabled>Replay</button>
            </div>
          </div>
        </div>
        <script type="module">
          import {{ createClient }} from "https://esm.sh/@anam-ai/js-sdk@latest";
          import {{ AnamEvent }} from "https://esm.sh/@anam-ai/js-sdk@latest/dist/module/types";

          const sessionToken = {token_json};
          const promptText = {text_json};
          const videoId = {video_id_json};
          const video = document.getElementById(videoId);
          const status = document.getElementById({status_id_json});
          const detail = document.getElementById({detail_id_json});
          const startButton = document.getElementById({start_id_json});
          const replay = document.getElementById({button_id_json});
          const shouldAutoPlay = {auto_play_json};
          const closeAfterTalk = {close_after_talk_json};
          const closeDelayMs = {close_delay_ms_json};
          let client = null;
          let busy = false;
          let streamStarted = false;
          let closeTimer = null;

          const setStatus = (message) => {{
            if (status) status.textContent = message;
          }};

          const setDetail = (message) => {{
            if (detail) detail.textContent = message || "";
          }};

          const errorMessage = (error) => {{
            if (!error) return "Unknown browser-side Anam error.";
            if (error.message) return error.message;
            try {{
              return JSON.stringify(error);
            }} catch (_) {{
              return String(error);
            }}
          }};

          function clearCloseTimer() {{
            if (closeTimer) {{
              clearTimeout(closeTimer);
              closeTimer = null;
            }}
          }}

          async function closeClientAfterTalk() {{
            clearCloseTimer();
            const activeClient = client;
            client = null;
            streamStarted = false;
            if (replay) replay.disabled = true;
            if (startButton) startButton.disabled = true;
            if (!activeClient) return;
            try {{
              await activeClient.stopStreaming();
            }} catch (error) {{
              console.warn(error);
            }}
            setStatus("Finished");
            setDetail("Press Play to hear this prompt again.");
            if (startButton) startButton.disabled = false;
          }}

          function scheduleCloseAfterTalk() {{
            if (!closeAfterTalk) return;
            clearCloseTimer();
            closeTimer = setTimeout(closeClientAfterTalk, closeDelayMs);
          }}

          async function speak() {{
            if (!client || busy) return;
            clearCloseTimer();
            busy = true;
            if (replay) replay.disabled = true;
            setStatus("Speaking");
            setDetail("");
            try {{
              await client.talk(promptText);
              setStatus(closeAfterTalk ? "Finishing" : "Ready");
              scheduleCloseAfterTalk();
            }} catch (error) {{
              console.error(error);
              setStatus("Talk error");
              setDetail(errorMessage(error));
            }} finally {{
              busy = false;
              if (replay) replay.disabled = false;
            }}
          }}

          async function start() {{
            if (streamStarted) {{
              await speak();
              return;
            }}
            try {{
              clearCloseTimer();
              if (startButton) startButton.disabled = true;
              if (video) {{
                video.autoplay = true;
                video.playsInline = true;
              }}
              setStatus("Connecting");
              setDetail("");
              client = createClient(sessionToken, {{ disableInputAudio: true }});
              client.addListener(AnamEvent.CONNECTION_ESTABLISHED, () => {{
                setStatus("Connected");
              }});
              client.addListener(AnamEvent.SESSION_READY, async () => {{
                streamStarted = true;
                setStatus("Ready");
                if (startButton) startButton.disabled = false;
                if (replay) replay.disabled = false;
                await speak();
              }});
              client.addListener(AnamEvent.CONNECTION_CLOSED, (code, details) => {{
                client = null;
                streamStarted = false;
                if (replay) replay.disabled = true;
                if (startButton) startButton.disabled = false;
                setStatus(closeAfterTalk ? "Finished" : "Closed");
                setDetail(details ? `${{code}}: ${{details}}` : "Press Play to hear this prompt again.");
              }});
              await client.streamToVideoElement(videoId);
            }} catch (error) {{
              console.error(error);
              setStatus("Stream error");
              setDetail(errorMessage(error));
              if (startButton) startButton.disabled = false;
            }}
          }}

          if (startButton) startButton.addEventListener("click", start);
          if (replay) replay.addEventListener("click", speak);
          window.addEventListener("beforeunload", () => {{
            clearCloseTimer();
            if (client) client.stopStreaming().catch(() => {{}});
          }});
          if (shouldAutoPlay) {{
            start();
          }} else {{
            setStatus("Ready");
          }}
        </script>
        """,
        height=560,
        scrolling=False,
    )


def render_examiner_avatar(text: str, *, cache_key: str, auto_play: bool = False) -> None:
    """Render the configured examiner avatar for already-selected examiner text.

    The avatar is intentionally presentation-only: the app still decides the
    question, guidance, grading, and whether the student moves on.
    """
    if anam_avatar_requested():
        render_anam_examiner_avatar(text, cache_key=cache_key, auto_play=auto_play)
        return

    if not simli_avatar_requested():
        return

    try:
        from simli_avatar import load_config
    except Exception as error:
        st.caption(f"Examiner avatar unavailable: {error}")
        return

    if not load_config():
        st.info("Simli avatar is enabled, but SIMLI_API_KEY, SIMLI_FACE_ID, and OPENAI_API_KEY are not all set.")
        return

    clean_text = " ".join((text or "").split())
    if not clean_text:
        return

    collect_avatar_preload_results()
    cache = st.session_state.setdefault("simli_avatar_cache", {})
    clean_text, avatar_cache_key = avatar_cache_key_for(clean_text, cache_key)
    cached = cache.get(avatar_cache_key)
    errors = st.session_state.setdefault("simli_avatar_errors", {})
    futures: dict[str, Future] = st.session_state.setdefault("simli_avatar_futures", {})

    st.markdown("#### AI examiner")
    if cached:
        if not render_avatar_video(
            cached,
            element_key=f"simli_{avatar_cache_key}",
            subtitle=clean_text,
            auto_play=auto_play,
        ):
            st.markdown(f"**Examiner says:** {clean_text}")
            if st.button("Reload examiner video", key=f"reload_bad_avatar_{avatar_cache_key}", width="stretch"):
                st.rerun()
        return

    if avatar_cache_key in futures and not futures[avatar_cache_key].done():
        st.markdown(
            """
            <div class="prep-loading-card">
              <div class="prep-loader"></div>
              <div>
                <h3>Preparing examiner follow-up</h3>
                <p>The examiner is getting the guiding question ready.</p>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Refresh examiner follow-up", key=f"load_avatar_{avatar_cache_key}", width="stretch"):
            collect_avatar_preload_results()
            st.rerun()
        return

    if avatar_cache_key in errors:
        st.warning(f"Examiner avatar could not be prepared: {errors[avatar_cache_key]}")
        if st.button("Try avatar again", key=f"retry_avatar_{avatar_cache_key}", width="stretch"):
            errors.pop(avatar_cache_key, None)
            st.rerun()
        return

    with st.spinner("Preparing the AI examiner video..."):
        url = prepare_examiner_avatar(clean_text, cache_key=cache_key)
    if not url:
        error = errors.get(avatar_cache_key)
        if error:
            st.warning(f"Examiner avatar could not be prepared: {error}")
        else:
            st.caption("Examiner avatar is not configured, so the question is shown as text.")
        return
    if not render_avatar_video(
        url,
        element_key=f"simli_{avatar_cache_key}",
        subtitle=clean_text,
        auto_play=auto_play,
    ):
        st.markdown(f"**Examiner says:** {clean_text}")
        if st.button("Reload examiner video", key=f"reload_new_avatar_{avatar_cache_key}", width="stretch"):
            st.rerun()


def render_examiner_transition(message: str, *, cache_key: str) -> None:
    clean_message = " ".join((message or "").split())
    if not clean_message:
        return
    st.success(clean_message)
    render_examiner_avatar(clean_message, cache_key=cache_key)


def prepare_persistent_question_avatars(
    questions: list[dict],
    *,
    asset_prefix: str,
    progress_callback=None,
) -> tuple[list[dict], list[str]]:
    """Create local avatar MP4 assets for final assigned questions when Simli is enabled."""
    if not simli_avatar_requested():
        return questions, []

    try:
        from simli_avatar import create_avatar_video_asset, load_config
    except Exception as error:
        return questions, [f"Avatar setup unavailable: {error}"]

    config = load_config()
    if not config:
        return questions, ["Avatar credentials are not fully configured, so question videos were not pre-created."]

    persistent_config = replace(config, prefer_hls=True, mp4_wait_seconds=max(config.mp4_wait_seconds, 35.0))
    prepared_questions: list[dict] = []
    warnings: list[str] = []

    try:
        question_wait_seconds = float(os.getenv("AVATAR_PREVIEW_PER_QUESTION_WAIT_SECONDS", "240"))
    except ValueError:
        question_wait_seconds = 240.0
    question_wait_seconds = max(60.0, question_wait_seconds)

    try:
        generation_attempts = int(os.getenv("AVATAR_PREVIEW_GENERATION_ATTEMPTS", "2"))
    except ValueError:
        generation_attempts = 2
    generation_attempts = max(1, generation_attempts)

    requests_sent = 0
    total = len(questions)
    for index, question in enumerate(questions, 1):
        text = " ".join(str(question.get("text", "")).split())
        if not text:
            prepared_questions.append({**question})
            continue

        prepared = {**question}
        question_ready = False
        last_readiness_warnings: list[str] = []

        cached_avatar_video = get_cached_avatar_asset(text, persistent_config)
        if cached_avatar_video:
            avatar_terminal_log(f"using cached avatar asset for assigned question {index}: {text[:90]}")
            prepared["avatar_video"] = cached_avatar_video
            if not cached_avatar_video.get("ready"):
                if progress_callback:
                    progress_callback(
                        index - 1,
                        total,
                        f"Checking cached examiner avatar for question {index}...",
                    )
                ready_questions, readiness_warnings = wait_until_question_avatars_ready(
                    [prepared],
                    timeout_seconds=question_wait_seconds,
                    progress_callback=lambda ready, _total, message, index=index, total=total: progress_callback(
                        index - 1 + ready,
                        total,
                        message.replace("1/1", f"{ready}/1") if message else f"Checking question {index}...",
                    )
                    if progress_callback
                    else None,
                )
                last_readiness_warnings = readiness_warnings
                prepared = ready_questions[0]
            if (prepared.get("avatar_video") or {}).get("ready"):
                store_cached_avatar_asset(text, persistent_config, prepared["avatar_video"])
                prepared_questions.append(prepared)
                avatar_terminal_log(f"cached avatar for question {index} is playable; moving to next question")
                if progress_callback:
                    progress_callback(index, total, f"Question {index} avatar is ready from cache.")
                continue

        for attempt in range(1, generation_attempts + 1):
            prepared = {**question}
            if progress_callback:
                progress_callback(
                    index - 1,
                    total,
                    f"Preparing examiner avatar for question {index} of {total} "
                    f"(attempt {attempt}/{generation_attempts})...",
                )
            try:
                avatar_terminal_log(
                    f"precreating assigned question {index} attempt {attempt}/{generation_attempts}: {text[:90]}"
                )
                spacing_seconds = simli_request_spacing_seconds()
                if requests_sent and spacing_seconds:
                    avatar_terminal_log(
                        f"spacing Simli request for {spacing_seconds:.1f}s before question {index} attempt {attempt}"
                    )
                    if progress_callback:
                        progress_callback(
                            index - 1,
                            total,
                            f"Spacing Simli request for {spacing_seconds:.1f}s to avoid rate limits...",
                        )
                    time.sleep(spacing_seconds)
                requests_sent += 1
                asset = create_avatar_video_asset(
                    text,
                    config=persistent_config,
                    allow_unready=True,
                    check_readiness=False,
                )
                url = str(asset["url"])
                avatar_video = {
                    "source_url": url,
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "asset_key": f"{asset_prefix}_q{index}_attempt{attempt}",
                    "kind": asset.get("kind") or ("hls" if ".m3u8" in url.lower() else "mp4"),
                    "ready": bool(asset.get("ready")),
                    "mp4_url": asset.get("mp4_url"),
                    "hls_url": asset.get("hls_url"),
                    "generation_attempt": attempt,
                }
                if ".m3u8" not in url.lower():
                    try:
                        local_video = cache_avatar_video_file(url)
                        avatar_video["path"] = str(local_video)
                        avatar_video["kind"] = "mp4_file"
                        avatar_video["ready"] = True
                        avatar_terminal_log(f"stored assigned question {index} avatar at {local_video}")
                    except Exception as download_error:
                        warnings.append(
                            f"Question {index} attempt {attempt} avatar URL was created, "
                            f"but the MP4 was not saved locally yet: {download_error}"
                        )
                        avatar_terminal_log(f"stored assigned question {index} as URL only: {download_error}")
                elif asset.get("ready"):
                    avatar_terminal_log(f"stored assigned question {index} as ready HLS stream")
                else:
                    avatar_terminal_log(f"stored assigned question {index} as pending HLS stream")
                prepared["avatar_video"] = avatar_video
                store_cached_avatar_asset(text, persistent_config, avatar_video)
            except Exception as error:
                last_readiness_warnings = [f"Question {index} attempt {attempt} avatar was not created: {error}"]
                avatar_terminal_log(last_readiness_warnings[0])
                if attempt < generation_attempts:
                    backoff_seconds = avatar_generation_backoff_seconds(attempt)
                    avatar_terminal_log(
                        f"backing off for {backoff_seconds:.1f}s before retrying question {index}"
                    )
                    if progress_callback:
                        progress_callback(
                            index - 1,
                            total,
                            f"Simli request failed. Waiting {backoff_seconds:.0f}s before retrying...",
                        )
                    time.sleep(backoff_seconds)
                continue

            if not (prepared.get("avatar_video") or {}).get("ready"):
                if progress_callback:
                    progress_callback(
                        index - 1,
                        total,
                        f"Waiting for question {index} avatar to become playable "
                        f"(attempt {attempt}/{generation_attempts})...",
                    )
                ready_questions, readiness_warnings = wait_until_question_avatars_ready(
                    [prepared],
                    timeout_seconds=question_wait_seconds,
                    progress_callback=lambda ready, _total, message, index=index, total=total: progress_callback(
                        index - 1 + ready,
                        total,
                        message.replace("1/1", f"{ready}/1") if message else f"Waiting for question {index}...",
                    )
                    if progress_callback
                    else None,
                )
                last_readiness_warnings = readiness_warnings
                prepared = ready_questions[0]

            if (prepared.get("avatar_video") or {}).get("ready"):
                question_ready = True
                store_cached_avatar_asset(text, persistent_config, prepared["avatar_video"])
                break

            if attempt < generation_attempts:
                backoff_seconds = avatar_generation_backoff_seconds(attempt)
                avatar_terminal_log(
                    f"question {index} avatar URLs stayed unavailable; retrying with a fresh Simli generation "
                    f"after {backoff_seconds:.1f}s"
                )
                if progress_callback:
                    progress_callback(
                        index - 1,
                        total,
                        f"Avatar URL stayed unavailable. Waiting {backoff_seconds:.0f}s before retrying...",
                    )
                time.sleep(backoff_seconds)

        if not question_ready:
            warnings.extend(f"Question {index}: {warning}" for warning in last_readiness_warnings)
            warnings.append(f"Question {index} avatar did not become playable after {generation_attempts} generation attempt(s).")
            prepared_questions.append(prepared)
            break

        prepared_questions.append(prepared)
        avatar_terminal_log(f"question {index} avatar is playable; moving to next question")
        if progress_callback:
            progress_callback(index, total, f"Question {index} avatar is ready.")

    if len(prepared_questions) < len(questions):
        prepared_questions.extend({**question} for question in questions[len(prepared_questions):])

    return prepared_questions, warnings


def cache_avatar_video_file(url: str) -> Path:
    """Download Simli MP4 once so Streamlit can serve it with normal video controls."""
    video_dir = Path("data/avatar_videos")
    video_dir.mkdir(parents=True, exist_ok=True)
    filename = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24] + ".mp4"
    path = video_dir / filename
    if path.exists() and path.stat().st_size > 0 and is_probably_mp4(path):
        return path
    if path.exists():
        path.unlink(missing_ok=True)

    import requests

    response = requests.get(url, timeout=45)
    if response.status_code >= 400:
        raise RuntimeError(f"Simli video download failed with status {response.status_code}.")
    if not response.content:
        raise RuntimeError("Simli video download returned an empty file.")
    content_type = response.headers.get("Content-Type", "").lower()
    content_preview = response.content[:200].strip()
    if "json" in content_type or content_preview.startswith(b"{"):
        try:
            error_payload = response.json()
        except ValueError:
            error_payload = response.text[:200]
        raise RuntimeError(f"Simli video file is not available yet: {error_payload}")
    path.write_bytes(response.content)
    if not is_probably_mp4(path):
        path.unlink(missing_ok=True)
        raise RuntimeError("Simli returned a file that is not a playable MP4 video yet.")
    return path


def probe_avatar_url(
    url: str,
    *,
    label: str = "avatar",
    timeout_seconds: float = 5.0,
    poll_interval: float = 1.0,
) -> dict:
    """Probe a saved Simli URL and describe whether it currently serves playable media."""
    if not url:
        return {"ready": False, "file_not_found": False, "checked": False}

    import requests

    deadline = time.monotonic() + timeout_seconds
    attempt = 0
    saw_file_not_found = False
    checked = False
    while time.monotonic() <= deadline:
        attempt += 1
        try:
            with requests.get(url, timeout=10, stream=True) as response:
                checked = True
                content_type = response.headers.get("Content-Type", "").lower()
                try:
                    preview = next(response.iter_content(chunk_size=128), b"").strip()
                except StopIteration:
                    preview = b""
                if (
                    response.status_code == 200
                    and preview
                    and "json" not in content_type
                    and not preview.lstrip().startswith(b"{")
                ):
                    avatar_terminal_log(
                        f"{label} URL ready after poll {attempt}: status={response.status_code}, content_type={content_type or 'unknown'}"
                    )
                    return {"ready": True, "file_not_found": False, "checked": True}
                try:
                    preview_text = preview[:80].decode("utf-8", errors="replace")
                except Exception:
                    preview_text = repr(preview[:40])
                if response.status_code == 404 and "File not found" in preview_text:
                    saw_file_not_found = True
                avatar_terminal_log(
                    f"{label} URL still pending; "
                    f"poll={attempt}, status={response.status_code}, "
                    f"content_type={content_type or 'unknown'}, preview={preview_text!r}"
                )
        except requests.RequestException as error:
            avatar_terminal_log(f"{label} URL poll {attempt} request error: {error}")
        time.sleep(poll_interval)
    return {"ready": False, "file_not_found": saw_file_not_found, "checked": checked}


def avatar_url_is_ready(
    url: str,
    *,
    label: str = "avatar",
    timeout_seconds: float = 5.0,
    poll_interval: float = 1.0,
) -> bool:
    """Return True only when a saved Simli URL currently serves video/playlist data."""
    return bool(
        probe_avatar_url(
            url,
            label=label,
            timeout_seconds=timeout_seconds,
            poll_interval=poll_interval,
        ).get("ready")
    )


def refresh_avatar_video_reference(avatar_video: dict | None) -> dict:
    """Update a stored/pending avatar reference if Simli has made it playable."""
    if not avatar_video:
        return {}
    refreshed = dict(avatar_video)
    path = refreshed.get("path")
    if path and Path(path).exists() and is_probably_mp4(Path(path)):
        refreshed["ready"] = True
        refreshed["kind"] = "mp4_file"
        return refreshed

    candidate_urls: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    for label, value in (
        ("source", refreshed.get("source_url")),
        ("hls", refreshed.get("hls_url")),
        ("mp4", refreshed.get("mp4_url")),
    ):
        if not value:
            continue
        url = str(value)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        candidate_urls.append((label, url))
    file_not_found_count = 0
    checked_count = 0
    for label, url in candidate_urls:
        probe = probe_avatar_url(url, label=label, timeout_seconds=4.0)
        if probe.get("checked"):
            checked_count += 1
        if probe.get("file_not_found"):
            file_not_found_count += 1
        if not probe.get("ready"):
            continue
        refreshed["source_url"] = url
        refreshed["ready"] = True
        refreshed.pop("terminal_file_not_found", None)
        if ".m3u8" in url.lower():
            refreshed["kind"] = "hls"
            return refreshed
        try:
            local_video = cache_avatar_video_file(url)
        except Exception:
            refreshed["kind"] = "mp4"
            return refreshed
        refreshed["path"] = str(local_video)
        refreshed["kind"] = "mp4_file"
        return refreshed

    refreshed["ready"] = False
    refreshed["terminal_file_not_found"] = bool(candidate_urls and checked_count == len(candidate_urls) and file_not_found_count == len(candidate_urls))
    if refreshed.get("kind") in {"hls", "mp4"}:
        refreshed["kind"] = f"{refreshed['kind']}_pending"
    return refreshed


def wait_until_question_avatars_ready(
    questions: list[dict],
    *,
    timeout_seconds: float = 240.0,
    progress_callback=None,
) -> tuple[list[dict], list[str]]:
    """Keep checking prepared avatar URLs until every question is playable or timeout expires."""
    started_at = time.monotonic()
    deadline = started_at + max(0.0, timeout_seconds)
    try:
        file_not_found_retry_seconds = float(os.getenv("AVATAR_FILE_NOT_FOUND_RETRY_SECONDS", "60"))
    except ValueError:
        file_not_found_retry_seconds = 60.0
    file_not_found_retry_seconds = max(15.0, file_not_found_retry_seconds)
    warnings: list[str] = []
    total = len(questions)

    while True:
        ready_count = 0
        refreshed_questions: list[dict] = []
        pending_numbers: list[str] = []
        terminal_file_not_found_numbers: list[str] = []

        for index, question in enumerate(questions, 1):
            refreshed = {**question}
            avatar_video = refresh_avatar_video_reference(refreshed.get("avatar_video") or {})
            refreshed["avatar_video"] = avatar_video
            if avatar_video.get("ready"):
                ready_count += 1
            else:
                pending_numbers.append(str(index))
                if avatar_video.get("terminal_file_not_found"):
                    terminal_file_not_found_numbers.append(str(index))
            refreshed_questions.append(refreshed)

        questions = refreshed_questions
        if progress_callback:
            progress_callback(
                ready_count,
                total,
                f"{ready_count}/{total} examiner avatar video(s) ready"
                + (f" — still waiting for question(s) {', '.join(pending_numbers)}" if pending_numbers else ""),
            )

        if ready_count == total:
            return questions, warnings

        if pending_numbers and set(terminal_file_not_found_numbers) == set(pending_numbers):
            elapsed = time.monotonic() - started_at
            if elapsed >= file_not_found_retry_seconds:
                warnings.append(
                    "`404 File not found` persisted long enough to retry with a fresh Simli generation. "
                    f"Pending question(s): {', '.join(pending_numbers)}."
                )
                return questions, warnings
            avatar_terminal_log(
                "Avatar URLs are still returning `404 File not found`; waiting briefly before retrying. "
                f"Pending question(s): {', '.join(pending_numbers)}."
            )

        if time.monotonic() >= deadline:
            warnings.append(
                "Avatar preparation timed out before every question became playable. "
                f"Still pending: question(s) {', '.join(pending_numbers)}."
            )
            return questions, warnings

        time.sleep(5)


def render_avatar_video_file(
    path: str | Path,
    *,
    element_key: str,
    subtitle: str = "",
    auto_play: bool = False,
) -> bool:
    try:
        local_video = Path(path)
        if not local_video.exists() or not is_probably_mp4(local_video):
            return False
        video_base64 = base64.b64encode(local_video.read_bytes()).decode("ascii")
    except Exception:
        return False

    subtitle_html = html_escape(subtitle)
    safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", element_key)
    safe_id_json = json.dumps(safe_id)
    autoplay_attr = "autoplay" if auto_play else ""
    autoplay_script = (
        f"""
        <script>
          const video = document.getElementById({safe_id_json});
          if (video) {{
            const playPromise = video.play();
            if (playPromise && typeof playPromise.catch === "function") {{
              playPromise.catch(() => {{}});
            }}
          }}
        </script>
        """
        if auto_play
        else ""
    )
    components.html(
        f"""
        <style>
          .avatar-native-card {{
            max-width: 620px;
            margin: 0.75rem auto 0.75rem;
            border: 1px solid #cfe3d5;
            border-radius: 18px;
            overflow: hidden;
            background: #fbfffc;
            box-shadow: 0 16px 34px rgba(37, 72, 53, 0.12);
            font-family: Aptos, Segoe UI, sans-serif;
          }}
          .avatar-native-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem 0.95rem;
            background: linear-gradient(135deg, #effbf3, #dff2e7);
            color: #203b36;
            font-weight: 750;
          }}
          .avatar-native-header span:last-child {{
            color: #5b9d73;
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
          }}
          .avatar-native-video {{
            width: 100%;
            aspect-ratio: 16 / 10;
            display: block;
            background: #eef7f0;
            object-fit: contain;
          }}
          .avatar-native-subtitle {{
            padding: 0.9rem 1rem;
            border-top: 1px solid #cfe3d5;
            background: rgba(255, 255, 253, 0.97);
            color: #203b36;
            line-height: 1.45;
            font-size: 0.98rem;
          }}
          .avatar-native-help {{
            padding: 0 1rem 0.85rem;
            color: #587267;
            font-size: 0.82rem;
          }}
        </style>
        <div class="avatar-native-card">
          <div class="avatar-native-header">
            <span>AI Examiner</span>
            <span>{'Speaking' if auto_play else 'Ready'}</span>
          </div>
          <video id="{safe_id}" class="avatar-native-video" controls preload="auto" playsinline {autoplay_attr}>
            <source src="data:video/mp4;base64,{video_base64}" type="video/mp4">
            Your browser cannot play this examiner video.
          </video>
          <div class="avatar-native-subtitle"><strong>Subtitles:</strong> {subtitle_html}</div>
          <div class="avatar-native-help">{'If the examiner does not start automatically, press play.' if auto_play else 'Press the video play button to hear the examiner. Use the fullscreen control if needed.'}</div>
        </div>
        {autoplay_script}
        """,
        height=520,
        scrolling=False,
    )
    return True


def is_probably_mp4(path: Path) -> bool:
    """Reject cached JSON/API error files that were saved with a .mp4 extension."""
    try:
        header = path.read_bytes()[:64]
    except OSError:
        return False
    if not header:
        return False
    if header.lstrip().startswith(b"{"):
        return False
    return b"ftyp" in header or header.startswith(b"\x00\x00")


def render_avatar_video(url: str, *, element_key: str, subtitle: str = "", auto_play: bool = False) -> bool:
    subtitle_html = html_escape(subtitle)
    is_hls = ".m3u8" in url.lower()
    if not is_hls:
        try:
            local_video = cache_avatar_video_file(url)
            return render_avatar_video_file(
                local_video,
                element_key=element_key,
                subtitle=subtitle,
                auto_play=auto_play,
            )
        except Exception as error:
            cache = st.session_state.setdefault("simli_avatar_cache", {})
            for cached_key, cached_url in list(cache.items()):
                if cached_url == url:
                    cache.pop(cached_key, None)
            st.warning(f"The examiner video was generated but could not be loaded into the page: {error}")
            st.caption("The question is still shown below so the assessment can continue. Try reloading the examiner video in a moment.")
            return False

    safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", element_key)
    safe_id_json = json.dumps(safe_id)
    url_json = json.dumps(url)
    is_hls_json = json.dumps(is_hls)
    autoplay_json = json.dumps(auto_play)
    components.html(
        f"""
        <style>
          .avatar-pop-card {{
            max-width: 560px;
            margin: 0.75rem auto 1rem;
            border: 1px solid #cfe3d5;
            border-radius: 20px;
            overflow: hidden;
            background: #fbfffc;
            box-shadow: 0 18px 38px rgba(37,72,53,.16);
            font-family: Aptos, Segoe UI, sans-serif;
          }}
          .avatar-pop-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.7rem 0.9rem;
            background: linear-gradient(135deg, #effbf3, #dff2e7);
            color: #203b36;
            font-weight: 750;
          }}
          .avatar-pop-video {{
            width: 100%;
            aspect-ratio: 16 / 10;
            display: block;
            background: #eef7f0;
            object-fit: contain;
          }}
          .avatar-pop-subtitle {{
            padding: 0.85rem 1rem 1rem;
            color: #203b36;
            background: rgba(255,255,253,.97);
            font-size: 1rem;
            line-height: 1.45;
            border-top: 1px solid #dcefe3;
          }}
          .avatar-pop-label {{
            color: #5b9d73;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: .08em;
          }}
        </style>
        <div class="avatar-pop-card">
          <div class="avatar-pop-header">
            <span>AI Examiner</span>
            <span class="avatar-pop-label">{'Speaking' if auto_play else 'Ready'}</span>
          </div>
          <video id="{safe_id}" class="avatar-pop-video" controls preload="metadata" playsinline></video>
          <div class="avatar-pop-subtitle">{subtitle_html}</div>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
        <script>
          const video = document.getElementById({safe_id_json});
          const src = {url_json};
          const isHls = {is_hls_json};
          const shouldAutoplay = {autoplay_json};
          function tryAutoplay() {{
            if (!shouldAutoplay || !video) return;
            video.autoplay = true;
            const playPromise = video.play();
            if (playPromise && typeof playPromise.catch === "function") {{
              playPromise.catch(() => {{}});
            }}
          }}
          if (!isHls) {{
            video.src = src;
            video.addEventListener("loadedmetadata", tryAutoplay, {{ once: true }});
          }} else if (video.canPlayType("application/vnd.apple.mpegurl")) {{
            video.src = src;
            video.addEventListener("loadedmetadata", tryAutoplay, {{ once: true }});
          }} else if (window.Hls && window.Hls.isSupported()) {{
            const hls = new Hls();
            hls.loadSource(src);
            hls.attachMedia(video);
            hls.on(Hls.Events.MANIFEST_PARSED, tryAutoplay);
          }} else {{
            video.outerHTML = '<p style="padding:1rem;color:#203b36;font-family:Segoe UI,sans-serif;">Avatar video is ready, but this browser cannot play the stream.</p>';
          }}
        </script>
        """,
        height=540,
        scrolling=False,
    )
    st.caption("If the examiner video does not load, open the returned Simli stream in a new tab.")
    st.link_button("Open examiner stream", url, width="stretch")
    return True


def combined_guided_response(guidance: dict, follow_up_response: str) -> str:
    return (
        f"First response: {guidance.get('original_response', '')}\n\n"
        f"Response after examiner follow-up: {follow_up_response.strip()}"
    )


def render_recorded_response(result: dict) -> None:
    """Show the response trail when the one permitted examiner prompt was used."""
    guided_attempt = result.get("guided_attempt")
    if not guided_attempt:
        st.write("**Student response:**", result.get("student_response", ""))
        if result.get("audio_path"):
            st.audio(result["audio_path"])
        render_delivery_indicators(result.get("delivery_indicators"))
        return
    st.write("**First response:**", guided_attempt.get("original_response", ""))
    if guided_attempt.get("original_audio_path"):
        st.caption("First recording")
        st.audio(guided_attempt["original_audio_path"])
    render_delivery_indicators(guided_attempt.get("original_delivery_indicators"))
    st.write("**Examiner's guiding question:**", guided_attempt.get("follow_up_question", ""))
    st.write("**Response after guidance:**", guided_attempt.get("follow_up_response", ""))
    if guided_attempt.get("reason"):
        st.caption(f"Guidance reason: {guided_attempt['reason']}")
    if result.get("audio_path"):
        st.caption("Recording after guidance")
        st.audio(result["audio_path"])
    render_delivery_indicators(result.get("delivery_indicators"))


def render_examiner_feedback_note(review: dict | None) -> None:
    """Show the examiner's typed feedback in the released student results view."""
    note = str((review or {}).get("note") or "").strip()
    if not note:
        return
    st.markdown(
        f"""
        <div class="assessment-help-card">
            <strong>Examiner feedback:</strong><br>
            {html_escape(note)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_delivery_indicators(indicators: dict | None) -> None:
    if not indicators:
        return
    st.caption(indicators.get("disclaimer", "Automated delivery indicators are advisory only."))
    if indicators.get("status") != "available":
        return
    col1, col2, col3 = st.columns(3)
    col1.metric("Recording", f"{indicators.get('duration_seconds', 0)}s")
    col2.metric("Estimated pace", f"{indicators.get('words_per_minute', '—')} wpm")
    pitch = indicators.get("pitch_range_semitones")
    col3.metric("Pitch variation", f"{pitch} semitones" if pitch is not None else "Unavailable")
    for note in indicators.get("notes", []):
        st.caption(note)


def render_student_processing_overlay(title: str, message: str) -> None:
    st.markdown(
        f"""
        <style>
        .student-processing-overlay {{
            position: fixed;
            inset: 0;
            z-index: 999999;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 2rem;
            background: rgba(247, 252, 248, 0.96);
        }}
        .student-processing-box {{
            width: min(620px, 92vw);
            display: flex;
            align-items: center;
            gap: 1.2rem;
            padding: 1.45rem 1.55rem;
            border: 1px solid #cfe3d5;
            border-radius: 18px;
            background: #fffffb;
            box-shadow: 0 18px 42px rgba(37, 72, 53, 0.16);
            font-family: Aptos, Segoe UI, sans-serif;
        }}
        .student-processing-box h3 {{
            margin: 0 0 0.3rem;
            color: #203b36;
            font-size: 1.28rem;
            line-height: 1.2;
        }}
        .student-processing-box p {{
            margin: 0;
            color: #587267;
            font-size: 1rem;
            line-height: 1.45;
        }}
        </style>
        <div class="student-processing-overlay" role="status" aria-live="polite">
          <div class="student-processing-box">
            <div class="prep-loader"></div>
            <div>
              <h3>{html_escape(title)}</h3>
              <p>{html_escape(message)}</p>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def discard_voice_preview(preview_key: str) -> None:
    """Delete an unsubmitted recording and its transcript only from session storage."""
    preview = st.session_state.pop(preview_key, None)
    if not preview:
        return
    sessions_dir = Path("data/sessions").resolve()
    for field in ("audio_path", "transcription_path"):
        value = preview.get(field)
        if not value:
            continue
        try:
            path = Path(value).resolve()
            path.relative_to(sessions_dir)
            path.unlink(missing_ok=True)
        except (OSError, ValueError):
            continue


class LockedAudioRecording:
    """Small adapter for a one-time browser recording saved in session state."""

    def __init__(self, data: bytes, name: str = "speech.wav") -> None:
        self._data = data
        self.name = name or "speech.wav"

    def getbuffer(self) -> bytes:
        return self._data


def discard_locked_recording(recording_key: str) -> None:
    st.session_state.pop(recording_key, None)


def capture_student_response(
    key_suffix: str,
    submit_label: str,
    *,
    allow_skip: bool = True,
    skip_label: str = "Skip question",
    review_transcript: bool = True,
    include_delivery: bool = True,
) -> dict | None:
    """Collect a browser microphone recording and transcript for grading."""
    if not hasattr(st, "audio_input"):
        st.error("Microphone answers require a newer Streamlit version with browser audio input.")
        return None
    st.markdown('<div class="portal-field-label">Speak into the microphone</div>', unsafe_allow_html=True)
    allow_rerecord = bool_env("ALLOW_STUDENT_RERECORD", False)
    if not allow_rerecord:
        st.warning(
            "This is a one-time recording. Start only when you are ready, and do not stop the recording until you have completed your answer."
        )
    if review_transcript:
        st.caption("Record once, transcribe it, then review what the system heard before submitting.")
    else:
        st.caption("Record once, then submit it. The system will process it and continue automatically.")
    preview_key = f"voice_preview_{key_suffix}"
    recording_key = f"voice_locked_recording_{key_suffix}"
    locked_recording = st.session_state.get(recording_key)

    if locked_recording:
        st.info("Recording captured for this attempt. Submit it to continue.")
        st.audio(locked_recording["bytes"], format=locked_recording.get("mime") or "audio/wav")
        recording = LockedAudioRecording(
            locked_recording["bytes"],
            locked_recording.get("name") or "speech.wav",
        )
        recording_fingerprint = locked_recording["fingerprint"]
    else:
        recording = st.audio_input("Record your answer", key=f"voice_response_{key_suffix}")
        recording_fingerprint = None
        if recording:
            recording_bytes = recording.getvalue()
            recording_fingerprint = hashlib.sha256(recording_bytes).hexdigest()
            st.session_state[recording_key] = {
                "bytes": recording_bytes,
                "fingerprint": recording_fingerprint,
                "name": getattr(recording, "name", "speech.wav"),
                "mime": getattr(recording, "type", "audio/wav"),
            }
            st.rerun()

    preview = st.session_state.get(preview_key)
    if preview and preview.get("fingerprint") != recording_fingerprint:
        # A fresh recording must be transcribed before it can replace the prior preview.
        discard_voice_preview(preview_key)
        preview = None

    if not preview:
        columns = st.columns(2) if allow_skip else st.columns(1)
        action_label = "Transcribe recording" if review_transcript else submit_label
        submit_recording = columns[0].button(
            action_label, type="primary", width="stretch", key=f"transcribe_voice_{key_suffix}"
        )
        skipped = columns[1].button(skip_label, width="stretch", key=f"skip_voice_{key_suffix}") if allow_skip else False
        if skipped:
            discard_locked_recording(recording_key)
            return {"text": "[Skipped question]", "skipped": True, "mode": "voice"}
        if not submit_recording:
            return None
        if not recording:
            st.warning("Record an answer before submitting it.")
            return None
        try:
            spinner_text = "Processing your answer..." if not review_transcript else "Transcribing your recording..."
            render_student_processing_overlay(
                "Submitting recording",
                spinner_text,
            )
            voice = transcribe_streamlit_audio(recording, include_delivery=include_delivery)
        except Exception as error:
            discard_locked_recording(recording_key)
            st.error(f"Your recording could not be transcribed: {error}")
            return None
        if not review_transcript:
            discard_locked_recording(recording_key)
            return {"fingerprint": recording_fingerprint, "skipped": False, **voice}
        st.session_state[preview_key] = {"fingerprint": recording_fingerprint, **voice}
        st.rerun()

    st.success("Check the transcript before submitting it for grading.")
    st.text_area(
        "What the system heard",
        value=preview["text"],
        height=120,
        disabled=True,
        key=f"transcript_preview_{key_suffix}",
    )
    render_delivery_indicators(preview.get("delivery_indicators"))
    columns = st.columns(3) if allow_skip and allow_rerecord else st.columns(2) if allow_rerecord else st.columns(2 if allow_skip else 1)
    use_transcript = columns[0].button(submit_label, type="primary", width="stretch", key=f"use_voice_{key_suffix}")
    retry = columns[1].button("Record again", width="stretch", key=f"retry_voice_{key_suffix}") if allow_rerecord else False
    skip_column = columns[2] if allow_skip and allow_rerecord else columns[1] if allow_skip else None
    skipped = skip_column.button(skip_label, width="stretch", key=f"skip_review_voice_{key_suffix}") if skip_column else False
    if retry:
        discard_voice_preview(preview_key)
        discard_locked_recording(recording_key)
        st.info("Record a replacement answer, then choose Transcribe recording again.")
        return None
    if skipped:
        discard_voice_preview(preview_key)
        discard_locked_recording(recording_key)
        return {"text": "[Skipped question]", "skipped": True, "mode": "voice"}
    if not use_transcript:
        return None
    st.session_state.pop(preview_key, None)
    discard_locked_recording(recording_key)
    return {"text": preview["text"], "skipped": False, "mode": "voice", **preview}


def apply_portal_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --portal-ink: #203b36;
            --portal-muted: #587267;
            --portal-mint: #5b9d73;
            --portal-paper: #fbfdf9;
        }
        html, body, [class*="css"] {
            font-family: "Aptos", "Segoe UI", "Trebuchet MS", sans-serif;
            font-size: 17px;
        }
        [data-testid="stAppViewContainer"] {
            background: radial-gradient(circle at 14% 12%, #dff4e4 0, #eff8f0 30%, #fbfcf8 67%, #eaf4ec 100%);
            color: var(--portal-ink);
        }
        [data-testid="stHeader"] { background: transparent; }
        [data-testid="stMainBlockContainer"] {
            max-width: 1180px;
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #f7fffa, #e3f5e8);
            border-right: 1px solid #cce4d3;
        }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
        [data-testid="stSidebar"] p { color: #294238; }
        h1, h2, h3 {
            color: var(--portal-ink) !important;
            font-family: "Trebuchet MS", "Aptos Display", "Segoe UI", sans-serif;
            font-weight: 700;
            letter-spacing: -0.025em;
        }
        p, li, label, [data-testid="stMarkdownContainer"] {
            color: var(--portal-ink);
            font-size: 1.03rem;
            line-height: 1.55;
        }
        [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {
            font-size: 0.96rem !important;
            line-height: 1.45 !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"],
        [data-testid="stExpander"] {
            background: rgba(255, 255, 253, 0.88) !important;
            border-color: #d6e7da !important;
            border-radius: 14px !important;
            box-shadow: 0 6px 18px rgba(37, 72, 53, 0.05) !important;
        }
        [data-testid="stExpander"] details,
        [data-testid="stExpander"] details > summary,
        [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
            background: transparent !important;
            color: var(--portal-ink) !important;
        }
        [data-testid="stExpander"] details > summary:hover {
            background: rgba(223, 242, 230, 0.65) !important;
            border-radius: 12px !important;
        }
        [data-testid="stExpander"] summary *,
        [data-testid="stExpander"] [data-testid="stMarkdownContainer"] *,
        [data-testid="stExpander"] p,
        [data-testid="stExpander"] li {
            color: var(--portal-ink) !important;
        }
        [data-testid="stForm"],
        [data-testid="stForm"] > div {
            background: rgba(255, 255, 253, 0.72) !important;
            border-color: #d8eadc !important;
            border-radius: 12px !important;
        }
        [data-testid="stMetric"] {
            background: #f8fffa;
            border: 1px solid #d9eadc;
            border-radius: 12px;
            padding: 0.7rem 0.85rem;
        }
        [data-testid="stMetricLabel"], [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {
            color: var(--portal-muted) !important;
        }
        .stButton > button, .stFormSubmitButton > button, .stLinkButton > a, .stDownloadButton > button {
            min-height: 2.65rem;
            border: 0;
            border-radius: 8px;
            background: #273940;
            color: #ffffff;
            font-weight: 600;
            transition: background 0.18s ease, transform 0.18s ease;
        }
        .stButton > button *, .stFormSubmitButton > button *, .stLinkButton > a *, .stDownloadButton > button * { color: #ffffff !important; }
        .stButton > button:hover, .stFormSubmitButton > button:hover, .stLinkButton > a:hover, .stDownloadButton > button:hover {
            background: #365e4a;
            color: #ffffff;
            transform: translateY(-1px);
        }
        .stButton > button:disabled { background: #c8d5cd; color: #77877d; }
        [data-baseweb="input"] > div,
        [data-baseweb="select"] > div,
        [data-baseweb="textarea"] > div {
            background: rgba(255, 255, 253, 0.96) !important;
            border-color: #cedfd3 !important;
            border-radius: 8px !important;
        }
        [data-baseweb="input"] input,
        [data-baseweb="textarea"] textarea,
        [data-baseweb="select"] * {
            color: var(--portal-ink) !important;
            font-family: "Aptos", "Segoe UI", "Trebuchet MS", sans-serif !important;
            font-size: 1.03rem !important;
            line-height: 1.5 !important;
        }
        [data-baseweb="select"] svg,
        [data-baseweb="select"] svg path {
            color: #4f8b68 !important;
            fill: #4f8b68 !important;
        }
        [data-baseweb="popover"] [role="listbox"],
        [data-baseweb="popover"] [data-baseweb="menu"],
        [role="listbox"],
        ul[role="listbox"] {
            background: #fbfffc !important;
            border: 1px solid #cfe3d5 !important;
            border-radius: 10px !important;
            box-shadow: 0 12px 26px rgba(37, 72, 53, 0.12) !important;
            color: var(--portal-ink) !important;
        }
        [data-baseweb="popover"] [role="option"],
        [data-baseweb="menu"] li,
        [role="listbox"] [role="option"],
        li[role="option"] {
            background: #fbfffc !important;
            color: var(--portal-ink) !important;
        }
        [data-baseweb="popover"] [role="option"]:hover,
        [data-baseweb="popover"] [aria-selected="true"],
        [role="listbox"] [role="option"]:hover,
        [role="listbox"] [aria-selected="true"] {
            background: #e6f5eb !important;
            color: #234a38 !important;
        }
        [data-baseweb="input"] input::placeholder,
        [data-baseweb="textarea"] textarea::placeholder {
            color: #7d9388 !important;
            opacity: 1;
        }
        [data-testid="stNumberInput"] [data-baseweb="input"],
        [data-testid="stNumberInput"] [data-baseweb="input"] > div,
        [data-testid="stNumberInput"] [data-baseweb="base-input"],
        [data-testid="stNumberInput"] input,
        [data-testid="stNumberInput"] button,
        [data-testid="stTextArea"] [data-baseweb="textarea"],
        [data-testid="stTextArea"] [data-baseweb="textarea"] > div {
            background: rgba(255, 255, 253, 0.96) !important;
            border-color: #cedfd3 !important;
            color: var(--portal-ink) !important;
        }
        [data-testid="stNumberInput"] button,
        [data-testid="stNumberInput"] button:hover,
        [data-testid="stNumberInput"] button:focus {
            background: #eef8f1 !important;
            border-color: #cedfd3 !important;
            color: #3f7657 !important;
            box-shadow: none !important;
            transform: none !important;
        }
        [data-testid="stNumberInput"] button *,
        [data-testid="stNumberInput"] button svg,
        [data-testid="stNumberInput"] button svg path {
            color: #3f7657 !important;
            fill: #3f7657 !important;
        }
        [data-testid="stNumberInput"] input {
            -webkit-text-fill-color: var(--portal-ink) !important;
        }
        [data-testid="stForm"] [data-testid="stNumberInput"],
        [data-testid="stForm"] [data-testid="stTextArea"],
        [data-testid="stForm"] [data-testid="stFormSubmitButton"] {
            background: transparent !important;
            color: var(--portal-ink) !important;
        }
        [data-testid="stForm"] label,
        [data-testid="stForm"] p,
        [data-testid="stForm"] span {
            color: var(--portal-ink) !important;
        }
        [data-testid="stTextArea"] textarea:disabled,
        [data-testid="stTextArea"] textarea[disabled],
        [data-testid="stTextArea"] [data-baseweb="textarea"] textarea:disabled,
        [data-testid="stTextArea"] [data-baseweb="textarea"] textarea[disabled] {
            color: var(--portal-ink) !important;
            -webkit-text-fill-color: var(--portal-ink) !important;
            opacity: 1 !important;
            background: transparent !important;
        }
        [data-testid="stTextArea"] [data-baseweb="textarea"]:has(textarea:disabled),
        [data-testid="stTextArea"] [data-baseweb="textarea"]:has(textarea[disabled]) {
            background: rgba(255, 255, 253, 0.96) !important;
            opacity: 1 !important;
        }
        [data-testid="stNumberInput"] button {
            background: #eff9f2 !important;
            border-color: #bfd8c7 !important;
            color: #2f5a45 !important;
            box-shadow: none !important;
        }
        [data-testid="stNumberInput"] button:hover {
            background: #dff2e6 !important;
            border-color: #83b996 !important;
        }
        [data-testid="stFileUploader"] section {
            background: rgba(255, 255, 253, 0.92) !important;
            border: 1px solid #cfe3d5 !important;
            border-radius: 12px !important;
            box-shadow: 0 8px 20px rgba(37, 72, 53, 0.05) !important;
        }
        [data-testid="stFileUploader"] section:hover {
            border-color: #8fc7a3 !important;
            background: #fbfffc !important;
        }
        [data-testid="stFileUploader"] section *,
        [data-testid="stFileUploader"] [data-testid="stMarkdownContainer"] p {
            color: var(--portal-ink) !important;
        }
        [data-testid="stFileUploader"] section small,
        [data-testid="stFileUploader"] section span {
            color: var(--portal-muted) !important;
        }
        [data-testid="stFileUploader"] section button {
            background: #eff9f2 !important;
            border: 1px solid #bfd8c7 !important;
            border-radius: 8px !important;
            color: #2f5a45 !important;
            box-shadow: none !important;
        }
        [data-testid="stFileUploader"] section button:hover {
            background: #dff2e6 !important;
            border-color: #83b996 !important;
            color: #234a38 !important;
        }
        [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"],
        [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] > div,
        [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] div,
        [data-testid="stFileUploader"] [class*="e3v525e7"],
        [data-testid="stFileUploader"] [class*="e3v525e7"] > div,
        [data-testid="stFileUploader"] [class*="e3v525e7"] [role="list"],
        [data-testid="stFileUploader"] [class*="e3v525e7"] [role="listitem"],
        [data-testid="stFileUploader"] [class*="e3v525e7"] button,
        [data-testid="stFileUploader"] div:has([data-testid="stFileUploaderFile"]),
        [data-testid="stFileUploader"] div:has(> [data-testid="stFileUploaderFile"]),
        [data-testid="stFileUploader"] li,
        [data-testid="stFileUploader"] li > div {
            background: #eafff1 !important;
            background-color: #eafff1 !important;
            border-color: #cfe3d5 !important;
            color: var(--portal-ink) !important;
            box-shadow: none !important;
        }
        [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] *,
        [data-testid="stFileUploader"] [class*="e3v525e7"] *,
        [data-testid="stFileUploader"] li *,
        [data-testid="stFileUploader"] div:has([data-testid="stFileUploaderFile"]) * {
            color: var(--portal-ink) !important;
            -webkit-text-fill-color: var(--portal-ink) !important;
        }
        [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] small,
        [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] span,
        [data-testid="stFileUploader"] [class*="e3v525e7"] small,
        [data-testid="stFileUploader"] [class*="e3v525e7"] span,
        [data-testid="stFileUploader"] div:has([data-testid="stFileUploaderFile"]) small,
        [data-testid="stFileUploader"] div:has([data-testid="stFileUploaderFile"]) span {
            color: #31614a !important;
            -webkit-text-fill-color: #31614a !important;
        }
        [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] button,
        [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzoneInstructions"] + button,
        [data-testid="stFileUploader"] [class*="e3v525e7"] button,
        [data-testid="stFileUploader"] div:has([data-testid="stFileUploaderFile"]) button,
        [data-testid="stFileUploader"] [aria-label*="Remove"],
        [data-testid="stFileUploader"] [aria-label*="Delete"] {
            background: #f3fff6 !important;
            background-color: #f3fff6 !important;
            border: 1px solid #bfd8c7 !important;
            color: #2f5a45 !important;
            box-shadow: none !important;
        }
        [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] button:hover,
        [data-testid="stFileUploader"] [class*="e3v525e7"] button:hover,
        [data-testid="stFileUploader"] div:has([data-testid="stFileUploaderFile"]) button:hover,
        [data-testid="stFileUploader"] [aria-label*="Remove"]:hover,
        [data-testid="stFileUploader"] [aria-label*="Delete"]:hover {
            background: #dff2e6 !important;
            border-color: #83b996 !important;
        }
        [data-testid="stFileUploader"] svg,
        [data-testid="stFileUploader"] svg path,
        [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] svg,
        [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] svg path,
        [data-testid="stFileUploader"] [class*="e3v525e7"] svg,
        [data-testid="stFileUploader"] [class*="e3v525e7"] svg path {
            color: #4f8b68 !important;
            fill: #4f8b68 !important;
        }
        [data-testid="stTooltipIcon"],
        [data-testid="stTooltipIcon"] svg,
        [data-testid="stTooltipIcon"] svg path {
            color: #5f9f78 !important;
            fill: #5f9f78 !important;
        }
        [data-baseweb="tooltip"],
        [role="tooltip"] {
            background: #fbfffc !important;
            border: 1px solid #cfe3d5 !important;
            border-radius: 10px !important;
            box-shadow: 0 10px 24px rgba(37, 72, 53, 0.12) !important;
            color: var(--portal-ink) !important;
        }
        [data-baseweb="tooltip"] *,
        [role="tooltip"] * {
            color: var(--portal-ink) !important;
        }
        [data-baseweb="popover"],
        [data-baseweb="popover"] > div,
        [data-baseweb="popover"] [data-testid="stTooltipContent"],
        [data-testid="stTooltipContent"] {
            background: #fbfffc !important;
            background-color: #fbfffc !important;
            border-color: #cfe3d5 !important;
            color: var(--portal-ink) !important;
            box-shadow: 0 10px 24px rgba(37, 72, 53, 0.12) !important;
        }
        [data-baseweb="popover"] *,
        [data-testid="stTooltipContent"] * {
            color: var(--portal-ink) !important;
        }
        [data-baseweb="popover"] svg,
        [data-baseweb="popover"] svg path {
            color: #fbfffc !important;
            fill: #fbfffc !important;
        }
        [data-testid="stTextInputRootElement"]:has(input[type="password"]),
        [data-testid="stTextInputRootElement"]:has(input[type="password"]) [data-baseweb="base-input"] {
            background: rgba(255, 255, 253, 0.96) !important;
            border-radius: 8px !important;
            overflow: hidden !important;
        }
        [data-testid="stTextInputRootElement"] input[type="password"] {
            background: transparent !important;
            width: 100% !important;
            padding-right: 2.35rem !important;
        }
        [data-testid="stTextInputRootElement"] input[type="password"] + button,
        [data-testid="stTextInputRootElement"]:has(input[type="password"]) button,
        [data-testid="stTextInputRootElement"] button[aria-label="Show password text"],
        [data-testid="stTextInputRootElement"] button[aria-label="Hide password text"],
        [data-testid="stTextInputRootElement"] button[title="Show password text"],
        [data-testid="stTextInputRootElement"] button[title="Hide password text"] {
            display: inline-flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            width: 2.2rem !important;
            min-width: 2.2rem !important;
            flex: 0 0 2.2rem !important;
            align-items: center !important;
            justify-content: center !important;
            padding: 0 !important;
            margin: 0 !important;
            border: 0 !important;
            background: transparent !important;
            background-color: transparent !important;
            box-shadow: none !important;
            color: #789086 !important;
        }
        [data-testid="stTextInputRootElement"]:has(input[type="password"]) button:hover,
        [data-testid="stTextInputRootElement"]:has(input[type="password"]) button:focus {
            background: rgba(91, 157, 115, 0.10) !important;
            background-color: rgba(91, 157, 115, 0.10) !important;
            border-radius: 7px !important;
            outline: none !important;
        }
        [data-testid="stTextInputRootElement"]:has(input[type="password"]) button svg,
        [data-testid="stTextInputRootElement"]:has(input[type="password"]) button svg path {
            color: #789086 !important;
            fill: #789086 !important;
        }
        [data-testid="stTextInputRootElement"] input[type="password"]::-ms-reveal,
        [data-testid="stTextInputRootElement"] input[type="password"]::-ms-clear {
            display: none;
        }
        [data-testid="stWidgetLabel"],
        [data-testid="stWidgetLabel"] p,
        [data-testid="stWidgetLabel"] label,
        [data-testid="stTextInput"] label,
        [data-testid="stRadio"] label,
        [data-testid="stRadio"] label p {
            color: #365248 !important;
            font-family: "Aptos", "Segoe UI", "Trebuchet MS", sans-serif !important;
            font-weight: 600;
        }
        [data-testid="stTabs"] [role="tab"] { color: #5b7165; font-weight: 600; }
        [data-testid="stTabs"] [aria-selected="true"] { color: #273940; }
        [data-testid="stTabs"] [data-baseweb="tab-highlight"] { background-color: #273940; }
        [data-testid="stRadio"] [role="radiogroup"] {
            gap: 0.55rem !important;
            align-items: center !important;
        }
        [data-testid="stRadio"] [role="radiogroup"] label,
        [data-testid="stRadio"] [role="radio"] {
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            min-height: 2.65rem !important;
            min-width: 6.1rem !important;
            padding: 0 1rem !important;
            border: 0 !important;
            border-radius: 8px !important;
            background: #273940 !important;
            color: #ffffff !important;
            box-shadow: none !important;
            cursor: pointer !important;
            transition: background 0.18s ease, transform 0.18s ease !important;
        }
        [data-testid="stRadio"] [role="radiogroup"] label:hover,
        [data-testid="stRadio"] [role="radio"]:hover,
        [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked),
        [data-testid="stRadio"] [role="radio"][aria-checked="true"],
        [data-testid="stRadio"] [role="radio"]:has(input:checked),
        [data-testid="stRadio"] [data-checked="true"] {
            background: #365e4a !important;
            color: #ffffff !important;
            transform: translateY(-1px);
        }
        [data-testid="stRadio"] [role="radiogroup"] label *,
        [data-testid="stRadio"] [role="radio"] *,
        [data-testid="stRadio"] [data-checked="true"] * {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
        }
        [data-testid="stRadio"] [role="radiogroup"] label input,
        [data-testid="stRadio"] [role="radiogroup"] label svg,
        [data-testid="stRadio"] [role="radiogroup"] label > div:first-child,
        [data-testid="stRadio"] [role="radiogroup"] label [data-baseweb="radio"],
        [data-testid="stRadio"] [role="radio"] input,
        [data-testid="stRadio"] [role="radio"] svg,
        [data-testid="stRadio"] [role="radio"] > div:first-child,
        [data-testid="stRadio"] [role="radio"] [data-baseweb="radio"] {
            display: none !important;
        }
        [data-testid="stAlert"] { border-radius: 10px; }
        [data-testid="stAlert"],
        [data-testid="stAlert"] > div {
            background: rgba(248, 255, 250, 0.96) !important;
            border-color: #cfe3d5 !important;
            color: var(--portal-ink) !important;
        }
        [data-testid="stAlert"] *,
        [data-testid="stStatusWidget"] *,
        [data-testid="stToast"] * {
            color: var(--portal-ink) !important;
        }
        [data-testid="stCheckbox"] *,
        [data-testid="stSelectbox"] *,
        [data-testid="stMultiSelect"] *,
        [data-testid="stSlider"] *,
        [data-testid="stDateInput"] *,
        [data-testid="stTimeInput"] *,
        [data-testid="stTextInput"] *,
        [data-testid="stTextArea"] *,
        [data-testid="stNumberInput"] * {
            color: var(--portal-ink) !important;
        }
        [data-baseweb="checkbox"] div,
        [data-baseweb="radio"] div,
        [data-baseweb="tag"],
        [data-baseweb="tag"] span,
        [data-baseweb="tag"] div {
            background: #eef9f2 !important;
            border-color: #bfd8c7 !important;
            color: var(--portal-ink) !important;
        }
        [data-testid="stRadio"] [role="radiogroup"] label,
        [data-testid="stRadio"] [role="radio"] {
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            min-height: 2.65rem !important;
            min-width: 6.1rem !important;
            padding: 0 1rem !important;
            border-radius: 8px !important;
            background: #273940 !important;
            color: #ffffff !important;
        }
        [data-testid="stRadio"] [role="radiogroup"] label:hover,
        [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked),
        [data-testid="stRadio"] [role="radio"]:hover,
        [data-testid="stRadio"] [role="radio"][aria-checked="true"],
        [data-testid="stRadio"] [role="radio"]:has(input:checked) {
            background: #365e4a !important;
            color: #ffffff !important;
        }
        [data-testid="stRadio"] [role="radiogroup"] label *,
        [data-testid="stRadio"] [role="radio"] * {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
        }
        [data-testid="stRadio"] [role="radiogroup"] label input,
        [data-testid="stRadio"] [role="radiogroup"] label svg,
        [data-testid="stRadio"] [role="radiogroup"] label > div:first-child,
        [data-testid="stRadio"] [role="radiogroup"] label [data-baseweb="radio"],
        [data-testid="stRadio"] [role="radio"] input,
        [data-testid="stRadio"] [role="radio"] svg,
        [data-testid="stRadio"] [role="radio"] > div:first-child,
        [data-testid="stRadio"] [role="radio"] [data-baseweb="radio"] {
            display: none !important;
        }
        [data-baseweb="tag"] svg,
        [data-baseweb="tag"] svg path {
            color: #3f7657 !important;
            fill: #3f7657 !important;
        }
        [data-testid="stDataFrame"],
        [data-testid="stTable"],
        [data-testid="stTable"] table,
        [data-testid="stTable"] thead,
        [data-testid="stTable"] tbody,
        [data-testid="stTable"] tr,
        [data-testid="stTable"] td,
        [data-testid="stTable"] th {
            background: #fbfffc !important;
            border-color: #d8eadc !important;
            color: var(--portal-ink) !important;
        }
        [data-testid="stDataFrame"] *,
        [data-testid="stTable"] * {
            color: var(--portal-ink) !important;
        }
        [data-testid="stMarkdownContainer"] code,
        [data-testid="stCodeBlock"],
        [data-testid="stCodeBlock"] pre,
        [data-testid="stCodeBlock"] code {
            background: #f4fbf6 !important;
            color: #203b36 !important;
            border-color: #d8eadc !important;
        }
        [data-testid="stForm"] div,
        [data-testid="stForm"] section,
        [data-testid="stExpander"] div,
        [data-testid="stExpander"] section {
            color: var(--portal-ink) !important;
        }
        [data-testid="stForm"] [role="spinbutton"],
        [data-testid="stForm"] input,
        [data-testid="stForm"] textarea,
        [data-testid="stForm"] [data-baseweb="input"],
        [data-testid="stForm"] [data-baseweb="base-input"],
        [data-testid="stForm"] [data-baseweb="textarea"],
        [data-testid="stForm"] [data-baseweb="select"] > div {
            background: rgba(255, 255, 253, 0.96) !important;
            color: var(--portal-ink) !important;
            -webkit-text-fill-color: var(--portal-ink) !important;
            border-color: #cedfd3 !important;
        }
        .stButton > button,
        .stFormSubmitButton > button,
        .stLinkButton > a,
        .stDownloadButton > button,
        [data-testid="stForm"] .stFormSubmitButton > button {
            background: #273940 !important;
            color: #ffffff !important;
            border: 0 !important;
        }
        .stButton > button *,
        .stFormSubmitButton > button *,
        .stLinkButton > a *,
        .stDownloadButton > button *,
        [data-testid="stForm"] .stFormSubmitButton > button * {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
        }
        .stButton > button:hover,
        .stFormSubmitButton > button:hover,
        .stLinkButton > a:hover,
        .stDownloadButton > button:hover,
        [data-testid="stForm"] .stFormSubmitButton > button:hover {
            background: #365e4a !important;
            color: #ffffff !important;
        }
        [data-testid="stNumberInput"] button,
        [data-testid="stFileUploader"] button,
        [data-testid="stTextInputRootElement"]:has(input[type="password"]) button {
            background: #eef9f2 !important;
            border: 1px solid #bfd8c7 !important;
            color: #2f5a45 !important;
        }
        [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"],
        [data-testid="stFileUploader"] [class*="e3v525e7"],
        [data-testid="stFileUploader"] [class*="e3v525e7"] > div,
        [data-testid="stFileUploader"] [class*="e3v525e7"] [role="listitem"],
        [data-testid="stFileUploader"] div:has([data-testid="stFileUploaderFile"]) {
            background: #eafff1 !important;
            background-color: #eafff1 !important;
            border-color: #cfe3d5 !important;
            color: var(--portal-ink) !important;
            box-shadow: none !important;
        }
        [data-testid="stNumberInput"] button *,
        [data-testid="stFileUploader"] button *,
        [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] *,
        [data-testid="stFileUploader"] [class*="e3v525e7"] *,
        [data-testid="stFileUploader"] div:has([data-testid="stFileUploaderFile"]) *,
        [data-testid="stTextInputRootElement"]:has(input[type="password"]) button * {
            color: var(--portal-ink) !important;
            -webkit-text-fill-color: var(--portal-ink) !important;
        }
        /* Final uploaded-file preview override only. The empty uploader keeps the normal light theme. */
        [data-testid="stFileUploader"] [class*="e3v525e7"],
        [data-testid="stFileUploader"] [class*="e3v525e7"] > div,
        [data-testid="stFileUploader"] [class*="e3v525e7"] [role="list"],
        [data-testid="stFileUploader"] [class*="e3v525e7"] [role="listitem"],
        [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"],
        [data-testid="stFileUploader"] div:has([data-testid="stFileUploaderFile"]) {
            background: #1e3d2b !important;
            background-color: #1e3d2b !important;
            border-color: #2d5a3f !important;
            color: #f7fff9 !important;
            -webkit-text-fill-color: #f7fff9 !important;
            box-shadow: none !important;
        }
        [data-testid="stFileUploader"] [class*="e3v525e7"] *,
        [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] *,
        [data-testid="stFileUploader"] div:has([data-testid="stFileUploaderFile"]) * {
            color: #f7fff9 !important;
            -webkit-text-fill-color: #f7fff9 !important;
        }
        [data-testid="stFileUploader"] button[aria-label="Add files"],
        [data-testid="stFileUploader"] button[aria-label="Add files"] *,
        [data-testid="stFileUploader"] button[aria-label="Add files"] svg {
            display: none !important;
            visibility: hidden !important;
            width: 0 !important;
            min-width: 0 !important;
            padding: 0 !important;
            margin: 0 !important;
            border: 0 !important;
        }
        [data-testid="stFileUploader"] [class*="e3v525e7"] svg,
        [data-testid="stFileUploader"] [class*="e3v525e7"] svg path,
        [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] svg,
        [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] svg path {
            color: #f7fff9 !important;
            fill: #f7fff9 !important;
        }
        [data-testid="stFileUploader"] [class*="e3v525e7"] button,
        [data-testid="stFileUploader"] [class*="e3v525e7"] button:hover,
        [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] button,
        [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] button:hover,
        [data-testid="stFileUploader"] [aria-label*="Remove"],
        [data-testid="stFileUploader"] [aria-label*="Delete"],
        [data-testid="stFileUploader"] [aria-label*="Clear"] {
            background: #f7fff9 !important;
            background-color: #f7fff9 !important;
            border: 1px solid #cfe3d5 !important;
            color: #1e3d2b !important;
            -webkit-text-fill-color: #1e3d2b !important;
            box-shadow: none !important;
        }
        [data-testid="stFileUploader"] [class*="e3v525e7"] button *,
        [data-testid="stFileUploader"] [class*="e3v525e7"] button svg,
        [data-testid="stFileUploader"] [class*="e3v525e7"] button svg path,
        [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] button *,
        [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] button svg,
        [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] button svg path {
            color: #1e3d2b !important;
            -webkit-text-fill-color: #1e3d2b !important;
            fill: #1e3d2b !important;
        }
        [data-testid="stTextInputRootElement"]:has(input[type="password"]) button {
            background: transparent !important;
            border: 0 !important;
        }
        [data-testid="stTextInputRootElement"]:has(input[type="password"]) button svg,
        [data-testid="stTextInputRootElement"]:has(input[type="password"]) button svg path {
            color: #789086 !important;
            fill: #789086 !important;
        }
        hr { border-color: #d9e9dd; }
        .portal-shell { margin-top: 1rem; }
        .portal-hero {
            min-height: 540px;
            box-sizing: border-box;
            padding: 3.25rem 2.7rem;
            border-radius: 22px;
            background: linear-gradient(150deg, #edfff2, #c9eed7);
            color: #21343b;
            box-shadow: 0 16px 38px rgba(31, 78, 52, 0.12);
        }
        .portal-eyebrow { color: #4c906d; font-size: 0.82rem; font-weight: 700; letter-spacing: 0.11em; text-transform: uppercase; }
        .portal-hero h1 { font-size: 2.35rem; line-height: 1.08; margin: 1.2rem 0 1rem; }
        .portal-hero p { color: #49685c; font-size: 1.05rem; line-height: 1.65; max-width: 24rem; }
        .portal-orb {
            display: grid; place-items: center; width: 142px; height: 142px; margin: 2.7rem auto 2.4rem;
            border: 1px solid rgba(70, 137, 99, 0.28); border-radius: 50%;
            background: rgba(255, 255, 255, 0.54); color: #376d50; font-size: 3.5rem;
        }
        .portal-feature { margin-top: 0.75rem; color: #365f4b; font-size: 0.95rem; }
        .portal-brand { color: #203b36; font-family: "Trebuchet MS", "Aptos Display", sans-serif; font-size: 2rem; font-weight: 750; letter-spacing: -0.04em; margin: 2.3rem 0 0.1rem; }
        .portal-brand span { color: #59a276; }
        .portal-subtitle { color: #587267; margin-bottom: 1.8rem; }
        .portal-field-label {
            color: #163d37 !important;
            font-size: 1.03rem;
            font-weight: 700;
            margin: 0 0 0.45rem;
        }
        .avatar-native-card {
            max-width: 620px;
            margin: 0.75rem auto 0;
            border: 1px solid #cfe3d5;
            border-bottom: 0;
            border-radius: 18px 18px 0 0;
            overflow: hidden;
            background: #fbfffc;
            box-shadow: 0 16px 34px rgba(37, 72, 53, 0.12);
        }
        .avatar-native-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem 0.95rem;
            background: linear-gradient(135deg, #effbf3, #dff2e7);
            color: #203b36;
            font-weight: 750;
        }
        .avatar-native-header span:last-child {
            color: #5b9d73;
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .avatar-native-subtitle {
            max-width: 620px;
            margin: 0 auto 0.75rem;
            padding: 0.9rem 1rem;
            border: 1px solid #cfe3d5;
            border-top: 0;
            border-radius: 0 0 18px 18px;
            background: rgba(255, 255, 253, 0.97);
            color: var(--portal-ink);
            line-height: 1.5;
            font-size: 1.04rem;
            box-shadow: 0 16px 34px rgba(37, 72, 53, 0.08);
        }
        .assessment-room-title {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
            padding: 1rem 1.1rem;
            margin: 0.4rem 0 0.7rem;
            border: 1px solid #cfe3d5;
            border-radius: 18px;
            background: rgba(255, 255, 253, 0.82);
            box-shadow: 0 10px 24px rgba(37, 72, 53, 0.06);
        }
        .assessment-room-title h2 {
            margin: 0.15rem 0 0.25rem;
            font-size: 1.78rem;
            line-height: 1.22;
        }
        .assessment-room-title p {
            margin: 0;
            color: var(--portal-muted) !important;
            font-size: 1rem;
            font-weight: 700;
        }
        .assessment-badge {
            flex: 0 0 auto;
            padding: 0.45rem 0.7rem;
            border-radius: 999px;
            background: #e8f6ed;
            color: #2f6c4b;
            font-weight: 750;
            font-size: 0.96rem;
            border: 1px solid #cbe4d3;
        }
        .ai-grading-comment {
            color: #213c36;
            font-size: 1rem;
            line-height: 1.55;
            margin: 0.12rem 0 0.55rem;
        }
        .ai-grading-evidence {
            color: #2b4f45;
            margin-top: -0.15rem;
        }
        .ai-grading-summary {
            color: #203b36;
            background: #eef9f1;
            border: 1px solid #cfe3d5;
            border-radius: 12px;
            padding: 0.85rem 0.95rem;
            margin: 0.75rem 0 0.9rem;
            line-height: 1.55;
            font-size: 1rem;
        }
        .student-stepbar {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 0;
            align-items: start;
            margin: 0.5rem 0 1rem;
            padding: 0.9rem 0.6rem 0.75rem;
            border-top: 1px solid #d8eadc;
            border-bottom: 1px solid #d8eadc;
            background: rgba(255, 255, 253, 0.58);
        }
        .student-step {
            position: relative;
            display: grid;
            justify-items: center;
            gap: 0.42rem;
            min-width: 0;
            color: #6e8179;
            text-align: center;
            font-size: 0.88rem;
            font-weight: 700;
            line-height: 1.25;
        }
        .student-step::before {
            content: "";
            position: absolute;
            top: 15px;
            left: 0;
            right: 0;
            height: 3px;
            background: #d9e7de;
            z-index: 0;
        }
        .student-step:first-child::before {
            left: 50%;
        }
        .student-step:last-child::before {
            right: 50%;
        }
        .student-step-dot {
            position: relative;
            z-index: 1;
            display: grid;
            place-items: center;
            width: 32px;
            height: 32px;
            border-radius: 999px;
            border: 2px solid #d9e7de;
            background: #fbfdf9;
            color: #587267;
            font-size: 0.86rem;
            font-weight: 800;
            box-sizing: border-box;
        }
        .student-step.done,
        .student-step.active {
            color: #203b36;
        }
        .student-step.done::before {
            background: #72b684;
        }
        .student-step.active::before {
            background: linear-gradient(90deg, #72b684 0 50%, #d9e7de 50% 100%);
        }
        .student-step.done .student-step-dot {
            border-color: #5b9d73;
            background: #5b9d73;
            color: #ffffff;
        }
        .student-step.active .student-step-dot {
            border-color: #2f6c4b;
            background: #e8f6ed;
            color: #203b36;
            box-shadow: 0 0 0 5px rgba(91, 157, 115, 0.16);
        }
        .student-step-text {
            display: block;
            overflow-wrap: anywhere;
        }
        .assessment-panel-label {
            margin: 0.35rem 0 0.45rem;
            color: #315348;
            font-size: 0.92rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }
        .assessment-help-card {
            padding: 0.85rem 0.95rem;
            margin: 0.75rem 0 0;
            border: 1px solid #d5e9da;
            border-radius: 14px;
            background: #f7fff9;
            color: var(--portal-muted);
            font-size: 1.02rem;
            line-height: 1.5;
        }
        .response-panel {
            margin-top: 1.15rem;
            padding: 1rem 1.1rem 1.1rem;
            border: 1px solid #cfe3d5;
            border-radius: 18px;
            background: rgba(255, 255, 253, 0.9);
            box-shadow: 0 10px 24px rgba(37, 72, 53, 0.06);
        }
        .response-panel h3 {
            margin: 0 0 0.25rem;
            font-size: 1.3rem;
        }
        .response-panel p {
            margin: 0 0 0.85rem;
            color: var(--portal-muted) !important;
        }
        .prep-loading-card {
            display: flex;
            align-items: center;
            gap: 1.2rem;
            padding: 1.4rem 1.5rem;
            border: 1px solid #cfe3d5;
            border-radius: 18px;
            background: rgba(255, 255, 253, 0.86);
            box-shadow: 0 12px 28px rgba(37, 72, 53, 0.08);
            margin: 1rem 0 1.2rem;
        }
        .prep-loading-card h3 {
            margin: 0 0 0.25rem;
            color: var(--portal-ink) !important;
            font-size: 1.1rem;
        }
        .prep-loading-card p {
            margin: 0;
            color: var(--portal-muted) !important;
        }
        .prep-loader {
            width: 46px;
            height: 46px;
            border-radius: 999px;
            border: 4px solid #dcefe3;
            border-top-color: #5b9d73;
            animation: prep-spin 0.9s linear infinite;
            flex: 0 0 auto;
        }
        @keyframes prep-spin {
            to { transform: rotate(360deg); }
        }
        @media (max-width: 800px) {
            [data-testid="stMainBlockContainer"] { padding-top: 1rem; }
            .portal-hero { min-height: auto; padding: 2rem; }
            .student-stepbar {
                grid-template-columns: 1fr;
                gap: 0.65rem;
                padding: 0.75rem 0.85rem;
            }
            .student-step {
                grid-template-columns: 32px 1fr;
                justify-items: start;
                text-align: left;
            }
            .student-step::before {
                top: 0;
                bottom: -0.65rem;
                left: 15px !important;
                right: auto !important;
                width: 3px;
                height: auto;
            }
            .student-step:last-child::before {
                display: none;
            }
            .student-step.active::before {
                background: linear-gradient(180deg, #72b684 0 50%, #d9e7de 50% 100%);
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_login() -> None:
    left, right = st.columns([1.1, 0.95], gap="large")
    with left:
        st.markdown(
            """
            <section class="portal-hero">
              <div class="portal-eyebrow">PSLE English Oral</div>
              <div class="portal-orb">&#127908;</div>
              <h1>Speak with confidence.</h1>
              <p>Prepare, respond, and grow through a guided oral assessment experience built for students and examiners.</p>
              <div class="portal-feature">&#10003; Student preparation and timed practice</div>
              <div class="portal-feature">&#10003; Examiner review and verified feedback</div>
            </section>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.markdown('<div class="portal-brand">ORAL <span>FOCUS</span></div>', unsafe_allow_html=True)
        st.markdown('<div class="portal-subtitle">Sign in to your assessment workspace.</div>', unsafe_allow_html=True)
        if "login_role" not in st.session_state:
            st.session_state.login_role = "Student"
        st.markdown('<div class="portal-field-label">Portal</div>', unsafe_allow_html=True)
        role_cols = st.columns(2, gap="small")
        with role_cols[0]:
            if st.button("Student", key="login_role_student", width="stretch"):
                st.session_state.login_role = "Student"
                st.rerun()
        with role_cols[1]:
            if st.button("Examiner", key="login_role_examiner", width="stretch"):
                st.session_state.login_role = "Examiner"
                st.rerun()
        role = st.session_state.login_role
        login_error = st.session_state.pop("login_error", None)
        if login_error:
            st.error(login_error)
        with st.form("login_form"):
            user_id = st.text_input("Student ID" if role == "Student" else "Examiner ID", placeholder="e.g. 001")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            submitted = st.form_submit_button("Sign in", type="primary", width="stretch")
        st.caption("Demo access: Student or Examiner ID `001` with password `002`.")
        with st.expander("Create a student account"):
            st.caption("Register with your own Student ID, then ask the examiner to assign an assessment to that ID.")
            with st.form("student_registration_form", clear_on_submit=True):
                new_student_id = st.text_input(
                    "New Student ID",
                    placeholder="e.g. student_002",
                    help="Use letters, numbers, dots, underscores, or hyphens.",
                )
                new_student_name = st.text_input("Display name", placeholder="e.g. Student 002")
                new_password = st.text_input("Create password", type="password")
                confirm_password = st.text_input("Confirm password", type="password")
                register_submitted = st.form_submit_button("Register student account", width="stretch")
            if register_submitted:
                if new_password != confirm_password:
                    st.error("The passwords do not match.")
                else:
                    try:
                        registered = register_student(new_student_id, new_password, new_student_name)
                    except ValueError as error:
                        st.error(str(error))
                    except Exception as error:
                        st.error(f"Student account could not be created: {error}")
                    else:
                        st.success(
                            f"Account created for {registered['name']} ({registered['id']}). "
                            "You can now sign in as Student."
                        )
    if submitted:
        user = authenticate(role, user_id, password)
        if not user:
            st.session_state["login_error"] = (
                "Wrong ID, password, or portal role. Please check your details and try again."
            )
            st.rerun()
        st.session_state.authenticated = True
        st.session_state.pop("login_error", None)
        st.session_state.user_role = role.lower()
        st.session_state.user_id = user["id"]
        st.session_state.user_name = user["name"]
        if role == "Student":
            st.session_state.preparation_deadline = None
            st.session_state.preparation_timer_assignment_id = None
            st.session_state.preparation_complete = False
            st.session_state.student_portal_stage = "selection"
            st.session_state.student_selected_assignment_id = None
        else:
            st.session_state.preparation_deadline = None
            st.session_state.preparation_timer_assignment_id = None
            st.session_state.preparation_complete = False
        st.rerun()

    with st.expander("About these accounts"):
        st.write("This prototype reads role-specific IDs and passwords from `data/users.json`. Do not use these demo credentials for a deployed application.")


def render_account_sidebar(role: str) -> None:
    with st.sidebar:
        st.title("Account")
        st.caption(f"{role}: {st.session_state.user_name} ({st.session_state.user_id})")
        if st.button("Logout", width="stretch"):
            logout()


def render_custom_rubric_upload() -> None:
    with st.expander("Add a custom English Oral rubric"):
        st.caption(
            "Upload a JSON rubric with one or more criteria. Each criterion needs a name, "
            "a positive `max_points` or `max_score`, and scoring levels. Only this portal's "
            "custom English Oral rubrics will appear in the grading selector."
        )
        custom_rubric = st.file_uploader(
            "Custom English Oral rubric (.json)",
            type=["json"],
            key="custom_english_oral_rubric",
        )
        if st.button("Validate and save rubric", key="save_custom_english_oral_rubric"):
            if not custom_rubric:
                st.warning("Choose a JSON rubric file first.")
                return
            try:
                rubric_name = save_english_oral_rubric(custom_rubric.name, custom_rubric.getvalue())
            except ValueError as error:
                st.error(f"The rubric was not saved: {error}")
                return
            st.session_state["rubric_upload_notice"] = (
                f"Saved '{rubric_display_name(rubric_name)}'. It is now available for assignment grading."
            )
            st.rerun()


def render_assignment_generation_loading(request: dict) -> None:
    """Prepare assignment questions while showing a dedicated loading screen."""
    st.markdown(
        """
        <div class="prep-loading-card">
          <div class="prep-loader"></div>
          <div>
            <h3>Generating questions for review</h3>
            <p>Saving the materials, reading the picture stimulus, and preparing the examiner review draft.</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    progress = st.progress(0, text="Starting question preparation...")
    temporary_directory = Path(tempfile.mkdtemp(prefix="exam-upload-"))
    subject = request["subject"]
    try:
        progress.progress(0.12, text="Starting the AI examiner...")
        crew = init_crew(subject, request["rubric"], request["student"]["id"])

        progress.progress(0.25, text="Saving the picture stimulus...")
        visual_file = save_queued_upload(request["visual_upload"], temporary_directory)

        use_fast_photo_path = bool_env("FAST_PHOTO_QUESTION_GENERATION", True) and supported_visual_image_path(visual_file)
        progress.progress(
            0.45,
            text=(
                "Reading the photo and generating oral questions..."
                if use_fast_photo_path
                else "Reading the image and generating oral questions..."
            ),
        )
        if use_fast_photo_path:
            try:
                visual_result = crew.run_visual_question_workflow(str(visual_file), num_questions=IMAGE_QUESTION_COUNT)
            except Exception as fast_error:
                progress.progress(
                    0.48,
                    text=f"Fast photo generation was unavailable; using full ingestion path. Reason: {fast_error}",
                )
                run_review_analysis = bool_env("QUESTION_REVIEW_CREW_ANALYSIS", False)
                visual_result = crew.run_ingestion_workflow(
                    str(visual_file),
                    material_type="visual",
                    extract_questions=True,
                    run_crew_analysis=run_review_analysis,
                )
        else:
            run_review_analysis = bool_env("QUESTION_REVIEW_CREW_ANALYSIS", False)
            visual_result = crew.run_ingestion_workflow(
                str(visual_file),
                material_type="visual",
                extract_questions=True,
                run_crew_analysis=run_review_analysis,
            )
        questions = visual_result.get("questions", [])[:IMAGE_QUESTION_COUNT]
        if not questions:
            raise RuntimeError(
                "No image questions were generated. Try a clearer image or check the AI service configuration."
            )

        visual_info = {
            "name": request["visual_upload"]["name"],
            "path": visual_result.get("ingest_result", {}).get("file_path"),
            "image_count": visual_result.get("ingest_result", {}).get("image_count", 0),
        }
        reading_info = None
        if request.get("reading_upload"):
            progress.progress(0.65, text="Saving the reading passage...")
            reading_file = save_queued_upload(request["reading_upload"], temporary_directory)
            if bool_env("FAST_READING_MATERIAL_PREP", True):
                try:
                    reading_result = save_reading_material_for_assignment(subject, reading_file)
                    stored_path = reading_result.get("file_path")
                    reading_text = reading_result.get("text", "")
                except Exception as reading_fast_error:
                    progress.progress(
                        0.7,
                        text=f"Fast reading save was unavailable; using full reading ingestion. Reason: {reading_fast_error}",
                    )
                    reading_result = crew.run_ingestion_workflow(
                        str(reading_file), material_type="reading", extract_questions=False
                    )
                    stored_path = reading_result.get("ingest_result", {}).get("file_path")
                    reading_text = extract_reading_passage(stored_path) if stored_path else ""
            else:
                reading_result = crew.run_ingestion_workflow(
                    str(reading_file), material_type="reading", extract_questions=False
                )
                stored_path = reading_result.get("ingest_result", {}).get("file_path")
                reading_text = extract_reading_passage(stored_path) if stored_path else ""
            reading_info = {
                "name": request["reading_upload"]["name"],
                "path": stored_path,
                "text": reading_text,
            }

        progress.progress(0.88, text="Preparing the review draft...")
        prepared_questions = [
            {**question, "generated_text": question.get("text", ""), "edited_by_examiner": False}
            for question in questions
        ]
        st.session_state.assignment_draft = {
            "draft_id": uuid.uuid4().hex,
            "student": request["student"],
            "title": request["title"],
            "subject": subject,
            "rubric": request["rubric"],
            "visual": visual_info,
            "questions": prepared_questions,
            "reading": reading_info,
        }
        st.session_state.assignment_generation_request = None
        progress.progress(1.0, text="Questions are ready for review.")
        st.rerun()
    except Exception as error:
        try:
            SubjectManager().delete_subject_data(subject)
        except Exception:
            pass
        st.session_state.assignment_generation_request = None
        st.error(f"The questions could not be prepared for review: {error}")
        st.caption("Please check that the uploaded image is readable and try Generate questions for review again.")
    finally:
        shutil.rmtree(temporary_directory, ignore_errors=True)


def render_create_assignment() -> None:
    students = list_students()
    rubrics = list_rubrics() or [DEFAULT_PSLE_RUBRIC]
    st.subheader("Create an assessment")
    st.caption("PSLE English Oral only. Select one picture stimulus and, if needed, one reading passage for this student.")
    notice = st.session_state.pop("rubric_upload_notice", None)
    if notice:
        st.success(notice)
    assignment_notice = st.session_state.pop("assignment_notice", None)
    if assignment_notice:
        st.success(assignment_notice)
    avatar_warnings = st.session_state.pop("assignment_avatar_warnings", None)
    if avatar_warnings:
        st.warning("Some examiner avatar videos could not be pre-created. Students can still read the questions normally.")
        for warning in avatar_warnings:
            st.caption(warning)
    render_custom_rubric_upload()
    if not students:
        st.warning("No registered students are available. Add students to `data/users.json` first.")
        return

    generation_request = st.session_state.get("assignment_generation_request")
    if generation_request:
        render_assignment_generation_loading(generation_request)
        return

    draft = st.session_state.get("assignment_draft")
    if draft:
        if draft.get("avatar_preview_questions"):
            preview_questions = draft["avatar_preview_questions"]
            preview_changed = False
            refreshed_preview_questions = []
            pending_numbers = []
            for number, question in enumerate(preview_questions, 1):
                refreshed_question = {**question}
                original_avatar_video = refreshed_question.get("avatar_video") or {}
                avatar_video = refresh_avatar_video_reference(original_avatar_video)
                refreshed_question["avatar_video"] = avatar_video
                if avatar_video != original_avatar_video:
                    preview_changed = True
                if not avatar_video.get("ready"):
                    pending_numbers.append(str(number))
                refreshed_preview_questions.append(refreshed_question)

            preview_questions = refreshed_preview_questions
            if preview_changed:
                draft["avatar_preview_questions"] = preview_questions
                st.session_state.assignment_draft = draft

            if pending_numbers:
                st.markdown("#### Preparing examiner avatars")
                st.markdown(
                    """
                    <div class="prep-loading-card">
                      <div class="prep-loader"></div>
                      <div>
                        <h3>Still preparing avatar videos</h3>
                        <p>The preview will appear only after all examiner avatar videos are playable.</p>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.warning(f"Still waiting for question(s): {', '.join(pending_numbers)}")
                st.caption(
                    "This delay is coming from Simli: it has returned video URLs, but those URLs are still serving "
                    "`File not found` instead of playable video. Press Refresh preview after a short wait."
                )
                refresh_column, edit_column = st.columns(2)
                if refresh_column.button("Refresh preview", width="stretch"):
                    for question in preview_questions:
                        question["avatar_video"] = refresh_avatar_video_reference(question.get("avatar_video") or {})
                    draft["avatar_preview_questions"] = preview_questions
                    st.session_state.assignment_draft = draft
                    st.rerun()
                if edit_column.button("Back to edit questions", width="stretch"):
                    draft.pop("avatar_preview_questions", None)
                    draft.pop("avatar_preview_warnings", None)
                    st.session_state.assignment_draft = draft
                    st.rerun()
                return

            st.markdown("#### Preview examiner avatars")
            st.info("All examiner avatar videos are ready. Check them before assigning the assessment.")
            for warning in draft.get("avatar_preview_warnings", []):
                st.caption(warning)

            for number, question in enumerate(preview_questions, 1):
                with st.container(border=True):
                    question_text = str(question.get("text", ""))
                    st.markdown(f"##### Question {number}")
                    st.write(question_text)
                    avatar_video = question.get("avatar_video") or {}
                    avatar_path = avatar_video.get("path")
                    avatar_url = avatar_video.get("source_url")
                    avatar_ready = avatar_video.get("ready")
                    if avatar_path and render_avatar_video_file(
                        avatar_path,
                        element_key=f"draft_avatar_file_{draft['draft_id']}_{number}",
                        subtitle=question_text,
                    ):
                        st.success("Saved local avatar video is ready.")
                    elif avatar_url:
                        if avatar_ready:
                            st.success("Avatar stream is ready.")
                            render_avatar_video(
                                avatar_url,
                                element_key=f"draft_avatar_url_{draft['draft_id']}_{number}",
                                subtitle=question_text,
                            )
                        else:
                            st.warning("Avatar is still preparing on Simli. It will not be shown until the URL is playable.")
                            st.caption("Use Refresh preview in a moment. This avoids showing the raw File not found response.")
                    else:
                        st.warning("No avatar video was prepared for this question. The student will still see the written question.")

            assign_column, refresh_column, edit_column = st.columns(3)
            if assign_column.button("Assign to student", type="primary", width="stretch"):
                try:
                    record = create_assignment(
                        student=draft["student"],
                        title=draft["title"],
                        subject=draft["subject"],
                        rubric=draft["rubric"],
                        visual=draft["visual"],
                        questions=preview_questions,
                        reading=draft["reading"],
                        examiner_id=st.session_state.user_id,
                    )
                except Exception as error:
                    st.error(f"The assessment was not assigned: {error}")
                    return

                st.session_state.assignment_draft = None
                avatar_count = sum(
                    1 for question in record["questions"] if (question.get("avatar_video") or {}).get("source_url")
                )
                st.session_state["assignment_notice"] = (
                    f"Assigned '{record['title']}' to {draft['student']['name']} with "
                    f"{len(record['questions'])} reviewed question(s). Prepared {avatar_count}/{len(record['questions'])} avatar video reference(s)."
                )
                st.rerun()

            if refresh_column.button("Refresh preview", width="stretch"):
                for question in preview_questions:
                    question["avatar_video"] = refresh_avatar_video_reference(question.get("avatar_video") or {})
                draft["avatar_preview_questions"] = preview_questions
                st.session_state.assignment_draft = draft
                st.rerun()

            if edit_column.button("Back to edit questions", width="stretch"):
                draft.pop("avatar_preview_questions", None)
                draft.pop("avatar_preview_warnings", None)
                st.session_state.assignment_draft = draft
                st.rerun()

            return

        st.markdown("#### Review AI-generated questions")
        st.info(
            "Edit any question before assigning it. The student and grader will use these final examiner-approved questions."
        )
        with st.form("review_assignment_questions"):
            edited_questions = []
            for number, question in enumerate(draft["questions"], 1):
                original_text = str(question.get("text", ""))
                text = st.text_area(
                    f"Question {number}",
                    value=original_text,
                    height=100,
                    key=f"draft_question_{draft['draft_id']}_{question.get('id', number)}",
                )
                edited_questions.append((question, text))

            assign_column, discard_column = st.columns(2)
            primary_label = "Prepare avatar preview" if simli_avatar_requested() else "Assign to student"
            assign = assign_column.form_submit_button(primary_label, type="primary", width="stretch")
            discard = discard_column.form_submit_button("Discard draft", width="stretch")

        if discard:
            try:
                SubjectManager().delete_subject_data(draft["subject"])
            except Exception:
                pass
            st.session_state.assignment_draft = None
            st.rerun()

        if not assign:
            return

        final_questions = []
        for question, edited_text in edited_questions:
            final_text = edited_text.strip()
            if not final_text:
                st.error("Every question needs text before the assessment can be assigned.")
                return
            generated_text = str(question.get("generated_text", question.get("text", "")))
            final_questions.append(
                {
                    **question,
                    "text": final_text,
                    "generated_text": generated_text,
                    "edited_by_examiner": final_text != generated_text,
                }
            )

        if not simli_avatar_requested():
            try:
                record = create_assignment(
                    student=draft["student"],
                    title=draft["title"],
                    subject=draft["subject"],
                    rubric=draft["rubric"],
                    visual=draft["visual"],
                    questions=final_questions,
                    reading=draft["reading"],
                    examiner_id=st.session_state.user_id,
                )
            except Exception as error:
                st.error(f"The assessment was not assigned: {error}")
                return

            st.session_state.assignment_draft = None
            if anam_avatar_requested():
                avatar_note = "Anam live examiner avatar will be used during the assessment."
            else:
                avatar_note = "Avatar playback is disabled, so students will see the written questions."
            st.session_state["assignment_notice"] = (
                f"Assigned '{record['title']}' to {draft['student']['name']} with "
                f"{len(record['questions'])} reviewed question(s). {avatar_note}"
            )
            st.rerun()

        avatar_warnings: list[str] = []
        if simli_avatar_requested():
            st.markdown(
                """
                <div class="prep-loading-card">
                  <div class="prep-loader"></div>
                  <div>
                    <h3>Preparing examiner avatar videos</h3>
                    <p>Creating the examiner clips for the final approved questions before assigning them to the student.</p>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            avatar_progress = st.progress(0, text="Starting examiner avatar preparation...")

            def update_avatar_progress(done: int, total: int, message: str) -> None:
                avatar_progress.progress(done / max(total, 1), text=message)

            with st.spinner("Please wait while the examiner avatars are prepared..."):
                final_questions, avatar_warnings = prepare_persistent_question_avatars(
                    final_questions,
                    asset_prefix=draft["draft_id"],
                    progress_callback=update_avatar_progress,
                )
                try:
                    wait_seconds = float(os.getenv("AVATAR_PREVIEW_WAIT_SECONDS", "360"))
                except ValueError:
                    wait_seconds = 360.0
                wait_seconds = max(60.0, wait_seconds)
                final_questions, readiness_warnings = wait_until_question_avatars_ready(
                    final_questions,
                    timeout_seconds=wait_seconds,
                    progress_callback=update_avatar_progress,
                )
                avatar_warnings.extend(readiness_warnings)
            ready_count = sum(1 for question in final_questions if (question.get("avatar_video") or {}).get("ready"))
            avatar_progress.progress(
                ready_count / max(len(final_questions), 1),
                text=f"{ready_count}/{len(final_questions)} examiner avatar video(s) ready.",
            )

        if not any((question.get("avatar_video") or {}).get("source_url") for question in final_questions):
            st.error("No examiner avatar videos were prepared. Please check the Simli/OpenAI settings, then try preparing the preview again.")
            for warning in avatar_warnings:
                st.caption(warning)
            return
        elif not all((question.get("avatar_video") or {}).get("ready") for question in final_questions):
            st.error("The avatar preview is not ready yet. I will not show the preview until all question videos are playable.")
            for warning in avatar_warnings:
                st.caption(warning)
            st.caption(
                "Try Prepare avatar preview again in a moment. You can increase AVATAR_PREVIEW_WAIT_SECONDS in .env "
                "if Simli often takes longer for your clips."
            )
            return
        draft["avatar_preview_questions"] = final_questions
        draft["avatar_preview_warnings"] = avatar_warnings
        st.session_state.assignment_draft = draft
        st.rerun()

    st.markdown("#### Choose the materials for this assessment")
    visual_upload = st.file_uploader(
        "Upload picture stimulus",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=False,
        help="Upload one picture stimulus for this student.",
        key="visual_material_uploads",
    )
    if visual_upload:
        st.caption(f"Selected picture stimulus: {visual_upload.name}")
    reading_upload = st.file_uploader(
        "Upload reading passage (optional)",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=False,
        help="Upload one optional reading passage, or leave this blank.",
        key="reading_material_uploads",
    )
    if reading_upload:
        st.caption(f"Selected reading passage: {reading_upload.name}")

    student_by_label = {f"{student['name']} ({student['id']})": student for student in students}
    with st.form("create_assignment"):
        selected_label = st.selectbox("Assign to registered student", list(student_by_label))
        title = st.text_input("Assessment title", value="PSLE English Oral Practice")
        rubric = st.selectbox("Grading rubric", rubrics, format_func=rubric_display_name)
        submitted = st.form_submit_button("Generate questions for review", type="primary", width="stretch")

    if not submitted:
        return
    if not visual_upload:
        st.error("Upload and select a picture stimulus before assigning the assessment.")
        return

    student = student_by_label[selected_label]
    subject = assignment_subject(student["id"])
    st.session_state.assignment_generation_request = {
        "request_id": uuid.uuid4().hex,
        "student": student,
        "title": title,
        "subject": subject,
        "rubric": rubric,
        "visual_upload": {
            "name": visual_upload.name,
            "bytes": visual_upload.getvalue(),
        },
        "reading_upload": (
            {
                "name": reading_upload.name,
                "bytes": reading_upload.getvalue(),
            }
            if reading_upload
            else None
        ),
    }
    st.rerun()


def _assignment_label(assignment: dict) -> str:
    return f"{assignment.get('student_name', assignment.get('student_id'))} — {assignment.get('title')} ({assignment.get('status')})"


def render_examiner_review() -> None:
    collect_deferred_reading_ai_grading()
    assignments = list_assignments()
    st.subheader("Review AI results")
    review_notice = st.session_state.pop("examiner_review_notice", None)
    if review_notice:
        level = review_notice.get("level", "success")
        message = review_notice.get("message", "")
        if level == "error":
            st.error(message)
        elif level == "warning":
            st.warning(message)
        else:
            st.success(message)
    if not assignments:
        st.info("No assessments have been assigned yet.")
        return

    assignments_by_id = {record["assignment_id"]: record for record in assignments}
    selected_review_assignment = st.session_state.get("review_assignment")
    if isinstance(selected_review_assignment, dict):
        selected_review_assignment = selected_review_assignment.get("assignment_id")
        st.session_state.review_assignment = selected_review_assignment
    if selected_review_assignment not in assignments_by_id:
        st.session_state.review_assignment = next(iter(assignments_by_id))

    selected_assignment_id = st.selectbox(
        "Student assessment",
        list(assignments_by_id),
        format_func=lambda assignment_id: _assignment_label(assignments_by_id[assignment_id]),
        key="review_assignment",
    )
    assignment = assignments_by_id[selected_assignment_id]
    results = assignment.get("results", [])
    completed = len(results)
    reviewed = sum(1 for result in results if result.get("examiner_review"))
    col1, col2, col3 = st.columns(3)
    col1.metric("Student", assignment.get("student_name", assignment.get("student_id")))
    col2.metric("AI responses", completed)
    col3.metric("Reviewed", reviewed)

    if assignment.get("reading"):
        reading_submission = assignment.get("reading_submission")
        if reading_submission:
            with st.expander("Reading-aloud submission", expanded=True):
                render_reading_review_summary(reading_submission, assignment)
                reading_grade = reading_submission.get("final_grading") or reading_submission.get("ai_grading")
                evidence_col, verify_col = st.columns([1.35, 0.85], gap="large", vertical_alignment="top")
                previous_note = (reading_submission.get("examiner_review") or {}).get("note", "")

                with verify_col:
                    st.markdown("#### Verify or adjust")
                    if reading_grade and reading_grade.get("scoring_source") == "pending_examiner_review":
                        st.caption("Listen to the recording and enter verified reading marks if needed.")
                    else:
                        st.caption("Check the recording before saving verified marks.")
                    with st.form(f"review_reading_{assignment['assignment_id']}"):
                        changes: dict[str, int] = {}
                        for criterion in reading_grade.get("scores", []) if reading_grade else []:
                            label = str(criterion.get("criterion", "Criterion"))
                            maximum = int(criterion.get("max_score", 0))
                            if maximum <= 0:
                                continue
                            changes[label] = int(
                                st.number_input(
                                    label,
                                    min_value=0,
                                    max_value=maximum,
                                    value=int(criterion.get("score", 0)),
                                    step=1,
                                    key=f"reading_score_{assignment['assignment_id']}_{label}",
                                )
                            )
                        note = st.text_area("Examiner note (optional)", value=previous_note)
                        saved_reading = st.form_submit_button("Save verified reading grade", width="stretch")
                    if (reading_submission.get("examiner_review") or {}).get("reviewed_at"):
                        st.caption(f"Last reviewed: {reading_submission['examiner_review']['reviewed_at']}")

                with evidence_col:
                    st.markdown("#### Evidence and AI grade")
                    st.write("**Transcript:**", reading_submission.get("transcript", ""))
                    if reading_submission.get("audio_path"):
                        st.audio(reading_submission["audio_path"])
                    render_delivery_indicators(reading_submission.get("delivery_indicators"))
                    if reading_grade:
                        heading = (
                            "Reading-aloud grade pending examiner review"
                            if reading_grade.get("scoring_source") == "pending_examiner_review"
                            else "Provisional reading-aloud grade"
                        )
                        render_grading_result(reading_grade, heading=heading)
                    if reading_submission.get("ai_grading_error"):
                        st.warning(f"Deferred AI reading grade could not be generated: {reading_submission['ai_grading_error']}")
                    elif reading_grade and reading_grade.get("scoring_source") == "pending_examiner_review":
                        st.info("The student has moved on. The deferred AI reading grade is still being prepared.")
                    elif reading_submission.get("ai_graded_at"):
                        st.success("Provisional AI reading grade is ready. Verify it against the audio before releasing results.")
                if saved_reading:
                    try:
                        apply_reading_examiner_review(
                            assignment["assignment_id"], changes, note, st.session_state.user_id
                        )
                    except Exception as error:
                        st.session_state["examiner_review_notice"] = {
                            "level": "error",
                            "message": f"Verified reading grade could not be saved: {error}",
                        }
                    else:
                        st.session_state["examiner_review_notice"] = {
                            "level": "success",
                            "message": "Verified reading grade saved.",
                        }
                    st.rerun()
        else:
            st.info("Reading-aloud passage assigned. Waiting for the student to submit the one-time recording.")
    if not results:
        st.info("The student has not submitted an image-question response yet.")
        return

    for number, result in enumerate(results, 1):
        final_grading = result.get("final_grading") or result.get("ai_grading") or {}
        ai_grading = result.get("ai_grading") or {}
        reviewed_at = (result.get("examiner_review") or {}).get("reviewed_at")
        title = f"Q{number}: {result.get('question', 'Question')[:80]}"
        with st.expander(title, expanded=(number == 1)):
            render_review_summary(
                ai_grading=ai_grading,
                final_grading=final_grading,
                reviewed_at=reviewed_at,
                released_at=assignment.get("results_released_at"),
                has_audio=bool(result.get("audio_path") or (result.get("guided_attempt") or {}).get("original_audio_path")),
                guidance_used=bool(result.get("guided_attempt")),
                skipped=bool(result.get("skipped")),
            )
            evidence_col, verify_col = st.columns([1.45, 0.85], gap="large", vertical_alignment="top")
            previous_note = (result.get("examiner_review") or {}).get("note", "")

            with verify_col:
                st.markdown("#### Verify or adjust")
                st.caption("Review the response, then save final marks for this question.")
                with st.form(f"review_{result['result_id']}"):
                    changes: dict[str, int] = {}
                    for criterion in final_grading.get("scores", []):
                        label = str(criterion.get("criterion", "Criterion"))
                        maximum = int(criterion.get("max_score", 0))
                        if maximum <= 0:
                            st.caption(f"{label}: not assessed by this workflow")
                            continue
                        changes[label] = int(
                            st.number_input(
                                label,
                                min_value=0,
                                max_value=maximum,
                                value=int(criterion.get("score", 0)),
                                step=1,
                                key=f"score_{result['result_id']}_{label}",
                            )
                        )
                    note = st.text_area(
                        "Examiner note (optional)",
                        value=previous_note,
                        key=f"note_{result['result_id']}",
                    )
                    saved = st.form_submit_button("Save verified grade", width="stretch")
                if reviewed_at:
                    st.caption(f"Last reviewed: {reviewed_at}")

            with evidence_col:
                st.markdown("#### Response and grading evidence")
                render_recorded_response(result)
                left, right = st.columns(2)
                with left:
                    render_grading_result(ai_grading, heading="AI grade")
                with right:
                    render_grading_result(final_grading, heading="Final grade")
                if result.get("crew_analysis"):
                    with st.expander("AI coaching analysis"):
                        st.write(result["crew_analysis"])

            if saved:
                try:
                    apply_examiner_review(
                        assignment["assignment_id"],
                        result["result_id"],
                        changes,
                        note,
                        st.session_state.user_id,
                    )
                except Exception as error:
                    st.session_state["examiner_review_notice"] = {
                        "level": "error",
                        "message": f"Verified grade could not be saved: {error}",
                    }
                else:
                    st.session_state["examiner_review_notice"] = {
                        "level": "success",
                        "message": f"Verified grade saved for question {number}. The original AI grade remains in the record.",
                        }
                st.rerun()

    reading_pending = bool(
        assignment.get("reading")
        and not (assignment.get("reading_submission") or {}).get("examiner_review")
    )
    unreviewed_questions = [result for result in results if not result.get("examiner_review")]
    st.markdown("#### Release final results")
    release_columns = st.columns(3)
    release_columns[0].metric("Reading review", "Verified" if not reading_pending else "Pending")
    release_columns[1].metric("Image reviews", f"{len(results) - len(unreviewed_questions)}/{len(results)} verified")
    release_columns[2].metric("Release status", "Released" if assignment.get("results_released_at") else "Not released")
    if assignment.get("results_released_at"):
        st.success(f"Final results released on {assignment['results_released_at']}.")
    elif assignment.get("status") != "completed":
        st.info("Results can be released after the student has submitted the complete assessment.")
    elif reading_pending or unreviewed_questions:
        parts = []
        if reading_pending:
            parts.append("reading aloud")
        if unreviewed_questions:
            parts.append(f"{len(unreviewed_questions)} image question(s)")
        st.warning(f"Verify {', '.join(parts)} before releasing the final results.")
    elif st.button("Approve and release final results", type="primary", width="stretch"):
        try:
            release_final_results(assignment["assignment_id"], st.session_state.user_id)
        except Exception as error:
            st.session_state["examiner_review_notice"] = {
                "level": "error",
                "message": f"The final results could not be released: {error}",
            }
        else:
            st.session_state["examiner_review_notice"] = {
                "level": "success",
                "message": "Final results released to the student.",
            }
        st.rerun()


def _provider_config_ready(provider: str) -> tuple[bool, str]:
    if provider == "anam":
        try:
            from anam_avatar import load_config
        except Exception as error:
            return False, f"Anam import error: {error}"
        return (True, "Anam credentials ready") if load_config() else (
            False,
            "Set ANAM_API_KEY plus ANAM_PERSONA_ID, or avatar/voice/LLM IDs.",
        )
    if provider == "simli":
        try:
            from simli_avatar import load_config
        except Exception as error:
            return False, f"Simli import error: {error}"
        return (True, "Simli credentials ready") if load_config() else (
            False,
            "Set SIMLI_API_KEY, SIMLI_FACE_ID, and OPENAI_API_KEY.",
        )
    return True, "Text-only fallback is active."


def render_demo_health_panel() -> None:
    provider = active_avatar_provider()
    avatar_ready, avatar_note = _provider_config_ready(provider)
    preparation_minutes = preparation_duration_seconds() // 60
    openai_ready = bool(os.getenv("OPENAI_API_KEY", "").strip())
    one_time_recording = not bool_env("ALLOW_STUDENT_RERECORD", False)
    rows = [
        {
            "Check": "OpenAI key",
            "Status": "Ready" if openai_ready else "Needs setup",
            "Details": "Used for question generation, transcription, and grading.",
        },
        {
            "Check": "Avatar provider",
            "Status": provider.title() if provider != "none" else "Text only",
            "Details": avatar_note,
        },
        {
            "Check": "Avatar configuration",
            "Status": "Ready" if avatar_ready else "Needs setup",
            "Details": "Presentation layer only; assessment still works with text fallback.",
        },
        {
            "Check": "Preparation timer",
            "Status": f"{preparation_minutes} minutes",
            "Details": "Controlled by PREPARATION_MINUTES in .env.",
        },
        {
            "Check": "Student recording",
            "Status": "One-time" if one_time_recording else "Retakes allowed",
            "Details": "Controlled by ALLOW_STUDENT_RERECORD in .env.",
        },
        {
            "Check": "Reading submission",
            "Status": "Fast" if bool_env("FAST_READING_SUBMISSION", True) else "Full AI grading during submit",
            "Details": (
                "Student moves on quickly; examiner sees deferred AI grade."
                if bool_env("FAST_READING_SUBMISSION", True)
                else "Student waits while reading grade is generated."
            ),
        },
        {
            "Check": "Deferred reading AI",
            "Status": "Enabled" if bool_env("DEFERRED_READING_AI_GRADING", True) else "Disabled",
            "Details": "Generates provisional reading grade after the student submits.",
        },
        {
            "Check": "Photo question generation",
            "Status": "Fast path" if bool_env("FAST_PHOTO_QUESTION_GENERATION", True) else "Full ingestion",
            "Details": "Fast path skips document chunking for standalone images.",
        },
    ]

    st.markdown("#### Demo health check")
    metric_cols = st.columns(3)
    metric_cols[0].metric("Avatar", provider.title() if provider != "none" else "Text only")
    metric_cols[1].metric("Preparation", f"{preparation_minutes} min")
    metric_cols[2].metric("Recording", "One-time" if one_time_recording else "Retakes")
    st.table(rows)
    if not openai_ready or not avatar_ready:
        st.warning("One or more demo services need configuration. The app will use available fallbacks where possible.")
    else:
        st.success("Core demo configuration is ready.")


def render_assignment_overview() -> None:
    assignments = list_assignments()
    st.subheader("Assignment overview")
    render_demo_health_panel()
    st.divider()
    delete_notice = st.session_state.pop("assignment_delete_notice", None)
    if delete_notice:
        if delete_notice.get("errors"):
            st.warning(delete_notice["message"])
        else:
            st.success(delete_notice["message"])
    if not assignments:
        st.info("Create an assessment to see it here.")
        return
    assignments.sort(key=lambda record: record.get("updated_at") or record.get("created_at") or "", reverse=True)
    assignments_by_id = {assignment["assignment_id"]: assignment for assignment in assignments}
    assignment_ids = list(assignments_by_id)
    if st.session_state.get("overview_assignment_picker") not in assignments_by_id:
        st.session_state["overview_assignment_picker"] = assignment_ids[0]
    selected_assignment_id = st.selectbox(
        "Select a student's assessment",
        assignment_ids,
        format_func=lambda assignment_id: _assignment_label(assignments_by_id[assignment_id]),
        key="overview_assignment_picker",
    )
    assignment = assignments_by_id[selected_assignment_id]
    results = assignment.get("results", [])
    score = sum((result.get("final_grading") or {}).get("total_score", 0) for result in results)
    maximum = sum((result.get("final_grading") or {}).get("max_score", 0) for result in results)
    col1, col2, col3 = st.columns(3)
    col1.metric("Questions graded", f"{len(results)}/{len(assignment.get('questions', []))}")
    col2.metric("Current score", f"{score}/{maximum}")
    col3.metric("Reading", "done" if assignment.get("reading_completed_at") else "not required" if not assignment.get("reading") else "pending")
    st.caption(f"Assigned: {assignment.get('created_at') or 'legacy record'} | Rubric: {assignment.get('rubric', '')}")
    st.divider()
    st.markdown("#### Reset student attempt")
    st.caption(
        "Remove the student's results, recordings, transcripts, and sessions, while keeping the "
        "assessment questions and materials ready for a fresh attempt."
    )
    reset_confirmed = st.checkbox(
        "I understand this resets the student's submitted attempt.",
        key=f"confirm_reset_results_{assignment['assignment_id']}",
    )
    if st.button(
        "Reset student results and sessions",
        type="secondary",
        disabled=not reset_confirmed,
        width="stretch",
        key=f"reset_results_{assignment['assignment_id']}",
    ):
        try:
            reset = reset_assignment_results(assignment["assignment_id"], st.session_state.user_id)
        except Exception as error:
            st.error(f"The student's attempt could not be reset: {error}")
        else:
            message = "Student results and sessions were reset. The assessment is ready for another attempt."
            if reset["errors"]:
                message += " Some related files could not be removed; see the application log."
            st.session_state["assignment_delete_notice"] = {
                "message": message,
                "errors": reset["errors"],
            }
            st.rerun()

    st.markdown("#### Delete entire test")
    st.warning(
        "Permanently delete this assessment, including its questions, materials, student results, "
        "recordings, transcripts, and sessions."
    )
    delete_confirmed = st.checkbox(
        "I understand this permanently deletes the student's entire test.",
        key=f"confirm_delete_assignment_{assignment['assignment_id']}",
    )
    if st.button(
        "Delete entire assessment",
        type="secondary",
        disabled=not delete_confirmed,
        width="stretch",
        key=f"delete_assignment_{assignment['assignment_id']}",
    ):
        try:
            deleted = delete_assignment(assignment["assignment_id"], st.session_state.user_id)
        except Exception as error:
            st.error(f"The assessment could not be deleted: {error}")
        else:
            message = "The assessment and its student submissions were deleted."
            if deleted["errors"]:
                message += " Some related files could not be removed; see the application log."
            st.session_state["assignment_delete_notice"] = {
                "message": message,
                "errors": deleted["errors"],
            }
            st.rerun()


def render_examiner_portal() -> None:
    render_account_sidebar("Examiner")
    st.title("Examiner Dashboard")
    st.caption("Upload one image, optionally add a reading passage, assign it to a registered student, then verify AI grading.")
    section_options = ["Assign assessment", "Results and review", "Overview"]
    if st.session_state.get("examiner_section") not in section_options:
        st.session_state.examiner_section = section_options[0]
    section_columns = st.columns(3, gap="small")
    for column, option in zip(section_columns, section_options):
        with column:
            if st.button(option, key=f"examiner_section_{option.lower().replace(' ', '_')}", width="stretch"):
                st.session_state.examiner_section = option
    section = st.session_state.examiner_section
    if section == "Assign assessment":
        render_create_assignment()
    elif section == "Results and review":
        render_examiner_review()
    else:
        render_assignment_overview()


def student_progress_stage(assignment: dict) -> str:
    """Return the current high-level student workflow stage for the progress bar."""
    if assignment.get("results_released_at"):
        return "results"
    if assignment.get("status") == "completed":
        return "submitted"

    portal_stage = st.session_state.get("student_portal_stage")
    if portal_stage in {"preparation_loading", "preparation"} or not st.session_state.get("preparation_complete"):
        return "preparation"

    if assignment.get("reading") and not assignment.get("reading_submission"):
        return "reading"
    return "questions"


def render_student_progress_indicator(assignment: dict) -> None:
    steps = [
        ("preparation", "Preparation"),
        ("reading", "Reading Aloud"),
        ("questions", "Image Questions"),
        ("submitted", "Submitted"),
        ("results", "Results"),
    ]
    active_stage = student_progress_stage(assignment)
    active_index = next(
        (index for index, (stage, _label) in enumerate(steps) if stage == active_stage),
        0,
    )
    step_html = []
    for index, (stage, label) in enumerate(steps):
        state = "done" if index < active_index else "active" if index == active_index else "pending"
        aria_current = "step" if stage == active_stage else "false"
        step_html.append(
            f'<div class="student-step {state}" aria-current="{aria_current}">'
            f'<span class="student-step-dot">{index + 1}</span>'
            f'<span class="student-step-text">{html_escape(label)}</span>'
            "</div>"
        )
    st.markdown(
        f'<nav class="student-stepbar" aria-label="Assessment progress">{"".join(step_html)}</nav>',
        unsafe_allow_html=True,
    )


def start_preparation_timer(assignment: dict) -> None:
    """Start the preparation timer only after the selected materials page opens."""
    assignment_id = assignment.get("assignment_id")
    if (
        st.session_state.preparation_timer_assignment_id != assignment_id
        or not st.session_state.preparation_deadline
    ):
        st.session_state.preparation_deadline = time.time() + preparation_duration_seconds()
        st.session_state.preparation_timer_assignment_id = assignment_id


def preparation_materials_status(assignment: dict) -> tuple[bool, list[str]]:
    """Verify preparation assets before starting the student's timer."""
    missing: list[str] = []
    if not visual_path(assignment):
        missing.append("picture stimulus")

    reading = assignment.get("reading")
    if reading:
        reading_text = str(reading.get("text", "")).strip()
        if not reading_text:
            missing.append("reading passage text")

    return not missing, missing


def render_preparation_loading(assignment: dict) -> None:
    st.subheader("Preparing your materials")
    ready, missing = preparation_materials_status(assignment)
    reading_note = " and reading passage" if assignment.get("reading") else ""
    if not ready:
        st.markdown(
            f"""
            <div class="prep-loading-card">
              <div class="prep-loader"></div>
              <div>
                <h3>Checking your assessment pack</h3>
                <p>Looking for the picture stimulus{reading_note} before the timer begins.</p>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        time.sleep(0.8)
        st.error(
            "This assessment cannot open yet because the following material is missing: "
            f"{', '.join(missing)}."
        )
        st.caption("Ask your examiner to re-upload or recreate the assessment. The preparation timer has not started.")
        if st.button("Back to assessment selection", width="stretch"):
            st.session_state.student_portal_stage = "selection"
            st.session_state.student_selected_assignment_id = None
            st.rerun()
        return

    st.markdown(
        f"""
        <style>
        .preparation-loading-overlay {{
            position: fixed;
            inset: 0;
            z-index: 999999;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 2rem;
            background: radial-gradient(circle at 12% 10%, #e3f3e7 0, #f6fbf7 38%, #fbfcf8 74%, #eaf4ec 100%);
        }}
        .preparation-loading-shell {{
            width: min(680px, 92vw);
        }}
        .preparation-loading-overlay .prep-loading-card {{
            background: rgba(255, 255, 253, 0.98);
            margin-bottom: 0.75rem;
        }}
        .preparation-loading-steps {{
            display: grid;
            gap: 0.5rem;
            padding: 0 0.35rem;
            color: #47665b;
            font-family: Aptos, Segoe UI, sans-serif;
            font-size: 0.92rem;
        }}
        .preparation-loading-step {{
            display: flex;
            align-items: center;
            gap: 0.55rem;
        }}
        .preparation-loading-dot {{
            width: 0.55rem;
            height: 0.55rem;
            border-radius: 999px;
            background: #5b9d73;
            box-shadow: 0 0 0 4px rgba(91, 157, 115, 0.16);
        }}
        </style>
        <div class="preparation-loading-overlay">
          <div class="preparation-loading-shell">
            <div class="prep-loading-card">
              <div class="prep-loader"></div>
              <div>
                <h3>Opening your assessment pack</h3>
                <p>Loading the picture stimulus{reading_note}. Your timer starts only after these materials are ready.</p>
              </div>
            </div>
            <div class="preparation-loading-steps">
              <div class="preparation-loading-step"><span class="preparation-loading-dot"></span><span>Checking picture stimulus</span></div>
              <div class="preparation-loading-step"><span class="preparation-loading-dot"></span><span>Checking reading passage</span></div>
              <div class="preparation-loading-step"><span class="preparation-loading-dot"></span><span>Preparing timed view</span></div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    time.sleep(1.1)

    st.session_state.preparation_deadline = None
    st.session_state.preparation_timer_assignment_id = None
    st.session_state.preparation_complete = False
    st.session_state.student_portal_stage = "preparation"
    st.rerun()

def render_assessment_loading(assignment: dict) -> None:
    st.session_state.preparation_deadline = None
    st.session_state.preparation_timer_assignment_id = None
    st.session_state.preparation_complete = True
    st.subheader("Setting up your assessment")
    st.markdown(
        """
        <style>
        .assessment-loading-overlay {
            position: fixed;
            inset: 0;
            z-index: 999999;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 2rem;
            background: radial-gradient(circle at 14% 12%, #dff4e4 0, #eff8f0 34%, #fbfcf8 70%, #eaf4ec 100%);
        }
        .assessment-loading-overlay .prep-loading-card {
            width: min(620px, 92vw);
            background: rgba(255, 255, 253, 0.98);
        }
        </style>
        <div class="assessment-loading-overlay">
          <div class="prep-loading-card">
            <div class="prep-loader"></div>
            <div>
              <h3>Preparing the exam room</h3>
              <p>Preparation materials are locked. Getting the examiner and assessment ready.</p>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    crew = ensure_assignment_crew(assignment)
    if not st.session_state.session_id:
        if not restore_assignment_session(crew, assignment["assignment_id"]):
            st.session_state.session_id = crew.start_session(
                metadata={"assignment_id": assignment["assignment_id"], "component": "student_assessment"}
            )
            mark_assignment_status(assignment["assignment_id"], "in_progress")
    answered_ids = {result.get("question_id") for result in assignment.get("results", [])}
    next_question = next(
        (item for item in assignment.get("questions", []) if item.get("id") not in answered_ids),
        None,
    )
    collect_avatar_preload_results()
    if not next_question:
        time.sleep(0.4)
    st.session_state.preparation_complete = True
    st.session_state.student_portal_stage = "assessment"
    st.rerun()


def question_avatar_cache_key(assignment_id: str, question: dict) -> str:
    question_id = str(question.get("id", ""))
    return f"{assignment_id}_{question_id}_question"


def question_has_saved_avatar(question: dict) -> bool:
    avatar_video = question.get("avatar_video") or {}
    if not avatar_video:
        return False
    path = avatar_video.get("path")
    if path and Path(path).exists() and is_probably_mp4(Path(path)):
        return True
    return bool(avatar_video.get("ready") and avatar_video.get("source_url"))


def avatar_preload_entries(assignment: dict) -> list[dict]:
    assignment_id = assignment.get("assignment_id", "")
    entries = []
    cache = st.session_state.setdefault("simli_avatar_cache", {})
    errors = st.session_state.setdefault("simli_avatar_errors", {})
    for index, question in enumerate(assignment.get("questions", []), 1):
        text = question.get("text", "")
        cache_key = question_avatar_cache_key(assignment_id, question)
        clean_text, avatar_cache_key = avatar_cache_key_for(text, cache_key)
        if not clean_text:
            continue
        entries.append(
            {
                "number": index,
                "text": clean_text,
                "cache_key": cache_key,
                "avatar_cache_key": avatar_cache_key,
                "ready": bool(cache.get(avatar_cache_key)),
                "error": errors.get(avatar_cache_key),
            }
        )
    return entries


@st.fragment(run_every=12)
def render_examiner_avatar_warmup(assignment: dict) -> None:
    """Only collect already-running avatar jobs; do not create new avatars during student prep."""
    if anam_avatar_requested():
        st.caption("Anam live examiner avatar is enabled. The examiner will speak each prompt during the assessment.")
        return

    collect_avatar_preload_results()
    saved_count = sum(1 for question in assignment.get("questions", []) if question_has_saved_avatar(question))
    total = len(assignment.get("questions", []))
    if total and saved_count == total:
        st.caption("Examiner avatar videos are already prepared for this assessment.")
    elif total:
        st.caption(
            f"{saved_count}/{total} examiner avatar video(s) were pre-prepared. "
            "Any missing avatar will fall back to the written question during assessment."
        )


def render_student_materials(assignment: dict) -> None:
    st.subheader("Your materials")
    st.write(f"**Assessment:** {assignment.get('title')}")
    image = visual_path(assignment)
    if image:
        st.image(image, caption="Picture stimulus", width="stretch")
    else:
        st.warning("The picture stimulus is unavailable. Ask your examiner to upload the assessment again.")

    if assignment.get("reading"):
        st.markdown("#### Reading passage preparation")
        st.caption("Read and prepare this passage here. You will record and submit it at the start of Take assessment.")
        st.text_area(
            "Reading passage",
            value=assignment["reading"].get("text", ""),
            height=220,
            disabled=True,
            key=f"materials_reading_{assignment['assignment_id']}",
        )
    else:
        st.caption("No reading-aloud passage was assigned for this assessment.")

    render_examiner_avatar_warmup(assignment)
    st.divider()
    st.warning("Continuing starts the assessment phase. You will not be able to return to these preparation materials.")
    if st.button("Continue to assessment", type="primary", width="stretch"):
        st.session_state.preparation_deadline = None
        st.session_state.preparation_timer_assignment_id = None
        st.session_state.preparation_complete = True
        st.session_state.student_portal_stage = "assessment_loading"
        st.rerun()
    start_preparation_timer(assignment)


@st.fragment(run_every=1)
def render_preparation_timer() -> None:
    """Display and enforce the student preparation window."""
    deadline = st.session_state.preparation_deadline
    if not deadline or st.session_state.preparation_complete:
        return

    seconds_remaining = max(0, int(deadline - time.time()))
    if seconds_remaining == 0:
        st.session_state.preparation_deadline = None
        st.session_state.preparation_timer_assignment_id = None
        st.session_state.preparation_complete = True
        st.session_state.student_portal_stage = "assessment_loading"
        st.rerun(scope="app")

    minutes, seconds = divmod(seconds_remaining, 60)
    total_seconds = preparation_duration_seconds()
    total_minutes = total_seconds // 60
    st.info(f"Preparation time remaining: **{minutes:02d}:{seconds:02d}** out of {total_minutes} minutes.")
    st.progress(min(1.0, seconds_remaining / total_seconds))


def ungraded_reading_result(reading_criteria: list[str]) -> dict:
    scores = [
        {
            "criterion": criterion,
            "score": 0,
            "max_score": 0,
            "feedback": "Pending examiner review.",
            "evidence": "Fast reading submission saved the recording without provisional AI grading.",
        }
        for criterion in reading_criteria
    ]
    return {
        "total_score": 0,
        "max_score": 0,
        "percentage": 0,
        "scores": scores,
        "tutoring_feedback": "Reading-aloud recording submitted. Examiner review is pending.",
        "scoring_source": "pending_examiner_review",
    }


def render_reading_before_questions(assignment: dict, crew: EducationCrew) -> bool:
    """Collect the reading-aloud submission before image questions begin."""
    reading = assignment.get("reading")
    if not reading:
        return True
    submission = assignment.get("reading_submission")
    if submission:
        return True

    reading_lock_key = f"reading_submission_locked_{assignment['assignment_id']}"
    st.markdown("### Reading Aloud")
    st.caption("Read this passage aloud and submit your recording once. You will not be able to review the transcript or retake it after submission.")
    st.text_area(
        "Reading passage",
        value=reading.get("text", ""),
        height=250,
        disabled=True,
        key=f"assessment_reading_{assignment['assignment_id']}",
    )

    if st.session_state.get(reading_lock_key):
        st.info("Your reading-aloud recording has been submitted and is being processed.")
        return False

    captured = capture_student_response(
        f"reading_{assignment['assignment_id']}",
        "Submit reading aloud",
        allow_skip=bool_env("ALLOW_READING_SKIP", False),
        skip_label="Skip reading aloud",
        review_transcript=False,
        include_delivery=not bool_env("FAST_READING_SUBMISSION", True),
    )
    if not captured:
        return False
    st.session_state[reading_lock_key] = True
    try:
        reading_criteria = crew.get_reading_criterion_names()
        if not reading_criteria:
            raise ValueError("The selected rubric does not contain a reading-aloud delivery criterion.")

        if bool_env("FAST_READING_SUBMISSION", True) and not captured.get("skipped"):
            grading_result = ungraded_reading_result(reading_criteria)
            save_reading_submission(
                assignment["assignment_id"],
                transcript=captured["text"],
                response_mode=captured.get("mode", "voice"),
                audio_path=captured.get("audio_path"),
                transcription_path=captured.get("transcription_path"),
                delivery_indicators=captured.get("delivery_indicators"),
                grading_result=grading_result,
                crew_analysis=(
                    "Fast reading submission was enabled. The student's recording and transcript "
                    "were saved immediately for examiner review. A deferred provisional AI reading "
                    "grade was queued in the background."
                ),
            )
            queue_deferred_reading_ai_grading(
                assignment,
                transcript=captured["text"],
                audio_path=captured.get("audio_path"),
                transcription_path=captured.get("transcription_path"),
                delivery_indicators=captured.get("delivery_indicators"),
                reading_criteria=reading_criteria,
            )
            st.session_state.pop(reading_lock_key, None)
            st.rerun()

        if captured.get("skipped"):
            evidence = {
                "audio_evidence": "The student skipped the reading-aloud task.",
                "delivery_indicators": None,
                "limitation": "No reading-aloud recording was submitted.",
            }
        else:
            evidence = {
                "audio_evidence": "A student recording was submitted for examiner review.",
                "delivery_indicators": captured.get("delivery_indicators"),
                "limitation": "Transcript and automated pace/pitch indicators cannot verify pronunciation on their own.",
            }
        render_student_processing_overlay(
            "Saving reading submission",
            "Preparing the reading-aloud record before moving on.",
        )
        workflow = crew.run_assessment_workflow(
            question="Reading-aloud submission. Assess only the selected reading-delivery rubric criteria.",
            student_response=captured["text"],
            context=json.dumps(evidence, indent=2),
            visual_context=f"Audio evidence: {json.dumps(evidence)}",
            save_to_session=True,
            audio_path=captured.get("audio_path"),
            transcription_path=captured.get("transcription_path"),
            delivery_indicators=captured.get("delivery_indicators"),
            criterion_names=reading_criteria,
            skipped=bool(captured.get("skipped")),
        )
        save_reading_submission(
            assignment["assignment_id"],
            transcript=captured["text"],
            response_mode=captured.get("mode", "voice"),
            audio_path=captured.get("audio_path"),
            transcription_path=captured.get("transcription_path"),
            delivery_indicators=captured.get("delivery_indicators"),
            grading_result=workflow["grading_result"],
            crew_analysis=workflow.get("crew_analysis", ""),
        )
        st.session_state.pop(reading_lock_key, None)
        st.rerun()
    except Exception as error:
        st.session_state.pop(reading_lock_key, None)
        st.error(f"The reading-aloud submission could not be saved: {error}")
    st.info("Submit the reading-aloud recording to unlock the image questions.")
    return False


def fast_assessment_response_flow() -> bool:
    return bool_env("FAST_ASSESSMENT_RESPONSE_FLOW", True)


def _finish_if_complete(assignment: dict, crew: EducationCrew) -> bool:
    question_ids = {question.get("id") for question in assignment.get("questions", [])}
    answered_ids = {result.get("question_id") for result in assignment.get("results", [])}
    if question_ids and question_ids.issubset(answered_ids):
        if assignment.get("status") != "completed":
            mark_assignment_status(assignment["assignment_id"], "completed")
        if st.session_state.session_id:
            crew.end_session()
        return True
    return False


def render_student_assessment(assignment: dict) -> None:
    collect_deferred_reading_ai_grading()
    st.subheader("Take assessment")
    if assignment.get("status") == "completed":
        st.success("You have already submitted this assessment. It can only be taken once.")
        if assignment.get("results_released_at"):
            st.info("Your examiner has released the final results in the Results tab.")
        else:
            st.info("Your submission is with the examiner for verification. Final results will appear in the Results tab once released.")
        return
    questions = assignment.get("questions", [])
    if not questions:
        st.warning("This legacy assignment has no saved questions. Ask the examiner to upload a new assessment.")
        return

    crew = ensure_assignment_crew(assignment)

    answered_ids = {result.get("question_id") for result in assignment.get("results", [])}
    if not st.session_state.session_id:
        if restore_assignment_session(crew, assignment["assignment_id"]):
            st.rerun()
        st.info("Your assessment session is being prepared.")
        return

    if _finish_if_complete(assignment, crew):
        st.success("Assessment submitted. Your examiner will verify the grades before releasing your final results.")
        return

    if not render_reading_before_questions(assignment, crew):
        return

    question = next((item for item in questions if item.get("id") not in answered_ids), None)
    if not question:
        st.info("No further questions are available.")
        return

    current_number = len(answered_ids) + 1
    question_id = str(question.get("id", ""))
    guidance = (assignment.get("guidance_attempts") or {}).get(question_id)
    pending_key = f"pending_response_{assignment['assignment_id']}_{question_id}"
    transition_key = f"examiner_transition_ready_{assignment['assignment_id']}_{question_id}"
    pending_response = st.session_state.get(pending_key)
    question_text = question.get("text", "")
    examiner_prompt = guidance.get("follow_up_question", "") if guidance else question_text
    examiner_cache_kind = "guidance" if guidance else "question"
    examiner_avatar_cache_key = (
        question_avatar_cache_key(assignment["assignment_id"], question)
        if examiner_cache_kind == "question"
        else f"{assignment['assignment_id']}_{question_id}_guidance"
    )
    response_key_suffix = (
        f"follow_up_{assignment['assignment_id']}_{question_id}"
        if guidance
        else f"response_{assignment['assignment_id']}_{question_id}"
    )
    avatar_prompt = examiner_prompt
    avatar_cache_key = examiner_avatar_cache_key
    avatar_auto_play = avatar_auto_play_once(avatar_cache_key, avatar_prompt)
    image = visual_path(assignment)

    st.markdown(
        f"""
        <section class="assessment-room-title">
          <div>
            <p>Image questions</p>
            <h2>{html_escape(question_text)}</h2>
          </div>
          <div class="assessment-badge">Question {current_number} of {len(questions)}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.progress(current_number / len(questions), text=f"Question {current_number} of {len(questions)}")

    examiner_col, stimulus_col = st.columns([0.95, 1.05], gap="large", vertical_alignment="top")
    with examiner_col:
        st.markdown('<div class="assessment-panel-label">Step 1 - Listen to the examiner</div>', unsafe_allow_html=True)
        stored_avatar = None if guidance or anam_avatar_requested() else refresh_avatar_video_reference(question.get("avatar_video") or {})
        stored_avatar_path = stored_avatar.get("path") if stored_avatar else None
        stored_avatar_url = stored_avatar.get("source_url") if stored_avatar else None
        stored_avatar_ready = bool(stored_avatar.get("ready")) if stored_avatar else False
        if stored_avatar_path and render_avatar_video_file(
            stored_avatar_path,
            element_key=f"stored_avatar_{assignment['assignment_id']}_{question_id}",
            subtitle=avatar_prompt,
        ):
            pass
        elif stored_avatar_ready and stored_avatar_url and render_avatar_video(
            stored_avatar_url,
            element_key=f"stored_avatar_url_{assignment['assignment_id']}_{question_id}",
            subtitle=avatar_prompt,
        ):
            pass
        elif guidance:
            queue_examiner_avatar_preload(examiner_prompt, cache_key=examiner_avatar_cache_key)
            render_examiner_avatar(avatar_prompt, cache_key=avatar_cache_key, auto_play=avatar_auto_play)
        else:
            render_examiner_avatar(avatar_prompt, cache_key=avatar_cache_key, auto_play=avatar_auto_play)
        if guidance:
            st.markdown(
                '<div class="assessment-help-card">Listen to the examiner guiding question, then record your final response. Your first response and this response will be assessed together.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="assessment-help-card">Press play if the examiner video is available, then look at the picture and answer the question.</div>',
                unsafe_allow_html=True,
            )

    with stimulus_col:
        st.markdown('<div class="assessment-panel-label">Step 2 - Look at the picture</div>', unsafe_allow_html=True)
        if image:
            st.image(image, caption="Picture stimulus", width="stretch")
        else:
            st.warning("The picture stimulus is unavailable. Ask your examiner to upload the assessment again.")

    if pending_response:
        captured = pending_response["captured"]
        skipped = pending_response["skipped"]
        follow_up_answer = pending_response.get("follow_up_answer")
        answer_for_grading = pending_response["answer_for_grading"]
        grading_context = pending_response.get("grading_context")
        examiner_transition = pending_response.get(
            "examiner_transition", ""
        )
    elif guidance:
        with st.container(border=True):
            st.markdown("### Step 3 - Record your final response")
            st.caption("Respond to the guiding question using the microphone. The system will combine this with your first answer for grading.")
            captured = capture_student_response(
                response_key_suffix,
                "Submit final response",
                review_transcript=not fast_assessment_response_flow(),
                include_delivery=not fast_assessment_response_flow(),
            )
        if not captured:
            return
        skipped = captured["skipped"]
        follow_up_answer = captured["text"] if not skipped else "[No response after guidance]"
        answer_for_grading = combined_guided_response(guidance, follow_up_answer)
        grading_context = json.dumps({"examiner_guidance": guidance}, indent=2)
        examiner_transition = ""
    else:
        with st.container(border=True):
            st.markdown("### Step 3 - Give your answer")
            if fast_assessment_response_flow():
                st.caption("Record your answer with the microphone, then submit it. The examiner will respond automatically.")
            else:
                st.caption("Record your answer with the microphone, transcribe it, check the text, then submit.")
            captured = capture_student_response(
                response_key_suffix,
                "Submit response",
                review_transcript=not fast_assessment_response_flow(),
                include_delivery=not fast_assessment_response_flow(),
            )
        if not captured:
            return
        skipped = captured["skipped"]
        if not skipped:
            render_student_processing_overlay(
                "Checking your answer",
                "The examiner is deciding whether to guide you or move to the next question.",
            )
            decision = crew.evaluate_oral_turn(
                question=assessment_question_with_visual_context(question),
                student_response=captured["text"],
                attempt_number=1,
                max_attempts=2,
                fast_evaluation=bool_env("FAST_ORAL_TURN_EVALUATION", True),
            )
            if not decision.get("accepted"):
                follow_up_question = decision.get("examiner_reply") or (
                    "What is one detail you can see in the picture that helps answer the question?"
                )
                try:
                    save_guidance_attempt(
                        assignment["assignment_id"],
                        question=question,
                        original_response=captured["text"],
                        follow_up_question=follow_up_question,
                        reason=decision.get("reason", ""),
                        response_mode=captured.get("mode", "voice"),
                        audio_path=captured.get("audio_path"),
                        transcription_path=captured.get("transcription_path"),
                        delivery_indicators=captured.get("delivery_indicators"),
                    )
                except Exception as error:
                    st.error(f"The guiding question could not be saved: {error}")
                    return
                guidance_avatar_cache_key = f"{assignment['assignment_id']}_{question_id}_guidance"
                if simli_avatar_requested():
                    st.markdown(
                        """
                        <div class="prep-loading-card">
                          <div class="prep-loader"></div>
                          <div>
                            <h3>Preparing examiner guidance</h3>
                            <p>The examiner is preparing a spoken guiding question for your next attempt.</p>
                          </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    render_student_processing_overlay(
                        "Preparing guidance",
                        "The examiner is preparing a spoken guiding question for your next attempt.",
                    )
                    prepare_examiner_avatar(follow_up_question, cache_key=guidance_avatar_cache_key)
                st.session_state.pop(pending_key, None)
                st.session_state.pop(transition_key, None)
                st.rerun()
            examiner_transition = ""
            follow_up_answer = None
            answer_for_grading = captured["text"]
            grading_context = None
        else:
            examiner_transition = ""
            follow_up_answer = None
            answer_for_grading = "[Skipped question]"
            grading_context = None

    if not pending_response:
        st.session_state[pending_key] = {
            "captured": captured,
            "skipped": skipped,
            "follow_up_answer": follow_up_answer,
            "answer_for_grading": answer_for_grading,
            "grading_context": grading_context,
            "examiner_transition": examiner_transition,
        }

    if examiner_transition and not st.session_state.get(transition_key):
        render_examiner_transition(
            examiner_transition,
            cache_key=f"{assignment['assignment_id']}_{question_id}_transition",
        )
        if st.button("Continue", type="primary", width="stretch", key=f"continue_after_avatar_{assignment['assignment_id']}_{question_id}"):
            st.session_state[transition_key] = True
            st.rerun()
        st.caption("Continue after the examiner response has played.")
        return
    if not examiner_transition:
        st.session_state[transition_key] = True

    render_student_processing_overlay(
        "Saving your response",
        "The examiner is grading this answer and preparing the next step.",
    )
    try:
        workflow = crew.run_assessment_workflow(
            question=question.get("text", ""),
            student_response=answer_for_grading,
            context=grading_context,
            visual_context=question.get("visual_context"),
            save_to_session=True,
            skipped=skipped,
            audio_path=captured.get("audio_path"),
            transcription_path=captured.get("transcription_path"),
            delivery_indicators=captured.get("delivery_indicators"),
        )
        add_assessment_result(
            assignment["assignment_id"],
            question=question,
            student_response=answer_for_grading,
            grading_result=workflow["grading_result"],
            session_id=st.session_state.session_id,
            crew_analysis=workflow.get("crew_analysis", ""),
            skipped=skipped,
            follow_up_response=follow_up_answer,
            response_mode=captured.get("mode", "voice"),
            audio_path=captured.get("audio_path"),
            transcription_path=captured.get("transcription_path"),
            delivery_indicators=captured.get("delivery_indicators"),
        )
    except Exception as error:
        st.error(f"Your response was not saved: {error}")
        return
    st.session_state.pop(pending_key, None)
    st.session_state.pop(transition_key, None)
    st.rerun()


def render_student_results(assignment: dict) -> None:
    st.subheader("Your results")
    if not assignment.get("results_released_at"):
        if assignment.get("status") == "completed":
            st.info("Your assessment has been submitted. Final results will appear here after your examiner verifies and releases them.")
        else:
            st.info("Final results will appear here after you complete the assessment and your examiner releases them.")
        return
    reading_submission = assignment.get("reading_submission")
    if reading_submission and (reading_submission.get("final_grading") or reading_submission.get("ai_grading")):
        with st.expander("Reading aloud", expanded=True):
            render_grading_result(reading_submission.get("final_grading") or reading_submission.get("ai_grading"))
            render_examiner_feedback_note(reading_submission.get("examiner_review"))
    results = assignment.get("results", [])
    if not results:
        st.info("Submit an image-question response to see its AI grade here.")
        return
    for number, result in enumerate(results, 1):
        with st.expander(f"Question {number}", expanded=(number == len(results))):
            st.write("**Question:**", result.get("question", ""))
            render_recorded_response(result)
            render_grading_result(result.get("final_grading") or result.get("ai_grading") or {})
            if result.get("examiner_review"):
                st.caption("An examiner has verified or adjusted this grade.")
                render_examiner_feedback_note(result.get("examiner_review"))


def render_student_portal() -> None:
    render_account_sidebar("Student")
    st.title("Student Assessment")
    assignments = [
        record
        for record in list_assignments(st.session_state.user_id)
        if record.get("questions")
    ]
    assignments.sort(key=lambda record: record.get("updated_at") or record.get("created_at") or "", reverse=True)
    if not assignments:
        st.info("No assessment has been assigned to your student ID yet.")
        return

    def student_assignment_label(record: dict) -> str:
        status = record.get("status", "assigned").replace("_", " ").title()
        if record.get("results_released_at"):
            status = "Completed - results available"
        elif record.get("status") == "completed":
            status = "Submitted — awaiting examiner"
        return f"{record.get('title', 'Assessment')} — {status}"

    assignments_by_id = {record["assignment_id"]: record for record in assignments}
    assignment_ids = list(assignments_by_id)
    if st.session_state.student_portal_stage == "selection":
        st.subheader("Select your assessment")
        st.caption("Choose the assessment assigned by your examiner before opening its preparation materials.")
        if st.session_state.get("student_assignment_id_picker") not in assignments_by_id:
            st.session_state.student_assignment_id_picker = assignment_ids[0]
        selected_assignment_id = st.selectbox(
            "Assigned assessment",
            assignment_ids,
            format_func=lambda assignment_id: student_assignment_label(assignments_by_id[assignment_id]),
            key="student_assignment_id_picker",
        )
        selected_assignment = assignments_by_id[selected_assignment_id]
        completed = selected_assignment.get("status") == "completed"
        if completed:
            if selected_assignment.get("results_released_at"):
                st.success("This assessment is complete and your examiner has released the final results.")
            else:
                st.info("This assessment is complete and is awaiting your examiner's verified results.")
        st.info(
            f"**{selected_assignment.get('title', 'Assessment')}** — "
            f"{len(selected_assignment.get('questions', []))} image question(s) assigned."
        )
        next_step_label = "View assessment results" if completed else "Continue to preparation materials"
        if st.button(next_step_label, type="primary", width="stretch"):
            if st.session_state.active_assignment_id != selected_assignment_id:
                reset_runtime_state()
            st.session_state.active_assignment_id = selected_assignment_id
            st.session_state.student_selected_assignment_id = selected_assignment_id
            st.session_state.preparation_deadline = None
            st.session_state.preparation_timer_assignment_id = None
            st.session_state.preparation_complete = False
            st.session_state.student_portal_stage = "results" if completed else "preparation_loading"
            st.rerun()
        return

    selected_assignment_id = st.session_state.student_selected_assignment_id
    if selected_assignment_id not in assignments_by_id:
        st.session_state.student_portal_stage = "selection"
        st.session_state.student_selected_assignment_id = None
        st.warning("That assessment is no longer available. Please select another assessment.")
        st.rerun()

    assignment = assignments_by_id[selected_assignment_id]
    if st.session_state.active_assignment_id != assignment["assignment_id"]:
        reset_runtime_state()
        st.session_state.active_assignment_id = assignment["assignment_id"]
    render_student_progress_indicator(assignment)
    st.caption(f"Status: {assignment.get('status', 'assigned').replace('_', ' ').title()}")
    if st.session_state.student_portal_stage == "preparation_loading":
        render_preparation_loading(assignment)
        return
    if st.session_state.student_portal_stage == "assessment_loading":
        render_assessment_loading(assignment)
        return
    if assignment.get("status") == "completed":
        st.subheader("Assessment complete")
        if assignment.get("results_released_at"):
            st.success("Your examiner has verified and released your final results.")
        else:
            st.info("You have completed this assessment. Your examiner is reviewing the results.")
        render_student_results(assignment)
        return
    if st.session_state.preparation_complete or st.session_state.student_portal_stage == "assessment":
        st.info("Preparation materials are locked. Continue with the assessment.")
        render_student_assessment(assignment)
        return

    render_preparation_timer()
    render_student_materials(assignment)

apply_portal_theme()

if not st.session_state.authenticated:
    render_login()
    st.stop()

if st.session_state.user_role == "examiner":
    render_examiner_portal()
else:
    render_student_portal()
