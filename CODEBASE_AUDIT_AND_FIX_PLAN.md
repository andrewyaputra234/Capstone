# Codebase audit and remediation plan

Audit date: 2026-06-20  
Scope: Streamlit portal, assignment/result persistence, grading/session workflow, project setup, and repository hygiene.

## Executive summary

The original Streamlit change had the beginnings of Student and Examiner login, but it could not meet the requested workflow. A student could only start a session and then the page stopped; uploaded work was subject-global rather than student-specific; and the AI results lived only in the current Streamlit browser session. An examiner therefore could not reliably see or adjust a student's grading.

The completed local-prototype implementation now provides a separate examiner dashboard, registered-student selection, required picture upload, optional reading-passage upload, per-assignment persistence, student submissions, and preserved AI/final grades. The original AI score is never overwritten by an examiner adjustment.

## Findings and remediation status

| Priority | Finding | Risk / observed behaviour | Resolution |
| --- | --- | --- | --- |
| Blocker | The student route stopped before the oral assessment UI. | Students could create a session but could not answer the assigned questions. | **Fixed.** The student portal now shows materials, submits image-question responses, and displays results. |
| Blocker | Results were stored only in `st.session_state`. | Refreshing or using another browser made examiner review impossible. | **Fixed.** Assignment, AI-grade, final-grade, and review records are persisted in `data/student_assignments.json`. |
| Blocker | Current uploads were attached to a shared subject, not a student assignment. | A later upload could change the material another student sees. | **Fixed.** Every assignment receives a unique, sanitised subject key and stores its own questions/material paths. |
| High | The examiner was effectively used as the assessment student in the existing UI. | Sessions and scores could be attributed to the examiner ID instead of the selected student. | **Fixed.** Student ID comes from the selected registered student for ingestion and from the signed-in student for sessions. |
| High | There was no examiner review/override path. | AI results could not be verified or corrected. | **Fixed.** The dashboard shows original AI and final grades side-by-side, supports criterion-level overrides and notes, and preserves an audit record. |
| High | A failed supplementary CrewAI call could discard an otherwise valid ingestion or rubric grade. | A transient provider error stopped assignment creation or submission. | **Fixed.** Supplementary analysis now degrades gracefully; provisional scoring is clearly marked for examiner verification. |
| High | A configured custom `SessionManager(session_dir=...)` still wrote to the default directory. | Tests, alternate deployments, and exports could read/write the wrong session location. | **Fixed.** Session paths now use `self.session_dir`; regression-tested. |
| Medium | JSON writes for subject configuration and sessions were non-atomic, and corrupt JSON could crash all session listing. | An interrupted write could leave data unreadable and block unrelated records. | **Fixed.** Atomic writes, explicit corrupt-config errors, and corrupt-session skipping are in place. |
| Medium | The old assignment file was a simple student-to-subject map. | It could not represent materials, attempts, results, review notes, or history. | **Fixed.** A versioned assignment store is used, with in-memory compatibility for the earlier map. |
| Medium | Reading aloud could be marked complete without audio evidence. | It could be mistaken for pronunciation/fluency scoring. | **Fixed in UI semantics.** Reading is shown as optional and completion-only; delivery criteria remain unassessed until audio scoring exists. |
| Medium | Documentation linked to files that are under `ignore/` or absent. | New users hit dead links and the README incorrectly said the web UI was pending. | **Fixed.** README links and portal instructions were updated. |
| Low | The shell `python` command resolves to the Windows App Installer shim in this environment. | Compile/test commands fail before project code runs. | **Documented.** Use `.venv\\Scripts\\python.exe` or activate the virtual environment. |
| Low | `app.py` is a legacy general-purpose UI with several broad exception handlers and a separate workflow. | Maintaining two active UIs would create drift and inconsistent behaviour. | **Contained.** The primary README and the legacy UI itself direct users to `streamlit_app.py`; retire or refactor `app.py` only after confirming no class still depends on it. |

## Security and deployment actions still required

These require a deployment/security decision rather than a safe local code edit.

1. **Rotate the OpenAI API key immediately.** A real credential was present in the local `.env` file during the audit. `.env` is gitignored, but a credential should be treated as exposed once it has been displayed to a tool or another person. Replace it in the OpenAI dashboard and update the local environment; do not commit it.
2. **Replace local ID-only login before any shared or internet-facing deployment.** `data/users.json` is a local prototype register, not authentication. Use the institution's SSO/identity provider, enforce examiner/student roles on the server, and add an audit trail with authenticated user identity.
3. **Move JSON data to a database for concurrent users.** Atomic file replacement prevents partial writes but does not provide record locking, backups, retention policy, or multi-machine access. Use a database with migrations and per-student authorization before concurrent examiner use.
4. **Remove or protect historical student data in Git.** `data/sessions/` is already tracked and contains session/audio artifacts. Adding it to `.gitignore` would not remove existing history. Obtain data-owner approval, remove the files from the index/history using the organisation's approved process, and add ignore rules for future real student records.
5. **Add consent, retention, and deletion policy.** Student responses, grades, and audio are educational records. Define who can view them, how long they are kept, and how deletion/export requests are handled.
6. **Add audio evidence before scoring reading delivery.** The current reading-passage completion is intentionally not a pronunciation or fluency score. Integrate recording/transcription and an examiner-approved rubric before changing that status.

## Implemented workflow

1. Maintain registered IDs in `data/users.json`.
2. An examiner opens **Assign assessment**, selects a registered student, uploads a picture, and optionally uploads a reading passage.
3. The system ingests the picture under a unique assignment subject, generates up to three questions, and persists the assignment.
4. The student signs in, views the assigned materials, optionally marks the reading passage complete, and submits each image-question answer.
5. AI rubric output is stored as `ai_grading`; the initial `final_grading` is a copy of it.
6. The examiner opens **Results and review**, compares the two grades, changes criterion values if necessary, and adds a note. The change is persisted without losing the AI output.

## Verification performed

All checks passed in the project virtual environment.

| Check | Result |
| --- | --- |
| `python -m compileall` for app, source, and tests | Pass |
| `python -m pip check` | Pass — no broken requirements |
| `python test_crew_integration.py` (non-live) | Pass — 6/6, live provider workflows intentionally skipped |
| `python verify_setup.py` | Pass — 5/5 environment checks |
| New persistence, review, fallback, and session tests | Pass — 8/8 |
| Streamlit `AppTest` login/render smoke checks | Pass — Student and Examiner dashboards render without exceptions |

Live OpenAI ingestion/grading was not run in this audit because it would create external provider usage. The graceful-fallback path is covered by a local regression test; run a supervised end-to-end upload with an approved key before classroom use.

## Changed files

- `streamlit_app.py` — examiner/student portals and upload/review workflow.
- `src/exam_portal_store.py` — tested file-backed assignment/review persistence.
- `data/users.json` — local registered-user starter data.
- `src/agent_a5_grader.py`, `src/rubric_engine.py`, `src/crew_orchestrator.py` — resilient, clearly marked grading/analysis fallback.
- `src/agent_a6_session_manager.py`, `src/subject_manager.py` — persistence corrections.
- `test_exam_portal_store.py`, `test_grading_resilience.py`, `test_persistence_safety.py` — regression coverage.
- `README.md` — current portal workflow and repaired documentation links.
