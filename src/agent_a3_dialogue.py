"""
Agent A3: Dialogue Manager
Extracts actual exam questions from ingested documents and manages Q&A dialogue flow.
Uses rubric-based assessment for scoring student responses.
Optional: Generate audio for questions/feedback using Agent A4 (TTS).
"""

import os
import re
import json
import subprocess
import sys
from typing import List, Dict
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from subject_manager import SubjectManager
from rubric_engine import RubricEngine
from agent_a6_session_manager import SessionManager

try:
    from agent_audio_input import AudioRecorder, SpeechToText
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False

load_dotenv()

class DialogueManager:
    """Manages oral assessment using actual extracted exam questions and rubric-based scoring."""
    
    def __init__(self, subject: str | None = None, rubric_name: str | None = None, 
                 session_id: str | None = None, use_sessions: bool = False):
        """
        Initialize dialogue manager.
        
        Args:
            subject: Subject/topic name for multi-subject organization
            rubric_name: Name of rubric to use for scoring
            session_id: Session ID (optional, for tracking)
            use_sessions: Whether to use session manager for tracking
        """
        self.subject = subject
        self.session_id = session_id
        self.use_sessions = use_sessions
        self.session_manager = SessionManager() if use_sessions else None
        self.subject_manager = SubjectManager()
        self.chroma_db_path = str(self.subject_manager.get_subject_chroma_path(subject))
        
        self.embedding_function = OpenAIEmbeddings(
            api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # Initialize LLM for question extraction and reasoning
        self.llm = ChatOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            model="gpt-3.5-turbo",
            temperature=0.7
        )
        
        # Load vector store
        self.vector_store = Chroma(
            persist_directory=self.chroma_db_path,
            embedding_function=self.embedding_function
        )
        
        # Initialize rubric engine
        self.rubric_engine = RubricEngine()
        if rubric_name:
            self.rubric_engine.load_rubric(rubric_name)
        
        # Conversation state
        self.questions = []
        self.current_question_index = 0
        self.answers = []
        self.scores = []
    
    def generate_audio(self, text: str, output_path: str | None = None, enable_audio: bool = True) -> str | None:
        """
        Generate audio for text using Agent A4 (TTS).
        
        Args:
            text: Text to convert to speech
            output_path: Path to save audio file (optional)
            enable_audio: Whether to generate audio (can disable for testing)
            
        Returns:
            Path to generated audio file, or None if disabled/failed
        """
        if not enable_audio or not text:
            return None
        
        try:
            # Default output path if not specified
            if not output_path:
                q_num = self.current_question_index + 1
                output_path = f"data/output/question_{q_num}_audio.wav"
            
            # Call Agent A4 TTS
            cmd = [
                sys.executable,
                "src/agent_a4_avatar.py",
                "--text", text,
                "--output", output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                return output_path
            else:
                print(f"⚠️ TTS failed: {result.stderr}")
                return None
        except Exception as e:
            print(f"⚠️ Audio generation error: {e}")
            return None
    
    def record_and_transcribe_answer(self, question_id: int, duration: int = 15) -> str | None:
        """
        Record student's oral answer and transcribe it.
        
        Args:
            question_id: ID of the question being answered
            duration: Maximum recording duration (seconds)
            
        Returns:
            Transcribed answer text, or None if recording/transcription failed
        """
        if not AUDIO_AVAILABLE:
            print("⚠️ Audio module not available. Please install: pip install pyaudio openai")
            return None
        
        try:
            # Create session directory
            session_dir = "data/sessions"
            os.makedirs(session_dir, exist_ok=True)
            
            # Record audio
            recorder = AudioRecorder()
            audio_path = recorder.record_audio(
                duration=duration,
                output_path=f"{session_dir}/q{question_id}_answer.wav"
            )
            
            # Transcribe audio
            stt = SpeechToText()
            result = stt.transcribe_audio(audio_path)
            
            # Save transcription
            with open(f"{session_dir}/q{question_id}_transcription.json", 'w') as f:
                json.dump({
                    "question_id": question_id,
                    "audio_file": audio_path,
                    "transcription": result
                }, f, indent=2)
            
            return result["text"]
        
        except Exception as e:
            print(f"❌ Audio recording/transcription error: {str(e)}")
            return None
    
    def extract_questions_from_document(self, num_questions: int = 5) -> List[Dict]:
        """
        Extract actual questions from the ingested document.
        Uses semantic search and pattern matching to identify questions.
        
        Args:
            num_questions: Number of questions to extract
            
        Returns:
            List of question dictionaries with id, text, and context
        """
        print(f"\n📚 Extracting questions from document...\n")
        
        # Get all chunks from the document
        retriever = self.vector_store.as_retriever(search_kwargs={"k": 50})
        doc_samples = retriever.invoke("question Q problem exercise")
        
        # Combine all chunks for analysis
        combined_text = "\n".join([doc.page_content for doc in doc_samples])
        
        questions = []
        
        # Pattern 1: Q1) Q2) Q3) format
        q_pattern = r'Q(\d+)\)\s*([^\n]+?)(?:\n|$)'
        matches = re.finditer(q_pattern, combined_text)
        seen = set()
        for match in matches:
            qid = int(match.group(1))
            qtext = match.group(2).strip()
            
            # Clean up the question text
            if qtext and len(qtext) > 5 and qtext not in seen:
                seen.add(qtext)
                # Remove common formatting noise
                qtext = qtext.replace('www.sgexam.com', '').strip()
                if qtext:
                    questions.append({
                        "id": len(questions) + 1,
                        "text": qtext,
                        "source": f"Question {qid} from document",
                        "answered": False,
                        "answer": None,
                        "scores": None
                    })
        
        # Pattern 2: Numbered format 1. 2. 3. or 1) 2) 3)
        if len(questions) < num_questions:
            num_pattern = r'^\s*(\d+)[.)\s]\s+([^\n]+?)(?:\n|$)'
            matches = re.finditer(num_pattern, combined_text, re.MULTILINE)
            for match in matches:
                qnum = int(match.group(1))
                qtext = match.group(2).strip()
                
                if qtext and len(qtext) > 10 and qtext not in seen and len(questions) < num_questions * 2:
                    seen.add(qtext)
                    qtext = qtext.replace('www.sgexam.com', '').strip()
                    if qtext:
                        # Avoid duplicates
                        if not any(q['text'] == qtext for q in questions):
                            questions.append({
                                "id": len(questions) + 1,
                                "text": qtext,
                                "source": f"Question {qnum} from document",
                                "answered": False,
                                "answer": None,
                                "scores": None
                            })
        
        # If LLM parsing is needed, try it as fallback
        if len(questions) < 3:
            prompt = ChatPromptTemplate.from_template(
                """Extract all exam questions from this text.
                Return ONLY a JSON list: {{"questions": ["Q1 text", "Q2 text", ...]}}
                
                Text:
                {content}"""
            )
            
            chain = prompt | self.llm | StrOutputParser()
            try:
                response = chain.invoke({"content": combined_text[:3000]})
                data = json.loads(response)
                for q_text in data.get("questions", []):
                    if q_text and len(q_text) > 5 and q_text not in seen:
                        seen.add(q_text)
                        questions.append({
                            "id": len(questions) + 1,
                            "text": q_text.strip(),
                            "source": "LLM-extracted from document",
                            "answered": False,
                            "answer": None,
                            "scores": None
                        })
            except:
                pass  # If LLM fails, use what we already extracted
        
        self.questions = questions[:num_questions]
        return self.questions
    
    def get_current_question(self) -> Dict | None:
        """Get the current unanswered question"""
        for q in self.questions:
            if not q["answered"]:
                return q
        return None
    
    def submit_answer(self, answer: str) -> Dict:
        """
        Submit an answer to the current question.
        
        Args:
            answer: Student's response
            
        Returns:
            Assessment result with feedback
        """
        question = self.get_current_question()
        if not question:
            return {"error": "All questions answered"}
        
        # Record answer
        question["answer"] = answer
        question["answered"] = True
        self.answers.append(answer)
        
        # Score using rubric if loaded
        result = {
            "question_id": question["id"],
            "question": question["text"],
            "answer": answer
        }
        
        if self.rubric_engine.current_rubric:
            scores = self.rubric_engine.score_answer(
                question["text"], 
                answer
            )
            
            question["scores"] = scores
            total_score = sum(s.score for s in scores)
            max_score = sum(s.max_score for s in scores)
            
            result["scores"] = {
                "criterion_scores": [
                    {
                        "criterion": s.criterion_name,
                        "score": s.score,
                        "max_score": s.max_score,
                        "feedback": s.feedback
                    }
                    for s in scores
                ],
                "total_score": total_score,
                "max_score": max_score,
                "percentage": round((total_score / max_score * 100) if max_score > 0 else 0, 1)
            }
            
            self.scores.append(total_score)
        else:
            result["note"] = "No rubric loaded - no scoring applied"
        
        return result
    
    def log_turn(self, speaker: str, text: str, audio_path: str | None = None) -> None:
        """
        Log a dialogue turn to session if sessions are enabled.
        
        Args:
            speaker: "avatar" or "student"
            text: The utterance text
            audio_path: Optional path to audio file
        """
        if self.use_sessions and self.session_manager and self.session_manager.current_session:
            self.session_manager.add_turn(
                speaker=speaker,
                text=text,
                audio_path=audio_path,
                metadata={"subject": self.subject, "question_id": self.current_question_index + 1}
            )
    
    def get_assessment_report(self) -> Dict:
        """Generate final assessment report"""
        if not self.questions:
            return {"error": "No questions asked"}
        
        answered_count = sum(1 for q in self.questions if q["answered"])
        
        report = {
            "subject": self.subject,
            "total_questions": len(self.questions),
            "answered_questions": answered_count,
            "questions": self.questions
        }
        
        if self.scores:
            total_score = sum(self.scores)
            max_possible = len(self.scores) * 10  # Basic calculation
            report["total_score"] = total_score
            report["average_score"] = round(total_score / len(self.scores), 1) if self.scores else 0
            report["percentage"] = round((total_score / max_possible * 100) if max_possible > 0 else 0, 1)
        
        return report


def interactive_assessment(subject: str | None = None, rubric_name: str | None = None, enable_audio: bool = False, use_audio_input: bool = False, use_sessions: bool = False, student_id: str = "student_001"):
    """
    Run interactive assessment mode
    
    Args:
        subject: Subject/topic name
        rubric_name: Name of rubric for scoring
        enable_audio: Whether to generate audio for questions
        use_audio_input: Whether to use audio recording for student answers
        use_sessions: Whether to track session with persistence
        student_id: Student ID for session tracking
    """
    subject_label = f" [{subject}]" if subject else ""
    audio_label = " [With Audio Output]" if enable_audio else ""
    audio_input_label = " [Audio Input Mode]" if use_audio_input else ""
    session_label = " [Session Tracking]" if use_sessions else ""
    print("\n" + "="*60)
    print(f"🎓 Oral Assessment System - Agent A3 (Dialogue Manager){subject_label}{audio_label}{audio_input_label}{session_label}")
    print("="*60 + "\n")
    
    # Initialize dialogue manager with session support
    dialogue = DialogueManager(subject=subject, rubric_name=rubric_name, use_sessions=use_sessions)
    
    # Create session if tracking is enabled
    if use_sessions:
        session_id = dialogue.session_manager.create_session(
            paper_id=subject or "assessment",
            student_id=student_id,
            metadata={
                "rubric": rubric_name,
                "subject": subject,
                "audio_input": use_audio_input,
                "audio_output": enable_audio
            }
        )
        dialogue.session_id = session_id
        dialogue.session_manager.start_session(session_id)
        print(f"\n📋 Session: {session_id}\n")
    
    # Extract questions from document
    questions = dialogue.extract_questions_from_document(num_questions=5)
    
    if not questions:
        print("❌ Could not extract questions from document")
        return
    
    print(f"✅ Extracted {len(questions)} questions:\n")
    for q in questions:
        print(f"  {q['id']}. {q['text']}\n")
    
    # Assessment loop
    while True:
        question = dialogue.get_current_question()
        
        if not question:
            # All questions answered - show report
            print("\n✅ Assessment Complete!\n")
            report = dialogue.get_assessment_report()
            
            # End session if tracking
            if use_sessions and dialogue.session_manager:
                dialogue.session_manager.end_session(dialogue.session_id)
                print(f"📋 Session saved: {dialogue.session_id}\n")
            
            print("="*60)
            print("Assessment Report")
            print("="*60)
            print(f"Questions Asked: {report['total_questions']}")
            print(f"Questions Answered: {report['answered_questions']}")
            
            if "total_score" in report:
                print(f"Total Score: {report['total_score']} / {report.get('max_possible', '?')}")
                print(f"Average Score: {report['average_score']}/10")
                print(f"Percentage: {report['percentage']}%")
            
            print("="*60 + "\n")
            break
        
        # Ask question
        print(f"❓ Question {dialogue.current_question_index + 1}/{len(dialogue.questions)}:")
        print(f"{question['text']}\n")
        
        # Log avatar's question to session
        dialogue.log_turn("avatar", question['text'])
        
        # Generate audio for question if enabled
        if enable_audio:
            print("🔊 Generating audio...")
            audio_file = dialogue.generate_audio(question['text'], enable_audio=True)
            if audio_file:
                print(f"✅ Audio available: {audio_file}\n")
        
        # Get answer (either via text input or audio recording)
        if use_audio_input:
            print("🎤 Recording audio answer (15 seconds max)...\n")
            answer = dialogue.record_and_transcribe_answer(question["id"], duration=15)
            
            if not answer:
                print("❌ Failed to record/transcribe audio. Try again.\n")
                continue
            
            print(f"✓ Transcribed answer: {answer}\n")
        else:
            answer = input("Your answer: ").strip()
        
        if not answer:
            print("Please provide an answer.\n")
            continue
        
        # Log student's answer to session
        dialogue.log_turn("student", answer)
        
        # Submit and get feedback
        print("\n⏳ Evaluating answer...\n")
        result = dialogue.submit_answer(answer)
        
        # Show feedback
        if "scores" in result:
            print("📊 Scores by Criterion:")
            for criterion_score in result["scores"]["criterion_scores"]:
                print(f"  {criterion_score['criterion']}: {criterion_score['score']}/{criterion_score['max_score']}")
            print(f"\n📈 Total: {result['scores']['total_score']}/{result['scores']['max_score']} ({result['scores']['percentage']}%)\n")
        elif "note" in result:
            print(f"ℹ️  {result['note']}\n")
        
        dialogue.current_question_index += 1
        print("-" * 60 + "\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Dialogue Manager for Assessment")
    parser.add_argument("--interactive", action="store_true", help="Run in interactive mode")
    parser.add_argument("--subject", type=str, default=None, help="Subject/topic name")
    parser.add_argument("--rubric", type=str, default=None, help="Rubric name to use for scoring")
    parser.add_argument("--audio", action="store_true", help="Generate audio for questions (requires pyttsx3)")
    parser.add_argument("--use-audio-input", action="store_true", help="Use audio recording for student answers (requires pyaudio + openai)")
    parser.add_argument("--use-sessions", action="store_true", help="Track assessment session with persistence")
    parser.add_argument("--student-id", type=str, default="student_001", help="Student ID for session tracking")
    args = parser.parse_args()
    
    interactive_assessment(subject=args.subject, rubric_name=args.rubric, enable_audio=args.audio, use_audio_input=args.use_audio_input, use_sessions=args.use_sessions, student_id=args.student_id)
