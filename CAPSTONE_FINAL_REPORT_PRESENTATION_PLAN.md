# Capstone Final Report And Presentation Plan

Last updated: 2026-07-28

This file is a practical checklist for finishing the final Capstone report and arranging the final presentation/demo for this project.

## Important Dates

Based on the committee reminder:

- Final Capstone report deadline: 2026-07-19, 11:59 PM
- Presentation/demo window: 2026-07-27 to 2026-08-05
- Last allowed presentation date: 2026-08-05, Wednesday
- Suggested presentation duration: 30 minutes
- Suggested split: 20 minutes presentation plus demo, 10 minutes Q&A

Important: today is 2026-07-28. The report deadline has already passed. If the final report has not been submitted, submit the latest complete version immediately and inform the academic supervisor as soon as possible.

## Immediate Action Checklist

Do these first.

- Confirm whether the final report was already submitted.
- If not submitted, submit immediately or ask the academic supervisor what to do about late submission.
- Email the academic supervisor and examiner to arrange the presentation slot.
- Offer 2-3 possible times between 2026-07-28 and 2026-08-05.
- Decide whether the demo will be live, recorded, or both.
- Prepare a clean demo dataset with no real student data or API keys shown.
- Commit only the code/docs that should be preserved.
- Avoid committing `.env`, real student data, audio recordings, generated session files, and local caches.

## Suggested Email To Arrange Presentation

Subject:

```text
Capstone Final Presentation Scheduling - Oral Focus
```

Email body:

```text
Dear [Supervisor Name] and [Examiner Name],

I would like to arrange my final Capstone presentation and demonstration for my project, Oral Focus, within the required presentation window.

My available slots are:

1. [Date and time]
2. [Date and time]
3. [Date and time]

The presentation will be about 30 minutes, with around 20 minutes for the project presentation and demo, followed by 10 minutes of Q&A.

The project is a Streamlit-based AI-assisted PSLE-style English Oral assessment portal with examiner assignment creation, student preparation, voice submissions, avatar prompt delivery, AI grading, examiner verification, and final result release.

Please let me know which slot works best.

Thank you.

Best regards,
[Your Name]
```

## Project Summary For Presentation

Project name in app: Oral Focus

One-sentence summary:

```text
Oral Focus is a local Streamlit prototype that supports PSLE-style English Oral assessment by helping examiners create assignments, generate picture-stimulus questions, collect student voice responses, provide AI-assisted grading, and release only examiner-verified results.
```

Problem being addressed:

- Oral assessment practice can be time-consuming for teachers to prepare, conduct, grade, and review.
- Students need structured practice with reading aloud and stimulus-based conversation.
- AI-generated feedback is useful, but final grading should still be checked by a human examiner.

Main users:

- Examiner or teacher
- Student

Core value:

- Reduces manual setup effort.
- Creates consistent oral-practice workflows.
- Captures voice evidence and transcripts.
- Gives fast provisional AI feedback.
- Keeps examiner verification before results are released.

## Features To Highlight

Use these as your main presentation points.

- Examiner login and student assignment creation.
- Picture stimulus upload.
- Optional reading passage upload.
- PSLE-style question generation from the uploaded image.
- Examiner review/editing of generated questions before assignment.
- 10-minute student preparation stage.
- Preparation timer starts only after materials are ready.
- One-time reading-aloud submission.
- One-time student voice submissions for oral questions.
- Speech-to-text transcription.
- Adaptive guiding question if the first answer is weak.
- First answer and guided answer are combined for grading.
- Anam live avatar speaks examiner prompts.
- Avatar is presentation-only; app logic still controls assessment state.
- AI grading uses custom rubrics.
- Stricter PSLE-style score caps reduce overly generous grading.
- Examiner review page shows AI grade, final grade, evidence, review state, and release state.
- Students only see results after examiner release.

## Architecture Summary

Use this if they ask how the system works technically.

Main app:

- `streamlit_app.py`
- Handles login, examiner portal, student portal, preparation timer, assessment pages, avatar rendering, and student results.

Persistence:

- `src/exam_portal_store.py`
- Stores users, assignments, submissions, reviews, releases, resets, and deletes.

AI orchestration:

- `src/crew_orchestrator.py`
- Handles question generation, oral-turn evaluation, guiding-question decisions, and grading workflow.

Rubric grading:

- `src/rubric_engine.py`
- Applies rubric criteria and stricter conservative score caps.

Feedback generation:

- `src/agent_a5_grader.py`
- Generates spoken-style tutoring feedback.

Voice and transcription:

- `src/voice_assessment.py`
- Saves recordings, transcribes responses, and provides advisory delivery indicators.

Avatar:

- `src/anam_avatar.py`
- Creates live Anam avatar sessions.

Data storage:

- Local JSON and local folders under `data/`.
- This is acceptable for prototype/demo use, but SQLite or Postgres would be better for production.

## Suggested 20-Minute Presentation Flow

Target timing:

| Time | Section | What To Say |
|---|---|---|
| 0:00-1:30 | Introduction | Introduce Oral Focus and the PSLE-style English Oral problem. |
| 1:30-3:30 | Motivation | Explain why preparation, voice collection, grading, and review are hard to manage manually. |
| 3:30-5:30 | Objectives | Explain examiner workflow, student workflow, AI-assisted feedback, and examiner verification. |
| 5:30-8:00 | System Design | Show architecture: Streamlit UI, local JSON store, AI generation, transcription, avatar, rubric grading. |
| 8:00-16:30 | Demo | Run through examiner assignment, student attempt, AI grading, examiner verification, and student results. |
| 16:30-18:30 | Evaluation | Mention testing, validation, and demo constraints. |
| 18:30-20:00 | Limitations And Future Work | Mention prototype storage, privacy, production security, browser QA, and scaling. |

Then leave about 10 minutes for Q&A.

## Live Demo Script

Use a clean test account and non-sensitive sample materials.

### Demo Part 1: Start The App

Command:

```powershell
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

Expected URL:

```text
http://localhost:8501
```

Say:

```text
This is a local Streamlit prototype. It is designed for a controlled demo and local testing rather than public deployment.
```

### Demo Part 2: Examiner Creates Assignment

Show:

- Examiner login.
- Assign assessment page.
- Select a registered student.
- Upload picture stimulus.
- Upload optional reading passage.
- Select or upload oral rubric.
- Generate questions.
- Review generated questions.
- Assign assessment.

Say:

```text
The examiner remains in control before the student sees the assignment. AI helps generate draft oral prompts, but the examiner can review and adjust them.
```

### Demo Part 3: Student Preparation

Show:

- Student login.
- Select assigned assessment.
- Preparation materials page.
- 10-minute timer.

Say:

```text
The timer starts only after the preparation materials are available, so the student does not lose preparation time while the app is still loading.
```

### Demo Part 4: Reading Aloud

Show:

- Reading passage.
- One-time recording/submission.
- Student does not edit transcript before submission.

Say:

```text
Reading aloud is handled as a one-shot exam-style submission. The recording and transcript are saved for examiner review.
```

### Demo Part 5: Image Questions And Avatar Prompt

Show:

- Avatar or text prompt.
- Student records response.
- If response is weak, guiding question appears.
- Student answers guided follow-up.

Say:

```text
The avatar is not making assessment decisions. The application controls the question, guidance decision, grading, and stored transcript. The avatar only presents the already-selected examiner text.
```

### Demo Part 6: AI Grading

Show:

- Saved answer.
- Rubric scores.
- Feedback.
- Evidence.

Say:

```text
The AI grade is provisional. The rubric engine now applies stricter PSLE-style scoring caps so short or generic answers are not over-rewarded.
```

### Demo Part 7: Examiner Review And Release

Show:

- Results and review page.
- AI score versus final score.
- Examiner score adjustment.
- Evidence and transcript.
- Verify components.
- Release final results.

Say:

```text
The system is designed so AI does not directly release grades to students. The examiner verifies the final grade before release.
```

### Demo Part 8: Student Views Results

Show:

- Student results after release.
- Final grades and feedback.

Say:

```text
Students only see released results after examiner verification, which keeps the teacher in the loop.
```

## Backup Demo Plan

Prepare this in case the live demo fails due to Wi-Fi, API limits, microphone permission, browser issues, or avatar provider problems.

- Record a short screen recording of the full demo flow.
- Keep screenshots of key pages:
  - examiner assignment creation;
  - generated questions;
  - student preparation;
  - recording page;
  - avatar prompt;
  - examiner review;
  - released student results.
- Keep a local test assignment already created.
- Keep a completed student attempt ready for review.
- If Anam avatar fails, show the fallback prompt text and explain that assessment logic remains functional.

Suggested wording:

```text
The avatar provider depends on external API availability, so I prepared a recorded fallback. The core assessment flow still works because the application stores and displays the prompt text independently of the avatar provider.
```

## Privacy And Safety Notes

Mention these if the demo uses recorded voice, transcripts, or student-style data.

- Use demo accounts only.
- Do not show real API keys.
- Do not show `.env`.
- Do not show real student records.
- Do not use real student voice recordings.
- Use fabricated or test responses.
- Explain that the current prototype stores data locally for development.
- Explain that production deployment would need stronger authentication, access controls, consent handling, and secure database storage.

## Testing And Validation To Mention

Latest known test command:

```powershell
.\.venv\Scripts\python.exe -m unittest discover
```

Latest known result:

```text
40 tests OK
```

Also mention:

- Syntax checks were run on major modules.
- Unit tests cover avatar setup behavior, voice submission helpers, assignment persistence, oral-turn evaluation, examiner review helpers, and related logic.
- Manual browser testing is still important for the final demo because Streamlit UI behavior depends on browser state, microphone permissions, and external avatar/transcription services.

## Limitations To Be Honest About

Say these confidently. Limitations are normal for a capstone prototype.

- This is a local Streamlit prototype, not a production deployment.
- Data is stored in local JSON files, not a production database.
- Authentication is prototype-grade.
- AI grading is provisional and must be examiner-verified.
- Pronunciation, expression, and delivery cannot be fully judged from transcript alone.
- Avatar services depend on external API availability.
- Multi-user concurrency has not been hardened.
- More end-to-end browser QA would be needed before real classroom use.

## Future Work

Good future-work points:

- Move local JSON storage to SQLite or Postgres.
- Add role-based access control and stronger authentication.
- Add export for examiner-verified results.
- Add browser-based automated UI tests.
- Improve reading-aloud scoring with better audio analysis.
- Add consent and privacy controls for student voice recordings.
- Refactor `streamlit_app.py` into smaller modules.
- Add deployment configuration for a controlled school environment.

## Likely Q&A And Suggested Answers

### Why use AI here?

AI reduces preparation and feedback workload by generating draft questions, transcribing responses, and producing provisional rubric-based feedback. The examiner still makes the final grading decision.

### Is the AI grade final?

No. The AI grade is provisional. The examiner reviews evidence, adjusts scores if needed, verifies each component, and releases the final result.

### Why use an avatar?

The avatar improves oral-assessment realism and makes the prompt delivery feel closer to an examiner-led interaction. It is deliberately presentation-only so it does not control grading or assessment logic.

### What happens if the avatar fails?

The prompt remains visible as text, and the student can continue. The core assessment workflow does not depend on the avatar.

### How do you protect student privacy?

For the prototype, demo data should be fabricated. In production, the system would need stronger authentication, secure database storage, access controls, consent handling, and clear retention policies for voice recordings.

### Why local JSON storage?

It was fast and transparent for prototype development. For real deployment, assignment, user, transcript, and result records should move to SQLite, Postgres, or another managed database.

### How is this different from a chatbot?

The system is workflow-controlled. It has examiner assignment creation, fixed assessment stages, one-time submissions, rubric grading, examiner verification, and result release. The avatar and AI do not freely run the exam.

### What was the hardest part?

Coordinating the assessment state across examiner and student workflows: preparation timing, one-time submissions, guiding questions, provisional grading, examiner verification, and result release.

### What would you improve next?

The next priority would be production-ready storage and access control, followed by stronger browser-based QA and better audio analysis for reading-aloud delivery.

## Report Outline

If you still need to update or rescue the final report, use this structure.

1. Introduction
2. Problem Statement
3. Project Objectives
4. Literature/Background
5. Requirements
6. System Design And Architecture
7. Implementation
8. Key Features
9. Testing And Evaluation
10. Limitations
11. Future Work
12. Conclusion
13. References
14. Appendices

## Report Content Mapping

Use the existing project docs as source material.

| Report Section | Useful Existing File |
|---|---|
| Project summary | `PROJECT_OVERVIEW.md` |
| Implementation details | `IMPLEMENTATION_REPORT_SUMMARY.md` |
| Architecture/workflow | `WORKFLOW_DIAGRAMS.md` |
| Rubric and grading | `RUBRIC_GUIDE.md` |
| Session handling | `SESSION_MANAGEMENT_GUIDE.md` |
| Setup/run instructions | `README.md` and `CODEX_SESSION_HANDOFF.md` |
| Known issues/future work | `CODEBASE_AUDIT_AND_FIX_PLAN.md` |

## Presentation Slide Outline

Suggested 10-slide version:

1. Title: Oral Focus
2. Problem And Motivation
3. Project Objectives
4. User Roles And Workflow
5. System Architecture
6. Key Feature 1: Assignment And Question Generation
7. Key Feature 2: Student Oral Assessment Flow
8. Key Feature 3: AI Grading With Examiner Verification
9. Demo
10. Limitations, Future Work, And Conclusion

## What To Commit Before Presentation

Check status:

```powershell
git status
```

Generally commit:

- source code changes;
- documentation files;
- clean sample rubric files if needed for demo;
- non-sensitive sample data required to reproduce the demo.

Avoid committing:

- `.env`;
- API keys;
- real student data;
- temporary audio files;
- generated runtime sessions;
- cache folders;
- large local output folders.

Current known uncommitted files from the last handoff:

```text
CODEX_SESSION_HANDOFF.md
data/student_assignments.json
data/subject_config.json
data/rubrics/examiner_psle_oral_psle_singapore_oral_combined_strict_upload_3.json
```

Recommended commit split:

```powershell
git add CODEX_SESSION_HANDOFF.md CAPSTONE_FINAL_REPORT_PRESENTATION_PLAN.md
git commit -m "Add capstone final presentation plan"
```

Only if the latest rubric/test assignment data is intentionally part of the demo:

```powershell
git add data/subject_config.json data/student_assignments.json data/rubrics/examiner_psle_oral_psle_singapore_oral_combined_strict_upload_3.json
git commit -m "Add strict oral practice demo data"
```

## Final Preparation Checklist

Day before presentation:

- Confirm meeting link, room, or venue.
- Confirm supervisor and examiner attendance.
- Run the app locally.
- Test examiner login.
- Test student login.
- Test microphone permission.
- Test image upload and question generation.
- Test one completed assignment review.
- Test result release.
- Prepare backup video.
- Prepare screenshots.
- Close unrelated browser tabs.
- Hide `.env` and sensitive files.
- Keep terminal command ready.

Presentation day:

- Start the app before the session.
- Open `http://localhost:8501`.
- Keep backup recording ready.
- Keep sample student/examiner credentials ready privately.
- Keep this markdown file open as your speaking guide.
- Keep Q&A answers short and confident.

