"""
Subject Manager - Organize documents and databases by subject/topic
Handles multi-subject database organization and switching.
"""

import os
import json
from pathlib import Path
from typing import List


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
    
    def get_subject_chroma_path(self, subject: str | None = None) -> Path:
        """Get Chroma DB path for a subject. If no subject, return base path."""
        if subject:
            path = self.chroma_base_path / f"{subject}_db"
            path.mkdir(parents=True, exist_ok=True)
            return path
        return self.chroma_base_path
    
    def list_subjects(self) -> List[str]:
        """List all available subjects (based on chroma_db subdirectories)."""
        subjects = []
        if self.chroma_base_path.exists():
            for item in self.chroma_base_path.iterdir():
                if item.is_dir() and item.name.endswith("_db"):
                    # Remove "_db" suffix to get subject name
                    subject = item.name[:-3]
                    subjects.append(subject)
        return sorted(subjects)
    
    def subject_exists(self, subject: str) -> bool:
        """Check if a subject database exists."""
        return (self.chroma_base_path / f"{subject}_db").exists()
    
    def get_subject_info(self, subject: str) -> dict:
        """Get information about a subject."""
        output_path = self.get_subject_output_path(subject)
        chunk_files = list(output_path.glob("*.txt"))
        
        mapped_rubric = self.config.get("subjects", {}).get(subject, {}).get("rubric")
        
        return {
            "name": subject,
            "exists": self.subject_exists(subject),
            "chunk_count": len(chunk_files),
            "input_path": str(self.get_subject_input_path(subject)),
            "output_path": str(output_path),
            "db_path": str(self.get_subject_chroma_path(subject)),
            "rubric": mapped_rubric,
        }
    
    def _load_config(self):
        """Load subject configuration from JSON file."""
        if self.config_file.exists():
            with open(self.config_file, "r") as f:
                self.config = json.load(f)
        else:
            self.config = {"subjects": {}}
    
    def _save_config(self):
        """Save subject configuration to JSON file."""
        with open(self.config_file, "w") as f:
            json.dump(self.config, f, indent=2)
    
    def set_subject_rubric(self, subject: str, rubric_name: str):
        """Map a rubric to a subject."""
        if "subjects" not in self.config:
            self.config["subjects"] = {}
        if subject not in self.config["subjects"]:
            self.config["subjects"][subject] = {}
        
        self.config["subjects"][subject]["rubric"] = rubric_name
        self._save_config()
        print(f"✓ Mapped rubric '{rubric_name}' to subject '{subject}'")
    
    def get_default_rubric(self, subject: str) -> str | None:
        """Get the mapped rubric for a subject from config."""
        return self.config.get("subjects", {}).get(subject, {}).get("rubric")
