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

    # First get target IDs from relationships
    cursor.execute(
        """SELECT r.target_id, r.relationship_type, r.strength
           FROM relationships r
           WHERE r.source_id = ?
           ORDER BY r.strength DESC
           LIMIT ?""",
        (entry_id, limit),
    )
    rel_rows = cursor.fetchall()
    conn.close()

    if not rel_rows:
        return []

    # Then fetch entry details from main DB
    from memtext.db import get_db_path

    db_path = get_db_path()
    if not db_path.exists():
        return []

    target_ids = [r["target_id"] for r in rel_rows]
    placeholders = ",".join("?" * len(target_ids))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        f"""SELECT id, title, content, entry_type, importance, tags, created_at
            FROM context_entries
            WHERE id IN ({placeholders})""",
        target_ids,
    )

    entry_rows = {row["id"]: dict(row) for row in cursor.fetchall()}
    conn.close()

    # Merge relationship data with entry data
    results = []
    for rel in rel_rows:
        if rel["target_id"] in entry_rows:
            entry = entry_rows[rel["target_id"]]
            entry["relationship_type"] = rel["relationship_type"]
            entry["strength"] = rel["strength"]
            results.append(entry)

    return results


def auto_detect_relationships(content_pairs: List[tuple]) -> List[tuple]:
    """Auto-detect relationships from content.

    Args:
        content_pairs: List of (entry_id, content) tuples

    Returns:
        List of (source_id, target_id, relationship_type, strength) tuples
    """
    relationships = []
    content_by_id = {cid: content.lower() for cid, content in content_pairs}

    # Extract key terms from each entry (first few words or important nouns)
    key_terms = {}
    for entry_id, content in content_pairs:
        words = content.lower().split()[:10]
        key_terms[entry_id] = set(words)

    keywords = {
        "depends_on": ["depends on", "requires", "needs", "build on"],
        "similar_to": ["similar to", "like", "also", "same"],
        "contrast_with": ["instead of", "rather than", "unlike", "but"],
        "related_to": ["related to", "see also", "see"],
    }

    for id1, content1 in content_pairs:
        for id2, content2 in content_pairs:
            if id1 >= id2:
                continue

            content1_lower = content1.lower()
            content2_lower = content2.lower()

            # Check if content1 has keywords and references content2's key terms
            for rel_type, keywords_list in keywords.items():
                has_keyword = any(kw in content1_lower for kw in keywords_list)
                references_other = any(
                    term in content1_lower for term in key_terms.get(id2, [])
                )

                if has_keyword and references_other:
                    relationships.append((id1, id2, rel_type, 0.8))
                    break

                # Also check reverse for bi-directional relationships
                has_keyword_rev = any(kw in content2_lower for kw in keywords_list)
                references_other_rev = any(
                    term in content2_lower for term in key_terms.get(id1, [])
                )

                if has_keyword_rev and references_other_rev:
                    relationships.append((id2, id1, rel_type, 0.8))
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


def generate_graph_visualization(output_path: Path, limit: int = 100) -> str:
    """Generate an HTML file with D3.js force-directed graph visualization.

    Args:
        output_path: Path to write the HTML file
        limit: Maximum number of nodes to include

    Returns:
        Path to generated HTML file as string
    """
    from memtext.db import get_db_path, list_entries

    db_path = get_db_path()
    if not db_path.exists():
        raise FileNotFoundError("Database not initialized")

    # Get entries and relationships
    entries = list_entries(limit=limit)

    graph_path = get_graph_path()
    if not graph_path.exists():
        # No relationships yet
        nodes = []
        links = []
    else:
        conn = sqlite3.connect(graph_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM relationships LIMIT 1000")
        rel_rows = cursor.fetchall()
        conn.close()

        links = [dict(row) for row in rel_rows]
        # Get unique target IDs
        node_ids = set()
        for link in links:
            node_ids.add(link["source_id"])
            node_ids.add(link["target_id"])
        nodes = [e for e in entries if e["id"] in node_ids]

    # Ensure all linked nodes have entry data
    entry_by_id = {e["id"]: e for e in entries}
    for node_id in node_ids:
        if node_id not in entry_by_id:
            # Add placeholder
            entry_by_id[node_id] = {
                "id": node_id,
                "title": f"Entry {node_id}",
                "entry_type": "unknown",
            }

    nodes = list(entry_by_id.values())

    # Build HTML with embedded D3.js
    html_template = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>MemText Graph Visualization</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        body { margin: 0; font-family: sans-serif; }
        .links line { stroke: #999; stroke-opacity: 0.6; }
        .nodes circle { stroke: #fff; stroke-width: 1.5px; }
        .node-label { font-size: 10px; }
        #graph { width: 100vw; height: 100vh; }
    </style>
</head>
<body>
<div id="graph"></div>
<script>
const nodes = {NODES};
const links = {LINKS};

const width = window.innerWidth;
const height = window.innerHeight;

const svg = d3.select("#graph")
    .append("svg")
    .attr("width", width)
    .attr("height", height)
    .attr("viewBox", [0, 0, width, height]);

const simulation = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(d => d.id).distance(100))
    .force("charge", d3.forceManyBody().strength(-300))
    .force("center", d3.forceCenter(width / 2, height / 2));

const link = svg.append("g")
    .attr("class", "links")
    .selectAll("line")
    .data(links)
    .join("line")
    .attr("stroke-width", d => Math.sqrt(d.strength || 1) * 2);

const node = svg.append("g")
    .attr("class", "nodes")
    .selectAll("circle")
    .data(nodes)
    .join("circle")
    .attr("r", 8)
    .attr("fill", d => {
        const colors = {{"decision": "#e41a1c", "pattern": "#377eb8", "error": "#4daf4a", "convention": "#984ea3", "memory": "#ff7f00", "note": "#999999"}};
        return colors[d.entry_type] || "#666";
    })
    .call(d3.drag()
        .on("start", dragstarted)
        .on("drag", dragged)
        .on("end", dragended));

const label = svg.append("g")
    .attr("class", "node-labels")
    .selectAll("text")
    .data(nodes)
    .join("text")
    .text(d => d.title)
    .attr("font-size", 9)
    .attr("dx", 12)
    .attr("dy", 4);

simulation.on("tick", () => {
    link
        .attr("x1", d => d.source.x)
        .attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x)
        .attr("y2", d => d.target.y);

    node
        .attr("cx", d => d.x)
        .attr("cy", d => d.y);

    label
        .attr("x", d => d.x)
        .attr("y", d => d.y);
});

function dragstarted(event, d) { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }
function dragged(event, d) { d.fx = event.x; d.fy = event.y; }
function dragended(event, d) { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }
</script>
</body>
</html>"""

    # Convert nodes/links to JSON for embedding
    import json

    nodes_json = []
    for n in nodes:
        nodes_json.append(
            {
                "id": n["id"],
                "title": n.get("title", "")[:50],
                "entry_type": n.get("entry_type", "note"),
            }
        )
    links_json = []
    for l in links:
        links_json.append(
            {
                "source": l["source_id"],
                "target": l["target_id"],
                "relationship_type": l.get("relationship_type", "related"),
                "strength": l.get("strength", 1.0),
            }
        )

    html = html_template.replace("{NODES}", json.dumps(nodes_json)).replace(
        "{LINKS}", json.dumps(links_json)
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return str(output_path)
