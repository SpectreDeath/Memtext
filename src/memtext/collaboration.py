"""Collaboration features: events, bundles, and activity tracking."""

import json
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
from enum import Enum


class EventType(Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    ACCESS = "ACCESS"
    SHARE = "SHARE"
    SESSION_START = "SESSION_START"
    SESSION_END = "SESSION_END"


@dataclass
class ContextEvent:
    """An event in the context system."""

    event_type: str
    entry_id: Optional[int] = None
    entry_title: Optional[str] = None
    project_path: Optional[str] = None
    session_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class EventStore:
    """Store and retrieve context events."""

    def __init__(self):
        self.events: List[ContextEvent] = []

    def add(self, event: ContextEvent):
        self.events.append(event)

    def get_recent(self, limit: int = 50) -> List[ContextEvent]:
        return self.events[-limit:]

    def get_for_entry(self, entry_id: int) -> List[ContextEvent]:
        return [e for e in self.events if e.entry_id == entry_id]

    def get_for_session(self, session_id: str) -> List[ContextEvent]:
        return [e for e in self.events if e.session_id == session_id]

    def clear(self):
        self.events.clear()


_global_events = EventStore()


def emit_event(
    event_type: str,
    entry_id: Optional[int] = None,
    entry_title: Optional[str] = None,
    project_path: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata: Optional[Dict] = None,
):
    """Emit a context event."""
    event = ContextEvent(
        event_type=event_type,
        entry_id=entry_id,
        entry_title=entry_title,
        project_path=project_path,
        session_id=session_id,
        metadata=metadata or {},
    )
    _global_events.add(event)
    return event


def get_events(limit: int = 50) -> List[Dict]:
    """Get recent events."""
    return [e.to_dict() for e in _global_events.get_recent(limit)]


class ProjectBundle:
    """Export/import project context as a bundle."""

    MANIFEST_FILE = "manifest.json"
    ENTRIES_DIR = "entries"

    def __init__(self, output_path: Path):
        self.output_path = output_path

    def export(self, include_shared: bool = True) -> Path:
        """Export project context to a .mtbundle file."""
        from memtext.db import query_entries, get_db_path, init_db

        db_path = get_db_path()
        if not db_path.exists():
            init_db()

        entries = query_entries(limit=1000)

        bundle_path = self.output_path.with_suffix(".mtbundle")

        with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zf:
            manifest = {
                "version": "0.4.0",
                "exported_at": datetime.now().isoformat(),
                "entry_count": len(entries),
            }
            zf.writestr(self.MANIFEST_FILE, json.dumps(manifest, indent=2))

            for entry in entries:
                entry_file = f"{self.ENTRIES_DIR}/{entry['id']}.json"
                zf.writestr(entry_file, json.dumps(entry, indent=2))

        return bundle_path

    def import_(self, overwrite: bool = False) -> int:
        """Import entries from a .mtbundle file."""
        from memtext.db import add_entry, entry_exists, init_db

        if not self.output_path.exists():
            raise FileNotFoundError(f"Bundle not found: {self.output_path}")

        init_db()
        count = 0

        with zipfile.ZipFile(self.output_path, "r") as zf:
            if self.MANIFEST_FILE not in zf.namelist():
                raise ValueError("Invalid bundle: manifest.json not found")

            for name in zf.namelist():
                if name.startswith(self.ENTRIES_DIR) and name.endswith(".json"):
                    with zf.open(name) as f:
                        entry_data = json.load(f)

                    if overwrite or not entry_exists(
                        entry_data["title"], entry_data.get("entry_type")
                    ):
                        add_entry(
                            title=entry_data["title"],
                            content=entry_data["content"],
                            entry_type=entry_data.get("entry_type", "note"),
                            tags=entry_data.get("tags", "").split(",")
                            if entry_data.get("tags")
                            else None,
                            importance=entry_data.get("importance", 1),
                        )
                        count += 1

        return count

    def list_contents(self) -> dict:
        """List bundle contents."""
        if not self.output_path.exists():
            raise FileNotFoundError(f"Bundle not found: {self.output_path}")

        with zipfile.ZipFile(self.output_path, "r") as zf:
            if self.MANIFEST_FILE not in zf.namelist():
                return {"error": "Invalid bundle"}

            with zf.open(self.MANIFEST_FILE) as f:
                return json.load(f)


class SessionTracker:
    """Track agent session activity."""

    def __init__(self):
        self.sessions: Dict[str, Dict] = {}

    def start_session(self, session_id: str, project_path: str = None) -> Dict:
        """Start a new session."""
        self.sessions[session_id] = {
            "session_id": session_id,
            "project_path": project_path or str(Path.cwd()),
            "started_at": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat(),
            "event_count": 0,
        }
        emit_event(
            EventType.SESSION_START.value,
            session_id=session_id,
            project_path=project_path,
        )
        return self.sessions[session_id]

    def end_session(self, session_id: str) -> Optional[Dict]:
        """End a session."""
        if session_id not in self.sessions:
            return None

        session = self.sessions[session_id]
        session["ended_at"] = datetime.now().isoformat()

        emit_event(
            EventType.SESSION_END.value,
            session_id=session_id,
            project_path=session.get("project_path"),
        )

        return self.sessions.pop(session_id)

    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session info."""
        return self.sessions.get(session_id)

    def update_activity(self, session_id: str):
        """Update session last active timestamp."""
        if session_id in self.sessions:
            self.sessions[session_id]["last_active"] = datetime.now().isoformat()
            self.sessions[session_id]["event_count"] += 1

    def list_active(self) -> List[Dict]:
        """List active sessions."""
        return list(self.sessions.values())


_global_sessions = SessionTracker()


def start_session(project_path: str = None) -> Dict:
    """Start a new tracking session."""
    import uuid

    session_id = str(uuid.uuid4())[:8]
    return _global_sessions.start_session(session_id, project_path)


def end_session(session_id: str) -> Optional[Dict]:
    """End a tracking session."""
    return _global_sessions.end_session(session_id)


def get_active_sessions() -> List[Dict]:
    """List active tracking sessions."""
    return _global_sessions.list_active()
