"""Agent skills for memtext context management."""

from memtext.db import (
    add_entry,
    get_entry,
    update_entry,
    delete_entry,
    query_entries,
    list_entries,
    register_project,
    list_projects,
    scan_for_projects,
)
from memtext.core import (
    synthesize_memories,
    SYNTHESIS_PROMPT
)


def context_manager(action: dict) -> dict:
    """Add, update, delete context entries."""
    action_type = action.get("action")

    if action_type == "add":
        entry_id = add_entry(
            action.get("title"),
            action.get("content"),
            action.get("type", "note"),
            action.get("tags"),
            action.get("linked_files"),
            action.get("importance", 1),
        )
        return {"status": "success", "entry_id": entry_id}

    elif action_type == "update":
        entry_id = action.get("entry_id")
        updated = update_entry(entry_id, **action.get("fields", {}))
        return {"status": "success" if updated else "not_found"}

    elif action_type == "delete":
        entry_id = action.get("entry_id")
        deleted = delete_entry(entry_id)
        return {"status": "success" if deleted else "not_found"}

    elif action_type == "get":
        entry = get_entry(action.get("entry_id"))
        return {"status": "success", "entry": entry}

    return {"status": "error", "message": "Unknown action"}


def context_retriever(query: dict) -> dict:
    """Query context entries."""
    if query.get("search"):
        results = query_entries(
            search_text=query.get("search"),
            entry_type=query.get("type"),
            min_importance=query.get("min_importance"),
            tags=query.get("tags"),
            limit=query.get("limit", 10),
        )
    else:
        results = list_entries(
            entry_type=query.get("type"), limit=query.get("limit", 10)
        )

    return {"status": "success", "results": results}


def context_pruner(query: dict) -> dict:
    """Find stale entries."""
    import datetime

    days = query.get("days", 30)
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()

    from memtext.db import get_db_path
    import sqlite3

    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM context_entries WHERE last_accessed < ? OR last_accessed IS NULL",
        (cutoff,),
    )
    rows = cursor.fetchall()
    conn.close()

    stale = [dict(row) for row in rows]
    return {"status": "success", "stale_entries": stale}


def project_manager(query: dict) -> dict:
    """Manage cross-project context."""
    action = query.get("action", "list")

    if action == "list":
        return {"status": "success", "projects": list_projects()}

    elif action == "register":
        project_id = register_project(query.get("path"), query.get("name"))
        return {"status": "success", "project_id": project_id}

    elif action == "scan":
        found = scan_for_projects(query.get("root_path"))
        for p in found:
            register_project(p)
        return {"status": "success", "found": found}

    return {"status": "error", "message": "Unknown action"}


def context_synthesizer(action: dict) -> dict:
    """Distill raw context into memories."""
    action_type = action.get("action", "synthesize")

    if action_type == "get_prompt":
        return {"status": "success", "prompt": SYNTHESIS_PROMPT}

    elif action_type == "synthesize":
        text = action.get("text")
        all_logs = action.get("all", False)
        count = synthesize_memories(source_text=text, recent_only=not all_logs)
        return {"status": "success", "new_memories": count}

    return {"status": "error", "message": "Unknown action"}
