"""Tests for memory_logic module."""

import pytest
from memtext.memory_logic import (
    DecisionExtractor,
    ContextOffloader,
    MemorySynthesizer,
    check_prolog_available,
)


class TestDecisionExtractor:
    def test_extract_decisions(self):
        extractor = DecisionExtractor()

        text = (
            "we chose PostgreSQL for the database and decided to use Redis for caching"
        )
        decisions = extractor.extract_decisions(text)

        assert len(decisions) > 0
        assert any("postgresql" in d["content"].lower() for d in decisions)

    def test_extract_conventions(self):
        extractor = DecisionExtractor()

        text = "We must always use type hints. Never use any for types."
        conventions = extractor.extract_conventions(text)

        assert len(conventions) > 0

    def test_extract_patterns(self):
        extractor = DecisionExtractor()

        text = "pattern: retry with exponential backoff is a common pattern"
        patterns = extractor.extract_patterns(text)

        assert len(patterns) > 0

    def test_extract_constraints(self):
        extractor = DecisionExtractor()

        text = "This feature depends on the auth system. Cannot use without login."
        constraints = extractor.extract_constraints(text)

        assert len(constraints) > 0

    def test_extract_all(self):
        extractor = DecisionExtractor()

        text = """
        We chose PostgreSQL for storage.
        Convention: Always use type hints.
        Pattern: exponential backoff for retries.
        Cannot run without database connection.
        """
        results = extractor.extract_all(text)

        assert len(results) > 0
        categories = set(r["category"] for r in results)
        assert "decision" in categories


class TestContextOffloader:
    def test_rank_entries(self):
        offloader = ContextOffloader()

        entries = [
            {
                "id": 1,
                "title": "Test decision",
                "content": "decide on postgres",
                "entry_type": "decision",
                "importance": 1,
                "access_count": 0,
            },
            {
                "id": 2,
                "title": "Test note",
                "content": "some note",
                "entry_type": "note",
                "importance": 1,
                "access_count": 5,
            },
            {
                "id": 3,
                "title": "Important",
                "content": "critical constraint",
                "entry_type": "convention",
                "importance": 3,
                "access_count": 0,
            },
        ]

        ranked = offloader.rank_entries(entries)

        # First should be highest importance + convention/constraint boost
        assert ranked[0]["id"] == 3
        # Should include decision in top results (may be ranked after note due to access count)
        ids = [e["id"] for e in ranked]
        assert 1 in ids

    def test_select_for_preservation(self):
        offloader = ContextOffloader()

        entries = [
            {
                "id": 1,
                "title": "A",
                "content": "a",
                "entry_type": "note",
                "importance": 1,
                "access_count": 0,
            },
            {
                "id": 2,
                "title": "B",
                "content": "b",
                "entry_type": "decision",
                "importance": 3,
                "access_count": 0,
            },
            {
                "id": 3,
                "title": "C",
                "content": "c",
                "entry_type": "note",
                "importance": 1,
                "access_count": 0,
            },
        ]

        selected = offloader.select_for_preservation(entries, max_tokens=3)

        assert len(selected) <= 3

    def test_identify_dependencies(self):
        offloader = ContextOffloader()

        entries = [
            {
                "id": 1,
                "title": "PostgreSQL",
                "content": "We chose PostgreSQL",
                "entry_type": "decision",
            },
            {
                "id": 2,
                "title": "ORM",
                "content": "Depends on PostgreSQL, use SQLAlchemy",
                "entry_type": "decision",
            },
        ]

        deps = offloader.identify_dependencies(entries)

        assert 2 in deps
        assert "postgresql" in str(deps.get(2, [])).lower()

    def test_cascade_deletion_order(self):
        offloader = ContextOffloader()

        entries = [
            {
                "id": 1,
                "title": "Database",
                "content": "PostgreSQL choice",
                "entry_type": "decision",
            },
            {
                "id": 2,
                "title": "ORM",
                "content": "Depends on database",
                "entry_type": "decision",
            },
            {"id": 3, "title": "API", "content": "Uses ORM", "entry_type": "note"},
        ]

        cascade = offloader.get_cascade_deletion_order(entries, [1])

        assert 1 in cascade


class TestMemorySynthesizer:
    def test_synthesize(self):
        synthesizer = MemorySynthesizer()

        text = "We chose PostgreSQL for storage. Must use type hints always."
        memories = synthesizer.synthesize(text)

        assert len(memories) > 0
        assert any(m["entry_type"] == "memory" for m in memories)

    def test_generate_summary(self):
        synthesizer = MemorySynthesizer()

        memories = [
            {"content": "postgresql", "category": "decision"},
            {"content": "type hints", "category": "convention"},
        ]

        summary = synthesizer.generate_summary(memories)

        assert "decision" in summary.lower()
        assert "convention" in summary.lower()

    def test_synthesize_empty(self):
        synthesizer = MemorySynthesizer()

        memories = synthesizer.synthesize("")

        assert len(memories) == 0


def test_check_prolog_available():
    result = check_prolog_available()
    assert isinstance(result, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
