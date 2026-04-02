# 🚀 Getting Started Guide - Oral Assessment System

## What Does This System Do?

Your system is an **AI-powered oral assessment tool**. Imagine a tutor that:
1. **Asks questions** from your documents (papers, exams, etc.)
2. **Listens to student answers** (via microphone or text)
3. **Grades them** against YOUR custom rubric
4. **Provides personalized feedback** in a tutoring style
5. **Speaks back** the feedback with a voice
6. **Saves everything** for review later

## Quick Start (5 minutes)

### Step 1: Prepare Your First Document

Create a simple text file with some questions:

**File: `data/input/biology/sample_exam.txt`**
```
Sample Biology Exam

Q1) What is photosynthesis?
Q2) Name the five kingdoms of life.
Q3) Explain the water cycle in detail.
```

### Step 2: Ingest Your Document

Tell the system to read and organize your document:

```bash
python run.py ingest data/input/biology/sample_exam.txt --subject biology
```

**What you'll see:**
```
Processing file...
Saving to subject: biology
✓ Successfully ingested 1 file
  Chunks created: 5
  Database location: data/chroma_db/biology_db/
```

### Step 3: Create or Choose a Rubric

Your system comes with example rubrics. See what's available:

```bash
ls data/rubrics/
```

**You'll see:**
```
essay_assignment.json      # Essay grading (7 criteria)
primary1_math.json         # Math grading
```

Or **create your own rubric** (`data/rubrics/biology_rubric.json`):

```json
{
  "name": "Biology Quiz Rubric",
  "criteria": [
    {
      "name": "Accuracy",
      "description": "Is the answer scientifically correct?",
      "max_score": 5,
      "levels": {
        "0": "Completely incorrect",
        "3": "Mostly correct with minor errors",
        "5": "Completely accurate"
      }
    },
    {
      "name": "Completeness",
      "description": "Does the answer cover all key points?",
      "max_score": 3,
      "levels": {
        "0": "Missing most points",
        "2": "Covers some points",
        "3": "Covers all key points"
      }
    }
  ]
}
```

### Step 4: Run an Assessment (Text Input)

Ask the system to quiz you using text answers:

```bash
python run.py dialogue --interactive --subject biology --rubric biology_rubric
```

**What happens:**

```
============================================================
🎓 Oral Assessment System - Agent A3 [biology]
============================================================

✅ Extracted 3 questions:

  1. What is photosynthesis?
  
  2. Name the five kingdoms of life.
  
  3. Explain the water cycle in detail.

❓ Question 1/3:
What is photosynthesis?

Your answer: Photosynthesis is the process where plants use sunlight to make food

⏳ Evaluating answer...

📊 Scores by Criterion:
  Accuracy: 4/5
  Completeness: 2/3
  
📈 Total: 6/8 (75%)

---
❓ Question 2/3:
Name the five kingdoms of life...
```

**After all questions:**
```
✅ Assessment Complete!

============================================================
Assessment Report
============================================================
Questions Asked: 3
Questions Answered: 3
Total Score: 20 / 24
Average Score: 6.7/8
Percentage: 83%
============================================================
```

---

## Full Workflow: Audio Assessment with Session Tracking

### For a Student (Audio Mode)

**Step 1: Run the full assessment**

```bash
python run.py dialogue \
  --interactive \
  --subject biology \
  --rubric biology_rubric \
  --audio \
  --use-audio-input \
  --use-sessions \
  --student-id alice_smith
```

**Step 2: What happens**

```
============================================================
🎓 Oral Assessment System [biology] [Audio Output] [Audio Input] [Session Tracking]
============================================================

✅ Created session: a3f7b2c1
   Paper: biology
   Student: alice_smith

📋 Session: a3f7b2c1

✅ Extracted 3 questions

❓ Question 1/3:
What is photosynthesis?

🔊 Generating audio...
✅ Audio available: data/output/question_1_audio.wav

🎤 Recording audio answer (15 seconds max)...
Recording for 15 seconds...
Press Ctrl+C to stop early.

Recording... 1s / 15s
Recording... 2s / 15s
...
[Student speaks their answer]
...
Recording... 12s / 15s
✓ Audio saved: data/sessions/q1_answer.wav (0.35 MB)

🔄 Transcribing audio: q1_answer.wav
✓ Transcribed: Photosynthesis is the process where plants use sunlight to create glucose and oxygen...

✓ Transcribed answer: Photosynthesis is the process...

⏳ Evaluating answer...

📊 Scores by Criterion:
  Accuracy: 5/5
  Completeness: 3/3

📈 Total: 8/8 (100%)

---
[Repeats for Q2, Q3...]

✅ Assessment Complete!

📋 Session saved: a3f7b2c1

============================================================
Assessment Report
============================================================
[Scores and results...]
============================================================
```

**Step 3: Review the session later**

```bash
# View session details
python src/agent_a6_session_manager.py view --session a3f7b2c1

# Export as JSON (open in browser/Excel)
python src/agent_a6_session_manager.py export --session a3f7b2c1 --format json --output results.json

# Export as spreadsheet
python src/agent_a6_session_manager.py export --session a3f7b2c1 --format csv --output results.csv
```

---

## Common Tasks

### Task 1: Grade an Assignment (Not a Quiz)

```bash
python run.py grade \
  "Write a 5-paragraph essay about photosynthesis" \
  --answer "Photosynthesis is the process where plants convert sunlight into chemical energy..." \
  --rubric essay_assignment
```

**Output:**
```
SCORE BREAKDOWN:
  Clarity & Organization: 4/5
  Content & Accuracy: 5/5
  Use of Examples: 2/3
  Language & Mechanics: 2/2
Total: 13/15 (86.7%)

TUTOR'S FEEDBACK:
Great job on explaining photosynthesis! You covered the main concepts well and organized 
your essay logically. To improve, try adding more specific examples...
```

### Task 2: List All Available Subjects

```bash
python run.py list-subjects
```

**Output:**
```
📚 Available Subjects:
--------------------------------------------------
  • biology
    Chunks: 15
    DB: data/chroma_db/biology_db/
  • math
    Chunks: 42
    DB: data/chroma_db/math_db/
  • chemistry
    Chunks: 8
    DB: data/chroma_db/chemistry_db/
```

### Task 3: View All Sessions

```bash
python src/agent_a6_session_manager.py list
```

**Output:**
```
Found 5 sessions:
  • a3f7b2c1 (alice_smith) - COMPLETED
  • b4g8c3d2 (bob_jones) - COMPLETED
  • c5h9d4e3 (charlie_davis) - ACTIVE
  • d6i0j5f4 (diana_patel) - COMPLETED
  • e7j1k6g5 (ethan_wilson) - COMPLETED
```

### Task 4: Delete a Session

```bash
python src/agent_a6_session_manager.py delete --session a3f7b2c1
```

---

## The Complete File Structure

After using the system, here's what you'll have:

```
Capstone/
├── run.py                           ← Main entry point
├── data/
│   ├── input/                       ← Your documents go here
│   │   ├── biology/
│   │   │   └── sample_exam.txt
│   │   ├── math/
│   │   │   └── practice_problems.pdf
│   │   └── ...
│   ├── output/                      ← Generated question audio
│   │   └── question_1_audio.wav
│   ├── rubrics/                     ← Your grading rubrics
│   │   ├── essay_assignment.json
│   │   ├── primary1_math.json
│   │   └── biology_rubric.json      ← Your custom rubric
│   ├── sessions/                    ← Saved assessments
│   │   ├── a3f7b2c1_session.json    ← Session file
│   │   ├── q1_answer.wav            ← Student audio
│   │   ├── q1_transcription.json    ← Whisper transcription
│   │   ├── a3f7b2c1_transcript.json ← Exported transcript
│   │   └── ...
│   └── chroma_db/                   ← Vector database (auto-created)
│       ├── biology_db/
│       ├── math_db/
│       └── ...
└── src/
    ├── agent_a1_ingestion.py        ← Load documents
    ├── agent_a3_dialogue.py         ← Ask questions
    ├── agent_a4_avatar.py           ← Generate speech
    ├── agent_a5_grader.py           ← Grade assignments
    ├── agent_a6_session_manager.py  ← Track sessions
    ├── agent_audio_input.py         ← Record audio
    └── ...
```

---

## Typical Day: Teacher Using This System

### Morning: Prepare Assessment

```bash
# 1. Create a folder with your exam questions
mkdir data/input/science
echo "Q1) What is gravity?
Q2) What causes seasons?" > data/input/science/exam.txt

# 2. Ingest the document
python run.py ingest data/input/science/exam.txt --subject science

# 3. Create a rubric (or use existing one)
# Copy essay_assignment.json to science_rubric.json
cp data/rubrics/essay_assignment.json data/rubrics/science_rubric.json
```

### During Class: Students Take Assessment

```bash
# Each student does:
python run.py dialogue \
  --interactive \
  --subject science \
  --rubric science_rubric \
  --use-audio-input \
  --use-sessions \
  --student-id student_name
```

**Each student:**
- Hears questions being read aloud
- Records their answers
- Gets immediate feedback
- Session auto-saves

### Evening: Review Results

```bash
# List all student sessions
python src/agent_a6_session_manager.py list

# View specific student's results
python src/agent_a6_session_manager.py view --session a3f7b2c1

# Export all transcripts for record-keeping
python src/agent_a6_session_manager.py export --session a3f7b2c1 --format csv
```

---

## Troubleshooting

### "Module not found: pyaudio"
```bash
# Install audio support
pip install pyaudio openai
```

### "OPENAI_API_KEY not set"
```bash
# Set your API key
export OPENAI_API_KEY="sk-..."

# On Windows (PowerShell):
$env:OPENAI_API_KEY = "sk-..."
```

### "No questions extracted"
- Make sure your document has questions in format: `Q1) text`, `1. text`, or `1) text`
- Or the system will try to extract them with AI

### "Audio recording failed"
- Make sure microphone is connected and working
- Try: `python src/agent_audio_input.py record --duration 5`

### "Transcription failed"
- Check internet connection (uses OpenAI API)
- Verify `OPENAI_API_KEY` is set

---

## Video of Workflow (Imagine This)

```
[Teacher uploads exam PDF]
        ↓
[System extracts questions]
        ↓
[Students run dialogue command]
        ↓
[Student hears: "What is photosynthesis?"]
        ↓
[Student speaks answer for 15 seconds]
        ↓
[System transcribes voice to text]
        ↓
[AI grades against rubric: 90%]
        ↓
[AI speaks feedback: "Great job..."]
        ↓
[Session saved with all data]
        ↓
[Teacher views results in dashboard]
```

---

## Commands Reference (Cheat Sheet)

```bash
# Setup & Ingestion
python run.py ingest <file> --subject <topic>

# Assessment
python run.py dialogue --interactive --subject <topic> --rubric <rubric_name>
python run.py dialogue --interactive --subject <topic> --rubric <rubric_name> --use-audio-input
python run.py dialogue --interactive --subject <topic> --rubric <rubric_name> --use-sessions --student-id alice

# Grading
python run.py grade "assignment" --answer "student work" --rubric <rubric_name>

# Session Management
python src/agent_a6_session_manager.py list
python src/agent_a6_session_manager.py view --session <id>
python src/agent_a6_session_manager.py export --session <id> --format json
python src/agent_a6_session_manager.py delete --session <id>

# Audio
python src/agent_audio_input.py record --duration 15
python src/agent_audio_input.py transcribe --audio file.wav
```

---

## Next Steps

1. **Try it yourself:**
   ```bash
   python run.py ingest data/input/mathematics/Sample_Calculus_Introduction.txt --subject calculus
   python run.py dialogue --interactive --subject calculus --rubric primary1_math
   ```

2. **Create your first rubric** for your subject

3. **Run an assessment** with students

4. **Review the session results**

5. **Export for archiving**

You're all set! 🎉
