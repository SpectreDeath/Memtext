import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memtext.core import (
    init_context, 
    get_context_dir, 
    add_log, 
    synthesize_memories,
    SYNTHESIS_PROMPT
)
from memtext.db import init_db, query_entries


@pytest.fixture
def clean_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_context()
    init_db()
    return get_context_dir()


def test_heuristic_synthesis(clean_env):
    # Add a log entry with a @memory marker
    add_log("Working on the project.\n@memory: Connection string should use port 5432.\nMore data.")
    
    count = synthesize_memories(recent_only=False)
    assert count == 1
    
    results = query_entries(entry_type="memory")
    assert len(results) == 1
    assert "port 5432" in results[0]["content"]
    assert results[0]["title"].startswith("Auto-Memory")


def test_manual_text_synthesis(clean_env):
    text = "Core Rule: Never use global variables (@tags: safety, clean-code)"
    count = synthesize_memories(source_text=text)
    assert count > 0 # Returns the result of add_entry which is id or -1
    
    results = query_entries(entry_type="memory")
    assert len(results) == 1
    assert results[0]["title"] == "Core Rule"
    assert "Never use global variables" in results[0]["content"]
    assert "safety" in results[0]["tags"]


def test_synthesis_prompt_exists():
    assert "Analyze" in SYNTHESIS_PROMPT
    assert "{text}" in SYNTHESIS_PROMPT
