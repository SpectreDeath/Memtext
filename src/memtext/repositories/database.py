"""Repositories for Memtext context storage.

Each class encapsulates a cohesive set of database operations.
All classes share a common database path and connection handling.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def get_db_path() -> Path:
    return Path.cwd() / ".context" / "memtext.db"


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Get a database connection with row factory set."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path) -> None:
    """Initialize the database with required tables and FTS5 virtual table."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS context_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                entry_type TEXT NOT NULL,
                tags TEXT,
                importance INTEGER DEFAULT 1,
                linked_files TEXT,
                parent_tag TEXT,
                source TEXT DEFAULT 'manual',
                trust_score REAL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                last_accessed TEXT,
                access_count INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS context_entries_fts
            USING fts5(title, content, entry_type, tags, content='context_entries', content_rowid='id')
        """)
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS context_entries_ai
            AFTER INSERT ON context_entries BEGIN
                INSERT INTO context_entries_fts(rowid, title, content, entry_type, tags)
                VALUES (new.id, new.title, new.content, new.entry_type, new.tags);
            END
        """)
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS context_entries_ad
            AFTER DELETE ON context_entries BEGIN
                INSERT INTO context_entries_fts(context_entries_fts, rowid, title, content, entry_type, tags)
                VALUES ('delete', old.id, old.title, old.content, old.entry_type, old.tags);
            END
        """)
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS context_entries_au
            AFTER UPDATE ON context_entries BEGIN
                INSERT INTO context_entries_fts(context_entries_fts, rowid, title, content, entry_type, tags)
                VALUES ('delete', old.id, old.title, old.content, old.entry_type, old.tags);
                INSERT INTO context_entries_fts(rowid, title, content, entry_type, tags)
                VALUES (new.id, new.title, new.content, new.entry_type, new.tags);
            END
        """)
        # Reflection insights table for offline consolidation (Dreams feature)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reflection_insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                source TEXT DEFAULT 'memtext-reflection-engine',
                trust_score REAL DEFAULT 0.85,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        logger.info("Database initialized at %s", db_path)


class SQLiteEntryManager:
    """Manages context entries in SQLite database."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or get_db_path()
        init_db(self.db_path)

    def add(
        self,
        title: str,
        content: str,
        entry_type: str,
        tags: list[str] = [],
        linked_files: list[str] = [],
        importance: int = 1,
        parent_tag: Optional[str] = None,
        source: str = "manual",
        trust_score: float = 1.0,
    ) -> int:
        """Create a new entry. Returns the new entry ID."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO context_entries
                (title, content, entry_type, tags, importance, linked_files, parent_tag, source, trust_score, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    content,
                    entry_type,
                    str(tags),
                    importance,
                    str(linked_files),
                    parent_tag,
                    source,
                    trust_score,
                    datetime.now().isoformat(),
                ),
            )
            entry_id = cursor.lastrowid
            conn.commit()
            logger.info(f"Added entry {entry_id}: {title!r}")
            return entry_id

    def get(self, entry_id: int) -> Optional[dict]:
        """Retrieve a single entry by ID."""
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM context_entries WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            conn.close()
            return None
        conn.execute(
            "UPDATE context_entries SET last_accessed = ?, access_count = access_count + 1 WHERE id = ?",
            (datetime.now().isoformat(), entry_id),
        )
        conn.commit()
        conn.close()
        return dict(row)

    def exists(self, title: str, entry_type: str = "note") -> bool:
        """Check if an entry with the given title and type exists."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM context_entries WHERE title = ? AND entry_type = ?",
                (title, entry_type),
            )
            return cursor.fetchone() is not None

    def list(
        self,
        entry_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        importance_min: int = 1,
        parent_tag: Optional[str] = None,
    ) -> list[dict]:
        """List entries with optional filters."""
        with get_connection(self.db_path) as conn:
            query = "SELECT * FROM context_entries WHERE importance >= ?"
            params: list = [importance_min]
            if entry_type:
                query += " AND entry_type = ?"
                params.append(entry_type)
            if parent_tag:
                query += " AND parent_tag = ?"
                params.append(parent_tag)
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def search(self, query: str, entry_type: str = None, limit: int = 10) -> list[dict]:
        """Full-text search using FTS5."""
        with get_connection(self.db_path) as conn:
            if not query or not query.strip():
                # Empty query - just list entries
                sql = "SELECT * FROM context_entries WHERE 1=1"
                params = []
                if entry_type:
                    sql += " AND entry_type = ?"
                    params.append(entry_type)
                sql += " ORDER BY created_at DESC LIMIT ?"
                params.append(limit)
                cursor = conn.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]

            if entry_type:
                cursor = conn.execute(
                    """
                    SELECT e.* FROM context_entries e
                    JOIN context_entries_fts f ON e.id = f.rowid
                    WHERE context_entries_fts MATCH ? AND e.entry_type = ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (query, entry_type, limit),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT e.* FROM context_entries e
                    JOIN context_entries_fts f ON e.id = f.rowid
                    WHERE context_entries_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (query, limit),
                )
            return [dict(row) for row in cursor.fetchall()]

    def update(
        self,
        entry_id: int,
        title: Optional[str] = None,
        content: Optional[str] = None,
        entry_type: Optional[str] = None,
        tags: Optional[list[str]] = None,
        linked_files: Optional[list[str]] = None,
        importance: Optional[int] = None,
        parent_tag: Optional[str] = None,
        source: Optional[str] = None,
        trust_score: Optional[float] = None,
    ) -> bool:
        """Update an existing entry. Returns True if updated."""
        updates = []
        params = []
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if content is not None:
            updates.append("content = ?")
            params.append(content)
        if entry_type is not None:
            updates.append("entry_type = ?")
            params.append(entry_type)
        if tags is not None:
            updates.append("tags = ?")
            params.append(str(tags))
        if linked_files is not None:
            updates.append("linked_files = ?")
            params.append(str(linked_files))
        if importance is not None:
            updates.append("importance = ?")
            params.append(importance)
        if parent_tag is not None:
            updates.append("parent_tag = ?")
            params.append(parent_tag)
        if source is not None:
            updates.append("source = ?")
            params.append(source)
        if trust_score is not None:
            updates.append("trust_score = ?")
            params.append(trust_score)

        if not updates:
            return False

        params.append(entry_id)
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                f"UPDATE context_entries SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete(self, entry_id: int) -> bool:
        """Delete an entry by ID."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM context_entries WHERE id = ?", (entry_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_for_review(self, limit: int = 20) -> list[dict]:
        """Get entries that need human review (trust_score < 1.0 or source != 'manual')."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT * FROM context_entries
                WHERE trust_score < 1.0 OR source != 'manual'
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def approve(self, entry_id: int) -> bool:
        """Approve an entry (set trust_score to 1.0 and source to 'manual')."""
        return self.update(entry_id, trust_score=1.0, source="manual")

    def reject(self, entry_id: int) -> bool:
        """Reject and delete an entry."""
        return self.delete(entry_id)

    def get_entry_history(self, entry_id: int) -> list[dict]:
        """Get history for an entry. Returns current entry as single-item history."""
        entry = self.get(entry_id)
        if entry:
            return [entry]
        return []


class SQLiteProjectRegistry:
    """Manages the global project registry at ~/.config/memtext/projects.db."""

    def __init__(self):
        config_dir = Path.home() / ".config" / "memtext"
        config_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = config_dir / "projects.db"
        self._init_db()

    def _init_db(self) -> None:
        with get_connection(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    last_accessed TEXT
                )
            """)
            conn.commit()

    def register(self, name: str, path: Path) -> int:
        """Register a project. Returns the project ID."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO projects (name, path, created_at, last_accessed) VALUES (?, ?, ?, ?)",
                (name, str(path.resolve()), datetime.now().isoformat(), datetime.now().isoformat()),
            )
            conn.commit()
            if cursor.lastrowid:
                return cursor.lastrowid
            # If it already existed, get the ID
            row = conn.execute("SELECT id FROM projects WHERE path = ?", (str(path.resolve()),)).fetchone()
            return row["id"] if row else -1

    def list(self) -> list[dict]:
        """List all registered projects."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute("SELECT * FROM projects ORDER BY last_accessed DESC")
            return [dict(row) for row in cursor.fetchall()]

    def scan_projects(self, root: Path = Path.cwd()) -> list[dict]:
        """Scan for projects with .context directories."""
        projects = []
        for context_dir in root.rglob(".context"):
            if context_dir.is_dir():
                project_path = context_dir.parent
                project_name = project_path.name
                self.register(project_name, project_path)
                projects.append({"name": project_name, "path": str(project_path)})
        return projects


# Alias for backward compatibility
EntryManager = SQLiteEntryManager