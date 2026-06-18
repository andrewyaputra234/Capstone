# CrewAI Regression And Integration Audit

Date: 2026-06-17  
Workspace: `C:\Users\SwiftX\Documents\Git\Capstone`

## Update: 2026-06-18 Follow-Up Hardening Pass

### Scope

Focused on remaining audit risks and practical regression traps:

- Live-test data pollution
- Legacy Streamlit entry point confusion
- Reading-only Chroma side effects
- Documentation pointing to stale app flows

### Additional Fixes Made

#### Fixed: Live Tests Used Fixed Runtime Subject Names

Problem:

- `test_crew_integration.py --live` used fixed subjects like `crew_test_math` and `crew_live_test`.
- Interrupted or failed live runs could leave Chroma DBs, subject config, copied documents, and session files behind.
- Later live runs could be affected by stale state.

Fix:

- Added a `TestContext` with per-run unique subject names.
- Added live cleanup for generated subjects and sessions in a `finally` block.

Status: resolved for future live runs. Non-live regression path verified.

#### Fixed: Reading-Only Ingestion Created Empty Chroma DB Directories

Problem:

- `SubjectManager.get_subject_chroma_path()` always created the path as a side effect.
- Reading-only ingestion skipped vector rebuild, but still returned `db_path` by calling that helper, creating an empty Chroma directory.

Fix:

- Added `create` parameter to `get_subject_chroma_path()`.
- `main.ingest_document()` now reports the path without creating it when `vector_rebuilt=False`.

Status: resolved and verified with a focused reading-only ingestion check:

- `vector_rebuilt=False`
- `image_count=0`
- no empty Chroma DB folder created

#### Fixed: Documentation Pointed To Legacy `app.py`

Problem:

- `STREAMLIT_GUIDE.md` told users to run `streamlit run app.py`.
- `app.py` is a legacy general assessment UI and does not include the current PSLE split picture/reading flow.

Fix:

- Updated `STREAMLIT_GUIDE.md` and `README.md` to point to `streamlit_app.py`.
- Added a visible warning inside `app.py` explaining that it is legacy and directing users to `streamlit_app.py`.

Status: resolved.

### Verification Run

Commands run:

```powershell
.venv\Scripts\python.exe -m compileall -q src streamlit_app.py app.py run.py verify_setup.py test_crew_integration.py testopenai.py
.venv\Scripts\python.exe verify_setup.py
.venv\Scripts\python.exe test_crew_integration.py
.venv\Scripts\python.exe -m pip check
```

Focused check run:

```powershell
# Simulated material_type="reading" ingestion.
# Verified no vector rebuild, no image extraction, and no empty Chroma DB directory.
```

Current result:

- Compile check: passed.
- `verify_setup.py`: passed `5/5`.
- `test_crew_integration.py`: passed `6/6` in non-live mode.
- `pip check`: no broken requirements.
- Reading-only ingestion: passed and did not create an empty Chroma DB.

Remaining note:

- Live OpenAI test still has not been rerun in this follow-up pass to avoid extra API calls.
- The live test is now safer to run because it uses isolated subjects and cleanup.

## Update: 2026-06-18 Codebase Scan And Fix Pass

### Scope

Reviewed the active PSLE oral workflow and nearby infrastructure:

- `streamlit_app.py`
- `src/crew_orchestrator.py`
- `src/main.py`
- `src/vector_store.py`
- `src/subject_manager.py`
- `src/agent_a3_dialogue.py`
- `src/agent_a5_grader.py`
- `src/agent_a6_session_manager.py`
- `src/agent_audio_input.py`
- `run.py`
- `verify_setup.py`
- `requirements.txt`

### Verification Run

Commands run:

```powershell
.venv\Scripts\python.exe -m compileall -q src streamlit_app.py app.py run.py verify_setup.py test_crew_integration.py testopenai.py
.venv\Scripts\python.exe verify_setup.py
.venv\Scripts\python.exe test_crew_integration.py
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe run.py search "data\input\psle_oral_english\Good morning, students. I hope you.txt" --query students
```

Focused check run:

```powershell
# Simulated reading-passage ingestion with material_type="reading"
# Verified vector_rebuilt=False and image_count=0.
```

Current result:

- Compile check: passed.
- `verify_setup.py`: passed `5/5`.
- `test_crew_integration.py`: passed `6/6` in non-live mode.
- `pip check`: no broken requirements.
- `run.py search`: works through `src/main.py` text search.
- Reading-only ingestion: passed and did not rebuild Chroma.

Live OpenAI workflow was not rerun in this pass to avoid extra API calls; non-live wiring and focused local regressions were verified.

### Blockers Found And Fixed

#### Fixed: `verify_setup.py` Failed On Python 3.13 And Windows Consoles

Problem:

- The Python version check used `10 <= version.major == 3`, which rejects Python 3.13.
- Unicode status symbols could crash under Windows `cp1252`.
- The CrewAI import path used package-style imports that are inconsistent with the script-style app bootstrap.

Fix:

- Added `src` to `sys.path`.
- Reconfigured stdout/stderr to UTF-8 where available.
- Corrected the version check to `version.major == 3 and 10 <= version.minor <= 13`.
- Switched CrewAI initialization to the same `env_fix` + `crew_orchestrator` import path used elsewhere.
- Replaced verification status emojis with ASCII-safe status labels.

Status: resolved and verified.

#### Fixed: Dependency Conflict Between CrewAI And `unstructured-inference`

Problem:

- `pip check` reported:

```text
crewai 0.193.2 has requirement onnxruntime==1.22.0, but you have onnxruntime 1.27.0.
```

- Pinning `onnxruntime==1.22.0` exposed:

```text
unstructured-inference 1.6.13 has requirement onnxruntime>=1.25.0
```

Fix:

- Pinned:

```text
onnxruntime==1.22.0
unstructured-inference==1.2.0
```

- Updated the active `.venv` to those versions.

Status: resolved. `pip check` now reports no broken requirements.

#### Fixed: `run.py search` Called Missing `src/qa.py`

Problem:

- `run.py search` was advertised but failed with `Script not found` because `src/qa.py` does not exist.

Fix:

- Rewired `run.py search` to call `src/main.py` with `--search`.
- Requires `--query`.
- Rejects `--interactive` with guidance to use `semantic-search --interactive`.

Status: resolved and manually verified.

#### Fixed: `run.py assistant` Advertised Missing `src/assistant.py`

Problem:

- `run.py assistant` was advertised but failed because `src/assistant.py` does not exist.

Fix:

- Removed `assistant` from the CLI choices and deleted the dead branch.

Status: resolved.

#### Fixed: `run.py session` Passed A String As An Argument List

Problem:

- `run.py session <action>` passed `args.path` directly to `run_script`.
- `run_script` expects a list; passing a string risks expanding the action into individual characters.

Fix:

- Converted the optional path into `session_args = [args.path] if args.path else []`.

Status: resolved.

#### Fixed: Reading Uploads Could Rebuild Or Break Chroma

Problem:

- `main.ingest_document()` rebuilt Chroma for every upload, including `material_type="reading"`.
- Reading uploads do not need vector rebuilds and were involved in Chroma tenant/client errors.
- Reading uploads could also overwrite visual material metadata and extracted visual images.

Fix:

- Reading ingestion skips `VectorStore(rebuild=True)`.
- Reading ingestion skips image extraction.
- Reading ingestion no longer overwrites `pdf_path`; it only updates `reading_path`.
- Return payload includes `vector_rebuilt`.

Status: resolved and verified with a focused reading-only ingestion check.

#### Fixed: Chroma Locks During Rebuild

Problem:

- On Windows, Chroma files can remain locked by another process or active client.
- Rebuilds could fail with `[WinError 32]` while deleting `data_level0.bin`.

Fix:

- `VectorStore` now retries DB deletion.
- If a subject DB remains locked, it rotates to a fresh DB folder and stores that path in subject metadata.
- Retrieval closes its `VectorStore` wrapper after use.
- `EducationCrew.run_ingestion_workflow()` cleans up an active dialogue manager before rebuilding ingestion state.
- Removed the overly aggressive Chroma `system.stop()` call that could leave the Rust client in a bad tenant state.

Status: mitigated. Existing stale Streamlit processes may still need to be restarted after code changes.

#### Fixed: Stale Reading Passage Across Subject Changes

Problem:

- Switching or reinitializing crew subjects cleared oral question state but not reading passage state.
- A passage from one subject could appear in another subject's oral test.

Fix:

- Added `reset_reading_state()`.
- Called it on crew initialization/change and after deleting current subject data.

Status: resolved.

#### Fixed: Data Deletion Tried To Remove Chroma Before Releasing Active Crew

Problem:

- Deleting current subject data could fail if the active crew/dialogue manager still held vector resources.

Fix:

- Streamlit now calls `crew.cleanup()` and clears active crew state before deleting selected current-subject data.
- `SubjectManager` deletion now retries transient Windows lock errors.

Status: mitigated.

#### Fixed: Runtime CLI Prints Could Crash On Windows Consoles

Problem:

- Several runtime print paths used Unicode symbols.
- In a non-UTF-8 Windows console, those can raise `UnicodeEncodeError`.

Fix:

- Converted CLI/runtime status prints in `subject_manager`, `agent_a6_session_manager`, `agent_a5_grader`, `agent_a3_dialogue`, `agent_audio_input`, `rubric_generator`, `run.py`, and `verify_setup.py` to ASCII-safe text.

Status: resolved for terminal-facing paths found in this scan. Streamlit UI labels still use icons where appropriate.

### Remaining Risks / Follow-Up

#### P1: Live OpenAI Regression Gate Not Run In This Pass

Reason:

- Avoided extra API usage during this codebase scan.

Recommended step:

```powershell
.venv\Scripts\python.exe test_crew_integration.py --live
```

Run after closing duplicate Streamlit processes, because live Chroma rebuilds can be affected by stale app processes on Windows.

#### P2: Live Tests Still Mutate Runtime Data

Risk:

- `test_crew_integration.py --live` creates subject data, Chroma DBs, and sessions.

Recommended fix:

- Move live tests to isolated temporary subject names and clean them up at the end.

#### P2: Broad Dependency Ranges Remain

Risk:

- `requirements.txt` still uses broad lower bounds for major AI packages.
- The two critical pins added here fix the known conflict, but a clean reinstall can still pull newer CrewAI/LangChain/OpenAI behavior.

Recommended fix:

- Add a lock file or pin the currently verified package set before final demo/submission.

#### P2: `app.py` Appears To Be A Legacy Parallel Streamlit App

Risk:

- `app.py` contains older document/session management logic that differs from the active `streamlit_app.py`.
- Running the wrong Streamlit entry point may expose stale flows.

Recommended fix:

- Decide whether `app.py` is legacy.
- If legacy, mark it clearly in docs or remove it from demo instructions.
- If active, port the PSLE reading/image split and Chroma fixes there too.

#### P3: Package-Style Imports Are Still Not Clean

Risk:

- The project remains script-style and relies on inserting `src` into `sys.path`.

Recommended fix:

- Either keep script-style bootstrapping consistent, or convert to a proper package with relative imports and package metadata.

## Executive Status

The CrewAI integration is operational. The full live integration test passed after allowing network access for the OpenAI-dependent workflow:

- Non-live integration checks: passed `6/6`.
- Live integration checks: passed `6/6`.
- Setup verification: passed `5/5` after fixing the verification script.
- Syntax/compile checks: passed for the main source, Streamlit apps, CLI, tests, and setup helpers.
- Dependency consistency: `pip check` reported no broken requirements.

No critical CrewAI wiring regression is currently blocking the project. The remaining work is mainly cleanup and hardening.

## Layered Verification Process

### Layer 1: Environment And Dependency Health

Checked:

```powershell
.venv\Scripts\python.exe --version
.venv\Scripts\python.exe -m pip show crewai crewai-tools langchain-openai openai chromadb streamlit
.venv\Scripts\python.exe -m pip check
```

Result:

- Python: `3.13.2`.
- CrewAI installed: `0.193.2`.
- CrewAI tools installed: `0.76.0`.
- OpenAI SDK installed: `2.42.0`.
- ChromaDB installed: `1.5.9`.
- Streamlit installed: `1.58.0`.
- `pip check`: no broken requirements.
- `.env` exists and contains `OPENAI_API_KEY`; the key value was not exposed.

Note: the plain `python` launcher failed in this sandbox with a Windows logon-session error, so all validation used `.venv\Scripts\python.exe`.

### Layer 2: Static Regression Checks

Checked:

```powershell
.venv\Scripts\python.exe -m compileall src run.py streamlit_app.py test_crew_integration.py verify_setup.py
.venv\Scripts\python.exe -m compileall app.py setup_venv.py testopenai.py
```

Result:

- All targeted files compiled successfully.
- No syntax-level regression was found.

### Layer 3: CrewAI Wiring

Key integration points:

- `src/crew_orchestrator.py:56`, `:95`, `:101`, `:125`, `:144` define CrewAI tools that call real project infrastructure.
- `src/crew_orchestrator.py:198`, `:211`, `:224`, `:237`, `:250` create the five CrewAI agents.
- `src/crew_orchestrator.py:311`, `:326`, `:393`, `:407`, `:467` define CrewAI tasks.
- `src/crew_orchestrator.py:336`, `:417`, `:478` create crews and call `kickoff()`.
- `run.py:190` exposes the CLI CrewAI command flow.
- `streamlit_app.py` initializes and uses `EducationCrew` for the CrewAI UI.

Official CrewAI documentation alignment:

- Direct code-defined crews, agents, and tasks are supported: https://docs.crewai.com/en/concepts/crews
- Agents support roles, goals, tools, and an LLM parameter: https://docs.crewai.com/en/concepts/agents
- Tasks support sequential execution and expected outputs: https://docs.crewai.com/en/concepts/tasks
- The `@tool` decorator is a supported custom tool pattern: https://docs.crewai.com/en/concepts/tools

The installed CrewAI version accepted the current `langchain_openai.ChatOpenAI` wiring during import, initialization, and live workflow execution.

### Layer 4: Local CrewAI Regression Tests

Checked:

```powershell
.venv\Scripts\python.exe verify_setup.py
.venv\Scripts\python.exe test_crew_integration.py
.venv\Scripts\python.exe run.py crew --subject math --rubric primary_math --crew-action init
```

Result:

- `verify_setup.py`: passed `5/5`.
- `test_crew_integration.py`: passed `6/6`; OpenAI-dependent checks were intentionally skipped in non-live mode.
- CLI CrewAI init: passed.

### Layer 5: Live CrewAI/OpenAI Workflow

Checked:

```powershell
.venv\Scripts\python.exe test_crew_integration.py --live
```

Result:

- First sandboxed run failed with `Connection error.` on OpenAI-dependent steps.
- Elevated network rerun passed `6/6`.
- Live coverage included ingestion, vector database creation, rubric mapping, question extraction, A5 grading, CrewAI analysis, and A6 session persistence.
- Non-blocking shutdown warning observed: `Failed to export span batch due to timeout, max retries or shutdown.`

Interpretation:

- The initial failure was network sandboxing, not a functional regression.
- The telemetry warning did not fail the workflow, but it is worth quieting or configuring before demos.

## Fixes Made During This Audit

### Fixed: `verify_setup.py` Python 3.13 False Failure

Problem:

- The version check used a bad chained comparison and rejected Python 3.13.
- It then attempted to print a failure symbol and crashed on Windows console encoding.

Fix:

- Added UTF-8 console reconfiguration at `verify_setup.py:16`.
- Added `src` to `sys.path` at `verify_setup.py:10`.
- Corrected the Python version condition at `verify_setup.py:43`.
- Aligned the CrewAI import with the rest of the repo at `verify_setup.py:125`.

Status: resolved and verified.

## Remaining Issues

### P1: CLI Advertises Missing Commands

Evidence:

- `run.py:27` includes `search` and `assistant` as command choices.
- `run.py:124` calls `src/qa.py`.
- `run.py:146` calls `src/assistant.py`.
- Neither `src/qa.py` nor `src/assistant.py` exists.

Observed failures:

```powershell
.venv\Scripts\python.exe run.py search data\Template.docx --query math
.venv\Scripts\python.exe run.py assistant data\Template.docx --query math
```

Both fail with `Script not found`.

Next step:

- Either restore `src/qa.py` and `src/assistant.py`, or remove these commands and update README/docs.

### P2: Live Tests Mutate Project Data

Evidence:

- Live integration tests update `data/subject_config.json`.
- Live tests create or refresh `data/input/`, `data/output/`, `data/chroma_db/`, and session JSON files.
- This audit generated `data/sessions/eeb8829d_session.json` during the sandbox-failed live run and `data/sessions/a00ba566_session.json` during the successful live run.

Next step:

- Make live tests use isolated temporary subject names and clean up after completion.
- Consider ignoring generated `data/input/`, `data/output/`, and `data/sessions/*_session.json` if they are test/runtime artifacts.

### P2: Dependency Versions Are Broad

Evidence:

- `requirements.txt` uses broad lower bounds such as `crewai>=0.50.0`, `crewai-tools>=0.0.1`, `openai>=0.27.0`, and `langchain-openai>=0.0.3`.
- The current known-good environment has CrewAI `0.193.2`, CrewAI tools `0.76.0`, OpenAI `2.42.0`, and LangChain OpenAI `1.3.2`.

Risk:

- A clean reinstall can pull newer major behavior and create regressions that were not present in this tested environment.

Next step:

- Add a lock file or pin a known-good version range before final delivery.

### P2: Model Configuration Is Split Across Modules

Evidence:

- `src/crew_orchestrator.py:189` uses `CREWAI_MODEL` with default `gpt-3.5-turbo`.
- `src/agent_a3_dialogue.py:71`, `src/agent_a5_grader.py:48`, `src/rubric_engine.py:189`, `src/rubric_generator.py:863`, and `src/rubric_generator.py:956` hard-code `gpt-3.5-turbo`.

Status:

- Live tests passed with the current environment.

Next step:

- Centralize model selection into environment variables or a config module so CrewAI, grading, dialogue, and rubric generation do not drift.

### P3: Package-Style Imports Are Not Yet Clean

Evidence:

- The current app expects `src` to be inserted onto `sys.path`.
- `streamlit_app.py`, `run.py`, `test_crew_integration.py`, and the fixed `verify_setup.py` follow that pattern.
- Direct package import still fails:

```powershell
.venv\Scripts\python.exe -c "import src.crew_orchestrator"
```

Failure:

```text
ModuleNotFoundError: No module named 'env_fix'
```

Next step:

- If this project will become an installable package, add proper package metadata and convert intra-`src` imports to package-relative imports.
- If it remains a script-style project, keep using the current `sys.path` bootstrap consistently.

### P3: CrewAI Telemetry Shutdown Warning

Evidence:

- The successful live test ended with:

```text
Failed to export span batch due to timeout, max retries or shutdown.
```

Status:

- Non-blocking; all functional assertions passed.

Next step:

- Configure or disable telemetry/tracing during tests and demos if the warning is distracting.

## What You Are Left With

1. Decide what to do with `run.py search` and `run.py assistant`: restore the missing scripts or remove the advertised commands.
2. Clean up live-test artifact handling so tests do not leave sessions and subject config changes behind.
3. Pin or lock dependency versions around the currently verified environment.
4. Centralize model configuration instead of hard-coding `gpt-3.5-turbo` in multiple modules.
5. Choose whether the project is script-style or package-style, then make imports consistent.
6. Optionally quiet CrewAI telemetry export warnings before demos.

## Recommended Regression Gate

Run this before submission or demo:

```powershell
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -m compileall src run.py streamlit_app.py app.py test_crew_integration.py verify_setup.py
.venv\Scripts\python.exe verify_setup.py
.venv\Scripts\python.exe test_crew_integration.py
.venv\Scripts\python.exe run.py crew --subject math --rubric primary_math --crew-action init
```

Run this when API/network access is allowed:

```powershell
.venv\Scripts\python.exe test_crew_integration.py --live
```

Expected result as of this audit:

- Local gate: pass.
- Live gate: pass `6/6`.
