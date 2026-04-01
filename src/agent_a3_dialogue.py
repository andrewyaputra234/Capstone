"""
Agent A3: Dialogue Manager
Generates questions from ingested documents and manages Q&A dialogue flow.
"""

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import random

load_dotenv()

class DialogueManager:
    """Manages oral assessment dialogue and question generation."""
    
    def __init__(self, chroma_db_path="./data/chroma_db"):
        """Initialize dialogue manager with vector store and LLM."""
        self.chroma_db_path = chroma_db_path
        self.embedding_function = OpenAIEmbeddings(
            api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # Initialize LLM for question generation and feedback
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
        
        # Conversation history
        self.conversation_history = []
        self.current_topic = None
        self.asked_questions = []
        
    def generate_initial_questions(self, num_questions=5):
        """
        Generate initial set of questions based on document content.
        
        Args:
            num_questions: Number of questions to generate
            
        Returns:
            List of question objects with metadata
        """
        print(f"\n📚 Generating {num_questions} initial questions from document...\n")
        
        # Get random insights from the document
        retriever = self.vector_store.as_retriever(search_kwargs={"k": 3})
        general_docs = retriever.invoke("project overview objectives goals")
        
        questions = []
        for i, doc in enumerate(general_docs[:min(3, len(general_docs))]):
            # Generate questions from these chunks
            prompt = ChatPromptTemplate.from_template(
                """Based on this document excerpt, generate 2 unique, assessment-style questions 
                that a graduate examiner would ask during an oral defense. 
                Make questions thoughtful and require detailed explanations.
                
                Document excerpt:
                {content}
                
                Return ONLY the questions, numbered 1. and 2., one per line."""
            )
            
            chain = prompt | self.llm | StrOutputParser()
            response = chain.invoke({"content": doc.page_content[:500]})
            
            # Parse questions
            for line in response.strip().split('\n'):
                if line.strip() and any(c.isalpha() for c in line):
                    # Clean up the question
                    question_text = line.replace('1.', '').replace('2.', '').strip()
                    if question_text and len(question_text) > 10:
                        questions.append({
                            'id': len(questions) + 1,
                            'text': question_text,
                            'source_chunk': doc.metadata.get('source', 'Unknown'),
                            'answered': False,
                            'answer': None,
                            'score': None
                        })
        
        # If we don't have enough questions, add some generic ones
        if len(questions) < num_questions:
            generic_questions = [
                "What is the main objective of your project?",
                "How does your system architecture work?",
                "What are the key components and agents in your system?",
                "What technical challenges did you face and how did you solve them?",
                "What are the future improvements for your system?",
            ]
            for q in generic_questions[: num_questions - len(questions)]:
                questions.append({
                    'id': len(questions) + 1,
                    'text': q,
                    'source_chunk': 'General',
                    'answered': False,
                    'answer': None,
                    'score': None
                })
        
        self.asked_questions = questions[:num_questions]
        return questions[:num_questions]
    
    def ask_next_question(self):
        """
        Get the next unanswered question.
        
        Returns:
            Question object or None if all answered
        """
        for question in self.asked_questions:
            if not question['answered']:
                return question
        return None
    
    def receive_answer(self, question_id, student_answer):
        """
        Record student's answer and generate feedback.
        
        Args:
            question_id: ID of the question being answered
            student_answer: Student's response text
            
        Returns:
            Feedback object with score and comments
        """
        # Find the question
        question = None
        for q in self.asked_questions:
            if q['id'] == question_id:
                question = q
                break
        
        if not question:
            return {"error": "Question not found"}
        
        # Store answer
        question['answer'] = student_answer
        question['answered'] = True
        
        # Generate feedback using LLM
        feedback = self._generate_feedback(question, student_answer)
        question['score'] = feedback['score']
        
        return feedback
    
    def _generate_feedback(self, question, answer):
        """
        Generate feedback and score for student answer.
        
        Args:
            question: Question object
            answer: Student's answer
            
        Returns:
            Feedback object with score and comments
        """
        # Retrieve relevant context from document
        retriever = self.vector_store.as_retriever(search_kwargs={"k": 2})
        context_docs = retriever.invoke(question['text'])
        context = "\n".join([doc.page_content for doc in context_docs])
        
        # Generate feedback prompt
        prompt = ChatPromptTemplate.from_template(
            """You are an expert academic examiner. Score the student's answer on a scale of 1-10.

Question: {question}
Student Answer: {answer}

Document Reference:
{context}

Provide:
1. Score (1-10)
2. Strengths in the answer
3. Areas for improvement
4. Brief comment

Format your response as:
SCORE: [number]
STRENGTHS: [text]
IMPROVEMENTS: [text]
COMMENT: [text]"""
        )
        
        chain = prompt | self.llm | StrOutputParser()
        response = chain.invoke({
            "question": question['text'],
            "answer": answer,
            "context": context[:1000]
        })
        
        # Parse response
        feedback = {
            'question_id': question['id'],
            'student_answer': answer,
            'score': 7,  # Default
            'strengths': '',
            'improvements': '',
            'comment': ''
        }
        
        try:
            for line in response.split('\n'):
                if line.startswith('SCORE:'):
                    score_text = line.replace('SCORE:', '').strip()
                    feedback['score'] = int(''.join(filter(str.isdigit, score_text.split('/')[0])))
                elif line.startswith('STRENGTHS:'):
                    feedback['strengths'] = line.replace('STRENGTHS:', '').strip()
                elif line.startswith('IMPROVEMENTS:'):
                    feedback['improvements'] = line.replace('IMPROVEMENTS:', '').strip()
                elif line.startswith('COMMENT:'):
                    feedback['comment'] = line.replace('COMMENT:', '').strip()
        except Exception as e:
            feedback['comment'] = response[:200]
        
        return feedback
    
    def get_dialogue_context(self):
        """Get current dialogue state and history."""
        return {
            'total_questions': len(self.asked_questions),
            'answered_count': sum(1 for q in self.asked_questions if q['answered']),
            'conversation_history': self.conversation_history,
            'questions': self.asked_questions
        }
    
    def generate_session_report(self):
        """Generate assessment report for this session."""
        if not self.asked_questions:
            return {"error": "No questions asked yet"}
        
        total_score = sum(q.get('score', 0) for q in self.asked_questions if q['answered'])
        answered = sum(1 for q in self.asked_questions if q['answered'])
        
        report = {
            'total_questions': len(self.asked_questions),
            'answered_questions': answered,
            'total_score': total_score,
            'average_score': total_score / answered if answered > 0 else 0,
            'responses': []
        }
        
        for q in self.asked_questions:
            if q['answered']:
                report['responses'].append({
                    'question': q['text'],
                    'answer': q['answer'],
                    'score': q['score']
                })
        
        return report


def interactive_assessment():
    """Interactive assessment mode."""
    print("\n" + "="*60)
    print("🎓 Oral Assessment System - Agent A3 (Dialogue Manager)")
    print("="*60 + "\n")
    
    # Initialize dialogue manager
    dialogue = DialogueManager()
    
    # Generate questions
    questions = dialogue.generate_initial_questions(num_questions=5)
    print(f"Generated {len(questions)} questions:\n")
    for q in questions:
        print(f"{q['id']}. {q['text']}\n")
    
    # Assessment loop
    while True:
        next_q = dialogue.ask_next_question()
        
        if not next_q:
            print("\n✅ All questions answered! Generating report...\n")
            report = dialogue.generate_session_report()
            print(f"Session Summary:")
            print(f"  - Total Questions: {report['total_questions']}")
            print(f"  - Answered: {report['answered_questions']}")
            print(f"  - Average Score: {report['average_score']:.1f}/10\n")
            break
        
        print(f"\n❓ Question {next_q['id']}/{len(dialogue.asked_questions)}:")
        print(f"{next_q['text']}\n")
        
        answer = input("Your answer: ").strip()
        
        if answer.lower() in ['skip', 'next']:
            print("Skipping this question...")
            continue
        
        if not answer:
            print("Please provide an answer.")
            continue
        
        # Get feedback
        print("\n⏳ Generating feedback...\n")
        feedback = dialogue.receive_answer(next_q['id'], answer)
        
        print(f"Score: {feedback['score']}/10")
        print(f"Strengths: {feedback['strengths']}")
        print(f"Improvements: {feedback['improvements']}")
        print(f"Comment: {feedback['comment']}\n")
        
        print("-" * 60)


if __name__ == "__main__":
    interactive_assessment()
