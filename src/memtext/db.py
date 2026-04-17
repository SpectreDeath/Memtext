"""Database operations for memtext.

This module provides an abstraction layer over SQLite.
All database operations go through repository classes defined in repositories/.
"""

from pathlib import Path

from .repositories.database import get_db_path


def get_db_path() -> Path:
    return get_db_path()


def get_db_version() -> int:
    """Get current schema version for migrations."""
    from .repositories.migrations import MigrationManager
    return MigrationManager().get_current_version()


def run_migrations():
    """Run database migrations for new features."""
    from .repositories.migrations import MigrationManager
    MigrationManager().apply(8, "Complete migration suite")


def init_db() -> Path:
    """Initialize database (used by migrate command)."""
    from .repositories.database import EntryManager
    em = EntryManager()
    return em.db_path


def add_entry(title, content, entry_type, tags=None, linked_files=None, importance=1,
              parent_tag=None):
    from .repositories.database import EntryManager
    em = EntryManager()
    return em.add(title, content, entry_type, tags or [], linked_files or [],
                  importance, parent_tag)


def get_entry(entry_id):
    from .repositories.database import EntryManager
    em = EntryManager()
    return em.get(entry_id)


def update_entry(entry_id, **kwargs):
    from .repositories.database import EntryManager
    em = EntryManager()
    return em.update(entry_id, **kwargs)


def delete_entry(entry_id):
    from .repositories.database import EntryManager
    em = EntryManager()
    return em.delete(entry_id)


def list_entries(entry_type=None, limit=100, parent_tag=None):
    from .repositories.database import EntryManager
    em = EntryManager()
    return em.list(entry_type, limit, parent_tag)


def query_entries(search_text, entry_type=None, min_importance=0, tags=None,
                  parent_tag=None, limit=20, use_fts=True):
    from .repositories.database import EntryManager
    em = EntryManager()
    if use_fts:
        return em.search(search_text, entry_type, limit)
    return em.list(entry_type, limit)


def add_shared_entry(title, content, entry_type, tags=None, importance=1,
                     project_id=None):
    from .repositories.database import EntryManager
    em = EntryManager()
    return em.add(title, content, entry_type, tags or [], [], importance,
                  parent_tag=None)


def get_shared_entries(project_id):
    from .repositories.database import EntryManager
    em = EntryManager()
    return em.list(project_id=project_id)


def make_shared(entry_id, project_id):
    # Shared entries tracked via project_id on entries table
    from .repositories.database import EntryManager
    em = EntryManager()
    return em.update(entry_id, project_id=project_id)


def create_template(name, description, fields):
    from .repositories.templates import TemplateRegistry
    tr = TemplateRegistry()
    return tr.create(name, description, "note", fields or {})


def get_template(name):
    from .repositories.templates import TemplateRegistry
    tr = TemplateRegistry()
    return tr.get(name)


def list_templates():
    from .repositories.templates import TemplateRegistry
    tr = TemplateRegistry()
    return tr.list()


def create_backup(backup_type="manual"):
    from .repositories.backups import BackupService
    bs = BackupService()
    return bs.create(backup_type)


def list_backups():
    from .repositories.backups import BackupService
    bs = BackupService()
    return bs.list()


def restore_backup(backup_id, backup_path=None):
    from .repositories.backups import BackupService
    bs = BackupService()
    return bs.restore(backup_id, backup_path)


def add_reminder(entry_id, remind_at, message=""):
    from .repositories.reminders import ReminderService
    rs = ReminderService()
    return rs.add(entry_id, remind_at, message)


def get_pending_reminders():
    from .repositories.reminders import ReminderService
    rs = ReminderService()
    return rs.get_pending()


def get_all_reminders(entry_id):
    from .repositories.reminders import ReminderService
    rs = ReminderService(entry_id=entry_id)
    return rs.get_all(entry_id)


def complete_reminder(reminder_id):
    from .repositories.reminders import ReminderService
    rs = ReminderService()
    return rs.complete(reminder_id)


def add_webhook(url, event, secret=None):
    from .repositories.webhooks import WebhookService
    ws = WebhookService()
    return ws.register(url, event, secret)


def list_webhooks(active_only=True):
    from .repositories.webhooks import WebhookService
    ws = WebhookService()
    return ws.list(active_only)


def remove_webhook(webhook_id):
    from .repositories.webhooks import WebhookService
    ws = WebhookService()
    return ws.remove(webhook_id)


def trigger_webhook(event_type, entry_data):
    from .repositories.webhooks import WebhookService
    ws = WebhookService()
    ws.trigger(event_type, entry_data)
