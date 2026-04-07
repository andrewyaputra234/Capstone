# ⚡ Quick Reference Card

## The 3-Step Workflow

```
1️⃣  LOAD YOUR DOCUMENT
    python run.py ingest <file> --subject <topic>

2️⃣  CHOOSE A RUBRIC (or create one)
    ls data/rubrics/
    
3️⃣  RUN ASSESSMENT
    python run.py dialogue --interactive --subject <topic> --rubric <rubric_name>
```

---

## Most Common Commands

| What You Want | Command |
|---|---|
| **Load a document** | `python run.py ingest path/to/file.pdf --subject math` |
| **Quiz yourself** | `python run.py dialogue --interactive --subject math --rubric primary1_math` |
| **Quiz with voice** | `python run.py dialogue --interactive --subject math --rubric primary1_math --use-audio-input` |
| **See student scores** | `python src/agent_a6_session_manager.py view --session <id>` |
| **Export student work** | `python src/agent_a6_session_manager.py export --session <id> --format csv` |
| **Grade an essay** | `python run.py grade "question" --answer "student answer" --rubric essay_assignment` |

---

## File Locations

| What | Where |
|---|---|
| Put YOUR documents here | `data/input/` |
| Rubrics (for grading) | `data/rubrics/` |
| Student sessions save here | `data/sessions/` |
| Audio from students | `data/sessions/q1_answer.wav` |

---

## Creating Your First Rubric

1. Copy an example:
   ```bash
   cp data/rubrics/essay_assignment.json data/rubrics/my_rubric.json
   ```

2. Edit in any text editor. Change:
   - `"name"`: Your rubric name
   - `"criteria"`: What you grade on
   - `"max_score"`: Points per criterion

3. Use in commands:
   ```bash
   python run.py dialogue --interactive --rubric my_rubric
   ```

---

## Example Rubric (Simple)

```json
{
  "name": "Math Quiz",
  "criteria": [
    {
      "name": "Correctness",
      "description": "Is the answer right?",
      "max_score": 5,
      "levels": {
        "0": "Wrong",
        "3": "Partially right",
        "5": "Completely right"
      }
    }
  ]
}
```

---

## Beginner Mistakes (Avoid These)

❌ **"Command not found: run.py"**
- Make sure you're in the `Capstone` folder
- Try: `pwd` (shows current folder)

❌ **"OPENAI_API_KEY not set"**
- You need an OpenAI API key
- Get one: https://platform.openai.com/api-keys
- On Windows: `$env:OPENAI_API_KEY = "sk-..."`

❌ **"No questions found"**
- Format questions as: `Q1) text` or `1. text`
- Or just ask the system to extract them (uses AI)

❌ **"Audio not working"**
- Check microphone with: `python src/agent_audio_input.py record --duration 5`
- If still broken: `pip install pyaudio`

---

## What Each Agent Does

| Agent | What It Does | Command |
|---|---|---|
| **A1** | Loads your PDFs/Word docs | `python run.py ingest` |
| **A3** | Asks questions & tracks dialogue | `python run.py dialogue` |
| **A4** | Speaks questions with voice | `--audio` flag |
| **A5** | Grades with rubric | `python run.py grade` |
| **A6** | Saves all student sessions | `--use-sessions` flag |
| **Audio** | Records student voices | `--use-audio-input` flag |

---

## Full Example: Teacher + Student

**Teacher (5 min setup):**
```bash
# 1. Add exam document
cp ~/my_exam.pdf data/input/biology/

# 2. Load it
python run.py ingest data/input/biology/my_exam.pdf --subject biology

# 3. Create grading rubric
nano data/rubrics/biology_rubric.json
# (Edit and save)
```

**Student (takes 10 min assessment):**
```bash
# Run the quiz with voice
python run.py dialogue \
  --interactive \
  --subject biology \
  --rubric biology_rubric \
  --audio \
  --use-audio-input \
  --use-sessions \
  --student-id alice_smith
```

**Teacher (reviews results):**
```bash
# See all student sessions
python src/agent_a6_session_manager.py list

# View one student's full assessment
python src/agent_a6_session_manager.py view --session <session_id>

# Export for grading spreadsheet
python src/agent_a6_session_manager.py export --session <session_id> --format csv
```

---

## Help Commands

```bash
# See all commands
python run.py --help

# See dialogue options
python src/agent_a3_dialogue.py --help

# See session options
python src/agent_a6_session_manager.py --help

# See audio options
python src/agent_audio_input.py --help
```

---

## Keyboard Shortcuts During Assessment

| Key | What It Does |
|---|---|
| `Ctrl+C` | Stop recording (during voice input) |
| `Enter` | Submit text answer |

---

## Progress Checklist (First Time Users)

- [ ] Read this guide (you're here!)
- [ ] Read `GETTING_STARTED.md` for full details
- [ ] Load a test document: `python run.py ingest data/input/mathematics/ --subject math`
- [ ] Run text-based quiz: `python run.py dialogue --interactive --subject math`
- [ ] Try voice assessment: add `--use-audio-input` flag
- [ ] View session: `python src/agent_a6_session_manager.py list`
- [ ] Export results: `python src/agent_a6_session_manager.py export --session <id> --format csv`
- [ ] Create your own rubric
- [ ] Grade an assignment: `python run.py grade "question" --answer "answer" --rubric your_rubric`

---

## Still Stuck?

Check these files:
- **General questions?** → `GETTING_STARTED.md`
- **Audio issues?** → `AUDIO_INPUT_GUIDE.md`
- **Session management?** → `SESSION_MANAGEMENT_GUIDE.md`
- **Rubric creation?** → `AGENT_A5_RUBRIC_GRADER.md`
- **Requirements met?** → `CAPSTONE_REQUIREMENTS_ASSESSMENT.md`

Or look at the example commands in each guide!

---

## Your System Status

✅ **Ready to use!**

Currently working:
- ✅ Load documents (PDFs, DOCX, TXT)
- ✅ Extract questions automatically
- ✅ Give quizzes (text or voice)
- ✅ Grade with custom rubrics
- ✅ Record student speeches
- ✅ Transcribe to text (Whisper AI)
- ✅ Save everything with session IDs
- ✅ Export results as JSON/CSV

Not yet (for Phase 3):
- ⏳ Beautiful web interface
- ⏳ REST API for integration

**You have 75% of a production system!** 🚀
