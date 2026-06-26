# Codebase health audit and fix log

Audit date: 2026-06-26  
Scope: Streamlit app, student/examiner assessment flow, persistence helpers, tests, generated artifacts, and obvious deployment blockers.

## Executive summary

The codebase is now in a healthier state than at the start of this pass. The main blocker discovered by the test suite was the oral-guidance threshold regression: passable answers could still be rejected for “needs more elaboration”, which could send students back into unnecessary guiding prompts. I fixed that and restored the missing regression helper.

I also fixed two broader reliability issues:

1. `testopenai.py` was making a real OpenAI API call during `unittest discover`.
2. Streamlit still had deprecated `use_container_width=True` calls that can become a runtime blocker after Streamlit removes that API.

After fixes, all Python files compile and the full discovered unit test suite passes.

## Verification snapshot

| Check | Result |
| --- | --- |
| Python compile for all non-venv `.py` files | Pass |
| `python -m unittest discover -v` | Pass, 28/28 |
| Deprecated `use_container_width` search | Removed from app/runtime Streamlit files |
| Generated runtime artifact git noise | Reduced via `.gitignore` |

Known non-blocking warning observed during tests:

- `audioread` emits Python 3.13 deprecation warnings for `aifc` and `sunau`; the installed compatibility packages allow the test to pass.

## Findings and fixes

| Priority | Finding | Risk / observed behavior | Fix status |
| --- | --- | --- | --- |
| Blocker | `EducationCrew._follow_up_is_allowed` was missing while tests still expected it. | `test_question_fallback.py` had 3 errors. More importantly, the student oral flow could over-prompt instead of moving on. | Fixed in `src/crew_orchestrator.py`. |
| High | Passable but brief answers could be rejected when the LLM said only “needs more elaboration.” | Students could be sent back to the same question even when the answer was good enough to grade. | Fixed. The evaluator now accepts passable answers and only permits follow-up prompts for near-fail cases. |
| High | `testopenai.py` made a real API call during test discovery. | Local tests could become slow, flaky, network-dependent, and could spend API credits unintentionally. | Fixed. The OpenAI check now only runs when `python testopenai.py` is executed directly. |
| High | New student registration initially stored plain-text passwords. | Bad security habit even for a prototype; risky if reused beyond local demo. | Fixed for new registrations using PBKDF2 password hashes. Legacy demo passwords remain compatible. |
| Medium | Streamlit deprecated `use_container_width=True` was still used in many controls. | Streamlit warns it will be removed; future app versions can break. | Fixed. Replaced with `width="stretch"`. |
| Medium | Generated avatar videos, speech recordings, logs, and per-assignment upload folders appeared as commit candidates. | Accidental commits of student/runtime data and noisy git status. | Fixed for future untracked files via `.gitignore`. Existing tracked files are not deleted. |
| Medium | Runtime data files are currently modified in the working tree. | They appear to be live testing artifacts and should not be casually reverted or committed without intent. | Logged only. Left untouched. |
| Low | Full tests still print some session-manager and grading fallback messages. | Noise only; tests pass. | Logged only. Could be cleaned later with logging/mocking. |

## Step-by-step remediation implemented

1. Ran repository scan and git-state check.
2. Ran compile checks and full unit test discovery.
3. Identified concentrated failures in `test_question_fallback.py`.
4. Inspected `EducationCrew.evaluate_oral_turn()`.
5. Restored and implemented `_follow_up_is_allowed()`.
6. Updated `evaluate_oral_turn()` so “needs more elaboration” alone does not block moving to the next question.
7. Re-ran focused oral-guidance tests.
8. Wrapped `testopenai.py` in a manual `main()` entrypoint so test discovery has no network side effects.
9. Replaced Streamlit `use_container_width=True` with `width="stretch"`.
10. Hardened new student registration with PBKDF2 password hashing while keeping legacy demo login compatibility.
11. Added regression coverage confirming registered students authenticate and are not stored with plain-text passwords.
12. Added ignore rules for generated runtime artifacts.
13. Re-ran compile and full test discovery.

## Files changed by this audit pass

- `.gitignore`
- `src/crew_orchestrator.py`
- `src/exam_portal_store.py`
- `src/audio_recorder_streamlit.py`
- `streamlit_app.py`
- `test_exam_portal_store.py`
- `testopenai.py`
- `CODEBASE_HEALTH_AUDIT_2026-06-26.md`

Note: `data/student_assignments.json`, `data/sessions/d3fe5bca_session.json`, and `src/simli_avatar.py` were already modified before or during recent app testing. I did not revert or overwrite those runtime/user changes.

## Remaining risks that need a bigger product/deployment decision

These are not safe to “just patch” without deciding how the app will be deployed.

1. **Existing tracked student/session data**
   - The repository already contains many `data/sessions/*` files and assignment artifacts.
   - `.gitignore` prevents future untracked runtime files from appearing, but it does not remove files already tracked by Git history.
   - Recommended process: decide which files are sample data, remove real/private student artifacts from the index/history, then keep runtime data outside Git.

2. **File-backed JSON persistence**
   - Atomic JSON writes help for local prototype use, but this is not enough for multiple concurrent users.
   - Recommended next step: move users, assignments, submissions, and grading records into SQLite/Postgres before deployment.

3. **Authentication is still prototype-grade**
   - New registrations are hashed, but there is no password reset, account approval, examiner-controlled student onboarding, rate limiting, or server-side session hardening.
   - Recommended next step: use a proper auth provider or at least add admin approval and role-protected routes before deployment.

4. **Avatar provider dependency**
   - Simli/OpenAI TTS video generation adds latency, cost, and network failure points.
   - Current fallback prevents the exam flow from depending on the avatar, which is correct for now.

5. **Python 3.13 audio dependency warnings**
   - Tests pass, but audio libraries still emit compatibility warnings.
   - Recommended next step: pin/verify audio dependencies for the final deployment Python version.

## Current health status

Current local status after this pass: usable for continued prototype testing.  
Do not deploy publicly yet without resolving the remaining security/persistence items above.
