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


# Add connection helper
def get_connection(db_path=None):
    import sqlite3
    db_path = db_path or get_db_path()
    return sqlite3.connect(db_path)



entry_exists = lambda *a, **kw: EntryManager().exists(*a, **kw)

get_entry_history = lambda *a, **kw: EntryManager().get_entry_history(*a, **kw)

# Project registry exports
register_project = lambda *a, **kw: ProjectRegistry().register(*a, **kw)
list_projects = lambda *a, **kw: ProjectRegistry().list(*a, **kw)
scan_for_projects = lambda *a, **kw: ProjectRegistry().scan(*a, **kw)

# Backward compatibility exports for tests and external consumers
def init_db():
    from .core import init_context
    return init_context()
def run_migrations():
    """Run all pending migrations."""
    from .repositories.migrations import MigrationManager
    MigrationManager().apply(8, "Complete migration suite")

def record_version_change(entry_id: int, field_name: str, old_value: str, new_value: str) -> bool:
    """Record a version change in the version_history table."""
    from .repositories.migrations import MigrationManager
    mm = MigrationManager()
    mm._ensure_meta_table() if hasattr(mm, '_ensure_meta_table') else None
    with get_connection(mm.db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO version_history (entry_id, field_name, old_value, new_value) VALUES (?, ?, ?, ?)",
            (entry_id, field_name, old_value, new_value),
        )
        conn.commit()
        return cursor.rowcount > 0

# Repository function exports
add_entry = lambda *a, **kw: EntryManager().add(*a, **kw)
get_entry = lambda *a, **kw: EntryManager().get(*a, **kw)
update_entry = lambda *a, **kw: EntryManager().update(*a, **kw)
delete_entry = lambda *a, **kw: EntryManager().delete(*a, **kw)
list_entries = lambda *a, **kw: EntryManager().list(*a, **kw)
query_entries = lambda *a, **kw: EntryManager().search(*a, **kw)
add_shared_entry = lambda *a, **kw: EntryManager().add(*a, **kw)
get_shared_entries = lambda *a, **kw: EntryManager().list(*a, **kw)
make_shared = lambda *a, **kw: EntryManager().update(*a, **kw)
create_template = lambda *a, **kw: TemplateRegistry().create(*a, **kw)
get_template = lambda *a, **kw: TemplateRegistry().get(*a, **kw)
list_templates = lambda *a, **kw: TemplateRegistry().list(*a, **kw)
create_backup = lambda *a, **kw: BackupService().create(*a, **kw)
list_backups = lambda *a, **kw: BackupService().list(*a, **kw)
restore_backup = lambda *a, **kw: BackupService().restore(*a, **kw)
add_reminder = lambda *a, **kw: ReminderService().add(*a, **kw)
get_pending_reminders = lambda *a, **kw: ReminderService().get_pending(*a, **kw)
get_all_reminders = lambda *a, **kw: ReminderService().get_all(*a, **kw)
complete_reminder = lambda *a, **kw: ReminderService().complete(*a, **kw)
add_webhook = lambda *a, **kw: WebhookService().register(*a, **kw)
list_webhooks = lambda *a, **kw: WebhookService().list(*a, **kw)
remove_webhook = lambda *a, **kw: WebhookService().remove(*a, **kw)
trigger_webhook = trigger_webhook


# Add connection helper
def get_connection(db_path=None):
    import sqlite3
    db_path = db_path or get_db_path()
    return sqlite3.connect(db_path)


entry_exists = lambda *a, **kw: EntryManager().exists(*a, **kw)

get_entry_history = lambda *a, **kw: EntryManager().get_entry_history(*a, **kw)

# Project registry exports
register_project = lambda *a, **kw: ProjectRegistry().register(*a, **kw)
list_projects = lambda *a, **kw: ProjectRegistry().list(*a, **kw)
scan_for_projects = lambda *a, **kw: ProjectRegistry().scan(*a, **kw)

# Backward compatibility exports for tests and external consumers
def init_db():
    from .core import init_context
    return init_context()
def run_migrations():
    """Run all pending migrations."""
    from .repositories.migrations import MigrationManager
    MigrationManager().apply(8, "Complete migration suite")

def record_version_change(entry_id: int, field_name: str, old_value: str, new_value: str) -> bool:
    """Record a version change in the version_history table."""
    from .repositories.migrations import MigrationManager
    mm = MigrationManager()
    mm._ensure_meta_table() if hasattr(mm, '_ensure_meta_table') else None
    with get_connection(mm.db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO version_history (entry_id, field_name, old_value, new_value) VALUES (?, ?, ?, ?)",
            (entry_id, field_name, old_value, new_value),
        )
        conn.commit()
        return cursor.rowcount > 0

# Repository function exports
add_entry = lambda *a, **kw: EntryManager().add(*a, **kw)
get_entry = lambda *a, **kw: EntryManager().get(*a, **kw)
update_entry = lambda *a, **kw: EntryManager().update(*a, **kw)
delete_entry = lambda *a, **kw: EntryManager().delete(*a, **kw)
list_entries = lambda *a, **kw: EntryManager().list(*a, **kw)
query_entries = lambda *a, **kw: EntryManager().search(*a, **kw)
add_shared_entry = lambda *a, **kw: EntryManager().add(*a, **kw)
get_shared_entries = lambda *a, **kw: EntryManager().list(*a, **kw)
make_shared = lambda *a, **kw: EntryManager().update(*a, **kw)
create_template = lambda *a, **kw: TemplateRegistry().create(*a, **kw)
get_template = lambda *a, **kw: TemplateRegistry().get(*a, **kw)
list_templates = lambda *a, **kw: TemplateRegistry().list(*a, **kw)
create_backup = lambda *a, **kw: BackupService().create(*a, **kw)
list_backups = lambda *a, **kw: BackupService().list(*a, **kw)
restore_backup = lambda *a, **kw: BackupService().restore(*a, **kw)
add_reminder = lambda *a, **kw: ReminderService().add(*a, **kw)
get_pending_reminders = lambda *a, **kw: ReminderService().get_pending(*a, **kw)
get_all_reminders = lambda *a, **kw: ReminderService().get_all(*a, **kw)
complete_reminder = lambda *a, **kw: ReminderService().complete(*a, **kw)
add_webhook = lambda *a, **kw: WebhookService().register(*a, **kw)
list_webhooks = lambda *a, **kw: WebhookService().list(*a, **kw)
remove_webhook = lambda *a, **kw: WebhookService().remove(*a, **kw)
trigger_webhook = trigger_webhook
