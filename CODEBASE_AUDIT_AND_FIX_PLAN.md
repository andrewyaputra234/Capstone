# Oral Focus codebase audit, progress, and fix plan

Last updated: 2026-06-30  
Scope: Streamlit student/examiner portal, oral-assessment workflow, assignment persistence, AI grading, avatar examiner integration, testing, and deployment readiness.

## Current project status

Oral Focus has moved from an early prototype into a working local assessment portal. The main student and examiner workflows are now implemented and regression-tested.

Overall status: **local prototype working, not yet production-ready**.

| Area | Progress | Status |
| --- | ---: | --- |
| Student login and account registration | 90% | Working locally |
| Examiner login | 85% | Working locally |
| Examiner assignment creation | 88% | Working, depends on AI/image ingestion and avatar provider |
| Examiner question review/editing | 90% | Working |
| Student preparation materials page | 90% | Working with timer |
| Student oral assessment flow | 85% | Working, recently cleaned up |
| Guiding-question flow | 85% | Working with one follow-up |
| AI grading and examiner verification | 90% | Working and persisted |
| Result release to student | 85% | Working |
| Delete/reset assessment attempts | 85% | Working |
| Simli avatar examiner | 70% | Integrated with preview/retry, still Simli-provider dependent |
| UI theme consistency | 80% | Mostly light theme, still needs visual QA |
| Automated regression tests | 80% | 28 tests passing |
| Deployment/security readiness | 35% | Needs database/auth/data-retention work |

## What has been completed

### Student workflow

- Students can log in with their registered ID and password.
- Students can register a new account locally.
- Students can select an assigned assessment before seeing preparation materials.
- Preparation materials are shown before the assessment stage.
- A 10-minute preparation timer starts only once the preparation materials are opened.
- Once students continue to assessment, they cannot return to preparation materials.
- Completed assessments cannot be retaken.
- Students can see pending/completed result status.

### Examiner workflow

- Examiners can log in separately.
- Examiners can upload picture stimuli.
- Examiners can optionally upload a reading passage.
- AI-generated questions are shown to the examiner for review.
- Examiners can edit the generated questions before assigning.
- Assignments are tied to a selected registered student.
- Examiners can review AI grades.
- Examiners can adjust criterion scores and save verified grades.
- Examiners can release final results after verification.
- Examiners can reset results/sessions or delete an entire assessment.
- Examiner submit feedback now persists after rerun, so save/release actions are visible.

### Assessment logic

- Student answers are persisted before transition screens, preventing the "same question repeats" issue.
- If an answer is good enough, the student moves to the next question.
- If the student struggles, the system asks one guiding question.
- The first response and the guided follow-up response are combined for grading.
- The system no longer asks for follow-up just because a passable answer could use more elaboration.
- Skipped questions are graded deterministically as zero for assessed criteria.

### Avatar examiner integration

- Simli avatar support is integrated behind environment variables.
- Avatar generation is presentation-only; app logic still controls the question, grading, and navigation.
- Main question avatars are now prepared during examiner assignment review, before the student receives the assessment.
- Examiner avatar preview was added before final assignment.
- The preview screen now waits for all question avatars to be playable before showing the final preview.
- Avatar preparation is now conservative and step-by-step: question 1 must become playable before question 2 starts, then question 3.
- If a Simli URL repeatedly returns `404 {"error":"File not found"}`, the app can retry by creating a fresh Simli generation for the same question.
- Main question avatar videos can still be warmed up while the student is viewing preparation materials as a fallback.
- The assessment loading screen still prepares the next avatar as a backup if no saved playable avatar is available.
- Avatar videos are cached locally under `data/avatar_videos/`.
- The video player was changed to a custom embedded MP4 player because some Simli MP4s showed as black `0:00` in Streamlit's default player.
- Terminal-only avatar diagnostics now show URL readiness status, HTTP status, content type, and `File not found` responses.

Known limitations:

- Guiding-question avatars cannot be preloaded because the guiding question only exists after the student answers.
- Simli sometimes returns `mp4_url`/`hls_url` before the underlying video file is available. In that case the returned URL may temporarily or persistently respond with `404 {"error":"File not found"}`.
- Avatar preview reliability is currently limited by Simli URL readiness, not by local question generation.

### Persistence and data handling

- Assignments and results persist in `data/student_assignments.json`.
- AI grade and examiner-final grade are stored separately.
- Original AI grades are preserved after examiner adjustment.
- Session persistence uses safer atomic writes in the session manager.
- Runtime generated avatar/audio/assignment files are now ignored for future untracked files.

### Testing and verification

Latest verification performed:

```powershell
.\.venv\Scripts\python.exe -m py_compile streamlit_app.py
.\.venv\Scripts\python.exe -m unittest discover -v
```

Result: **28 tests OK**.

## Recent fixes and improvements

| Date | Change | Impact |
| --- | --- | --- |
| 2026-06-29 | Examiner save/release notices now persist after rerun. | Examiner submit actions no longer look like they did nothing. |
| 2026-06-29 | Student assessment page reorganised into clearer steps. | Less scrolling/confusion during assessment. |
| 2026-06-29 | Avatar videos warm up during preparation materials. | Reduces waiting time during assessment. |
| 2026-06-29 | Avatar MP4 rendering changed to embedded HTML video. | Avoids black `0:00` Streamlit video issue. |
| 2026-06-30 | Added examiner avatar preview before assignment. | Examiner can verify avatar playback before students receive the assessment. |
| 2026-06-30 | Changed avatar creation to safer step-by-step preparation. | Reduces Simli connection resets and avoids half-ready preview pages. |
| 2026-06-30 | Added Simli URL readiness diagnostics and retry settings. | Terminal logs now reveal `404 File not found`, content type, and retry behavior. |
| 2026-06-30 | Removed unnecessary post-submit “thank you/recorded response” transition. | Student flow moves forward faster after submit or skip. |
| 2026-06-26 | Oral-guidance threshold restored. | Good-enough answers move on instead of receiving unnecessary prompts. |
| 2026-06-26 | `testopenai.py` made manual-only. | Test discovery no longer makes real OpenAI API calls. |
| 2026-06-26 | Streamlit deprecated `use_container_width` replaced with `width`. | Removes future Streamlit compatibility risk. |
| 2026-06-26 | New student registration stores password hashes. | Better local security for new accounts. |

## Current known risks / blockers

### 1. Deployment-grade authentication is not ready

Current login is suitable for a local prototype, not public deployment.

Remaining work:

- Add proper session authentication.
- Add examiner/student role enforcement on the server side.
- Add account approval or examiner-created student accounts.
- Add password reset/change flow.
- Avoid using local `data/users.json` as the long-term user store.

### 2. JSON file storage is not enough for concurrent deployment

The app currently stores users, assignments, sessions, and results in JSON files.

This is acceptable for local demo use, but not for multiple simultaneous users.

Recommended next step:

- Move to SQLite for local/demo deployment or Postgres for hosted deployment.
- Add migrations.
- Add per-student/examiner authorization checks.

### 3. Existing tracked data may contain test/student artifacts

The repository already contains files under `data/sessions/`, assignment images, and generated outputs.

`.gitignore` helps prevent future accidental additions, but it does not remove files already tracked.

Recommended next step:

- Decide which data is safe sample data.
- Remove real/private data from Git tracking.
- Keep runtime generated files outside the repository for deployment.

### 4. Avatar provider reliability

Simli/OpenAI TTS adds cost, latency, and external failure points.

Current mitigation:

- Avatar is optional.
- Questions are still shown as text.
- Avatar generation is cached.
- Question avatars are prepared and previewed before assignment when possible.
- The preview waits for playable URLs instead of showing broken `File not found` streams.
- The app retries a fresh Simli generation if a returned URL does not become playable.
- Question avatars still warm up during preparation as fallback.
- Developer terminal logs show detailed avatar URL readiness diagnostics.

Remaining work:

- Decide whether Simli is reliable enough for the final demo or whether avatar should remain a bonus/toggle feature.
- Consider switching to a provider/API mode that gives stable completed-video assets instead of temporary URLs.
- Consider adding a "skip avatar preview and assign text-only" examiner option for demos when Simli is slow.

Recommended `.env` tuning for local testing:

```env
AVATAR_PREVIEW_PER_QUESTION_WAIT_SECONDS=150
AVATAR_PREVIEW_GENERATION_ATTEMPTS=2
AVATAR_PRECREATE_WORKERS=1
```

Use `AVATAR_PREVIEW_GENERATION_ATTEMPTS=3` only if Simli frequently returns permanent `404 File not found` URLs and the extra wait is acceptable.

### 5. Full end-to-end UI still needs manual QA

Automated tests cover persistence and logic, but Streamlit UI behavior should still be manually checked.

Manual test checklist:

- Examiner login.
- Student registration.
- Examiner creates assignment.
- Examiner edits AI questions and assigns.
- Student selects assignment.
- Student preparation timer starts.
- Examiner avatar preview appears before assignment only after all question avatars are playable.
- Student preparation page still works if avatar is unavailable.
- Student enters assessment.
- Avatar video plays.
- Student submits answer.
- Weak answer triggers one guiding question.
- Good answer moves to next question.
- Completed assessment cannot be retaken.
- Examiner saves verified grades.
- Examiner releases results.
- Student sees released results.
- Examiner reset/delete still works smoothly.

## Step-by-step next plan

### Phase 1 - Stabilise local demo

- [x] Fix repeated-question/student rerun issue.
- [x] Improve student assessment layout.
- [x] Add visible examiner submit feedback.
- [x] Warm up avatar videos during preparation.
- [x] Add examiner-side avatar preview before final assignment.
- [x] Add step-by-step avatar preparation and retry for broken Simli URLs.
- [x] Add terminal diagnostics for Simli URL readiness.
- [x] Remove unnecessary post-submit thank-you transition.
- [x] Keep full test suite passing.
- [ ] Manually QA the complete examiner-to-student-to-results flow.
- [ ] Capture screenshots for report/demo documentation.

### Phase 2 - Improve examiner and student UX

- [ ] Add clearer loading/progress messages during AI question generation.
- [x] Add examiner preview of assigned avatar questions.
- [ ] Add examiner option to assign text-only if avatar provider is slow.
- [ ] Add a compact avatar/video mode to reduce scrolling.
- [ ] Add clearer "awaiting examiner verification" student result screen.
- [ ] Add a dashboard count of pending reviews.

### Phase 3 - Prepare for deployment

- [ ] Replace JSON storage with SQLite/Postgres.
- [ ] Replace prototype login with proper authentication.
- [ ] Move runtime files out of Git.
- [ ] Add backup/export/retention policy.
- [ ] Add environment-specific config for local/demo/production.
- [ ] Add deployment documentation.

## Main changed files

- `streamlit_app.py` - main student/examiner portal, UI, flow, avatar rendering.
- `src/exam_portal_store.py` - users, assignments, grading, review persistence.
- `src/crew_orchestrator.py` - AI assessment orchestration and oral turn decision logic.
- `src/simli_avatar.py` - Simli avatar client and video URL preparation.
- `src/env_fix.py` - runtime environment fixes and telemetry disabling.
- `test_exam_portal_store.py` - persistence and examiner workflow regression tests.
- `test_question_fallback.py` - oral-guidance threshold tests.
- `test_simli_avatar.py` - avatar configuration tests.
- `test_grading_resilience.py` - grading fallback tests.
- `test_persistence_safety.py` - session/config persistence tests.

## How to run locally

Use the project virtual environment:

```powershell
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

Run verification:

```powershell
.\.venv\Scripts\python.exe -m py_compile streamlit_app.py
.\.venv\Scripts\python.exe -m unittest discover -v
```

Demo login:

- Student: `001` / `002`
- Examiner: `001` / `002`

## Final note

The project is in a strong position for a capstone prototype/demo. The core flow is now present: examiner assigns, student prepares and answers, AI grades, examiner verifies, and student receives results.

The biggest remaining gap is not functionality; it is production hardening: database storage, proper authentication, runtime file management, and privacy/security controls.
