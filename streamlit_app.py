"""Local Streamlit portal for assigning and reviewing oral assessments.

Run with: ``streamlit run streamlit_app.py``
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent / "src"))

from env_fix import apply_runtime_fixes

apply_runtime_fixes()

from crew_orchestrator import DEFAULT_PSLE_RUBRIC, EducationCrew
from exam_portal_store import (
    add_assessment_result,
    apply_examiner_review,
    authenticate,
    create_assignment,
    get_active_assignment,
    list_assignments,
    list_english_oral_rubrics,
    list_students,
    mark_assignment_status,
    mark_reading_completed,
    rubric_display_name,
    save_guidance_attempt,
    save_english_oral_rubric,
)
from subject_manager import SubjectManager
from voice_assessment import transcribe_streamlit_audio

load_dotenv()

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
    st.session_state.authenticated = False
    st.session_state.user_role = None
    st.session_state.user_id = ""
    st.session_state.user_name = ""
    st.rerun()


def init_crew(subject: str, rubric: str, student_id: str) -> EducationCrew:
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
    st.write("**Examiner's guiding question:**", guided_attempt.get("follow_up_question", ""))
    st.write("**Response after guidance:**", guided_attempt.get("follow_up_response", ""))
    if guided_attempt.get("reason"):
        st.caption(f"Guidance reason: {guided_attempt['reason']}")
    if result.get("audio_path"):
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


def capture_student_response(key_suffix: str, submit_label: str) -> dict | None:
    """Offer typing or browser microphone recording, returning text plus audio evidence."""
    mode = st.radio(
        "Answer using",
        ["Type response", "Speak into microphone"],
        horizontal=True,
        key=f"response_mode_{key_suffix}",
    )
    if mode == "Type response":
        with st.form(f"typed_response_{key_suffix}"):
            text = st.text_area(
                "Your response",
                height=140,
                placeholder="Type what you would say to the examiner.",
            )
            submit_col, skip_col = st.columns(2)
            submitted = submit_col.form_submit_button(submit_label, type="primary", use_container_width=True)
            skipped = skip_col.form_submit_button("Skip question", use_container_width=True)
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
        transcribe_col, skip_col = st.columns(2)
        transcribe = transcribe_col.button(
            "Transcribe recording", type="primary", use_container_width=True, key=f"transcribe_voice_{key_suffix}"
        )
        skipped = skip_col.button("Skip question", use_container_width=True, key=f"skip_voice_{key_suffix}")
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
    use_col, retry_col, skip_col = st.columns(3)
    use_transcript = use_col.button(submit_label, type="primary", use_container_width=True, key=f"use_voice_{key_suffix}")
    retry = retry_col.button("Record again", use_container_width=True, key=f"retry_voice_{key_suffix}")
    skipped = skip_col.button("Skip question", use_container_width=True, key=f"skip_review_voice_{key_suffix}")
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


def render_login() -> None:
    st.title("Examination Portal")
    st.caption("A local prototype for assigning PSLE-style oral practice and reviewing AI grades.")
    role = st.radio("Login as", ["Student", "Examiner"], horizontal=True)
    with st.form("login_form"):
        user_id = st.text_input("Student ID" if role == "Student" else "Examiner ID")
        submitted = st.form_submit_button(f"Enter {role} portal", type="primary", use_container_width=True)
    if submitted:
        user = authenticate(role, user_id)
        if not user:
            st.error("That ID is not in the local user register.")
            return
        st.session_state.authenticated = True
        st.session_state.user_role = role.lower()
        st.session_state.user_id = user["id"]
        st.session_state.user_name = user["name"]
        st.rerun()

    with st.expander("Where do registered students come from?"):
        st.write("This prototype reads registered student and examiner IDs from `data/users.json`.")


def render_account_sidebar(role: str) -> None:
    with st.sidebar:
        st.title("Account")
        st.caption(f"{role}: {st.session_state.user_name} ({st.session_state.user_id})")
        if st.button("Logout", use_container_width=True):
            logout()


def _upload_label(upload, index: int) -> str:
    return f"{index + 1}. {Path(upload.name).name} ({upload.size / 1024:.0f} KB)"


def choose_uploaded_material(label: str, uploads, *, key: str, optional: bool = False):
    if not uploads:
        return None
    options = list(range(len(uploads)))
    if optional:
        options = [None, *options]
    selected = st.selectbox(
        label,
        options,
        key=key,
        format_func=lambda index: "No reading passage" if index is None else _upload_label(uploads[index], index),
    )
    return None if selected is None else uploads[selected]


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
    render_custom_rubric_upload()
    if not students:
        st.warning("No registered students are available. Add students to `data/users.json` first.")
        return

    st.markdown("#### Choose the materials for this assignment")
    visual_uploads = st.file_uploader(
        "Upload one or more picture stimuli",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        help="Only the picture you select below is sent to this student; the rest are not assigned.",
        key="visual_material_uploads",
    ) or []
    visual_upload = choose_uploaded_material(
        "Picture stimulus to assign", visual_uploads, key="selected_visual_material"
    )
    reading_uploads = st.file_uploader(
        "Upload one or more reading passages",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
        help="Choose one passage below, or leave it unselected. Reading is optional.",
        key="reading_material_uploads",
    ) or []
    reading_upload = choose_uploaded_material(
        "Reading passage to assign (optional)",
        reading_uploads,
        key="selected_reading_material",
        optional=True,
    )

    student_by_label = {f"{student['name']} ({student['id']})": student for student in students}
    with st.form("create_assignment"):
        selected_label = st.selectbox("Assign to registered student", list(student_by_label))
        title = st.text_input("Assessment title", value="PSLE English Oral Practice")
        rubric = st.selectbox("Grading rubric", rubrics, format_func=rubric_display_name)
        submitted = st.form_submit_button("Assign selected materials", type="primary", use_container_width=True)

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

            record = create_assignment(
                student=student,
                title=title,
                subject=subject,
                rubric=rubric,
                visual=visual_info,
                questions=questions,
                reading=reading_info,
                examiner_id=st.session_state.user_id,
            )
    except Exception as error:
        # Ingestion creates subject folders before the JSON assignment is saved.
        # Remove those orphaned artifacts when the assignment cannot be completed.
        try:
            SubjectManager().delete_subject_data(subject)
        except Exception:
            pass
        st.error(f"The assessment was not assigned: {error}")
        return
    finally:
        shutil.rmtree(temporary_directory, ignore_errors=True)

    st.success(f"Assigned '{record['title']}' to {student['name']}.")
    st.caption(f"Created {len(record['questions'])} image question(s).")
    with st.expander("Generated questions"):
        for number, question in enumerate(record["questions"], 1):
            st.write(f"**Q{number}.** {question.get('text', '')}")


def _assignment_label(assignment: dict) -> str:
    return f"{assignment.get('student_name', assignment.get('student_id'))} — {assignment.get('title')} ({assignment.get('status')})"


def render_examiner_review() -> None:
    assignments = list_assignments()
    st.subheader("Review AI results")
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
        reading_status = "completed" if assignment.get("reading_completed_at") else "not marked complete"
        st.caption(f"Reading passage: {reading_status} (reading delivery is not AI-scored).")
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
                saved = st.form_submit_button("Save verified grade", use_container_width=True)
            if saved:
                apply_examiner_review(
                    assignment["assignment_id"],
                    result["result_id"],
                    changes,
                    note,
                    st.session_state.user_id,
                )
                st.success("Verified grade saved. The original AI grade remains in the record.")
                st.rerun()
            if reviewed_at:
                st.caption(f"Last reviewed: {reviewed_at}")


def render_assignment_overview() -> None:
    assignments = list_assignments()
    st.subheader("Assignment overview")
    if not assignments:
        st.info("Create an assessment to see it here.")
        return
    for assignment in assignments:
        results = assignment.get("results", [])
        score = sum((result.get("final_grading") or {}).get("total_score", 0) for result in results)
        maximum = sum((result.get("final_grading") or {}).get("max_score", 0) for result in results)
        with st.expander(_assignment_label(assignment)):
            col1, col2, col3 = st.columns(3)
            col1.metric("Questions graded", f"{len(results)}/{len(assignment.get('questions', []))}")
            col2.metric("Current score", f"{score}/{maximum}")
            col3.metric("Reading", "done" if assignment.get("reading_completed_at") else "not required" if not assignment.get("reading") else "pending")
            st.caption(f"Assigned: {assignment.get('created_at') or 'legacy record'} | Rubric: {assignment.get('rubric', '')}")


def render_examiner_portal() -> None:
    render_account_sidebar("Examiner")
    st.title("Examiner Dashboard")
    st.caption("Upload one image, optionally add a reading passage, assign it to a registered student, then verify AI grading.")
    create_tab, review_tab, overview_tab = st.tabs(["Assign assessment", "Results and review", "Overview"])
    with create_tab:
        render_create_assignment()
    with review_tab:
        render_examiner_review()
    with overview_tab:
        render_assignment_overview()


def render_student_materials(assignment: dict) -> None:
    st.subheader("Your materials")
    st.write(f"**Assessment:** {assignment.get('title')}")
    image = visual_path(assignment)
    if image:
        st.image(image, caption="Picture stimulus", use_container_width=True)
    else:
        st.warning("The picture stimulus is unavailable. Ask your examiner to upload the assessment again.")

    reading = assignment.get("reading")
    if reading:
        st.markdown("#### Reading aloud (optional)")
        st.text_area(
            "Passage",
            value=reading.get("text", ""),
            height=220,
            disabled=True,
            key=f"reading_{assignment['assignment_id']}",
        )
        if assignment.get("reading_completed_at"):
            st.success("Reading passage marked complete.")
        elif st.button("Mark reading passage complete", use_container_width=True):
            mark_reading_completed(assignment["assignment_id"])
            st.rerun()
    else:
        st.caption("No reading-aloud passage was assigned for this assessment.")


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
    st.subheader("Image questions")
    questions = assignment.get("questions", [])
    if not questions:
        st.warning("This legacy assignment has no saved questions. Ask the examiner to upload a new assessment.")
        return

    crew = ensure_assignment_crew(assignment)
    if _finish_if_complete(assignment, crew):
        st.success("Assessment complete. Your results are ready in the Results tab.")
        return

    answered_ids = {result.get("question_id") for result in assignment.get("results", [])}
    question = next((item for item in questions if item.get("id") not in answered_ids), None)
    if not question:
        st.info("No further questions are available.")
        return

    if not st.session_state.session_id:
        if st.button("Begin assessment", type="primary", use_container_width=True):
            st.session_state.session_id = crew.start_session(
                metadata={"assignment_id": assignment["assignment_id"], "component": "student_assessment"}
            )
            mark_assignment_status(assignment["assignment_id"], "in_progress")
            st.rerun()
        st.caption("Your examiner will be able to review the AI score after each submitted answer.")
        return

    current_number = len(answered_ids) + 1
    st.progress(current_number / len(questions), text=f"Question {current_number} of {len(questions)}")
    st.write(f"### {question.get('text', '')}")
    image = visual_path(assignment)
    if image:
        st.image(image, width=550)
    question_id = str(question.get("id", ""))
    guidance = (assignment.get("guidance_attempts") or {}).get(question_id)

    if guidance:
        st.info("Your examiner has given one guiding question. Use it to improve your answer; there will not be another prompt for this item.")
        st.write(f"**Examiner:** {guidance.get('follow_up_question', '')}")
        captured = capture_student_response(
            f"follow_up_{assignment['assignment_id']}_{question_id}", "Submit final response"
        )
        if not captured:
            return
        skipped = captured["skipped"]
        follow_up_answer = captured["text"] if not skipped else "[No response after guidance]"
        answer_for_grading = combined_guided_response(guidance, follow_up_answer)
        grading_context = json.dumps({"examiner_guidance": guidance}, indent=2)
    else:
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
                    )
                except Exception as error:
                    st.error(f"The guiding question could not be saved: {error}")
                    return
                st.rerun()
            follow_up_answer = None
            answer_for_grading = captured["text"]
            grading_context = None
        else:
            follow_up_answer = None
            answer_for_grading = "[Skipped question]"
            grading_context = None

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
    st.rerun()


def render_student_results(assignment: dict) -> None:
    st.subheader("Your results")
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
    assignment = get_active_assignment(st.session_state.user_id)
    if not assignment:
        past_assignments = list_assignments(st.session_state.user_id)
        assignment = past_assignments[0] if past_assignments else None
    if not assignment:
        st.info("No assessment has been assigned to your student ID yet.")
        return

    if st.session_state.active_assignment_id != assignment["assignment_id"]:
        reset_runtime_state()
        st.session_state.active_assignment_id = assignment["assignment_id"]
    st.caption(f"Status: {assignment.get('status', 'assigned').replace('_', ' ').title()}")
    materials_tab, assessment_tab, results_tab = st.tabs(["Materials", "Take assessment", "Results"])
    with materials_tab:
        render_student_materials(assignment)
    with assessment_tab:
        render_student_assessment(assignment)
    with results_tab:
        render_student_results(assignment)


if not st.session_state.authenticated:
    render_login()
    st.stop()

if st.session_state.user_role == "examiner":
    render_examiner_portal()
else:
    render_student_portal()
