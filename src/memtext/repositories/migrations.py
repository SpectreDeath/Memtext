"""Migrations — database schema version management."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import sqlite3

from ..core import get_db_path, get_connection, log


class MigrationManager:
    """Manages database schema migrations and version tracking."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or get_db_path()
        self._ensure_meta_table()

    def _ensure_meta_table(self) -> None:
        """Create the schema_version table if missing."""
        with get_connection(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    description TEXT
                )
            """)
            conn.commit()

    def get_current_version(self) -> int:
        """Return the current schema version (0 if none)."""
        with get_connection(self.db_path) as conn:
            row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
            return row[0] if row and row[0] is not None else 0

    def apply(self, target_version: int, description: str = "") -> None:
        """Apply migrations up to target_version."""
        # Migration functions keyed by version number
        migrations = {
            1: self._migrate_1_initial_schema,
            2: self._migrate_2_add_fts,
            3: self._migrate_3_add_reminders,
            # Extend as needed
        }
        current = self.get_current_version()
        if current >= target_version:
            log.info(f"Database already at version {current}")
            return
        for ver in range(current + 1, target_version + 1):
            migrator = migrations.get(ver)
            if migrator:
                log.info(f"Applying migration v{ver}: {description or migrator.__doc__}")
                migrator()
                self._record_version(ver, description or migrator.__doc__)
            else:
                raise ValueError(f"No migration defined for version {ver}")

    def _record_version(self, version: int, description: str) -> None:
        with get_connection(self.db_path) as conn:
            conn.execute(
                "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                (version, description),
            )
            conn.commit()

    # --- Individual migrations ---
    def _migrate_1_initial_schema(self) -> None:
        """Create core tables: entries, context_entries, etc."""
        # Handled by EntryManager._init_db; this is a no-op here since tables auto-created
        pass

    def _migrate_2_add_fts(self) -> None:
        """Add FTS5 virtual table and triggers."""
        with get_connection(self.db_path) as conn:
            conn.execute("DROP TABLE IF EXISTS context_fts")
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS context_fts USING fts5(title, content, tokensize=1)"
            )
            # Populate from existing entries
            rows = conn.execute("SELECT id, title, content FROM entries").fetchall()
            for row in rows:
                conn.execute(
                    "INSERT INTO context_fts (rowid, title, content) VALUES (?, ?, ?)",
                    (row["id"], row["title"], row["content"]),
                )
            conn.commit()

    def _migrate_3_add_reminders(self) -> None:
        """Create reminders table."""
        with get_connection(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_id INTEGER NOT NULL,
                    message TEXT,
                    remind_at TIMESTAMP NOT NULL,
                    completed BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(remind_at, completed)")
            conn.commit()
