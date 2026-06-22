# 🎓 Multi-Agent Oral Assessment System

An AI-powered system for giving oral assessments to students with automatic grading, feedback, and session tracking.

## What Can You Do?

✅ **Load any document** (PDF, DOCX, TXT)  
✅ **Extract exam questions** automatically  
✅ **Conduct oral assessments** with text or voice  
✅ **Record student voices** and transcribe automatically  
✅ **Grade instantly** against your custom rubric  
✅ **Save everything** with one command  
✅ **Export results** as JSON/CSV for record-keeping  

## Quick Start (2 minutes)

### Web UI For Current PSLE Oral Flow

```bash
streamlit run streamlit_app.py
```

Use this app for the current split oral workflow: optional picture stimulus upload, optional reading passage upload, reading aloud section, and three stimulus-based conversation questions.

### Examiner and student workflow

1. Start the app with the project virtual environment: `\.venv\Scripts\streamlit.exe run streamlit_app.py`.
2. Log in as an examiner, select a registered student, upload one or more picture stimuli and reading passages, then choose the exact picture and optional passage for that student.
3. Choose the built-in **PSLE English Oral** rubric or upload a validated custom English Oral JSON rubric. The selected rubric is saved with the assignment and used by the AI grader.
4. The app creates a separate assignment for that student and saves the generated image questions.
5. The student logs in, completes the optional reading passage and the image questions, and receives the AI result. The reading-aloud submission is graded only against the selected rubric's reading-delivery criteria. If an initial image answer is clearly too weak or unrelated, the AI examiner gives one focused guiding question before the final grade.
6. The examiner opens **Results and review** to see both the original AI grade and the final verified grade. They must verify the reading-aloud grade (when assigned) and every image-question grade, then select **Approve and release final results**. Criterion-level changes do not overwrite the AI record.

Students can choose **Type response** or **Speak into microphone** for the reading passage and each image question. A spoken answer is transcribed and the recording is available to the examiner with advisory pace/pitch indicators. A reading grade is therefore provisional and must be checked against the recording; these indicators are not a pronunciation, accent, emotion, or official oral-exam score. Students submit each assigned assessment only once and cannot see grades until the examiner releases the verified final results.

The local register is [`data/users.json`](data/users.json). Add a student there before trying to assign an assessment. This is a local prototype login, not production authentication.

### 1. Load a Document

```bash
python run.py ingest data/input/mathematics/ --subject math
```

### 2. Run an Assessment

```bash
python run.py dialogue --interactive --subject math --rubric primary1_math
```

### 3. With Audio (Optional)

```bash
python run.py dialogue --interactive --subject math --rubric primary1_math --audio --use-audio-input --use-sessions --student-id alice_smith
```

## Documentation

**Start here:** [Quick Reference](ignore/QUICK_REFERENCE.md) ⚡ (60 seconds)

| Guide | When to Read |
|---|---|
| [Quick Reference](ignore/QUICK_REFERENCE.md) | Command cheat sheet (START HERE!) |
| [Getting Started](ignore/GETTING_STARTED.md) | Complete beginner walkthrough |
| [WORKFLOW_DIAGRAMS.md](WORKFLOW_DIAGRAMS.md) | Visual flowcharts |
| Audio input guide | Not currently included in this repository |
| [SESSION_MANAGEMENT_GUIDE.md](SESSION_MANAGEMENT_GUIDE.md) | Saving assessments |
| Rubric guide | [RUBRIC_GUIDE.md](RUBRIC_GUIDE.md) |
| [Requirements assessment](ignore/CAPSTONE_REQUIREMENTS_ASSESSMENT.md) | Requirements mapping |

## Installation (3 minutes)

```bash
# 1. Navigate to project
cd Capstone

# 2. Activate virtual environment
venv\Scripts\activate  # Windows
source venv/bin/activate  # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set OpenAI API key
$env:OPENAI_API_KEY = "sk-your-key-here"  # Windows
export OPENAI_API_KEY="sk-your-key-here"  # Mac/Linux

# 5. You're ready!
python run.py --help
```

## Common Tasks

```bash
# Load a document
python run.py ingest data/input/biology/exam.pdf --subject biology

# Take a text quiz
python run.py dialogue --interactive --subject biology --rubric biology_rubric

# Take with voice recording
python run.py dialogue --interactive --subject biology --rubric biology_rubric --use-audio-input

# Grade an assignment
python run.py grade "assignment question" --answer "student answer" --rubric essay_assignment

# View student sessions
python src/agent_a6_session_manager.py list

# Export results to Excel
python src/agent_a6_session_manager.py export --session <id> --format csv
```

## File Structure

```
Capstone/
├── run.py                          # Main entry point
├── data/
│   ├── input/                      # Your documents
│   ├── rubrics/                    # Grading rubrics
│   ├── sessions/                   # Saved assessments
│   └── output/                     # Generated audio
├── src/
│   ├── agent_a1_ingestion.py       # Load documents
│   ├── agent_a3_dialogue.py        # Ask questions
│   ├── agent_a4_avatar.py          # Speak aloud
│   ├── agent_a5_grader.py          # Grade assignments
│   ├── agent_a6_session_manager.py # Track sessions
│   ├── agent_audio_input.py        # Record voice
│   └── ...
└── *.md files                      # Documentation
```

## System Status

| Feature | Status |
|---|---|
| Document ingestion | ✅ Complete |
| Question extraction | ✅ Complete |
| Dialogue Q&A | ✅ Complete |
| Text-to-speech | ✅ Complete |
| Speech-to-text | ✅ Complete |
| Rubric grading | ✅ Complete |
| Session tracking | ✅ Complete |
| Export (JSON/CSV) | ✅ Complete |
| Examiner/student web UI | ✅ Local prototype complete |
| REST API | ⏳ Coming |

**Current: 75% feature complete** - Ready for use!

## For Your Capstone Project

This system implements core requirements:
- ✅ Session management (FR-1 to FR-3)
- ✅ Audio recording & ASR (FR-4 to FR-6)
- ✅ Paper ingestion (FR-7 to FR-9)
- ✅ Dialogue & agents (FR-10 to FR-12)
- ✅ Avatar output (FR-13 to FR-14)
- ✅ Transcript logging (FR-15 to FR-16)
- ✅ Feedback & rubrics (FR-17 to FR-19)
- ⏳ Web UI (Phase 3)
- ⏳ REST API (Phase 3)

See [CAPSTONE_REQUIREMENTS_ASSESSMENT.md](CAPSTONE_REQUIREMENTS_ASSESSMENT.md) for details.

## Next Steps

1. Read the [Quick Reference](ignore/QUICK_REFERENCE.md) (2 min)
2. Load your first document (3 min)
3. Run a quiz (5 min)
4. Create a custom rubric (5 min)
5. Use in your classroom!

## Troubleshooting

**"Command not found"** → Activate virtual environment first
**"OPENAI_API_KEY not set"** → Get key from https://platform.openai.com/api-keys
**"No questions found"** → Format as "Q1) text" or let AI extract them
**"Audio not working"** → Check microphone or run `pip install pyaudio`

More help: See [Getting Started](ignore/GETTING_STARTED.md)

---

**Start with the [Quick Reference](ignore/QUICK_REFERENCE.md) →**

Built for educators. Powered by AI. Run on your machine.
