"""Prolog-based memory logic for context offloading.

Uses Prolog to determine what to preserve when compressing context,
extract high-value memories from raw context, and track memory dependencies.
"""

import re
from typing import Optional
from pathlib import Path


def get_prolog():
    try:
        from pyswip import Prolog as PyswipProlog

        return PyswipProlog
    except ImportError:
        return None


PROLOG_AVAILABLE = get_prolog() is not None


MEMORY_EXTRACTION_RULES = """
% Memory importance classification
important(X) :- decision(X).
important(X) :- pattern_discovered(X).
important(X) :- convention(X).
important(X) :- constraint(X).
important(X) :- linked_to(X, Y), important(Y).

% What to preserve based on importance and access patterns
preserve(X) :- important(X).
preserve(X) :- not_duplicate(X), access_count(X, N), N > 2.
preserve(X) :- frequently_linked(X).

% Decision extraction patterns
contains_decision(Text) :- sub_string(Text, _, _, _, "choosing").
contains_decision(Text) :- sub_string(Text, _, _, _, "decided").
contains_decision(Text) :- sub_string(Text, _, _, _, "chose").
contains_decision(Text) :- sub_string(Text, _, _, _, "adopted").
contains_decision(Text) :- sub_string(Text, _, _, _, "selected").

% Convention extraction
contains_convention(Text) :- sub_string(Text, _, _, _, "always").
contains_convention(Text) :- sub_string(Text, _, _, _, "never").
contains_convention(Text) :- sub_string(Text, _, _, _, "must").
contains_convention(Text) :- sub_string(Text, _, _, _, "convention").

% Pattern extraction
contains_pattern(Text) :- sub_string(Text, _, _, _, "pattern").
contains_pattern(Text) :- sub_string(Text, _, _, _, "pattern:").
contains_pattern(Text) :- sub_string(Text, _, _, _, "recurring").

% Constraint extraction
contains_constraint(Text) :- sub_string(Text, _, _, _, "cannot").
contains_constraint(Text) :- sub_string(Text, _, _, _, "must not").
contains_constraint(Text) :- sub_string(Text, _, _, _, "required").
contains_constraint(Text) :- sub_string(Text, _, _, _, "depends on").

% Dependency relationships
linked_to(X, Y) :- depends_on(X, Y).
linked_to(X, Y) :- related_to(X, Y).
linked_to(X, Y) :- similar_to(X, Y).

% Duplicate detection
not_duplicate(X) :- not(duplicate_of(X, _)).
"""


class DecisionExtractor:
    """Extract structured decisions from raw context text using patterns and Prolog."""

    DECISION_PATTERNS = [
        (r"(?:we|I)\s+(?:chose|decided|adopted|selected|picked)\s+(\w+)", "chosen"),
        (r"(?:use|using)\s+(\w+)\s+(?:for|as)", "technology"),
        (r"(?:switched|migrated)\s+(?:to|from)\s+(\w+)", "migration"),
        (r"(?:rather than|instead of)\s+(\w+)", "rejection"),
    ]

    CONVENTION_PATTERNS = [
        (r"(?:always|never)\s+(?:use|do|avoid)", "directive"),
        (r"(?:must|should)\s+(?:always|never)", "rule"),
        (r"(?:convention|standard):\s*(.+)", "convention"),
    ]

    PATTERN_PATTERNS = [
        (r"pattern:?\s*(.+)", "discovered"),
        (r"recurring\s+(.+)", "recurring"),
    ]

    CONSTRAINT_PATTERNS = [
        (r"depends on\s+(.+)", "dependency"),
        (r"(?:must|required to)\s+(.+)", "requirement"),
        (r"cannot\s+(.+)", "prohibition"),
    ]

    def __init__(self):
        self.prolog = None
        if PROLOG_AVAILABLE:
            self._init_prolog()

    def _init_prolog(self):
        self.prolog = get_prolog()()
        for rule in MEMORY_EXTRACTION_RULES.split("\n"):
            if rule.strip() and not rule.startswith("%"):
                try:
                    self.prolog.assertz(rule.strip())
                except Exception:
                    pass

    def extract_decisions(self, text: str) -> list:
        """Extract decision mentions from text."""
        decisions = []
        for pattern, decision_type in self.DECISION_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match) < 50:
                    decisions.append(
                        {
                            "content": match,
                            "type": decision_type,
                            "category": "decision",
                        }
                    )
        return decisions

    def extract_conventions(self, text: str) -> list:
        """Extract conventions from text."""
        conventions = []
        for pattern, conv_type in self.CONVENTION_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match) < 200:
                    conventions.append(
                        {"content": match, "type": conv_type, "category": "convention"}
                    )
        return conventions

    def extract_patterns(self, text: str) -> list:
        """Extract patterns from text."""
        patterns = []
        for pattern, pat_type in self.PATTERN_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match) < 200:
                    patterns.append(
                        {"content": match, "type": pat_type, "category": "pattern"}
                    )
        return patterns

    def extract_constraints(self, text: str) -> list:
        """Extract constraints from text."""
        constraints = []
        for pattern, cons_type in self.CONSTRAINT_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match) < 200:
                    constraints.append(
                        {"content": match, "type": cons_type, "category": "constraint"}
                    )
        return constraints

    def extract_all(self, text: str) -> list:
        """Extract all memory types from text."""
        results = []
        results.extend(self.extract_decisions(text))
        results.extend(self.extract_conventions(text))
        results.extend(self.extract_patterns(text))
        results.extend(self.extract_constraints(text))
        return results


class ContextOffloader:
    """Determine what to preserve when offloading context."""

    def __init__(self):
        self.extractor = DecisionExtractor()

    def rank_entries(self, entries: list) -> list:
        """Rank entries by preservation priority.

        Uses importance scoring:
        - decisions +3
        - conventions +2
        - constraints +2
        - patterns +2
        - linked entries +1 per link
        - access_count +1 per access
        """
        scored = []
        for entry in entries:
            score = 1  # base score
            entry_type = entry.get("entry_type", "").lower()
            content = entry.get("content", "").lower()
            title = entry.get("title", "").lower()

            if entry_type == "decision" or "decision" in content or "decide" in content:
                score += 3
            if entry_type == "convention" or "convention" in content:
                score += 2
            if "constraint" in content or "must" in content or "required" in content:
                score += 2
            if "pattern" in content or "recurring" in content:
                score += 2

            # Boost if has tags (manual importance signal)
            if entry.get("tags"):
                score += 1

            # Access-based boost
            access_count = entry.get("access_count", 0)
            score += min(access_count, 5)  # cap at +5

            # Importance field boost
            importance = entry.get("importance", 1)
            score += importance

            scored.append((score, entry))

        return [e[1] for e in sorted(scored, key=lambda x: x[0], reverse=True)]

    def select_for_preservation(
        self, entries: list, max_tokens: Optional[int] = None
    ) -> list:
        """Select entries to preserve within token budget.

        Args:
            entries: List of context entries
            max_tokens: Maximum tokens to preserve (None = keep all)
        """
        ranked = self.rank_entries(entries)

        if max_tokens is None:
            return ranked

        selected = []
        total_tokens = 0
        for entry in ranked:
            entry_tokens = len(entry.get("content", "").split()) + len(
                entry.get("title", "").split()
            )

            if total_tokens + entry_tokens <= max_tokens:
                selected.append(entry)
                total_tokens += entry_tokens
            else:
                break

        return selected

    def identify_dependencies(self, entries: list) -> dict:
        """Build dependency graph between entries.

        Returns:
            Dict mapping entry_id to list of dependent entry_ids
        """
        dependencies = {}

        for entry in entries:
            entry_id = entry.get("id")
            content = entry.get("content", "")
            title = entry.get("title", "")

            deps = set()

            # Look for dependency mentions
            dep_patterns = [
                r"(?:depends on|related to|similar to)[\s:]+([^\n]+)",
                r"(?:see also|see)[\s:]+([^\n]+)",
            ]

            for pattern in dep_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    if len(match) < 100:
                        deps.add(match.strip())

            dependencies[entry_id] = list(deps)

        return dependencies

    def get_cascade_deletion_order(self, entries: list, delete_ids: list) -> list:
        """Get entries that should be deleted when dependency is deleted.

        Args:
            entries: All context entries
            delete_ids: IDs of entries to delete

        Returns:
            Ordered list of entry IDs to delete (dependencies first)
        """
        deps = self.identify_dependencies(entries)
        to_delete = set(delete_ids)

        # Find all entries that depend on deleted entries
        for entry_id in delete_ids:
            for eid, dependencies in deps.items():
                if entry_id in dependencies:
                    to_delete.add(eid)

        return list(to_delete)


class MemorySynthesizer:
    """Synthesize new memories from raw context."""

    def __init__(self):
        self.extractor = DecisionExtractor()

    def synthesize(self, context_text: str) -> list:
        """Extract high-value memories from context text.

        Args:
            context_text: Raw context to analyze

        Returns:
            List of synthesized memory dicts ready for storage
        """
        memories = self.extractor.extract_all(context_text)

        synthesized = []
        seen = set()

        for mem in memories:
            key = (mem.get("content", ""), mem.get("category", ""))
            if key not in seen and mem.get("content"):
                seen.add(key)

                # Assign importance based on category
                importance = 1
                if mem.get("category") == "decision":
                    importance = 3
                elif mem.get("category") in ("convention", "constraint"):
                    importance = 2

                synthesized.append(
                    {
                        "title": f"{mem.get('category', 'memory').title()}: {mem.get('content', '')[:50]}",
                        "content": mem.get("content", ""),
                        "entry_type": "memory",
                        "importance": importance,
                        "tags": [mem.get("category", "memory")],
                    }
                )

        return synthesized

    def generate_summary(self, memories: list) -> str:
        """Generate a summary of extracted memories.

        Args:
            memories: List of memory dicts

        Returns:
            Markdown summary string
        """
        if not memories:
            return "No memories extracted."

        lines = ["# Synthesized Memories\n"]

        by_category = {}
        for mem in memories:
            cat = mem.get("category", "unknown")
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(mem)

        for category, items in by_category.items():
            lines.append(f"## {category.title()}\n")
            for item in items:
                lines.append(f"- {item.get('content', '')}")
            lines.append("")

        return "\n".join(lines)


def check_prolog_available() -> bool:
    """Check if Prolog (pyswip) is available."""
    return PROLOG_AVAILABLE


def get_prolog_instance():
    """Get Prolog instance if available."""
    if PROLOG_AVAILABLE:
        return get_prolog()()
    return None
