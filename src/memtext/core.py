import re
from datetime import datetime
from pathlib import Path


def get_context_dir() -> Path:
    return Path.cwd() / ".context"


def init_context():
    ctx_dir = get_context_dir()
    ctx_dir.mkdir(exist_ok=True)

    (ctx_dir / "session-logs").mkdir(exist_ok=True)

    if not (ctx_dir / "identity.md").exists():
        (ctx_dir / "identity.md").write_text("""# Project Identity

## Purpose
Brief description of the project.

## Stack
- Language: 
- Framework: 
- Database: 

## Key Components
- `src/` - Core source code
- `tests/` - Test files

## Conventions
- Code style: 
- Testing: 
- Documentation: 
""")

    if not (ctx_dir / "decisions.md").exists():
        (ctx_dir / "decisions.md").write_text(
            """# Architecture Decisions

## """
            + datetime.now().strftime("%Y-%m-%d")
            + """ - Initial Setup
- Initialized context storage with memtext
"""
        )

    (ctx_dir / ".gitignore").write_text("""# Memtext context
.context/
""")

    root_gitignore = Path.cwd() / ".gitignore"
    if root_gitignore.exists():
        content = root_gitignore.read_text()
        if ".context/" not in content:
            with open(root_gitignore, "a") as f:
                f.write("\n# Memtext context\n.context/\n")
            print(f"Added .context/ to {root_gitignore}")
    else:
        print("Tip: Create a .gitignore with '.context/' to exclude from Git")

    print(f"Initialized .context/ at {ctx_dir}")
    print("Files created: identity.md, decisions.md, session-logs/, .gitignore")


def save_context(text: str, tags: list = None):
    ctx_dir = get_context_dir()
    if not ctx_dir.exists():
        init_context()

    decision_file = ctx_dir / "decisions.md"
    with open(decision_file, "a") as f:
        f.write(f"\n## {datetime.now().strftime('%Y-%m-%d')}")
        if tags:
            f.write(f" [{', '.join(tags)}]")
        f.write(f"\n- {text}\n")

    print(f"Saved to {decision_file}")


def query_context(query: str, limit: int = 5):
    ctx_dir = get_context_dir()
    if not ctx_dir.exists():
        print("No .context/ found. Run 'memtext init' first.")
        return []

    results = []
    regex = re.compile(query, re.IGNORECASE)

    for file_path in ctx_dir.rglob("*.md"):
        try:
            content = file_path.read_text(errors="ignore")
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if regex.search(line):
                    results.append(
                        {
                            "file": file_path.name,
                            "line": line.strip()[:200],
                            "content": line.strip(),
                        }
                    )
                    if len(results) >= limit:
                        return results
        except Exception as e:
            print(f"Error reading {file_path}: {e}")

    return results


def add_log(text: str, session: str = None):
    ctx_dir = get_context_dir()
    if not ctx_dir.exists():
        init_context()

    date = datetime.now().strftime("%Y-%m-%d")
    log_file = ctx_dir / "session-logs" / f"{date}.md"

    session_name = session or datetime.now().strftime("%H:%M")

    if log_file.exists():
        with open(log_file, "a") as f:
            f.write(f"\n### {session_name}\n{text}\n")
    else:
        with open(log_file, "w") as f:
            f.write(f"# Session Log {date}\n\n### {session_name}\n{text}\n")

    print(f"Logged to {log_file}")


def migrate_to_db():
    """Migrate filesystem context to SQLite database."""
    from memtext.db import add_entry, init_db

    ctx_dir = get_context_dir()
    if not ctx_dir.exists():
        print("No .context directory to migrate.")
        return 0

    init_db()
    count = 0

    # 1. Migrate decisions
    decisions_file = ctx_dir / "decisions.md"
    if decisions_file.exists():
        content = decisions_file.read_text()
        for line in content.split("\n"):
            if line.startswith("- "):
                title = line[2:].strip()
                if add_entry(title, title, "decision") != -1:
                    count += 1

    # 2. Migrate logs
    logs_dir = ctx_dir / "session-logs"
    if logs_dir.exists():
        for log_file in logs_dir.glob("*.md"):
            content = log_file.read_text()
            # Simple heuristic: treat lines starting with ### as titles
            current_title = f"Log {log_file.stem}"
            current_body = []
            for line in content.split("\n"):
                if line.startswith("### "):
                    if current_body:
                        # Save previous section
                        if (
                            add_entry(current_title, "\n".join(current_body), "note")
                            != -1
                        ):
                            count += 1
                    current_title = line[4:].strip()
                    current_body = []
                elif not line.startswith("#"):
                    current_body.append(line)

            if current_body:
                if add_entry(current_title, "\n".join(current_body), "note") != -1:
                    count += 1

    # 3. Migrate identity
    identity_file = ctx_dir / "identity.md"
    if identity_file.exists():
        content = identity_file.read_text()
        if add_entry("Project Identity", content, "convention") != -1:
            count += 1

    return count
