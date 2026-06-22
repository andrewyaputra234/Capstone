"""
Agent A6: Session Manager
Manages assessment sessions with tracking, state management, and persistence.

Features:
- Create sessions with unique IDs
- Track session state (INIT, ACTIVE, COMPLETED)
- Manage dialogue turns with metadata
- Save/load sessions from disk
- Generate session reports
"""

import os
import json
import uuid
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class SessionState(Enum):
    """Session lifecycle states"""
    INIT = "INIT"           # Session created, not started
    ACTIVE = "ACTIVE"       # Assessment in progress
    PAUSED = "PAUSED"       # Assessment paused
    COMPLETED = "COMPLETED" # Assessment finished
    CANCELLED = "CANCELLED" # Assessment cancelled


@dataclass
class Turn:
    """Single dialogue turn (question or answer)"""
    turn_id: int
    timestamp: str
    speaker: str           # "avatar" or "student"
    text: str
    audio_path: Optional[str] = None
    transcription_path: Optional[str] = None
    metadata: Optional[Dict] = None
    
    def to_dict(self):
        return asdict(self)


@dataclass
class Session:
    """Assessment session"""
    session_id: str
    paper_id: str
    student_id: str
    date_created: str
    state: str             # SessionState.value
    turns: List[Dict]      # Turn objects as dicts
    scores: Optional[List[Dict]] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    metadata: Optional[Dict] = None
    
    def to_dict(self):
        return asdict(self)


class SessionManager:
    """Manage assessment sessions"""
    
    SESSION_DIR = "data/sessions"
    
    def __init__(self, session_dir: str = SESSION_DIR):
        """
        Initialize session manager.
        
        Args:
            session_dir: Directory to store session files (default: data/sessions)
        """
        self.session_dir = session_dir
        os.makedirs(session_dir, exist_ok=True)
        self.current_session = None
    
    def create_session(self, paper_id: str, student_id: str, metadata: Optional[Dict] = None) -> str:
        """
        Create a new assessment session.
        
        Args:
            paper_id: ID of the paper/assignment being assessed
            student_id: ID of the student
            metadata: Optional metadata (e.g., rubric_id, subject)
        
        Returns:
            session_id
        """
        session_id = str(uuid.uuid4())[:8]  # Short UUID
        timestamp = datetime.now().isoformat()
        
        session = Session(
            session_id=session_id,
            paper_id=paper_id,
            student_id=student_id,
            date_created=timestamp,
            state=SessionState.INIT.value,
            turns=[],
            scores=None,
            metadata=metadata or {}
        )
        
        self.current_session = session
        self.save_session(session)
        
        print(f"[OK] Created session: {session_id}")
        print(f"   Paper: {paper_id}")
        print(f"   Student: {student_id}")
        
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Load session from disk"""
        session_path = self._get_session_path(session_id)
        
        if not session_path.exists():
            print(f"[ERROR] Session not found: {session_id}")
            return None
        
        try:
            with open(session_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not read session {session_id}; the file was not changed.") from exc
        
        session = Session(
            session_id=data['session_id'],
            paper_id=data['paper_id'],
            student_id=data['student_id'],
            date_created=data['date_created'],
            state=data['state'],
            turns=data['turns'],
            scores=data.get('scores'),
            start_time=data.get('start_time'),
            end_time=data.get('end_time'),
            metadata=data.get('metadata')
        )
        
        self.current_session = session
        return session
    
    def save_session(self, session: Session) -> None:
        """Atomically save a session to disk."""
        session_path = self._get_session_path(session.session_id)
        session_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{session_path.stem}-",
            suffix=".tmp",
            dir=session_path.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(session.to_dict(), f, indent=2)
                f.write("\n")
            os.replace(temporary_path, session_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink(missing_ok=True)
    
    def save_current_session(self) -> None:
        """Save the current session"""
        if self.current_session:
            self.save_session(self.current_session)
    
    def start_session(self, session_id: str) -> bool:
        """Start (activate) a session"""
        session = self.get_session(session_id)
        if not session:
            return False
        
        if session.state == SessionState.ACTIVE.value:
            print(f"[WARN] Session already active: {session_id}")
            return False
        
        session.state = SessionState.ACTIVE.value
        session.start_time = datetime.now().isoformat()
        self.save_session(session)
        self.current_session = session
        
        print(f"[OK] Started session: {session_id}")
        return True
    
    def end_session(self, session_id: str) -> bool:
        """Complete a session"""
        session = self.get_session(session_id)
        if not session:
            return False
        
        session.state = SessionState.COMPLETED.value
        session.end_time = datetime.now().isoformat()
        self.save_session(session)
        self.current_session = session
        
        print(f"[OK] Completed session: {session_id}")
        return True
    
    def add_turn(self, speaker: str, text: str, audio_path: Optional[str] = None,
                 transcription_path: Optional[str] = None, metadata: Optional[Dict] = None) -> int:
        """
        Add a dialogue turn to current session.
        
        Args:
            speaker: "avatar" or "student"
            text: The utterance text
            audio_path: Optional path to audio file
            transcription_path: Optional path to transcription JSON
            metadata: Optional metadata dict
        
        Returns:
            turn_id
        """
        if not self.current_session:
            raise ValueError("No active session. Create or load a session first.")
        
        turn_id = len(self.current_session.turns) + 1
        timestamp = datetime.now().isoformat()
        
        turn = Turn(
            turn_id=turn_id,
            timestamp=timestamp,
            speaker=speaker,
            text=text,
            audio_path=audio_path,
            transcription_path=transcription_path,
            metadata=metadata
        )
        
        self.current_session.turns.append(turn.to_dict())
        self.save_current_session()
        
        return turn_id
    
    def add_scores(self, scores: List[Dict]) -> None:
        """
        Add rubric scores to session.
        
        Args:
            scores: List of score dicts:
                [{
                    "Q1": grading_result_dict,
                    ...
                }, ...]
        """
        if not self.current_session:
            raise ValueError("No active session")
        
        # Append scores instead of replacing (supports multiple questions)
        if self.current_session.scores is None:
            self.current_session.scores = []
        
        self.current_session.scores.extend(scores)
        self.save_current_session()
    
    def get_session_report(self, session_id: str) -> Optional[Dict]:
        """Generate a session report"""
        session = self.get_session(session_id)
        if not session:
            return None
        
        # Calculate turn statistics
        avatar_turns = [t for t in session.turns if t['speaker'] == 'avatar']
        student_turns = [t for t in session.turns if t['speaker'] == 'student']
        
        report = {
            "session_id": session.session_id,
            "paper_id": session.paper_id,
            "student_id": session.student_id,
            "state": session.state,
            "date_created": session.date_created,
            "start_time": session.start_time,
            "end_time": session.end_time,
            "duration_seconds": self._calculate_duration(session),
            "statistics": {
                "total_turns": len(session.turns),
                "avatar_turns": len(avatar_turns),
                "student_turns": len(student_turns),
            },
            "scores": session.scores,
            "transcript": session.turns
        }
        
        return report
    
    def export_transcript(self, session_id: str, format: str = "json", 
                         output_path: Optional[str] = None) -> Optional[str]:
        """
        Export session transcript.
        
        Args:
            session_id: Session to export
            format: "json", "csv", or "text"
            output_path: Where to save (default: auto-generate)
        
        Returns:
            Path to exported file
        """
        session = self.get_session(session_id)
        if not session:
            return None
        
        if output_path is None:
            ext = format if format in ["json", "csv", "txt"] else "txt"
            output_path = f"{self.session_dir}/{session_id}_transcript.{ext}"
        
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        
        if format == "json":
            report = self.get_session_report(session_id)
            with open(output_path, 'w') as f:
                json.dump(report, f, indent=2)
        
        elif format == "csv":
            import csv
            with open(output_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["Turn", "Speaker", "Timestamp", "Text", "Audio", "Transcription"])
                for turn in session.turns:
                    writer.writerow([
                        turn['turn_id'],
                        turn['speaker'],
                        turn['timestamp'],
                        turn['text'][:100],
                        turn.get('audio_path', ''),
                        turn.get('transcription_path', '')
                    ])
        
        elif format == "text":
            with open(output_path, 'w') as f:
                f.write(f"Session: {session.session_id}\n")
                f.write(f"Student: {session.student_id}\n")
                f.write(f"Paper: {session.paper_id}\n")
                f.write(f"State: {session.state}\n")
                f.write(f"Created: {session.date_created}\n")
                f.write("\n" + "="*80 + "\n")
                f.write("TRANSCRIPT\n")
                f.write("="*80 + "\n\n")
                
                for turn in session.turns:
                    speaker = turn['speaker'].upper()
                    text = turn['text']
                    timestamp = turn['timestamp']
                    f.write(f"[{timestamp}] {speaker}:\n{text}\n\n")
        
        print(f"[OK] Exported transcript: {output_path}")
        return output_path
    
    def list_sessions(self) -> List[str]:
        """List readable session IDs, ignoring an individual corrupt session file."""
        sessions = []
        for file in Path(self.session_dir).glob("*_session.json"):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                session_id = data.get('session_id')
                if session_id:
                    sessions.append(session_id)
            except (OSError, json.JSONDecodeError, AttributeError):
                print(f"[WARN] Skipping unreadable session file: {file}")
        return sorted(sessions)

    def find_active_session_for_assignment(self, assignment_id: str) -> Optional[Session]:
        """Restore the newest active session associated with an assignment."""
        session_files = sorted(
            Path(self.session_dir).glob("*_session.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for session_file in session_files:
            try:
                with open(session_file, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                metadata = data.get("metadata") or {}
                if (
                    data.get("state") == SessionState.ACTIVE.value
                    and metadata.get("assignment_id") == assignment_id
                    and data.get("session_id")
                ):
                    return self.get_session(data["session_id"])
            except (OSError, json.JSONDecodeError, AttributeError, ValueError):
                continue
        return None
    
    def delete_session(self, session_id: str, include_artifacts: bool = True) -> bool:
        """Delete a session and optional files referenced by the session."""
        session_path = self._get_session_path(session_id)
        try:
            session_data = None
            if session_path.exists():
                with open(session_path, 'r') as f:
                    session_data = json.load(f)

            if include_artifacts and session_data:
                self._delete_session_artifacts(session_id, session_data)

            session_path.unlink()
            if self.current_session and self.current_session.session_id == session_id:
                self.current_session = None
            print(f"[OK] Deleted session: {session_id}")
            return True
        except FileNotFoundError:
            return False
    
    def delete_all_sessions(self, include_artifacts: bool = True) -> Dict:
        """Delete all persisted sessions."""
        deleted = []
        failed = []
        for session_id in self.list_sessions():
            try:
                if self.delete_session(session_id, include_artifacts=include_artifacts):
                    deleted.append(session_id)
                else:
                    failed.append({"session_id": session_id, "error": "not found"})
            except Exception as e:
                failed.append({"session_id": session_id, "error": str(e)})

        return {
            "deleted": deleted,
            "failed": failed,
        }
    
    # Helper methods
    
    def _get_session_path(self, session_id: str) -> Path:
        """Get a session path within this manager's configured storage directory."""
        return Path(self.session_dir) / f"{session_id}_session.json"
    
    def _delete_session_artifacts(self, session_id: str, session_data: Dict) -> None:
        """Delete transcript exports and turn-level artifacts safely inside session_dir."""
        session_dir = Path(self.session_dir).resolve()
        candidates = []

        for turn in session_data.get("turns", []):
            for key in ["audio_path", "transcription_path"]:
                value = turn.get(key)
                if value:
                    candidates.append(Path(value))

        candidates.extend(Path(self.session_dir).glob(f"{session_id}_transcript.*"))

        for path in candidates:
            try:
                resolved = path.resolve()
                resolved.relative_to(session_dir)
            except (OSError, ValueError):
                continue

            if resolved.exists() and resolved.is_file():
                resolved.unlink()
    
    @staticmethod
    def _calculate_duration(session: Session) -> Optional[float]:
        """Calculate session duration in seconds"""
        if not session.start_time or not session.end_time:
            return None
        
        try:
            start = datetime.fromisoformat(session.start_time)
            end = datetime.fromisoformat(session.end_time)
            return (end - start).total_seconds()
        except (TypeError, ValueError):
            return None


def main():
    """CLI interface for session management"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Session Manager for Oral Assessment")
    subparsers = parser.add_subparsers(dest='action', help='Action to perform')
    
    # Create session
    create_parser = subparsers.add_parser('create', help='Create new session')
    create_parser.add_argument('--paper', required=True, help='Paper ID')
    create_parser.add_argument('--student', required=True, help='Student ID')
    create_parser.add_argument('--rubric', help='Rubric ID')
    create_parser.add_argument('--subject', help='Subject/topic')
    
    # List sessions
    subparsers.add_parser('list', help='List all sessions')
    
    # View session
    view_parser = subparsers.add_parser('view', help='View session details')
    view_parser.add_argument('--session', required=True, help='Session ID')
    
    # Export session
    export_parser = subparsers.add_parser('export', help='Export session transcript')
    export_parser.add_argument('--session', required=True, help='Session ID')
    export_parser.add_argument('--format', choices=['json', 'csv', 'text'], default='json')
    export_parser.add_argument('--output', help='Output file path')
    
    # Delete session
    delete_parser = subparsers.add_parser('delete', help='Delete session')
    delete_parser.add_argument('--session', required=True, help='Session ID')
    
    args = parser.parse_args()
    
    manager = SessionManager()
    
    if args.action == 'create':
        metadata = {}
        if hasattr(args, 'rubric') and args.rubric:
            metadata['rubric_id'] = args.rubric
        if hasattr(args, 'subject') and args.subject:
            metadata['subject'] = args.subject
        
        session_id = manager.create_session(
            paper_id=args.paper,
            student_id=args.student,
            metadata=metadata
        )
        print(f"\nSession ID: {session_id}")
    
    elif args.action == 'list':
        sessions = manager.list_sessions()
        if not sessions:
            print("No sessions found")
        else:
            print(f"\nFound {len(sessions)} sessions:")
            for sid in sessions:
                session = manager.get_session(sid)
                if session:
                    print(f"  - {sid} ({session.student_id}) - {session.state}")
    
    elif args.action == 'view':
        report = manager.get_session_report(args.session)
        if report:
            print(json.dumps(report, indent=2))
    
    elif args.action == 'export':
        path = manager.export_transcript(
            args.session,
            format=args.format,
            output_path=args.output
        )
        if path:
            print(f"Exported to: {path}")
    
    elif args.action == 'delete':
        manager.delete_session(args.session)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
