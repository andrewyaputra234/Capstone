"""
Crew Orchestrator - Multi-Agent AI System for Educational Assessment

Coordinates CrewAI agents with the existing agent stack:
  main.py (ingestion) · agent_a3_dialogue · agent_a5_grader · agent_a6_session_manager
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from env_fix import apply_runtime_fixes

apply_runtime_fixes()

from crewai import Agent, Crew, Task
from crewai.tools import tool
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

DEFAULT_PSLE_SUBJECT = "psle_oral_english"
DEFAULT_PSLE_RUBRIC = "psle_oral_english"

PSLE_ORAL_CONTEXT = """
This system is focused on PSLE English oral practice.
Assume uploaded documents are PSLE-style English oral examination materials:
reading-aloud passages, purpose/audience/context preambles, visual stimulus
descriptions or images, stimulus-based conversation prompts, and follow-up prompts.

Assessment focus:
- Reading Aloud: clarity, pronunciation evidence, fluency, pace, expression,
  and awareness of purpose, audience, and context.
- Stimulus-based Conversation: relevant personal response, reference to the
  stimulus, elaborated ideas, examples, reasons, accurate spoken English, and
  confident interaction.

Coaching behavior:
- If the student struggles, do not give a full model answer immediately.
- Ask one scaffolded follow-up question, offer a sentence starter, or give two
  simple choices that help the student continue.
- Keep the tone calm, age-appropriate, and encouraging for a Primary 6 learner.
- After support, invite the student to try again or add one more detail.
"""


# ---------------------------------------------------------------------------
# Runtime context – tools read the active EducationCrew instance state
# ---------------------------------------------------------------------------

@dataclass
class _CrewRuntimeContext:
    subject: str = ""
    rubric_name: str = ""
    session_id: Optional[str] = None
    dialogue_manager: Any = None
    session_manager: Any = None


_ctx = _CrewRuntimeContext()


def _set_runtime_context(crew: "EducationCrew") -> None:
    _ctx.subject = crew.subject
    _ctx.rubric_name = crew.rubric_name or ""
    _ctx.session_id = crew.session_id
    _ctx.dialogue_manager = crew.dialogue_manager
    _ctx.session_manager = crew.session_manager


# ---------------------------------------------------------------------------
# CrewAI tools wired to real infrastructure
# ---------------------------------------------------------------------------

@tool("Extract Document Content")
def extract_document_content(file_path: str) -> str:
    """Extract and summarize educational document content from a file path."""
    try:
        from main import load_document, split_document

        documents = load_document(Path(file_path))
        chunks = split_document(documents, chunk_size=1000, chunk_overlap=100)
        preview = "\n".join(chunk.page_content for chunk in chunks[:3])
        return (
            f"Extracted {len(chunks)} content chunks from {Path(file_path).name}.\n\n"
            f"Preview:\n{preview[:2000]}"
        )
    except Exception as e:
        return f"Error extracting document: {e}"


def _retrieve_vector_context(query: str, num_results: int = 5) -> str:
    """Internal helper – same logic as the CrewAI tool."""
    try:
        if not _ctx.subject:
            return "Error: no subject configured for vector retrieval."

        from vector_store import VectorStore

        store = None
        try:
            store = VectorStore(rebuild=False, subject=_ctx.subject)
            results = store.semantic_search(query, top_k=num_results)
        finally:
            if store is not None:
                store.close()
        if not results:
            return f"No vector results for query: {query}"

        lines = []
        for text, score, source in results:
            snippet = text.strip().replace("\n", " ")[:300]
            lines.append(f"[{source} | score={score:.3f}] {snippet}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error retrieving from vector store: {e}"


@tool("Retrieve Vector Context")
def retrieve_vector_context(query: str, num_results: int = 5) -> str:
    """Retrieve relevant content from the subject vector store for a query."""
    return _retrieve_vector_context(query, num_results)


@tool("Extract Exam Questions")
def extract_exam_questions(num_questions: int = 5) -> str:
    """Extract exam questions from the ingested document for the active subject."""
    try:
        if _ctx.dialogue_manager is None:
            from agent_a3_dialogue import DialogueManager

            _ctx.dialogue_manager = DialogueManager(
                subject=_ctx.subject,
                rubric_name=_ctx.rubric_name or None,
                extract_images=True,
            )

        visual_only = bool(
            _ctx.dialogue_manager.subject_manager.get_subject_material_path(
                _ctx.subject,
                "visual",
            )
        )
        questions = _ctx.dialogue_manager.extract_questions_from_document(
            num_questions=num_questions,
            visual_only=visual_only,
        )
        return json.dumps(
            [{"id": q["id"], "text": q["text"], "source": q.get("source", "")} for q in questions],
            indent=2,
        )
    except Exception as e:
        return f"Error extracting questions: {e}"


@tool("Apply Rubric Scoring")
def apply_rubric_scoring(question: str, student_response: str) -> str:
    """Score a student response against the active rubric using Agent A5."""
    try:
        from agent_a5_grader import RubricGrader

        if not _ctx.rubric_name:
            return "Error: no rubric configured."

        grader = RubricGrader(rubric_name=_ctx.rubric_name)
        result = grader.generate_tutoring_feedback(
            assignment=question,
            answer=student_response,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error during rubric scoring: {e}"


@tool("Save Assessment Result")
def save_assessment_result(question: str, student_response: str, grading_json: str) -> str:
    """Persist a Q&A turn and grading result to the active session (Agent A6)."""
    try:
        if _ctx.session_manager is None or not _ctx.session_manager.current_session:
            return "No active session – result not persisted."

        _ctx.session_manager.add_turn(speaker="avatar", text=question)
        _ctx.session_manager.add_turn(speaker="student", text=student_response)

        grading = json.loads(grading_json)
        q_num = len(_ctx.session_manager.current_session.scores or []) + 1
        _ctx.session_manager.add_scores([{f"Q{q_num}": grading}])
        return f"Saved Q{q_num} to session {_ctx.session_manager.current_session.session_id}"
    except Exception as e:
        return f"Error saving assessment: {e}"


# ---------------------------------------------------------------------------
# EducationCrew
# ---------------------------------------------------------------------------

class EducationCrew:
    """Orchestrates CrewAI agents on top of the existing assessment infrastructure."""

    def __init__(
        self,
        subject: str,
        rubric_name: str | None = None,
        verbose: bool = True,
        student_id: str = "student_001",
    ):
        self.subject = subject
        self.rubric_name = rubric_name
        self.verbose = verbose
        self.student_id = student_id
        self.session_id: Optional[str] = None

        from agent_a6_session_manager import SessionManager
        from subject_manager import SubjectManager

        self.session_manager = SessionManager()
        self.subject_manager = SubjectManager()
        self.dialogue_manager = None

        model = os.getenv("CREWAI_MODEL", "gpt-3.5-turbo")
        self.llm = ChatOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            model=model,
            temperature=0.7,
        )
        self._setup_agents()

    def _setup_agents(self) -> None:
        self.ingestion_agent = Agent(
            role="PSLE Oral English Document Analyst",
            goal=(
                "Extract PSLE English oral passages, stimulus-based conversation "
                f"prompts, visual stimulus details, and assessor notes for {self.subject}"
            ),
            backstory=(
                "Experienced Singapore primary English oral examiner who identifies "
                "reading-aloud material, purpose/audience/context cues, visual stimulus "
                "details, and conversation opportunities from PSLE-style documents."
            ),
            llm=self.llm,
            verbose=self.verbose,
            allow_delegation=False,
            tools=[extract_document_content, retrieve_vector_context, extract_exam_questions],
        )

        self.question_agent = Agent(
            role="PSLE Oral Prompt Designer",
            goal="Generate PSLE-style English oral conversation prompts aligned with the ingested document",
            backstory=(
                "Primary English oral specialist who creates age-appropriate prompts "
                "that move from observation to personal response, opinion, and reflection."
            ),
            llm=self.llm,
            verbose=self.verbose,
            allow_delegation=False,
            tools=[retrieve_vector_context, extract_exam_questions],
        )

        self.dialogue_agent = Agent(
            role="PSLE Oral English Assessor And Coach",
            goal="Conduct interactive PSLE English oral practice and scaffold students who struggle",
            backstory=(
                "Warm but exam-aware oral assessor who listens carefully, prompts for "
                "clearer ideas, gives sentence starters when needed, and helps Primary 6 "
                "students build confidence without supplying complete answers too early."
            ),
            llm=self.llm,
            verbose=self.verbose,
            allow_delegation=False,
            tools=[retrieve_vector_context],
        )

        self.grading_agent = Agent(
            role="PSLE Oral English Rubric Evaluator",
            goal=f"Score oral English responses against the training rubric: {self.rubric_name}",
            backstory=(
                "Fair, evidence-based evaluator of reading aloud and stimulus-based "
                "conversation responses. Scores are based only on observable student evidence."
            ),
            llm=self.llm,
            verbose=self.verbose,
            allow_delegation=False,
            tools=[apply_rubric_scoring, retrieve_vector_context],
        )

        self.feedback_agent = Agent(
            role="PSLE Oral English Feedback Coach",
            goal="Generate concise, actionable feedback and one next speaking move",
            backstory=(
                "Compassionate Primary 6 English tutor who gives specific spoken feedback, "
                "sentence starters, and one manageable next step for oral improvement."
            ),
            llm=self.llm,
            verbose=self.verbose,
            allow_delegation=False,
        )

    def _get_dialogue_manager(self):
        if self.dialogue_manager is None:
            from agent_a3_dialogue import DialogueManager

            self.dialogue_manager = DialogueManager(
                subject=self.subject,
                rubric_name=self.rubric_name,
                use_sessions=bool(self.session_id),
                extract_images=True,
            )
            if self.session_id and self.session_manager:
                self.dialogue_manager.session_manager = self.session_manager
        return self.dialogue_manager

    def start_session(self, metadata: Optional[Dict] = None) -> str:
        """Create and activate an assessment session via Agent A6."""
        meta = metadata or {}
        meta.update({
            "subject": self.subject,
            "rubric": self.rubric_name,
            "engine": "crewai",
            "assessment_focus": "PSLE English oral practice",
        })
        self.session_id = self.session_manager.create_session(
            paper_id=self.subject,
            student_id=self.student_id,
            metadata=meta,
        )
        self.session_manager.start_session(self.session_id)
        return self.session_id

    def end_session(self) -> bool:
        if not self.session_id:
            return False
        return self.session_manager.end_session(self.session_id)

    def ingest_document(self, file_path: str, material_type: Optional[str] = None) -> Dict[str, Any]:
        """Run the real ingestion pipeline (main.py) without CrewAI."""
        from main import ingest_document

        return ingest_document(
            file_path,
            subject=self.subject,
            rubric=self.rubric_name,
            material_type=material_type,
        )

    def run_ingestion_workflow(
        self,
        file_path: str,
        material_type: Optional[str] = None,
        extract_questions: bool = True,
        run_crew_analysis: bool = True,
    ) -> Dict[str, Any]:
        """
        Full ingestion: real pipeline + question extraction + CrewAI analysis.
        """
        _set_runtime_context(self)

        if self.dialogue_manager is not None:
            try:
                self.dialogue_manager.cleanup()
            except Exception:
                pass
            self.dialogue_manager = None

        ingest_result = self.ingest_document(file_path, material_type=material_type)
        questions = []
        if extract_questions:
            dialogue = self._get_dialogue_manager()
            questions = dialogue.extract_questions_from_document(
                num_questions=10,
                visual_only=(material_type == "visual"),
            )
        else:
            return {
                "workflow": "ingestion",
                "subject": self.subject,
                "file_path": file_path,
                "ingest_result": ingest_result,
                "questions": questions,
                "crew_analysis": "Material ingested. Question extraction was skipped for this upload.",
            }

        if not run_crew_analysis:
            return {
                "workflow": "ingestion",
                "subject": self.subject,
                "file_path": file_path,
                "ingest_result": ingest_result,
                "questions": questions,
                "crew_analysis": (
                    "Question review used the fast ingestion path: the uploaded material was ingested "
                    "and vision-grounded questions were generated without the supplemental CrewAI "
                    "analysis pass."
                ),
            }

        preview = _retrieve_vector_context(
            "PSLE English oral reading aloud stimulus-based conversation prompt picture photograph",
            num_results=3,
        )

        ingestion_task = Task(
            description=(
                f"{PSLE_ORAL_CONTEXT}\n\n"
                f"Analyze the ingested PSLE English oral document for subject '{self.subject}'.\n"
                f"File: {ingest_result['file_path']}\n"
                f"Material type: {material_type or 'general'}\n"
                f"Chunks: {ingest_result['chunk_count']}, Images: {ingest_result['image_count']}\n\n"
                f"Vector context sample:\n{preview}\n\n"
                f"Extracted questions ({len(questions)}):\n"
                f"{json.dumps([q['text'] for q in questions[:5]], indent=2)}\n\n"
                "Summarize: (1) reading-aloud passage or preamble, if present, "
                "(2) stimulus or image context, (3) stimulus-based conversation prompts, "
                "(4) likely oral skills assessed, (5) useful coaching focus areas."
            ),
            agent=self.ingestion_agent,
            expected_output="Structured PSLE oral English analysis of passages, stimuli, prompts, and coaching focus areas",
        )

        question_task = Task(
            description=(
                f"{PSLE_ORAL_CONTEXT}\n\n"
                "Using the ingestion analysis, suggest 3 additional PSLE-style "
                "stimulus-based conversation prompts that complement the extracted ones. "
                "For each: prompt text, expected oral skill, a scaffold for a struggling "
                "student, and a brief strong-response outline."
            ),
            agent=self.question_agent,
            expected_output="3 supplemental PSLE oral prompts with scaffolds and strong-response outlines",
        )

        crew = Crew(
            agents=[self.ingestion_agent, self.question_agent],
            tasks=[ingestion_task, question_task],
            verbose=self.verbose,
        )
        try:
            crew_analysis = str(crew.kickoff())
        except Exception as error:
            crew_analysis = (
                "Supplementary CrewAI analysis was unavailable, but the uploaded material "
                f"and extracted questions were saved. Reason: {error}"
            )

        return {
            "workflow": "ingestion",
            "subject": self.subject,
            "file_path": file_path,
            "ingest_result": ingest_result,
            "questions": questions,
            "crew_analysis": crew_analysis,
        }

    def grade_response(
        self,
        question: str,
        student_response: str,
        visual_context: Optional[str] = None,
        criterion_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Grade using Agent A5 RubricGrader (structured, reliable scores)."""
        from agent_a5_grader import RubricGrader

        if not self.rubric_name:
            raise ValueError("rubric_name is required for grading")

        grader = RubricGrader(rubric_name=self.rubric_name)
        return grader.generate_tutoring_feedback(
            assignment=question,
            answer=student_response,
            visual_context=visual_context,
            criterion_names=criterion_names,
        )

    def get_reading_criterion_names(self) -> List[str]:
        """Return rubric criteria intended for reading-aloud delivery scoring."""
        from rubric_engine import RubricEngine

        if not self.rubric_name:
            return []
        engine = RubricEngine()
        if not engine.load_rubric(self.rubric_name):
            return []
        names = []
        for criterion in engine.current_rubric.get("criteria", []):
            name = str(criterion.get("name", ""))
            description = str(criterion.get("description", ""))
            text = f"{name} {description}".lower()
            if any(
                marker in text
                for marker in (
                    "reading aloud",
                    "oral reading",
                    "pronunciation",
                    "fluency",
                    "articulation",
                    "oral delivery",
                )
            ):
                names.append(name)
        return names

    @staticmethod
    def _is_skipped_response(student_response: str) -> bool:
        return (student_response or "").strip().lower() in {
            "",
            "[skipped]",
            "[skipped question]",
            "skipped",
            "skip",
        }

    def run_assessment_workflow(
        self,
        question: str,
        student_response: str,
        context: Optional[str] = None,
        visual_context: Optional[str] = None,
        save_to_session: bool = True,
        skipped: bool = False,
        audio_path: Optional[str] = None,
        transcription_path: Optional[str] = None,
        delivery_indicators: Optional[Dict[str, Any]] = None,
        criterion_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Hybrid assessment: Agent A5 rubric grading + CrewAI enrichment.
        """
        _set_runtime_context(self)

        is_skipped = skipped or self._is_skipped_response(student_response)
        if is_skipped:
            from agent_a5_grader import RubricGrader

            if not self.rubric_name:
                raise ValueError("rubric_name is required for grading")

            student_response = (student_response or "").strip() or "[Skipped question]"
            grader = RubricGrader(rubric_name=self.rubric_name)
            grading_result = grader.generate_skipped_feedback(
                assignment=question,
                answer=student_response,
                visual_context=visual_context,
                criterion_names=criterion_names,
            )
        else:
            grading_result = self.grade_response(
                question,
                student_response,
                visual_context=visual_context,
                criterion_names=criterion_names,
            )

        if save_to_session and self.session_manager.current_session:
            self.session_manager.add_turn(
                speaker="avatar",
                text=question,
                metadata=(
                    {"visual_context": visual_context}
                    if visual_context
                    else None
                ),
            )
            self.session_manager.add_turn(
                speaker="student",
                text=student_response,
                audio_path=audio_path,
                transcription_path=transcription_path,
                metadata={"status": "skipped"} if is_skipped else None,
            )
            q_num = len(self.session_manager.current_session.scores or []) + 1
            self.session_manager.add_scores([{f"Q{q_num}": grading_result}])

        if is_skipped:
            return {
                "workflow": "assessment",
                "subject": self.subject,
                "rubric": self.rubric_name,
                "session_id": self.session_id,
                "question": question,
                "visual_context": visual_context,
                "student_response": student_response,
                "audio_path": audio_path,
                "transcription_path": transcription_path,
                "delivery_indicators": delivery_indicators,
                "skipped": True,
                "grading_result": grading_result,
                "crew_analysis": (
                    "Question skipped. No oral response evidence was provided, "
                    "so assessed criteria were recorded as 0."
                ),
            }

        grading_summary = json.dumps(
            {
                "total_score": grading_result["total_score"],
                "max_score": grading_result["max_score"],
                "percentage": grading_result["percentage"],
                "criteria": grading_result["scores"],
                "tutoring_feedback": grading_result["tutoring_feedback"],
            },
            indent=2,
        )

        assessment_task = Task(
            description=(
                f"{PSLE_ORAL_CONTEXT}\n\n"
                f"Review this graded PSLE English oral response and add pedagogical insight.\n\n"
                f"QUESTION: {question}\n"
                f"{f'VISUAL STIMULUS FACTS: {visual_context}' if visual_context else ''}\n"
                f"STUDENT RESPONSE: {student_response}\n"
                f"{f'CONTEXT: {context}' if context else ''}\n\n"
                f"RUBRIC GRADING (from Agent A5 – authoritative scores):\n{grading_summary}\n\n"
                "Provide: (1) strengths, (2) oral-response gaps, (3) one scaffolded "
                "follow-up question or sentence starter if the student struggled, "
                "(4) encouragement. Do NOT change the rubric scores."
            ),
            agent=self.dialogue_agent,
            expected_output="PSLE oral English coaching analysis building on rubric scores",
        )

        feedback_task = Task(
            description=(
                f"{PSLE_ORAL_CONTEXT}\n\n"
                f"Based on the rubric grading below, write 120-180 words of oral-practice feedback.\n\n"
                f"{grading_summary}\n\n"
                "Be specific, encouraging, and actionable. Include one short sentence "
                "starter the student can use in the next attempt."
            ),
            agent=self.feedback_agent,
            expected_output="Personalized PSLE oral English feedback with one sentence starter",
        )

        crew = Crew(
            agents=[self.dialogue_agent, self.feedback_agent],
            tasks=[assessment_task, feedback_task],
            verbose=self.verbose,
        )
        try:
            crew_output = str(crew.kickoff())
        except Exception as error:
            crew_output = (
                "Supplementary CrewAI coaching analysis was unavailable. The rubric grade "
                f"was still recorded. Reason: {error}"
            )

        return {
            "workflow": "assessment",
            "subject": self.subject,
            "rubric": self.rubric_name,
            "session_id": self.session_id,
            "question": question,
            "visual_context": visual_context,
            "student_response": student_response,
            "audio_path": audio_path,
            "transcription_path": transcription_path,
            "delivery_indicators": delivery_indicators,
            "skipped": False,
            "grading_result": grading_result,
            "crew_analysis": crew_output,
        }

    def run_oral_assessment(
        self,
        num_questions: int = 5,
        auto_start_session: bool = True,
    ) -> Dict[str, Any]:
        """
        Extract questions from ingested document and grade each via hybrid workflow.
        Intended for programmatic/CLI use with pre-supplied answers via run_assessment_workflow.
        """
        if auto_start_session and not self.session_id:
            self.start_session()

        dialogue = self._get_dialogue_manager()
        visual_only = bool(self.subject_manager.get_subject_material_path(self.subject, "visual"))
        questions = dialogue.extract_questions_from_document(
            num_questions=num_questions,
            visual_only=visual_only,
        )

        return {
            "session_id": self.session_id,
            "subject": self.subject,
            "questions": questions,
            "message": f"Extracted {len(questions)} questions. Use run_assessment_workflow per answer.",
        }

    def run_interactive_dialogue(
        self,
        question: str,
        conversation_history: List[Dict],
    ) -> str:
        """CrewAI dialogue with vector-store context from the ingested document."""
        _set_runtime_context(self)

        context = _retrieve_vector_context(question, num_results=3)

        dialogue_task = Task(
            description=(
                f"{PSLE_ORAL_CONTEXT}\n\n"
                f"Conduct an interactive PSLE English oral coaching turn about: {question}\n\n"
                f"Document context:\n{context}\n\n"
                f"Conversation history:\n{json.dumps(conversation_history, indent=2)}\n\n"
                "Respond in 2-4 short sentences. If the student is stuck, give one "
                "sentence starter or one guiding question. If the student has answered, "
                "ask for one more detail, example, feeling, or reason. Do not give a full model answer."
            ),
            agent=self.dialogue_agent,
            expected_output="Concise PSLE oral coaching response",
        )

        crew = Crew(agents=[self.dialogue_agent], tasks=[dialogue_task], verbose=self.verbose)
        response = str(crew.kickoff())

        if self.session_manager.current_session:
            last = conversation_history[-1] if conversation_history else None
            if last and last.get("role") == "user":
                self.session_manager.add_turn(speaker="student", text=last["content"])
            self.session_manager.add_turn(speaker="avatar", text=response)

        return response

    def evaluate_oral_turn(
        self,
        question: str,
        student_response: str,
        conversation_history: Optional[List[Dict]] = None,
        attempt_number: int = 1,
        max_attempts: int = 3,
    ) -> Dict[str, Any]:
        """
        Decide whether an oral answer is sufficient to grade or needs prompting.

        Returns a structured decision used by the real-time Streamlit oral flow.
        """
        _set_runtime_context(self)

        response = (student_response or "").strip()
        if self._looks_like_struggling_response(response):
            return {
                "accepted": False,
                "status": "struggling",
                "examiner_reply": self._adaptive_follow_up_question(
                    question,
                    response,
                    "The response is empty, very short, or indicates the student is stuck.",
                ),
                "reason": "The response is empty, very short, or indicates the student is stuck.",
                "rubric_focus": ["Stimulus Response Relevance", "Idea Development", "Interaction And Confidence"],
            }

        if os.getenv("FAST_ORAL_TURN_EVALUATION", "true").strip().lower() in {"1", "true", "yes", "on"}:
            return self._fast_oral_turn_decision(question, response, attempt_number, max_attempts)

        context = _retrieve_vector_context(question, num_results=3)
        history = conversation_history or []
        rubric_summary = self._rubric_summary()

        prompt = (
            f"{PSLE_ORAL_CONTEXT}\n\n"
            "You are a real-time PSLE oral examiner. Judge whether the latest "
            "student response is sufficient to pass and move to the next question, "
            "or whether the student is at risk of failing this prompt and needs one "
            "brief hint. Accepted means the answer is passable enough to grade and "
            "continue; it does not mean the answer is excellent.\n\n"
            f"QUESTION: {question}\n"
            f"LATEST STUDENT RESPONSE: {response}\n"
            f"ATTEMPT: {attempt_number} of {max_attempts}\n\n"
            f"DOCUMENT CONTEXT:\n{context}\n\n"
            f"CONVERSATION HISTORY:\n{json.dumps(history, indent=2)}\n\n"
            f"TRAINING RUBRIC:\n{rubric_summary}\n\n"
            "Default to accepting and moving on when the answer is sufficient enough "
            "to pass: it addresses the prompt, contains at least one relevant idea, "
            "and has some connection to the image or oral topic, even if it is brief "
            "or could be improved. Do not ask for extra detail merely to make a fair "
            "answer stronger.\n\n"
            "Only prompt again with one focused follow-up question when the answer is almost a fail: empty, "
            "very short with no clear idea, unrelated to the image/topic, badly "
            "off-topic, impossible to understand, or directly contradicts important "
            "visual facts. If a student gives a wrong visible detail, ask them to "
            "look again and correct that detail. If this is the final attempt, accept "
            "unless there is no meaningful answer.\n\n"
            "If accepted, the examiner_reply should be a short transition such as "
            "'Thank you, let's move on to the next question.' Do not include hints, "
            "sentence starters, or improvement advice when accepted.\n"
            "If not accepted, give exactly one short, concrete follow-up QUESTION. "
            "Make it adaptive to the student's first response like a real oral examiner: "
            "briefly refer to what the student said, then guide the student to clarify, "
            "correct, connect to the picture/topic, give a reason, or add one visible detail. "
            "Do not use generic prompts such as 'Can you add another detail?' unless they are "
            "anchored to the student's answer. Do not give the answer, a full model response, "
            "or a sentence starter.\n\n"
            "Good follow-up style examples:\n"
            "- Student said 'because it is clean': 'You mentioned that it keeps people clean. "
            "Can you explain what might happen if they do not do this before eating?'\n"
            "- Student said 'they are at school': 'You said they are at school. Look at their hands "
            "and the sink: what action are they doing, and why might it matter?'\n\n"
            "Return ONLY valid JSON with this exact shape:\n"
            "{\n"
            '  "accepted": true,\n'
            '  "status": "accepted|needs_prompt|struggling",\n'
            '  "examiner_reply": "one natural examiner response, 1-3 short sentences",\n'
            '  "reason": "brief reason",\n'
            '  "rubric_focus": ["criterion name"]\n'
            "}"
        )

        try:
            raw = self.llm.invoke(prompt).content
            decision = self._parse_json_object(raw)
            accepted = bool(decision.get("accepted"))
            reason = str(decision.get("reason", "")).strip()
            if not accepted and not self._follow_up_is_allowed(response, reason):
                accepted = True
            if attempt_number >= max_attempts and response and decision.get("status") != "struggling":
                accepted = True

            examiner_reply = str(decision.get("examiner_reply", "")).strip()
            if accepted:
                examiner_reply = "Thank you, let's move on to the next question."
            elif not examiner_reply or self._looks_generic_follow_up(examiner_reply):
                examiner_reply = self._adaptive_follow_up_question(question, response, reason)

            return {
                "accepted": accepted,
                "status": "accepted" if accepted else decision.get("status", "needs_prompt"),
                "examiner_reply": examiner_reply,
                "reason": reason,
                "rubric_focus": decision.get("rubric_focus", []),
            }
        except Exception as e:
            return self._fallback_oral_turn_decision(question, response, attempt_number, max_attempts, str(e))

    @staticmethod
    def _follow_up_is_allowed(response: str, reason: str) -> bool:
        """Return whether a first answer is weak enough to justify the one follow-up.

        The live oral flow should not trap a student on the same prompt merely
        because a passable answer could be stronger. A follow-up is reserved for
        near-fail cases: unrelated, contradictory, empty, unclear, or too minimal
        to grade fairly.
        """
        normalized_response = (response or "").strip().lower()
        normalized_reason = (reason or "").strip().lower()
        word_count = len(normalized_response.split())

        if word_count <= 4:
            return True

        hard_prompt_markers = [
            "unrelated",
            "off-topic",
            "off topic",
            "irrelevant",
            "contradict",
            "wrong visible",
            "incorrect visible",
            "no meaningful",
            "empty",
            "very short",
            "impossible to understand",
            "unclear",
            "cannot understand",
            "does not address",
            "fails to address",
        ]
        if any(marker in normalized_reason for marker in hard_prompt_markers):
            return True

        improvement_only_markers = [
            "needs more elaboration",
            "needs elaboration",
            "more elaboration",
            "add another detail",
            "could provide more detail",
            "could be improved",
            "limited elaboration",
            "connection to the visual stimulus",
        ]
        if word_count >= 5 and any(marker in normalized_reason for marker in improvement_only_markers):
            return False

        return False

    def _looks_like_struggling_response(self, response: str) -> bool:
        if len(response.split()) < 4:
            return True
        struggling_markers = [
            "i don't know",
            "i dont know",
            "i do not know",
            "not sure",
            "no idea",
            "cannot",
            "can't answer",
            "help",
            "stuck",
        ]
        lowered = response.lower()
        return any(marker in lowered for marker in struggling_markers)

    def _fast_oral_turn_decision(
        self,
        question: str,
        response: str,
        attempt_number: int,
        max_attempts: int,
    ) -> Dict[str, Any]:
        """Low-latency first-pass decision for demo-speed oral flow."""
        word_count = len(response.split())
        accepted = word_count >= 6 or (attempt_number >= max_attempts and word_count >= 4)
        if accepted:
            return {
                "accepted": True,
                "status": "accepted",
                "examiner_reply": "Thank you, let's move on to the next question.",
                "reason": "Fast oral-turn evaluation accepted a passable-length response.",
                "rubric_focus": ["Stimulus Response Relevance", "Idea Development"],
            }
        return {
            "accepted": False,
            "status": "needs_prompt",
            "examiner_reply": self._adaptive_follow_up_question(
                question,
                response,
                "The response is short and may need one more reason, example, or visible detail.",
            ),
            "reason": "Fast oral-turn evaluation requested guidance for a short response.",
            "rubric_focus": ["Stimulus Response Relevance", "Idea Development", "Interaction And Confidence"],
        }

    @staticmethod
    def _looks_generic_follow_up(reply: str) -> bool:
        normalized = " ".join((reply or "").strip().lower().split())
        if not normalized:
            return True
        generic_markers = [
            "can you add another detail",
            "can you explain more",
            "can you elaborate",
            "tell me more",
            "say more",
            "what can you see in the picture",
            "what is one detail you can see",
            "look at the picture and answer",
        ]
        return any(marker in normalized for marker in generic_markers)

    @staticmethod
    def _student_response_reference(response: str, *, max_words: int = 12) -> str:
        clean = " ".join((response or "").replace("\n", " ").split())
        if not clean:
            return ""
        words = clean.split()
        if len(words) > max_words:
            clean = " ".join(words[:max_words]).rstrip(".,;:") + "..."
        return clean

    def _adaptive_follow_up_question(self, question: str, response: str, reason: str = "") -> str:
        """Build a student-specific guiding question when the model is generic or unavailable."""
        reference = self._student_response_reference(response)
        normalized_reason = (reason or "").lower()

        if not reference:
            return (
                "Take another look at the picture. What is one person, object, or action "
                "you can mention to begin answering this question?"
            )

        if any(marker in normalized_reason for marker in ("unrelated", "off-topic", "off topic", "irrelevant")):
            return (
                f'You mentioned "{reference}". How can you connect that idea back to the picture '
                "and the question being asked?"
            )

        if any(marker in normalized_reason for marker in ("contradict", "wrong visible", "incorrect visible")):
            return (
                f'You mentioned "{reference}". Look carefully at the picture again: what visible '
                "detail might you need to correct or describe more accurately?"
            )

        if any(marker in normalized_reason for marker in ("unclear", "cannot understand", "impossible to understand")):
            return (
                f'I heard "{reference}". Can you say that idea again more clearly and link it to '
                "one detail in the picture?"
            )

        return (
            f'You said "{reference}". Can you add one reason, example, or visible detail from '
            "the picture to explain your answer further?"
        )

    def _fallback_oral_turn_decision(
        self,
        question: str,
        response: str,
        attempt_number: int,
        max_attempts: int,
        error: str,
    ) -> Dict[str, Any]:
        word_count = len(response.split())
        accepted = word_count >= 6 or (attempt_number >= max_attempts and word_count >= 4)
        if accepted:
            reply = "Thank you, let's move on to the next question."
            status = "accepted"
        else:
            reply = self._adaptive_follow_up_question(
                question,
                response,
                "Fallback decision used because LLM judgement failed.",
            )
            status = "needs_prompt"
        return {
            "accepted": accepted,
            "status": status,
            "examiner_reply": reply,
            "reason": f"Fallback decision used because LLM judgement failed: {error[:120]}",
            "rubric_focus": ["Idea Development", "Stimulus Response Relevance"],
        }

    def _rubric_summary(self) -> str:
        try:
            from rubric_engine import RubricEngine

            if not self.rubric_name:
                return "No rubric configured."
            engine = RubricEngine()
            if not engine.load_rubric(self.rubric_name):
                return f"Rubric '{self.rubric_name}' could not be loaded."
            criteria = engine.current_rubric.get("criteria", [])
            return "\n".join(
                f"- {c.get('name', 'Criterion')}: {c.get('description', '')}"
                for c in criteria
            )
        except Exception as e:
            return f"Rubric summary unavailable: {e}"

    def _parse_json_object(self, text: str) -> Dict[str, Any]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start:end + 1])
            raise

    def run_multi_question_assessment(
        self,
        questions_and_responses: List[Dict],
    ) -> Dict[str, Any]:
        if not self.session_id:
            self.start_session()

        assessments = []
        for item in questions_and_responses:
            result = self.run_assessment_workflow(
                question=item["question"],
                student_response=item["response"],
                visual_context=item.get("visual_context"),
                save_to_session=True,
            )
            assessments.append(result)

        return {
            "subject": self.subject,
            "rubric": self.rubric_name,
            "session_id": self.session_id,
            "total_questions": len(questions_and_responses),
            "assessments": assessments,
        }

    def cleanup(self) -> None:
        if self.dialogue_manager:
            self.dialogue_manager.cleanup()
            self.dialogue_manager = None


if __name__ == "__main__":
    crew = EducationCrew(
        subject=DEFAULT_PSLE_SUBJECT,
        rubric_name=DEFAULT_PSLE_RUBRIC,
        verbose=True,
    )
    print("EducationCrew initialized.")
    print(f"  Subject: {crew.subject}")
    print(f"  Rubric:  {crew.rubric_name}")
    print(f"  Model:   {crew.llm.model_name}")
