# CrewAI Regression And Integration Audit

Date: 2026-06-17  
Workspace: `C:\Users\SwiftX\Documents\Git\Capstone`

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
