from __future__ import annotations

import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path
from src.subject_manager import SubjectManager

ROOT = Path(__file__).resolve().parent


def run_script(script_name: str, args: list[str]) -> int:
    script_path = ROOT / "src" / script_name
    if not script_path.exists():
        print(f"Script not found: {script_path}")
        return 1

    result = subprocess.run([sys.executable, str(script_path), *args], cwd=ROOT)
    return result.returncode


def main() -> int:
    parser = ArgumentParser(description="Run Capstone project commands from the repo root.")
    parser.add_argument(
        "command",
        choices=["ingest", "search", "semantic-search", "assistant", "dialogue", "list-subjects"],
        help="Command to run.",
    )
    parser.add_argument("path", nargs="?", default=None, help="Path to a DOCX/PDF file or folder containing them.")
    parser.add_argument("--output-dir", default=None, help="Output directory for ingestion.")
    parser.add_argument("--query", default=None, help="Search query or assistant question.")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run in interactive mode for search or assistant.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild the vector database from scratch.",
    )
    parser.add_argument(
        "--subject",
        default=None,
        help="Subject/topic name for multi-subject organization.",
    )
    parser.add_argument(
        "--rubric",
        default=None,
        help="Rubric name to use for scoring in dialogue mode.",
    )
    parser.add_argument(
        "--audio",
        action="store_true",
        help="Generate audio for questions in dialogue mode (requires pyttsx3).",
    )
    args = parser.parse_args()

    if args.command == "list-subjects":
        # List all available subjects
        subject_manager = SubjectManager()
        subjects = subject_manager.list_subjects()
        
        if not subjects:
            print("No subjects found. Ingest your first document using:")
            print("  python run.py ingest <path> --subject <topic>")
        else:
            print("\n📚 Available Subjects:")
            print("-" * 50)
            for subject in subjects:
                info = subject_manager.get_subject_info(subject)
                print(f"  • {subject}")
                print(f"    Chunks: {info['chunk_count']}")
                print(f"    DB: {info['db_path']}")
            print()
        return 0

    if args.command == "ingest":
        if not args.path:
            parser.error("ingest command requires a path argument")
        ingest_args = [args.path]
        if args.output_dir:
            ingest_args += ["--output-dir", args.output_dir]
        if args.query:
            ingest_args += ["--search", args.query]
        if args.subject:
            ingest_args += ["--subject", args.subject]
        return run_script("main.py", ingest_args)

    if args.command == "search":
        if not args.path:
            parser.error("search command requires a path argument")
        search_args = [args.path]
        if args.query:
            search_args += ["--query", args.query]
        if args.interactive:
            search_args += ["--interactive"]
        return run_script("qa.py", search_args)

    if args.command == "semantic-search":
        vs_args = []
        if args.rebuild:
            vs_args += ["--rebuild"]
        if args.query:
            vs_args += ["--query", args.query]
        if args.interactive:
            vs_args += ["--interactive"]
        if args.subject:
            vs_args += ["--subject", args.subject]
        return run_script("vector_store.py", vs_args)

    if args.command == "assistant":
        if not args.path:
            parser.error("assistant command requires a path argument")
        assistant_args = [args.path]
        if args.query:
            assistant_args += ["--query", args.query]
        if args.interactive:
            assistant_args += ["--interactive"]
        return run_script("assistant.py", assistant_args)

    if args.command == "dialogue":
        dialogue_args = []
        if args.interactive:
            dialogue_args += ["--interactive"]
        if args.subject:
            dialogue_args += ["--subject", args.subject]
        if args.rubric:
            dialogue_args += ["--rubric", args.rubric]
        if args.audio:
            dialogue_args += ["--audio"]
        return run_script("agent_a3_dialogue.py", dialogue_args)

    print("Unknown command")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
