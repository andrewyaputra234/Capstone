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

**Start here:** [QUICK_REFERENCE.md](QUICK_REFERENCE.md) ⚡ (60 seconds)

| Guide | When to Read |
|---|---|
| [QUICK_REFERENCE.md](QUICK_REFERENCE.md) | Command cheat sheet (START HERE!) |
| [GETTING_STARTED.md](GETTING_STARTED.md) | Complete beginner walkthrough |
| [WORKFLOW_DIAGRAMS.md](WORKFLOW_DIAGRAMS.md) | Visual flowcharts |
| [AUDIO_INPUT_GUIDE.md](AUDIO_INPUT_GUIDE.md) | Recording & voice features |
| [SESSION_MANAGEMENT_GUIDE.md](SESSION_MANAGEMENT_GUIDE.md) | Saving assessments |
| [AGENT_A5_RUBRIC_GRADER.md](AGENT_A5_RUBRIC_GRADER.md) | Creating rubrics |
| [CAPSTONE_REQUIREMENTS_ASSESSMENT.md](CAPSTONE_REQUIREMENTS_ASSESSMENT.md) | Requirements mapping |

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
| Web UI | ⏳ Coming |
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

1. Read [QUICK_REFERENCE.md](QUICK_REFERENCE.md) (2 min)
2. Load your first document (3 min)
3. Run a quiz (5 min)
4. Create a custom rubric (5 min)
5. Use in your classroom!

## Troubleshooting

**"Command not found"** → Activate virtual environment first
**"OPENAI_API_KEY not set"** → Get key from https://platform.openai.com/api-keys
**"No questions found"** → Format as "Q1) text" or let AI extract them
**"Audio not working"** → Check microphone or run `pip install pyaudio`

More help: See [GETTING_STARTED.md](GETTING_STARTED.md)

---

**Start with [QUICK_REFERENCE.md](QUICK_REFERENCE.md) →**

Built for educators. Powered by AI. Run on your machine.
