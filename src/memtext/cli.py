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
    add_parser.add_argument("--parent-tag", help="Parent tag for hierarchy")
    add_parser.add_argument("--template", help="Use a predefined template")
    add_parser.add_argument("--importance", type=int, default=1, help="Importance 1-5")

    list_parser = subparsers.add_parser("list", help="List entries from SQLite")
    list_parser.add_argument("--type", help="Filter by type")
    list_parser.add_argument("--parent-tag", help="Filter by parent tag")
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

    # Reminder commands
    remind_parser = subparsers.add_parser(
        "remind",
        help="Set a reminder for an entry",
        description="Flag an entry for follow-up review at a specific time",
    )
    remind_parser.add_argument("entry_id", type=int, help="Entry ID")
    remind_parser.add_argument("--at", required=True, help="Reminder time (YYYY-MM-DD HH:MM)")
    remind_parser.add_argument("--message", help="Reminder message")

    reminders_parser = subparsers.add_parser(
        "reminders",
        help="List pending reminders",
        description="Show all pending reminders that are due",
    )

    reminder_complete_parser = subparsers.add_parser(
        "reminder-complete",
        help="Mark reminder as completed",
        description="Mark a reminder as done",
    )
    reminder_complete_parser.add_argument("reminder_id", type=int, help="Reminder ID")

    reminder_list_parser = subparsers.add_parser(
        "reminder-list",
        help="List all reminders",
        description="List all reminders, optionally filtered by entry",
    )
    reminder_list_parser.add_argument("--entry-id", type=int, help="Filter by entry ID")

    # Encryption commands
    encrypt_parser = subparsers.add_parser(
        "encrypt",
        help="Encrypt an entry",
        description="Encrypt entry content with a password",
    )
    encrypt_parser.add_argument("entry_id", type=int, help="Entry ID")

    decrypt_parser = subparsers.add_parser(
        "decrypt",
        help="Decrypt an entry",
        description="Decrypt entry content with a password",
    )
    decrypt_parser.add_argument("entry_id", type=int, help="Entry ID")

    # Template management
    template_parser = subparsers.add_parser(
        "template",
        help="Manage entry templates",
        description="Create, list, and view entry templates",
    )
    template_subparsers = template_parser.add_subparsers(dest="template_command")

    template_add_parser = template_subparsers.add_parser("add", help="Create a new template")
    template_add_parser.add_argument("name", help="Template name")
    template_add_parser.add_argument("--description", help="Template description")
    template_add_parser.add_argument("--type", default="note", help="Entry type")
    template_add_parser.add_argument("--fields", help="JSON schema for fields")

    template_list_parser = template_subparsers.add_parser("list", help="List all templates")
    template_show_parser = template_subparsers.add_parser("show", help="Show template details")
    template_show_parser.add_argument("name", help="Template name")

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

    history_parser = subparsers.add_parser(
        "history",
        help="Show entry version history",
        description="Display change history for an entry",
    )
    history_parser.add_argument("entry_id", type=int, help="Entry ID")
    retag_parser.add_argument("--entry-id", type=int, help="Entry ID to retag")
    retag_parser.add_argument("--all", action="store_true", help="Retag all entries")

    link_parser = subparsers.add_parser(
        "link",
        help="Build relationship graph",
        description="Auto-detect relationships between entries",
    )

    graph_parser = subparsers.add_parser(
        "graph",
        help="Generate graph visualization",
        description="Create an interactive HTML force graph of entry relationships",
    )
    graph_parser.add_argument("--output", default="memtext_graph.html", help="Output HTML file")
    graph_parser.add_argument("--limit", type=int, default=100, help="Max nodes to include")
    link_parser.add_argument("--entry-id", type=int, help="Entry ID to find links for")
    link_parser.add_argument("--limit", type=int, default=5, help="Max results")

    serve_parser = subparsers.add_parser(
        "serve",
        help="Start API server",
        description="Start the MemText REST API server. Requires: pip install memtext[api]",
    )

    # Git sync commands
    sync_parser = subparsers.add_parser(
        "sync",
        help="Synchronize context with git remote",
        description="Push/pull .context/ changes to/from a git remote",
    )

    # Backup/Restore commands
    backup_parser = subparsers.add_parser(
        "backup",
        help="Create a database backup",
        description="Create a backup of the memtext database",
    )
    backup_parser.add_argument("--type", default="manual", choices=["manual", "scheduled"], help="Backup type")

    backup_list_parser = subparsers.add_parser(
        "backup-list",
        help="List available backups",
        description="Show all available backups",
    )

    restore_parser = subparsers.add_parser(
        "restore",
        help="Restore from a backup",
        description="Restore database from a backup file or backup ID",
    )

    # Webhook commands
    webhook_parser = subparsers.add_parser(
        "webhook",
        help="Manage webhooks",
        description="Create, list, and manage webhooks for event notifications",
    )
    webhook_subparsers = webhook_parser.add_subparsers(dest="webhook_command")

    wh_add_parser = webhook_subparsers.add_parser("add", help="Add a new webhook")
    wh_add_parser.add_argument("url", help="Webhook URL")
    wh_add_parser.add_argument("--event", default="all", choices=["create", "update", "delete", "all"], help="Event type")
    wh_add_parser.add_argument("--secret", help="Optional secret for signing")

    wh_list_parser = webhook_subparsers.add_parser("list", help="List webhooks")
    wh_remove_parser = webhook_subparsers.add_parser("remove", help="Remove a webhook")
    wh_remove_parser.add_argument("webhook_id", type=int, help="Webhook ID")
    wh_test_parser = webhook_subparsers.add_parser("test", help="Test a webhook")
    wh_test_parser.add_argument("webhook_id", type=int, help="Webhook ID")
    restore_parser.add_argument("backup_id", nargs="?", type=int, help="Backup ID to restore")
    restore_parser.add_argument("--file", help="Restore from a specific backup file path")
    sync_parser.add_argument("--push", action="store_true", help="Push to remote")
    sync_parser.add_argument("--pull", action="store_true", help="Pull from remote")
    sync_parser.add_argument("--remote", help="Set remote URL")
    sync_parser.add_argument("--auto", action="store_true", help="Enable auto-sync on changes")
    sync_parser.add_argument("--no-auto", action="store_true", help="Disable auto-sync")
    sync_parser.add_argument("--status", action="store_true", help="Show sync status")
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

            # Handle template
            if args.template:
                from memtext.db import get_template
                template = get_template(args.template)
                if not template:
                    raise ValidationError(f"Template not found: {args.template}")
                # Template provides defaults; args still override
                # For now, template just validates existence and can auto-set type
                # Content from --content or title
                entry_type = template.get("entry_type", args.type)
            else:
                entry_type = args.type

            content = args.content or args.text
            if not args.content:
                print(
                    "Note: Using title as content. Use --content to specify separate content."
                )
            try:
                entry_id = add_entry(
                    args.text, content, entry_type, args.tags, importance=args.importance, parent_tag=args.parent_tag
                )
            try:
                entry_id = add_entry(
                    args.text,
                    content,
                    args.type,
                    args.tags,
                    importance=args.importance,
                    parent_tag=args.parent_tag,
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
            entries = list_entries(args.type, args.limit, parent_tag=args.parent_tag)
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

        elif args.command == "remind":
            try:
                from memtext.db import add_reminder, get_entry

                # Validate entry exists
                entry = get_entry(args.entry_id)
                if not entry:
                    raise ValidationError(f"Entry {args.entry_id} not found")

                reminder_id = add_reminder(args.entry_id, args.at, args.message)
                if reminder_id > 0:
                    print(f"Reminder {reminder_id} set for entry {args.entry_id} at {args.at}")
                    logger.info(f"Added reminder for entry {args.entry_id}")
                else:
                    print("Failed to create reminder")
            except Exception as e:
                raise DatabaseError(f"Reminder creation failed: {e}")

        elif args.command == "reminders":
            try:
                from memtext.db import get_pending_reminders

                pending = get_pending_reminders()
                if not pending:
                    print("No pending reminders.")
                for r in pending:
                    print(f"#{r['id']} [{r['remind_at']}] Entry {r['entry_id']}: {r['title']}")
                    if r['message']:
                        print(f"  Note: {r['message']}")
            except Exception as e:
                raise DatabaseError(f"Failed to get reminders: {e}")

        elif args.command == "reminder-complete":
            try:
                from memtext.db import complete_reminder

                if complete_reminder(args.reminder_id):
                    print(f"Reminder {args.reminder_id} marked complete")
                else:
                    print(f"Reminder {args.reminder_id} not found")
            except Exception as e:
                raise DatabaseError(f"Failed to complete reminder: {e}")

        elif args.command == "reminder-list":
            try:
                from memtext.db import get_all_reminders

                reminders = get_all_reminders(args.entry_id)
                if not reminders:
                    print("No reminders found.")
                for r in reminders:
                    status = "✓" if r['completed'] else "○"
                    print(f"{status} #{r['id']} Entry {r['entry_id']} at {r['remind_at']}: {r.get('message', '')}")
            except Exception as e:
                raise DatabaseError(f"Failed to list reminders: {e}")

        elif args.command == "encrypt":
            try:
                import getpass
                from memtext.encryption import encrypt_entry

                password = getpass.getpass("Encryption password: ")
                if not password:
                    raise ValidationError("Password cannot be empty")
                confirm = getpass.getpass("Confirm password: ")
                if password != confirm:
                    raise ValidationError("Passwords do not match")

                if encrypt_entry(args.entry_id, password):
                    print(f"Entry {args.entry_id} encrypted successfully")
                    logger.info(f"Encrypted entry {args.entry_id}")
                else:
                    print("Encryption failed. Check that entry exists.")
            except Exception as e:
                raise DatabaseError(f"Encryption failed: {e}")

        elif args.command == "decrypt":
            try:
                import getpass
                from memtext.encryption import decrypt_entry, is_entry_encrypted
                from memtext.db import update_entry, get_entry

                if not is_entry_encrypted(args.entry_id):
                    print(f"Entry {args.entry_id} is not encrypted")
                    return

                password = getpass.getpass("Decryption password: ")
                if not password:
                    raise ValidationError("Password cannot be empty")

                content = decrypt_entry(args.entry_id, password)
                if content is None:
                    print("Decryption failed. Wrong password or corrupted data.")
                    return

                # Restore plaintext content and mark as not encrypted
                conn = __import__('sqlite3').connect(get_db_path())
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE context_entries SET content = ?, is_encrypted = 0, encrypted_content = NULL WHERE id = ?",
                    (content, args.entry_id)
                )
                conn.commit()
                conn.close()
                print(f"Entry {args.entry_id} decrypted successfully")
                logger.info(f"Decrypted entry {args.entry_id}")
            except Exception as e:
                raise DatabaseError(f"Decryption failed: {e}")

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

        elif args.command == "template":
            if not args.template_command:
                template_parser.print_help()
                return 0

            from memtext.db import create_template, get_template, list_templates

            if args.template_command == "add":
                fields_schema = {}
                if args.fields:
                    try:
                        import json
                        fields_schema = json.loads(args.fields)
                    except json.JSONDecodeError:
                        raise ValidationError("Invalid JSON for --fields")

                success = create_template(
                    args.name,
                    args.description or f"Template for {args.name}",
                    args.type,
                    fields_schema,
                )
                if success:
                    print(f"Template '{args.name}' created")
                else:
                    print("Failed to create template")

            elif args.template_command == "list":
                templates = list_templates()
                if not templates:
                    print("No templates found. Use 'memtext template add' to create one.")
                for t in templates:
                    print(f"[{t['entry_type']}] {t['name']} - {t['description']}")

            elif args.template_command == "show":
                tmpl = get_template(args.name)
                if tmpl:
                    print(f"Template: {tmpl['name']}")
                    print(f"Type: {tmpl['entry_type']}")
                    print(f"Description: {tmpl['description']}")
                    print(f"Fields: {tmpl['fields']}")
                else:
                    print(f"Template '{args.name}' not found")

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

        elif args.command == "history":
            try:
                from memtext.db import get_entry_history, get_entry

                entry = get_entry(args.entry_id)
                if not entry:
                    print(f"Entry {args.entry_id} not found")
                else:
                    print(f"History for: {entry['title']}")
                    print("-" * 40)
                    history = get_entry_history(args.entry_id)
                    if not history:
                        print("No history available.")
                    for h in history:
                        print(f"[{h['changed_at']}] {h['field_name']}: {h['old_value']} → {h['new_value']}")
            except Exception as e:
                raise DatabaseError(f"Failed to get history: {e}")

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

        elif args.command == "graph":
            try:
                from memtext.graph import generate_graph_visualization

                output = Path(args.output)
                path = generate_graph_visualization(output, limit=args.limit)
                print(f"Graph visualization saved to {path}")
                logger.info(f"Generated graph visualization at {path}")
            except Exception as e:
                raise DatabaseError(f"Graph generation failed: {e}")

        elif args.command == "sync":
            try:
                from memtext.sync import (
                    git_push, git_pull, set_remote, enable_auto_sync,
                    disable_auto_sync, load_sync_config, init_git_repo
                )

                if args.remote:
                    set_remote(args.remote)
                    print(f"Remote URL set to {args.remote}")

                if args.auto:
                    enable_auto_sync()
                    print("Auto-sync enabled")

                if args.no_auto:
                    disable_auto_sync()
                    print("Auto-sync disabled")

                if args.status:
                    config = load_sync_config()
                    print(f"Remote: {config.get('remote_url') or 'Not set'}")
                    print(f"Auto-sync: {'enabled' if config.get('auto_sync') else 'disabled'}")
                    print(f"Last sync: {config.get('last_sync') or 'Never'}")

                if args.push:
                    init_git_repo()
                    success, msg = git_push()
                    print(msg)
                    if not success:
                        raise DatabaseError(msg)

                if args.pull:
                    init_git_repo()
                    success, msg = git_pull()
                    print(msg)
                    if not success:
                        raise DatabaseError(msg)

                # If no action specified, show status
                if not any([args.push, args.pull, args.remote, args.auto, args.no_auto, args.status]):
                    sync_parser.print_help()

            except Exception as e:
                raise DatabaseError(f"Sync failed: {e}")

        elif args.command == "backup":
            try:
                from memtext.db import create_backup

                backup_id = create_backup(args.type)
                if backup_id:
                print(f"Backup created: ID {backup_id}")
                logger.info(f"Created backup {backup_id}")
            except Exception as e:
                raise DatabaseError(f"Backup failed: {e}")

        elif args.command == "webhook":
            from memtext.db import add_webhook, list_webhooks, remove_webhook, trigger_webhook

            if not args.webhook_command:
                webhook_parser.print_help()
                return 0

            if args.webhook_command == "add":
                webhook_id = add_webhook(args.url, args.event, args.secret)
                if webhook_id > 0:
                    print(f"Webhook {webhook_id} added for {args.event} events on {args.url}")
                    logger.info(f"Added webhook {webhook_id}")
                else:
                    print("Failed to add webhook")

            elif args.webhook_command == "list":
                hooks = list_webhooks()
                if not hooks:
                    print("No webhooks configured.")
                for h in hooks:
                    print(f"#{h['id']} [{h['event']}] {h['url']} (active={h['active']})")

            elif args.webhook_command == "remove":
                if remove_webhook(args.webhook_id):
                    print(f"Webhook {args.webhook_id} removed")
                else:
                    print(f"Webhook {args.webhook_id} not found")

            elif args.webhook_command == "test":
                # Trigger a test webhook call
                test_data = {
                    "id": 0,
                    "title": "Test Webhook",
                    "entry_type": "test",
                }
                try:
                    # Temporarily enable all webhooks including inactive for test?
                    # For now just call trigger_webhook which only triggers active ones
                    trigger_webhook("test", test_data)
                    print(f"Test event sent to webhook {args.webhook_id}")
                except Exception as e:
                    print(f"Test failed: {e}")

        elif args.command == "backup-list":
            try:
                from memtext.db import list_backups

                backups = list_backups()
                if not backups:
                    print("No backups found.")
                for b in backups:
                    print(f"#{b['id']} [{b['backup_type']}] {b['backup_path']}")
                    print(f"  Size: {b['size_bytes']} bytes, Entries: {b['entry_count']}, Created: {b['created_at']}")
            except Exception as e:
                raise DatabaseError(f"Failed to list backups: {e}")

        elif args.command == "restore":
            try:
                from memtext.db import restore_backup
                from pathlib import Path

                success = False
                if args.backup_id:
                    success = restore_backup(backup_id=args.backup_id)
                elif args.file:
                    success = restore_backup(backup_path=Path(args.file))
                else:
                    print("Specify a backup ID or --file <path>")
                    return 0

                if success:
                    print("Restore completed successfully")
                    logger.info("Database restored from backup")
                else:
                    print("Restore failed. Check backup exists and is valid.")
            except Exception as e:
                raise DatabaseError(f"Restore failed: {e}")

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
