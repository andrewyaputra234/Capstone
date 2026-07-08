# Implementation Report Summary

## Project focus

This project implements a local Streamlit-based oral assessment portal for a PSLE-style English Oral workflow. The system supports examiner assignment creation, student preparation, reading-aloud submission, image-based oral questions, AI grading, examiner review, and avatar-based question delivery.

## Recent implementation work

### 1. Anam AI avatar integration

The avatar provider was changed from a static Simli video-generation approach to an Anam live-avatar session approach.

Implemented changes:

- Added Anam configuration through `.env`.
- Added support for `AVATAR_PROVIDER=anam`.
- Added server-side Anam session-token creation.
- Added browser-side Anam avatar rendering in the student assessment page.
- The avatar now speaks the examiner-approved question text using Anam `talk()`.
- Guiding questions are also spoken by the avatar when the student's first answer is too weak.
- The avatar remains presentation-only; assessment logic, grading, question order, and transcript handling stay inside the application.

Required Anam configuration:

```env
AVATAR_PROVIDER=anam
ENABLE_ANAM_AVATAR=true
ANAM_API_KEY=...
ANAM_PERSONA_ID=...
```

Reliability changes:

- Added fallback text display if Anam cannot start.
- Added clearer browser-side error messages for stream/talk failures.
- Added automatic Anam session closing after speech to reduce live-session concurrency problems.

Relevant settings:

```env
ANAM_CLOSE_SESSION_AFTER_TALK=true
ANAM_CLOSE_SESSION_DELAY_SECONDS=10
```

### 2. Faster photo question generation

The original image-question generation path used document chunking, embeddings, vector-store rebuilding, and then vision extraction. This was unnecessary for standalone image uploads.

Implemented changes:

- Added a fast standalone-photo workflow.
- For `.png`, `.jpg`, `.jpeg`, and `.webp` uploads, the app now skips chunking and vector-store rebuild.
- The app directly sends the image to the vision model and asks for three PSLE-style oral prompts.
- The generated questions still preserve depth by covering:
  - observation and reasoning;
  - personal connection or experience;
  - broader reflection such as responsibility, safety, values, or community.

Relevant settings:

```env
FAST_PHOTO_QUESTION_GENERATION=true
VISION_QUESTION_MODEL=gpt-4o
QUESTION_REVIEW_CREW_ANALYSIS=false
```

The older full ingestion path remains available for PDF, DOCX, and TXT materials.

### 3. Streamlined student answer flow

The previous image-question flow required students to manually transcribe, review, and submit their answer. This added waiting time.

Implemented changes:

- Image-question responses now use a faster one-step submission flow.
- Students record and submit once.
- The app transcribes in the background because text is still needed for grading and guidance decisions.
- Delivery analysis is skipped for image-question answers to reduce waiting time.
- Fast oral-turn evaluation accepts passable responses quickly and only triggers a guiding question for very short, unclear, or struggling answers.

Relevant settings:

```env
FAST_ASSESSMENT_RESPONSE_FLOW=true
FAST_ORAL_TURN_EVALUATION=true
```

### 4. Simplified avatar speaking behavior

The avatar was simplified so it only speaks assessment-critical prompts.

Current avatar behavior:

- Speaks the main image question.
- Speaks the guiding question only if the student's first answer is too weak.
- Does not give extra silence nudges.
- Does not say "I'm still here."
- Does not interrupt while the student is preparing or recording.

This makes the oral assessment flow clearer and reduces unnecessary avatar sessions.

### 5. Reading-aloud submission improvements

The reading-aloud task was changed to reduce retakes and speed up student progression.

Implemented changes:

- Reading aloud is now a one-shot submission.
- Students do not see or review the transcript before submitting.
- The recording is saved for examiner review.
- Retaking is not allowed after a successful save.
- Skipping reading aloud is disabled by default.
- Fast reading submission saves the transcript/recording immediately and defers detailed examiner judgement.

Relevant settings:

```env
FAST_READING_SUBMISSION=true
ALLOW_READING_SKIP=false
```

### 6. Custom loading screens

The default Streamlit loading behavior caused blurred page transitions during recording submission and grading.

Implemented changes:

- Added custom full-screen loading overlays for student-facing processing steps.
- Used custom loading UI for:
  - recording submission;
  - answer checking;
  - guidance preparation;
  - response grading/saving;
  - assessment setup.

This improves user experience by making processing states clearer and more polished.

### 7. Preparation loading and material readiness

The student preparation page now checks that required materials are available before starting the preparation timer.

Implemented changes:

- Added a loading screen before preparation materials open.
- Verified picture stimulus availability.
- Verified reading passage text availability when a reading task exists.
- The preparation timer starts only after materials are ready.
- If materials are missing, the student sees an error and the timer does not start.

## Current assessment flow

1. Examiner uploads a picture stimulus and optional reading passage.
2. The app generates three PSLE-style image oral questions.
3. Examiner reviews and assigns the assessment.
4. Student opens preparation materials.
5. Student completes one-shot reading-aloud submission, if assigned.
6. Avatar speaks the current image question.
7. Student records and submits an answer.
8. If the answer is too weak, the app generates one guiding question and the avatar speaks it.
9. Student submits a final response if guidance was needed.
10. The system grades and saves the response.
11. Examiner reviews final results and releases them to the student.

## Design decisions

- The avatar is not the AI examiner brain.
- The application remains responsible for question logic, grading, state transitions, and transcripts.
- The avatar only presents already-decided examiner text.
- Photo-only workflows should avoid vector-store overhead.
- Reading-aloud submissions should prevent repeated retakes.
- Student-facing waits should use clear custom loading states.

## Testing and validation

The following checks were used during implementation:

```powershell
.venv\Scripts\python.exe -m py_compile streamlit_app.py src\crew_orchestrator.py src\anam_avatar.py src\voice_assessment.py
.venv\Scripts\python.exe -m unittest test_anam_avatar.py test_simli_avatar.py test_voice_assessment.py test_exam_portal_store.py
```

These checks validate configuration parsing, avatar setup behavior, voice submission helpers, assignment persistence, and syntax correctness.
