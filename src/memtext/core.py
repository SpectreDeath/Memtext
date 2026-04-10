import subprocess
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

    try:
        result = subprocess.run(
            ["grep", "-r", "-i", "--include=*.md", query, str(ctx_dir)],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        result = subprocess.run(
            ["rg", "-i", query, str(ctx_dir), "--type", "md"],
            capture_output=True,
            text=True,
        )

    results = []
    for line in result.stdout.split("\n")[:limit]:
        if ":" in line:
            parts = line.split(":", 1)
            file_path = Path(parts[0]).name
            content = parts[1][:200]
            results.append({"file": file_path, "line": content, "content": content})

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
