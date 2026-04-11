import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memtext.skills import (
    context_manager,
    context_retriever,
    context_pruner,
    project_manager
)
from memtext.db import init_db


@pytest.fixture
def clean_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()
    monkeypatch.setattr("memtext.db.PROJECT_REGISTRY", tmp_path / "projects.db")
    return tmp_path


def test_context_manager_add(clean_env):
    action = {
        "action": "add",
        "title": "Skill Note",
        "content": "Added via skill",
        "type": "note",
        "importance": 3
    }
    result = context_manager(action)
    assert result["status"] == "success"
    assert "entry_id" in result


def test_context_retriever(clean_env):
    context_manager({
        "action": "add", 
        "title": "Searchable", 
        "content": "Find me"
    })
    
    query = {"search": "Searchable"}
    result = context_retriever(query)
    assert result["status"] == "success"
    assert len(result["results"]) == 1
    assert result["results"][0]["title"] == "Searchable"


def test_project_manager_list(clean_env):
    query = {"action": "list"}
    result = project_manager(query)
    assert result["status"] == "success"
    assert "projects" in result


def test_context_pruner(clean_env):
    # This might be tricky to test without mocking time or manually inserting old dates
    # For now, just ensure it runs without error
    query = {"days": 0}
    result = context_pruner(query)
    assert result["status"] == "success"
    assert "stale_entries" in result
