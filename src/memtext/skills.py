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
from memtext.core import synthesize_memories, SYNTHESIS_PROMPT
from memtext.memory_logic import (
    DecisionExtractor,
    ContextOffloader,
    MemorySynthesizer,
    check_prolog_available,
)
from memtext.prolog_memory import (
    query_memory,
    classify_memory,
    preserve_memory,
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


def context_offloader(action: dict) -> dict:
    """Prolog-based context offloading and memory extraction."""
    action_type = action.get("action", "extract")

    if action_type == "check_prolog":
        return {"status": "success", "available": check_prolog_available()}

    elif action_type == "extract":
        text = action.get("text", "")
        extractor = DecisionExtractor()
        decisions = extractor.extract_decisions(text)
        conventions = extractor.extract_conventions(text)
        patterns = extractor.extract_patterns(text)
        constraints = extractor.extract_constraints(text)

        return {
            "status": "success",
            "extracted": {
                "decisions": decisions,
                "conventions": conventions,
                "patterns": patterns,
                "constraints": constraints,
            },
        }

    elif action_type == "rank":
        entries = action.get("entries", [])
        offloader = ContextOffloader()
        ranked = offloader.rank_entries(entries)
        return {"status": "success", "ranked": ranked}

    elif action_type == "select":
        entries = action.get("entries", [])
        max_tokens = action.get("max_tokens")
        offloader = ContextOffloader()
        selected = offloader.select_for_preservation(entries, max_tokens)
        return {"status": "success", "selected": selected}

    elif action_type == "synthesize":
        context_text = action.get("text", "")
        synthesizer = MemorySynthesizer()
        memories = synthesizer.synthesize(context_text)
        summary = synthesizer.generate_summary(memories)

        if action.get("save", False):
            count = 0
            for mem in memories:
                add_entry(
                    mem.get("title"),
                    mem.get("content"),
                    mem.get("entry_type"),
                    mem.get("tags"),
                    importance=mem.get("importance", 1),
                )
                count += 1
            return {"status": "success", "saved": count, "summary": summary}

        return {"status": "success", "memories": memories, "summary": summary}

    elif action_type == "dependencies":
        entries = action.get("entries", [])
        delete_ids = action.get("delete_ids", [])

        if not entries:
            return {"status": "error", "message": "entries required"}

        offloader = ContextOffloader()

        if delete_ids:
            cascade = offloader.get_cascade_deletion_order(entries, delete_ids)
            return {"status": "success", "cascade_deletion": cascade}

        deps = offloader.identify_dependencies(entries)
        return {"status": "success", "dependencies": deps}

    return {"status": "error", "message": "Unknown action"}


def prolog_memory_skill(action: dict) -> dict:
    """Prolog-based memory classification and preservation.

    Actions:
        - query: Query Prolog engine (e.g., "important(X)")
        - classify: Classify an entry dict
        - preserve: Select entries to preserve
    """
    action_type = action.get("action", "query")

    if action_type == "query":
        goal = action.get("goal", "important(X)")
        results = query_memory(goal)
        return {"status": "success", "results": results}

    elif action_type == "classify":
        entry = action.get("entry", {})
        result = classify_memory(entry)
        return {"status": "success", "classification": result}

    elif action_type == "preserve":
        entries = action.get("entries", [])
        max_count = action.get("max_count", 20)
        preserved = preserve_memory(entries, max_count)
        return {"status": "success", "preserved": preserved}

    return {"status": "error", "message": "Unknown action"}
