# Codex Session Handoff

Last updated: 2026-07-27

This file summarizes the recent Codex work so the project can be moved to another PC and continued with context.

## Project Status

The project is a local Streamlit oral-assessment portal for a PSLE-style English Oral workflow. It supports:

- examiner assignment creation;
- picture-stimulus question generation;
- optional reading-aloud passage;
- student preparation timer;
- one-time student voice submissions;
- Anam live-avatar prompt delivery;
- AI grading with examiner verification;
- final result release to students.

The latest known automated test result is:

```powershell
.\.venv\Scripts\python.exe -m unittest discover
```

Result: `40 tests OK`.

## Current Git State

Latest local commit:

```text
25eea7c stricter
```

As of this handoff update, the working tree still has uncommitted runtime/test-data changes:

- `data/student_assignments.json`
- `data/subject_config.json`
- `data/rubrics/examiner_psle_oral_psle_singapore_oral_combined_strict_upload_3.json`

These appear to be assignment/rubric test data, not core app code. Commit them only if the new test assignment and uploaded rubric should be preserved in repo history.

## Important Run Command

On this machine, `streamlit.exe` was blocked by Windows Application Control because the executable launcher was unsigned.

Use this instead:

```powershell
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

Or, if the PowerShell profile wrapper is available:

```powershell
streamlit run streamlit_app.py
```

The local app URL is usually:

```text
http://localhost:8501
```

## Environment Variables

Do not commit `.env` because it contains API keys.

The other PC needs its own `.env` with the required values. Important settings currently used include:

```env
OPENAI_API_KEY=...
AVATAR_PROVIDER=anam
ENABLE_ANAM_AVATAR=true
ANAM_API_KEY=...
ANAM_PERSONA_ID=...
PREPARATION_MINUTES=10
FAST_PHOTO_QUESTION_GENERATION=true
FAST_READING_MATERIAL_PREP=true
FAST_READING_SUBMISSION=true
DEFERRED_READING_AI_GRADING=true
FAST_ASSESSMENT_RESPONSE_FLOW=true
FAST_ORAL_TURN_EVALUATION=true
ALLOW_STUDENT_RERECORD=false
ALLOW_READING_SKIP=false
QUESTION_REVIEW_CREW_ANALYSIS=false
VISION_QUESTION_MODEL=gpt-4o
```

Anam can alternatively be configured with avatar/voice/LLM IDs instead of a persona ID if needed.

## Recent Changes

### Student Experience

- Added a student progress indicator:
  `Preparation -> Reading Aloud -> Image Questions -> Submitted -> Results`.
- Fixed raw HTML showing in the progress indicator by rendering compact HTML.
- Set preparation time to 10 minutes using `PREPARATION_MINUTES`.
- Timer now starts only after required materials are ready.
- Preparation materials lock after the student enters assessment.
- Reading aloud is a one-time recording/submission.
- Student does not see or edit the transcript before submitting.
- Custom loading overlays replace the default blurred Streamlit loading behavior.

### Question Generation Performance

- Photo question generation uses the fast vision path for standalone images.
- Reading passage preparation during assignment creation now uses a faster save/extract path.
- The app no longer runs full chunk/vector ingestion for a reading passage during question-review generation unless the fast path fails.
- This avoids extra waiting when generating review questions from a photo plus reading passage.

### Avatar Behavior

- Anam live avatar is used as the current provider.
- The avatar is presentation-only; the application still controls questions, grading, navigation, and state.
- Avatar speaks the main question and, when needed, one guiding question.
- Extra silence nudges and repeated "still here" behavior were removed.
- If avatar setup fails, the prompt remains available as text so the assessment can continue.

### Guiding Questions

- Guiding questions are now more adaptive to the student's answer.
- Generic repeated prompts were reduced.
- The system guides most incomplete answers unless the first response is already strong.
- The first answer and guided response are combined for final grading.

### Reading Aloud Grading

- Reading-aloud submission is fast.
- AI reading grading is deferred so the student can continue without waiting.
- Examiner still verifies the final grade before release.
- The reading assessment uses transcript completeness and broad delivery indicators, but examiner judgement remains required for pronunciation, expression, and audio quality.

### Examiner Review

- Results/review layout was improved.
- Response evidence and AI/final grades are on the left.
- Verify/adjust controls are on the right.
- The review page now shows AI score, final score, score adjustment, review status, release status, and evidence status.
- AI grading comments were made darker for readability without changing the rest of the UI.
- Fixed an issue where the 3rd question had to be verified twice before the release button appeared. The review dropdown now stores assignment IDs instead of stale assignment objects.

### Strict Oral Scoring And Avatar Replay

- Added stricter PSLE-style grading guidance so the AI starts conservatively and only awards top marks when the answer clearly meets top-band descriptors.
- Added deterministic score caps for very short, generic, unsupported, fragmented, or weakly relevant oral answers.
- Low and mid-range score feedback is now kept fairer and less overly positive.
- Avatar controls were clarified with `Start` and `Play again` behavior.
- Video avatar renderers now include a replay button for manually replaying examiner prompts.
- The preparation timer is rendered after materials are available so the timer starts with the actual preparation view.

### Report Documentation

Updated report-related files:

- `PROJECT_OVERVIEW.md`
- `IMPLEMENTATION_REPORT_SUMMARY.md`
- `CODEBASE_AUDIT_AND_FIX_PLAN.md`

These contain implementation details suitable for the written report.

## Files To Move Through Git

Commit code and documentation files, for example:

```powershell
git add streamlit_app.py src/rubric_engine.py src/agent_a5_grader.py CODEX_SESSION_HANDOFF.md
git commit -m "Tighten oral grading and improve avatar replay"
git push
```

If preserving the latest uploaded rubric/test assignment data is intentional, commit it separately:

```powershell
git add data/subject_config.json data/student_assignments.json data/rubrics/examiner_psle_oral_psle_singapore_oral_combined_strict_upload_3.json
git commit -m "Add strict oral practice rubric test data"
```

On the other PC:

```powershell
git pull
```

Then recreate `.env` locally on the other PC.

## Do Not Commit

Avoid committing:

- `.env`
- real API keys;
- real student data;
- temporary audio recordings;
- generated session files;
- local runtime caches.

Check before committing:

```powershell
git status
```

## Suggested Next Improvements

Possible next items:

- Add browser-based manual QA checklist screenshots for the report.
- Polish the examiner overview dashboard further.
- Add result export for examiner-verified grades.
- Refactor `streamlit_app.py` into smaller modules.
- Move local JSON storage to SQLite for safer multi-user testing.
- Improve reading-aloud scoring rubric details for fluency, pronunciation, pacing, and expression.

## Quick Continuation Prompt

When continuing with Codex on another PC, paste this:

```text
Please read CODEX_SESSION_HANDOFF.md, PROJECT_OVERVIEW.md, and IMPLEMENTATION_REPORT_SUMMARY.md first. Continue helping me with the Streamlit oral assessment portal from the latest state.
```
