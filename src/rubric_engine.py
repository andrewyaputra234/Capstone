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
            max_score = criterion.get("max_score", 10)
            levels = criterion.get("levels", {})
            
            # Score using LLM (you can implement scoring logic here)
            # For now, placeholder
            score = self._score_criterion(answer, description, levels, max_score)
            feedback = levels.get(str(score), f"Score: {score}/{max_score}")
            
            scores.append(RubricScore(
                criterion_name=name,
                score=score,
                max_score=max_score,
                feedback=feedback,
                evidence=answer[:100]  # First 100 chars as evidence
            ))
        
        return scores
    
    def _score_criterion(self, answer: str, description: str, 
                        levels: Dict, max_score: int) -> int:
        """
        Score based on criterion. 
        This is a placeholder - can be enhanced with LLM scoring.
        """
        # Simple heuristic: check if answer is empty
        if not answer or len(answer.strip()) == 0:
            return 0
        
        # Check answer length as proxy for effort
        answer_length = len(answer.split())
        
        if answer_length < 3:
            return max(0, max_score // 4)  # 25%
        elif answer_length < 10:
            return max(0, max_score // 2)  # 50%
        elif answer_length < 50:
            return max(0, (max_score * 3) // 4)  # 75%
        else:
            return max_score  # Full score
    
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
