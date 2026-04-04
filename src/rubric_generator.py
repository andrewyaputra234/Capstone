"""
Rubric Generator: Auto-generate assessment rubrics based on education level and subject.
Supports Primary School, Secondary School, High School, and University levels.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional


# Rubric templates by education level and subject
RUBRIC_TEMPLATES = {
    "Primary": {
        "math": {
            "name": "Primary Mathematics",
            "criteria": [
                {
                    "name": "Conceptual Understanding",
                    "description": "Student demonstrates understanding of basic mathematical concepts",
                    "max_points": 25,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 25, "description": "Clearly explains concepts with examples"},
                        {"level": "Good", "points": 20, "description": "Explains concepts with minor gaps"},
                        {"level": "Fair", "points": 15, "description": "Basic understanding shown"},
                        {"level": "Poor", "points": 5, "description": "Limited understanding"}
                    ]
                },
                {
                    "name": "Problem Solving",
                    "description": "Student can solve mathematical problems using correct methods",
                    "max_points": 25,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 25, "description": "Solves problems accurately with steps shown"},
                        {"level": "Good", "points": 20, "description": "Mostly correct solutions with steps"},
                        {"level": "Fair", "points": 15, "description": "Some correct solutions"},
                        {"level": "Poor", "points": 5, "description": "Incorrect solutions"}
                    ]
                },
                {
                    "name": "Calculation Accuracy",
                    "description": "Student performs arithmetic operations correctly",
                    "max_points": 25,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 25, "description": "All calculations correct"},
                        {"level": "Good", "points": 20, "description": "Most calculations correct (1-2 minor errors)"},
                        {"level": "Fair", "points": 15, "description": "Several correct calculations"},
                        {"level": "Poor", "points": 5, "description": "Most calculations incorrect"}
                    ]
                },
                {
                    "name": "Communication",
                    "description": "Student communicates mathematical thinking clearly",
                    "max_points": 25,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 25, "description": "Clear and organized explanation"},
                        {"level": "Good", "points": 20, "description": "Generally clear explanation"},
                        {"level": "Fair", "points": 15, "description": "Somewhat unclear"},
                        {"level": "Poor", "points": 5, "description": "Unclear or confusing"}
                    ]
                }
            ]
        },
        "english": {
            "name": "Primary English Language",
            "criteria": [
                {
                    "name": "Comprehension",
                    "description": "Student understands and recalls text content",
                    "max_points": 25,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 25, "description": "Accurately identifies all key ideas"},
                        {"level": "Good", "points": 20, "description": "Identifies most key ideas"},
                        {"level": "Fair", "points": 15, "description": "Identifies some key ideas"},
                        {"level": "Poor", "points": 5, "description": "Misses key ideas"}
                    ]
                },
                {
                    "name": "Vocabulary",
                    "description": "Student uses appropriate vocabulary",
                    "max_points": 25,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 25, "description": "Uses varied, age-appropriate vocabulary"},
                        {"level": "Good", "points": 20, "description": "Uses appropriate vocabulary mostly"},
                        {"level": "Fair", "points": 15, "description": "Uses basic vocabulary"},
                        {"level": "Poor", "points": 5, "description": "Limited vocabulary use"}
                    ]
                },
                {
                    "name": "Grammar & Spelling",
                    "description": "Student uses correct grammar and spelling",
                    "max_points": 25,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 25, "description": "Mostly correct grammar/spelling (0-1 errors)"},
                        {"level": "Good", "points": 20, "description": "Minor grammar/spelling errors (2-3)"},
                        {"level": "Fair", "points": 15, "description": "Several errors (4-5)"},
                        {"level": "Poor", "points": 5, "description": "Many errors"}
                    ]
                },
                {
                    "name": "Verbal Expression",
                    "description": "Student expresses ideas clearly and confidently",
                    "max_points": 25,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 25, "description": "Clear, confident, well-organized expression"},
                        {"level": "Good", "points": 20, "description": "Generally clear expression"},
                        {"level": "Fair", "points": 15, "description": "Somewhat unclear but understandable"},
                        {"level": "Poor", "points": 5, "description": "Unclear or hesitant"}
                    ]
                }
            ]
        },
        "science": {
            "name": "Primary Science",
            "criteria": [
                {
                    "name": "Conceptual Understanding",
                    "description": "Student understands scientific concepts",
                    "max_points": 25,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 25, "description": "Clear understanding with examples"},
                        {"level": "Good", "points": 20, "description": "Good understanding"},
                        {"level": "Fair", "points": 15, "description": "Basic understanding"},
                        {"level": "Poor", "points": 5, "description": "Limited understanding"}
                    ]
                },
                {
                    "name": "Observation & Description",
                    "description": "Student observes and describes phenomena accurately",
                    "max_points": 25,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 25, "description": "Detailed and accurate descriptions"},
                        {"level": "Good", "points": 20, "description": "Mostly accurate descriptions"},
                        {"level": "Fair", "points": 15, "description": "Some accurate details"},
                        {"level": "Poor", "points": 5, "description": "Inaccurate descriptions"}
                    ]
                },
                {
                    "name": "Scientific Reasoning",
                    "description": "Student explains cause and effect",
                    "max_points": 25,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 25, "description": "Clear cause-effect explanations"},
                        {"level": "Good", "points": 20, "description": "Generally logical explanations"},
                        {"level": "Fair", "points": 15, "description": "Basic reasoning"},
                        {"level": "Poor", "points": 5, "description": "Weak or missing reasoning"}
                    ]
                },
                {
                    "name": "Communication",
                    "description": "Student communicates scientific ideas clearly",
                    "max_points": 25,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 25, "description": "Clear and well-organized"},
                        {"level": "Good", "points": 20, "description": "Generally clear"},
                        {"level": "Fair", "points": 15, "description": "Somewhat unclear"},
                        {"level": "Poor", "points": 5, "description": "Unclear"}
                    ]
                }
            ]
        }
    },
    "Secondary": {
        "math": {
            "name": "Secondary Mathematics",
            "criteria": [
                {
                    "name": "Conceptual Mastery",
                    "description": "Deep understanding of mathematical concepts",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Comprehensive understanding with connections"},
                        {"level": "Good", "points": 16, "description": "Solid understanding"},
                        {"level": "Fair", "points": 10, "description": "Basic understanding with gaps"},
                        {"level": "Poor", "points": 4, "description": "Limited understanding"}
                    ]
                },
                {
                    "name": "Problem Solving & Analysis",
                    "description": "Can solve complex problems using multiple strategies",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Solves complex problems with clear strategy"},
                        {"level": "Good", "points": 16, "description": "Mostly successful problem-solving"},
                        {"level": "Fair", "points": 10, "description": "Attempts solutions with some success"},
                        {"level": "Poor", "points": 4, "description": "Struggles with problems"}
                    ]
                },
                {
                    "name": "Mathematical Reasoning",
                    "description": "Justifies answers and explains reasoning",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Clear logical justifications"},
                        {"level": "Good", "points": 16, "description": "Sound reasoning shown"},
                        {"level": "Fair", "points": 10, "description": "Some reasoning provided"},
                        {"level": "Poor", "points": 4, "description": "Minimal reasoning"}
                    ]
                },
                {
                    "name": "Application & Accuracy",
                    "description": "Applies concepts correctly and accurately",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Accurate application in varied contexts"},
                        {"level": "Good", "points": 16, "description": "Mostly accurate application"},
                        {"level": "Fair", "points": 10, "description": "Some accurate applications"},
                        {"level": "Poor", "points": 4, "description": "Inaccurate application"}
                    ]
                },
                {
                    "name": "Communication",
                    "description": "Articulates mathematical thinking clearly",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Clear, precise, well-organized communication"},
                        {"level": "Good", "points": 16, "description": "Generally clear communication"},
                        {"level": "Fair", "points": 10, "description": "Somewhat unclear"},
                        {"level": "Poor", "points": 4, "description": "Unclear or incomplete"}
                    ]
                }
            ]
        },
        "english": {
            "name": "Secondary English Language & Literature",
            "criteria": [
                {
                    "name": "Textual Analysis",
                    "description": "Analyzes literary texts and devices effectively",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Insightful analysis of text and techniques"},
                        {"level": "Good", "points": 16, "description": "Good understanding of text and devices"},
                        {"level": "Fair", "points": 10, "description": "Basic analysis"},
                        {"level": "Poor", "points": 4, "description": "Limited analysis"}
                    ]
                },
                {
                    "name": "Vocabulary & Language Use",
                    "description": "Sophisticated and contextual vocabulary",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Sophisticated, varied vocabulary"},
                        {"level": "Good", "points": 16, "description": "Good range of vocabulary"},
                        {"level": "Fair", "points": 10, "description": "Adequate vocabulary"},
                        {"level": "Poor", "points": 4, "description": "Limited vocabulary"}
                    ]
                },
                {
                    "name": "Argumentation & Evidence",
                    "description": "Supports claims with relevant evidence",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Well-developed arguments with strong evidence"},
                        {"level": "Good", "points": 16, "description": "Reasonable arguments with evidence"},
                        {"level": "Fair", "points": 10, "description": "Attempts arguments with some evidence"},
                        {"level": "Poor", "points": 4, "description": "Weak or missing arguments"}
                    ]
                },
                {
                    "name": "Grammar & Style",
                    "description": "Correct grammar, syntax, and writing style",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Excellent grammar and sophisticated style"},
                        {"level": "Good", "points": 16, "description": "Correct grammar with good style"},
                        {"level": "Fair", "points": 10, "description": "Generally correct with minor errors"},
                        {"level": "Poor", "points": 4, "description": "Frequent errors"}
                    ]
                },
                {
                    "name": "Organization & Coherence",
                    "description": "Well-structured and logically organized",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Excellent structure and flow"},
                        {"level": "Good", "points": 16, "description": "Clear organization"},
                        {"level": "Fair", "points": 10, "description": "Basic organization"},
                        {"level": "Poor", "points": 4, "description": "Poorly organized"}
                    ]
                }
            ]
        },
        "science": {
            "name": "Secondary Science",
            "criteria": [
                {
                    "name": "Scientific Knowledge",
                    "description": "Demonstrates solid knowledge of concepts",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Comprehensive knowledge"},
                        {"level": "Good", "points": 16, "description": "Good knowledge"},
                        {"level": "Fair", "points": 10, "description": "Basic knowledge"},
                        {"level": "Poor", "points": 4, "description": "Limited knowledge"}
                    ]
                },
                {
                    "name": "Analysis & Interpretation",
                    "description": "Analyzes data and interprets results",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Thorough analysis with correct interpretation"},
                        {"level": "Good", "points": 16, "description": "Good analysis"},
                        {"level": "Fair", "points": 10, "description": "Some analysis"},
                        {"level": "Poor", "points": 4, "description": "Limited analysis"}
                    ]
                },
                {
                    "name": "Scientific Reasoning",
                    "description": "Logical application of scientific principles",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Sound logical reasoning"},
                        {"level": "Good", "points": 16, "description": "Generally logical"},
                        {"level": "Fair", "points": 10, "description": "Basic reasoning"},
                        {"level": "Poor", "points": 4, "description": "Weak reasoning"}
                    ]
                },
                {
                    "name": "Methodology & Practice",
                    "description": "Follows proper experimental procedure",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Excellent procedure and technique"},
                        {"level": "Good", "points": 16, "description": "Good procedure"},
                        {"level": "Fair", "points": 10, "description": "Generally follows procedure"},
                        {"level": "Poor", "points": 4, "description": "Improper procedure"}
                    ]
                },
                {
                    "name": "Communication",
                    "description": "Clear scientific communication",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Clear and precise communication"},
                        {"level": "Good", "points": 16, "description": "Generally clear"},
                        {"level": "Fair", "points": 10, "description": "Somewhat clear"},
                        {"level": "Poor", "points": 4, "description": "Unclear"}
                    ]
                }
            ]
        }
    },
    "High School": {
        "math": {
            "name": "High School Mathematics (Advanced)",
            "criteria": [
                {
                    "name": "Advanced Conceptual Understanding",
                    "description": "Mastery of advanced mathematical concepts",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Expert-level understanding with synthesis"},
                        {"level": "Good", "points": 16, "description": "Strong understanding"},
                        {"level": "Fair", "points": 10, "description": "Adequate understanding"},
                        {"level": "Poor", "points": 4, "description": "Incomplete understanding"}
                    ]
                },
                {
                    "name": "Problem Solving (Complex)",
                    "description": "Solves multi-step and non-routine problems",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Solves complex problems effectively"},
                        {"level": "Good", "points": 16, "description": "Good problem-solving"},
                        {"level": "Fair", "points": 10, "description": "Some success with complex problems"},
                        {"level": "Poor", "points": 4, "description": "Difficulty with complex problems"}
                    ]
                },
                {
                    "name": "Mathematical Proof & Rigor",
                    "description": "Provides rigorous proofs and justifications",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Rigorous logical proofs"},
                        {"level": "Good", "points": 16, "description": "Sound justifications"},
                        {"level": "Fair", "points": 10, "description": "Some justification"},
                        {"level": "Poor", "points": 4, "description": "Minimal justification"}
                    ]
                },
                {
                    "name": "Application & Integration",
                    "description": "Applies concepts to new contexts",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Seamless application across contexts"},
                        {"level": "Good", "points": 16, "description": "Good application"},
                        {"level": "Fair", "points": 10, "description": "Some application"},
                        {"level": "Poor", "points": 4, "description": "Limited application"}
                    ]
                },
                {
                    "name": "Articulation & Clarity",
                    "description": "Articulates ideas with precision",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Precise, elegant articulation"},
                        {"level": "Good", "points": 16, "description": "Clear articulation"},
                        {"level": "Fair", "points": 10, "description": "Adequate clarity"},
                        {"level": "Poor", "points": 4, "description": "Unclear"},
                    ]
                }
            ]
        },
        "english": {
            "name": "High School English & Literature",
            "criteria": [
                {
                    "name": "Critical Analysis",
                    "description": "Advanced critical analysis of texts",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Sophisticated critical analysis"},
                        {"level": "Good", "points": 16, "description": "Strong analysis"},
                        {"level": "Fair", "points": 10, "description": "Adequate analysis"},
                        {"level": "Poor", "points": 4, "description": "Weak analysis"}
                    ]
                },
                {
                    "name": "Sophisticated Language Use",
                    "description": "Sophisticated, intentional language choices",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Masterful language use"},
                        {"level": "Good", "points": 16, "description": "Sophisticated vocabulary"},
                        {"level": "Fair", "points": 10, "description": "Adequate vocabulary"},
                        {"level": "Poor", "points": 4, "description": "Limited vocabulary"}
                    ]
                },
                {
                    "name": "Evidence & Reasoning",
                    "description": "Complex arguments with strong evidence",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Compelling arguments with multiple perspectives"},
                        {"level": "Good", "points": 16, "description": "Well-reasoned arguments"},
                        {"level": "Fair", "points": 10, "description": "Adequate arguments with evidence"},
                        {"level": "Poor", "points": 4, "description": "Weak arguments"}
                    ]
                },
                {
                    "name": "Style & Development",
                    "description": "Sophisticated style and development",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Excellent control of style and development"},
                        {"level": "Good", "points": 16, "description": "Good style and development"},
                        {"level": "Fair", "points": 10, "description": "Adequate development"},
                        {"level": "Poor", "points": 4, "description": "Weak development"}
                    ]
                },
                {
                    "name": "Conventions & Execution",
                    "description": "Mastery of writing conventions",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Flawless conventions"},
                        {"level": "Good", "points": 16, "description": "Excellent command of conventions"},
                        {"level": "Fair", "points": 10, "description": "Generally correct"},
                        {"level": "Poor", "points": 4, "description": "Frequent errors"}
                    ]
                }
            ]
        },
        "science": {
            "name": "High School Science (Advanced)",
            "criteria": [
                {
                    "name": "Conceptual Mastery",
                    "description": "Deep understanding of complex concepts",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Expert-level conceptual understanding"},
                        {"level": "Good", "points": 16, "description": "Strong understanding"},
                        {"level": "Fair", "points": 10, "description": "Adequate understanding"},
                        {"level": "Poor", "points": 4, "description": "Limited understanding"}
                    ]
                },
                {
                    "name": "Data Analysis & Interpretation",
                    "description": "Advanced data analysis skills",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Sophisticated analysis with clear interpretation"},
                        {"level": "Good", "points": 16, "description": "Strong analytical skills"},
                        {"level": "Fair", "points": 10, "description": "Adequate analysis"},
                        {"level": "Poor", "points": 4, "description": "Weak analysis"}
                    ]
                },
                {
                    "name": "Scientific Inquiry",
                    "description": "Demonstrates scientific thinking",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Excellent scientific inquiry"},
                        {"level": "Good", "points": 16, "description": "Sound inquiry"},
                        {"level": "Fair", "points": 10, "description": "Basic inquiry"},
                        {"level": "Poor", "points": 4, "description": "Weak inquiry"}
                    ]
                },
                {
                    "name": "Lab & Experimental Skills",
                    "description": "Advanced lab techniques",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Expert lab execution"},
                        {"level": "Good", "points": 16, "description": "Strong lab skills"},
                        {"level": "Fair", "points": 10, "description": "Adequate technique"},
                        {"level": "Poor", "points": 4, "description": "Weak technique"}
                    ]
                },
                {
                    "name": "Communication & Presentation",
                    "description": "Professional scientific communication",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Professional-level communication"},
                        {"level": "Good", "points": 16, "description": "Clear communication"},
                        {"level": "Fair", "points": 10, "description": "Adequate communication"},
                        {"level": "Poor", "points": 4, "description": "Unclear communication"}
                    ]
                }
            ]
        }
    },
    "University": {
        "math": {
            "name": "University Mathematics",
            "criteria": [
                {
                    "name": "Theoretical Mastery",
                    "description": "Command of theoretical mathematics",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Deep theoretical understanding with insight"},
                        {"level": "Good", "points": 16, "description": "Strong theoretical grasp"},
                        {"level": "Fair", "points": 10, "description": "Adequate theoretical knowledge"},
                        {"level": "Poor", "points": 4, "description": "Limited theoretical understanding"}
                    ]
                },
                {
                    "name": "Proof & Rigor",
                    "description": "Rigorous mathematical proofs",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Elegant, rigorous proofs"},
                        {"level": "Good", "points": 16, "description": "Sound proofs"},
                        {"level": "Fair", "points": 10, "description": "Mostly correct proofs"},
                        {"level": "Poor", "points": 4, "description": "Incomplete proofs"}
                    ]
                },
                {
                    "name": "Advanced Problem Solving",
                    "description": "Solves advanced, abstract problems",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Elegantly solves advanced problems"},
                        {"level": "Good", "points": 16, "description": "Solves advanced problems effectively"},
                        {"level": "Fair", "points": 10, "description": "Some success with advanced problems"},
                        {"level": "Poor", "points": 4, "description": "Struggles with advanced problems"}
                    ]
                },
                {
                    "name": "Mathematical Reasoning & Synthesis",
                    "description": "Connects and synthesizes concepts",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Excellent synthesis and connections"},
                        {"level": "Good", "points": 16, "description": "Good reasoning and synthesis"},
                        {"level": "Fair", "points": 10, "description": "Some connections made"},
                        {"level": "Poor", "points": 4, "description": "Limited synthesis"}
                    ]
                },
                {
                    "name": "Academic Communication",
                    "description": "Professional mathematical writing",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Excellent mathematical writing"},
                        {"level": "Good", "points": 16, "description": "Clear and professional"},
                        {"level": "Fair", "points": 10, "description": "Adequate clarity"},
                        {"level": "Poor", "points": 4, "description": "Unclear writing"}
                    ]
                }
            ]
        },
        "english": {
            "name": "University English & Literature",
            "criteria": [
                {
                    "name": "Scholarly Analysis",
                    "description": "Sophisticated scholarly analysis",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Publishable scholarly analysis"},
                        {"level": "Good", "points": 16, "description": "Strong scholarly work"},
                        {"level": "Fair", "points": 10, "description": "Adequate scholarly analysis"},
                        {"level": "Poor", "points": 4, "description": "Weak scholarship"}
                    ]
                },
                {
                    "name": "Literary Theory & Methodology",
                    "description": "Uses literary theory sophisticatedly",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Masterful application of theory"},
                        {"level": "Good", "points": 16, "description": "Strong theoretical application"},
                        {"level": "Fair", "points": 10, "description": "Adequate theory use"},
                        {"level": "Poor", "points": 4, "description": "Limited theory use"}
                    ]
                },
                {
                    "name": "Argumentation & Evidence",
                    "description": "Sophisticated academic argumentation",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Compelling, nuanced arguments"},
                        {"level": "Good", "points": 16, "description": "Well-developed arguments"},
                        {"level": "Fair", "points": 10, "description": "Adequate arguments"},
                        {"level": "Poor", "points": 4, "description": "Weak or unclear arguments"}
                    ]
                },
                {
                    "name": "Intellectual Engagement",
                    "description": "Shows original thinking",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Original and insightful thinking"},
                        {"level": "Good", "points": 16, "description": "Good intellectual engagement"},
                        {"level": "Fair", "points": 10, "description": "Some original thinking"},
                        {"level": "Poor", "points": 4, "description": "Limited original thinking"}
                    ]
                },
                {
                    "name": "Academic Style & Conventions",
                    "description": "Mastery of academic conventions",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Perfect academic style"},
                        {"level": "Good", "points": 16, "description": "Excellent academic style"},
                        {"level": "Fair", "points": 10, "description": "Adequate conventions"},
                        {"level": "Poor", "points": 4, "description": "Weak conventions"}
                    ]
                }
            ]
        },
        "science": {
            "name": "University Science (Research)",
            "criteria": [
                {
                    "name": "Research Knowledge",
                    "description": "Command of research-level knowledge",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "State-of-the-art knowledge"},
                        {"level": "Good", "points": 16, "description": "Strong research knowledge"},
                        {"level": "Fair", "points": 10, "description": "Adequate knowledge"},
                        {"level": "Poor", "points": 4, "description": "Limited knowledge"}
                    ]
                },
                {
                    "name": "Research Methodology",
                    "description": "Sophisticated research design",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Excellent research design"},
                        {"level": "Good", "points": 16, "description": "Sound methodology"},
                        {"level": "Fair", "points": 10, "description": "Adequate methodology"},
                        {"level": "Poor", "points": 4, "description": "Weak methodology"}
                    ]
                },
                {
                    "name": "Data Analysis & Interpretation",
                    "description": "Advanced quantitative/qualitative analysis",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Sophisticated statistical analysis"},
                        {"level": "Good", "points": 16, "description": "Strong analytical methods"},
                        {"level": "Fair", "points": 10, "description": "Adequate analysis"},
                        {"level": "Poor", "points": 4, "description": "Weak analysis"}
                    ]
                },
                {
                    "name": "Scientific Innovation",
                    "description": "Demonstrates original research contribution",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Novel and impactful contribution"},
                        {"level": "Good", "points": 16, "description": "Good original contribution"},
                        {"level": "Fair", "points": 10, "description": "Some originality"},
                        {"level": "Poor", "points": 4, "description": "Limited originality"}
                    ]
                },
                {
                    "name": "Academic Communication",
                    "description": "Professional research communication",
                    "max_points": 20,
                    "rubric_levels": [
                        {"level": "Excellent", "points": 20, "description": "Publication-quality writing"},
                        {"level": "Good", "points": 16, "description": "Professional communication"},
                        {"level": "Fair", "points": 10, "description": "Adequate communication"},
                        {"level": "Poor", "points": 4, "description": "Unclear communication"}
                    ]
                }
            ]
        }
    }
}


def generate_rubric(
    subject: str,
    education_level: str,
    custom_subject: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate a rubric based on subject and education level.
    
    Args:
        subject: Subject name (math, english, science) - normalized to lowercase
        education_level: Primary, Secondary, High School, or University
        custom_subject: Optional custom subject name to use instead of auto-generated name
        
    Returns:
        Dictionary containing the rubric
    """
    subject_lower = subject.lower().strip()
    
    # Normalize subject names - check for keywords anywhere in the string
    if any(word in subject_lower for word in ["math", "maths", "mathematics", "calculus", "algebra", "arithmetic"]):
        subject_key = "math"
    elif any(word in subject_lower for word in ["eng", "english", "literature", "ela", "language", "writing"]):
        subject_key = "english"
    elif any(word in subject_lower for word in ["sci", "science", "biology", "chem", "physics", "life sci"]):
        subject_key = "science"
    else:
        # Default to generic math rubric
        subject_key = "math"
        print(f"[INFO] Subject '{subject}' not in template. Using generic math rubric.")
    
    # Get the template
    if education_level not in RUBRIC_TEMPLATES:
        print(f"[WARNING] Unknown education level '{education_level}'. Using Primary level.")
        education_level = "Primary"
    
    if subject_key not in RUBRIC_TEMPLATES[education_level]:
        print(f"[INFO] No template for {subject_key} at {education_level} level. Using math template.")
        subject_key = "math"
    
    rubric_template = RUBRIC_TEMPLATES[education_level][subject_key]
    
    # Create rubric with custom subject name if provided
    rubric = {
        "name": custom_subject or rubric_template["name"],
        "level": education_level,
        "subject": subject,
        "criteria": rubric_template["criteria"]
    }
    
    return rubric


def save_rubric(rubric: Dict[str, Any], rubric_name: str) -> str:
    """
    Save rubric to JSON file.
    
    Args:
        rubric: Rubric dictionary
        rubric_name: Name for the rubric file (without .json)
        
    Returns:
        Path to saved rubric file
    """
    rubrics_dir = Path("data/rubrics")
    rubrics_dir.mkdir(parents=True, exist_ok=True)
    
    rubric_path = rubrics_dir / f"{rubric_name}.json"
    
    with open(rubric_path, "w", encoding="utf-8") as f:
        json.dump(rubric, f, indent=2, ensure_ascii=False)
    
    print(f"[OK] Rubric saved: {rubric_path}")
    return str(rubric_path)


def get_or_create_rubric(
    subject: str,
    education_level: str
) -> tuple[str, str]:
    """
    Get existing rubric or create a new one.
    
    Args:
        subject: Subject name
        education_level: Education level
        
    Returns:
        Tuple of (rubric_name, rubric_path)
    """
    rubric_name = f"{education_level.lower()}_{subject.lower()}"
    rubric_path = Path("data/rubrics") / f"{rubric_name}.json"
    
    # If rubric already exists, return it
    if rubric_path.exists():
        print(f"[OK] Rubric already exists: {rubric_path}")
        return rubric_name, str(rubric_path)
    
    # Generate and save new rubric
    print(f"[INFO] Generating {education_level} {subject} rubric...")
    rubric = generate_rubric(
        subject=subject,
        education_level=education_level,
        custom_subject=f"{education_level} {subject.title()}"
    )
    
    return rubric_name, save_rubric(rubric, rubric_name)


def list_available_rubrics() -> Dict[str, list]:
    """
    List all available rubrics grouped by education level.
    
    Returns:
        Dictionary with education levels as keys
    """
    available = {
        "Primary": ["math", "english", "science"],
        "Secondary": ["math", "english", "science"],
        "High School": ["math", "english", "science"],
        "University": ["math", "english", "science"]
    }
    return available


if __name__ == "__main__":
    # Test rubric generation
    print("Testing rubric generation...\n")
    
    for level in ["Primary", "Secondary", "High School", "University"]:
        for subject in ["math", "english", "science"]:
            print(f"\nGenerating {level} {subject}...")
            rubric = generate_rubric(subject, level)
            rubric_name, path = get_or_create_rubric(subject, level)
            print(f"✓ Created: {rubric_name}")
    
    print("\n[OK] All rubrics generated successfully!")
