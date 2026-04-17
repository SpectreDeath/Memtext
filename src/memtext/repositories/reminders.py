"""Reminder service — time-based entry notifications."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from ..core import get_db_path, get_connection, log


class ReminderService:
    """Manages reminders linked to entries."""

    def __init__(self, db_path=None, entry_manager=None):
        from ..repositories.database import EntryManager  # lazy to avoid circular
        self.db_path = db_path or get_db_path()
        self.entry_manager = entry_manager or EntryManager(self.db_path)
        self._ensure_table()

    def _ensure_table(self) -> None:
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

    def add(self, entry_id: int, remind_at: datetime, message: str = "") -> int:
        """Schedule a reminder."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO reminders (entry_id, message, remind_at) VALUES (?, ?, ?)",
                (entry_id, message, remind_at.isoformat()),
            )
            conn.commit()
            log.info(f"Reminder {cursor.lastrowid} set for entry {entry_id} at {remind_at}")
            return cursor.lastrowid

    def get_pending(self) -> List[dict]:
        """Return reminders due now (not completed, time <= now)."""
        now = datetime.now().isoformat()
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE completed = 0 AND remind_at <= ? ORDER BY remind_at",
                (now,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all(self, entry_id: int) -> List[dict]:
        """Return all reminders for an entry."""
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE entry_id = ? ORDER BY remind_at", (entry_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def complete(self, reminder_id: int) -> bool:
        """Mark a reminder as done."""
        with get_connection(self.db_path) as conn:
            result = conn.execute(
                "UPDATE reminders SET completed = 1 WHERE id = ?", (reminder_id,)
            )
            conn.commit()
            return result.rowcount > 0
