"""Database operations for memtext.

This module provides an abstraction layer over SQLite or PostgreSQL.
All database operations go through repository classes defined in repositories/.
"""

from __future__ import annotations

import os
from pathlib import Path

# Try to import PostgreSQL adapter
try:
    from .repositories.postgres import PostgresEntryManager, is_postgres_enabled
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    PostgresEntryManager = None  # type: ignore
    is_postgres_enabled = lambda: False  # type: ignore

from .repositories.database import EntryManager as SQLiteEntryManager
from .repositories.backups import BackupService
from .repositories.projects import ProjectRegistry
from .repositories.reminders import ReminderService
from .repositories.templates import TemplateRegistry
from .repositories.webhooks import WebhookService

# Use local get_db_path for project context entries (for SQLite fallback)
from .repositories.database import get_db_path as _local_get_db_path
from .repositories.migrations import MigrationManager

# Use local get_db_path for project context entries
get_db_path = _local_get_db_path

PROJECT_REGISTRY = None


def get_entry_manager():
    """Get the appropriate entry manager based on configuration."""
    if is_postgres_enabled():
        return PostgresEntryManager()
    else:
        return SQLiteEntryManager()


def get_db_version() -> int:
    """Get current schema version for migrations."""
    # For PostgreSQL, we'd need to query the schema_version table
    # For now, fallback to SQLite implementation
    return MigrationManager().get_current_version()


def run_migrations():
    """Run all pending migrations."""
    # For PostgreSQL, we'd need to run PostgreSQL-specific migrations
    # For now, fallback to SQLite implementation
    MigrationManager().apply(8, "Complete migration suite")


def record_version_change(entry_id: int, field_name: str, old_value: str, new_value: str) -> bool:
    """Record a version change in the version_history table."""
    # For PostgreSQL, we'd need to use the PostgreSQL connection
    # For now, fallback to SQLite implementation
    from .repositories.migrations import MigrationManager

    mm = MigrationManager()
    mm._ensure_meta_table()
    with get_connection(mm.db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO version_history (entry_id, field_name, old_value, new_value) VALUES (?, ?, ?, ?)",
            (entry_id, field_name, old_value, new_value),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_connection(db_path: Optional[Path] = None):
    """Get a database connection (SQLite only for now)."""
    db_path = db_path or get_db_path()
    import sqlite3
    return sqlite3.connect(db_path)


def init_db():
    """Initialize the database (SQLite or PostgreSQL)."""
    # First initialize context directory structure
    from .core import init_context
    init_context()
    
    # Then initialize the database
    # Get entry manager to trigger database initialization
    entry_manager = get_entry_manager()
    
    # For SQLite, the constructor already initializes the DB
    # For PostgreSQL, we need to trigger initialization
    import asyncio
    if hasattr(entry_manager, '_init_db'):
        if asyncio.iscoroutinefunction(entry_manager._init_db):
            asyncio.run(entry_manager._init_db())
        else:
            entry_manager._init_db()
    
    # Return the database path for backward compatibility with tests
    from .repositories.database import get_db_path
    return get_db_path()


def add_entry(title, content="", entry_type="note", tags=None, parent_tag=None, importance=1):
    """Create a new entry. Backward compatible signature."""
    import asyncio
    
    if not content:
        content = title
    
    entry_manager = get_entry_manager()
    
    if hasattr(entry_manager, 'add'):
        # Check if it's an async method (PostgreSQL)
        if asyncio.iscoroutinefunction(entry_manager.add):
            # Run the async method
            return asyncio.run(entry_manager.add(
                title, content, entry_type, tags or [], [], importance, parent_tag
            ))
        else:
            # Synchronous method (SQLite)
            return entry_manager.add(
                title, content, entry_type, tags or [], [], importance, parent_tag
            )
    else:
        # Fallback to SQLite
        em = SQLiteEntryManager()
        return em.add(title, content, entry_type, tags or [], [], importance, parent_tag)


def get_entry(entry_id):
    """Retrieve a single entry by ID."""
    import asyncio
    
    entry_manager = get_entry_manager()
    
    if hasattr(entry_manager, 'get'):
        # Check if it's an async method (PostgreSQL)
        if asyncio.iscoroutinefunction(entry_manager.get):
            # Run the async method
            return asyncio.run(entry_manager.get(entry_id))
        else:
            # Synchronous method (SQLite)
            return entry_manager.get(entry_id)
    else:
        # Fallback to SQLite
        em = SQLiteEntryManager()
        return em.get(entry_id)


def update_entry(entry_id, **kwargs):
    """Update an entry."""
    import asyncio
    
    entry_manager = get_entry_manager()
    
    if hasattr(entry_manager, 'update'):
        # Check if it's an async method (PostgreSQL)
        if asyncio.iscoroutinefunction(entry_manager.update):
            # Run the async method
            return asyncio.run(entry_manager.update(entry_id, **kwargs))
        else:
            # Synchronous method (SQLite)
            return entry_manager.update(entry_id, **kwargs)
    else:
        # Fallback to SQLite
        em = SQLiteEntryManager()
        return em.update(entry_id, **kwargs)


def delete_entry(entry_id):
    """Remove an entry."""
    import asyncio
    
    entry_manager = get_entry_manager()
    
    if hasattr(entry_manager, 'delete'):
        # Check if it's an async method (PostgreSQL)
        if asyncio.iscoroutinefunction(entry_manager.delete):
            # Run the async method
            return asyncio.run(entry_manager.delete(entry_id))
        else:
            # Synchronous method (SQLite)
            return entry_manager.delete(entry_id)
    else:
        # Fallback to SQLite
        em = SQLiteEntryManager()
        return em.delete(entry_id)


def list_entries(entry_type=None, limit=100, parent_tag=None):
    """List entries, optionally filtered."""
    import asyncio
    
    entry_manager = get_entry_manager()
    
    if hasattr(entry_manager, 'list'):
        # Check if it's an async method (PostgreSQL)
        if asyncio.iscoroutinefunction(entry_manager.list):
            # Run the async method
            return asyncio.run(entry_manager.list(entry_type, limit, parent_tag))
        else:
            # Synchronous method (SQLite)
            return entry_manager.list(entry_type, limit, parent_tag)
    else:
        # Fallback to SQLite
        em = SQLiteEntryManager()
        return em.list(entry_type, limit, parent_tag)


def query_entries(
    search_text=None,
    entry_type=None,
    min_importance=0,
    tags=None,
    parent_tag=None,
    limit=20,
    use_fts=True,
):
    """Search entries."""
    import asyncio
    
    entry_manager = get_entry_manager()
    
    if hasattr(entry_manager, 'search'):
        # Check if it's an async method (PostgreSQL)
        if asyncio.iscoroutinefunction(entry_manager.search):
            # Run the async method
            return asyncio.run(entry_manager.search(
                search_text or "", entry_type, limit
            ))
        else:
            # Synchronous method (SQLite)
            return entry_manager.search(
                search_text or "", entry_type, limit
            )
    else:
        # Fallback to SQLite
        em = SQLiteEntryManager()
        return em.search(
            search_text or "", entry_type, limit
        )


def add_shared_entry(title, content, entry_type, tags=None, importance=1, project_id=None):
    """Create a new shared entry."""
    import asyncio
    
    entry_manager = get_entry_manager()
    
    if hasattr(entry_manager, 'add'):  # Simplified - would need a specific method
        # Check if it's an async method (PostgreSQL)
        if asyncio.iscoroutinefunction(entry_manager.add):
            # Run the async method
            return asyncio.run(entry_manager.add(
                title, content, entry_type, tags or [], [], importance, None
            ))
        else:
            # Synchronous method (SQLite)
            return entry_manager.add(
                title, content, entry_type, tags or [], [], importance, None
            )
    else:
        # Fallback to SQLite
        em = SQLiteEntryManager()
        return em.add(title, content, entry_type, tags or [], [], importance, None)


def get_shared_entries(project_id):
    """Get shared entries for a project."""
    import asyncio
    
    entry_manager = get_entry_manager()
    
    # This would need a specific method in the PostgreSQL adapter
    # For now, fall back to SQLite
    em = SQLiteEntryManager()
    return em.list(project_id=project_id)


def make_shared(entry_id, project_id):
    """Mark an entry as shared."""
    import asyncio
    
    entry_manager = get_entry_manager()
    
    if hasattr(entry_manager, 'update'):
        # Check if it's an async method (PostgreSQL)
        if asyncio.iscoroutinefunction(entry_manager.update):
            # Run the async method
            return asyncio.run(entry_manager.update(entry_id, is_shared=True))
        else:
            # Synchronous method (SQLite)
            return entry_manager.update(entry_id, is_shared=True)
    else:
        # Fallback to SQLite
        em = SQLiteEntryManager()
        return em.update(entry_id, is_shared=True)


# Additional functions for advanced PostgreSQL features

def hybrid_search(
    query_text: str,
    query_embedding: List[float],
    text_weight: float = 0.3,
    vector_weight: float = 0.7,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Perform hybrid search using pgvector and pg_trgm (PostgreSQL only)."""
    import asyncio
    
    if not is_postgres_enabled():
        # Fallback to regular search for SQLite
        return query_entries(search_text=query_text, limit=limit)
    
    entry_manager = get_entry_manager()
    
    if hasattr(entry_manager, 'hybrid_search'):
        # Check if it's an async method (PostgreSQL)
        if asyncio.iscoroutinefunction(entry_manager.hybrid_search):
            # Run the async method
            return asyncio.run(entry_manager.hybrid_search(
                query_text, query_embedding, text_weight, vector_weight, limit
            ))
        else:
            # Synchronous method (shouldn't happen for this advanced feature)
            return entry_manager.hybrid_search(
                query_text, query_embedding, text_weight, vector_weight, limit
            )
    else:
        # Fallback to regular search
        return query_entries(search_text=query_text, limit=limit)


def add_session_log(
    project_id: str,
    log_date: str,
    content: str,
    embedding: Optional[List[float]] = None,
    trust_score: float = 1.0
) -> str:
    """Add a session log entry (PostgreSQL only)."""
    import asyncio
    
    if not is_postgres_enabled():
        # For SQLite, fall back to regular logging
        from .core import add_log
        add_log(content)
        return "sqlite-fallback"
    
    entry_manager = get_entry_manager()
    
    if hasattr(entry_manager, 'add_session_log'):
        # Check if it's an async method (PostgreSQL)
        if asyncio.iscoroutinefunction(entry_manager.add_session_log):
            # Run the async method
            return asyncio.run(entry_manager.add_session_log(
                project_id, log_date, content, embedding, trust_score
            ))
        else:
            # Synchronous method (shouldn't happen for this advanced feature)
            return entry_manager.add_session_log(
                project_id, log_date, content, embedding, trust_score
            )
    else:
        # Fallback to SQLite logging
        from .core import add_log
        add_log(content)
        return "sqlite-fallback"


def get_session_logs(
    project_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Get session logs with time-series filtering (PostgreSQL only)."""
    import asyncio
    
    if not is_postgres_enabled():
        # For SQLite, return empty list or fallback
        return []
    
    entry_manager = get_entry_manager()
    
    if hasattr(entry_manager, 'get_session_logs'):
        # Check if it's an async method (PostgreSQL)
        if asyncio.iscoroutinefunction(entry_manager.get_session_logs):
            # Run the async method
            return asyncio.run(entry_manager.get_session_logs(
                project_id, start_date, end_date, limit
            ))
        else:
            # Synchronous method (shouldn't happen for this advanced feature)
            return entry_manager.get_session_logs(
                project_id, start_date, end_date, limit
            )
    else:
        # Fallback to empty list
        return []


# Legacy functions for backward compatibility
def create_template(name, description, fields):
    tr = TemplateRegistry()
    return tr.create(name, description, "note", fields or {})


def get_template(name):
    tr = TemplateRegistry()
    return tr.get(name)


def list_templates():
    tr = TemplateRegistry()
    return tr.list()


def create_backup(backup_type="manual"):
    bs = BackupService()
    return bs.create(backup_type)


def list_backups():
    bs = BackupService()
    return bs.list()


def restore_backup(backup_id, backup_path=None):
    bs = BackupService()
    return bs.restore(backup_id, backup_path)


def add_reminder(entry_id, remind_at, message=""):
    rs = ReminderService()
    return rs.add(entry_id, remind_at, message)


def get_pending_reminders():
    rs = ReminderService()
    return rs.get_pending()


def get_all_reminders(entry_id):
    rs = ReminderService()
    return rs.get_all(entry_id)


def complete_reminder(reminder_id):
    rs = ReminderService()
    return rs.complete(reminder_id)


def add_webhook(url, event, secret=None):
    ws = WebhookService()
    return ws.register(url, event, secret)


def list_webhooks(active_only=True):
    ws = WebhookService()
    return ws.list(active_only)


def remove_webhook(webhook_id):
    ws = WebhookService()
    return ws.remove(webhook_id)


def trigger_webhook(event_type, entry_data):
    ws = WebhookService()
    ws.trigger(event_type, entry_data)


def entry_exists(title, entry_type="note"):
    em = SQLiteEntryManager()  # TODO: Make this work with PostgreSQL too
    return em.exists(title, entry_type)


def get_entry_history(entry_id):
    em = SQLiteEntryManager()  # TODO: Make this work with PostgreSQL too
    return em.get_entry_history(entry_id)


def register_project(path, name=None):
    pr = ProjectRegistry()
    return pr.register(path, name)


def list_projects():
    pr = ProjectRegistry()
    return pr.list()


def scan_for_projects(root_path=None):
    pr = ProjectRegistry()
    return pr.scan(root_path)
