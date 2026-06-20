"""
Subject Manager - Organize documents and databases by subject/topic
Handles multi-subject database organization and switching.
"""

import os
import json
import shutil
import gc
import time
import tempfile
from pathlib import Path
from typing import Dict, List


class SubjectManager:
    """Manages subject-based organization of data and vector databases."""
    
    def __init__(self, base_path: str = "./data"):
        self.base_path = Path(base_path)
        self.input_path = self.base_path / "input"
        self.output_path = self.base_path / "output"
        self.chroma_base_path = self.base_path / "chroma_db"
        self.config_file = self.base_path / "subject_config.json"
        
        # Ensure directories exist
        self.input_path.mkdir(parents=True, exist_ok=True)
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.chroma_base_path.mkdir(parents=True, exist_ok=True)
        
        # Load or create config file
        self._load_config()
    
    def get_subject_input_path(self, subject: str | None = None) -> Path:
        """Get input path for a subject. If no subject, return base input path."""
        if subject:
            path = self.input_path / subject
            path.mkdir(parents=True, exist_ok=True)
            return path
        return self.input_path
    
    def get_subject_output_path(self, subject: str | None = None) -> Path:
        """Get output path for a subject. If no subject, return base output path."""
        if subject:
            path = self.output_path / subject
            path.mkdir(parents=True, exist_ok=True)
            return path
        return self.output_path
    
    def get_subject_chroma_path(self, subject: str | None = None, create: bool = True) -> Path:
        """Get Chroma DB path for a subject. If no subject, return base path."""
        if subject:
            configured_path = self.config.get("subjects", {}).get(subject, {}).get("chroma_path")
            path = Path(configured_path) if configured_path else self.chroma_base_path / f"{subject}_db"
            if create:
                path.mkdir(parents=True, exist_ok=True)
            return path
        return self.chroma_base_path
    
    def list_subjects(self) -> List[str]:
        """List all available subjects (based on chroma_db subdirectories)."""
        subjects = set(self.config.get("subjects", {}).keys())
        if self.chroma_base_path.exists():
            for item in self.chroma_base_path.iterdir():
                if item.is_dir() and item.name.endswith("_db"):
                    # Remove "_db" suffix to get subject name
                    subject = item.name[:-3]
                    subjects.add(subject)
        return sorted(subjects)
    
    def list_ingested_subjects(self) -> List[str]:
        """List subjects that have any stored uploads, chunks, databases, images, or config."""
        subjects = set(self.config.get("subjects", {}).keys())

        for base in [self.input_path, self.output_path]:
            if base.exists():
                subjects.update(item.name for item in base.iterdir() if item.is_dir())

        if self.chroma_base_path.exists():
            for item in self.chroma_base_path.iterdir():
                if item.is_dir() and item.name.endswith("_db"):
                    subjects.add(item.name[:-3])

        if self.base_path.exists():
            for item in self.base_path.glob("*_images"):
                if item.is_dir():
                    subjects.add(item.name[:-7])

        return sorted(subjects)
    
    def subject_exists(self, subject: str) -> bool:
        """Check if a subject database exists."""
        configured_path = self.config.get("subjects", {}).get(subject, {}).get("chroma_path")
        db_path = Path(configured_path) if configured_path else self.chroma_base_path / f"{subject}_db"
        return db_path.exists()
    
    def get_subject_info(self, subject: str) -> dict:
        """Get information about a subject."""
        input_path = self.input_path / subject
        output_path = self.output_path / subject
        configured_path = self.config.get("subjects", {}).get(subject, {}).get("chroma_path")
        db_path = Path(configured_path) if configured_path else self.chroma_base_path / f"{subject}_db"
        chunk_files = list(output_path.glob("*.txt"))
        
        mapped_rubric = self.config.get("subjects", {}).get(subject, {}).get("rubric")
        
        return {
            "name": subject,
            "exists": self.subject_exists(subject),
            "chunk_count": len(chunk_files),
            "input_path": str(input_path),
            "output_path": str(output_path),
            "db_path": str(db_path),
            "rubric": mapped_rubric,
        }
    
    def _load_config(self):
        """Load subject configuration from JSON file."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"Could not read subject configuration at {self.config_file}. "
                    "The file was not changed."
                ) from exc
            if not isinstance(config, dict):
                raise ValueError(f"Subject configuration at {self.config_file} must be a JSON object.")
            self.config = config
        else:
            self.config = {"subjects": {}}
    
    def _save_config(self):
        """Atomically save subject configuration to avoid partial JSON writes."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{self.config_file.stem}-",
            suffix=".tmp",
            dir=self.config_file.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
                f.write("\n")
            os.replace(temporary_path, self.config_file)
        finally:
            if temporary_path.exists():
                temporary_path.unlink(missing_ok=True)
    
    def set_subject_rubric(self, subject: str, rubric_name: str):
        """Map a rubric to a subject."""
        if "subjects" not in self.config:
            self.config["subjects"] = {}
        if subject not in self.config["subjects"]:
            self.config["subjects"][subject] = {}
        
        self.config["subjects"][subject]["rubric"] = rubric_name
        self._save_config()
        print(f"[OK] Mapped rubric '{rubric_name}' to subject '{subject}'")
    
    def get_default_rubric(self, subject: str) -> str | None:
        """Get the mapped rubric for a subject from config."""
        return self.config.get("subjects", {}).get(subject, {}).get("rubric")
    
    def set_subject_pdf(self, subject: str, pdf_path: str):
        """Store which PDF file is used for a subject."""
        if "subjects" not in self.config:
            self.config["subjects"] = {}
        if subject not in self.config["subjects"]:
            self.config["subjects"][subject] = {}
        
        self.config["subjects"][subject]["pdf_path"] = pdf_path
        self._save_config()
        print(f"[OK] Stored PDF path for subject '{subject}': {pdf_path}")
    
    def get_subject_pdf(self, subject: str) -> str | None:
        """Retrieve the PDF path stored for a subject."""
        return self.config.get("subjects", {}).get(subject, {}).get("pdf_path")

    def set_subject_chroma_path(self, subject: str, chroma_path: str):
        """Store the active Chroma database path for a subject."""
        if "subjects" not in self.config:
            self.config["subjects"] = {}
        if subject not in self.config["subjects"]:
            self.config["subjects"][subject] = {}

        self.config["subjects"][subject]["chroma_path"] = chroma_path
        self._save_config()

    def set_subject_material_path(self, subject: str, material_type: str, file_path: str):
        """Store a subject material path, such as visual stimulus or reading passage."""
        if material_type not in {"visual", "reading"}:
            raise ValueError("material_type must be 'visual' or 'reading'")
        if "subjects" not in self.config:
            self.config["subjects"] = {}
        if subject not in self.config["subjects"]:
            self.config["subjects"][subject] = {}

        self.config["subjects"][subject][f"{material_type}_path"] = file_path
        self._save_config()

    def get_subject_material_path(self, subject: str, material_type: str) -> str | None:
        """Retrieve a subject material path, such as visual stimulus or reading passage."""
        if material_type not in {"visual", "reading"}:
            raise ValueError("material_type must be 'visual' or 'reading'")
        return self.config.get("subjects", {}).get(subject, {}).get(f"{material_type}_path")

    def delete_subject_data(self, subject: str) -> Dict:
        """
        Delete all locally stored ingestion artifacts for a subject.

        Removes copied uploads, chunk files, Chroma DB, extracted images, and the
        subject's config entry. Rubrics and sessions are intentionally left alone.
        """
        if not subject or subject.strip() in {".", ".."}:
            raise ValueError("Subject name is required")

        targets = {
            "input": self.input_path / subject,
            "output": self.output_path / subject,
            "chroma": self.chroma_base_path / f"{subject}_db",
            "images": self.base_path / f"{subject}_images",
        }
        configured_chroma = self.config.get("subjects", {}).get(subject, {}).get("chroma_path")
        if configured_chroma:
            targets["configured_chroma"] = Path(configured_chroma)

        deleted_paths = []
        missing_paths = []
        seen_paths = set()
        for path in targets.values():
            resolved = str(path.resolve())
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            if not path.exists():
                missing_paths.append(str(path))
                continue

            self._remove_path_inside_base(path)
            deleted_paths.append(str(path))

        removed_config = False
        if subject in self.config.get("subjects", {}):
            del self.config["subjects"][subject]
            self._save_config()
            removed_config = True

        return {
            "subject": subject,
            "deleted_paths": deleted_paths,
            "missing_paths": missing_paths,
            "removed_config": removed_config,
        }

    def _remove_path_inside_base(self, path: Path) -> None:
        """Remove a file or directory only if it resolves inside the data directory."""
        resolved_base = self.base_path.resolve()
        resolved_path = path.resolve()
        try:
            resolved_path.relative_to(resolved_base)
        except ValueError as exc:
            raise ValueError(f"Refusing to delete outside data directory: {path}") from exc

        if resolved_path.is_dir():
            last_error = None
            for _ in range(3):
                try:
                    shutil.rmtree(resolved_path)
                    return
                except PermissionError as exc:
                    last_error = exc
                    gc.collect()
                    time.sleep(0.25)
                except OSError as exc:
                    if getattr(exc, "winerror", None) != 32:
                        raise
                    last_error = exc
                    gc.collect()
                    time.sleep(0.25)
            raise last_error
        else:
            resolved_path.unlink()
