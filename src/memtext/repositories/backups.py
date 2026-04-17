"""Backup and restore operations for the database."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import sqlite3
import shutil

from ..core import get_db_path, get_connection, log


class BackupService:
    """Manages database backups."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or get_db_path()
        self.backups_dir = self.db_path.parent / "backups"
        self.backups_dir.mkdir(exist_ok=True)

    def create(self, backup_type: str = "manual") -> Optional[int]:
        """Create a timestamped backup. Returns backup ID or None on failure."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"memtext_{backup_type}_{timestamp}.db"
        backup_path = self.backups_dir / backup_name
        try:
            # SQLite backup API (safe, no lock)
            with get_connection(self.db_path) as src:
                with sqlite3.connect(backup_path) as dst:
                    src.backup(dst)
            log.info(f"Backup created: {backup_path.name}")
            # Record in backups table
            with get_connection(self.db_path) as conn:
                cursor = conn.execute(
                    "INSERT INTO _backups (backup_path, backup_type, created_at) VALUES (?, ?, ?)",
                    (str(backup_path), backup_type, datetime.now().isoformat()),
                )
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            log.error(f"Backup failed: {e}")
            return None

    def list(self) -> list[dict]:
        """Return all available backups with metadata."""
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, backup_path, backup_type, created_at FROM _backups ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def restore(self, backup_id: int, backup_path: Optional[Path] = None) -> bool:
        """Restore database from a backup."""
        with get_connection(self.db_path) as conn:
            if backup_path is None:
                row = conn.execute("SELECT backup_path FROM _backups WHERE id = ?", (backup_id,)).fetchone()
                if row is None:
                    return False
                backup_path = Path(row["backup_path"])
        # Restore using SQLite backup API
        try:
            with sqlite3.connect(backup_path) as src:
                with get_connection(self.db_path) as dst:
                    src.backup(dst)
            log.info(f"Restored from backup: {backup_path.name}")
            return True
        except Exception as e:
            log.error(f"Restore failed: {e}")
            return False
