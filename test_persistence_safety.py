"""Regression tests for configurable, resilient local persistence."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from agent_a6_session_manager import SessionManager
from subject_manager import SubjectManager


class PersistenceSafetyTests(unittest.TestCase):
    def test_session_manager_honours_custom_session_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = SessionManager(session_dir=directory)
            session_id = manager.create_session("paper", "student")
            self.assertTrue((Path(directory) / f"{session_id}_session.json").exists())

    def test_corrupt_session_does_not_hide_readable_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = SessionManager(session_dir=directory)
            session_id = manager.create_session("paper", "student")
            (Path(directory) / "broken_session.json").write_text("not json", encoding="utf-8")
            self.assertEqual(manager.list_sessions(), [session_id])

    def test_invalid_subject_config_is_not_silently_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "subject_config.json").write_text("not json", encoding="utf-8")
            with self.assertRaises(ValueError):
                SubjectManager(base_path=directory)
            self.assertEqual((base / "subject_config.json").read_text(encoding="utf-8"), "not json")


if __name__ == "__main__":
    unittest.main()
