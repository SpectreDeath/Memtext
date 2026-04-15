"""Database operations for memtext."""

from pathlib import Path
import sqlite3


def get_db_path() -> Path:
    return Path.cwd() / ".context" / "memtext.db"


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
            source TEXT DEFAULT 'manual',
            linked_files TEXT,
            is_shared INTEGER DEFAULT 0,
            project_id INTEGER,
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


def update_fts(title: str, content: str, entry_type: str, tags: str):
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO context_fts (title, content, entry_type, tags) VALUES (?, ?, ?, ?)",
            (title, content, entry_type, tags or ""),
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
) -> int:
    if entry_exists(title, entry_type):
        return -1

    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO context_entries (title, content, entry_type, tags, linked_files, importance) VALUES (?, ?, ?, ?, ?, ?)",
            (
                title,
                content,
                entry_type,
                ",".join(tags or []),
                ",".join(linked_files or []),
                importance,
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
    fields = ", ".join(f"{k}=?" for k in kwargs.keys())
    values = list(kwargs.values()) + [entry_id]
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE context_entries SET {fields} WHERE id=?", values)
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


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
    limit: int = 10,
) -> list:
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

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

    query += f" ORDER BY importance DESC, last_accessed DESC LIMIT {limit}"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def list_entries(entry_type: str = None, limit: int = 10) -> list:
    return query_entries(entry_type=entry_type, limit=limit)


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
    root_path = root_path or str(Path.home())
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
