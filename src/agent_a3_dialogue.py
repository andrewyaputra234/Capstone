"""
Agent A3: Dialogue Manager
Extracts actual exam questions from ingested documents and manages Q&A dialogue flow.
Uses rubric-based assessment for scoring student responses.
"""

import os
import re
import json
from typing import List, Dict
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from subject_manager import SubjectManager
from rubric_engine import RubricEngine

load_dotenv()

class DialogueManager:
    """Manages oral assessment using actual extracted exam questions and rubric-based scoring."""
    
    def __init__(self, subject: str | None = None, rubric_name: str | None = None):
        """
        Initialize dialogue manager.
        
        Args:
            subject: Subject/topic name for multi-subject organization
            rubric_name: Name of rubric to use for scoring
        """
        self.subject = subject
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


def interactive_assessment(subject: str | None = None, rubric_name: str | None = None):
    """Run interactive assessment mode"""
    subject_label = f" [{subject}]" if subject else ""
    print("\n" + "="*60)
    print(f"🎓 Oral Assessment System - Agent A3 (Dialogue Manager){subject_label}")
    print("="*60 + "\n")
    
    # Initialize
    dialogue = DialogueManager(subject=subject, rubric_name=rubric_name)
    
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
        
        answer = input("Your answer: ").strip()
        
        if not answer:
            print("Please provide an answer.\n")
            continue
        
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
    args = parser.parse_args()
    
    interactive_assessment(subject=args.subject, rubric_name=args.rubric)
