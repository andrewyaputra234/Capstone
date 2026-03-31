# Capstone

A simple document ingestion and search prototype.

## What this project does

- loads `.docx` files from `data/input`
- splits them into text chunks
- saves chunk files into `data/output`
- supports keyword search over saved chunk files

## Repository structure

- `src/`
  - `main.py` — ingest documents and save chunks
  - `qa.py` — search saved chunk files
  - `agent_a1_ingestion.py` — original ingestion example
- `data/input/` — place source `.docx` files here
- `data/output/` — generated chunk output goes here
- `venv/` — Python virtual environment
- `requirements.txt` — Python dependencies

## Setup

1. Open PowerShell in the project root:
   `C:\Users\User\OneDrive\Documents\GitHub\Capstone`
2. Activate the virtual environment:
   `.
   venv\Scripts\Activate.ps1`
3. Install requirements if needed:
   `python -m pip install -r requirements.txt`

## Usage

### Ingest documents and save chunks

From the root folder:

```powershell
python src/main.py data/input --output-dir data/output
```

If you want to search while ingesting:

```powershell
python src/main.py data/input --output-dir data/output --search "project"
```

### Search saved chunk files

From the root folder:

```powershell
python src/qa.py data/output --query "project"
```

Or use interactive search:

```powershell
python src/qa.py data/output --interactive
```

### Use the assistant

From the root folder:

```powershell
python src/assistant.py data/output --query "project"
```

Or interactive assistant mode:

```powershell
python src/assistant.py data/output --interactive
```

### Run from the root with a single wrapper

You can also use the root wrapper script to run commands from the repo root:

```powershell
python run.py ingest data/input --output-dir data/output
python run.py search data/output --query "project"
python run.py assistant data/output --query "project"
python run.py assistant data/output --interactive
```

## Good next steps

- add more `.docx` files to `data/input`
- improve search behavior and output format
- add a small UI or chat interface later
- add embedding/AI features once the data pipeline is stable

## Notes

- Keep code in `src/` and data in `data/`.
- Run commands from the repo root for the simplest paths.
