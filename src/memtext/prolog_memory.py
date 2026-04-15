"""Prolog-based memory system for MemText agents.

This module provides a Prolog-based memory logic system that agents can query
to extract, classify, and preserve memories from context.

The Prolog engine manages:
- Memory extraction rules
- Memory importance classification
- Dependency tracking
- Memory preservation decisions

Usage by agents:
    from memtext.prolog_memory import query_memory, classif_memory, preserve_memory

    # Query for important decisions
    results = query_memory("important(X)")

    # Classify what to preserve
    preservable = preserve_memory(entries)
"""

import re
import json
from typing import Optional, List, Dict, Any
from pathlib import Path
from dataclasses import dataclass, asdict


def get_prolog():
    """Get Prolog instance if pyswip is available."""
    try:
        from pyswip import Prolog as PyswipProlog

        return PyswipProlog
    except ImportError:
        return None


PROLOG_AVAILABLE = get_prolog() is not None


PROLOG_MEMORY_RULES = """
% ============================================
% MEMTEXT MEMORY ONTOLOGY
% ============================================

% Memory types
memory_type(decision).
memory_type(convention).
memory_type(pattern).
memory_type(constraint).
memory_type(error).
memory_type(note).

% ============================================
% IMPORTANCE CLASSIFICATION
% ============================================
% Level 3: Critical (decisions, constraints)
important(X) :- decision(X), !.
important(X) :- constraint(X), !.

% Level 2: High (conventions, patterns)
important(X) :- convention(X), !.
important(X) :- pattern(X), !.

% Level 1: Normal (notes, errors)
important(X) :- note(X).
important(X) :- error(X).

% ============================================
% PRESERVATION RULES  
% ============================================

% Always preserve important memories
preserve(X) :- important(X).

% Preserve if frequently accessed (>= 3 times)
preserve(X) :- access_count(X, N), N >= 3.

% Preserve if referenced by other important memory
preserve(X) :- referenced_by(X, Y), important(Y).

% Preserve if recently created (within 7 days)
preserve(X) :- created_recently(X, 7).

% Don't preserve: duplicates, stale, low-value
discard(X) :- duplicate_of(X, _).
discard(X) :- stale(X, 30), not(important(X)).
discard(X) :- low_value(X), not(preserve(X)).

% ============================================
% EXTRACTION PATTERNS
% ============================================

% Decision detection keywords
decision_keyword(chosen).
decision_keyword(decided).
decision_keyword(adopted).
decision_keyword(selected).
decision_keyword(picked).
decision_keyword(going_with).

% Convention detection keywords
convention_keyword(always).
convention_keyword(never).
convention_keyword(must).
convention_keyword(convention).
convention_keyword(standard).

% Pattern detection keywords  
pattern_keyword(pattern).
pattern_keyword(recurring).
pattern_keyword(recurrent).
pattern_keyword(common).

% Constraint detection keywords
constraint_keyword(cannot).
constraint_keyword(must_not).
constraint_keyword(required).
constraint_keyword(depends_on).
constraint_keyword(requires).

% Extract memory type from text
extract_type(Text, decision) :- contains(Text, DecisionKey), decision_keyword(DecisionKey), !.
extract_type(Text, convention) :- contains(Text, ConvKey), convention_keyword(ConvKey), !.
extract_type(Text, pattern) :- contains(Text, PatKey), pattern_keyword(PatKey), !.
extract_type(Text, constraint) :- contains(Text, ConsKey), constraint_keyword(ConsKey), !.
extract_type(Text, note).

% ============================================
% RELATIONSHIP TRACKING
% ============================================

% Entry relationships
depends_on(X, Y) :- sub_string(X, _, _, _, "depends on"), sub_string(Y, _, _, _, "depends on"), X \\= Y.
related_to(X, Y) :- sub_string(X, _, _, _, "related to"), X \\= Y.
similar_to(X, Y) :- sub_string(X, _, _, _, "similar to"), X \\= Y.
contradicts(X, Y) :- sub_string(X, _, _, _, "instead of"), sub_string(Y, _, _, _, "instead of"), X \\= Y.

% ============================================
% MEMORY EXTRACTION QUERIES
% ============================================

% Main extraction: returns all important memories from context
extract_memories(Text, Memories) :- 
    findall(memory(Type, Content), extract_type(Text, Type), Memories).

% Get importance score (1-5)
importance_score(decision, 5).
importance_score(convention, 4).
importance_score(pattern, 4).
importance_score(constraint, 5).
importance_score(error, 2).
importance_score(note, 1).

% ============================================
% QUERY PREDICATES FOR AGENTS
% ============================================

% Query: Is X important?
q_important(X) :- important(X).

% Query: Should X be preserved?
q_preserve(X) :- preserve(X).

% Query: What's the importance of X?
q_importance(X, Score) :- important(X), importance_score(X, Score).

% Query: Find related entries
q_related(X, Y) :- related_to(X, Y).
q_related(X, Y) :- depends_on(X, Y).
"""


class PrologMemory:
    """Prolog-based memory system for agents."""

    def __init__(self):
        self.prolog = None
        self._initialized = False
        if PROLOG_AVAILABLE:
            self._init_prolog()

    def _init_prolog(self):
        """Initialize Prolog with memory rules."""
        try:
            self.prolog = get_prolog()()
            for rule in PROLOG_MEMORY_RULES.split("\n"):
                rule = rule.strip()
                if rule and not rule.startswith("%") and not rule.startswith("=="):
                    try:
                        self.prolog.assertz(rule)
                    except Exception:
                        pass
            self._initialized = True
        except Exception as e:
            print(f"Prolog init error: {e}")
            self._initialized = False

    def is_available(self) -> bool:
        """Check if Prolog is available."""
        return PROLOG_AVAILABLE and self._initialized

    def query(self, goal: str) -> List[Dict]:
        """Query the Prolog memory engine.

        Args:
            goal: Prolog goal string, e.g., "important(X)"

        Returns:
            List of matching bindings
        """
        if not self.is_available():
            return []

        try:
            results = []
            for solution in self.prolog.query(goal):
                results.append(dict(solution))
            return results
        except Exception:
            return []

    def extract_type(self, text: str) -> str:
        """Extract memory type from text using Prolog."""
        if not self.is_available():
            return "note"

        results = self.query(f"extract_type('{text}', Type)")
        if results:
            return results[0].get("Type", "note")
        return "note"

    def get_importance(self, entry_type: str) -> int:
        """Get importance score for a memory type."""
        results = self.query(f"importance_score({entry_type}, Score)")
        if results:
            return results[0].get("Score", 1)
        return 1


def query_memory(goal: str) -> List[Dict]:
    """Query the memory Prolog engine.

    Agent function to query memories from Prolog.

    Args:
        goal: Prolog goal (e.g., "important(X)", "preserve(X)")

    Returns:
        List of matching results

    Example:
        >>> results = query_memory("important(X)")
        >>> for r in results:
        >>>     print(r['X'])
    """
    pm = PrologMemory()
    return pm.query(goal)


def classify_memory(entry: Dict) -> Dict:
    """Classify a memory entry using Prolog rules.

    Args:
        entry: Dict with 'title', 'content', 'entry_type', etc.

    Returns:
        Dict with classification results

    Example:
        >>> entry = {'title': 'We chose Postgres', 'content': '...', 'entry_type': 'decision'}
        >>> result = classify_memory(entry)
        >>> print(result['importance'])  # 5
        >>> print(result['should_preserve'])  # True
    """
    pm = PrologMemory()

    entry_type = entry.get("entry_type", "note")
    importance = pm.get_importance(entry_type)

    preserve_goal = f"preserve({entry_type})"
    should_preserve = len(pm.query(preserve_goal)) > 0

    important_goal = f"important({entry_type})"
    is_important = len(pm.query(important_goal)) > 0

    return {
        "entry_type": entry_type,
        "importance": importance,
        "is_important": is_important,
        "should_preserve": should_preserve,
        "prolog_available": pm.is_available(),
    }


def preserve_memory(entries: List[Dict], max_count: int = 20) -> List[Dict]:
    """Select memories to preserve using Prolog rules.

    Args:
        entries: List of entry dicts
        max_count: Maximum memories to preserve

    Returns:
        Ordered list of entries to preserve (highest importance first)
    """
    pm = PrologMemory()

    if not pm.is_available():
        # Fallback: simple importance sorting
        return sorted(entries, key=lambda e: e.get("importance", 1), reverse=True)[
            :max_count
        ]

    scored = []
    for entry in entries:
        entry_type = entry.get("entry_type", "note")

        # Get importance score
        importance_results = pm.query(f"importance_score({entry_type}, Score)")
        importance = importance_results[0].get("Score", 1) if importance_results else 1

        # Boost by access count
        access_count = entry.get("access_count", 0)
        importance += min(access_count, 3)

        scored.append((importance, entry))

    # Sort by importance (descending)
    scored.sort(key=lambda x: x[0], reverse=True)

    return [e[1] for e in scored[:max_count]]


def extract_memories_from_text(text: str) -> List[Dict]:
    """Extract memories from raw text using Prolog.

    Args:
        text: Raw context text

    Returns:
        List of extracted memory dicts
    """
    pm = PrologMemory()

    if not pm.is_available():
        # Fallback to regex-based extraction
        from memtext.memory_logic import DecisionExtractor

        extractor = DecisionExtractor()
        extracted = extractor.extract_all(text)

        return [
            {
                "content": e.get("content", ""),
                "type": e.get("category", "note"),
                "source": "regex_fallback",
            }
            for e in extracted
        ]

    # Use Prolog extraction
    results = pm.query(f"extract_memories('{text}', Memories)")

    if not results:
        return []

    memories = results[0].get("Memories", [])
    return [{"content": str(m), "type": "note", "source": "prolog"} for m in memories]


def get_related_memories(entry_id: int, entries: List[Dict]) -> List[Dict]:
    """Find related memories using Prolog relationship rules.

    Args:
        entry_id: ID of the entry to find relations for
        entries: All available entries

    Returns:
        List of related entries
    """
    from memtext.graph import get_related_entries

    related = get_related_entries(entry_id)
    return related


# ============================================
# AGENT API FUNCTIONS
# ============================================


def agent_query_important() -> List[Dict]:
    """Agent query: Get all important memory types."""
    return query_memory("q_important(X)")


def agent_query_preserve() -> List[Dict]:
    """Agent query: Get memories that should be preserved."""
    return query_memory("q_preserve(X)")


def agent_get_importance(entry_type: str) -> int:
    """Agent function: Get importance score for a type."""
    pm = PrologMemory()
    return pm.get_importance(entry_type)


def agent_check_relation(entry1: str, entry2: str) -> bool:
    """Agent function: Check if two entries are related."""
    results = query_memory(f"q_related({entry1}, {entry2})")
    return len(results) > 0


# ============================================
# FALLBACK WHEN PROLOG NOT AVAILABLE
# ============================================


class SimpleClassifier:
    """Simple fallback when Prolog is not available."""

    IMPORTANCE_MAP = {
        "decision": 5,
        "constraint": 5,
        "convention": 4,
        "pattern": 4,
        "error": 2,
        "note": 1,
    }

    @classmethod
    def classify(cls, entry: Dict) -> Dict:
        entry_type = entry.get("entry_type", "note")
        importance = cls.IMPORTANCE_MAP.get(entry_type, 1)

        return {
            "entry_type": entry_type,
            "importance": importance,
            "is_important": importance >= 4,
            "should_preserve": importance >= 3,
            "prolog_available": False,
        }

    @classmethod
    def preserve(cls, entries: List[Dict], max_count: int = 20) -> List[Dict]:
        scored = []
        for entry in entries:
            entry_type = entry.get("entry_type", "note")
            importance = cls.IMPORTANCE_MAP.get(entry_type, 1)
            importance += min(entry.get("access_count", 0), 3)
            scored.append((importance, entry))

        scored.sort(reverse=True)
        return [e[1] for e in scored[:max_count]]


def query_memory_simple(goal: str) -> List[Dict]:
    """Simple fallback query when Prolog unavailable."""
    return []


# ============================================
# INIT CHECK
# ============================================


def check_prolog() -> Dict[str, Any]:
    """Check Prolog availability and status."""
    pm = PrologMemory()
    return {
        "available": PROLOG_AVAILABLE,
        "initialized": pm.is_available(),
        "rules_loaded": len(PROLOG_MEMORY_RULES),
    }


if __name__ == "__main__":
    status = check_prolog()
    print(f"Prolog Status: {status}")

    # Demo queries
    if status["available"] and status["initialized"]:
        print("\nDemo queries:")
        print(f"  important(decision): {query_memory('important(decision)')}")
        print(f"  preserve(note): {query_memory('preserve(note)')}")
