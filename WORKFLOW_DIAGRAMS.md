# System Workflow Diagrams

## High-Level: What Happens When You Use This System

```
┌─────────────────────────────────────────────────────────────────┐
│                   TEACHER / EDUCATOR                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. CREATE CONTENT                                                │
│     ├─ Write exam questions in a document                        │
│     ├─ Save as .pdf, .docx, or .txt                              │
│     └─ Put in: data/input/subject_name/                          │
│                                                                   │
│  2. INGEST DOCUMENT                                               │
│     ├─ Command: python run.py ingest <file> --subject <topic>    │
│     ├─ System reads document                                     │
│     ├─ Extracts questions automatically                          │
│     └─ Saves to vector database                                  │
│                                                                   │
│  3. CREATE GRADING RUBRIC                                         │
│     ├─ Copy example: cp essay_assignment.json my_rubric.json     │
│     ├─ Edit criteria & points                                    │
│     └─ Save to: data/rubrics/                                    │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      STUDENT                                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  4. TAKE ASSESSMENT                                               │
│     ├─ Command: python run.py dialogue --interactive ...          │
│     ├─ System asks: "Question 1: What is...?"                    │
│     ├─ Student answers (text or voice)                           │
│     ├─ System grades instantly: ✓ 90%                            │
│     └─ Repeat for all questions                                  │
│                                                                   │
│  5. AUTOMATIC FEATURES                                            │
│     ├─ 🔊 Questions spoken aloud (optional)                      │
│     ├─ 🎤 Student voice recorded & transcribed                   │
│     ├─ 📊 Instant scores shown                                   │
│     └─ 💾 Everything saved to session                            │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    TEACHER / REVIEWER                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  6. REVIEW RESULTS                                                │
│     ├─ Command: python src/agent_a6_session_manager.py list      │
│     ├─ See all students and their scores                         │
│     ├─ Command: python src/agent_a6_session_manager.py view --s  │
│     ├─ View student's answers with timestamps                    │
│     └─ Command: python src/agent_a6_session_manager.py export    │
│     └─ ... export for Excel spreadsheet                          │
│                                                                   │
│  7. KEEP RECORDS                                                  │
│     ├─ All sessions saved in: data/sessions/                     │
│     ├─ Export formats: JSON, CSV, TXT                            │
│     └─ Auditable: every answer with timestamp                    │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Step-by-Step: Text Assessment Workflow

```
START
  ↓
┌─────────────────────────────────┐
│ python run.py ingest <file>     │
│ --subject math                  │
└─────────────────────────────────┘
  ↓ System loads document & extracts questions
  ↓
┌─────────────────────────────────┐
│ Questions found:                │
│ 1. What is 5 + 3?               │
│ 2. Solve: x + 5 = 12            │
│ 3. What is 20% of 50?           │
└─────────────────────────────────┘
  ↓
┌─────────────────────────────────┐
│ python run.py dialogue          │
│ --interactive                   │
│ --subject math                  │
│ --rubric primary1_math          │
└─────────────────────────────────┘
  ↓ System starts questioning
  ↓
┌─────────────────────────────────┐
│ ❓ Question 1/3:                │
│ What is 5 + 3?                  │
│                                 │
│ Your answer: 8                  │
│                                 │
│ 📊 Scores: 5/5 ✓                │
└─────────────────────────────────┘
  ↓
┌─────────────────────────────────┐
│ ❓ Question 2/3:                │
│ Solve: x + 5 = 12               │
│                                 │
│ Your answer: x = 7              │
│                                 │
│ 📊 Scores: 4/5 ✓                │
└─────────────────────────────────┘
  ↓
┌─────────────────────────────────┐
│ ❓ Question 3/3:                │
│ What is 20% of 50?              │
│                                 │
│ Your answer: 10                 │
│                                 │
│ 📊 Scores: 5/5 ✓                │
└─────────────────────────────────┘
  ↓
┌─────────────────────────────────┐
│ ✅ Assessment Complete!         │
│                                 │
│ Total: 14/15 (93%)              │
│ Average: 4.7/5                  │
└─────────────────────────────────┘
  ↓
END
```

---

## Step-by-Step: Audio Assessment Workflow

```
START
  ↓
┌──────────────────────────────────────────────┐
│ python run.py dialogue --interactive         │
│ --subject biology                            │
│ --rubric biology_rubric                      │
│ --audio                  (speak questions)   │
│ --use-audio-input        (record answers)    │
│ --use-sessions           (save everything)   │
│ --student-id alice_smith                     │
└──────────────────────────────────────────────┘
  ↓
┌──────────────────────────────────────────────┐
│ ✅ Created session: a3f7b2c1                 │
│ 📋 Session: a3f7b2c1                         │
└──────────────────────────────────────────────┘
  ↓
┌──────────────────────────────────────────────┐
│ ❓ Question 1/3:                             │
│ What is photosynthesis?                      │
│                                              │
│ [AI speaks question aloud]                   │
│ 🔊 Audio available: question_1_audio.wav    │
└──────────────────────────────────────────────┘
  ↓
┌──────────────────────────────────────────────┐
│ 🎤 Recording audio answer (15 seconds)...    │
│                                              │
│ [Student speaks their answer]                │
│                                              │
│ Recording... 1s / 15s                        │
│ Recording... 5s / 15s                        │
│ Recording... 10s / 15s                       │
│ [Student finishes]                           │
│                                              │
│ ✓ Audio saved: q1_answer.wav (0.35 MB)     │
└──────────────────────────────────────────────┘
  ↓
┌──────────────────────────────────────────────┐
│ 🔄 Transcribing audio...                     │
│                                              │
│ [OpenAI Whisper processes voice]             │
│                                              │
│ ✓ Transcribed:                               │
│ "Photosynthesis is the process where plants  │
│  use sunlight to create glucose and oxygen"  │
└──────────────────────────────────────────────┘
  ↓
┌──────────────────────────────────────────────┐
│ ⏳ Evaluating answer...                      │
│                                              │
│ [AI grades against rubric]                   │
│                                              │
│ 📊 Scores:                                   │
│ Accuracy: 5/5                                │
│ Completeness: 3/3                            │
│ Total: 8/8 (100%)                            │
└──────────────────────────────────────────────┘
  ↓
[Repeats for Questions 2, 3...]
  ↓
┌──────────────────────────────────────────────┐
│ ✅ Assessment Complete!                      │
│                                              │
│ 📋 Session saved: a3f7b2c1                   │
│                                              │
│ Files saved:                                 │
│ ├─ a3f7b2c1_session.json (all data)         │
│ ├─ q1_answer.wav (student voice)             │
│ ├─ q1_transcription.json (text)              │
│ ├─ q2_answer.wav                             │
│ └─ ...                                       │
│                                              │
│ Total: 24/24 (100%)                          │
└──────────────────────────────────────────────┘
  ↓
END
```

---

## Teacher Review Workflow

```
Later that day...
  ↓
┌──────────────────────────────────────────────┐
│ python src/agent_a6_session_manager.py list  │
└──────────────────────────────────────────────┘
  ↓ See all students
  ↓
┌──────────────────────────────────────────────┐
│ Found 3 sessions:                            │
│  • a3f7b2c1 (alice_smith) - COMPLETED       │
│  • b4g8c3d2 (bob_jones) - COMPLETED         │
│  • c5h9d4e3 (charlie_davis) - COMPLETED    │
└──────────────────────────────────────────────┘
  ↓
┌──────────────────────────────────────────────┐
│ python src/agent_a6_session_manager.py view  │
│ --session a3f7b2c1                           │
└──────────────────────────────────────────────┘
  ↓ See alice's full assessment
  ↓
┌──────────────────────────────────────────────┐
│ Session Report:                              │
│                                              │
│ Student: alice_smith                         │
│ Session: a3f7b2c1                            │
│ Duration: 15 minutes                         │
│ Total Score: 24/24 (100%)                    │
│                                              │
│ Turns:                                       │
│ Turn 1 [10:30] Avatar: "Question 1?"         │
│ Turn 2 [10:31] Student: "Answer 1..."        │
│ Turn 3 [10:32] Avatar: "Question 2?"         │
│ ...                                          │
└──────────────────────────────────────────────┘
  ↓
┌──────────────────────────────────────────────┐
│ python src/agent_a6_session_manager.py       │
│ export --session a3f7b2c1 --format csv       │
└──────────────────────────────────────────────┘
  ↓ Export for Excel
  ↓
┌──────────────────────────────────────────────┐
│ CSV File (Spreadsheet):                      │
│                                              │
│ Turn | Speaker | Time    | Text              │
│─────┼──────────┼─────────┼──────────────     │
│ 1   | Avatar  | 10:30   | Q1: Photos...?    │
│ 2   | Student | 10:31   | Photos is when... │
│ 3   | Avatar  | 10:32   | Q2: Cycles...?    │
│ 4   | Student | 10:33   | Cycles is...      │
└──────────────────────────────────────────────┘
  ↓
┌──────────────────────────────────────────────┐
│ Open in Excel / Google Sheets                │
│ Print for records                            │
│ Calculate statistics                         │
│ Share with students                          │
└──────────────────────────────────────────────┘
  ↓
END
```

---

## System Architecture

```
┌─────────────────────────────────┐
│      CLI Entry Point            │
│      (run.py)                   │
└──────────────┬──────────────────┘
               │
       ┌───────┴───────┐
       │               │
       ↓               ↓
    ┌─────────┐   ┌──────────┐
    │ Ingest  │   │ Dialogue │
    │ (Agent  │   │ (Agent   │
    │  A1)    │   │  A3)     │
    └────┬────┘   └────┬─────┘
         │             │
         ↓             ↓
    ┌─────────────────────────┐
    │  Vector Database        │
    │  (ChromaDB)             │
    │  Stores document chunks │
    └────────┬────────────────┘
             │
             ↓
    ┌─────────────────────────┐
    │  Dialogue Management    │
    │  Asks questions         │
    │  Scores with Rubric     │
    └────────┬────────────────┘
             │
    ┌────────┼────────────────┬─────────┐
    │        │                │         │
    ↓        ↓                ↓         ↓
  ┌──────┐ ┌──────┐  ┌──────────┐ ┌──────────┐
  │ A4:  │ │Audio │  │ A5:      │ │ A6:      │
  │ TTS  │ │Input │  │ Grader   │ │Sessions  │
  │      │ │(ASR) │  │          │ │          │
  └──────┘ └──────┘  └──────────┘ └──────────┘
    │        │           │            │
    └────────┼───────────┼────────────┘
             │           │
             ↓           ↓
        ┌─────────────────────────┐
        │  Session Storage        │
        │  (data/sessions/)       │
        │  - JSON files           │
        │  - Audio recordings     │
        │  - Transcriptions       │
        └─────────────────────────┘
```

---

## From Zero to Assessment (Timeline)

```
Day 1: Setup
├─ 09:00 - Download and install system
├─ 09:15 - Generate OpenAI API key
├─ 09:30 - Run: python run.py ingest <file> --subject <topic>
├─ 09:45 - Create rubric: edit JSON file
└─ 10:00 - ✅ System ready!

Day 2: First Assessment
├─ 09:00 - Student starts: python run.py dialogue --interactive
├─ 09:05 - Question 1: Audio plays + student records answer
├─ 09:10 - Question 2: Same process
├─ 09:15 - Question 3: Same process
├─ 09:20 - ✅ Results displayed with full scores
└─ 09:25 - Session auto-saved

Day 3: Review + Export
├─ 09:00 - python src/agent_a6_session_manager.py list
├─ 09:05 - View all student sessions
├─ 09:10 - Export all as CSV
├─ 09:15 - Open Excel: all assessments in spreadsheet
└─ 09:30 - ✅ Grade book created & archived!
```

Total time investment: ~1 hour setup → unlimited assessments

---

**Use these diagrams to understand the system better!**
