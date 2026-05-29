"""Project registry — cross-project context linking."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def get_connection(db_path=None):
    db_path = db_path or get_db_path()
    return sqlite3.connect(db_path)


def get_db_path() -> Path:
    return Path.cwd() / ".context" / "memtext.db"


PROJECT_REGISTRY = None


class ProjectRegistry:
    """Manages the global project registry database."""

    def __init__(self, registry_path: Optional[Path] = None):
        self.registry_path = registry_path or self._get_registry_path()
        self._ensure_table()

    @staticmethod
    def _get_registry_path() -> Path:
        global PROJECT_REGISTRY
        path = Path.home() / ".config" / "memtext" / "projects.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        PROJECT_REGISTRY = path
        return path

    def _ensure_table(self) -> None:
        with get_connection(self.registry_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def register(self, path: str, name: str = None) -> int:
        """Add a project to the registry."""
        path = str(Path(path).resolve()) if isinstance(path, str) else str(path)
        name = name or Path(path).name
        with get_connection(self.registry_path) as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO projects (path, name) VALUES (?, ?)",
                (path, name),
            )
            conn.commit()
            logger.info(f"Registered project: {name} at {path}")
            return cursor.lastrowid

    def list(self) -> List[dict]:
        """Return all registered projects."""
        with get_connection(self.registry_path) as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY name").fetchall()
            return [dict(r) for r in rows]

    def scan(self, root_path=None) -> List[dict]:
        """Recursively find projects (directories containing .context/)."""
        found = []
        root = Path(root_path) if root_path else Path.cwd()
        for dirpath, dirnames, filenames in root.walk():
            if ".context" in dirnames:
                project_path = Path(dirpath)
                found.append(
                    {
                        "path": str(project_path),
                        "name": project_path.name,
                        "registered": False,
                    }
                )
        return found
