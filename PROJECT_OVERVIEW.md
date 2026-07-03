# Project overview

Last updated: 2026-07-01  
Project name in app: **Oral Focus**

## Purpose

This project is a local Streamlit prototype for an AI-assisted oral assessment portal. It supports two main roles:

- **Examiner**: creates an oral assessment, uploads materials, reviews AI-generated questions, optionally prepares avatar videos, verifies grades, adds written feedback, releases final results, and can reset/delete student sessions.
- **Student**: logs in, selects an assigned assessment, reads preparation materials during a timed preparation stage, completes reading-aloud and image-question responses, and later views released results.

The system is designed for a PSLE-style English oral workflow, with one picture stimulus, an optional reading passage, reading-aloud submission, and three image-based oral questions.

## Current product flow

### Login and accounts

- The app has a custom Streamlit login screen with **Student** and **Examiner** roles.
- Demo credentials still exist in `data/users.json`.
- Students can register with their own student ID and password.
- New registered passwords are stored using PBKDF2 hashing.
- Authentication is still prototype-grade and should not be treated as production security.

### Examiner flow

1. Examiner logs in.
2. Examiner opens **Assign assessment**.
3. Examiner uploads one picture stimulus.
4. Examiner may upload one reading passage.
5. Examiner selects a registered student.
6. Examiner selects or uploads an English oral rubric.
7. The app extracts/generates oral questions from the uploaded material.
8. Examiner can adjust the generated questions before assignment.
9. If Simli avatar is enabled, the app attempts to prepare examiner-avatar videos for the final questions before assignment.
10. Examiner previews avatar clips when available.
11. Examiner assigns the assessment to the student.
12. After the student completes the assessment, examiner opens **Results and review**.
13. Examiner reviews reading-aloud grade when present.
14. Examiner reviews each image-question result.
15. Examiner can adjust rubric scores and type optional feedback notes.
16. Examiner releases final results only after required components are verified.

### Student flow

1. Student logs in.
2. Student first sees a page to select an assigned assessment.
3. Student continues to the preparation stage.
4. Preparation materials are shown separately from the assessment page.
5. A 10-minute preparation timer starts once the preparation materials have loaded.
6. Student can continue early, but once they continue they cannot return to the materials.
7. During preparation, the app should use already-saved avatar references from examiner-side preparation; it should not create new avatar videos for the student.
8. Student enters the assessment page.
9. If a reading passage was assigned, student completes reading aloud first.
10. Student answers each image question by typing or recording/transcribing.
11. If the first response is clearly weak or unrelated, the AI gives one guiding question.
12. The guiding question is adapted to the student's first response. It should briefly refer to what the student said and guide them to clarify, correct, connect to the picture/topic, give a reason, or add one visible detail.
13. Student can answer again after the guiding question.
14. The first answer and guided follow-up answer are combined for grading.
15. If the first response is good enough, the app moves to the next question.
16. After all questions are completed, student waits for examiner release.
17. Once released, student can view grades, recordings/transcripts, and examiner feedback notes.

## Current result and feedback behavior

- AI grades are stored first as provisional grades.
- Examiner review creates or updates `final_grading`.
- The original AI grade is preserved.
- Examiner notes are saved under `examiner_review.note`.
- Student results only appear after `results_released_at` is set.
- Student results now show examiner-typed feedback for:
  - reading-aloud submission;
  - each image-question result.

## Avatar integration

The app supports two avatar presentation providers:

- **Anam** for live WebRTC examiner avatars that speak the already-selected prompt with `talk()`.
- **Simli** as the older static-video fallback that pre-generates HLS/MP4 clips.

Important design decision:

- The avatar provider is not the AI examiner brain.
- The app still controls the question text, grading, guiding-question logic, state transitions, and stored transcripts.
- The provider only presents already-decided examiner text.

Recommended Anam environment variables:

```env
AVATAR_PROVIDER=anam
ENABLE_ANAM_AVATAR=true
ANAM_API_KEY=...
ANAM_PERSONA_ID=...
```

Instead of `ANAM_PERSONA_ID`, you can configure an ephemeral runtime persona:

```env
ANAM_AVATAR_ID=...
ANAM_VOICE_ID=...
ANAM_LLM_ID=...
ANAM_SYSTEM_PROMPT=You are a calm oral examiner. Speak only the assessment prompt provided by the application.
```

Simli fallback environment variables:

```env
AVATAR_PROVIDER=simli
ENABLE_SIMLI_AVATAR=true
SIMLI_API_KEY=...
SIMLI_FACE_ID=...
OPENAI_API_KEY=...
```

Current avatar behavior:

- In Anam mode, examiner questions and guiding follow-ups are spoken live during the assessment.
- In Anam mode, assignment creation does not wait for static avatar videos.
- In Simli mode, avatar videos are prepared during examiner assignment/preview, not during the student assessment.
- The assessment must still work even if avatar playback fails.

## Data storage

This is a local prototype using file-backed JSON and local folders.

Important data locations:

- `data/users.json`  
  Stores local student/examiner users.

- `data/student_assignments.json`  
  Stores assignment records, questions, student submissions, grading, examiner reviews, release status, and avatar references.

- `data/rubrics/`  
  Stores built-in and custom oral rubrics.

- `data/sessions/`  
  Stores session files and some recorded-session metadata.

- `data/input/`  
  Stores uploaded or sample input materials.

- `data/output/`  
  Stores generated chunk files and processing outputs.

- `data/chroma_db/`  
  Stores vector databases created during ingestion.

- `data/avatar_cache/` or related local avatar cache paths when configured/created by the app.  
  Used for cached avatar video files when the app downloads playable video assets.

The JSON store uses atomic writes to reduce corruption risk, but it is not designed for many concurrent users. For deployment, move assignments/users/results to SQLite or Postgres.

## Important files

### Main application

- `streamlit_app.py`  
  Main Streamlit web app. Contains login, examiner portal, student portal, preparation timer, assessment pages, avatar preview/rendering, and student results rendering.

### Persistence and assignment lifecycle

- `src/exam_portal_store.py`  
  Handles users, authentication, student registration, assignments, reading submissions, image-question results, examiner reviews, result release, reset, and delete.

### AI orchestration

- `src/crew_orchestrator.py`  
  Coordinates ingestion, question generation, oral-turn evaluation, guiding-question decisions, and grading workflow.

### Avatar client

- `src/simli_avatar.py`  
  Creates TTS audio through OpenAI, sends audio to Simli, and returns avatar video asset information.

### Voice and transcription

- `src/voice_assessment.py`  
  Handles voice transcription and recording indicators.

- `src/audio_recorder_streamlit.py`  
  Streamlit audio recording component/helper.

### Ingestion and retrieval

- `src/agent_a1_ingestion.py`  
  Loads and chunks documents/images.

- `src/agent_image_extractor.py`  
  Extracts page images or stores image stimuli.

- `src/vector_store.py`  
  Builds and reads local Chroma vector databases.

- `src/subject_manager.py`  
  Manages subject metadata and document paths.

### Grading and rubrics

- `src/agent_a5_grader.py`  
  Grading agent logic.

- `src/rubric_engine.py`  
  Rubric parsing/normalization and grading helpers.

- `src/rubric_generator.py`  
  Custom rubric generation/handling.

### Tests

- `test_exam_portal_store.py`
- `test_grading_resilience.py`
- `test_persistence_safety.py`
- `test_question_fallback.py`
- `test_simli_avatar.py`
- `test_voice_assessment.py`

Current full test command:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```

Recent known result: **28 tests passing**.

## How to run locally

From the project root:

```powershell
.\.venv\Scripts\streamlit.exe run streamlit_app.py
```

Alternative:

```powershell
streamlit run streamlit_app.py
```

If `.env` values are not available in the terminal, enable environment-file loading in the IDE or set variables directly in PowerShell.

## Current theme/UI direction

The app uses a light green/cream exam-portal theme named **Oral Focus**.

Important UI goals:

- Friendly for students.
- Still formal enough for an exam setting.
- Avoid dark components where text becomes unreadable.
- Login, role selection, tab buttons, upload areas, response buttons, and result cards should remain visually consistent.
- Student assessment layout should be clear and sequential, with the examiner/avatar area, stimulus image, and response controls arranged so students know exactly what to do next.

## Recent fixes and behavioral changes

- Replaced deprecated `use_container_width` usage with `width="stretch"`.
- Fixed repeated-question and over-guiding behavior by tightening oral-turn follow-up rules.
- Added student registration with hashed passwords.
- Improved login error handling for incorrect credentials.
- Added examiner delete/reset options:
  - reset student results/sessions while keeping assessment materials;
  - delete entire assessment/test.
- Improved light theme styling for upload boxes, tabs, role buttons, password field, result cards, and text areas.
- Added 10-minute preparation timer.
- Split student flow so assessment selection and preparation materials are not on the same page.
- Locked preparation materials once the student moves into the assessment.
- Prevented completed assignments from returning students to the preparation stage.
- Added reading-passage skip option.
- Prevented reading passage from reappearing after the final image question.
- Removed unnecessary “thank you / recorded response” transition after submission/skip.
- Moved avatar creation away from student assessment loading and toward examiner-side preparation.
- Added terminal-style avatar preparation logs.
- Added student-visible examiner feedback notes after results are released.
- Made guiding questions more adaptive to the student's first response instead of generic follow-up prompts.

## Known issues and risks

### Avatar readiness

Simli may return HLS/MP4 URLs before they are playable. The app may log repeated 404 responses like:

```text
{"error":"File not found"}
```

This means the returned video URL exists in Simli's response but the video file is not ready yet. It does not always mean the whole app is broken, but it can make avatar preview slow or unreliable.

### Local JSON persistence

The app is good for a local prototype but not production multi-user deployment.

Risks:

- race conditions if several users write at once;
- JSON corruption if interrupted despite atomic write safeguards;
- no proper database constraints;
- local files may contain sensitive student artifacts.

### Authentication

Still prototype-grade.

Missing production features:

- password reset;
- rate limiting;
- account approval;
- strong session management;
- role-protected server routes;
- audit logs.

### Runtime data in Git

Some runtime artifacts may already be tracked or present in the repository.

Before public deployment or submission, decide what is sample data and what should be removed from Git history/index.

### Python/audio warnings

Some audio tests may show Python 3.13 compatibility/deprecation warnings from audio dependencies. Tests currently pass.

## Recommended next steps

1. Stabilize the full examiner-to-student-to-results happy path without relying on avatar playback.
2. Keep Simli avatar optional behind `ENABLE_SIMLI_AVATAR`.
3. For demo reliability, prepare avatar clips early and verify they are playable before the student begins.
4. Add a simple admin/seed-user flow so examiners can manage student accounts cleanly.
5. Move persistence from JSON to SQLite if more realistic multi-user testing is needed.
6. Add visual regression checks or a UI checklist for dark-theme component leaks.
7. Keep `CODEBASE_HEALTH_AUDIT_2026-06-26.md` as the audit history, and use this file as the current broad project context.

## Useful context for future assistance

When asking another assistant, teammate, or lecturer for help, provide:

1. this `PROJECT_OVERVIEW.md`;
2. `streamlit_app.py`;
3. `src/exam_portal_store.py`;
4. `src/crew_orchestrator.py`;
5. `src/simli_avatar.py` if the question involves avatars;
6. the relevant test file if the question involves a regression.

For broad architectural advice, this overview may be enough. For exact code changes, provide the relevant source file too.
