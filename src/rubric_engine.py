"""
Rubric Engine - Load and apply scoring rubrics
Handles rubric-based assessment with flexible criteria
"""

import json
import yaml
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class RubricCriterion:
    """Represents a single rubric criterion"""
    name: str
    description: str
    max_score: int
    levels: Dict[int, str]  # {score: description}


@dataclass
class RubricScore:
    """Result of rubric-based scoring"""
    criterion_name: str
    score: int
    max_score: int
    feedback: str
    evidence: Optional[str] = None


class RubricEngine:
    """Manages rubric loading and scoring"""
    
    def __init__(self, rubric_path: Optional[str] = None):
        """
        Initialize rubric engine.
        
        Args:
            rubric_path: Path to rubric file (JSON/YAML) or None to use default
        """
        self.rubric_path = Path(rubric_path) if rubric_path else Path("./data/rubrics")
        self.rubric_path.mkdir(parents=True, exist_ok=True)
        self.current_rubric = None
        self.current_rubric_name = None
    
    def load_rubric(self, rubric_name: str) -> bool:
        """
        Load a rubric by name (without extension).
        Searches for .json or .yaml files.
        
        Args:
            rubric_name: Name of rubric (e.g., "math_primary1", "science_problem_solving")
            
        Returns:
            True if loaded successfully, False otherwise
        """
        # Try JSON first
        json_path = self.rubric_path / f"{rubric_name}.json"
        if json_path.exists():
            try:
                with open(json_path, 'r') as f:
                    self.current_rubric = json.load(f)
                    self.current_rubric_name = rubric_name
                    return True
            except Exception as e:
                print(f"Error loading JSON rubric: {e}")
                return False
        
        # Try YAML
        yaml_path = self.rubric_path / f"{rubric_name}.yaml"
        if yaml_path.exists():
            try:
                with open(yaml_path, 'r') as f:
                    self.current_rubric = yaml.safe_load(f)
                    self.current_rubric_name = rubric_name
                    return True
            except Exception as e:
                print(f"Error loading YAML rubric: {e}")
                return False
        
        print(f"Rubric '{rubric_name}' not found in {self.rubric_path}")
        return False
    
    def list_available_rubrics(self) -> List[str]:
        """List all available rubrics"""
        rubrics = set()
        for file in self.rubric_path.glob("*.json"):
            rubrics.add(file.stem)
        for file in self.rubric_path.glob("*.yaml"):
            rubrics.add(file.stem)
        return sorted(list(rubrics))
    
    def score_answer(self, question: str, answer: str, 
                    criterion_name: Optional[str] = None) -> List[RubricScore]:
        """
        Score an answer against the loaded rubric.
        
        Args:
            question: The question asked
            answer: Student's answer
            criterion_name: Optional specific criterion to score (if None, score all)
            
        Returns:
            List of RubricScore objects
        """
        if not self.current_rubric:
            raise ValueError("No rubric loaded. Call load_rubric() first.")
        
        scores = []
        
        # Get criteria to evaluate
        criteria = self.current_rubric.get("criteria", [])
        if not criteria:
            raise ValueError("Rubric has no criteria defined")
        
        for criterion in criteria:
            if criterion_name and criterion.get("name") != criterion_name:
                continue
            
            name = criterion.get("name", "Unknown")
            description = criterion.get("description", "")
            # Handle both 'max_points' (from auto-generated) and 'max_score' (from old format)
            max_score = criterion.get("max_points", criterion.get("max_score", 10))
            # Handle both 'rubric_levels' and 'levels' keys
            levels = criterion.get("rubric_levels", criterion.get("levels", {}))
            
            # Score using LLM with question context
            score = self._score_criterion(question, answer, description, levels, max_score)
            
            # Generate feedback - handle both list and dict formats for levels
            if isinstance(levels, list):
                # List format - find matching level description
                feedback = f"Score: {score}/{max_score}"
                for level_item in levels:
                    if isinstance(level_item, dict) and level_item.get("points") == score:
                        feedback = level_item.get("description", feedback)
                        break
            else:
                # Dict format - use the dict
                feedback = levels.get(str(score), f"Score: {score}/{max_score}") if levels else f"Score: {score}/{max_score}"
            
            scores.append(RubricScore(
                criterion_name=name,
                score=score,
                max_score=max_score,
                feedback=feedback,
                evidence=answer[:100]  # First 100 chars as evidence
            ))
        
        return scores
    
    def _score_criterion(self, question: str, answer: str, description: str, 
                        levels: Dict, max_score: int) -> int:
        """
        Score based on criterion using LLM semantic evaluation.
        Evaluates if the answer meets the criterion, not just length.
        Handles both dict format {score: description} and array format [{"points": x, "description": "..."}]
        """
        if not answer or len(answer.strip()) == 0:
            return 0
        
        # Normalize levels to dict format if it's an array
        if isinstance(levels, list):
            # Convert array format to dict: {points: description}
            normalized_levels = {}
            for item in levels:
                if isinstance(item, dict):
                    points = item.get("points", 0)
                    desc = item.get("description", "")
                    if points > 0:
                        normalized_levels[points] = desc
            levels_dict = normalized_levels if normalized_levels else {max_score: "Excellent"}
        else:
            levels_dict = levels if levels else {max_score: "Excellent"}
        
        # Use LLM to evaluate answer quality based on criterion
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.prompts import ChatPromptTemplate
            from langchain_core.output_parsers import StrOutputParser
            from dotenv import load_dotenv
            import os
            
            load_dotenv()
            
            llm = ChatOpenAI(
                api_key=os.getenv("OPENAI_API_KEY"),
                model="gpt-3.5-turbo",
                temperature=0.2
            )
            
            # Build level descriptions from normalized dict
            level_descriptions = "\n".join([f"  {k}: {v}" for k, v in sorted(levels_dict.items())])
            
            evaluation_prompt = ChatPromptTemplate.from_template("""
Evaluate this student answer.

Question: {question}
Student's answer: {answer}

Evaluation criterion: {criterion}

Score levels:
{levels}

Choose the score that best matches how well the answer addresses this criterion. Reply with ONLY the score number.
""")
            
            chain = evaluation_prompt | llm | StrOutputParser()
            
            result = chain.invoke({
                "question": question,
                "answer": answer,
                "criterion": description,
                "levels": level_descriptions
            })
            
            # Extract the number from result
            import re
            result_clean = result.strip()
            
            # Try to find a number in the response
            numbers = re.findall(r'\b(\d+)\b', result_clean)
            
            if numbers:
                score = int(numbers[0])  # Take first number found
                return min(score, max_score)
            else:
                # If no number found, fallback to 50%
                return max_score // 2
                
        except Exception as e:
            print(f"LLM evaluation error: {e}")
            # Fallback: If answer exists, give 50% score
            return max_score // 2
    
    def generate_rubric_template(self, rubric_name: str, 
                                criteria_count: int = 3) -> Dict:
        """
        Generate a rubric template for creation.
        
        Args:
            rubric_name: Name of the rubric
            criteria_count: Number of evaluation criteria
            
        Returns:
            Dictionary template
        """
        template = {
            "name": rubric_name,
            "description": "Assessment rubric for evaluating student responses",
            "criteria": []
        }
        
        for i in range(1, criteria_count + 1):
            criterion = {
                "name": f"Criterion {i}",
                "description": "Description of what this criterion evaluates",
                "max_score": 10,
                "levels": {
                    "0": "No attempt or incorrect",
                    "5": "Partial understanding",
                    "8": "Good understanding",
                    "10": "Excellent understanding"
                }
            }
            template["criteria"].append(criterion)
        
        return template
    
    def save_rubric(self, rubric_name: str, rubric_data: Dict, 
                   format: str = "json") -> bool:
        """
        Save a rubric to file.
        
        Args:
            rubric_name: Name of rubric
            rubric_data: Rubric dictionary
            format: 'json' or 'yaml'
            
        Returns:
            True if successful
        """
        try:
            if format == "json":
                path = self.rubric_path / f"{rubric_name}.json"
                with open(path, 'w') as f:
                    json.dump(rubric_data, f, indent=2)
            elif format == "yaml":
                path = self.rubric_path / f"{rubric_name}.yaml"
                with open(path, 'w') as f:
                    yaml.dump(rubric_data, f, default_flow_style=False)
            else:
                raise ValueError("Format must be 'json' or 'yaml'")
            
            print(f"Rubric saved to {path}")
            return True
        except Exception as e:
            print(f"Error saving rubric: {e}")
            return False
