"""Asynchronous memory reflection engine ("Dreams") for Memtext.

This module provides offline consolidation of session logs to extract long-term
behavioral patterns, architectural rules, and user preferences.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


REFLECTION_PROMPT = """You are an offline memory optimization engine for an AI development agent.
Review the following recent session logs. Do not write, debug, or refactor code.
Your sole task is memory synthesis and compression. Produce a clean, high-level markdown document detailing:

1. RECURRING PATTERNS & ANTI-PATTERNS: Document repetitive engineering mistakes, structural bugs, or successful workflows executed across multiple sessions.
2. IMPLICIT USER PREFERENCES: Identify behavioral preferences or strict constraints the user has demonstrated but not explicitly committed to identity.md.
3. CONTRADICTION RESOLUTION: Highlight conflicting information or outdated assumptions between past logs and current structures.

Format your response as clean, structured markdown with clear section headings.
"""

LOG_PAYLOAD_HEADER = """
RAW LOGS FOR ANALYSIS:
"""


def estimate_tokens(text: str) -> int:
    """Estimate token count. ~4 characters per token for English text."""
    return len(text) // 4


def get_recent_session_logs(limit: int = 20) -> List[Dict[str, Any]]:
    """Fetch recent unreflected session logs.
    
    For PostgreSQL: uses get_session_logs with time-series filtering.
    For SQLite: reads from .context/session-logs/ directory.
    """
    from .core import get_context_dir
    from .db import get_session_logs, is_postgres_enabled
    
    if is_postgres_enabled():
        import asyncio
        logs = asyncio.run(get_session_logs(limit=limit))
        return logs if logs else []
    else:
        ctx_dir = get_context_dir()
        logs_dir = ctx_dir / "session-logs"
        if not logs_dir.exists():
            return []
        
        log_files = sorted(logs_dir.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]
        logs = []
        for log_file in log_files:
            content = log_file.read_text()
            logs.append({
                "id": log_file.stem,
                "log_date": log_file.stem,
                "content": content,
                "created_at": datetime.fromtimestamp(log_file.stat().st_mtime).isoformat(),
            })
        return logs


def format_logs_for_reflection(logs: List[Dict[str, Any]]) -> str:
    """Format logs into a single payload for LLM analysis."""
    formatted = []
    for log in logs:
        date = log.get("log_date", log.get("id", "unknown"))
        content = log.get("content", "")
        formatted.append(f"Log ({date}):\n{content}")
    return "\n\n---\n\n".join(formatted)


def run_reflection_cycle(project_path: str = None, max_logs: int = 20, max_tokens: int = 4000) -> Dict[str, Any]:
    """
    Run an asynchronous-style 'dream' cycle on context files.
    
    Phase 1: Ingestion & Scoping - fetch recent unreflected session logs
    Phase 2: The Reflection Prompt - run LLM analysis
    Phase 3: Token Budgeting & Pruning - compress if needed
    
    Args:
        project_path: Target project directory (defaults to cwd)
        max_logs: Number of recent logs to analyze
        max_tokens: Token budget threshold for pruning
        
    Returns:
        Dict with status, message, and insights count
    """
    from .db import add_entry
    
    original_cwd = os.getcwd()
    try:
        if project_path:
            os.chdir(project_path)
        
        # Phase 1: Ingestion & Scoping
        recent_logs = get_recent_session_logs(limit=max_logs)
        if not recent_logs:
            return {"status": "not_found", "message": "No new session logs to reflect on.", "insights_count": 0}
        
        log_payload = format_logs_for_reflection(recent_logs)
        total_tokens = estimate_tokens(log_payload)
        
        # Phase 2: The Reflection Prompt - call LLM
        distilled_insights = _run_llm_reflection(log_payload)
        
        if not distilled_insights:
            return {"status": "error", "message": "LLM reflection failed or unavailable.", "insights_count": 0}
        
        # Phase 3: Save to database with agent-staging metadata
        meta = {
            "source_session_ids": [log.get("id") for log in recent_logs],
            "log_count": len(recent_logs),
        }
        entry_id = save_reflection_insight(distilled_insights, meta)
        
        # Also save as regular memory entry for query consistency
        if entry_id > 0:
            add_entry(
                title="Reflection Insights",
                content=distilled_insights,
                entry_type="memory",
                tags=["reflection", "dreams", "consolidation"],
                importance=3,
                trust_score=0.85,
                source="memtext-reflection-engine",
            )
        
        # Token budgeting check - trigger pruning if threshold exceeded
        pruning_status = None
        if total_tokens > max_tokens:
            pruning_status = _trigger_pruning(recent_logs, total_tokens)
        
        return {
            "status": "success",
            "message": "Reflection cycle complete. Long-term insights updated.",
            "insights_count": 1 if entry_id > 0 else 0,
            "tokens_processed": total_tokens,
            "pruning_status": pruning_status,
        }
    finally:
        os.chdir(original_cwd)


def _run_llm_reflection(log_payload: str) -> Optional[str]:
    """Run the LLM reflection pipeline.
    
    Tries local Ollama first, then OpenAI, then falls back to rule-based analysis.
    """
    from .llm import is_local_available, synthesize_with_local, synthesize_with_openai
    
    # Prepare the reflection prompt
    full_prompt = f"{REFLECTION_PROMPT}\n\n{LOG_PAYLOAD_HEADER}{log_payload}"
    
    # Try local Ollama
    if is_local_available():
        result = synthesize_with_local(full_prompt, model="llama3")
        if result:
            return result.summary or "Reflection completed with local LLM."
    
    # Try OpenAI
    if os.environ.get("OPENAI_API_KEY"):
        result = synthesize_with_openai(full_prompt)
        if result:
            return result.summary or "Reflection completed with OpenAI."
    
    # Fall back to rule-based analysis
    return _rule_based_reflection(log_payload)


def _rule_based_reflection(log_payload: str) -> str:
    """Rule-based reflection when no LLM is available."""
    insights = ["# Reflection Insights\n"]
    
    # Extract patterns using simple heuristics
    lines = log_payload.split("\n")
    error_patterns = []
    patterns = []
    
    for line in lines:
        line_lower = line.lower()
        if "error" in line_lower or "bug" in line_lower or "fix" in line_lower:
            error_patterns.append(line.strip())
        if "prefer" in line_lower or "should" in line_lower:
            patterns.append(line.strip())
    
    if error_patterns:
        insights.append("\n## Recurring Patterns & Anti-Patterns\n")
        insights.append("Analysis detected potential recurring issues:\n")
        for p in error_patterns[:5]:
            insights.append(f"- {p}\n")
    
    if patterns:
        insights.append("\n## Potential User Preferences\n")
        insights.append("User may have expressed preferences:\n")
        for p in patterns[:5]:
            insights.append(f"- {p}\n")
    
    if not error_patterns and not patterns:
        insights.append("\nNo clear patterns detected in recent logs.\n")
    
    return "".join(insights)


def _trigger_pruning(logs: List[Dict[str, Any]], total_tokens: int) -> str:
    """Trigger pruning/compression of high-overhead logs.
    
    Compresses logs into a single summary entry to prevent memory rot.
    """
    from .core import get_context_dir
    from .db import add_entry
    
    ctx_dir = get_context_dir()
    logs_dir = ctx_dir / "session-logs"
    
    if not logs_dir.exists() or not logs:
        return "No logs to prune"
    
    # Create a compressed summary
    compressed = ["# Archived Session Log Summaries\n"]
    compressed.append(f"Archived {len(logs)} logs on {datetime.now().strftime('%Y-%m-%d')}\n")
    compressed.append(f"Original size: ~{total_tokens} tokens\n\n")
    
    for log in logs:
        date = log.get("log_date", log.get("id", "unknown"))
        content = log.get("content", "")
        key_lines = [ln for ln in content.split("\n") if ln.strip().startswith(("- ", "* ", "@memory:"))]
        if key_lines:
            compressed.append(f"\n## {date}\n")
            compressed.extend(key_lines[:3])
    
    summary_content = "".join(compressed)
    
    # Save archived summary
    add_entry(
        title="Archived Logs Summary",
        content=summary_content,
        entry_type="note",
        tags=["archive", "reflection", "pruned"],
        importance=2,
        trust_score=0.85,
        source="memtext-reflection-engine",
    )
    
    return f"Pruned {len(logs)} logs into compressed summary"


def save_reflection_insight(
    content: str,
    meta: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Save a reflection insight to the database.
    
    Stores insights in the reflection_insights table (PostgreSQL/SQLite)
    with trust_score flagging for agent staging.
    
    Args:
        content: The markdown content of the insight
        meta: Optional metadata dict (source session IDs, tags, etc.)
        
    Returns:
        Entry ID if successful, -1 if failed
    """
    metadata_json = json.dumps(meta) if meta else None
    
    # For PostgreSQL
    from .db import is_postgres_enabled
    if is_postgres_enabled():
        import asyncio
        return asyncio.run(_save_reflection_insight_postgres(content, metadata_json))
    
    # For SQLite - use the reflection_insights table directly
    from .repositories.database import get_connection, get_db_path, init_db
    db_path = get_db_path()
    
    # Ensure database and table exist
    init_db(db_path)
    
    try:
        with get_connection(db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO reflection_insights (content, source, trust_score, metadata)
                VALUES (?, ?, ?, ?)
                """,
                (content, "memtext-reflection-engine", 0.85, metadata_json),
            )
            conn.commit()
            logger.info("Saved reflection insight to database")
            return cursor.lastrowid
    except Exception as e:
        logger.error(f"Failed to save reflection insight: {e}")
        return -1


async def _save_reflection_insight_postgres(content: str, metadata_json: Optional[str]) -> int:
    """Save reflection insight to PostgreSQL."""
    from .repositories.postgres import get_connection
    
    conn = await get_connection()
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO reflection_insights (content, source, trust_score, metadata)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            content,
            "memtext-reflection-engine",
            0.85,
            metadata_json,
        )
        logger.info("Saved reflection insight to PostgreSQL")
        return hash(str(row['id'])) & 0x7FFFFFFF if row else -1
    except Exception as e:
        logger.error(f"Failed to save reflection insight to PostgreSQL: {e}")
        return -1
    finally:
        await conn.close()