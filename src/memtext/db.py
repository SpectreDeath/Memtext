"""Database operations for memtext.

This module provides an abstraction layer over SQLite.
All database operations go through repository classes defined in repositories/.
"""

from .repositories.backups import BackupService
from .repositories.database import EntryManager, get_connection
from .repositories.database import get_db_path as _local_get_db_path
from .repositories.projects import ProjectRegistry
from .repositories.reminders import ReminderService
from .repositories.templates import TemplateRegistry
from .repositories.webhooks import WebhookService

# Use local get_db_path for project context entries
get_db_path = _local_get_db_path

PROJECT_REGISTRY = None


def get_db_version() -> int:
    """Get current schema version for migrations."""
    from .repositories.migrations import MigrationManager

    return MigrationManager().get_current_version()


def run_migrations():
    """Run all pending migrations."""
    from .repositories.migrations import MigrationManager

    MigrationManager().apply(8, "Complete migration suite")


def record_version_change(entry_id: int, field_name: str, old_value: str, new_value: str) -> bool:
    """Record a version change in the version_history table."""
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


def init_db():
    from .core import init_context

    return init_context()


def add_entry(title, content="", entry_type="note", tags=None, parent_tag=None, importance=1):
    """Create a new entry. Backward compatible signature."""
    if not content:
        content = title
    em = EntryManager()
    return em.add(title, content, entry_type, tags or [], [], importance, parent_tag)


def get_entry(entry_id):
    em = EntryManager()
    return em.get(entry_id)


def update_entry(entry_id, **kwargs):
    em = EntryManager()
    return em.update(entry_id, **kwargs)


def delete_entry(entry_id):
    em = EntryManager()
    return em.delete(entry_id)


def list_entries(entry_type=None, limit=100, parent_tag=None):
    em = EntryManager()
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
    em = EntryManager()
    return em.search(search_text or "", entry_type, limit)


def add_shared_entry(title, content, entry_type, tags=None, importance=1, project_id=None):
    em = EntryManager()
    return em.add(title, content, entry_type, tags or [], [], importance, None)


def get_shared_entries(project_id):
    em = EntryManager()
    return em.list(project_id=project_id)


def make_shared(entry_id, project_id):
    em = EntryManager()
    return em.update(entry_id, project_id=project_id)


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
    em = EntryManager()
    return em.exists(title, entry_type)


def get_entry_history(entry_id):
    em = EntryManager()
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
