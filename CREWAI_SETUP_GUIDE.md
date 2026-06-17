# CrewAI Integration Guide

This project combines **CrewAI multi-agent orchestration** with the existing agent stack:

| Layer | Module | Role |
|-------|--------|------|
| Ingestion | `src/main.py` | Chunk, embed, extract images |
| Dialogue | `src/agent_a3_dialogue.py` | Question extraction, Q&A |
| Grading | `src/agent_a5_grader.py` | Rubric scoring + tutoring feedback |
| Sessions | `src/agent_a6_session_manager.py` | Transcript + export |
| Orchestration | `src/crew_orchestrator.py` | CrewAI agents + real tools |

## Setup

```powershell
cd Capstone
venv\Scripts\activate
pip install -r requirements.txt

# .env file
OPENAI_API_KEY=sk-your-key
CREWAI_MODEL=gpt-3.5-turbo   # optional, default gpt-3.5-turbo
```

Verify:

```powershell
python verify_setup.py
python test_crew_integration.py
python test_crew_integration.py --live
```

## CLI (CrewAI)

```powershell
# Initialize crew config check
python run.py crew --subject math --rubric primary_math --crew-action init

# Ingest document + CrewAI analysis + question extraction
python run.py crew data/sample.txt --subject math --rubric primary_math --crew-action ingest

# Grade one response (A5 + CrewAI), saves session
python run.py crew --subject math --rubric primary_math --crew-action assess ^
  --query "What is 5 + 3?" --answer "Eight"

# Extract oral exam questions from ingested subject
python run.py crew --subject math --rubric primary_math --crew-action oral
```

## Streamlit UI

```powershell
streamlit run streamlit_app.py
```

Tabs:

1. **Ingest Document** – real pipeline + CrewAI analysis
2. **Oral Assessment** – document questions, A5 grading + Crew enrichment
3. **Grade Response** – single Q&A evaluation
4. **Q&A Dialogue** – multi-turn tutor with vector context
5. **Results** – in-memory + persisted Agent A6 sessions

Legacy full UI (non-CrewAI): `streamlit run app.py`

## Architecture

```
Upload → ingest_document() → ChromaDB + images
              ↓
       DialogueManager.extract_questions()
              ↓
Student answer → RubricGrader (authoritative scores)
              ↓
       CrewAI agents (pedagogical analysis + feedback)
              ↓
       SessionManager (persist transcript + scores)
```

CrewAI tools call real infrastructure via `_CrewRuntimeContext` (subject, rubric, session).

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `OPENAI_API_KEY not set` | Create `.env` in project root |
| No questions extracted | Format as `Q1) text` or ingest richer content |
| ChromaDB locked | Close Streamlit tabs using the subject; refresh cache |
| Crew slow / costly | Set `CREWAI_MODEL=gpt-3.5-turbo` in `.env` |
