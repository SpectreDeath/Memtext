import pytest
import sys
from pathlib import Path
import sqlite3

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memtext.db import (
    init_db, 
    get_db_path, 
    add_entry, 
    get_entry, 
    update_entry, 
    delete_entry, 
    query_entries,
    register_project,
    list_projects,
    entry_exists
)


@pytest.fixture
def clean_db(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()
    return get_db_path()


def test_init_db_creates_database(clean_db):
    assert clean_db.exists()
    assert clean_db.name == "memtext.db"


def test_db_has_required_tables(clean_db):
    conn = sqlite3.connect(clean_db)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    assert "context_entries" in tables
    assert "projects" in tables
    assert "context_fts" in tables


def test_add_and_get_entry(clean_db):
    entry_id = add_entry("Test Title", "Test Content", tags=["tag1", "tag2"])
    assert entry_id > 0
    
    entry = get_entry(entry_id)
    assert entry["title"] == "Test Title"
    assert entry["content"] == "Test Content"
    assert entry["tags"] == "tag1,tag2"


def test_entry_exists(clean_db):
    add_entry("Unique Title", "Content", entry_type="decision")
    assert entry_exists("Unique Title", "decision") is True
    assert entry_exists("Unique Title", "note") is False
    assert entry_exists("Nonexistent") is False


def test_idempotent_add(clean_db):
    id1 = add_entry("Single Title", "Content")
    id2 = add_entry("Single Title", "Content")
    assert id1 > 0
    assert id2 == -1


def test_update_entry(clean_db):
    entry_id = add_entry("Old Title", "Old Content")
    success = update_entry(entry_id, title="New Title", importance=5)
    assert success is True
    
    entry = get_entry(entry_id)
    assert entry["title"] == "New Title"
    assert entry["importance"] == 5


def test_delete_entry(clean_db):
    entry_id = add_entry("To be deleted", "Content")
    assert delete_entry(entry_id) is True
    assert get_entry(entry_id) is None


def test_query_entries(clean_db):
    add_entry("Python logic", "Writing code", tags=["py"])
    add_entry("Java logic", "More code", tags=["java"])
    
    results = query_entries(search_text="logic")
    assert len(results) == 2
    
    results = query_entries(tags="py")
    assert len(results) == 1
    assert results[0]["title"] == "Python logic"


def test_project_registry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Monkeypatch the registry path to avoid polluting home config
    monkeypatch.setattr("memtext.db.PROJECT_REGISTRY", tmp_path / "projects.db")
    
    p_id = register_project(str(tmp_path), "TestProj")
    assert p_id > 0
    
    projects = list_projects()
    assert len(projects) == 1
    assert projects[0]["name"] == "TestProj"
    assert projects[0]["path"] == str(tmp_path)
