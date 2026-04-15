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
from memtext import logging_config

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

    export_parser = subparsers.add_parser(
        "export",
        help="Export project context to bundle",
        description="Export context to a .mtbundle file for sharing",
    )
    export_parser.add_argument(
        "--output", help="Output filename (default: context.mtbundle)"
    )

    import_parser = subparsers.add_parser(
        "import",
        help="Import project context from bundle",
        description="Import context from a .mtbundle file",
    )
    import_parser.add_argument("file", help="Bundle file to import")
    import_parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing entries"
    )

    share_parser = subparsers.add_parser(
        "share",
        help="Share an entry across projects",
        description="Mark an entry as shared for cross-project access",
    )
    share_parser.add_argument("entry_id", type=int, help="Entry ID to share")

    synthesize_ai_parser = subparsers.add_parser(
        "synthesize-ai",
        help="Synthesize with AI (requires LLM)",
        description="Use LLM for intelligent memory synthesis. Supports Ollama (local) or OpenAI.",
    )
    synthesize_ai_parser.add_argument("--text", help="Text to synthesize")
    synthesize_ai_parser.add_argument(
        "--model", default="llama3", help="Model for local synthesis"
    )
    synthesize_ai_parser.add_argument(
        "--rule-based", action="store_true", help="Use rule-based fallback"
    )

    retag_parser = subparsers.add_parser(
        "retag",
        help="Auto-tag entries",
        description="Automatically tag entries based on content",
    )
    retag_parser.add_argument("--entry-id", type=int, help="Entry ID to retag")
    retag_parser.add_argument("--all", action="store_true", help="Retag all entries")

    link_parser = subparsers.add_parser(
        "link",
        help="Build relationship graph",
        description="Auto-detect relationships between entries",
    )
    link_parser.add_argument("--entry-id", type=int, help="Entry ID to find links for")
    link_parser.add_argument("--limit", type=int, default=5, help="Max results")

    serve_parser = subparsers.add_parser(
        "serve",
        help="Start API server",
        description="Start the MemText REST API server. Requires: pip install memtext[api]",
    )
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    serve_parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload"
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
            if not args.content:
                print(
                    "Note: Using title as content. Use --content to specify separate content."
                )
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

        elif args.command == "export":
            try:
                from memtext.collaboration import ProjectBundle

                output_path = (
                    Path(args.output) if args.output else Path.cwd() / "context"
                )
                bundle = ProjectBundle(output_path)
                output = bundle.export()
                print(f"Exported to: {output.name}")
                logger.info(f"Exported bundle to {output}")
            except Exception as e:
                raise DatabaseError(f"Export failed: {e}")

        elif args.command == "import":
            try:
                from memtext.collaboration import ProjectBundle

                bundle_file = Path(args.file)
                if not bundle_file.exists():
                    raise ValidationError(f"File not found: {args.file}")
                bundle = ProjectBundle(bundle_file)
                count = bundle.import_(overwrite=args.overwrite)
                print(f"Imported {count} entries")
                logger.info(f"Imported {count} entries from {bundle_file.name}")
            except Exception as e:
                raise DatabaseError(f"Import failed: {e}")

        elif args.command == "share":
            require_context_dir()
            try:
                from memtext.db import make_shared

                entry_id = args.entry_id
                success = make_shared(entry_id)
                if success:
                    print(f"Entry {entry_id} marked as shared")
                    logger.info(f"Marked entry {entry_id} as shared")
                else:
                    print(f"Entry {entry_id} not found")
            except Exception as e:
                raise DatabaseError(f"Share failed: {e}")

        elif args.command == "synthesize-ai":
            try:
                from memtext.llm import (
                    synthesize,
                    synthesize_rule_based,
                    check_llm_available,
                )

                available = check_llm_available()
                print(f"LLM availability: {available}")

                if args.rule_based:
                    text = args.text or "Sample context for testing"
                    result = synthesize_rule_based(text)
                    print(f"\nSummary: {result.summary}")
                    print(f"Memories: {len(result.memories)}")
                    print(f"Tags: {result.tags}")
                else:
                    if args.text:
                        result = synthesize(args.text)
                        if result:
                            print(f"\nSummary: {result.summary}")
                            print(f"Memories: {len(result.memories)}")
                            for mem in result.memories:
                                print(f"  - {mem.get('title')}")
                            print(f"Tags: {result.tags}")
                        else:
                            print(
                                "No LLM available. Install openai package or run Ollama."
                            )
                    else:
                        print("No text provided. Use --text or --rule-based")
            except ImportError:
                print("Error: LLM package not installed.")
                print("Run: pip install memtext[llm]")
                return 5

        elif args.command == "retag":
            try:
                from memtext.llm import AutoTagger

                require_context_dir()

                tagger = AutoTagger()

                if args.all:
                    entries = list_entries(limit=100)
                    for entry in entries:
                        tags = tagger.tag_content(entry.get("content", ""))
                        if tags:
                            print(f"Entry {entry['id']}: {', '.join(tags)}")
                elif args.entry_id:
                    from memtext.db import get_entry

                    entry = get_entry(args.entry_id)
                    if entry:
                        tags = tagger.tag_content(entry.get("content", ""))
                        print(f"Entry {args.entry_id} tags: {', '.join(tags)}")
                    else:
                        print(f"Entry {args.entry_id} not found")
                else:
                    print("Use --entry-id or --all")
            except Exception as e:
                raise DatabaseError(f"Retag failed: {e}")

        elif args.command == "link":
            try:
                require_context_dir()
                from memtext.graph import (
                    get_related_entries,
                    build_relationships_from_entries,
                    init_graph,
                )

                init_graph()

                if args.entry_id:
                    related = get_related_entries(args.entry_id, args.limit)
                    if related:
                        print(f"Related to entry {args.entry_id}:")
                        for r in related:
                            print(f"  [{r.get('entry_type')}] {r.get('title')}")
                    else:
                        print("No relationships found")
                else:
                    entries = list_entries(limit=50)
                    count = build_relationships_from_entries(entries)
                    print(f"Built {count} relationships")
            except Exception as e:
                raise DatabaseError(f"Link failed: {e}")

        elif args.command == "serve":
            try:
                from memtext.api import run as api_run

                logger.info(f"Starting API server on {args.host}:{args.port}")
                api_run(host=args.host, port=args.port, reload=args.reload)
            except ImportError:
                print("Error: FastAPI not installed.")
                print("Run: pip install memtext[api]")
                return 5

        else:
            parser.print_help()

    except MemTextError as e:
        return handle_error(e)
    except Exception as e:
        return handle_error(e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
