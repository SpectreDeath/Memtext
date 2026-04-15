"""Relationship graph for MemText context.

Tracks relationships between entries for better context retrieval.
"""

import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Set
from collections import defaultdict


def get_graph_path() -> Path:
    """Get path to relationship graph database."""
    return Path.cwd() / ".context" / "relationships.db"


def init_graph() -> Path:
    """Initialize relationship graph database."""
    graph_path = get_graph_path()
    graph_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(graph_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            relationship_type TEXT NOT NULL,
            strength REAL DEFAULT 1.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_id, target_id, relationship_type)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cooccurrence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            session_id TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_relationships_source
        ON relationships(source_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cooccurrence_entry
        ON cooccurrence(entry_id)
    """)

    conn.commit()
    conn.close()
    return graph_path


def add_relationship(
    source_id: int,
    target_id: int,
    relationship_type: str = "related",
    strength: float = 1.0,
) -> bool:
    """Add a relationship between two entries."""
    graph_path = get_graph_path()
    if not graph_path.exists():
        init_graph()

    try:
        conn = sqlite3.connect(graph_path)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT OR REPLACE INTO relationships 
               (source_id, target_id, relationship_type, strength) 
               VALUES (?, ?, ?, ?)""",
            (source_id, target_id, relationship_type, strength),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error:
        return False


def get_related_entries(entry_id: int, limit: int = 10) -> List[Dict]:
    """Get entries related to the given entry."""
    graph_path = get_graph_path()
    if not graph_path.exists():
        return []

    conn = sqlite3.connect(graph_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """SELECT r.*, e.title, e.content, e.entry_type
           FROM relationships r
           JOIN context_entries e ON r.target_id = e.id
           WHERE r.source_id = ?
           ORDER BY r.strength DESC
           LIMIT ?""",
        (entry_id, limit),
    )

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def auto_detect_relationships(content_pairs: List[tuple]) -> List[tuple]:
    """Auto-detect relationships from content.

    Args:
        content_pairs: List of (entry_id, content) tuples

    Returns:
        List of (source_id, target_id, relationship_type, strength) tuples
    """
    relationships = []
    content_by_id = {cid: content.lower() for cid, content in content_pairs}

    keywords = {
        "depends_on": ["depends on", "requires", "needs", "build on"],
        "similar_to": ["similar to", "like", "also", "same"],
        "contrast_with": ["instead of", "rather than", "unlike", "but"],
        "related_to": ["related to", "see also", "see", "关联"],
    }

    for id1, content1 in content_pairs:
        for id2, content2 in content_pairs:
            if id1 >= id2:
                continue

            for rel_type, keywords_list in keywords.items():
                if any(kw in content1 for kw in keywords_list):
                    if any(kw in content2 for kw in keywords_list):
                        relationships.append((id1, id2, rel_type, 0.8))
                        break

    return relationships


def build_relationships_from_entries(entries: List[Dict]) -> int:
    """Build relationships by analyzing entry content."""
    content_pairs = [(e["id"], e.get("content", "")) for e in entries if "id" in e]
    relations = auto_detect_relationships(content_pairs)

    count = 0
    for source_id, target_id, rel_type, strength in relations:
        if add_relationship(source_id, target_id, rel_type, strength):
            count += 1

    return count


def record_cooccurrence(entry_id: int, session_id: str = None):
    """Record that an entry was accessed in a session."""
    graph_path = get_graph_path()
    if not graph_path.exists():
        init_graph()

    conn = sqlite3.connect(graph_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO cooccurrence (entry_id, session_id) VALUES (?, ?)",
        (entry_id, session_id),
    )
    conn.commit()
    conn.close()


def get_frequently_accessed_together(entry_id: int, limit: int = 5) -> List[Dict]:
    """Get entries frequently accessed together with this one."""
    graph_path = get_graph_path()
    if not graph_path.exists():
        return []

    conn = sqlite3.connect(graph_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT c2.entry_id, COUNT(*) as access_count, e.title, e.content
        FROM cooccurrence c1
        JOIN cooccurrence c2 ON c1.session_id = c2.session_id
            AND c1.entry_id != c2.entry_id
        JOIN context_entries e ON c2.entry_id = e.id
        WHERE c1.entry_id = ?
        GROUP BY c2.entry_id
        ORDER BY access_count DESC
        LIMIT ?
    """,
        (entry_id, limit),
    )

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_relationship_stats() -> Dict:
    """Get statistics about the relationship graph."""
    graph_path = get_graph_path()
    if not graph_path.exists():
        return {"total_relationships": 0, "total_cooccurrences": 0}

    conn = sqlite3.connect(graph_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM relationships")
    rel_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM cooccurrence")
    cooc_count = cursor.fetchone()[0]

    conn.close()

    return {
        "total_relationships": rel_count,
        "total_cooccurrences": cooc_count,
    }


def suggest_related(query: str, entries: List[Dict], limit: int = 5) -> List[Dict]:
    """Suggest related entries based on query keywords."""
    query_terms = set(query.lower().split())
    scored = []

    for entry in entries:
        content = entry.get("content", "").lower()
        title = entry.get("title", "").lower()
        text = f"{title} {content}"

        score = sum(1 for term in query_terms if term in text)
        if score > 0:
            scored.append((score, entry))

    scored.sort(reverse=True)
    return [e[1] for e in scored[:limit]]
