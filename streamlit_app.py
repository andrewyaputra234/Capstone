"""Local Streamlit portal for assigning and reviewing oral assessments.

Run with: ``streamlit run streamlit_app.py``
"""

from __future__ import annotations

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
    list_students,
    mark_assignment_status,
    mark_reading_completed,
)
from subject_manager import SubjectManager

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
    rubric_dir = Path("data/rubrics")
    return sorted(file.stem for file in rubric_dir.glob("*.json")) if rubric_dir.exists() else []


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


def render_create_assignment() -> None:
    students = list_students()
    rubrics = list_rubrics() or [DEFAULT_PSLE_RUBRIC]
    st.subheader("Create an assessment")
    st.caption("A picture stimulus is required. The reading-aloud passage is optional.")
    if not students:
        st.warning("No registered students are available. Add students to `data/users.json` first.")
        return

    student_by_label = {f"{student['name']} ({student['id']})": student for student in students}
    with st.form("create_assignment"):
        selected_label = st.selectbox("Assign to registered student", list(student_by_label))
        title = st.text_input("Assessment title", value="PSLE English Oral Practice")
        rubric = st.selectbox("Rubric", rubrics, index=0)
        visual_upload = st.file_uploader(
            "Picture stimulus (required)",
            type=["png", "jpg", "jpeg", "webp"],
            help="This image is used to generate up to three stimulus-based conversation questions.",
        )
        reading_upload = st.file_uploader(
            "Reading passage (optional)",
            type=["pdf", "docx", "txt"],
            help="Students can view this before the image questions. Reading delivery is not automatically scored.",
        )
        submitted = st.form_submit_button("Upload and assign", type="primary", use_container_width=True)

    if not submitted:
        return
    if not visual_upload:
        st.error("Upload a picture stimulus before assigning the assessment.")
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
            st.write("**Student response:**", result.get("student_response", ""))
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

    with st.form(f"response_{assignment['assignment_id']}_{question.get('id')}"):
        response = st.text_area(
            "Your response",
            height=140,
            placeholder="Type what you would say to the examiner.",
        )
        submit_col, skip_col = st.columns(2)
        submitted = submit_col.form_submit_button("Submit response", type="primary", use_container_width=True)
        skipped = skip_col.form_submit_button("Skip question", use_container_width=True)

    if not submitted and not skipped:
        return
    if submitted and not response.strip():
        st.warning("Please enter a response, or choose Skip question.")
        return

    answer = response.strip() if submitted else "[Skipped question]"
    with st.spinner("AI is grading your response..."):
        try:
            workflow = crew.run_assessment_workflow(
                question=question.get("text", ""),
                student_response=answer,
                visual_context=question.get("visual_context"),
                save_to_session=True,
                skipped=skipped,
            )
            add_assessment_result(
                assignment["assignment_id"],
                question=question,
                student_response=answer,
                grading_result=workflow["grading_result"],
                session_id=st.session_state.session_id,
                crew_analysis=workflow.get("crew_analysis", ""),
                skipped=skipped,
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
            st.write("**Your response:**", result.get("student_response", ""))
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
