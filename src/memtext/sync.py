"""Git sync utilities for MemText.

Provides automatic synchronization of .context/ directory with a git remote.
Uses GitPython for pythonic git operations.
"""

import json
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

try:
    from git import Repo, InvalidGitRepositoryError, GitCommandError

    HAS_GITPYTHON = True
except ImportError:
    HAS_GITPYTHON = False

from memtext.db import get_db_path


def get_sync_config_path() -> Path:
    """Get path to sync configuration file."""
    return Path.cwd() / ".context" / "sync.conf"


def load_sync_config() -> Dict[str, Any]:
    """Load sync configuration."""
    config_path = get_sync_config_path()
    if not config_path.exists():
        return {
            "remote_url": None,
            "branch": "main",
            "auto_sync": False,
            "last_sync": None,
        }
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {
            "remote_url": None,
            "branch": "main",
            "auto_sync": False,
            "last_sync": None,
        }


def save_sync_config(config: Dict[str, Any]) -> None:
    """Save sync configuration."""
    config_path = get_sync_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


def init_git_repo() -> Optional[Path]:
    """Initialize git repo in .context/ if not already."""
    ctx_dir = Path.cwd() / ".context"
    if not ctx_dir.exists():
        return None

    try:
        repo = Repo.init(ctx_dir)
        gitignore = ctx_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("# Memtext context files\n*.db\n*.log\n")
        return ctx_dir
    except Exception as e:
        print(f"Failed to initialize git repo: {e}")
        return None


def get_repo() -> Optional[Any]:
    """Get git Repo object for .context/."""
    ctx_dir = Path.cwd() / ".context"
    if not ctx_dir.exists():
        return None
    try:
        return Repo(ctx_dir)
    except InvalidGitRepositoryError:
        return None


def git_add_context() -> bool:
    """Stage all changes in .context/."""
    repo = get_repo()
    if not repo:
        return False
    try:
        repo.index.add(["."])
        return True
    except GitCommandError:
        return False


def git_commit(message: str) -> bool:
    """Commit staged changes."""
    repo = get_repo()
    if not repo:
        return False
    try:
        # Only commit if there are staged changes
        if repo.index.diff("HEAD"):
            repo.index.commit(message)
            return True
        return True  # Nothing to commit, not an error
    except GitCommandError:
        return False


def git_push() -> tuple[bool, str]:
    """Push to remote."""
    config = load_sync_config()
    remote_url = config.get("remote_url")
    if not remote_url:
        return False, "No remote URL configured. Use 'memtext sync --remote <url>'"

    repo = get_repo()
    if not repo:
        return False, "No git repository initialized"

    try:
        # Add remote if not exists
        if remote_url not in [r.url for r in repo.remotes]:
            repo.create_remote("origin", remote_url)
        origin = repo.remote("origin")
        origin.push()
        config["last_sync"] = "pushed"
        save_sync_config(config)
        return True, "Pushed successfully"
    except GitCommandError as e:
        return False, f"Push failed: {e}"


def git_pull() -> tuple[bool, str]:
    """Pull from remote."""
    config = load_sync_config()
    remote_url = config.get("remote_url")
    if not remote_url:
        return False, "No remote URL configured"

    repo = get_repo()
    if not repo:
        return False, "No git repository initialized"

    try:
        if remote_url not in [r.url for r in repo.remotes]:
            repo.create_remote("origin", remote_url)
        origin = repo.remote("origin")
        origin.pull()
        config["last_sync"] = "pulled"
        save_sync_config(config)
        return True, "Pulled successfully"
    except GitCommandError as e:
        return False, f"Pull failed: {e}"


def sync(commit_message: str = "Update via memtext sync") -> None:
    """Auto-sync: add, commit, push if configured."""
    config = load_sync_config()
    if not config.get("auto_sync"):
        return

    repo = get_repo()
    if not repo:
        init_git_repo()

    git_add_context()
    git_commit(commit_message)
    if config.get("remote_url"):
        git_push()


def set_remote(url: str) -> None:
    """Set the git remote URL."""
    config = load_sync_config()
    config["remote_url"] = url
    save_sync_config(config)


def enable_auto_sync() -> None:
    """Enable automatic sync on save."""
    config = load_sync_config()
    config["auto_sync"] = True
    save_sync_config(config)


def disable_auto_sync() -> None:
    """Disable automatic sync on save."""
    config = load_sync_config()
    config["auto_sync"] = False
    save_sync_config(config)
