"""Repositories — database abstractions for Memtext.

Each class encapsulates a cohesive set of database operations.
All classes share a common database path and connection handling.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

import sqlite3
import logging

from ..models import Entry, SharedEntry, Reminder, Template, Webhook, Project, VersionChange

logger = logging.getLogger(__name__)


def get_db_path() -> Path:
    return Path.cwd() / ".context" / "memtext.db"


def get_connection(db_path: Optional[Path] = None):
    db_path = db_path or get_db_path()
    return sqlite3.connect(db_path)


class EntryManager:
    """CRUD operations for memory entries."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or get_db_path()
        self._init_db()

    def _init_db(self) -> None:
        """Create tables if they don't exist (matching original memtext schema)."""
        with get_connection(self.db_path) as conn:
            # Use original table names for compatibility
            conn.execute("""
                CREATE TABLE IF NOT EXISTS context_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    entry_type TEXT NOT NULL DEFAULT 'note',
                    importance INTEGER DEFAULT 1,
                    tags TEXT,
                    parent_tag TEXT,
                    source TEXT DEFAULT 'manual',
                    linked_files TEXT,
                    is_shared INTEGER DEFAULT 0,
                    project_id INTEGER,
                    reminder_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP,
                    access_count INTEGER DEFAULT 0,
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_context_entries_type ON context_entries(entry_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_context_entries_parent ON context_entries(parent_tag)")
            conn.commit()

    def add(
        self,
        title: str,
        content: str,
        entry_type: str,
        tags: list[str] = [],
        linked_files: list[str] = [],
        importance: int = 1,
        parent_tag: Optional[str] = None,
    ) -> int:
        """Create a new entry. Returns the new entry ID."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO entries
                (title, content, entry_type, tags, importance, linked_files, parent_tag, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    content,
                    entry_type,
                    str(tags),
                    importance,
                    str(linked_files),
                    parent_tag,
                    "manual",
                    datetime.now().isoformat(),
                ),
            )
            entry_id = cursor.lastrowid
            conn.commit()
            log.info(f"Added entry {entry_id}: {title!r}")
            return entry_id

    def get(self, entry_id: int) -> Optional[Entry]:
        """Retrieve a single entry by ID."""
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM context_entries WHERE id = ?", (entry_id,)
            ).fetchone()
            if row is None:
                return None
            # Increment access count
            conn.execute(
                "UPDATE context_entries SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                (datetime.now().isoformat(), entry_id),
            )
            conn.commit()
            return Entry(**dict(row))

    def update(self, entry_id: int, **kwargs) -> bool:
        """Update an entry. Returns True if modified."""
        if not kwargs:
            return False
        # Build SET clause dynamically
        allowed = {"title", "content", "entry_type", "tags", "importance", "linked_files", "parent_tag"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        updates["updated_at"] = datetime.now().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [entry_id]
        with get_connection(self.db_path) as conn:
            result = conn.execute(f"UPDATE context_entries SET {set_clause} WHERE id = ?", values)
            conn.commit()
            return result.rowcount > 0

    def delete(self, entry_id: int) -> bool:
        """Remove an entry."""
        with get_connection(self.db_path) as conn:
            result = conn.execute("DELETE FROM context_entries WHERE id = ?", (entry_id,))
            conn.commit()
            return result.rowcount > 0

    def list(self, entry_type: Optional[str] = None, limit: int = 100, parent_tag: Optional[str] = None) -> list[Entry]:
        """List entries, optionally filtered."""
        query = "SELECT * FROM context_entries WHERE 1=1"
        params = []
        if entry_type:
            query += " AND entry_type = ?"
            params.append(entry_type)
        if parent_tag:
            query += " AND parent_tag = ?"
            params.append(parent_tag)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with get_connection(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [Entry(**dict(r)) for r in rows]

    def exists(self, title: str, entry_type: str) -> bool:
        """Check if an entry with given title/type exists."""
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM context_entries WHERE title = ? AND entry_type = ?",
                (title, entry_type),
            ).fetchone()
            return row is not None

    def search(self, query_text: str, entry_type: Optional[str] = None, limit: int = 20) -> list[Entry]:
        """Simple LIKE-based search across entries."""
        with get_connection(self.db_path) as conn:
            sql = """
                SELECT * FROM context_entries
                WHERE (title LIKE ? OR content LIKE ?)
            """
            params = [f"%{query_text}%", f"%{query_text}%"]
            if entry_type:
                sql += " AND entry_type = ?"
                params.append(entry_type)
            sql += " LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [Entry(**dict(r)) for r in rows]

    def exists(self, title: str, entry_type: str) -> bool:
        """Check if an entry with given title/type exists."""
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM entries WHERE title = ? AND entry_type = ?",
                (title, entry_type),
            ).fetchone()
            return row is not None

    def search(self, query_text: str, entry_type: Optional[str] = None, limit: int = 20) -> list[Entry]:
        """Full-text search across entries."""
        # Build FTS query
        # (Implementation would use FTS5 virtual table; details omitted for brevity)
        # For now, fallback to simple LIKE
        with get_connection(self.db_path) as conn:
            sql = """
                SELECT * FROM entries
                WHERE (title LIKE ? OR content LIKE ?)
            """
            params = [f"%{query_text}%", f"%{query_text}%"]
            if entry_type:
                sql += " AND entry_type = ?"
                params.append(entry_type)
            sql += " LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [Entry(**dict(r)) for r in rows]
