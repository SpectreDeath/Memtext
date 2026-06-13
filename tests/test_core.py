import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memtext.artifacts import (
    post_llm_artifact_hook,
    read_scratchpad,
    save_scratchpad_artifact,
    write_scratchpad,
)
from memtext.core import (
    add_log,
    add_skill,
    compile_context,
    deprecate_entry,
    distill_logs,
    get_context_dir,
    init_context,
    migrate_to_db,
    query_context,
    save_context,
    view_skill,
)
from memtext.db import query_entries


@pytest.fixture
def clean_ctx(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_context()
    return get_context_dir()


def test_init_context(clean_ctx):
    assert clean_ctx.exists()
    assert (clean_ctx / "identity.md").exists()
    assert (clean_ctx / "decisions.md").exists()
    assert (clean_ctx / "session-logs").is_dir()
    assert (clean_ctx / "artifacts").is_dir()
    assert (clean_ctx / ".gitignore").read_text() == "# Memtext context\n*\n!.gitignore\n"


def test_scratchpad_artifact_workflow(clean_ctx):
    assert write_scratchpad("Draft decision", append=False) == "Scratchpad updated."
    assert read_scratchpad() == "Draft decision"

    result = save_scratchpad_artifact("Architecture Draft", scope="design")
    assert result.startswith("Saved scratchpad state as memory artifact:")

    artifacts = list((clean_ctx / "artifacts").glob("artifact_*_architecture_draft.md"))
    assert len(artifacts) == 1
    content = artifacts[0].read_text()
    assert "type: memory_artifact" in content
    assert "scope: design" in content
    assert "Draft decision" in content
    assert read_scratchpad() == "Scratchpad is empty."


def test_post_llm_artifact_hook(clean_ctx):
    write_scratchpad("Existing draft", append=False)
    response = post_llm_artifact_hook(
        'Before <artifact name="Gephi Rules" scope="visualization">Use ForceAtlas2</artifact> After'
    )

    assert "[System Hook: Saved inline directive as memory artifact:" in response
    assert "Use ForceAtlas2" not in response
    assert read_scratchpad() == "Existing draft"
    assert (clean_ctx / "artifacts").exists()


def test_post_llm_artifact_hook_single_quoted(clean_ctx):
    response = post_llm_artifact_hook(
        "<artifact name='Single Quoted' scope='cli'>Single quoted content</artifact>"
    )

    assert "Single quoted content" not in response
    assert "[System Hook: Saved inline directive as memory artifact:" in response


def test_artifact_filename_collision_loop(clean_ctx, monkeypatch):
    class FrozenDatetime:
        @classmethod
        def now(cls):
            return datetime(2026, 6, 13, 12, 0, 0)

    monkeypatch.setattr("memtext.artifacts.datetime", FrozenDatetime)
    artifacts_dir = clean_ctx / "artifacts"
    (artifacts_dir / "artifact_20260613_120000_duplicate.md").write_text("existing")

    write_scratchpad("replacement", append=False)
    result = save_scratchpad_artifact("Duplicate")

    assert "artifact_20260613_120000_duplicate_1.md" in result
    assert (artifacts_dir / "artifact_20260613_120000_duplicate.md").read_text() == "existing"


def test_save_context(clean_ctx):
    save_context("Decision data", tags=["test"])
    content = (clean_ctx / "decisions.md").read_text()
    assert "Decision data" in content
    assert "[test]" in content


def test_native_query_context(clean_ctx):
    (clean_ctx / "test.md").write_text("Unique keyword exists here")
    results = query_context("Unique keyword")
    assert len(results) == 1
    assert results[0]["file"] == "test.md"
    assert "Unique keyword" in results[0]["content"]


def test_add_log(clean_ctx):
    add_log("Session data", session="test-session")
    log_files = list((clean_ctx / "session-logs").glob("*.md"))
    assert len(log_files) == 1
    content = log_files[0].read_text()
    assert "### test-session" in content
    assert "Session data" in content


def test_migrate_to_db(clean_ctx):
    save_context("Architecture decision 1")
    add_log("Epic log entry", session="S1")
    (clean_ctx / "identity.md").write_text("# Project Identity\nStack: Python")

    count = migrate_to_db()
    assert count >= 3  # Decision, Log section, Identity

    # Verify in DB
    results = query_entries(search_text="Architecture")
    assert len(results) > 0
    assert results[0]["entry_type"] == "decision"

    results = query_entries(search_text="Epic")
    assert len(results) > 0
    assert results[0]["entry_type"] == "note"

    results = query_entries(search_text="Identity")
    assert len(results) > 0
    assert results[0]["entry_type"] == "convention"


def test_add_skill(clean_ctx):
    idx = add_skill("run-linting", "Runs Ruff formatting and import checks")
    assert idx == 0
    assert (clean_ctx / "skills" / "run-linting.md").exists()
    assert (clean_ctx / "skills.md").exists()
    skills_content = (clean_ctx / "skills.md").read_text()
    assert "run-linting" in skills_content


def test_view_skill(clean_ctx):
    add_skill("deploy-staging", "Deploys to staging environment")
    content = view_skill("deploy-staging")
    assert content is not None
    assert "deploy-staging" in content
    assert "Description" in content


def test_view_skill_not_found(clean_ctx):
    content = view_skill("nonexistent-skill")
    assert content is None


def test_distill_logs(clean_ctx):
    add_log("Epic session log", session="S1")
    add_log("@memory: Fixed the auth bug with JWT refresh", session="S2")
    count = distill_logs()
    assert count >= 0


def test_compile_context(clean_ctx):
    output = compile_context("init")
    assert "Project Identity" in output
    assert "Architecture Decisions" in output


def test_deprecate_entry(clean_ctx):
    (clean_ctx / "test-decision.md").write_text("# Test Decision\nSome content")
    success = deprecate_entry("entry", "test-decision", "new-decision")
    assert success is True
    content = (clean_ctx / "test-decision.md").read_text()
    assert "status: deprecated" in content
    assert "superseded_by: new-decision" in content


def test_update_entry(clean_ctx):
    from memtext.db import add_entry, get_entry

    entry_id = add_entry("Original Title", "Original content", importance=1)
    assert entry_id > 0

    from memtext.repositories.database import EntryManager
    em = EntryManager()
    success = em.update(entry_id, title="Updated Title", importance=5)
    assert success is True

    entry = get_entry(entry_id)
    assert entry["title"] == "Updated Title"
    assert entry["importance"] == 5


def test_update_entry_cli(clean_ctx, capsys):
    from memtext.db import add_entry

    entry_id = add_entry("CLI Test", "Original content")

    import sys
    sys.argv = ["memtext", "update", str(entry_id), "--title", "CLI Updated"]
    from memtext.cli import main
    main()

    from memtext.db import get_entry
    entry = get_entry(entry_id)
    assert entry["title"] == "CLI Updated"
