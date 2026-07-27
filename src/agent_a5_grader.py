"""
Agent A5: Rubric Grader
Generates detailed tutoring feedback based on rubric criteria.
Provides evidence-based, constructive feedback as if a tutor is speaking to the student.
"""

import os
import json
from typing import List, Dict, Optional
from pathlib import Path
from argparse import ArgumentParser
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from rubric_engine import RubricEngine

load_dotenv()


class RubricGrader:
    """Generates tutoring feedback based on rubric criteria."""
    
    def __init__(self, rubric_name: str = None, rubric_dict: Dict = None):
        """
        Initialize grader with a specific rubric.
        
        Args:
            rubric_name: Name of the rubric file to use (string path/name)
            rubric_dict: Direct rubric dictionary (for AI-generated rubrics)
        """
        self.rubric_engine = RubricEngine()
        
        if rubric_dict:
            # Use provided rubric dictionary directly (AI-generated)
            self.rubric_name = rubric_dict.get("name", "custom_rubric")
            self.rubric_engine.current_rubric = rubric_dict
        elif rubric_name:
            # Load rubric from file
            self.rubric_name = rubric_name
            if not self.rubric_engine.load_rubric(rubric_name):
                raise ValueError(f"Could not load rubric: {rubric_name}")
        else:
            raise ValueError("Either rubric_name or rubric_dict must be provided")
        
        self.llm = None
        self.rubric_data = self.rubric_engine.current_rubric

    def _get_llm(self) -> ChatOpenAI:
        if self.llm is None:
            self.llm = ChatOpenAI(
                api_key=os.getenv("OPENAI_API_KEY"),
                model="gpt-3.5-turbo",
                temperature=0.7
            )
        return self.llm

    @staticmethod
    def _is_skipped_or_blank_answer(answer: str) -> bool:
        normalized = (answer or "").strip().lower()
        return normalized in {
            "",
            "[skipped]",
            "[skipped question]",
            "skipped",
            "skip",
        }
    
    def generate_tutoring_feedback(
        self,
        assignment: str,
        answer: str,
        visual_context: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None,
        criterion_names: Optional[List[str]] = None,
    ) -> Dict:
        """
        Generate tutoring feedback as if a teacher/tutor is speaking to the student.
        
        Args:
            assignment: The assignment question or prompt
            answer: The student's response/answer
            visual_context: Optional factual description of the visual stimulus
            conversation_history: Optional oral-practice turns that led to the final answer
            
        Returns:
            Dictionary with tutoring feedback and scores
        """
        if self._is_skipped_or_blank_answer(answer):
            return self.generate_skipped_feedback(
                assignment=assignment,
                answer=answer,
                visual_context=visual_context,
                criterion_names=criterion_names,
            )

        # Score against rubric
        scores = self.rubric_engine.score_answer(
            assignment,
            answer,
            visual_context=visual_context,
            criterion_names=criterion_names,
        )
        
        # Generate natural tutoring feedback
        tutoring_feedback = self._generate_tutoring_speech(
            assignment=assignment,
            answer=answer,
            scores=scores,
            rubric=self.rubric_data,
            visual_context=visual_context,
            conversation_history=conversation_history,
        )
        total_score = sum(s.score for s in scores)
        max_score = sum(s.max_score for s in scores)
        scoring_source = (
            "fallback"
            if any(score.source == "fallback" for score in scores if score.max_score > 0)
            else "ai"
        )
        
        return {
            "assignment": assignment,
            "answer": answer,
            "visual_context": visual_context,
            "scores": [
                {
                    "criterion": s.criterion_name,
                    "score": s.score,
                    "max_score": s.max_score,
                    "feedback": s.feedback,
                    "evidence": s.evidence,
                    "source": s.source,
                }
                for s in scores
            ],
            "tutoring_feedback": tutoring_feedback,
            "total_score": total_score,
            "max_score": max_score,
            "percentage": round((total_score / max_score * 100) if max_score > 0 else 0, 1),
            "scoring_source": scoring_source,
        }

    def generate_skipped_feedback(
        self,
        assignment: str,
        answer: str = "[Skipped question]",
        visual_context: Optional[str] = None,
        criterion_names: Optional[List[str]] = None,
    ) -> Dict:
        """Return deterministic zero scoring when a question is skipped."""
        display_answer = (answer or "").strip() or "[Skipped question]"
        scores = self.rubric_engine.score_answer(
            assignment,
            "",
            visual_context=visual_context,
            criterion_names=criterion_names,
        )
        total_score = sum(s.score for s in scores)
        max_score = sum(s.max_score for s in scores)

        return {
            "assignment": assignment,
            "answer": display_answer,
            "visual_context": visual_context,
            "skipped": True,
            "scores": [
                {
                    "criterion": s.criterion_name,
                    "score": s.score,
                    "max_score": s.max_score,
                    "feedback": s.feedback,
                    "evidence": s.evidence,
                    "source": s.source,
                }
                for s in scores
            ],
            "tutoring_feedback": (
                "This question was skipped, so there was no answer to assess and "
                "the assessed criteria receive 0. Next time, try giving even one "
                "simple observation or reason before moving on."
            ),
            "total_score": total_score,
            "max_score": max_score,
            "percentage": round((total_score / max_score * 100) if max_score > 0 else 0, 1),
            "scoring_source": "deterministic",
        }
    
    def _generate_tutoring_speech(
        self,
        assignment: str,
        answer: str,
        scores: List,
        rubric: Dict,
        visual_context: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None,
    ) -> str:
        """
        Generate natural language tutoring feedback as if a tutor is speaking.
        
        Args:
            assignment: The assignment/question
            answer: Student's answer
            scores: List of RubricScore objects
            rubric: The rubric data
            visual_context: Optional factual description of the visual stimulus
            conversation_history: Optional oral-practice turns that led to the final answer
            
        Returns:
            Natural language tutoring feedback
        """
        # Build rubric context
        visual_text = visual_context.strip() if visual_context else (
            "No separate visual description was provided. Use only visual facts "
            "that appear in the assignment text."
        )
        history_text = ""
        if conversation_history:
            history_text = json.dumps(conversation_history[-6:], indent=2)

        rubric_context = f"""
Tutor profile:
You are Ms Tan, a warm but precise Primary 6 English oral coach.
You have a calm examiner style: friendly, specific, and honest about what needs fixing.
You do not give empty praise, and you never praise a visual detail that conflicts with the stimulus facts.

Assessment/Question:
{assignment}

Visual stimulus facts:
{visual_text}

Student's final answer:
{answer}
"""

        if history_text:
            rubric_context += f"\nRecent oral turns before grading:\n{history_text}\n"

        rubric_context += "\nScoring rubric:\n"
        
        for criterion in rubric.get("criteria", []):
            # Handle both 'max_points' (from auto-generated) and 'max_score' (from old format)
            max_pts = criterion.get('max_points', criterion.get('max_score', 0))
            # Get rubric_levels array and convert to readable format
            rubric_levels = criterion.get('rubric_levels', [])
            if rubric_levels and isinstance(rubric_levels, list):
                levels_text = ", ".join([f"{item.get('level', 'Level')}: {item.get('points', 0)} pts" for item in rubric_levels])
            else:
                levels_text = "See rubric levels"
            rubric_context += f"\n- {criterion['name']}: {criterion.get('description', '')} (Max {max_pts} points)"
            if levels_text:
                rubric_context += f"\n  Levels: {levels_text}"
        
        rubric_context += "\n\nStudent's criterion results:"
        for score in scores:
            if score.max_score == 0:
                score_text = "Not assessed"
            else:
                score_text = f"{score.score}/{score.max_score}"
            evidence_text = f" Evidence: {score.evidence}" if score.evidence else ""
            rubric_context += (
                f"\n- {score.criterion_name}: {score_text}. "
                f"Feedback: {score.feedback}.{evidence_text}"
            )
        
        prompt = ChatPromptTemplate.from_template("""
{rubric_context}

Now generate detailed PSLE English oral practice feedback as if Ms Tan is speaking directly to the student.
Requirements:
- Start with one real strength that is supported by the student's answer.
- If the scores are low or mid-range, keep the praise brief and focus more on the next improvement.
- If the answer conflicts with the visual stimulus facts, clearly and gently name the mismatch.
- Explain the biggest improvement area using the criterion results.
- Give one improved sentence starter or model phrase the student can use next time.
- Mention reading aloud only if it was actually assessed.
- Keep it suitable for an avatar/TTS system: plain text, 5-7 short sentences, no markdown bullets.
- Avoid generic lines like "great job" or "keep up the good work" unless they are tied to specific evidence.
- Do not make the feedback sound better than the marks. Be fair, specific, and slightly strict.
- Do not claim this is an official PSLE score; treat it as practice feedback.

Tutoring Feedback (spoken to student):""")
        
        try:
            chain = prompt | self._get_llm() | StrOutputParser()
            feedback = chain.invoke({"rubric_context": rubric_context})
            return feedback.strip()
        except Exception as error:
            print(f"[WARN] AI tutoring feedback unavailable: {error}")
            assessed = [score for score in scores if score.max_score > 0]
            if not assessed:
                return "No assessable oral-response evidence was recorded for this item."
            strongest = max(assessed, key=lambda score: score.score / score.max_score)
            focus = min(assessed, key=lambda score: score.score / score.max_score)
            return (
                f"Your response was recorded. A live AI coaching message was unavailable, so use the criterion feedback instead. "
                f"Your strongest area was {strongest.criterion_name}: {strongest.feedback} "
                f"Focus next on {focus.criterion_name}: {focus.feedback} "
                "Try adding one specific detail and one reason in your next response."
            )
    
    def grade_assignment(self, assignment_file: str, answer_file: str) -> Dict:
        """
        Grade an assignment from files.
        
        Args:
            assignment_file: Path to assignment question/prompt file
            answer_file: Path to student answer file
            
        Returns:
            Grading result with feedback
        """
        # Load assignment and answer
        with open(assignment_file, 'r', encoding='utf-8') as f:
            assignment = f.read()
        
        with open(answer_file, 'r', encoding='utf-8') as f:
            answer = f.read()
        
        return self.generate_tutoring_feedback(assignment, answer)


def main():
    parser = ArgumentParser(description="Agent A5: Rubric Grader - Generate tutoring feedback")
    parser.add_argument("--answer", type=str, required=True, help="Student answer text")
    parser.add_argument("--assignment", type=str, required=True, help="Assignment/question text")
    parser.add_argument("--rubric", type=str, required=True, help="Rubric name to use for grading")
    args = parser.parse_args()
    
    grader = RubricGrader(rubric_name=args.rubric)
    result = grader.generate_tutoring_feedback(
        assignment=args.assignment,
        answer=args.answer
    )
    
    # Display results
    print("\n" + "="*70)
    print(f"TUTORING FEEDBACK - {args.rubric.upper()}")
    print("="*70)
    print(f"\nAssignment: {result['assignment']}")
    print(f"Your Answer: {result['answer']}\n")
    
    print("SCORE BREAKDOWN:")
    for score in result['scores']:
        print(f"  - {score['criterion']}: {score['score']}/{score['max_score']}")
    
    print(f"\nTotal: {result['total_score']}/{result['max_score']} ({result['percentage']}%)\n")
    
    print("TUTOR'S FEEDBACK:")
    print(f"{result['tutoring_feedback']}\n")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
