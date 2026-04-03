"""
Streamlit Web UI for Oral Assessment System
Main entry point for teacher/student interface
"""

import streamlit as st
from streamlit_option_menu import option_menu
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from subject_manager import SubjectManager
from agent_a3_dialogue import DialogueManager
from agent_a6_session_manager import SessionManager
import json
import os

# Configure page
st.set_page_config(
    page_title="Oral Assessment System",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if "current_subject" not in st.session_state:
    st.session_state.current_subject = None
if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = None
if "assessment_active" not in st.session_state:
    st.session_state.assessment_active = False

# Custom CSS
st.markdown("""
<style>
    .main-header {
        text-align: center;
        color: #1f77b4;
        margin-bottom: 2rem;
    }
    .success-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d4edda;
        border-left: 4px solid #28a745;
    }
    .info-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d1ecf1;
        border-left: 4px solid #17a2b8;
    }
    .warning-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
    }
</style>
""", unsafe_allow_html=True)

# Main header
st.markdown("""
<h1 class="main-header">📚 Oral Assessment System</h1>
<p style="text-align: center; color: gray;">AI-Powered Assessment with Rubric-Based Feedback</p>
""", unsafe_allow_html=True)

# Initialize managers
subject_manager = SubjectManager()
session_manager = SessionManager()

# Sidebar navigation
with st.sidebar:
    st.title("🎯 Navigation")
    
    selected = option_menu(
        menu_title=None,
        options=["Dashboard", "Upload Document", "Assessment", "Results", "Settings"],
        icons=["house", "upload", "chat-dots", "bar-chart", "gear"],
        menu_icon="cast",
        default_index=0,
        styles={
            "container": {"padding": "0!important", "background-color": "#f0f2f6"},
            "icon": {"color": "orange", "font-size": "25px"},
            "nav-link": {"font-size": "16px", "text-align": "left", "margin":"0px"},
            "nav-link-selected": {"background-color": "#1f77b4"},
        }
    )

# ============================================================================
# PAGE: DASHBOARD
# ============================================================================
if selected == "Dashboard":
    st.header("📊 Dashboard")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        subjects = subject_manager.list_subjects()
        st.metric("Available Subjects", len(subjects))
    
    with col2:
        sessions = session_manager.list_sessions()
        st.metric("Total Sessions", len(sessions))
    
    with col3:
        rubric_path = Path("data/rubrics")
        rubrics = list(rubric_path.glob("*.json")) if rubric_path.exists() else []
        st.metric("Available Rubrics", len(rubrics))
    
    st.divider()
    
    st.subheader("📚 Available Subjects")
    if subjects:
        for subject in subjects:
            info = subject_manager.get_subject_info(subject)
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**{subject}**")
            with col2:
                st.write(f"Chunks: {info['chunk_count']}")
            with col3:
                rubric = info.get('rubric', 'None')
                st.write(f"Rubric: {rubric if rubric else '❌ Not mapped'}")
    else:
        st.info("No subjects found. Upload a document to get started!")
    
    st.divider()
    
    st.subheader("🎯 Quick Start")
    st.markdown("""
    1. **Upload Document** → Add your test/assignment (PDF, DOCX, TXT)
    2. **Map Rubric** → Select grading criteria
    3. **Start Assessment** → Ask students questions
    4. **View Results** → See scores and feedback
    """)

# ============================================================================
# PAGE: UPLOAD DOCUMENT
# ============================================================================
elif selected == "Upload Document":
    st.header("📤 Upload Document")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Step 1: Upload File")
        uploaded_file = st.file_uploader(
            "Choose a document (PDF, DOCX, or TXT)",
            type=["pdf", "docx", "txt"]
        )
        
        if uploaded_file:
            st.success(f"✓ File selected: {uploaded_file.name}")
    
    with col2:
        st.subheader("Step 2: Configure Subject")
        subject_name = st.text_input(
            "Enter subject name",
            placeholder="e.g., PSLE_Math, Grade5_English"
        )
        
        st.subheader("Step 3: Select Rubric")
        rubric_path = Path("data/rubrics")
        rubric_files = list(rubric_path.glob("*.json")) if rubric_path.exists() else []
        rubric_names = [f.stem for f in rubric_files]
        
        if rubric_names:
            rubric_name = st.selectbox("Choose rubric", rubric_names)
        else:
            st.warning("No rubrics found. Please create one first.")
            rubric_name = None
    
    # Process upload
    if st.button("📤 Upload & Process", type="primary", use_container_width=True):
        if not uploaded_file:
            st.error("Please select a file")
        elif not subject_name:
            st.error("Please enter a subject name")
        elif not rubric_name:
            st.error("Please select a rubric")
        else:
            # Save file
            input_dir = Path("data/input")
            input_dir.mkdir(parents=True, exist_ok=True)
            file_path = input_dir / uploaded_file.name
            
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            st.info(f"Processing {uploaded_file.name}...")
            
            # Run ingestion using the current Python interpreter (venv)
            import subprocess
            import sys
            result = subprocess.run(
                [
                    sys.executable, "src/main.py",
                    str(file_path),
                    "--subject", subject_name,
                    "--rubric", rubric_name
                ],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                st.markdown("""
                <div class="success-box">
                <h3>✅ Document Uploaded Successfully!</h3>
                <p><strong>Subject:</strong> {}</p>
                <p><strong>Rubric:</strong> {}</p>
                <p><strong>Status:</strong> Ready for assessment</p>
                </div>
                """.format(subject_name, rubric_name), unsafe_allow_html=True)
                
                st.session_state.current_subject = subject_name
            else:
                st.error(f"Error: {result.stderr}")

# ============================================================================
# PAGE: ASSESSMENT
# ============================================================================
elif selected == "Assessment":
    st.header("🎤 Student Assessment")
    
    # Select subject
    subjects = subject_manager.list_subjects()
    if not subjects:
        st.warning("No subjects available. Please upload a document first.")
    else:
        col1, col2 = st.columns(2)
        
        with col1:
            subject = st.selectbox("Select Subject", subjects)
        
        with col2:
            student_id = st.text_input("Student ID", value="student_001")
        
        st.divider()
        
        # Initialize DialogueManager for this subject
        from agent_a3_dialogue import DialogueManager
        dialogue_manager = DialogueManager(subject=subject)
        
        # Start assessment
        if st.button("🎯 Start Assessment", type="primary", use_container_width=True):
            st.session_state.assessment_active = True
            st.session_state.current_subject = subject
            st.session_state.questions = dialogue_manager.extract_questions_from_document(num_questions=5)
            st.session_state.current_question_index = 0
            st.session_state.answers = []
            
            # Create session
            session_id = session_manager.create_session(
                paper_id=subject,
                student_id=student_id,
                metadata={"started_from": "streamlit_ui"}
            )
            st.session_state.current_session_id = session_id
            
            st.success(f"✓ Assessment started | Session: {session_id}")
            st.success(f"✓ Loaded {len(st.session_state.questions)} questions!")
        
        # Assessment interface
        if st.session_state.assessment_active and st.session_state.current_session_id:
            questions = st.session_state.get("questions", [])
            question_idx = st.session_state.get("current_question_index", 0)
            
            if questions and question_idx < len(questions):
                current_q = questions[question_idx]
                
                # Display progress
                st.progress(
                    (question_idx + 1) / len(questions),
                    text=f"Question {question_idx + 1} of {len(questions)}"
                )
                
                st.divider()
                
                # Display question
                st.subheader(f"Q{question_idx + 1}: {current_q.get('text', 'Question')}")
                
                # Get answer from user
                answer = st.text_area(
                    "Your Answer:",
                    height=100,
                    key=f"answer_{question_idx}"
                )
                
                # Buttons
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    if st.button("✓ Submit Answer", use_container_width=True):
                        if answer.strip():
                            # Log turn to session
                            session_manager.add_turn(
                                st.session_state.current_session_id,
                                speaker="student",
                                text=answer
                            )
                            
                            # Score the answer
                            rubric_name = subject_manager.get_default_rubric(subject)
                            from agent_a5_grader import RubricGrader
                            grader = RubricGrader(rubric_name)
                            scores = grader.grade_answer(
                                question=current_q.get('text', ''),
                                answer=answer
                            )
                            
                            # Save scores to session
                            session_manager.add_scores(
                                st.session_state.current_session_id,
                                {f"Q{question_idx + 1}": scores}
                            )
                            
                            # Move to next question
                            st.session_state.current_question_index += 1
                            st.success("✓ Answer recorded! Moving to next question...")
                            st.rerun()
                        else:
                            st.warning("Please enter an answer")
                
                with col2:
                    if st.button("⏭️ Skip Question", use_container_width=True):
                        st.session_state.current_question_index += 1
                        st.rerun()
                
                with col3:
                    if st.button("🏁 End Assessment", use_container_width=True):
                        session_manager.end_session(st.session_state.current_session_id)
                        st.session_state.assessment_active = False
                        st.success("✓ Assessment completed!")
                        st.info("Go to Results tab to view your scores")
                        st.rerun()
            
            else:
                # All questions completed
                st.success("🎉 All questions completed!")
                if st.button("View Results", type="primary", use_container_width=True):
                    session_manager.end_session(st.session_state.current_session_id)
                    st.session_state.assessment_active = False
                    st.rerun()

# ============================================================================
# PAGE: RESULTS
# ============================================================================
elif selected == "Results":
    st.header("📊 Assessment Results")
    
    sessions = session_manager.list_sessions()
    
    if not sessions:
        st.info("No sessions found yet.")
    else:
        session_id = st.selectbox(
            "Select Session",
            sessions,
            format_func=lambda x: f"{x} - View results"
        )
        
        if session_id:
            try:
                session_data = session_manager.get_session_report(session_id)
                
                # ===== SESSION METADATA =====
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Student ID", session_data["student_id"])
                with col2:
                    st.metric("Subject", session_data["paper_id"])
                with col3:
                    st.metric("Questions", session_data["statistics"]["student_turns"])
                with col4:
                    st.metric("Status", session_data["state"])
                
                st.divider()
                
                # ===== SCORES & GRADES =====
                scores = session_data.get("scores", {})
                
                if scores:
                    st.subheader("📈 Scores & Grades")
                    
                    # Display overall score if available
                    if isinstance(scores, dict):
                        cols = st.columns(len(scores))
                        for idx, (criterion, score) in enumerate(scores.items()):
                            with cols[idx]:
                                if isinstance(score, dict):
                                    # Score with details
                                    score_value = score.get("score", 0)
                                    max_score = score.get("max_score", 10)
                                    percentage = (score_value / max_score * 100) if max_score > 0 else 0
                                    st.metric(
                                        criterion.replace("_", " ").title(),
                                        f"{score_value}/{max_score}",
                                        f"{percentage:.0f}%"
                                    )
                                else:
                                    # Simple score value
                                    st.metric(criterion.replace("_", " ").title(), score)
                    
                    # Detailed score breakdown
                    with st.expander("📋 Detailed Score Breakdown"):
                        st.json(scores)
                else:
                    st.info("No scores recorded yet for this session.")
                
                st.divider()
                
                # ===== QUESTIONS & ANSWERS =====
                st.subheader("💬 Questions & Answers")
                
                turns = session_data.get("turns", [])
                question_num = 0
                
                for i, turn in enumerate(turns):
                    speaker = turn.get('speaker', '').lower()
                    text = turn.get('text', '').strip()
                    timestamp = turn.get('timestamp', '')
                    
                    if speaker == 'avatar' and text:
                        question_num += 1
                        with st.expander(f"**Q{question_num}:** {text[:60]}..." if len(text) > 60 else f"**Q{question_num}:** {text}"):
                            st.write(f"**Time:** {timestamp}")
                    
                    elif speaker == 'student' and text:
                        with st.expander(f"   └─ **Answer:** {text[:60]}..." if len(text) > 60 else f"   └─ **Answer:** {text}"):
                            st.write(f"**Time:** {timestamp}")
                
                st.divider()
                
                # ===== EXPORT OPTIONS =====
                st.subheader("💾 Export Results")
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    if st.button("📄 Export as CSV", use_container_width=True):
                        output_file = session_manager.export_transcript(session_id, format="csv")
                        if output_file:
                            st.success(f"✓ Exported: {output_file}")
                        else:
                            st.error("Export failed")
                
                with col2:
                    if st.button("📋 Export as JSON", use_container_width=True):
                        output_file = session_manager.export_transcript(session_id, format="json")
                        if output_file:
                            st.success(f"✓ Exported: {output_file}")
                        else:
                            st.error("Export failed")
                
                with col3:
                    if st.button("📝 Export as Text", use_container_width=True):
                        output_file = session_manager.export_transcript(session_id, format="text")
                        if output_file:
                            st.success(f"✓ Exported: {output_file}")
                        else:
                            st.error("Export failed")
                
            except Exception as e:
                st.error(f"Error loading session: {e}")
                st.write("**Debug Info:**")
                st.write(f"Session ID: {session_id}")
                import traceback
                st.code(traceback.format_exc())

# ============================================================================
# PAGE: SETTINGS
# ============================================================================
elif selected == "Settings":
    st.header("⚙️ Settings")
    
    tab1, tab2, tab3 = st.tabs(["Rubrics", "Subjects", "System"])
    
    with tab1:
        st.subheader("Manage Rubrics")
        st.info("Rubrics are stored in: data/rubrics/")
        
        rubric_path = Path("data/rubrics")
        rubric_files = list(rubric_path.glob("*.json")) if rubric_path.exists() else []
        
        if rubric_files:
            for rubric_file in rubric_files:
                with st.expander(f"📋 {rubric_file.stem}"):
                    with open(rubric_file) as f:
                        rubric_data = json.load(f)
                    st.json(rubric_data)
        else:
            st.warning("No rubrics found")
    
    with tab2:
        st.subheader("Subject Configuration")
        
        subjects = subject_manager.list_subjects()
        if subjects:
            for subject in subjects:
                with st.expander(f"📚 {subject}"):
                    info = subject_manager.get_subject_info(subject)
                    st.write(f"**Chunks:** {info['chunk_count']}")
                    st.write(f"**Database:** {info['db_path']}")
                    
                    current_rubric = info.get('rubric', 'Not set')
                    rubric_path = Path("data/rubrics")
                    rubric_names = [f.stem for f in rubric_path.glob("*.json")]
                    
                    new_rubric = st.selectbox(
                        f"Set rubric for {subject}",
                        rubric_names,
                        index=rubric_names.index(current_rubric) if current_rubric in rubric_names else 0,
                        key=f"rubric_{subject}"
                    )
                    
                    if st.button(f"Update {subject}", key=f"update_{subject}"):
                        subject_manager.set_subject_rubric(subject, new_rubric)
                        st.success(f"Updated!")
        else:
            st.info("No subjects configured yet")
    
    with tab3:
        st.subheader("System Information")
        st.write(f"**Data Directory:** {Path('data').absolute()}")
        st.write(f"**Subjects:** {len(subjects)} available")
        st.write(f"**Sessions:** {len(session_manager.list_sessions())} recorded")
        
        if st.button("🔄 Refresh Cache"):
            st.cache_data.clear()
            st.success("Cache cleared!")

# Footer
st.divider()
st.markdown("""
<p style="text-align: center; color: gray; font-size: 0.9rem;">
Oral Assessment System v1.0 | Built with Streamlit + LangChain
</p>
""", unsafe_allow_html=True)
