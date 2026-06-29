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
    save_reading_submission,
    reset_assignment_results,
)
from subject_manager import SubjectManager
from voice_assessment import transcribe_streamlit_audio

load_dotenv()

# Keep the portal shell fast. The CrewAI stack imports PyTorch and LangChain, so
# it is loaded only when a student begins an assessment or an examiner generates
# a new one.
DEFAULT_PSLE_RUBRIC = "psle_oral_english"

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
    ("simli_avatar_cache", {}),
    ("simli_avatar_errors", {}),
    ("simli_avatar_futures", {}),
    ("simli_avatar_future_meta", {}),
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
            st.caption(criterion["feedback"])
        if criterion.get("evidence"):
            st.caption(f"Evidence: {criterion['evidence']}")

    if grading.get("tutoring_feedback"):
        st.info(grading["tutoring_feedback"])


def save_uploaded_file(uploaded_file, directory: Path) -> Path:
    """Save an upload under a controlled temporary directory."""
    safe_name = Path(uploaded_file.name).name
    path = directory / safe_name
    path.write_bytes(uploaded_file.getbuffer())
    return path


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


def simli_avatar_requested() -> bool:
    return os.getenv("ENABLE_SIMLI_AVATAR", "").strip().lower() in {"1", "true", "yes", "on"}


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
    return clean_text, f"simli_v2:{cache_key}:{text_hash}"


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


def create_avatar_video_in_background(text: str) -> str:
    """Worker-safe avatar generation. Do not access Streamlit state in this function."""
    from simli_avatar import create_avatar_video_url

    return create_avatar_video_url(text)


def avatar_terminal_log(message: str) -> None:
    """Print avatar preload progress only to the Streamlit terminal."""
    enabled = os.getenv("AVATAR_PRELOAD_TERMINAL_LOG", "true").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        return
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] [avatar-preload] {message}", flush=True)


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


def render_examiner_avatar(text: str, *, cache_key: str) -> None:
    """Render a Simli examiner avatar for already-selected examiner text.

    Simli is intentionally presentation-only: the app still decides the
    question, guidance, grading, and whether the student moves on.
    """
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
        if not render_avatar_video(cached, element_key=f"simli_{avatar_cache_key}", subtitle=clean_text):
            st.markdown(f"**Examiner says:** {clean_text}")
            if st.button("Reload examiner video", key=f"reload_bad_avatar_{avatar_cache_key}", width="stretch"):
                st.rerun()
        return

    if avatar_cache_key in futures and not futures[avatar_cache_key].done():
        st.info("The examiner video is still getting ready. You can read the question below while it finishes.")
        st.markdown(f"**Examiner says:** {clean_text}")
        if st.button("Load examiner video", key=f"load_avatar_{avatar_cache_key}", width="stretch"):
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
    if not render_avatar_video(url, element_key=f"simli_{avatar_cache_key}", subtitle=clean_text):
        st.markdown(f"**Examiner says:** {clean_text}")
        if st.button("Reload examiner video", key=f"reload_new_avatar_{avatar_cache_key}", width="stretch"):
            st.rerun()


def render_examiner_transition(message: str, *, cache_key: str) -> None:
    clean_message = " ".join((message or "").split())
    if not clean_message:
        return
    st.success(clean_message)
    render_examiner_avatar(clean_message, cache_key=cache_key)


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


def render_avatar_video(url: str, *, element_key: str, subtitle: str = "") -> bool:
    subtitle_html = html_escape(subtitle)
    is_hls = ".m3u8" in url.lower()
    if not is_hls:
        try:
            local_video = cache_avatar_video_file(url)
            video_base64 = base64.b64encode(local_video.read_bytes()).decode("ascii")
        except Exception as error:
            cache = st.session_state.setdefault("simli_avatar_cache", {})
            for cached_key, cached_url in list(cache.items()):
                if cached_url == url:
                    cache.pop(cached_key, None)
            st.warning(f"The examiner video was generated but could not be loaded into the page: {error}")
            st.caption("The question is still shown below so the assessment can continue. Try reloading the examiner video in a moment.")
            return False
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
                <span>Ready</span>
              </div>
              <video class="avatar-native-video" controls preload="auto" playsinline>
                <source src="data:video/mp4;base64,{video_base64}" type="video/mp4">
                Your browser cannot play this examiner video.
              </video>
              <div class="avatar-native-subtitle"><strong>Subtitles:</strong> {subtitle_html}</div>
              <div class="avatar-native-help">Press the video play button to hear the examiner. Use the fullscreen control if needed.</div>
            </div>
            """,
            height=520,
            scrolling=False,
        )
        return True

    safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", element_key)
    safe_id_json = json.dumps(safe_id)
    url_json = json.dumps(url)
    is_hls_json = json.dumps(is_hls)
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
            <span class="avatar-pop-label">Speaking</span>
          </div>
          <video id="{safe_id}" class="avatar-pop-video" controls autoplay playsinline></video>
          <div class="avatar-pop-subtitle">{subtitle_html}</div>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
        <script>
          const video = document.getElementById({safe_id_json});
          const src = {url_json};
          const isHls = {is_hls_json};
          const playWhenReady = () => video.play().catch(() => {{}});
          if (!isHls) {{
            video.src = src;
            video.addEventListener("canplay", playWhenReady, {{ once: true }});
          }} else if (video.canPlayType("application/vnd.apple.mpegurl")) {{
            video.src = src;
            video.addEventListener("canplay", playWhenReady, {{ once: true }});
          }} else if (window.Hls && window.Hls.isSupported()) {{
            const hls = new Hls();
            hls.loadSource(src);
            hls.attachMedia(video);
            hls.on(Hls.Events.MANIFEST_PARSED, playWhenReady);
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


def capture_student_response(key_suffix: str, submit_label: str, *, allow_skip: bool = True) -> dict | None:
    """Offer typing or browser microphone recording, returning text plus audio evidence."""
    response_mode_key = f"response_mode_{key_suffix}"
    if st.session_state.get(response_mode_key) not in {"Type response", "Speak into microphone"}:
        st.session_state[response_mode_key] = "Type response"

    st.markdown('<div class="portal-field-label">Answer using</div>', unsafe_allow_html=True)
    mode_columns = st.columns(2, gap="small")
    with mode_columns[0]:
        if st.button("Write text", key=f"response_mode_text_{key_suffix}", width="stretch"):
            st.session_state[response_mode_key] = "Type response"
            st.rerun()
    with mode_columns[1]:
        if st.button("Speak into microphone", key=f"response_mode_voice_{key_suffix}", width="stretch"):
            st.session_state[response_mode_key] = "Speak into microphone"
            st.rerun()
    mode = st.session_state[response_mode_key]

    if mode == "Type response":
        with st.form(f"typed_response_{key_suffix}"):
            text = st.text_area(
                "Your response",
                height=140,
                placeholder="Type what you would say to the examiner.",
            )
            columns = st.columns(2) if allow_skip else st.columns(1)
            submitted = columns[0].form_submit_button(submit_label, type="primary", width="stretch")
            skipped = columns[1].form_submit_button("Skip question", width="stretch") if allow_skip else False
        if not submitted and not skipped:
            return None
        if submitted and not text.strip():
            st.warning("Please enter a response, record your answer, or choose Skip question.")
            return None
        return {"text": text.strip() if submitted else "[Skipped question]", "skipped": skipped, "mode": "text"}

    if not hasattr(st, "audio_input"):
        st.error("Microphone answers require a newer Streamlit version with browser audio input.")
        return None
    st.caption("Record in the browser, transcribe it, then review the captured text before sending it for grading.")
    recording = st.audio_input("Record your answer", key=f"voice_response_{key_suffix}")
    preview_key = f"voice_preview_{key_suffix}"
    recording_fingerprint = None
    if recording:
        st.audio(recording)
        recording_fingerprint = hashlib.sha256(recording.getvalue()).hexdigest()

    preview = st.session_state.get(preview_key)
    if preview and preview.get("fingerprint") != recording_fingerprint:
        # A fresh recording must be transcribed before it can replace the prior preview.
        discard_voice_preview(preview_key)
        preview = None

    if not preview:
        columns = st.columns(2) if allow_skip else st.columns(1)
        transcribe = columns[0].button(
            "Transcribe recording", type="primary", width="stretch", key=f"transcribe_voice_{key_suffix}"
        )
        skipped = columns[1].button("Skip question", width="stretch", key=f"skip_voice_{key_suffix}") if allow_skip else False
        if skipped:
            return {"text": "[Skipped question]", "skipped": True, "mode": "voice"}
        if not transcribe:
            return None
        if not recording:
            st.warning("Record an answer before transcribing it.")
            return None
        try:
            with st.spinner("Transcribing your recording..."):
                voice = transcribe_streamlit_audio(recording)
        except Exception as error:
            st.error(f"Your recording could not be transcribed: {error}")
            return None
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
    columns = st.columns(3) if allow_skip else st.columns(2)
    use_transcript = columns[0].button(submit_label, type="primary", width="stretch", key=f"use_voice_{key_suffix}")
    retry = columns[1].button("Record again", width="stretch", key=f"retry_voice_{key_suffix}")
    skipped = columns[2].button("Skip question", width="stretch", key=f"skip_review_voice_{key_suffix}") if allow_skip else False
    if retry:
        discard_voice_preview(preview_key)
        st.info("Record a replacement answer, then choose Transcribe recording again.")
        return None
    if skipped:
        discard_voice_preview(preview_key)
        return {"text": "[Skipped question]", "skipped": True, "mode": "voice"}
    if not use_transcript:
        return None
    st.session_state.pop(preview_key, None)
    return {"text": preview["text"], "skipped": False, **preview}


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
        p, li, label, [data-testid="stMarkdownContainer"] { color: var(--portal-ink); }
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
            font-size: 0.92rem;
            font-weight: 600;
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
            line-height: 1.45;
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
            font-size: 1.35rem;
            line-height: 1.25;
        }
        .assessment-room-title p {
            margin: 0;
            color: var(--portal-muted) !important;
        }
        .assessment-badge {
            flex: 0 0 auto;
            padding: 0.45rem 0.7rem;
            border-radius: 999px;
            background: #e8f6ed;
            color: #2f6c4b;
            font-weight: 750;
            font-size: 0.85rem;
            border: 1px solid #cbe4d3;
        }
        .assessment-panel-label {
            margin: 0.35rem 0 0.45rem;
            color: #315348;
            font-size: 0.78rem;
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
            font-size: 0.92rem;
            line-height: 1.45;
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
            font-size: 1.12rem;
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
    render_custom_rubric_upload()
    if not students:
        st.warning("No registered students are available. Add students to `data/users.json` first.")
        return

    draft = st.session_state.get("assignment_draft")
    if draft:
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
            assign = assign_column.form_submit_button(
                "Assign reviewed assessment", type="primary", width="stretch"
            )
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
        st.session_state["assignment_notice"] = (
            f"Assigned '{record['title']}' to {draft['student']['name']} with {len(record['questions'])} reviewed question(s)."
        )
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
    temporary_directory = Path(tempfile.mkdtemp(prefix="exam-upload-"))
    try:
        with st.spinner("Saving the materials and generating image questions..."):
            crew = init_crew(subject, rubric, student["id"])
            visual_file = save_uploaded_file(visual_upload, temporary_directory)
            visual_result = crew.run_ingestion_workflow(
                str(visual_file), material_type="visual", extract_questions=True
            )
            questions = visual_result.get("questions", [])[:3]
            if not questions:
                raise RuntimeError(
                    "No image questions were generated. Try a clearer image or check the AI service configuration."
                )

            visual_info = {
                "name": visual_upload.name,
                "path": visual_result.get("ingest_result", {}).get("file_path"),
                "image_count": visual_result.get("ingest_result", {}).get("image_count", 0),
            }
            reading_info = None
            if reading_upload:
                reading_file = save_uploaded_file(reading_upload, temporary_directory)
                reading_result = crew.run_ingestion_workflow(
                    str(reading_file), material_type="reading", extract_questions=False
                )
                stored_path = reading_result.get("ingest_result", {}).get("file_path")
                reading_info = {
                    "name": reading_upload.name,
                    "path": stored_path,
                    "text": extract_reading_passage(stored_path) if stored_path else "",
                }

            prepared_questions = [
                {**question, "generated_text": question.get("text", ""), "edited_by_examiner": False}
                for question in questions
            ]
            st.session_state.assignment_draft = {
                "draft_id": uuid.uuid4().hex,
                "student": student,
                "title": title,
                "subject": subject,
                "rubric": rubric,
                "visual": visual_info,
                "questions": prepared_questions,
                "reading": reading_info,
            }
    except Exception as error:
        # Ingestion creates subject folders before the JSON assignment is saved.
        # Remove those orphaned artifacts when the assignment cannot be completed.
        try:
            SubjectManager().delete_subject_data(subject)
        except Exception:
            pass
        st.error(f"The questions could not be prepared for review: {error}")
        return
    finally:
        shutil.rmtree(temporary_directory, ignore_errors=True)

    st.rerun()


def _assignment_label(assignment: dict) -> str:
    return f"{assignment.get('student_name', assignment.get('student_id'))} — {assignment.get('title')} ({assignment.get('status')})"


def render_examiner_review() -> None:
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

    assignment = st.selectbox(
        "Student assessment",
        assignments,
        format_func=_assignment_label,
        key="review_assignment",
    )
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
                st.write("**Transcript:**", reading_submission.get("transcript", ""))
                if reading_submission.get("audio_path"):
                    st.audio(reading_submission["audio_path"])
                render_delivery_indicators(reading_submission.get("delivery_indicators"))
                reading_grade = reading_submission.get("final_grading") or reading_submission.get("ai_grading")
                if reading_grade:
                    render_grading_result(reading_grade, heading="Provisional reading-aloud grade")
                st.caption("The grade uses the selected reading-delivery rubric criteria. Verify it against the recording before relying on it.")
                previous_note = (reading_submission.get("examiner_review") or {}).get("note", "")
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
                if (reading_submission.get("examiner_review") or {}).get("reviewed_at"):
                    st.caption(f"Last reviewed: {reading_submission['examiner_review']['reviewed_at']}")
        else:
            st.caption("Reading passage: awaiting the student's recorded submission.")
    if not results:
        st.info("The student has not submitted an image-question response yet.")
        return

    for number, result in enumerate(results, 1):
        final_grading = result.get("final_grading") or result.get("ai_grading") or {}
        ai_grading = result.get("ai_grading") or {}
        reviewed_at = (result.get("examiner_review") or {}).get("reviewed_at")
        title = f"Q{number}: {result.get('question', 'Question')[:80]}"
        with st.expander(title, expanded=(number == 1)):
            render_recorded_response(result)
            left, right = st.columns(2)
            with left:
                render_grading_result(ai_grading, heading="AI grade")
            with right:
                render_grading_result(final_grading, heading="Final grade")
            if result.get("crew_analysis"):
                with st.expander("AI coaching analysis"):
                    st.write(result["crew_analysis"])

            st.markdown("#### Verify or adjust")
            previous_note = (result.get("examiner_review") or {}).get("note", "")
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
            if reviewed_at:
                st.caption(f"Last reviewed: {reviewed_at}")

    reading_pending = bool(
        assignment.get("reading")
        and not (assignment.get("reading_submission") or {}).get("examiner_review")
    )
    unreviewed_questions = [result for result in results if not result.get("examiner_review")]
    st.markdown("#### Release final results")
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


def render_assignment_overview() -> None:
    assignments = list_assignments()
    st.subheader("Assignment overview")
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


def start_preparation_timer(assignment: dict) -> None:
    """Start the 10-minute timer only after the selected materials page opens."""
    assignment_id = assignment.get("assignment_id")
    if (
        st.session_state.preparation_timer_assignment_id != assignment_id
        or not st.session_state.preparation_deadline
    ):
        st.session_state.preparation_deadline = time.time() + 10 * 60
        st.session_state.preparation_timer_assignment_id = assignment_id


def render_preparation_loading(assignment: dict) -> None:
    st.subheader("Preparing your materials")
    st.markdown(
        f"""
        <div class="prep-loading-card">
          <div class="prep-loader"></div>
          <div>
            <h3>Opening your assessment pack</h3>
            <p>Loading the picture stimulus{ " and reading passage" if assignment.get("reading") else "" } before the timer begins.</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.spinner("Getting everything ready..."):
        time.sleep(1.1)
    st.session_state.preparation_deadline = None
    st.session_state.preparation_timer_assignment_id = None
    st.session_state.preparation_complete = False
    st.session_state.student_portal_stage = "preparation"
    st.rerun()


def render_assessment_loading(assignment: dict) -> None:
    st.subheader("Setting up your assessment")
    st.markdown(
        """
        <div class="prep-loading-card">
          <div class="prep-loader"></div>
          <div>
            <h3>Preparing the exam room</h3>
            <p>Locking the preparation materials and getting the examiner ready.</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.spinner("Starting your assessment session..."):
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
    if next_question:
        collect_avatar_preload_results()
        clean_text, avatar_cache_key = avatar_cache_key_for(
            next_question.get("text", ""),
            question_avatar_cache_key(assignment["assignment_id"], next_question),
        )
        cache = st.session_state.setdefault("simli_avatar_cache", {})
        futures: dict[str, Future] = st.session_state.setdefault("simli_avatar_futures", {})
        if clean_text and not cache.get(avatar_cache_key) and avatar_cache_key not in futures:
            queue_examiner_avatar_preload(
                next_question.get("text", ""),
                cache_key=question_avatar_cache_key(assignment["assignment_id"], next_question),
            )
    else:
        time.sleep(0.4)
    st.session_state.preparation_complete = True
    st.session_state.student_portal_stage = "assessment"
    st.rerun()


def question_avatar_cache_key(assignment_id: str, question: dict) -> str:
    question_id = str(question.get("id", ""))
    return f"{assignment_id}_{question_id}_question"


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
    """Prepare known question avatars while the student is viewing materials."""
    if not simli_avatar_requested():
        return
    try:
        from simli_avatar import load_config
    except Exception:
        return
    if not load_config():
        st.caption("Examiner video warm-up is enabled but avatar credentials are not fully configured.")
        return

    collect_avatar_preload_results()
    for entry in avatar_preload_entries(assignment):
        if entry["ready"] or entry["error"]:
            continue
        queue_examiner_avatar_preload(entry["text"], cache_key=entry["cache_key"])


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

    start_preparation_timer(assignment)
    render_examiner_avatar_warmup(assignment)
    st.divider()
    st.warning("Continuing starts the assessment phase. You will not be able to return to these preparation materials.")
    if st.button("Continue to assessment", type="primary", width="stretch"):
        st.session_state.student_portal_stage = "assessment_loading"
        st.rerun()


@st.fragment(run_every=1)
def render_preparation_timer() -> None:
    """Display and enforce the student preparation window."""
    deadline = st.session_state.preparation_deadline
    if not deadline or st.session_state.preparation_complete:
        return

    seconds_remaining = max(0, int(deadline - time.time()))
    if seconds_remaining == 0:
        st.session_state.preparation_complete = True
        st.warning("Preparation time has ended. The assessment phase is now open and materials are locked.")
        st.rerun(scope="app")

    minutes, seconds = divmod(seconds_remaining, 60)
    st.info(f"Preparation time remaining: **{minutes:02d}:{seconds:02d}**")
    st.progress(seconds_remaining / (10 * 60))


def render_reading_before_questions(assignment: dict, crew: EducationCrew) -> bool:
    """Collect the reading-aloud submission before image questions begin."""
    reading = assignment.get("reading")
    if not reading:
        return True

    st.markdown("### Reading Aloud")
    st.caption("Read this passage aloud, record it, review its transcript, then submit before moving on to the three image questions.")
    st.text_area(
        "Reading passage",
        value=reading.get("text", ""),
        height=250,
        disabled=True,
        key=f"assessment_reading_{assignment['assignment_id']}",
    )
    submission = assignment.get("reading_submission")
    if submission:
        st.success("Reading aloud submitted. Continue to the image questions below.")
        st.write("**Submitted transcript:**", submission.get("transcript", ""))
        if submission.get("audio_path"):
            st.audio(submission["audio_path"])
        render_delivery_indicators(submission.get("delivery_indicators"))
        st.caption("Your recording has been sent to the examiner for review. Your final grade will be released after verification.")
        return True

    captured = capture_student_response(
        f"reading_{assignment['assignment_id']}", "Submit reading aloud", allow_skip=False
    )
    if not captured:
        return False
    try:
        reading_criteria = crew.get_reading_criterion_names()
        if not reading_criteria:
            raise ValueError("The selected rubric does not contain a reading-aloud delivery criterion.")
        evidence = {
            "audio_evidence": "A student recording was submitted for examiner review.",
            "delivery_indicators": captured.get("delivery_indicators"),
            "limitation": "Transcript and automated pace/pitch indicators cannot verify pronunciation on their own.",
        }
        with st.spinner("AI is preparing a provisional reading-aloud grade..."):
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
            )
        save_reading_submission(
            assignment["assignment_id"],
            transcript=captured["text"],
            response_mode=captured.get("mode", "text"),
            audio_path=captured.get("audio_path"),
            transcription_path=captured.get("transcription_path"),
            delivery_indicators=captured.get("delivery_indicators"),
            grading_result=workflow["grading_result"],
            crew_analysis=workflow.get("crew_analysis", ""),
        )
        st.rerun()
    except Exception as error:
        st.error(f"The reading-aloud submission could not be saved: {error}")
    st.info("Submit the reading-aloud recording to unlock the image questions.")
    return False


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

    if not render_reading_before_questions(assignment, crew):
        return

    if _finish_if_complete(assignment, crew):
        st.success("Assessment submitted. Your examiner will verify the grades before releasing your final results.")
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
        render_examiner_avatar(
            examiner_prompt,
            cache_key=(
                question_avatar_cache_key(assignment["assignment_id"], question)
                if examiner_cache_kind == "question"
                else f"{assignment['assignment_id']}_{question_id}_guidance"
            ),
        )
        if guidance:
            st.markdown(
                '<div class="assessment-help-card">This is your one guiding question. Answer it clearly; your first response and this response will be assessed together.</div>',
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
            "examiner_transition", "Thank you, let's move on to the next question."
        )
    elif guidance:
        with st.container(border=True):
            st.markdown("### Step 3 - Record or type your final response")
            st.caption("Respond to the guiding question. The system will combine this with your first answer for grading.")
            captured = capture_student_response(
                f"follow_up_{assignment['assignment_id']}_{question_id}", "Submit final response"
            )
        if not captured:
            return
        skipped = captured["skipped"]
        follow_up_answer = captured["text"] if not skipped else "[No response after guidance]"
        answer_for_grading = combined_guided_response(guidance, follow_up_answer)
        grading_context = json.dumps({"examiner_guidance": guidance}, indent=2)
        examiner_transition = "Thank you, let's move on to the next question."
    else:
        with st.container(border=True):
            st.markdown("### Step 3 - Give your answer")
            st.caption("Choose one answer method. If you speak, transcribe first, check the text, then submit.")
            captured = capture_student_response(
                f"response_{assignment['assignment_id']}_{question_id}", "Submit response"
            )
        if not captured:
            return
        skipped = captured["skipped"]
        if not skipped:
            with st.spinner("Examiner is checking whether this answer can be graded..."):
                decision = crew.evaluate_oral_turn(
                    question=assessment_question_with_visual_context(question),
                    student_response=captured["text"],
                    attempt_number=1,
                    max_attempts=2,
                )
            if not decision.get("accepted"):
                try:
                    save_guidance_attempt(
                        assignment["assignment_id"],
                        question=question,
                        original_response=captured["text"],
                        follow_up_question=decision.get("examiner_reply") or (
                            "What is one detail you can see in the picture that helps answer the question?"
                        ),
                        reason=decision.get("reason", ""),
                        response_mode=captured.get("mode", "text"),
                        audio_path=captured.get("audio_path"),
                        transcription_path=captured.get("transcription_path"),
                        delivery_indicators=captured.get("delivery_indicators"),
                    )
                except Exception as error:
                    st.error(f"The guiding question could not be saved: {error}")
                    return
                st.session_state.pop(pending_key, None)
                st.session_state.pop(transition_key, None)
                st.rerun()
            examiner_transition = decision.get("examiner_reply") or "Thank you, let's move on to the next question."
            follow_up_answer = None
            answer_for_grading = captured["text"]
            grading_context = None
        else:
            examiner_transition = "Thank you. I have recorded that response."
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

    if not st.session_state.get(transition_key):
        render_examiner_transition(
            examiner_transition,
            cache_key=f"{assignment['assignment_id']}_{question_id}_transition",
        )
        if st.button("Continue", type="primary", width="stretch", key=f"continue_after_avatar_{assignment['assignment_id']}_{question_id}"):
            st.session_state[transition_key] = True
            st.rerun()
        st.caption("Continue after the examiner response has played.")
        return

    with st.spinner("AI is grading your response..."):
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
                response_mode=captured.get("mode", "text"),
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
        st.info("Preparation materials are locked. Continue with the assessment or view results.")
        assessment_tab, results_tab = st.tabs(["Take assessment", "Results"])
        with assessment_tab:
            render_student_assessment(assignment)
        with results_tab:
            render_student_results(assignment)
    else:
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
