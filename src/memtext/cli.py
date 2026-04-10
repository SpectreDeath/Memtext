import argparse
import sys
from pathlib import Path

from memtext.core import init_context, save_context, query_context, add_log
from memtext.db import (
    init_db,
    add_entry,
    list_entries,
    query_entries,
    register_project,
    list_projects,
    scan_for_projects,
)


def main():
    parser = argparse.ArgumentParser(prog="memtext")
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
        choices=["decision", "pattern", "note", "error", "convention"],
    )
    add_parser.add_argument("--tags", nargs="*", help="Tags")
    add_parser.add_argument("--importance", type=int, default=1)

    list_parser = subparsers.add_parser("list", help="List entries from SQLite")
    list_parser.add_argument("--type", help="Filter by type")
    list_parser.add_argument("--limit", type=int, default=10)

    projects_parser = subparsers.add_parser("projects", help="List projects")
    projects_parser.add_argument(
        "--scan", action="store_true", help="Scan for projects"
    )

    migrate_parser = subparsers.add_parser("migrate", help="Migrate v0.1.x to v0.2.0")

    args = parser.parse_args()

    if args.command == "init":
        init_context()
        init_db()
    elif args.command == "save":
        save_context(args.text, args.tags)
    elif args.command == "query":
        results = query_context(args.text, args.limit)
        for r in results:
            print(f"[{r['file']}] {r['line']}")
            print(f"  {r['content'][:200]}")
            print()
    elif args.command == "log":
        add_log(args.text, args.session)
    elif args.command == "add":
        content = args.content or args.text
        entry_id = add_entry(
            args.text, content, args.type, args.tags, importance=args.importance
        )
        print(f"Saved entry {entry_id}")
    elif args.command == "list":
        entries = list_entries(args.type, args.limit)
        for e in entries:
            print(f"[{e['id']}] {e['title']} ({e['entry_type']})")
    elif args.command == "projects":
        if args.scan:
            found = scan_for_projects()
            for p in found:
                register_project(p)
            print(f"Found {len(found)} projects")
        for p in list_projects():
            print(f"{p['path']} - {p['name']}")
    elif args.command == "migrate":
        from memtext.core import get_context_dir

        ctx_dir = get_context_dir()
        decisions_file = ctx_dir / "decisions.md"
        if not decisions_file.exists():
            print("No old format found")
            return
        content = decisions_file.read_text()
        lines = content.split("\n")
        count = 0
        for line in lines:
            if line.startswith("- "):
                add_entry(line[2:], line[2:], "decision")
                count += 1
        print(f"Migrated {count} decisions to SQLite")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
