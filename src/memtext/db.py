"""Database operations for memtext."""

from pathlib import Path
import sqlite3
import json
from datetime import datetime


def get_db_path() -> Path:
    return Path.cwd() / ".context" / "memtext.db"


def get_db_version() -> int:
    """Get current schema version for migrations."""
    db_path = get_db_path()
    if not db_path.exists():
        return 0

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if schema_version table exists
    cursor.execute("""
        SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'
    """)

    if not cursor.fetchone():
        conn.close()
        return 0

    cursor.execute(
        "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1"
    )
    row = cursor.fetchone()
    conn.close()

    return row[0] if row else 0


def run_migrations():
    """Run database migrations for new features."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    current_version = get_db_version()

    # Migration 1: Add schema_version table if not exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migration 1: Add reminders table (version 1)
    if current_version < 1:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER NOT NULL,
                remind_at TIMESTAMP NOT NULL,
                message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed INTEGER DEFAULT 0,
                FOREIGN KEY (entry_id) REFERENCES context_entries(id) ON DELETE CASCADE
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_reminders_remind_at ON reminders(remind_at)"
        )
        cursor.execute("INSERT INTO schema_version (version) VALUES (1)")
        conn.commit()

    # Migration 2: Add templates table (version 2)
    if current_version < 2:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                entry_type TEXT NOT NULL,
                fields TEXT NOT NULL,  -- JSON schema for template fields
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("INSERT INTO schema_version (version) VALUES (2)")
        conn.commit()

    # Migration 3: Add version_history table (version 3)
    if current_version < 3:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS version_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER NOT NULL,
                field_name TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (entry_id) REFERENCES context_entries(id) ON DELETE CASCADE
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_version_history_entry ON version_history(entry_id)"
        )
        cursor.execute("INSERT INTO schema_version (version) VALUES (3)")
        conn.commit()

    # Migration 4: Add encryption keys table (version 4)
    if current_version < 4:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS encryption_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER NOT NULL,
                key_fingerprint TEXT NOT NULL,
                encrypted_data BLOB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (entry_id) REFERENCES context_entries(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("INSERT INTO schema_version (version) VALUES (4)")
        conn.commit()

    # Migration 5: Add webhooks table (version 5)
    if current_version < 5:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS webhooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                event TEXT NOT NULL,  -- create, update, delete
                secret TEXT,
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("INSERT INTO schema_version (version) VALUES (5)")
        conn.commit()

    # Migration 6: Add backups table (version 6)
    if current_version < 6:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_path TEXT NOT NULL,
                backup_type TEXT DEFAULT 'manual',  -- manual, scheduled
                entry_count INTEGER,
                size_bytes INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("INSERT INTO schema_version (version) VALUES (6)")
        conn.commit()

    # Migration 7: Add tag hierarchy table (version 7)
    if current_version < 7:
        # Check if parent_tag column already exists
        cursor.execute("PRAGMA table_info(context_entries)")
        columns = [row[1] for row in cursor.fetchall()]
        if "parent_tag" not in columns:
            cursor.execute("ALTER TABLE context_entries ADD COLUMN parent_tag TEXT")
        cursor.execute("INSERT INTO schema_version (version) VALUES (7)")
        conn.commit()

    # Migration 8: Add encryption support (version 8)
    if current_version < 8:
        cursor.execute(
            "ALTER TABLE context_entries ADD COLUMN is_encrypted INTEGER DEFAULT 0"
        )
        cursor.execute("ALTER TABLE context_entries ADD COLUMN encrypted_content TEXT")
        cursor.execute("INSERT INTO schema_version (version) VALUES (8)")
        conn.commit()

    conn.close()


def init_db() -> Path:
    db_path = get_db_path()
    db_path.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL,
            name TEXT,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS context_fts USING fts5(title, content, entry_type, tags)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_context_entries_last_accessed 
        ON context_entries(last_accessed)
    """)

    conn.commit()
    conn.close()

    run_migrations()
    populate_default_templates()
    return db_path


def entry_exists(title: str, entry_type: str = None) -> bool:
    """Check if an entry with the same title and type already exists."""
    db_path = get_db_path()
    if not db_path.exists():
        return False
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    if entry_type:
        cursor.execute(
            "SELECT 1 FROM context_entries WHERE title = ? AND entry_type = ?",
            (title, entry_type),
        )
    else:
        cursor.execute("SELECT 1 FROM context_entries WHERE title = ?", (title,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def update_fts(
    title: str, content: str, entry_type: str, tags: str, parent_tag: str = None
):
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO context_fts (title, content, entry_type, tags, parent_tag) VALUES (?, ?, ?, ?, ?)",
            (title, content, entry_type, tags or "", parent_tag),
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error in update_fts: {e}")
    finally:
        if "conn" in locals():
            conn.close()


def add_entry(
    title: str,
    content: str,
    entry_type: str = "note",
    tags: list = None,
    linked_files: list = None,
    importance: int = 1,
    parent_tag: str = None,
) -> int:
    if entry_exists(title, entry_type):
        return -1

    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO context_entries (title, content, entry_type, tags, linked_files, importance, parent_tag) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                title,
                content,
                entry_type,
                ",".join(tags or []),
                ",".join(linked_files or []),
                importance,
                parent_tag,
            ),
        )
        entry_id = cursor.lastrowid
        conn.commit()
        update_fts(title, content, entry_type, ",".join(tags or []))
        return entry_id
    except sqlite3.Error as e:
        print(f"Database error in add_entry: {e}")
        return -1
    finally:
        if "conn" in locals():
            conn.close()


def get_entry(entry_id: int) -> dict:
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM context_entries WHERE id=?", (entry_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_entry(entry_id: int, **kwargs) -> bool:
    # Get current values before updating
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM context_entries WHERE id=?", (entry_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False
    old_values = dict(row)
    conn.close()

    # Record version changes for each field being updated
    for field, new_value in kwargs.items():
        if field in old_values:
            old_val = old_values[field]
            # Only record if value actually changed
            if str(old_val) != str(new_value):
                record_version_change(entry_id, field, old_val, new_value)

    # Perform the update
    fields = ", ".join(f"{k}=?" for k in kwargs.keys())
    values = list(kwargs.values()) + [entry_id]
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE context_entries SET {fields} WHERE id=?", values)
    conn.commit()

    # Update FTS if title or content changed
    if "title" in kwargs or "content" in kwargs:
        cursor.execute(
            "SELECT title, content, entry_type, tags, parent_tag FROM context_entries WHERE id=?",
            (entry_id,),
        )
        row = cursor.fetchone()
        if row:
            # Delete old FTS entry and insert new one
            cursor.execute("DELETE FROM context_fts WHERE rowid = ?", (entry_id,))
            cursor.execute(
                "INSERT INTO context_fts (title, content, entry_type, tags, parent_tag) VALUES (?, ?, ?, ?, ?)",
                (row[0], row[1], row[2], row[3] or "", row[4]),
            )
            conn.commit()

    conn.close()
    return True


def delete_entry(entry_id: int) -> bool:
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM context_entries WHERE id=?", (entry_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def query_entries(
    search_text: str = None,
    entry_type: str = None,
    min_importance: int = None,
    tags: str = None,
    parent_tag: str = None,
    limit: int = 10,
    use_fts: bool = True,
) -> list:
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Use FTS5 for text search if available
    if search_text and use_fts:
        try:
            fts_query = f"{search_text}*"
            cursor.execute(
                """SELECT e.* FROM context_entries e
                   JOIN context_fts f ON e.id = f.rowid
                   WHERE context_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (fts_query, limit),
            )
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except sqlite3.Error:
            pass

    # Fallback to LIKE search
    query = "SELECT * FROM context_entries WHERE 1=1"
    params = []

    if search_text:
        query += " AND (title LIKE ? OR content LIKE ?)"
        params.extend([f"%{search_text}%", f"%{search_text}%"])

    if entry_type:
        query += " AND entry_type = ?"
        params.append(entry_type)

    if min_importance:
        query += " AND importance >= ?"
        params.append(min_importance)

    if tags:
        for tag in tags.split(","):
            query += " AND tags LIKE ?"
            params.append(f"%{tag}%")

    if parent_tag:
        query += " AND parent_tag = ?"
        params.append(parent_tag)

    query += f" ORDER BY importance DESC, last_accessed DESC LIMIT {limit}"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def list_entries(
    entry_type: str = None, limit: int = 10, parent_tag: str = None
) -> list:
    return query_entries(entry_type=entry_type, limit=limit, parent_tag=parent_tag)


PROJECT_REGISTRY = Path.home() / ".config" / "memtext" / "projects.db"


def get_registry_path() -> Path:
    PROJECT_REGISTRY.parent.mkdir(exist_ok=True)
    return PROJECT_REGISTRY


def init_registry():
    reg_path = get_registry_path()
    conn = sqlite3.connect(reg_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL,
            name TEXT,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    return reg_path


def register_project(path: str, name: str = None) -> int:
    reg_path = get_registry_path()
    if not reg_path.exists():
        init_registry()

    name = name or Path(path).name
    conn = sqlite3.connect(reg_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO projects (path, name, last_active) VALUES (?, ?, CURRENT_TIMESTAMP)",
        (path, name),
    )
    project_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return project_id


def list_projects() -> list:
    reg_path = get_registry_path()
    if not reg_path.exists():
        return []

    conn = sqlite3.connect(reg_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects ORDER BY last_active DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def scan_for_projects(root_path: str = None) -> list:
    root_path = root_path or str(Path.cwd())
    projects = []
    for path in Path(root_path).rglob(".context"):
        if path.is_dir():
            project_path = str(path.parent)
            if project_path not in [p["path"] for p in list_projects()]:
                projects.append(project_path)
    return projects


def add_shared_entry(
    title: str,
    content: str,
    entry_type: str = "note",
    tags: list = None,
    importance: int = 1,
    project_id: int = None,
) -> int:
    """Add a shared entry available across projects."""
    db_path = get_db_path()
    if not db_path.exists():
        return -1

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO context_entries 
               (title, content, entry_type, tags, importance, is_shared, project_id) 
               VALUES (?, ?, ?, ?, ?, 1, ?)""",
            (title, content, entry_type, ",".join(tags or []), importance, project_id),
        )
        entry_id = cursor.lastrowid
        conn.commit()
        update_fts(title, content, entry_type, ",".join(tags or []))
        return entry_id
    except sqlite3.Error:
        return -1
    finally:
        if "conn" in locals():
            conn.close()


def get_shared_entries(project_id: int = None) -> list:
    """Get shared entries, optionally filtered by project."""
    db_path = get_db_path()
    if not db_path.exists():
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if project_id:
        cursor.execute(
            "SELECT * FROM context_entries WHERE is_shared = 1 AND project_id = ? ORDER BY importance DESC",
            (project_id,),
        )
    else:
        cursor.execute(
            "SELECT * FROM context_entries WHERE is_shared = 1 ORDER BY importance DESC"
        )

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def make_shared(entry_id: int) -> bool:
    """Mark an entry as shared."""
    db_path = get_db_path()
    if not db_path.exists():
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE context_entries SET is_shared = 1 WHERE id = ?", (entry_id,))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success


# Reminder management
def add_reminder(entry_id: int, remind_at: str, message: str = None) -> int:
    """Add a reminder for an entry. Returns reminder ID or -1 on error."""
    db_path = get_db_path()
    if not db_path.exists():
        return -1

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO reminders (entry_id, remind_at, message) VALUES (?, ?, ?)",
            (entry_id, remind_at, message),
        )
        reminder_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return reminder_id
    except sqlite3.Error:
        return -1


def get_pending_reminders() -> list:
    """Get all pending reminders (not completed, time <= now)."""
    db_path = get_db_path()
    if not db_path.exists():
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.*, e.title, e.content
        FROM reminders r
        JOIN context_entries e ON r.entry_id = e.id
        WHERE r.completed = 0 AND r.remind_at <= datetime('now')
        ORDER BY r.remind_at ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_reminders(entry_id: int = None) -> list:
    """Get all reminders, optionally filtered by entry_id."""
    db_path = get_db_path()
    if not db_path.exists():
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if entry_id:
        cursor.execute(
            "SELECT * FROM reminders WHERE entry_id = ? ORDER BY remind_at DESC",
            (entry_id,),
        )
    else:
        cursor.execute("SELECT * FROM reminders ORDER BY remind_at DESC")

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# Backup/Restore
def create_backup(backup_type: str = "manual") -> Optional[int]:
    """Create a backup of the database. Returns backup ID or None on failure."""
    db_path = get_db_path()
    if not db_path.exists():
        return None

    backups_dir = db_path.parent / "backups"
    backups_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"backup_{timestamp}.db"
    backup_path = backups_dir / backup_filename

    try:
        # Use SQLite backup API for consistency
        source_conn = sqlite3.connect(db_path)
        dest_conn = sqlite3.connect(str(backup_path))
        source_conn.backup(dest_conn)
        source_conn.close()
        dest_conn.close()

        # Get backup size
        size_bytes = backup_path.stat().st_size

        # Count entries in backup
        backup_conn = sqlite3.connect(str(backup_path))
        cursor = backup_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM context_entries")
        entry_count = cursor.fetchone()[0]
        backup_conn.close()

        # Record in backups table
        main_conn = sqlite3.connect(db_path)
        cursor = main_conn.cursor()
        cursor.execute(
            "INSERT INTO backups (backup_path, backup_type, entry_count, size_bytes) VALUES (?, ?, ?, ?)",
            (str(backup_path), backup_type, entry_count, size_bytes),
        )
        backup_id = cursor.lastrowid
        main_conn.commit()
        main_conn.close()

        return backup_id
    except sqlite3.Error:
        return None


def list_backups() -> list:
    """List all backups recorded in the database."""
    db_path = get_db_path()
    if not db_path.exists():
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM backups ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def restore_backup(backup_id: int = None, backup_path: Path = None) -> bool:
    """Restore database from a backup."""
    db_path = get_db_path()
    if not db_path.exists():
        return False

    # Resolve backup path
    if backup_id is not None:
        backups = list_backups()
        backup = next((b for b in backups if b["id"] == backup_id), None)
        if not backup:
            return False
        backup_file = Path(backup["backup_path"])
    elif backup_path:
        backup_file = backup_path
    else:
        return False

    if not backup_file.exists():
        return False

    try:
        # Restore using SQLite backup API
        backup_conn = sqlite3.connect(str(backup_file))
        dest_conn = sqlite3.connect(str(db_path))
        backup_conn.backup(dest_conn)
        backup_conn.close()
        dest_conn.close()
        return True
    except sqlite3.Error:
        return False


# Webhooks
def add_webhook(url: str, event: str, secret: str = None) -> int:
    """Add a new webhook subscription. Returns webhook ID or -1 on error."""
    db_path = get_db_path()
    if not db_path.exists():
        return -1

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO webhooks (url, event, secret) VALUES (?, ?, ?)",
            (url, event, secret),
        )
        webhook_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return webhook_id
    except sqlite3.Error:
        return -1


def list_webhooks(active_only: bool = True) -> list:
    """List all webhooks."""
    db_path = get_db_path()
    if not db_path.exists():
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if active_only:
        cursor.execute(
            "SELECT * FROM webhooks WHERE active = 1 ORDER BY created_at DESC"
        )
    else:
        cursor.execute("SELECT * FROM webhooks ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def remove_webhook(webhook_id: int) -> bool:
    """Delete a webhook."""
    db_path = get_db_path()
    if not db_path.exists():
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success


def trigger_webhook(event_type: str, entry_data: dict) -> None:
    """Trigger webhooks for a given event type."""
    import threading
    import json
    import urllib.request

    webhooks = list_webhooks(active_only=True)
    relevant = [w for w in webhooks if w["event"] in [event_type, "all"]]

    def send_webhook(webhook):
        try:
            payload = {
                "event": event_type,
                "entry_id": entry_data.get("id"),
                "title": entry_data.get("title"),
                "entry_type": entry_data.get("entry_type"),
                "timestamp": datetime.now().isoformat(),
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                webhook["url"],
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                # Optionally check resp.status == 200
                pass
        except Exception:
            # Silent failure for webhooks
            pass

    for w in relevant:
        threading.Thread(target=send_webhook, args=(w,), daemon=True).start()

    # Resolve backup path
    if backup_id is not None:
        backups = list_backups()
        backup = next((b for b in backups if b["id"] == backup_id), None)
        if not backup:
            return False
        backup_file = Path(backup["backup_path"])
    elif backup_path:
        backup_file = backup_path
    else:
        return False

    if not backup_file.exists():
        return False

    try:
        # Restore using SQLite backup API
        backup_conn = sqlite3.connect(str(backup_file))
        dest_conn = sqlite3.connect(str(db_path))
        backup_conn.backup(dest_conn)
        backup_conn.close()
        dest_conn.close()
        return True
    except sqlite3.Error:
        return False


def complete_reminder(reminder_id: int) -> bool:
    """Mark a reminder as completed."""
    db_path = get_db_path()
    if not db_path.exists():
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE reminders SET completed = 1 WHERE id = ?", (reminder_id,))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success


# Version history
def record_version_change(entry_id: int, field_name: str, old_value, new_value) -> bool:
    """Record a change to an entry's field."""
    db_path = get_db_path()
    if not db_path.exists():
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO version_history (entry_id, field_name, old_value, new_value) VALUES (?, ?, ?, ?)",
            (
                entry_id,
                field_name,
                str(old_value) if old_value is not None else None,
                str(new_value) if new_value is not None else None,
            ),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error:
        return False


def get_entry_history(entry_id: int) -> list:
    """Get version history for an entry."""
    db_path = get_db_path()
    if not db_path.exists():
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM version_history WHERE entry_id = ? ORDER BY changed_at DESC",
        (entry_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# Template management
def create_template(
    name: str, description: str, entry_type: str, fields_schema: dict
) -> bool:
    """Create a new entry template."""
    db_path = get_db_path()
    if not db_path.exists():
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO templates (name, description, entry_type, fields) VALUES (?, ?, ?, ?)",
            (name, description, entry_type, json.dumps(fields_schema)),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error:
        return False


def get_template(name: str) -> dict:
    """Get a template by name."""
    db_path = get_db_path()
    if not db_path.exists():
        return None

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM templates WHERE name = ?", (name,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def list_templates() -> list:
    """List all templates."""
    db_path = get_db_path()
    if not db_path.exists():
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM templates ORDER BY name")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def populate_default_templates():
    """Create default templates if they don't exist."""
    default_templates = [
        {
            "name": "decision",
            "description": "Architecture or technical decision",
            "entry_type": "decision",
            "fields_schema": {
                "title": {"type": "string", "required": True},
                "content": {"type": "string", "required": True},
                "tags": {"type": "array", "default": ["decision"]},
                "importance": {"type": "integer", "default": 3},
            },
        },
        {
            "name": "pattern",
            "description": "Reusable pattern discovered",
            "entry_type": "pattern",
            "fields_schema": {
                "title": {"type": "string", "required": True},
                "content": {"type": "string", "required": True},
                "tags": {"type": "array", "default": ["pattern"]},
                "importance": {"type": "integer", "default": 3},
            },
        },
        {
            "name": "error",
            "description": "Error and workaround",
            "entry_type": "error",
            "fields_schema": {
                "title": {"type": "string", "required": True},
                "content": {"type": "string", "required": True},
                "tags": {"type": "array", "default": ["error"]},
                "importance": {"type": "integer", "default": 4},
            },
        },
        {
            "name": "convention",
            "description": "Project convention or standard",
            "entry_type": "convention",
            "fields_schema": {
                "title": {"type": "string", "required": True},
                "content": {"type": "string", "required": True},
                "tags": {"type": "array", "default": ["convention"]},
                "importance": {"type": "integer", "default": 2},
            },
        },
        {
            "name": "memory",
            "description": "High-value synthesized memory",
            "entry_type": "memory",
            "fields_schema": {
                "title": {"type": "string", "required": True},
                "content": {"type": "string", "required": True},
                "tags": {"type": "array", "default": ["memory"]},
                "importance": {"type": "integer", "default": 3},
            },
        },
    ]

    for tmpl in default_templates:
        create_template(
            tmpl["name"],
            tmpl["description"],
            tmpl["entry_type"],
            tmpl["fields_schema"],
        )
