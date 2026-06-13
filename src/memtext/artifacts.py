"""Scratchpad and memory artifact helpers."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .core import get_context_dir

ARTIFACT_PATTERN = re.compile(
    r"<artifact\s+name=(?P<quote>['\"])(?P<name>[^'\"]+)(?P=quote)"
    r"(?:\s+scope=(?P=quote)(?P<scope>[^'\"]+)(?P=quote))?>"
    r"(?P<content>.*?)</artifact>",
    re.DOTALL,
)


def get_scratchpad_path() -> Path:
    return get_context_dir() / "scratchpad.tmp"


def get_artifacts_dir() -> Path:
    return get_context_dir() / "artifacts"


def write_scratchpad(content: str, append: bool = False) -> str:
    scratchpad_path = get_scratchpad_path()
    scratchpad_path.parent.mkdir(exist_ok=True)
    mode = "a" if append else "w"
    with scratchpad_path.open(mode, encoding="utf-8") as file:
        file.write(content.rstrip() + "\n")
    return "Scratchpad updated."


def read_scratchpad() -> str:
    scratchpad_path = get_scratchpad_path()
    if not scratchpad_path.exists():
        return "Scratchpad is empty."
    content = scratchpad_path.read_text(encoding="utf-8").strip()
    return content or "Scratchpad is empty."


def clear_scratchpad() -> str:
    scratchpad_path = get_scratchpad_path()
    if scratchpad_path.exists():
        scratchpad_path.unlink()
    return "Scratchpad cleared."


def _safe_slug(value: str, fallback: str) -> str:
    slug = value.strip().lower()
    slug = re.sub(r"[^a-z0-9._-]+", "_", slug)
    slug = slug.strip("._-")
    return slug or fallback


def _artifact_filename(artifact_name: str, created: datetime) -> Path:
    timestamp = created.strftime("%Y%m%d_%H%M%S")
    slug = _safe_slug(artifact_name, "artifact")
    return Path(f"artifact_{timestamp}_{slug}.md")


def _unique_artifact_path(artifacts_dir: Path, artifact_name: str, created: datetime) -> Path:
    artifact_file = artifacts_dir / _artifact_filename(artifact_name, created)
    if not artifact_file.exists():
        return artifact_file

    counter = 1
    timestamp = created.strftime("%Y%m%d_%H%M%S")
    slug = _safe_slug(artifact_name, "artifact")
    while True:
        artifact_file = artifacts_dir / f"artifact_{timestamp}_{slug}_{counter}.md"
        if not artifact_file.exists():
            return artifact_file
        counter += 1


def _artifact_content(
    artifact_name: str, scope: str, scratch_content: str, created: datetime
) -> str:
    return f"""---
type: memory_artifact
created: {created.isoformat()}
scope: {scope}
name: {artifact_name}
---

# Memory Artifact: {artifact_name}

## Intent / Process History
Captured scratchpad execution trace for analytical transparency.

## Contents
```text
{scratch_content}

```
"""


def save_scratchpad_artifact(
    artifact_name: str,
    scope: str = "general",
    clear: bool = True,
) -> str:
    scratchpad_path = get_scratchpad_path()
    if not scratchpad_path.exists():
        return "Error: No scratchpad content found to convert into an artifact."

    scratch_content = scratchpad_path.read_text(encoding="utf-8").strip()
    if not scratch_content:
        return "Error: Scratchpad is blank."

    artifacts_dir = get_artifacts_dir()
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    created = datetime.now()
    artifact_file = _unique_artifact_path(artifacts_dir, artifact_name, created)

    artifact_file.write_text(
        _artifact_content(artifact_name, scope, scratch_content, created),
        encoding="utf-8",
    )

    if clear:
        scratchpad_path.unlink()

    return f"Saved scratchpad state as memory artifact: {artifact_file.name}"


def post_llm_artifact_hook(agent_response: str, clear: bool = True) -> str:
    match = ARTIFACT_PATTERN.search(agent_response)
    if not match:
        return agent_response

    content = match.group("content").strip()
    if not content:
        return agent_response

    artifacts_dir = get_artifacts_dir()
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    created = datetime.now()
    artifact_file = _unique_artifact_path(artifacts_dir, match.group("name"), created)
    artifact_file.write_text(
        _artifact_content(
            match.group("name"),
            match.group("scope") or "general",
            content,
            created,
        ),
        encoding="utf-8",
    )

    status = f"Saved inline directive as memory artifact: {artifact_file.name}"
    return ARTIFACT_PATTERN.sub(f"\n[System Hook: {status}]\n", agent_response, count=1)
