"""
CrewAI Educational Assessment – fully integrated with the core agent stack.

Run:  streamlit run streamlit_app.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent / "src"))

from env_fix import apply_runtime_fixes
apply_runtime_fixes()

from agent_a6_session_manager import SessionManager
from crew_orchestrator import DEFAULT_PSLE_RUBRIC, DEFAULT_PSLE_SUBJECT, EducationCrew
from subject_manager import SubjectManager

load_dotenv()

st.set_page_config(
    page_title="CrewAI Oral Assessment",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Session state defaults
for key, default in [
    ("crew", None),
    ("crew_subject", None),
    ("crew_rubric", None),
    ("session_id", None),
    ("questions", []),
    ("question_index", 0),
    ("assessment_active", False),
    ("assessment_results", []),
    ("conversation_history", []),
    ("oral_guidance", {}),
    ("oral_turns", {}),
    ("oral_attempts", {}),
    ("oral_accepted_answers", {}),
    ("ingest_result", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


def list_rubrics() -> list[str]:
    rubric_dir = Path("data/rubrics")
    if not rubric_dir.exists():
        return []
    return sorted(f.stem for f in rubric_dir.glob("*.json"))


def init_crew(subject: str, rubric: str, student_id: str) -> EducationCrew:
    crew = EducationCrew(
        subject=subject,
        rubric_name=rubric,
        verbose=False,
        student_id=student_id,
    )
    if st.session_state.session_id:
        crew.session_id = st.session_state.session_id
        crew.session_manager.get_session(st.session_state.session_id)
    return crew


def reset_oral_state(clear_questions: bool = True) -> None:
    if clear_questions:
        st.session_state.questions = []
    st.session_state.question_index = 0
    st.session_state.assessment_active = False
    st.session_state.oral_guidance = {}
    st.session_state.oral_turns = {}
    st.session_state.oral_attempts = {}
    st.session_state.oral_accepted_answers = {}


def ensure_psle_crew(subject: str, rubric: str, student_id: str) -> EducationCrew:
    crew = st.session_state.get("crew")
    if (
        crew is None
        or st.session_state.get("crew_subject") != subject
        or st.session_state.get("crew_rubric") != rubric
    ):
        crew = init_crew(subject, rubric, student_id)
        st.session_state.crew = crew
        st.session_state.crew_subject = subject
        st.session_state.crew_rubric = rubric
        st.session_state.session_id = None
        reset_oral_state(clear_questions=True)
    return crew


def question_with_visual_context(question: dict) -> str:
    """Combine oral prompt text with the visual facts used for assessment."""
    visual_context = question.get("visual_context")
    if visual_context:
        return (
            "Assessment component: stimulus-based conversation. Do not assess "
            "reading-aloud delivery unless an actual reading-aloud passage or audio "
            "evidence is provided.\n\n"
            f"Visual stimulus description: {visual_context}\n\n"
            f"Oral prompt: {question.get('text', '')}"
        )
    return question.get("text", "")


def render_grading_result(grading: dict) -> None:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Score", f"{grading.get('total_score', 0)}/{grading.get('max_score', 0)}")
    with col2:
        st.metric("Percentage", f"{grading.get('percentage', 0)}%")
    with col3:
        pct = grading.get("percentage", 0)
        status = (
            "Excellent" if pct >= 80
            else "Good" if pct >= 70
            else "Fair" if pct >= 60
            else "Needs Improvement"
        )
        st.metric("Status", status)

    for criterion in grading.get("scores", []):
        st.write(
            f"**{criterion.get('criterion', 'Criterion')}**: "
            f"{criterion.get('score', 0)}/{criterion.get('max_score', 0)}"
        )
        if criterion.get("feedback"):
            st.caption(criterion["feedback"])
        if criterion.get("evidence"):
            st.caption(f"Evidence: {criterion['evidence']}")

    if grading.get("tutoring_feedback"):
        st.info(grading["tutoring_feedback"])


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
subject_manager = SubjectManager()
session_manager = SessionManager()
existing_subjects = subject_manager.list_subjects()
rubrics = list_rubrics()

with st.sidebar:
    st.title("⚙️ Configuration")

    subject_mode = st.radio("Subject", ["Existing", "New"], horizontal=True, index=1)
    if subject_mode == "Existing" and existing_subjects:
        subject = st.selectbox("Select subject", existing_subjects)
    else:
        subject = st.text_input(
            "Subject name",
            value=DEFAULT_PSLE_SUBJECT,
            placeholder="e.g. psle_oral_english",
        )

    rubric_options = rubrics if rubrics else [DEFAULT_PSLE_RUBRIC]
    rubric_index = rubric_options.index(DEFAULT_PSLE_RUBRIC) if DEFAULT_PSLE_RUBRIC in rubric_options else 0
    rubric = st.selectbox(
        "Rubric",
        rubric_options,
        index=rubric_index,
    )

    student_id = st.text_input("Student ID", value="student_001")

    if st.button("Initialize Crew", type="primary", use_container_width=True):
        st.session_state.crew = init_crew(subject, rubric, student_id)
        st.session_state.crew_subject = subject
        st.session_state.crew_rubric = rubric
        reset_oral_state(clear_questions=True)
        st.success("Crew ready")

    st.divider()
    st.markdown("### Session")
    if st.session_state.session_id:
        st.code(st.session_state.session_id)
    else:
        st.caption("No active session")

    if st.button("New Session", use_container_width=True):
        if st.session_state.crew:
            sid = st.session_state.crew.start_session()
            st.session_state.session_id = sid
            reset_oral_state(clear_questions=True)
            st.rerun()
        else:
            st.warning("Initialize crew first")

    st.divider()
    st.caption(
        f"Subjects: {len(existing_subjects)} · "
        f"Rubrics: {len(rubrics)} · "
        f"Crew: {'✅' if st.session_state.crew else '⏳'}"
    )

# ---------------------------------------------------------------------------
# Main tabs
# ---------------------------------------------------------------------------
st.markdown("# PSLE English Oral Practice")
st.caption("CrewAI assessor-coach | PSLE-style reading aloud and stimulus-based conversation")

tab_ingest, tab_oral, tab_manual, tab_dialogue, tab_results, tab_manage = st.tabs([
    "📁 Ingest Document",
    "🎤 Oral Assessment",
    "📝 Grade Response",
    "💬 Q&A Dialogue",
    "📊 Results",
    "Manage Data",
])

# ---- Ingest ----
with tab_ingest:
    st.markdown("## PSLE Oral Document Ingestion")
    st.markdown(
        "Upload a PSLE-style English oral document for reading-aloud passages, visual stimuli, "
        "and stimulus-based conversation prompts."
    )

    uploaded = st.file_uploader(
        "PDF, DOCX, TXT, or image",
        type=["pdf", "docx", "txt", "png", "jpg", "jpeg", "webp"],
    )

    st.caption(f"Uploads will be analysed under subject `{subject}` with rubric `{rubric}`.")

    if uploaded:
        if st.button("🚀 Ingest with Crew", type="primary"):
            with st.spinner("Running ingestion pipeline and CrewAI analysis..."):
                try:
                    crew = ensure_psle_crew(subject, rubric, student_id)
                    tmp = Path(tempfile.mkdtemp()) / uploaded.name
                    tmp.write_bytes(uploaded.getbuffer())

                    result = crew.run_ingestion_workflow(str(tmp))
                    st.session_state.ingest_result = result
                    st.session_state.questions = result.get("questions", [])[:3]
                    reset_oral_state(clear_questions=False)

                    st.success("Ingestion complete")
                    ir = result["ingest_result"]
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Chunks", ir.get("chunk_count", 0))
                    c2.metric("Images", ir.get("image_count", 0))
                    c3.metric("Questions", len(result.get("questions", [])))

                    with st.expander("Extracted questions", expanded=True):
                        for q in result.get("questions", []):
                            st.write(f"**Q{q['id']}:** {q['text']}")

                    with st.expander("CrewAI analysis"):
                        st.markdown(result.get("crew_analysis", ""))

                    existing_subjects  # refresh sidebar on next rerun
                except Exception as e:
                    st.error(f"Ingestion failed: {e}")
                    import traceback
                    st.code(traceback.format_exc())
    if st.session_state.ingest_result:
        st.divider()
        st.json(st.session_state.ingest_result.get("ingest_result", {}))

# ---- Oral assessment from document ----
with tab_oral:
    st.markdown("## PSLE Oral Assessment")
    st.markdown("Prompts are extracted from the ingested oral document, then assessed and coached interactively.")

    if not st.session_state.crew:
        st.warning("Initialize the crew first.")
    elif not st.session_state.questions:
        if st.button("Load questions from subject"):
            with st.spinner("Extracting questions..."):
                oral = st.session_state.crew.run_oral_assessment(num_questions=3)
                st.session_state.questions = oral.get("questions", [])
                st.session_state.oral_guidance = {}
                st.session_state.oral_turns = {}
                st.session_state.oral_attempts = {}
                st.session_state.oral_accepted_answers = {}
                st.rerun()
        else:
            st.info("Ingest a document first, or click **Load questions from subject**.")
    else:
        if not st.session_state.session_id:
            st.info("Tip: click **New Session** in the sidebar to persist results.")

        if st.button("🎯 Start Assessment", type="primary") and not st.session_state.assessment_active:
            if not st.session_state.session_id:
                sid = st.session_state.crew.start_session()
                st.session_state.session_id = sid
            st.session_state.questions = st.session_state.questions[:3]
            st.session_state.assessment_active = True
            st.session_state.question_index = 0
            st.session_state.oral_guidance = {}
            st.session_state.oral_turns = {}
            st.session_state.oral_attempts = {}
            st.session_state.oral_accepted_answers = {}
            st.rerun()

        if st.session_state.assessment_active:
            idx = st.session_state.question_index
            questions = st.session_state.questions

            if idx < len(questions):
                q = questions[idx]
                st.progress((idx + 1) / len(questions), text=f"Question {idx + 1} of {len(questions)}")
                st.subheader(f"Q{idx + 1}: {q['text']}")

                if q.get("image_path") and os.path.exists(q["image_path"]):
                    st.image(q["image_path"], width=500)
                if q.get("visual_context"):
                    with st.expander("Visual context used by examiner"):
                        st.write(q["visual_context"])

                qid = str(q.get("id", idx + 1))
                assessment_question = question_with_visual_context(q)
                turns = st.session_state.oral_turns.setdefault(
                    qid,
                    [{"role": "assistant", "content": q["text"]}],
                )
                attempt_count = st.session_state.oral_attempts.get(qid, 0)

                for turn in turns:
                    role = "assistant" if turn["role"] == "assistant" else "user"
                    st.chat_message(role).write(turn["content"])

                answer = st.text_area(
                    "Your response",
                    key=f"oral_answer_{idx}_{len(turns)}",
                    height=120,
                    placeholder="Speak or type your answer here. The examiner will decide whether to prompt you or move on.",
                )

                c1, c2, c3 = st.columns(3)
                with c1:
                    respond = st.button("Respond", type="primary", use_container_width=True)
                with c2:
                    skip = st.button("Skip", use_container_width=True)
                with c3:
                    end = st.button("End", use_container_width=True)

                if respond:
                    if not answer.strip():
                        st.warning("Please give an answer, even if it is just what you notice first.")
                    else:
                        attempt_number = attempt_count + 1
                        turns.append({"role": "user", "content": answer.strip()})
                        with st.spinner("Examiner is listening..."):
                            decision = st.session_state.crew.evaluate_oral_turn(
                                question=assessment_question,
                                student_response=answer.strip(),
                                conversation_history=turns,
                                attempt_number=attempt_number,
                                max_attempts=3,
                            )
                        turns.append({
                            "role": "assistant",
                            "content": decision["examiner_reply"],
                            "decision": decision,
                        })
                        st.session_state.oral_attempts[qid] = attempt_number

                        if decision.get("accepted"):
                            final_answer = " ".join(
                                turn["content"] for turn in turns if turn["role"] == "user"
                            )
                            st.session_state.oral_accepted_answers[qid] = final_answer
                            with st.spinner("Recording and grading the accepted answer..."):
                                result = st.session_state.crew.run_assessment_workflow(
                                    question=q["text"],
                                    student_response=final_answer,
                                    context=json.dumps(turns, indent=2),
                                    visual_context=q.get("visual_context"),
                                    save_to_session=bool(st.session_state.session_id),
                                )
                            result["interactive_turns"] = turns
                            result["examiner_decision"] = decision
                            st.session_state.assessment_results.append(result)
                            st.session_state.question_index += 1
                        st.rerun()

                if skip:
                    turns.append({
                        "role": "assistant",
                        "content": "Let's move to the next question.",
                        "decision": {"accepted": False, "status": "skipped"},
                    })
                    st.session_state.question_index += 1
                    st.rerun()

                if end:
                    st.session_state.assessment_active = False
                    if st.session_state.session_id:
                        st.session_state.crew.end_session()
                    st.rerun()
            else:
                st.success("All three questions completed!")
                st.session_state.assessment_active = False
                if st.session_state.session_id:
                    st.session_state.crew.end_session()

# ---- Manual single response grading ----
with tab_manual:
    st.markdown("## Grade a Single Response")
    col1, col2 = st.columns(2)
    with col1:
        question = st.text_area("Question", height=100, key="manual_q")
    with col2:
        response = st.text_area("Student response", height=100, key="manual_r")

    if st.button("📊 Evaluate", type="primary"):
        if not st.session_state.crew:
            st.error("Initialize crew first.")
        elif not question or not response:
            st.error("Enter question and response.")
        else:
            with st.spinner("A5 rubric grading + CrewAI analysis..."):
                try:
                    if not st.session_state.session_id:
                        sid = st.session_state.crew.start_session()
                        st.session_state.session_id = sid

                    result = st.session_state.crew.run_assessment_workflow(
                        question=question,
                        student_response=response,
                        save_to_session=True,
                    )
                    st.session_state.assessment_results.append(result)
                    st.success("Assessment complete")

                    st.markdown("### Rubric scores (Agent A5)")
                    render_grading_result(result["grading_result"])

                    with st.expander("CrewAI analysis"):
                        st.markdown(result.get("crew_analysis", ""))
                except Exception as e:
                    st.error(str(e))

# ---- Dialogue ----
with tab_dialogue:
    st.markdown("## Interactive Q&A Dialogue")
    main_q = st.text_input("Topic / main question", placeholder="What is photosynthesis?")

    for msg in st.session_state.conversation_history:
        role = "user" if msg["role"] == "user" else "assistant"
        st.chat_message(role).write(msg["content"])

    user_input = st.chat_input("Your message")
    if user_input and st.session_state.crew and main_q:
        st.session_state.conversation_history.append({"role": "user", "content": user_input})
        with st.spinner("Tutor thinking..."):
            reply = st.session_state.crew.run_interactive_dialogue(
                question=main_q,
                conversation_history=st.session_state.conversation_history,
            )
            st.session_state.conversation_history.append({"role": "assistant", "content": reply})
            st.rerun()

    if st.button("Clear conversation"):
        st.session_state.conversation_history = []
        st.rerun()

# ---- Results ----
with tab_results:
    st.markdown("## Assessment Results")

    # In-memory results from this Streamlit session
    if st.session_state.assessment_results:
        st.subheader(f"This session: {len(st.session_state.assessment_results)} assessment(s)")
        for i, result in enumerate(reversed(st.session_state.assessment_results), 1):
            with st.expander(f"Assessment {i} – {result.get('subject', '')}", expanded=(i == 1)):
                st.write("**Q:**", result["question"][:200])
                st.write("**A:**", result["student_response"][:200])
                render_grading_result(result["grading_result"])
                with st.expander("CrewAI analysis"):
                    st.markdown(result.get("crew_analysis", ""))

        st.download_button(
            "Download JSON",
            data=json.dumps(st.session_state.assessment_results, indent=2, default=str),
            file_name="crew_assessment_results.json",
            mime="application/json",
        )

    st.divider()

    # Persisted sessions from Agent A6
    st.subheader("Persisted sessions (Agent A6)")
    sessions = session_manager.list_sessions()
    if sessions:
        selected = st.selectbox("Session", sessions)
        if selected:
            report = session_manager.get_session_report(selected)
            if report:
                c1, c2, c3 = st.columns(3)
                c1.metric("Student", report["student_id"])
                c2.metric("Subject", report["paper_id"])
                c3.metric("State", report["state"])
                st.json(report)
    else:
        st.info("No persisted sessions yet.")

# ---- Manage data ----
with tab_manage:
    st.markdown("## Manage Stored Data")

    notice = st.session_state.get("manage_data_notice")
    if notice:
        st.success(notice)
        del st.session_state["manage_data_notice"]

    st.markdown("### Ingested Documents")
    st.caption("Deletes copied uploads, generated chunks, vector databases, extracted images, and subject metadata.")
    ingested_subjects = subject_manager.list_ingested_subjects()

    if ingested_subjects:
        selected_subjects = st.multiselect(
            "Subjects to delete",
            ingested_subjects,
            help="This removes the ingested document data for each selected subject. Sessions are not deleted here.",
        )
        confirm_docs = st.checkbox(
            "I understand this will delete the selected ingested documents and vector databases.",
            key="confirm_delete_ingested_docs",
        )

        if st.button(
            "Delete Selected Documents",
            type="primary",
            disabled=not selected_subjects or not confirm_docs,
            use_container_width=True,
        ):
            deleted = []
            failed = []
            for subject_name in selected_subjects:
                try:
                    subject_manager.delete_subject_data(subject_name)
                    deleted.append(subject_name)
                except Exception as e:
                    failed.append(f"{subject_name}: {e}")

            if any(s in selected_subjects for s in [st.session_state.get("crew_subject"), subject]):
                st.session_state.crew = None
                st.session_state.crew_subject = None
                st.session_state.crew_rubric = None
                st.session_state.session_id = None
                st.session_state.ingest_result = None
                reset_oral_state(clear_questions=True)

            if failed:
                st.error("Some subjects could not be deleted:")
                st.write(failed)
            if deleted:
                st.session_state.manage_data_notice = (
                    f"Deleted ingested data for {len(deleted)} subject(s): {', '.join(deleted)}"
                )
                st.rerun()

        if st.checkbox("Show stored subject details", key="show_subject_storage_details"):
            for subject_name in ingested_subjects:
                with st.expander(subject_name):
                    st.json(subject_manager.get_subject_info(subject_name))
    else:
        st.info("No ingested documents found.")

    st.divider()

    st.markdown("### Sessions")
    st.caption("Deletes persisted Agent A6 session files. Ingested documents are not deleted here.")
    persisted_sessions = session_manager.list_sessions()

    if persisted_sessions:
        selected_sessions = st.multiselect(
            "Sessions to delete",
            persisted_sessions,
            help="Select one or more persisted sessions to remove.",
        )
        confirm_sessions = st.checkbox(
            "I understand this will permanently delete the selected sessions.",
            key="confirm_delete_sessions",
        )

        if st.button(
            "Delete Selected Sessions",
            type="primary",
            disabled=not selected_sessions or not confirm_sessions,
            use_container_width=True,
        ):
            deleted = []
            failed = []
            for session_id in selected_sessions:
                try:
                    if session_manager.delete_session(session_id):
                        deleted.append(session_id)
                    else:
                        failed.append(f"{session_id}: not found")
                except Exception as e:
                    failed.append(f"{session_id}: {e}")

            if st.session_state.session_id in deleted:
                st.session_state.session_id = None
                if st.session_state.crew:
                    st.session_state.crew.session_id = None

            if failed:
                st.error("Some sessions could not be deleted:")
                st.write(failed)
            if deleted:
                st.session_state.manage_data_notice = (
                    f"Deleted {len(deleted)} session(s): {', '.join(deleted)}"
                )
                st.rerun()

        with st.expander("Delete all sessions"):
            confirm_all_sessions = st.checkbox(
                "I understand this will delete every persisted session.",
                key="confirm_delete_all_sessions",
            )
            if st.button(
                "Delete All Sessions",
                disabled=not confirm_all_sessions,
                use_container_width=True,
            ):
                result = session_manager.delete_all_sessions()
                if result["failed"]:
                    st.error("Some sessions could not be deleted:")
                    st.write(result["failed"])
                if result["deleted"]:
                    st.session_state.session_id = None
                    if st.session_state.crew:
                        st.session_state.crew.session_id = None
                    st.session_state.manage_data_notice = (
                        f"Deleted {len(result['deleted'])} persisted session(s)."
                    )
                    st.rerun()
    else:
        st.info("No persisted sessions found.")
