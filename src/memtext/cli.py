import argparse
import sys
import logging
from pathlib import Path

from memtext.core import (
    init_context,
    save_context,
    query_context,
    add_log,
    synthesize_memories,
)
from memtext.db import (
    init_db,
    add_entry,
    list_entries,
    register_project,
    list_projects,
    scan_for_projects,
    get_db_path,
)

logger = logging.getLogger("memtext")


class MemTextError(Exception):
    """Base exception for memtext errors."""

    exit_code = 1

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ContextNotFoundError(MemTextError):
    """Raised when .context/ directory is not found."""

    exit_code = 2

    def __init__(self):
        super().__init__("No .context/ directory found. Run 'memtext init' first.")


class DatabaseError(MemTextError):
    """Raised for database-related errors."""

    exit_code = 3


class ValidationError(MemTextError):
    """Raised for input validation errors."""

    exit_code = 4


def setup_logging(verbose: bool = False):
    """Configure logging for memtext."""
    level = logging.DEBUG if verbose else logging.INFO

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    logger.setLevel(level)
    logger.addHandler(handler)

    if not verbose:
        logger.propagate = False


def handle_error(error: Exception) -> int:
    """Handle errors gracefully and return exit code."""
    if isinstance(error, MemTextError):
        print(f"Error: {error.message}", file=sys.stderr)
        return error.exit_code
    elif isinstance(error, argparse.ArgumentError):
        print(f"Argument error: {error}", file=sys.stderr)
        return 4
    else:
        logger.exception("Unexpected error")
        print(f"Unexpected error: {error}", file=sys.stderr)
        return 1


def require_context_dir() -> Path:
    """Ensure .context/ directory exists."""
    ctx_dir = Path.cwd() / ".context"
    if not ctx_dir.exists():
        raise ContextNotFoundError()
    return ctx_dir


def validate_importance(value: int) -> int:
    """Validate importance level."""
    if not 1 <= value <= 5:
        raise ValidationError("Importance must be between 1 and 5")
    return value


def validate_entry_type(value: str) -> str:
    """Validate entry type."""
    valid_types = ["decision", "pattern", "note", "error", "convention", "memory"]
    if value not in valid_types:
        raise ValidationError(f"Invalid type. Must be one of: {', '.join(valid_types)}")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="memtext",
        description="Context offloading for AI agents - persistent memory across sessions",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init", help="Initialize .context/ directory")

    save_parser = subparsers.add_parser("save", help="Save context entry")
    save_parser.add_argument("text", help="Context text to save")
    save_parser.add_argument("--tags", nargs="*", help="Optional tags")

    query_parser = subparsers.add_parser("query", help="Search context")
    query_parser.add_argument("text", help="Search query")
    query_parser.add_argument("--limit", type=int, default=5, help="Max results")

    log_parser = subparsers.add_parser("log", help="Add session log entry")
    log_parser.add_argument("text", help="Session note")
    log_parser.add_argument("--session", help="Session name")

    add_parser = subparsers.add_parser("add", help="Add context entry to SQLite")
    add_parser.add_argument("text", help="Entry title")
    add_parser.add_argument("--content", help="Full content")
    add_parser.add_argument(
        "--type",
        default="note",
        help="Entry type",
    )
    add_parser.add_argument("--tags", nargs="*", help="Tags")
    add_parser.add_argument("--importance", type=int, default=1, help="Importance 1-5")

    list_parser = subparsers.add_parser("list", help="List entries from SQLite")
    list_parser.add_argument("--type", help="Filter by type")
    list_parser.add_argument("--limit", type=int, default=10)

    projects_parser = subparsers.add_parser("projects", help="List projects")
    projects_parser.add_argument(
        "--scan", action="store_true", help="Scan for projects"
    )

    subparsers.add_parser("migrate", help="Migrate v0.1.x to v0.2.0")

    synth_parser = subparsers.add_parser(
        "synthesize",
        help="Synthesize logs into memories",
        description="Extract high-value memories from session logs. Scans for @memory markers in logs or processes provided text.",
    )
    synth_parser.add_argument(
        "--text",
        help="Manual text to synthesize (format: Title: Content (@tags: t1, t2))",
    )
    synth_parser.add_argument(
        "--all", action="store_true", help="Scan all logs (default is recent only)"
    )

    offload_parser = subparsers.add_parser(
        "offload",
        help="Context offloading and extraction",
        description="Extract and rank memories from context. Use for context window management.",
    )
    offload_parser.add_argument(
        "--extract",
        action="store_true",
        help="Extract decisions/conventions/patterns from text",
    )
    offload_parser.add_argument("--text", help="Text to analyze (for --extract)")
    offload_parser.add_argument(
        "--rank", action="store_true", help="Rank entries by preservation priority"
    )
    offload_parser.add_argument(
        "--save", action="store_true", help="Save extracted memories to DB"
    )

    args = parser.parse_args(argv)

    setup_logging(args.verbose)

    if not args.command:
        parser.print_help()
        return 0

    try:
        if args.command == "init":
            init_context()
            init_db()
            logger.info("Initialized context storage")

        elif args.command == "save":
            if not args.text:
                raise ValidationError("Text is required for save command")
            save_context(args.text, args.tags)
            logger.info(f"Saved context: {args.text[:50]}...")

        elif args.command == "query":
            if not args.text:
                raise ValidationError("Search query is required")
            require_context_dir()
            results = query_context(args.text, args.limit)
            if not results:
                print("No results found.")
            for r in results:
                print(f"[{r['file']}] {r['line']}")
                print(f"  {r['content'][:200]}")
                print()

        elif args.command == "log":
            if not args.text:
                raise ValidationError("Log text is required")
            add_log(args.text, args.session)
            logger.info("Added session log")

        elif args.command == "add":
            if not args.text:
                raise ValidationError("Title is required for add command")
            validate_entry_type(args.type)
            validate_importance(args.importance)
            content = args.content or args.text
            try:
                entry_id = add_entry(
                    args.text, content, args.type, args.tags, importance=args.importance
                )
                if entry_id > 0:
                    print(f"Saved entry {entry_id}")
                    logger.info(f"Added entry: {args.text}")
                else:
                    print("Entry already exists. Use a different title.")
            except Exception as e:
                raise DatabaseError(f"Failed to add entry: {e}")

        elif args.command == "list":
            require_context_dir()
            entries = list_entries(args.type, args.limit)
            if not entries:
                print("No entries found.")
            for e in entries:
                print(f"[{e['id']}] {e['title']} ({e['entry_type']})")

        elif args.command == "projects":
            if args.scan:
                found = scan_for_projects()
                for p in found:
                    register_project(p)
                print(f"Found {len(found)} projects")
                logger.info(f"Scanned and registered {len(found)} projects")
            projects = list_projects()
            if not projects:
                print(
                    "No projects registered. Run 'memtext init' or 'memtext projects --scan'"
                )
            for p in projects:
                print(f"{p['path']} - {p['name']}")

        elif args.command == "migrate":
            from memtext.core import migrate_to_db

            require_context_dir()
            count = migrate_to_db()
            print(f"Migrated {count} entries to SQLite")
            logger.info(f"Migrated {count} entries")

        elif args.command == "synthesize":
            count = synthesize_memories(source_text=args.text, recent_only=not args.all)
            print(f"Synthesized {count} new memories from logs")
            logger.info(f"Synthesized {count} memories")

        elif args.command == "offload":
            from memtext.memory_logic import (
                DecisionExtractor,
                ContextOffloader,
                MemorySynthesizer,
            )
            from memtext.db import query_entries

            if args.extract:
                if not args.text:
                    raise ValidationError("--text required for --extract")

                extractor = DecisionExtractor()
                decisions = extractor.extract_decisions(args.text)
                conventions = extractor.extract_conventions(args.text)
                patterns = extractor.extract_patterns(args.text)
                constraints = extractor.extract_constraints(args.text)

                print(f"## Decisions ({len(decisions)})")
                for d in decisions:
                    print(f"- {d['content']}")

                print(f"\n## Conventions ({len(conventions)})")
                for c in conventions:
                    print(f"- {c['content']}")

                print(f"\n## Patterns ({len(patterns)})")
                for p in patterns:
                    print(f"- {p['content']}")

                print(f"\n## Constraints ({len(constraints)})")
                for c in constraints:
                    print(f"- {c['content']}")

                if args.save:
                    require_context_dir()
                    synthesizer = MemorySynthesizer()
                    memories = synthesizer.synthesize(args.text)
                    for mem in memories:
                        add_entry(
                            mem.get("title"),
                            mem.get("content"),
                            mem.get("entry_type"),
                            mem.get("tags"),
                            importance=mem.get("importance", 1),
                        )
                    print(f"\nSaved {len(memories)} memories to database")
                    logger.info(f"Saved {len(memories)} synthesized memories")

            elif args.rank:
                require_context_dir()
                entries = query_entries(limit=100)
                if not entries:
                    print("No entries to rank.")
                else:
                    offloader = ContextOffloader()
                    ranked = offloader.rank_entries(entries)

                    print("# Ranked for Preservation")
                    print("Top entries by importance:\n")
                    for i, entry in enumerate(ranked[:20], 1):
                        imp = entry.get("importance", 1)
                        accesses = entry.get("access_count", 0)
                        print(f"{i}. [{entry['entry_type']}] {entry['title']}")
                        print(f"   importance={imp}, accesses={accesses}")

        else:
            parser.print_help()

    except MemTextError as e:
        return handle_error(e)
    except Exception as e:
        return handle_error(e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
