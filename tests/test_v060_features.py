"""Tests for Memtext v0.6.0 features."""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memtext.db import (
    init_db,
    get_db_path,
    add_entry,
    get_entry,
    add_reminder,
    get_all_reminders,
    complete_reminder,
    create_template,
    get_template,
    list_templates,
    record_version_change,
    get_entry_history,
    add_webhook,
    list_webhooks,
    remove_webhook,
    create_backup,
    list_backups,
)


@pytest.fixture
def clean_db(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()
    return get_db_path()


# Reminders
def test_add_reminder(clean_db):
    entry_id = add_entry("Test Entry", "Content", entry_type="note")
    reminder_id = add_reminder(entry_id, "2026-06-01 10:00", "Review this")
    assert reminder_id > 0
    reminders = get_all_reminders(entry_id)
    assert len(reminders) == 1


def test_complete_reminder(clean_db):
    entry_id = add_entry("Entry to complete", "Content")
    reminder_id = add_reminder(entry_id, "2026-06-01 10:00", "Test")
    success = complete_reminder(reminder_id)
    assert success is True


# Templates
def test_create_template(clean_db):
    template_id = create_template(
        "custom-decision", "Custom template", "decision", {"title": {"type": "string"}}
    )
    assert template_id > 0


def test_get_template(clean_db):
    create_template("test-template", "Test desc", "note", {"title": {"type": "string"}})
    template = get_template("test-template")
    assert template is not None


def test_list_templates(clean_db):
    templates = list_templates()
    assert len(templates) >= 5


# Version History
def test_record_version_change(clean_db):
    entry_id = add_entry("Version Test", "Original content")
    success = record_version_change(entry_id, "content", "Original", "New")
    assert success is True
    history = get_entry_history(entry_id)
    assert len(history) == 1


# Webhooks
def test_add_webhook(clean_db):
    webhook_id = add_webhook("https://example.com/hook", "create")
    assert webhook_id > 0


def test_list_webhooks(clean_db):
    add_webhook("https://example.com/hook1", "create")
    webhooks = list_webhooks()
    assert len(webhooks) >= 1


def test_remove_webhook(clean_db):
    webhook_id = add_webhook("https://example.com/temp", "delete")
    success = remove_webhook(webhook_id)
    assert success is True


# Backups
def test_create_backup(clean_db):
    add_entry("Backup Test", "Content")
    backup_id = create_backup("manual")
    assert backup_id > 0


def test_list_backups(clean_db):
    create_backup("manual")
    backups = list_backups()
    assert len(backups) >= 1


# Tags Hierarchy
def test_entry_with_parent_tag(clean_db):
    entry_id = add_entry(
        "Postgres Decision",
        "Database content",
        entry_type="decision",
        parent_tag="database",
    )
    entry = get_entry(entry_id)
    assert entry["parent_tag"] == "database"
