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
        
        print(f"✅ Created session: {session_id}")
        print(f"   Paper: {paper_id}")
        print(f"   Student: {student_id}")
        
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Load session from disk"""
        session_path = self._get_session_path(session_id)
        
        if not session_path.exists():
            print(f"❌ Session not found: {session_id}")
            return None
        
        with open(session_path, 'r') as f:
            data = json.load(f)
        
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
        """Save session to disk"""
        session_path = self._get_session_path(session.session_id)
        session_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(session_path, 'w') as f:
            json.dump(session.to_dict(), f, indent=2)
    
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
            print(f"⚠️  Session already active: {session_id}")
            return False
        
        session.state = SessionState.ACTIVE.value
        session.start_time = datetime.now().isoformat()
        self.save_session(session)
        self.current_session = session
        
        print(f"▶️  Started session: {session_id}")
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
        
        print(f"✓ Completed session: {session_id}")
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
                    "criterion": "criterion_name",
                    "score": 4,
                    "max_score": 5,
                    "feedback": "Great job..."
                }, ...]
        """
        if not self.current_session:
            raise ValueError("No active session")
        
        self.current_session.scores = scores
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
        
        print(f"✅ Exported transcript: {output_path}")
        return output_path
    
    def list_sessions(self) -> List[str]:
        """List all session IDs"""
        sessions = []
        for file in Path(self.session_dir).glob("*_session.json"):
            with open(file, 'r') as f:
                data = json.load(f)
                sessions.append(data['session_id'])
        return sessions
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        session_path = self._get_session_path(session_id)
        try:
            session_path.unlink()
            print(f"✓ Deleted session: {session_id}")
            return True
        except FileNotFoundError:
            return False
    
    # Helper methods
    
    @staticmethod
    def _get_session_path(session_id: str, base_dir: str = SESSION_DIR) -> Path:
        """Get file path for session"""
        return Path(base_dir) / f"{session_id}_session.json"
    
    @staticmethod
    def _calculate_duration(session: Session) -> Optional[float]:
        """Calculate session duration in seconds"""
        if not session.start_time or not session.end_time:
            return None
        
        try:
            start = datetime.fromisoformat(session.start_time)
            end = datetime.fromisoformat(session.end_time)
            return (end - start).total_seconds()
        except:
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
                    print(f"  • {sid} ({session.student_id}) - {session.state}")
    
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
