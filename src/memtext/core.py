import re
from datetime import datetime
from pathlib import Path

from .repositories.database import EntryManager


def get_context_dir() -> Path:
    return Path.cwd() / ".context"


def init_context():
    ctx_dir = get_context_dir()
    ctx_dir.mkdir(exist_ok=True)

    (ctx_dir / "session-logs").mkdir(exist_ok=True)
    (ctx_dir / "artifacts").mkdir(exist_ok=True)

    skills_dir = ctx_dir / "skills"
    skills_dir.mkdir(exist_ok=True)

    skills_index = ctx_dir / "skills.md"
    if not skills_index.exists():
        skills_index.write_text("""# Available Project Skills

*Skills are ordered by frequency of use. Each skill is a Markdown file in `.context/skills/`.*

<!-- Skills index - auto-maintained by memtext add-skill -->
""")

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

    (ctx_dir / ".gitignore").write_text(
        """# Memtext context
*
!.gitignore
"""
    )

    root_gitignore = Path.cwd() / ".gitignore"
    if root_gitignore.exists():
        content = root_gitignore.read_text()
        if ".context/" not in content:
            with open(root_gitignore, "a") as f:
                f.write("\n# Memtext context\n.context/\n")
    else:
        print("Tip: Create a .gitignore with '.context/' to exclude from Git")

    print(f"Initialized .context/ at {ctx_dir}")
    print(
        "Files created: identity.md, decisions.md, skills.md, skills/, session-logs/, artifacts/, .gitignore"
    )


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
    try:
        regex = re.compile(query, re.IGNORECASE)
    except re.error as e:
        print(f"Invalid regex query: {e}")
        return []

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
    ctx_dir = get_context_dir()
    if not ctx_dir.exists():
        print("No .context directory to migrate.")
        return 0

    entry_mgr = EntryManager()
    count = 0

    # 1. Migrate decisions
    decisions_file = ctx_dir / "decisions.md"
    if decisions_file.exists():
        content = decisions_file.read_text()
        for line in content.split("\n"):
            if line.startswith("- "):
                title = line[2:].strip()
                if entry_mgr.add(title, title, "decision") != -1:
                    count += 1

    # 2. Migrate logs
    logs_dir = ctx_dir / "session-logs"
    if logs_dir.exists():
        for log_file in logs_dir.glob("*.md"):
            content = log_file.read_text()
            current_title = f"Log {log_file.stem}"
            current_body = []
            for line in content.split("\n"):
                if line.startswith("### "):
                    if current_body:
                        if entry_mgr.add(current_title, "\n".join(current_body), "note") != -1:
                            count += 1
                    current_title = line[4:].strip()
                    current_body = []
                elif not line.startswith("#"):
                    current_body.append(line)

            if current_body:
                if entry_mgr.add(current_title, "\n".join(current_body), "note") != -1:
                    count += 1

    # 3. Migrate identity
    identity_file = ctx_dir / "identity.md"
    if identity_file.exists():
        content = identity_file.read_text()
        if entry_mgr.add("Project Identity", content, "convention") != -1:
            count += 1

    return count


SYNTHESIS_PROMPT = """
Analyze the following raw session logs and extract key "Memories".
A Memory is a distilled, high-value piece of information such as a decision, a discovered pattern, or a critical project constraint.

Format your output as a list of memories:
- [Memory Title]: [Memory Content] (@tags: tag1, tag2)

RAW LOGS:
{text}
"""


def synthesize_memories(source_text: str = None, recent_only: bool = True):
    """
    Extract high-value memories from raw logs.
    If source_text is provided, it distills that text.
    Otherwise, it scans recent session logs for '@memory' markers.

    Returns:
        int: Count of new memories created
    """
    entry_mgr = EntryManager()
    count = 0

    if source_text:
        match = re.match(r"(.*?): (.*?) \(@tags: (.*?)\)", source_text)
        if match:
            title, content, tags_str = match.groups()
            tags = [t.strip() for t in tags_str.split(",")]
            entry_id = entry_mgr.add(title, content, "memory", tags=tags)
            if entry_id > 0:
                count = 1
        else:
            entry_id = entry_mgr.add("Synthesized Memory", source_text, "memory")
            if entry_id > 0:
                count = 1
        return count

    ctx_dir = get_context_dir()
    logs_dir = ctx_dir / "session-logs"
    if not logs_dir.exists():
        return 0

    log_files = sorted(logs_dir.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)
    if recent_only:
        log_files = log_files[:2]

    for log_file in log_files:
        content = log_file.read_text()
        pattern = re.compile(r"@memory:\s*(.*?)(?=\n|@|$)", re.IGNORECASE | re.DOTALL)
        matches = pattern.findall(content)
        for match in matches:
            text = match.strip()
            title = text.split("\n")[0][:50]
            memory_title = f"Auto-Memory: {title}"
            if entry_mgr.add(memory_title, text, "memory") != -1:
                count += 1

    return count


def generate_summary(memories: list) -> str:
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


def add_skill(name: str, description: str, content: str = None) -> int:
    ctx_dir = get_context_dir()
    if not ctx_dir.exists():
        init_context()

    skills_dir = ctx_dir / "skills"
    skills_dir.mkdir(exist_ok=True)

    skill_file = skills_dir / f"{name}.md"
    if skill_file.exists():
        return -1

    if content is None:
        content = f"""# {name}

## Description
{description}

## Prerequisites
- Ensure you are in the project root directory

## Steps
1.
2.
3.

## Expected Output
> Add expected output here

## Notes
<!-- Add any additional notes here -->
"""

    skill_file.write_text(content)

    skills_index = ctx_dir / "skills.md"
    with open(skills_index, "a") as f:
        f.write(f"\n* **{name}**: {description}")

    return 0


def view_skill(name: str) -> str:
    ctx_dir = get_context_dir()
    if not ctx_dir.exists():
        raise FileNotFoundError("No .context/ directory found. Run 'memtext init' first.")

    skill_file = ctx_dir / "skills" / f"{name}.md"
    if not skill_file.exists():
        return None

    return skill_file.read_text()


def distill_logs(date_str: str = None, use_llm: bool = False, model: str = "llama3") -> int:
    ctx_dir = get_context_dir()
    if not ctx_dir.exists():
        return 0

    logs_dir = ctx_dir / "session-logs"
    if not logs_dir.exists():
        return 0

    log_files = sorted(logs_dir.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)

    if date_str:
        log_files = [f for f in log_files if date_str in f.name]

    if not log_files:
        return 0

    count = 0
    for log_file in log_files:
        if use_llm:
            try:
                from memtext.llm import synthesize_with_local

                content = log_file.read_text()
                result = synthesize_with_local(content, model)
                if result:
                    existing = log_file.read_text()
                    distilled_section = f"\n\n## Distilled Takeaways: {log_file.stem}\n\n"
                    for mem in result.memories:
                        distilled_section += f"* **Problem:** {mem.get('content', '')[:100]}\n"
                    log_file.write_text(existing + distilled_section)
                    count += 1
            except Exception:
                pass
        else:
            content = log_file.read_text()
            distilled = []
            lines = content.split("\n")
            for line in lines:
                if line.strip().startswith(("##", "###")):
                    if distilled:
                        distilled.append("")
                    distilled.append(f"* **{line.strip().lstrip('# ')}**: See original log entry")
                    continue
                if "@memory:" in line:
                    text = line.split("@memory:")[1].strip()
                    distilled.append(f"* **Memory**: {text}")

            if distilled:
                existing = log_file.read_text()
                log_file.write_text(
                    existing + "\n\n## Distilled Takeaways\n" + "\n".join(distilled)
                )
                count += 1

    return count


def compile_context(mode: str = "active") -> str:
    ctx_dir = get_context_dir()
    if not ctx_dir.exists():
        init_context()

    parts = []

    identity_file = ctx_dir / "identity.md"
    if identity_file.exists():
        parts.append(identity_file.read_text())

    decisions_file = ctx_dir / "decisions.md"
    if decisions_file.exists():
        parts.append(decisions_file.read_text())

    skills_index = ctx_dir / "skills.md"
    if skills_index.exists():
        skills_content = skills_index.read_text()
        skills_content = skills_content.replace(
            "<!-- Skills index - auto-maintained by memtext add-skill -->\n", ""
        )
        parts.append(skills_content)

    if mode == "active":
        logs_dir = ctx_dir / "session-logs"
        if logs_dir.exists():
            log_files = sorted(
                logs_dir.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True
            )[:3]
            for log_file in log_files:
                content = log_file.read_text()
                if "## Distilled Takeaways" in content:
                    distilled_match = re.search(
                        r"## Distilled Takeaways.*?(?=\n## |\Z)", content, re.DOTALL
                    )
                    if distilled_match:
                        parts.append(distilled_match.group(0))
                else:
                    lines = content.split("\n")
                    key_lines = [
                        ln for ln in lines if "@memory:" in ln or ln.strip().startswith(("*", "-"))
                    ]
                    if key_lines:
                        parts.append(
                            f"\n\n## Recent: {log_file.stem}\n" + "\n".join(key_lines[:20])
                        )

    return "\n".join(parts)


def deprecate_entry(entry_type: str, name: str, superseded_by: str = None) -> bool:
    ctx_dir = get_context_dir()
    if not ctx_dir.exists():
        return False

    # First try database entries
    try:
        from memtext.db import get_entry_manager
        em = get_entry_manager()
        if entry_type == "entry":
            # Try to find by ID first
            if name.isdigit():
                entry_id = int(name)
                entry = em.get(entry_id) if hasattr(em, 'get') else None
            else:
                # Search by title
                results = em.search(name, limit=1) if hasattr(em, 'search') else []
                entry = results[0] if results else None
            if entry:
                return em.update(entry['id'], trust_score=0.0) if hasattr(em, 'update') else False
    except Exception:
        pass

    # Fallback to markdown files
    target_file = None
    if (ctx_dir / f"{name}.md").exists():
        target_file = ctx_dir / f"{name}.md"
    elif (ctx_dir / name).exists():
        target_file = ctx_dir / name

    if not target_file or not target_file.exists():
        return False

    content = target_file.read_text()
    frontmatter = """---
status: deprecated
"""
    if superseded_by:
        frontmatter += f"superseded_by: {superseded_by}\n"
    frontmatter += f"date: {datetime.now().strftime('%Y-%m-%d')}\n---\n\n"

    if content.startswith("---"):
        end_frontmatter = content.find("---", 3)
        if end_frontmatter > 0:
            content = content[end_frontmatter + 3 :]
    target_file.write_text(frontmatter + content)

    return True


def prune_deprecated():
    ctx_dir = get_context_dir()
    if not ctx_dir.exists():
        return 0

    skills_index = ctx_dir / "skills.md"
    if skills_index.exists():
        content = skills_index.read_text()
        lines = content.split("\n")
        filtered = [ln for ln in lines if "status: deprecated" not in ln.lower()]
        skills_index.write_text("\n".join(filtered))

    skills_dir = ctx_dir / "skills"
    if skills_dir.exists():
        for skill_file in skills_dir.glob("*.md"):
            content = skill_file.read_text()
            if content.startswith("---") and "status: deprecated" in content.split("---")[1]:
                skills_index = ctx_dir / "skills.md"
                index_content = skills_index.read_text()
                skill_name = skill_file.stem
                index_content = re.sub(rf"\n\* \*\*{skill_name}\*\*.*", "", index_content)
                skills_index.write_text(index_content)

    return 0
