"""Template registry — predefined entry templates."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from ..core import get_db_path, get_connection, log


class TemplateRegistry:
    """Manages entry templates."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or get_db_path()
        self._ensure_table()

    def _ensure_table(self) -> None:
        with get_connection(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    entry_type TEXT NOT NULL,
                    fields_schema TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def create(self, name: str, description: str, entry_type: str, fields_schema: dict = {}) -> bool:
        """Define a new template."""
        try:
            with get_connection(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO templates (name, description, entry_type, fields_schema) VALUES (?, ?, ?, ?)",
                    (name, description, entry_type, str(fields_schema)),
                )
                conn.commit()
            log.info(f"Template created: {name}")
            return True
        except sqlite3.IntegrityError:
            return False  # already exists

    def get(self, name: str) -> Optional[dict]:
        """Retrieve a template by name."""
        with get_connection(self.db_path) as conn:
            row = conn.execute("SELECT * FROM templates WHERE name = ?", (name,)).fetchone()
            return dict(row) if row else None

    def list(self) -> list[dict]:
        """List all templates."""
        with get_connection(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM templates ORDER BY name").fetchall()
            return [dict(r) for r in rows]

    def populate_defaults(self) -> None:
        """Create built-in templates if none exist."""
        existing = self.list()
        if existing:
            return  # Already populated
        defaults = [
            ("decision", "Architecture decision record", "decision", {"rationale": "text", "alternatives": "list"}),
            ("note", "General note", "note", {"context": "text"}),
            ("error", "Error and workaround", "error", {"error_msg": "text", "fix": "text"}),
        ]
        for name, desc, etype, schema in defaults:
            self.create(name, desc, etype, schema)
        log.info("Default templates populated")
