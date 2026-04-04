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
from rubric_generator import get_or_create_rubric, list_available_rubrics
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
if "selected_rubric" not in st.session_state:
    st.session_state.selected_rubric = None
if "rubric_mode" not in st.session_state:
    st.session_state.rubric_mode = "generated"

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
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader("Step 1: Upload Document")
        uploaded_file = st.file_uploader(
            "Choose a document (PDF, DOCX, or TXT)",
            type=["pdf", "docx", "txt"]
        )
        
        if uploaded_file:
            st.success(f"✓ File selected: {uploaded_file.name}")
    
    with col2:
        st.subheader("Step 2: Subject Name")
        
        subject_name = st.text_input(
            "Subject name",
            placeholder="e.g., Math, English, Biology"
        )
    
    with col3:
        st.subheader("Step 3: Rubric Setup")
        
        rubric_choice = st.radio(
            "How would you like to set up the rubric?",
            options=["Auto-Generate", "Upload Custom"],
            help="Choose between auto-generating a rubric or providing your own template"
        )
        
        rubric_name = None
        
        if rubric_choice == "Auto-Generate":
            st.markdown("**Auto-Generate by Education Level**")
            
            education_level = st.selectbox(
                "Select education level",
                options=["Primary", "Secondary", "High School", "University"],
                key="edu_level_select"
            )
            
            # Extract subject type for rubric generation
            subject_type = "math"
            if subject_name:
                subject_lower = subject_name.lower()
                if any(word in subject_lower for word in ["eng", "english", "literature"]):
                    subject_type = "english"
                elif any(word in subject_lower for word in ["sci", "science", "bio", "chem", "physics"]):
                    subject_type = "science"
                elif any(word in subject_lower for word in ["math", "maths", "calc"]):
                    subject_type = "math"
            
            if st.button("🔄 Generate Rubric", type="secondary", use_container_width=True):
                if not subject_name:
                    st.error("Please enter a subject name first")
                else:
                    with st.spinner(f"Generating {education_level} {subject_name} rubric..."):
                        try:
                            rubric_name, rubric_path = get_or_create_rubric(
                                subject=subject_type,
                                education_level=education_level
                            )
                            st.success(f"✅ Rubric ready: {rubric_name}")
                            st.session_state.selected_rubric = rubric_name
                            st.session_state.rubric_mode = "generated"
                        except Exception as e:
                            st.error(f"Error generating rubric: {e}")
            
            # Show available rubrics
            rubric_path = Path("data/rubrics")
            rubric_files = list(rubric_path.glob("*.json")) if rubric_path.exists() else []
            rubric_names = [f.stem for f in rubric_files]
            
            if rubric_names:
                default_idx = 0
                if "selected_rubric" in st.session_state and st.session_state.selected_rubric in rubric_names:
                    default_idx = rubric_names.index(st.session_state.selected_rubric)
                
                rubric_name = st.selectbox(
                    "Select rubric to use",
                    options=rubric_names,
                    index=default_idx,
                    key="generated_rubric_select"
                )
            else:
                st.warning("⚠️ No rubrics available yet. Generate one first.")
        
        else:  # Upload Custom
            st.markdown("**Upload Custom Rubric Template**")
            st.info("📋 Upload a JSON rubric template to use with this document")
            
            custom_rubric_file = st.file_uploader(
                "Choose a JSON rubric template",
                type=["json"],
                key="custom_rubric_upload"
            )
            
            if custom_rubric_file:
                try:
                    # Validate JSON format
                    import json
                    rubric_data = json.load(custom_rubric_file)
                    
                    # Basic validation
                    if "criteria" not in rubric_data:
                        st.error("❌ Invalid rubric format. Must have 'criteria' field.")
                    else:
                        # Save the custom rubric to data/rubrics/
                        rubric_name = custom_rubric_file.name.replace(".json", "")
                        rubric_save_path = Path("data/rubrics") / f"{rubric_name}.json"
                        
                        with open(rubric_save_path, "w") as f:
                            json.dump(rubric_data, f, indent=2)
                        
                        st.success(f"✅ Rubric loaded: {rubric_name}")
                        st.session_state.selected_rubric = rubric_name
                        st.session_state.rubric_mode = "custom"
                        
                except json.JSONDecodeError:
                    st.error("❌ Invalid JSON file. Please check the format.")
                except Exception as e:
                    st.error(f"❌ Error processing rubric: {e}")
    
    st.divider()
    
    # Process upload
    col1, col2 = st.columns([3, 1])
    
    with col1:
        process_btn = st.button("📤 Upload & Process", type="primary", use_container_width=True)
    
    if process_btn:
        if not uploaded_file:
            st.error("❌ Please select a document")
        elif not subject_name:
            st.error("❌ Please enter a subject name")
        elif not st.session_state.get("selected_rubric"):
            st.error("❌ Please generate or upload a rubric first")
        else:
            rubric_name = st.session_state.selected_rubric
            
            # Save file to SUBJECT-SPECIFIC directory
            input_dir = subject_manager.get_subject_input_path(subject_name)
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
                text=True,
                timeout=120  # 2 minute timeout
            )
            
            if result.returncode == 0:
                mode = st.session_state.get("rubric_mode", "generated")
                mode_label = "Auto-Generated" if mode == "generated" else "Custom"
                
                st.markdown("""
                <div class="success-box">
                <h3>✅ Document Uploaded Successfully!</h3>
                <p><strong>Subject:</strong> {}</p>
                <p><strong>Rubric:</strong> {} ({})</p>
                <p><strong>Status:</strong> Ready for assessment</p>
                <p><strong style="color: #856404;">📌 Next Step:</strong> Go to <strong>Assessment</strong> tab and select this subject to start</p>
                </div>
                """.format(subject_name, rubric_name, mode_label), unsafe_allow_html=True)
                
                st.session_state.current_subject = subject_name
                st.balloons()
            else:
                st.error(f"❌ Processing Error:\n{result.stderr}")
                st.info("Please try again or check that the PDF/DOCX format is valid")

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
        
        # If user selected a different subject, reset assessment state
        if st.session_state.assessment_active and st.session_state.get("current_subject") != subject:
            st.session_state.assessment_active = False
            st.session_state.questions = []
            st.session_state.current_question_index = 0
            st.info("Subject changed. Previous assessment cleared.")
        
        # Initialize DialogueManager for this subject (store in session to preserve images across reruns)
        if "dialogue_manager" not in st.session_state or st.session_state.get("dialogue_manager_subject") != subject:
            from agent_a3_dialogue import DialogueManager
            st.session_state.dialogue_manager = DialogueManager(subject=subject, extract_images=True)
            st.session_state.dialogue_manager_subject = subject
        
        dialogue_manager = st.session_state.dialogue_manager
        
        # Refresh button to reload DialogueManager with fresh images
        col_refresh = st.columns([1, 9])
        with col_refresh[0]:
            if st.button("Refresh", help="Reload questions and images from latest document", use_container_width=True):
                # Force recreate DialogueManager with fresh image extraction
                st.session_state.dialogue_manager = None
                st.session_state.dialogue_manager_subject = None
                from agent_a3_dialogue import DialogueManager
                st.session_state.dialogue_manager = DialogueManager(subject=subject, extract_images=True)
                st.session_state.dialogue_manager_subject = subject
                st.rerun()
        
        # Start assessment
        if st.button("🎯 Start Assessment", type="primary", use_container_width=True):
            # CRITICAL: Create a FRESH DialogueManager to load latest document and images
            from agent_a3_dialogue import DialogueManager
            fresh_dialogue_manager = DialogueManager(subject=subject, extract_images=True)
            
            st.session_state.assessment_active = True
            st.session_state.current_subject = subject
            # Use the fresh DialogueManager to extract questions
            st.session_state.questions = fresh_dialogue_manager.extract_questions_from_document(num_questions=5)
            st.session_state.current_question_index = 0
            st.session_state.answers = []
            # Store the fresh DialogueManager for use during assessment
            st.session_state.assessment_dialogue_manager = fresh_dialogue_manager
            
            # Create session
            session_id = session_manager.create_session(
                paper_id=subject,
                student_id=student_id,
                metadata={"started_from": "streamlit_ui"}
            )
            st.session_state.current_session_id = session_id
            
            st.success(f"✓ Assessment started | Session: {session_id}")
            st.success(f"✓ Loaded {len(st.session_state.questions)} questions!")
            st.rerun()  # Rerun to display the questions immediately
        
        # Assessment interface
        if st.session_state.assessment_active and st.session_state.current_session_id:
            questions = st.session_state.get("questions", [])
            question_idx = st.session_state.get("current_question_index", 0)
            session_id = st.session_state.current_session_id
            
            # Use the fresh DialogueManager from assessment start
            dialogue_manager = st.session_state.get("assessment_dialogue_manager")
            
            # Reload session to ensure current_session is set
            session_data = session_manager.get_session(session_id)
            if session_data:
                session_manager.current_session = session_data
            
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
                
                # Display image if available
                image_path = current_q.get('image_path')
                
                # Try different sources for the image
                if image_path and os.path.exists(image_path):
                    try:
                        st.image(image_path, caption=f"Question reference", use_container_width=True)
                    except Exception as e:
                        st.warning(f"Could not display image: {e}")
                else:
                    # If question doesn't have an image_path, try to get one from DialogueManager
                    if dialogue_manager and hasattr(dialogue_manager, 'page_images') and dialogue_manager.page_images:
                        # Try to get page image - prefer page 1 as default
                        fallback_img = dialogue_manager.page_images.get(1) or next(iter(dialogue_manager.page_images.values()), None)
                        if fallback_img and os.path.exists(fallback_img):
                            st.image(fallback_img, caption="Question reference (paper overview)", use_container_width=True)
                
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
                            # Log turn to session (no session_id parameter)
                            session_manager.add_turn(
                                speaker="student",
                                text=answer
                            )
                            
                            # Score the answer
                            rubric_name = subject_manager.get_default_rubric(subject)
                            from agent_a5_grader import RubricGrader
                            grader = RubricGrader(rubric_name)
                            grading_result = grader.generate_tutoring_feedback(
                                assignment=current_q.get('text', ''),
                                answer=answer
                            )
                            
                            # Extract scores from result
                            scores = grading_result.get('scores', [])
                            
                            # Save scores to session (no session_id parameter)
                            session_manager.add_scores([{f"Q{question_idx + 1}": grading_result}])
                            
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
