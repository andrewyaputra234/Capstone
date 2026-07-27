"""
Rubric Engine - Load and apply scoring rubrics
Handles rubric-based assessment with flexible criteria
"""

import json
import re
import yaml
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
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
    source: str = "ai"


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
    
    def score_answer(
        self,
        question: str,
        answer: str,
        criterion_name: Optional[str] = None,
        criterion_names: Optional[List[str]] = None,
        visual_context: Optional[str] = None,
    ) -> List[RubricScore]:
        """
        Score an answer against the loaded rubric.
        
        Args:
            question: The question asked
            answer: Student's answer
            criterion_name: Optional specific criterion to score (if None, score all)
            criterion_names: Optional list of criteria to score; useful when an
                assessment step is intentionally limited to a rubric component.
            visual_context: Optional factual description of the visual stimulus
            
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
            if criterion_names and criterion.get("name") not in criterion_names:
                continue
            
            name = criterion.get("name", "Unknown")
            description = criterion.get("description", "")
            # Handle both 'max_points' (from auto-generated) and 'max_score' (from old format)
            max_score = criterion.get("max_points", criterion.get("max_score", 10))
            # Handle both 'rubric_levels' and 'levels' keys
            levels = criterion.get("rubric_levels", criterion.get("levels", {}))
            
            if self._should_skip_reading_aloud(name, description, question, visual_context):
                scores.append(RubricScore(
                    criterion_name=name,
                    score=0,
                    max_score=0,
                    feedback=(
                        "Not assessed for this stimulus-based response because no "
                        "reading-aloud or audio delivery evidence was provided."
                    ),
                    evidence=None,
                    source="not_assessed",
                ))
                continue
            
            evaluation = self._evaluate_criterion(
                question=question,
                answer=answer,
                criterion_name=name,
                description=description,
                levels=levels,
                max_score=max_score,
                visual_context=visual_context,
            )
            score = evaluation["score"]
            visual_mismatch = self._detect_visual_color_mismatch(
                answer=answer,
                visual_context=visual_context or question,
            )
            if visual_mismatch and self._is_visual_accuracy_criterion(name, description):
                score_cap = self._score_at_or_below(max_score // 2, levels, max_score)
                if score > score_cap:
                    score = score_cap
                evaluation["feedback"] = (
                    f"{visual_mismatch}. This makes the response only partly relevant; "
                    "check the picture carefully and correct that detail."
                )
                evaluation["evidence"] = visual_mismatch

            strict_cap = self._strict_score_cap(
                answer=answer,
                criterion_name=name,
                description=description,
                levels=levels,
                max_score=max_score,
                question=question,
                visual_context=visual_context,
            )
            if strict_cap:
                score_cap, cap_reason = strict_cap
                if score > score_cap:
                    score = score_cap
                    evaluation["feedback"] = cap_reason
                    evaluation["evidence"] = self._short_answer_evidence(answer)
            
            # Generate feedback - handle both list and dict formats for levels
            feedback = evaluation.get("feedback") or self._level_feedback(levels, score, max_score)
            
            scores.append(RubricScore(
                criterion_name=name,
                score=score,
                max_score=max_score,
                feedback=feedback,
                evidence=evaluation.get("evidence") or answer[:100],
                source=evaluation.get("source", "ai"),
            ))
        
        return scores
    
    def _score_criterion(
        self,
        question: str,
        answer: str,
        description: str,
        levels: Dict,
        max_score: int,
        criterion_name: str = "Criterion",
        visual_context: Optional[str] = None,
    ) -> int:
        """
        Score based on criterion using LLM semantic evaluation.
        Evaluates if the answer meets the criterion, not just length.
        Handles both dict format {score: description} and array format [{"points": x, "description": "..."}]
        """
        return self._evaluate_criterion(
            question=question,
            answer=answer,
            criterion_name=criterion_name,
            description=description,
            levels=levels,
            max_score=max_score,
            visual_context=visual_context,
        )["score"]
    
    def _evaluate_criterion(
        self,
        question: str,
        answer: str,
        criterion_name: str,
        description: str,
        levels: Dict,
        max_score: int,
        visual_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Evaluate a criterion and return a score with evidence-based feedback."""
        if not answer or len(answer.strip()) == 0:
            return {
                "score": 0,
                "feedback": "No answer was provided for this criterion.",
                "evidence": None,
            }
        
        levels_dict = self._normalize_levels(levels, max_score)
        allowed_scores = sorted(levels_dict.keys())
        
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
            allowed_text = ", ".join(str(score) for score in allowed_scores)
            visual_text = visual_context.strip() if visual_context else "Not provided."
            
            evaluation_prompt = ChatPromptTemplate.from_template("""
Evaluate one rubric criterion for this student answer.

Assessment question/context:
{question}

Visual stimulus facts, if any:
{visual_context}

Student's answer:
{answer}

Criterion name: {criterion_name}
Evaluation criterion: {criterion}

Score levels:
{levels}

Allowed score numbers: {allowed_scores}

Important:
- Choose only one of the allowed score numbers.
- Base the score on observable evidence in the student's answer.
- Mark as a strict PSLE-style oral examiner, not a generous tutor. Start from the lower matching band and move up only when the answer clearly earns it.
- Do not give the highest score unless the answer fully satisfies the top-band descriptor with specific evidence.
- Short, generic, repeated, or unsupported answers must stay in the lower or middle bands even if they are on-topic.
- A one-sentence answer with little elaboration should not receive high Idea Development marks.
- A response that does not clearly answer the question should not receive high Relevance marks.
- Understandable but grammatically weak or fragmented spoken English should not receive high Language marks.
- For visual stimulus questions, compare the answer to the visual facts. If the answer directly contradicts a visible fact, lower the relevant score and mention the mismatch.
- Do not invent visual facts. If no visual facts are provided, say the answer needs more detail rather than claiming it is visually wrong.
- Do not reward reading-aloud delivery, pronunciation, fluency, or expression unless actual audio/delivery evidence is provided.
- Feedback must be one specific sentence that explains why this score was chosen and names one concrete next step when useful.

Return ONLY valid JSON with this shape:
{{"score": 0, "feedback": "specific criterion feedback", "evidence": "short evidence from the answer"}}
""")
            
            chain = evaluation_prompt | llm | StrOutputParser()
            
            result = chain.invoke({
                "question": question,
                "answer": answer,
                "criterion_name": criterion_name,
                "criterion": description,
                "levels": level_descriptions,
                "allowed_scores": allowed_text,
                "visual_context": visual_text,
            })
            
            parsed = self._parse_json_object(result)
            raw_score = int(parsed.get("score", max_score // 2))
            score = self._nearest_allowed_score(raw_score, allowed_scores, max_score)
            feedback = str(parsed.get("feedback") or "").strip()
            evidence = str(parsed.get("evidence") or "").strip()

            return {
                "score": score,
                "feedback": feedback or self._level_feedback(levels, score, max_score),
                "evidence": evidence or answer[:100],
                "source": "ai",
            }
                
        except Exception as e:
            print(f"LLM evaluation error: {e}")
            score = self._nearest_allowed_score(max_score // 2, allowed_scores, max_score)
            return {
                "score": score,
                "feedback": self._level_feedback(levels, score, max_score),
                "evidence": answer[:100],
                "source": "fallback",
            }
    
    def _normalize_levels(self, levels: Dict, max_score: int) -> Dict[int, str]:
        """Normalize supported rubric level formats to {points: description}."""
        if isinstance(levels, list):
            normalized = {}
            for item in levels:
                if isinstance(item, dict):
                    try:
                        points = int(item.get("points", 0))
                    except (TypeError, ValueError):
                        continue
                    normalized[points] = str(item.get("description", "")).strip()
            return normalized if normalized else {0: "No evidence", max_score: "Excellent"}

        if isinstance(levels, dict):
            normalized = {}
            for points, desc in levels.items():
                try:
                    normalized[int(points)] = str(desc).strip()
                except (TypeError, ValueError):
                    continue
            return normalized if normalized else {0: "No evidence", max_score: "Excellent"}

        return {0: "No evidence", max_score: "Excellent"}
    
    def _nearest_allowed_score(self, score: int, allowed_scores: List[int], max_score: int) -> int:
        """Clamp a model score to the closest rubric-supported point value."""
        if not allowed_scores:
            return max(0, min(score, max_score))
        clamped = max(0, min(score, max_score))
        return min(allowed_scores, key=lambda allowed: (abs(allowed - clamped), allowed))
    
    def _level_feedback(self, levels: Dict, score: int, max_score: int) -> str:
        """Find the rubric-level description for a selected score."""
        levels_dict = self._normalize_levels(levels, max_score)
        return levels_dict.get(score, f"Score: {score}/{max_score}")
    
    def _score_at_or_below(self, target: int, levels: Dict, max_score: int) -> int:
        """Pick the highest allowed rubric score that is no higher than target."""
        allowed_scores = sorted(self._normalize_levels(levels, max_score).keys())
        lower_or_equal = [score for score in allowed_scores if score <= target]
        if lower_or_equal:
            return max(lower_or_equal)
        return min(allowed_scores) if allowed_scores else max(0, min(target, max_score))

    def _strict_score_cap(
        self,
        *,
        answer: str,
        criterion_name: str,
        description: str,
        levels: Dict,
        max_score: int,
        question: str,
        visual_context: Optional[str],
    ) -> Optional[Tuple[int, str]]:
        """Apply conservative ceilings before accepting an AI-generated score."""
        if max_score <= 0:
            return None

        normalized_answer = self._normalize_answer_for_caps(answer)
        words = re.findall(r"[a-zA-Z0-9']+", normalized_answer)
        word_count = len(words)
        criterion_text = f"{criterion_name} {description}".lower()
        is_reading = self._is_reading_delivery_criterion(criterion_text)
        category = self._strict_criterion_category(criterion_text)

        if word_count == 0:
            return self._score_at_or_below(0, levels, max_score), "No answer was provided for this criterion."

        if not is_reading and word_count < 5:
            return (
                self._score_at_or_below(max(1, max_score // 3), levels, max_score),
                "The response is too brief to show clear understanding, elaboration, or confident spoken interaction.",
            )

        if category == "relevance":
            if self._is_generic_or_minimal_answer(normalized_answer) or word_count < 10:
                return (
                    self._score_at_or_below(max_score // 2, levels, max_score),
                    "The response is relevant only at a basic level and needs a clearer answer with specific details.",
                )
            if visual_context and not self._mentions_enough_context(normalized_answer, question, visual_context):
                return (
                    self._score_at_or_below(max_score - max(1, max_score // 4), levels, max_score),
                    "The response answers generally but does not use enough specific detail from the question or stimulus for a top score.",
                )

        if category == "ideas":
            if word_count < 16:
                return (
                    self._score_at_or_below(max_score // 2, levels, max_score),
                    "The idea is too brief for a high development score; it needs explanation, examples, or a clearer reason.",
                )
            if word_count < 30 and not self._has_reason_or_example(normalized_answer):
                return (
                    self._score_at_or_below(max_score // 2, levels, max_score),
                    "The answer gives a point but does not develop it with a clear reason, example, or explanation.",
                )

        if category == "language":
            if word_count < 8:
                return (
                    self._score_at_or_below(max_score // 2, levels, max_score),
                    "There is too little spoken language evidence to award a high language score.",
                )
            if self._has_fragmented_language(normalized_answer):
                return (
                    self._score_at_or_below(max_score // 2, levels, max_score),
                    "Frequent fragmented or unclear phrasing limits the language score even though some meaning is understandable.",
                )

        if category == "interaction":
            if word_count < 8:
                return (
                    self._score_at_or_below(max(1, max_score // 3), levels, max_score),
                    "The response is too short or dependent to show strong interaction and confidence.",
                )
            if word_count < 16:
                return (
                    self._score_at_or_below(max_score - 1, levels, max_score),
                    "The response shows some engagement but is too brief for full interaction and confidence marks.",
                )

        if is_reading and word_count < 20:
            return (
                self._score_at_or_below(max_score // 2, levels, max_score),
                "The reading evidence is too short or incomplete to justify a high reading-aloud score.",
            )

        return None

    def _normalize_answer_for_caps(self, answer: str) -> str:
        cleaned = re.sub(r"\b(first response|response after guidance|examiner guidance)\s*:", " ", answer or "", flags=re.I)
        cleaned = re.sub(r"\[[^\]]+\]", " ", cleaned)
        return " ".join(cleaned.split()).lower()

    def _strict_criterion_category(self, criterion_text: str) -> str:
        if any(marker in criterion_text for marker in ("stimulus", "relevance", "visual", "picture")):
            return "relevance"
        if any(marker in criterion_text for marker in ("idea", "development", "elaboration", "reason", "example")):
            return "ideas"
        if any(marker in criterion_text for marker in ("language", "grammar", "vocabulary", "sentence")):
            return "language"
        if any(marker in criterion_text for marker in ("interaction", "confidence", "responsive", "engagement")):
            return "interaction"
        return "other"

    def _is_reading_delivery_criterion(self, criterion_text: str) -> bool:
        return any(
            marker in criterion_text
            for marker in ("reading aloud", "oral reading", "pronunciation", "fluency", "expression", "delivery")
        )

    def _is_generic_or_minimal_answer(self, answer: str) -> bool:
        generic_patterns = [
            r"\bi (?:do not|don't) know\b",
            r"\bnot sure\b",
            r"\bi think (?:it )?is (?:good|nice|fun|bad|important)\b",
            r"\bit is (?:good|nice|fun|bad|important)\b",
            r"\bbecause (?:it )?is (?:good|nice|fun|bad|important)\b",
        ]
        return any(re.search(pattern, answer) for pattern in generic_patterns)

    def _has_reason_or_example(self, answer: str) -> bool:
        return bool(
            re.search(
                r"\b(because|since|so that|therefore|for example|for instance|such as|this shows|this means|if|when|as a result)\b",
                answer,
            )
        )

    def _has_fragmented_language(self, answer: str) -> bool:
        words = re.findall(r"[a-zA-Z0-9']+", answer)
        if len(words) < 12:
            return False
        repeated_fillers = len(re.findall(r"\b(um|uh|erm|like|then then|and and)\b", answer))
        sentence_like = len(re.findall(r"\b(i|we|they|he|she|it|there|this|that)\b", answer))
        return repeated_fillers >= 3 or sentence_like == 0

    def _mentions_enough_context(self, answer: str, question: str, visual_context: str) -> bool:
        source_text = f"{question} {visual_context}".lower()
        answer_words = set(re.findall(r"[a-zA-Z]{4,}", answer))
        source_words = {
            word
            for word in re.findall(r"[a-zA-Z]{4,}", source_text)
            if word not in {
                "what",
                "where",
                "when",
                "which",
                "this",
                "that",
                "they",
                "them",
                "with",
                "from",
                "about",
                "because",
                "question",
                "picture",
                "visual",
                "student",
                "answer",
            }
        }
        return len(answer_words & source_words) >= 2

    def _short_answer_evidence(self, answer: str) -> str:
        cleaned = " ".join((answer or "").split())
        return cleaned[:140] if cleaned else "No usable answer evidence."
    
    def _is_visual_accuracy_criterion(self, name: str, description: str) -> bool:
        criterion_text = f"{name} {description}".lower()
        return any(
            marker in criterion_text
            for marker in ["stimulus", "relevance", "visual", "detail", "directly"]
        )
    
    def _detect_visual_color_mismatch(self, answer: str, visual_context: Optional[str]) -> Optional[str]:
        """Detect simple object-color contradictions such as blue vs orange rollercoaster."""
        if not answer or not visual_context:
            return None

        object_terms = [
            "rollercoaster",
            "roller coaster",
            "coaster",
            "ride",
            "track",
            "train",
            "car",
            "seat",
            "shirt",
            "bottle",
            "water bottle",
            "sky",
            "helmet",
            "bag",
            "sign",
        ]
        visual_colours = self._object_colours(visual_context, object_terms)
        answer_colours = self._object_colours(answer, object_terms)

        for obj, student_colours in answer_colours.items():
            expected_colours = visual_colours.get(obj)
            if not expected_colours:
                continue
            wrong_colours = student_colours - expected_colours
            if wrong_colours:
                student_colour = sorted(wrong_colours)[0]
                expected_colour = sorted(expected_colours)[0]
                display_obj = obj.replace("rollercoaster", "rollercoaster")
                return (
                    f"The answer says the {display_obj} is {student_colour}, "
                    f"but the visual context describes it as {expected_colour}"
                )
        return None
    
    def _object_colours(self, text: str, object_terms: List[str]) -> Dict[str, set]:
        colours = [
            "red",
            "orange",
            "yellow",
            "green",
            "blue",
            "purple",
            "pink",
            "black",
            "white",
            "brown",
            "grey",
            "gray",
            "silver",
            "gold",
        ]
        colour_pattern = "|".join(colours)
        lowered = text.lower()
        found: Dict[str, set] = {}

        for obj in object_terms:
            canonical_obj = obj.replace(" ", "")
            obj_pattern = re.escape(obj).replace(r"\ ", r"\s+")
            before_pattern = rf"\b({colour_pattern})\b(?:[-\s]+\w+){{0,3}}\s+{obj_pattern}s?\b"
            after_pattern = rf"\b{obj_pattern}s?\b(?:\s+\w+){{0,4}}\s+\b({colour_pattern})\b"

            for match in re.finditer(before_pattern, lowered):
                found.setdefault(canonical_obj, set()).add(match.group(1))
            for match in re.finditer(after_pattern, lowered):
                found.setdefault(canonical_obj, set()).add(match.group(1))

        return found
    
    def _parse_json_object(self, text: str) -> Dict[str, Any]:
        """Parse a JSON object even if the model wraps it in extra text."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise
    
    def _should_skip_reading_aloud(
        self,
        name: str,
        description: str,
        question: str,
        visual_context: Optional[str],
    ) -> bool:
        """Reading-aloud delivery needs delivery/audio evidence; stimulus chat does not provide it."""
        criterion_text = f"{name} {description}".lower()
        reading_markers = ("reading aloud", "oral reading", "pronunciation", "fluency", "articulation")
        if not any(marker in criterion_text for marker in reading_markers):
            return False

        context = f"{question}\n{visual_context or ''}".lower()
        delivery_evidence_markers = [
            "audio evidence",
            "delivery evidence",
            "pronunciation evidence",
            "fluency evidence",
            "pace evidence",
            "expression evidence",
            "recording analysis",
            "reading-aloud recording",
            "oral delivery notes",
        ]
        return not any(marker in context for marker in delivery_evidence_markers)
    
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
