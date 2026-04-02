# 🎓 Agent A5: Rubric Grader + Tutoring Feedback + Avatar

## Overview

**Agent A5** enables you to:
1. ✅ **Grade assignments** against custom rubrics
2. ✅ **Generate tutoring feedback** as if a tutor is speaking to the student
3. ✅ **Convert to avatar speech** for engaging audio feedback

---

## Quick Start

### **Step 1: Create a Custom Rubric**

Create a JSON file in `data/rubrics/` with your rubric:

```bash
data/rubrics/your_rubric.json
```

Example structure:
```json
{
  "name": "Math Problem Rubric",
  "criteria": [
    {
      "name": "Correctness",
      "description": "Is the final answer correct?",
      "max_score": 5,
      "levels": {
        "0": "Answer is incorrect",
        "3": "Answer is mostly correct with minor errors",
        "5": "Answer is completely correct"
      }
    },
    {
      "name": "Working/Method",
      "description": "Are the steps clearly shown?",
      "max_score": 3,
      "levels": {
        "0": "No working shown",
        "2": "Some steps shown but incomplete",
        "3": "All steps clearly shown"
      }
    },
    {
      "name": "Explanation",
      "description": "Is there a clear explanation?",
      "max_score": 2,
      "levels": {
        "0": "No explanation",
        "1": "Brief explanation",
        "2": "Clear, detailed explanation"
      }
    }
  ]
}
```

### **Step 2: Grade an Assignment**

```bash
# Grade using only text input
python run.py grade \
  "What is 5 + 3?" \
  --answer "8" \
  --rubric "math_problem"

# Or use file paths
python run.py grade \
  path/to/assignment.txt \
  --answer "path/to/student_answer.txt" \
  --rubric "your_rubric"
```

### **Step 3: Get Tutoring Feedback + Audio**

The system automatically:
1. **Scores** the answer against rubric criteria
2. **Generates** tutoring feedback (conversational, supportive)
3. **Converts to audio** for avatar delivery

---

## Complete Workflow Example

### **Scenario: Essay Assignment**

#### **1. Create a custom rubric** (`data/rubrics/essay_rubric.json`)

```json
{
  "name": "Essay Rubric",
  "criteria": [
    {
      "name": "Clarity",
      "description": "Is the essay clear and easy to understand?",
      "max_score": 5,
      "levels": {
        "0": "Unclear and confusing",
        "3": "Generally clear",
        "5": "Very clear and well-written"
      }
    },
    {
      "name": "Evidence",
      "description": "Are there good examples or evidence?",
      "max_score": 3,
      "levels": {
        "0": "No examples",
        "2": "Some examples",
        "3": "Excellent specific examples"
      }
    },
    {
      "name": "Grammar",
      "description": "Are there grammar/spelling errors?",
      "max_score": 2,
      "levels": {
        "0": "Many errors",
        "1": "Few errors",
        "2": "No errors"
      }
    }
  ]
}
```

#### **2. Grade the student's essay**

```bash
python run.py grade \
  "Write an essay about renewable energy" \
  --answer "Renewable energy is energy from natural sources that never run out. Solar power comes from the sun using special panels. Wind power uses turbines to catch wind. Both are clean and don't hurt the environment." \
  --rubric "essay_rubric"
```

#### **3. System Output**

```
======================================================================
RUBRIC SCORES:
======================================================================
  Clarity                5/5
  Evidence              2/3
  Grammar               2/2
  TOTAL                 9/10 (90.0%)

======================================================================
TUTOR'S FEEDBACK (Ready to speak via avatar):
======================================================================

Your essay does a wonderful job explaining renewable energy clearly! 
I especially liked how you gave specific examples like solar panels and wind turbines. 
To make it even stronger, try adding more details about WHY these are important - 
perhaps mention cost savings or environmental benefits compared to fossil fuels. 
These are great concepts to explore more!

======================================================================
GENERATING AVATAR SPEECH...
======================================================================
✓ Audio generated: data/output/tutoring_feedback_audio.wav
```

---

## Usage Patterns

### **Pattern 1: Direct Grade Command**

```bash
python run.py grade \
  "question text" \
  --answer "student answer text" \
  --rubric "rubric_name"
```

### **Pattern 2: Score + Detailed Feedback**

Uses Agent A5 directly:
```bash
python src/agent_a5_grader.py \
  --assignment "Your assignment here" \
  --answer "Student's answer here" \
  --rubric "essay_rubric"
```

### **Pattern 3: Programmatic Grading (Python)**

```python
from src.agent_a5_grader import RubricGrader

grader = RubricGrader(rubric_name="essay_rubric")

result = grader.generate_tutoring_feedback(
    assignment="Your assignment prompt",
    answer="Student's submission"
)

print(result['tutoring_feedback'])  # Get the tutoring speech
print(result['scores'])              # Get criterion scores
print(result['percentage'])           # Get overall percentage
```

---

## Features

### ✅ **Rubric-Based Scoring**
- Score against custom criteria
- Support for rubric levels (0→max points)
- Track scores by criterion

### ✅ **Tutoring Feedback**
- Conversational tone (as if tutor speaking)
- Specific, actionable suggestions
- Encouragement + constructive feedback
- Ready for audio conversion

### ✅ **Avatar Speech**
- Automatic TTS conversion (pyttsx3)
- Save as WAV audio files
- Suitable for accessibility & engagement

---

## Creating Rubrics for Your Subjects

### **Math Problem Rubric**
```json
{
  "name": "Math Problem Rubric",
  "criteria": [
    {"name": "Correctness", "max_score": 5, "description": "Is the answer correct?"},
    {"name": "Working", "max_score": 3, "description": "Are steps shown?"},
    {"name": "Explanation", "max_score": 2, "description": "Is there a clear explanation?"}
  ]
}
```

### **Science Lab Report Rubric**
```json
{
  "name": "Lab Report Rubric",
  "criteria": [
    {"name": "Hypothesis", "max_score": 2, "description": "Is the hypothesis clear?"},
    {"name": "Results", "max_score": 3, "description": "Are results accurately recorded?"},
    {"name": "Analysis", "max_score": 3, "description": "Is the analysis thorough?"},
    {"name": "Conclusion", "max_score": 2, "description": "Does conclusion match results?"}
  ]
}
```

### **Language Skills Rubric**
```json
{
  "name": "Language Skills Rubric",
  "criteria": [
    {"name": "Vocabulary", "max_score": 3, "description": "Appropriate word choice?"},
    {"name": "Grammar", "max_score": 2, "description": "Correct grammar usage?"},
    {"name": "Fluency", "max_score": 3, "description": "Natural expression?"},
    {"name": "Pronunciation", "max_score": 2, "description": "Clear pronunciation?"}
  ]
}
```

---

## Files Modified/Created

✅ **Created**:
- `src/agent_a5_grader.py` - Rubric grader with tutoring feedback
- `data/rubrics/essay_assignment.json` - Example essay rubric

✅ **Updated**:
- `run.py` - Added `grade` command

---

## Integration with Other Agents

| Agent | Purpose | Integration |
|-------|---------|-------------|
| **A1** | Document Ingestion | Ingest assignment files |
| **A3** | Dialogue Manager | Generate feedback for dialogues |
| **A4** | Avatar/TTS | Convert feedback to audio |
| **A5** | Rubric Grader | **NEW** - Score & provide tutoring feedback |

---

## Advanced: Programmatic Workflow

```python
from pathlib import Path
from src.agent_a5_grader import RubricGrader

# Load assignment from file
assignment_file = Path("data/assignments/essay_prompt.txt")
answer_file = Path("data/student_submissions/student1_answer.txt")

with open(assignment_file) as f:
    assignment = f.read()
with open(answer_file) as f:
    answer = f.read()

# Grade it
grader = RubricGrader(rubric_name="essay_rubric")
result = grader.generate_tutoring_feedback(assignment, answer)

# Save feedback
feedback_file = Path("data/output/feedback.txt")
with open(feedback_file, 'w') as f:
    f.write(result['tutoring_feedback'])

# Generate audio
import subprocess
subprocess.run([
    "python", "src/agent_a4_avatar.py",
    "--text", result['tutoring_feedback'],
    "--output", "data/output/feedback_audio.wav"
])

print(f"Score: {result['percentage']}%")
print(f"Feedback saved: {feedback_file}")
```

---

## Next Steps

1. **Create rubrics** for your subjects in `data/rubrics/`
2. **Test grading** with sample assignments
3. **Listen to audio** feedback as tutor would speak it
4. **Refine rubrics** based on feedback quality
5. **Integrate into workflow** - use with A1 (ingest) + A3 (dialogue) + A4 (audio)

---

**Your Complete System is Now:**
- ✅ A1: Document Ingestion
- ✅ A2: Semantic Search
- ✅ A3: Dialogue Manager
- ✅ A4: Avatar/TTS
- ✅ **A5: Rubric Grader** ← NEW!
- ⏳ A6: Orchestrator (Coming next)
