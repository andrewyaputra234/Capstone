# Capstone Repository Cleanup Plan

Last updated: 2026-07-28

This file records what can be cleaned from the Capstone repository and what should be kept for the current Oral Focus demo.

## Current App

The current program is:

```powershell
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

Current app entry point:

```text
streamlit_app.py
```

The old Streamlit UI is:

```text
app.py
```

`app.py` is legacy. It is not the current Oral Focus PSLE-style oral portal.

## Cleanup Principle

Before the final presentation, prefer a conservative cleanup:

- Remove local caches and duplicate environments.
- Do not delete source files that may still be imported by the current app.
- Do not delete demo data needed for the presentation.
- Do not remove tracked files from Git unless you are sure they are not needed for report/demo evidence.

After the presentation, a deeper cleanup can remove old UI/code paths and historical generated data.

## Safe Local Cleanup Candidates

These are not part of the source program.

| Path | What It Is | Recommendation |
|---|---|---|
| `venv/` | Duplicate virtual environment | Can delete if `.venv/` works |
| `__pycache__/` | Python bytecode cache | Can delete |
| `.agents/` | Local agent/runtime folder | Can delete if not using it |
| `data/chroma_db/` | Rebuildable vector DB cache | Can delete if you do not need old vector indexes |
| `data/avatar_videos/` | Generated/cached avatar videos | Can delete if not needed for backup demo |
| `data/streamlit_*.log` | Runtime logs | Can delete |

Current approximate sizes:

| Path | Size |
|---|---:|
| `.venv/` | 2611 MB |
| `venv/` | 1747 MB |
| `data/avatar_videos/` | 49 MB |
| `data/chroma_db/` | 45 MB |
| `data/sessions/` | 12 MB |
| `data/input/` | 7 MB |

Recommended first local disk cleanup:

```powershell
Remove-Item -LiteralPath .\venv -Recurse -Force
Remove-Item -LiteralPath .\__pycache__ -Recurse -Force
```

Only delete `.venv/` if you are ready to recreate it:

```powershell
Remove-Item -LiteralPath .\.venv -Recurse -Force
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Do Not Delete Before Demo

Keep these for the current app and presentation:

```text
streamlit_app.py
src/
requirements.txt
data/users.json
data/student_assignments.json
data/subject_config.json
data/rubrics/
PROJECT_OVERVIEW.md
IMPLEMENTATION_REPORT_SUMMARY.md
CODEX_SESSION_HANDOFF.md
CAPSTONE_FINAL_REPORT_PRESENTATION_PLAN.md
```

Keep `.env` locally, but never commit it.

## Legacy Or Older Program Files

These are old or general-system files. Some are still used indirectly, so do not delete them blindly.

| Path | Status | Notes |
|---|---|---|
| `app.py` | Legacy UI | Old Streamlit app; not current demo app |
| `run.py` | CLI entry point | Older command-line workflow; useful for docs/testing |
| `src/main.py` | Ingestion helpers | Still imported by current code for loading/ingestion fallback |
| `src/agent_a1_ingestion.py` | Older ingestion agent | Used by legacy UI/CLI |
| `src/agent_a3_dialogue.py` | Dialogue manager | Still imported by current orchestration paths |
| `src/agent_a4_avatar.py` | Older avatar/TTS path | Older CLI-style avatar helper |
| `src/rubric_generator.py` | Older rubric generator | Used by legacy UI |
| `src/vector_store.py` | Vector DB helper | Still part of ingestion/search path |
| `ignore/` | Older docs | Useful for report/background, not needed at runtime |

Recommendation:

- Before presentation: keep them.
- After presentation: move legacy-only files to an `archive/` folder or remove them on a cleanup branch, then run tests.

## Generated Data To Review

These are generated runtime/demo artifacts. Some are already tracked by Git.

Tracked generated artifacts found:

```text
data/streamlit_*.log                         4 tracked files
data/sessions/speech_*                       22 tracked files
data/assignment_*_images/*                   5 tracked files
data/input/assignment_*/*                    5 tracked files
data/output/assignment_*/*                   5 tracked files
```

These should probably not be in Git long term, because `.gitignore` already excludes similar future files.

Conservative cleanup after presentation:

```powershell
git rm --cached data/streamlit_*.log
git rm --cached data/sessions/speech_*
git rm --cached -r data/assignment_*_images
git rm --cached -r data/input/assignment_*
git rm --cached -r data/output/assignment_*
git commit -m "Stop tracking generated runtime artifacts"
```

This removes them from Git tracking but keeps the local files. After confirming nothing important is needed locally, delete them from disk separately.

## Session Files

`data/sessions/` contains many generated session records and speech files.

Keep only the demo sessions you plan to show. Delete or untrack the rest after the presentation.

For privacy, do not include real student recordings or transcripts in the submitted repo.

## Data Files To Treat Carefully

Do not delete these without making a backup:

```text
data/users.json
data/student_assignments.json
data/subject_config.json
```

They control demo accounts, assignments, questions, grading state, and result release.

If cleaning these, make a backup first:

```powershell
Copy-Item .\data\users.json .\data\users.backup.json
Copy-Item .\data\student_assignments.json .\data\student_assignments.backup.json
Copy-Item .\data\subject_config.json .\data\subject_config.backup.json
```

Do not commit backup files if they contain real/demo student data.

## Current Git Status Notes

At the time this file was created:

```text
D  CODEBASE_HEALTH_AUDIT_2026-06-26.md
?? CAPSTONE_FINAL_REPORT_PRESENTATION_PLAN.md
?? CAPSTONE_REPO_CLEANUP_PLAN.md
```

`CODEBASE_HEALTH_AUDIT_2026-06-26.md` appears deleted. If that deletion was accidental, restore it before committing:

```powershell
git restore CODEBASE_HEALTH_AUDIT_2026-06-26.md
```

If the deletion was intentional, commit the deletion with the cleanup.

## Recommended Cleanup Order

1. Commit useful docs first:

```powershell
git add CAPSTONE_FINAL_REPORT_PRESENTATION_PLAN.md CAPSTONE_REPO_CLEANUP_PLAN.md
git commit -m "Add capstone presentation and cleanup plans"
```

2. Make sure the current app still runs:

```powershell
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

3. Delete the duplicate `venv/` folder if `.venv/` works.

4. Delete obvious caches:

```powershell
Remove-Item -LiteralPath .\__pycache__ -Recurse -Force
```

5. After the presentation, untrack generated runtime files and commit that separately.

6. Only after tests pass, consider archiving or deleting the legacy `app.py` workflow.

## Validation After Cleanup

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover
.\.venv\Scripts\python.exe -m py_compile streamlit_app.py src\exam_portal_store.py src\crew_orchestrator.py src\rubric_engine.py src\voice_assessment.py src\anam_avatar.py
```

Then manually test:

- examiner login;
- assignment creation;
- question generation;
- student preparation page;
- recording/submission;
- examiner review;
- result release;
- student result view.

