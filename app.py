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
from rubric_generator import get_or_create_rubric, list_available_rubrics, generate_rubric_from_document
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
        
        education_level = st.selectbox(
            "Select education level",
            options=["Primary", "Secondary", "High School", "University"],
            key="edu_level_select"
        )
        
        rubric_choice = st.radio(
            "Rubric generation method:",
            options=["AI Auto-Detect Topic", "Manual Selection", "Upload Custom"],
            help="AI Auto-Detect reads your paper and creates a focused rubric; Manual lets you choose a pre-built rubric"
        )
        
        rubric_name = None
        detected_topic = None
        
        if rubric_choice == "AI Auto-Detect Topic":
            st.markdown("**AI will analyze your document and create a topic-specific rubric**")
            
            if st.button("🤖 Analyze Document & Generate Rubric", type="primary", use_container_width=True):
                if not uploaded_file:
                    st.error("Please upload a document first")
                elif not subject_name:
                    st.error("Please enter a subject name first")
                else:
                    with st.spinner("Analyzing document and generating topic-specific rubric..."):
                        try:
                            import tempfile
                            import shutil
                            
                            # Extract document content using DocumentIngestionAgent
                            from agent_a1_ingestion import DocumentIngestionAgent
                            ingestion_agent = DocumentIngestionAgent()
                            
                            # Save uploaded file to Windows temp directory
                            temp_dir = tempfile.mkdtemp()
                            temp_path = Path(temp_dir) / uploaded_file.name
                            
                            with open(temp_path, "wb") as f:
                                f.write(uploaded_file.getbuffer())
                            
                            st.info(f"📄 Analyzing: {uploaded_file.name}")
                            
                            # Extract content from the actual uploaded file
                            doc_content = ingestion_agent.extract_text(str(temp_path))
                            
                            if not doc_content or len(doc_content.strip()) < 100:
                                st.warning("⚠️ Document appears to be empty or unreadable. Please try another file.")
                            else:
                                # Determine subject type
                                subject_lower = subject_name.lower()
                                if any(word in subject_lower for word in ["eng", "english", "literature"]):
                                    subject_type = "english"
                                elif any(word in subject_lower for word in ["sci", "science", "bio", "chem", "physics"]):
                                    subject_type = "science"
                                else:
                                    subject_type = "math"
                                
                                # AI detect topic and generate rubric
                                st.info("🤖 Detecting topic and generating criteria...")
                                detected_topic, rubric_dict = generate_rubric_from_document(
                                    document_content=doc_content,
                                    subject_type=subject_type,
                                    education_level=education_level
                                )
                                
                                # Save generated rubric
                                rubric_dir = Path("data/rubrics")
                                rubric_dir.mkdir(parents=True, exist_ok=True)
                                
                                rubric_filename = f"{education_level.lower()}_{detected_topic.replace(' ', '_').lower()}.json"
                                rubric_path = rubric_dir / rubric_filename
                                
                                with open(rubric_path, "w") as f:
                                    json.dump(rubric_dict, f, indent=2)
                                
                                st.session_state.selected_rubric = rubric_filename.replace('.json', '')
                                st.session_state.detected_topic = detected_topic
                                st.session_state.topic_rubric = rubric_dict
                                st.success(f"✅ Topic detected: **{detected_topic}**")
                                st.info(f"Generated {education_level} rubric with {len(rubric_dict.get('criteria', []))} custom criteria for this topic.")
                                
                                # Show rubric criteria preview
                                with st.expander("📋 View Generated Rubric Criteria"):
                                    for criterion in rubric_dict.get('criteria', []):
                                        st.write(f"**{criterion['name']}** (Max {criterion['max_points']} points)")
                                        st.write(f"*{criterion['description']}*")
                            
                            # Clean up temp directory
                            try:
                                shutil.rmtree(temp_dir)
                            except:
                                pass
                        except Exception as e:
                            st.error(f"Error during analysis: {str(e)}")
                            import traceback
                            print(traceback.format_exc())
        
        elif rubric_choice == "Manual Selection":
            st.markdown("**Select from Pre-built Rubric Templates**")
            
            if st.button("📚 Load Pre-built Rubric", type="secondary", use_container_width=True):
                if not subject_name:
                    st.error("Please enter a subject name first")
                else:
                    with st.spinner(f"Generating {education_level} {subject_name} rubric..."):
                        try:
                            # Extract subject type
                            subject_lower = subject_name.lower()
                            if any(word in subject_lower for word in ["eng", "english", "literature"]):
                                subject_type = "english"
                            elif any(word in subject_lower for word in ["sci", "science", "bio", "chem", "physics"]):
                                subject_type = "science"
                            else:
                                subject_type = "math"
                            
                            rubric_name, rubric_path = get_or_create_rubric(
                                subject=subject_type,
                                education_level=education_level
                            )
                            st.success(f"✅ Loaded: {rubric_name}")
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
                    "Or select from available rubrics",
                    options=rubric_names,
                    index=default_idx,
                    key="generated_rubric_select"
                )
            else:
                st.warning("⚠️ No pre-built rubrics available yet. Use AI Auto-Detect or generate one first.")
        
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
                print(f"[DEBUG] Loaded session {session_id}, current_session={'SET' if session_manager.current_session else 'NOT SET'}")
            else:
                print(f"[ERROR] Failed to load session {session_id}")
                st.error(f"Could not load session: {session_id}")
            
            if questions and question_idx < len(questions):
                current_q = questions[question_idx]
                
                # Add question to session transcript if not already added
                # (Use simple check: if this is our first time on this question, add it)
                if not st.session_state.get(f"q{question_idx}_added"):
                    try:
                        session_manager.add_turn(
                            speaker="avatar",
                            text=current_q.get('text', 'Question')
                        )
                        st.session_state[f"q{question_idx}_added"] = True
                        print(f"[OK] Added Q{question_idx + 1} to session transcript")
                    except Exception as e:
                        st.warning(f"Could not save question to transcript: {e}")
                        print(f"[ERROR] Failed to add question: {e}")
                
                # Display progress
                st.progress(
                    (question_idx + 1) / len(questions),
                    text=f"Question {question_idx + 1} of {len(questions)}"
                )
                
                st.divider()
                
                # Display question
                st.subheader(f"Q{question_idx + 1}: {current_q.get('text', 'Question')}")
                
                # Display image if available (smaller size for better UI)
                image_path = current_q.get('image_path')
                
                # Try different sources for the image
                if image_path and os.path.exists(image_path):
                    try:
                        st.image(image_path, caption=f"Question reference", width=500)
                    except Exception as e:
                        st.warning(f"Could not display image: {e}")
                else:
                    # If question doesn't have an image_path, try to get one from DialogueManager
                    if dialogue_manager and hasattr(dialogue_manager, 'page_images') and dialogue_manager.page_images:
                        # Try to get page image - prefer page 1 as default
                        fallback_img = dialogue_manager.page_images.get(1) or next(iter(dialogue_manager.page_images.values()), None)
                        if fallback_img and os.path.exists(fallback_img):
                            st.image(fallback_img, caption="Question reference (paper overview)", width=500)
                
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
                            
                            # Score the answer using the appropriate rubric
                            # Prefer AI-generated topic-specific rubric if available
                            from agent_a5_grader import RubricGrader
                            
                            if "topic_rubric" in st.session_state and st.session_state.topic_rubric:
                                # Use the AI-generated topic-specific rubric
                                grader = RubricGrader(rubric_dict=st.session_state.topic_rubric)
                                detected_topic = st.session_state.get("detected_topic", "Custom Topic")
                                st.info(f"📍 Using AI-generated rubric for: {detected_topic}")
                            else:
                                # Fall back to default rubric
                                rubric_name = subject_manager.get_default_rubric(subject)
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
                st.divider()
                
                # ===== QUESTIONS & ANSWERS WITH FEEDBACK =====
                st.subheader("💬 Questions, Answers & Feedback")
                
                # Get turns from transcript (not "turns")
                transcript = session_data.get("transcript", [])
                scores_list = session_data.get("scores", [])
                
                # DEBUG: Show what we have
                with st.expander("🔍 Debug Info"):
                    st.write(f"**Transcript items:** {len(transcript)}")
                    st.write(f"**Scores items:** {len(scores_list)}")
                    if transcript:
                        st.write("**Transcript speakers:**")
                        for t in transcript:
                            st.write(f"- {t.get('speaker', 'unknown')}: {t.get('text', '')[:80]}...")
                    else:
                        st.warning("❌ No transcript items found!")
                
                # Organize turns by question
                questions = []
                current_question = None
                question_num = 0
                
                for turn in transcript:
                    speaker = turn.get('speaker', '').lower()
                    text = turn.get('text', '').strip()
                    
                    if speaker == 'avatar' and text:
                        question_num += 1
                        if current_question:
                            questions.append(current_question)
                        current_question = {
                            "number": question_num,
                            "question": text,
                            "answer": None,
                            "scores": None
                        }
                    elif speaker == 'student' and text and current_question:
                        current_question["answer"] = text
                
                if current_question:
                    questions.append(current_question)
                
                # Match scores with questions from the scores list
                # scores_list is formatted as: [{"Q1": grading_result}, {"Q2": grading_result}, ...]
                if scores_list:
                    for score_dict in scores_list:
                        for key, value in score_dict.items():
                            # Extract question number from key like "Q1", "Q2", etc.
                            if key.startswith("Q"):
                                try:
                                    q_num = int(key[1:])
                                    if q_num <= len(questions):
                                        questions[q_num - 1]["scores"] = value
                                except (ValueError, IndexError):
                                    pass
                
                # Display questions with answers and feedback
                if questions:
                    for q_info in questions:
                        q_num = q_info["number"]
                        q_text = q_info["question"]
                        answer = q_info["answer"]
                        q_scores = q_info["scores"]
                        
                        with st.container(border=True):
                            # Question header
                            st.markdown(f"## Q{q_num}: {q_text[:100]}{'...' if len(q_text) > 100 else ''}")
                            
                            # Student answer
                            if answer:
                                with st.expander(f"📝 Student Answer", expanded=False):
                                    st.write(answer)
                            else:
                                st.warning("No answer provided for this question")
                            
                            # Scores and feedback
                            if q_scores:
                                if isinstance(q_scores, dict) and "tutoring_feedback" in q_scores:
                                    # This is a grading result with feedback
                                    st.markdown("### 📊 Score & Feedback")
                                    
                                    # Score summary
                                    total = q_scores.get("total_score", 0)
                                    max_score = q_scores.get("max_score", 100)
                                    percentage = q_scores.get("percentage", 0)
                                    
                                    col1, col2, col3 = st.columns(3)
                                    with col1:
                                        st.metric("Score", f"{total}/{max_score}")
                                    with col2:
                                        st.metric("Percentage", f"{percentage}%")
                                    with col3:
                                        status = "Excellent" if percentage >= 80 else "Good" if percentage >= 70 else "Fair" if percentage >= 60 else "Needs Improvement"
                                        st.metric("Status", status)
                                    
                                    # Criteria breakdown
                                    criteria_scores = q_scores.get("scores", [])
                                    if criteria_scores:
                                        st.markdown("**Criteria Breakdown:**")
                                        for criterion in criteria_scores:
                                            if isinstance(criterion, dict):
                                                criterion_name = criterion.get("criterion", "Unknown")
                                                score = criterion.get("score", 0)
                                                max_s = criterion.get("max_score", 10)
                                                feedback = criterion.get("feedback", "")
                                                
                                                col_name, col_score = st.columns([3, 1])
                                                with col_name:
                                                    st.write(f"**{criterion_name}**")
                                                    if feedback:
                                                        st.caption(f"_{feedback}_")
                                                with col_score:
                                                    st.metric("", f"{score}/{max_s}", label_visibility="collapsed")
                                    
                                    # Tutoring feedback
                                    tutoring = q_scores.get("tutoring_feedback", "")
                                    if tutoring:
                                        st.markdown("### 🎓 Tutor Feedback")
                                        st.info(tutoring)
                            else:
                                st.info("No scoring data available for this question")
                            
                            st.divider()
                else:
                    st.info("No questions found in this session.")
                
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
    
    tab1, tab2, tab3, tab4 = st.tabs(["Rubrics", "Subjects", "System", "Clear Data"])
    
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
    
    with tab4:
        st.subheader("🗑️ Clear Data & Cache")
        st.warning("⚠️ **WARNING:** Clearing data cannot be undone. Please be careful!")
        
        st.divider()
        
        # Clear Sessions
        st.subheader("📋 Clear Sessions")
        sessions_list = session_manager.list_sessions()
        sessions_count = len(sessions_list)
        st.write(f"**{sessions_count} sessions** currently stored")
        
        if sessions_count > 0:
            st.write("**Select sessions to delete:**")
            sessions_to_delete = []
            
            for session_id in sessions_list:
                if st.checkbox(f"📋 {session_id}", key=f"session_{session_id}"):
                    sessions_to_delete.append(session_id)
            
            if sessions_to_delete:
                st.info(f"✓ {len(sessions_to_delete)} session(s) selected for deletion")
                
                if st.button("🗑️ Delete Selected Sessions", key="delete_selected_sessions"):
                    for session_id in sessions_to_delete:
                        session_file = Path("data/sessions") / f"{session_id}_session.json"
                        if session_file.exists():
                            session_file.unlink()
                    st.success(f"✓ {len(sessions_to_delete)} session(s) deleted!")
                    st.rerun()
            
            st.divider()
            
            # Clear All Sessions Option
            if st.button("🗑️ Clear ALL Sessions", key="clear_all_sessions"):
                st.session_state.confirm_all_sessions_mode = True
            
            if st.session_state.get("confirm_all_sessions_mode", False):
                st.warning("⚠️ This will delete ALL assessment sessions!")
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.checkbox("I understand this will delete ALL sessions", key="confirm_all_sessions_1"):
                        if st.button("✓ Yes, Delete All Sessions", key="confirm_delete_all_sessions"):
                            import shutil
                            sessions_dir = Path("data/sessions")
                            if sessions_dir.exists():
                                shutil.rmtree(sessions_dir)
                                sessions_dir.mkdir(parents=True, exist_ok=True)
                            st.session_state.confirm_all_sessions_mode = False
                            st.success("✓ All sessions cleared!")
                            st.rerun()
                
                with col2:
                    if st.button("✗ Cancel", key="cancel_delete_all_sessions"):
                        st.session_state.confirm_all_sessions_mode = False
                        st.rerun()
        else:
            st.info("No sessions to clear")
        
        st.divider()
        
        # Clear Rubrics
        st.subheader("📋 Clear Rubrics")
        rubric_path = Path("data/rubrics")
        rubric_files = list(rubric_path.glob("*.json")) if rubric_path.exists() else []
        rubric_count = len(rubric_files)
        st.write(f"**{rubric_count} rubrics** currently stored")
        
        if rubric_count > 0:
            st.write("**Select rubrics to delete:**")
            rubrics_to_delete = []
            
            for rubric_file in rubric_files:
                # Don't allow deletion of templates by default
                is_template = any(x in rubric_file.stem for x in ["primary", "secondary", "high_school", "university"])
                disabled = is_template
                
                if st.checkbox(
                    f"📋 {rubric_file.stem}" + (" (Template)" if is_template else ""),
                    key=f"rubric_{rubric_file.stem}",
                    disabled=disabled
                ):
                    rubrics_to_delete.append(rubric_file)
            
            if rubrics_to_delete:
                st.info(f"✓ {len(rubrics_to_delete)} rubric(s) selected for deletion")
                
                if st.button("🗑️ Delete Selected Rubrics", key="delete_selected_rubrics"):
                    for rubric_file in rubrics_to_delete:
                        rubric_file.unlink()
                    st.success(f"✓ {len(rubrics_to_delete)} rubric(s) deleted!")
                    st.rerun()
            
            st.divider()
            
            # Clear All Rubrics Option
            if st.button("🗑️ Clear ALL Rubrics (except templates)", key="clear_all_rubrics"):
                st.session_state.confirm_all_rubrics_mode = True
            
            if st.session_state.get("confirm_all_rubrics_mode", False):
                st.warning("⚠️ This will delete ALL custom rubrics!")
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.checkbox("I understand this will delete ALL custom rubrics", key="confirm_all_rubrics_1"):
                        if st.button("✓ Yes, Delete All Custom Rubrics", key="confirm_delete_all_rubrics"):
                            for rubric_file in rubric_files:
                                if not any(x in rubric_file.stem for x in ["primary", "secondary", "high_school", "university"]):
                                    rubric_file.unlink()
                            st.session_state.confirm_all_rubrics_mode = False
                            st.success("✓ Custom rubrics cleared! (Templates preserved)")
                            st.rerun()
                
                with col2:
                    if st.button("✗ Cancel", key="cancel_delete_all_rubrics"):
                        st.session_state.confirm_all_rubrics_mode = False
                        st.rerun()
        else:
            st.info("No rubrics to clear")
        
        st.divider()
        
        # Clear Papers/Uploads
        st.subheader("📄 Clear Uploaded Papers & Vector Databases")
        subjects_list = subject_manager.list_subjects()
        st.write(f"**{len(subjects_list)} subjects** with data currently stored")
        
        if len(subjects_list) > 0:
            st.write("**Select subjects to delete:**")
            subjects_to_delete = []
            
            for subject in subjects_list:
                if st.checkbox(f"📚 {subject}", key=f"subject_{subject}"):
                    subjects_to_delete.append(subject)
            
            if subjects_to_delete:
                st.info(f"✓ {len(subjects_to_delete)} subject(s) selected for deletion")
                
                if st.button("🗑️ Delete Selected Papers & Databases", key="delete_selected_papers"):
                    import shutil
                    import gc
                    import time
                    
                    # Step 0: Close any active DialogueManager instances
                    if 'dialogue_manager' in st.session_state:
                        try:
                            st.session_state.dialogue_manager.cleanup()
                            del st.session_state.dialogue_manager
                            st.write("✓ Closed dialogue manager connections")
                        except Exception as e:
                            st.warning(f"Could not close dialogue manager: {str(e)}")
                    
                    # Step 1: Clear all Streamlit caches to release vector store references
                    try:
                        st.cache_data.clear()
                        st.cache_resource.clear()
                        st.write("✓ Cleared Streamlit caches")
                    except:
                        pass
                    
                    # Step 2: Force garbage collection multiple times
                    for _ in range(3):
                        gc.collect()
                        time.sleep(0.3)
                    st.write("✓ Forced garbage collection")
                    
                    deletion_errors = []
                    deleted_count = 0
                    
                    for subject in subjects_to_delete:
                        try:
                            st.info(f"🔄 Deleting {subject}...")
                            
                            # Delete input files
                            input_subject_dir = Path("data/input") / subject
                            if input_subject_dir.exists():
                                shutil.rmtree(input_subject_dir)
                                st.write(f"  ✓ Deleted input files")
                            
                            # Delete output chunks
                            output_subject_dir = Path("data/output") / subject
                            if output_subject_dir.exists():
                                shutil.rmtree(output_subject_dir)
                                st.write(f"  ✓ Deleted output chunks")
                            
                            # Delete vector database with aggressive retry
                            db_deleted = False
                            for chroma_db in Path("data/chroma_db").glob("*_db"):
                                if subject.lower() in chroma_db.name.lower():
                                    try:
                                        # Try immediate deletion first
                                        shutil.rmtree(chroma_db)
                                        db_deleted = True
                                        st.write(f"  ✓ Deleted vector database")
                                    except PermissionError as e:
                                        # Database still locked, try harder
                                        st.write(f"  ⏳ Database locked, retrying...")
                                        for attempt in range(3):
                                            try:
                                                time.sleep(0.5)
                                                gc.collect()
                                                
                                                # Try deleting individual files
                                                import os
                                                for root, dirs, files in os.walk(chroma_db, topdown=False):
                                                    for f in files:
                                                        try:
                                                            os.unlink(os.path.join(root, f))
                                                        except:
                                                            pass
                                                    for d in dirs:
                                                        try:
                                                            os.rmdir(os.path.join(root, d))
                                                        except:
                                                            pass
                                                
                                                os.rmdir(chroma_db)
                                                db_deleted = True
                                                st.write(f"  ✓ Deleted vector database (attempt {attempt+1})")
                                                break
                                            except Exception as retry_error:
                                                if attempt == 2:
                                                    deletion_errors.append(f"{subject}: Database is locked - close any open documents and try again")
                            
                            # Delete extracted images
                            images_dir = Path("data") / f"{subject}_images"
                            if images_dir.exists():
                                shutil.rmtree(images_dir)
                                st.write(f"  ✓ Deleted extracted images")
                            
                            # Remove from subject config
                            if subject in subject_manager.config["subjects"]:
                                del subject_manager.config["subjects"][subject]
                            
                            deleted_count += 1
                            st.success(f"✓ {subject} deleted successfully!")
                        
                        except Exception as e:
                            deletion_errors.append(f"{subject}: {str(e)}")
                            st.error(f"❌ Error deleting {subject}: {str(e)}")
                    
                    subject_manager._save_config()
                    
                    if deletion_errors:
                        st.warning(f"⚠️ Partially completed: {deleted_count}/{len(subjects_to_delete)} subject(s) deleted")
                        for error in deletion_errors:
                            st.error(f"❌ {error}")
                        st.info("💡 **How to fix:**\n1. Navigate away from the Assessment page\n2. Click 'Refresh Cache' in the System tab\n3. Try deleting again")
                    else:
                        st.success(f"✓ {deleted_count} subject(s) deleted successfully!")
                    
                    st.rerun()
            
            st.divider()
            
            # Clear All Papers Option
            if st.button("🗑️ Clear ALL Papers & Databases", key="clear_all_papers"):
                st.session_state.confirm_all_papers_mode = True
            
            if st.session_state.get("confirm_all_papers_mode", False):
                st.warning("⚠️ This will delete ALL uploaded papers and vector databases!")
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.checkbox("I understand this will delete ALL data", key="confirm_all_papers_1"):
                        if st.button("✓ Yes, Delete Everything", key="confirm_delete_all_papers"):
                            import shutil
                            import gc
                            import time
                            
                            # Step 0: Close any active DialogueManager instances
                            if 'dialogue_manager' in st.session_state:
                                try:
                                    st.session_state.dialogue_manager.cleanup()
                                    del st.session_state.dialogue_manager
                                    st.write("✓ Closed dialogue manager connections")
                                except Exception as e:
                                    st.warning(f"Could not close dialogue manager: {str(e)}")
                            
                            # Step 1: Clear all caches to release handles
                            try:
                                st.cache_data.clear()
                                st.cache_resource.clear()
                                st.write("✓ Cleared Streamlit caches")
                            except:
                                pass
                            
                            # Step 2: Force garbage collection multiple times
                            for _ in range(3):
                                gc.collect()
                                time.sleep(0.3)
                            st.write("✓ Forced garbage collection")
                            
                            st.info("🔄 Clearing all papers and databases...")
                            
                            errors = []
                            
                            try:
                                # Clear input files
                                input_dir = Path("data/input")
                                if input_dir.exists():
                                    shutil.rmtree(input_dir)
                                    input_dir.mkdir(parents=True, exist_ok=True)
                                st.write("✓ Cleared input files")
                                
                                # Clear output chunks
                                output_dir = Path("data/output")
                                if output_dir.exists():
                                    shutil.rmtree(output_dir)
                                    output_dir.mkdir(parents=True, exist_ok=True)
                                st.write("✓ Cleared output chunks")
                                
                                # Clear vector databases with aggressive retry
                                chroma_dir = Path("data/chroma_db")
                                if chroma_dir.exists():
                                    try:
                                        shutil.rmtree(chroma_dir)
                                        chroma_dir.mkdir(parents=True, exist_ok=True)
                                        st.write("✓ Cleared vector databases")
                                    except PermissionError:
                                        st.write("⏳ Databases locked, retrying...")
                                        for attempt in range(3):
                                            try:
                                                time.sleep(0.5)
                                                gc.collect()
                                                
                                                # Try file-by-file deletion
                                                import os
                                                for root, dirs, files in os.walk(chroma_dir, topdown=False):
                                                    for f in files:
                                                        try:
                                                            os.unlink(os.path.join(root, f))
                                                        except:
                                                            pass
                                                    for d in dirs:
                                                        try:
                                                            os.rmdir(os.path.join(root, d))
                                                        except:
                                                            pass
                                                
                                                os.rmdir(chroma_dir)
                                                chroma_dir.mkdir(parents=True, exist_ok=True)
                                                st.write(f"✓ Cleared vector databases (attempt {attempt+1})")
                                                break
                                            except Exception as retry_error:
                                                if attempt == 2:
                                                    errors.append("Vector databases are locked - couldn't delete")
                                
                                # Clear extracted images
                                for images_dir in Path("data").glob("*_images"):
                                    try:
                                        shutil.rmtree(images_dir)
                                    except:
                                        pass
                                st.write("✓ Cleared extracted images")
                                
                                # Reset subject config
                                subject_manager.config["subjects"] = {}
                                subject_manager._save_config()
                                st.write("✓ Reset subject configuration")
                                
                                st.session_state.confirm_all_papers_mode = False
                                
                                if errors:
                                    st.warning("⚠️ Mostly completed!")
                                    for error in errors:
                                        st.error(f"❌ {error}")
                                    st.info("💡 **How to fix:**\n1. Navigate away from the Assessment page\n2. Click 'Refresh Cache' in the System tab\n3. Try again")
                                else:
                                    st.success("✓ All papers, databases, and images cleared!")
                                
                                st.rerun()
                            
                            except Exception as e:
                                st.error(f"Error during cleanup: {str(e)}")
                                st.info("💡 **How to fix:**\n1. Navigate away from the Assessment page\n2. Click 'Refresh Cache' in the System tab\n3. Try again")
                
                with col2:
                    if st.button("✗ Cancel", key="cancel_delete_all_papers"):
                        st.session_state.confirm_all_papers_mode = False
                        st.rerun()
        else:
            st.info("No papers/uploads to clear")
        
        st.divider()
        
        # Clear Everything
        st.subheader("🔴 Clear EVERYTHING")
        st.error("⛔ **DANGER ZONE:** This will delete EVERYTHING including sessions, rubrics, papers, and databases!")
        
        if st.button("🔴 CLEAR ALL DATA", key="clear_all"):
            if st.checkbox("I understand this will delete EVERYTHING", key="confirm_all_1"):
                if st.checkbox("I am absolutely sure - this cannot be undone", key="confirm_all_2"):
                    import shutil
                    
                    # Clear everything in data directory except config files
                    data_dir = Path("data")
                    if data_dir.exists():
                        for item in data_dir.iterdir():
                            if item.is_dir():
                                shutil.rmtree(item)
                            elif item.name not in ["subject_config.json"]:
                                item.unlink()
                    
                    # Reset subject config
                    subject_manager.config["subjects"] = {}
                    subject_manager._save_config()
                    
                    st.success("✓ All data cleared! System reset to fresh state.")
                    st.rerun()

# Footer
st.divider()
st.markdown("""
<p style="text-align: center; color: gray; font-size: 0.9rem;">
Oral Assessment System v1.0 | Built with Streamlit + LangChain
</p>
""", unsafe_allow_html=True)
