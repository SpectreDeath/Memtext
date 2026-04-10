import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memtext.db import init_db, get_db_path


def test_init_db_creates_database(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = init_db()
    assert db_path.exists()
    assert db_path.name == "memtext.db"


def test_db_has_required_tables(tmp_path, monkeypatch):
    import sqlite3

    monkeypatch.chdir(tmp_path)
    init_db()
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    assert "context_entries" in tables
    assert "projects" in tables
