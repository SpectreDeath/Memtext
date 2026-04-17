"""Webhook dispatcher — external event notifications."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional, List
import urllib.request
import urllib.error
import json

from ..core import get_db_path, get_connection, log


class WebhookService:
    """Manages webhook subscriptions and event delivery."""

    def __init__(self, db_path=None):
        self.db_path = db_path or get_db_path()
        self._ensure_table()

    def _ensure_table(self) -> None:
        with get_connection(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS webhooks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    event TEXT NOT NULL,
                    secret TEXT,
                    active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def register(self, url: str, event: str, secret: Optional[str] = None) -> int:
        """Subscribe a webhook to an event type."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO webhooks (url, event, secret) VALUES (?, ?, ?)",
                (url, event, secret),
            )
            conn.commit()
            log.info(f"Webhook {cursor.lastrowid} registered for {event}")
            return cursor.lastrowid

    def list(self, active_only: bool = True) -> List[dict]:
        """List all webhooks."""
        query = "SELECT * FROM webhooks"
        params = []
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY created_at DESC"
        with get_connection(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def remove(self, webhook_id: int) -> bool:
        """Delete a webhook."""
        with get_connection(self.db_path) as conn:
            result = conn.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
            conn.commit()
            return result.rowcount > 0

    def trigger(self, event_type: str, entry_data: dict) -> None:
        """POST webhook payloads for all subscribers of event_type."""
        endpoints = self.list(active_only=True)
        for wh in endpoints:
            if wh["event"] != event_type:
                continue
            payload = {
                "event": event_type,
                "data": entry_data,
                "timestamp": datetime.now().isoformat(),
            }
            try:
                req = urllib.request.Request(
                    wh["url"],
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status not in (200, 201, 202, 204):
                        log.warning(f"Webhook {wh['id']} returned {resp.status}")
            except Exception as e:
                log.error(f"Webhook {wh['id']} delivery failed: {e}")
