"""Shared helpers for jobOS-bot Claude Code hooks (stdlib only)."""

from __future__ import annotations

import json
import os
import shutil
import sys
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import Any

# Paths no agent may read or edit (privacy).
PROTECTED_EXACT: frozenset[str] = frozenset(
    {".env", "config/profile.yaml", "config/cv_base.md"},
)
PROTECTED_DIRS: tuple[str, ...] = ("data",)
PROTECTED_GLOBS: tuple[str, ...] = ("config/*.pdf",)

# Production code owned by Antigravity: Claude Code never edits it.
PRODUCTION_EXACT: frozenset[str] = frozenset({"cli.py"})
PRODUCTION_DIRS: tuple[str, ...] = ("src",)


def read_payload() -> dict[str, Any]:
    """Read the hook JSON payload from stdin; empty or invalid input yields {}."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def project_root(payload: dict[str, Any]) -> Path:
    """Resolve the repository root.

    Order: $JOBOS_HOOK_ROOT (test override) -> location of this file (<root>/.claude/hooks/)
    -> $CLAUDE_PROJECT_DIR -> payload cwd -> os.getcwd(). The file location wins over the
    variable because $CLAUDE_PROJECT_DIR can point elsewhere (e.g. after /cd).
    """
    override = os.environ.get("JOBOS_HOOK_ROOT")
    if override:
        return Path(override).resolve()
    from_file = Path(__file__).resolve().parents[2]
    if (from_file / ".claude" / "hooks").is_dir() and (from_file / ".git").exists():
        return from_file
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_dir:
        return Path(env_dir).resolve()
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd:
        return Path(cwd).resolve()
    return Path.cwd().resolve()


def relative_to_root(file_path: str, root: Path) -> str | None:
    """Return the POSIX path of file_path relative to root, or None if it lies outside."""
    candidate = Path(file_path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        rel = resolved.relative_to(root)
    except ValueError:
        return None
    return PurePosixPath(rel.as_posix()).as_posix()


def _in_dir(rel: str, directory: str) -> bool:
    return rel == directory or rel.startswith(directory + "/")


def protected_reason(rel: str) -> str | None:
    """Explain why a repo-relative path is protected, or None if it is not."""
    if rel in PROTECTED_EXACT:
        return f"'{rel}' es una ruta protegida (privacidad)"
    for directory in PROTECTED_DIRS:
        if _in_dir(rel, directory):
            return f"'{rel}' está dentro de '{directory}/', ruta protegida (privacidad)"
    for pattern in PROTECTED_GLOBS:
        if fnmatch(rel.lower(), pattern) and rel.count("/") == pattern.count("/"):
            return f"'{rel}' coincide con '{pattern}', ruta protegida (privacidad)"
    return None


def production_reason(rel: str) -> str | None:
    """Explain why a repo-relative path is production code owned by Antigravity."""
    if rel in PRODUCTION_EXACT:
        return f"'{rel}' es código de producción (dueño: Antigravity)"
    for directory in PRODUCTION_DIRS:
        if _in_dir(rel, directory):
            return f"'{rel}' está en '{directory}/', código de producción (dueño: Antigravity)"
    return None


def find_tool(root: Path, name: str) -> str | None:
    """Prefer the project's .venv binary, then fall back to PATH."""
    venv_bin = root / ".venv" / "bin" / name
    if venv_bin.is_file() and os.access(venv_bin, os.X_OK):
        return str(venv_bin)
    return shutil.which(name)


def block(reason: str) -> int:
    """Write the reason to stderr and return the blocking exit code (2)."""
    print(reason, file=sys.stderr)
    return 2
