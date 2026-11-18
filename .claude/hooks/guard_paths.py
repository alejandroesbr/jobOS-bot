"""PreToolUse hook for Edit|Write|MultiEdit|NotebookEdit.

Blocks (exit 2) any write to production code (src/**, cli.py) or protected paths.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from _common import block, production_reason, project_root, protected_reason, read_payload, relative_to_root

PATH_KEYS: tuple[str, ...] = ("file_path", "notebook_path", "path")


def target_paths(payload: dict[str, Any]) -> list[str]:
    """Extract every target path from the tool input."""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return []
    found: list[str] = []
    for key in PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            found.append(value)
    return found


def check(paths: list[str], root: Path) -> str | None:
    """Return a blocking reason for the first forbidden path, or None if all are allowed."""
    for raw in paths:
        rel = relative_to_root(raw, root)
        if rel is None:
            continue
        reason = protected_reason(rel) or production_reason(rel)
        if reason is not None:
            return f"Bloqueado por .claude/hooks/guard_paths.py: {reason}. Claude Code no edita esta ruta."
    return None


def main() -> int:
    payload = read_payload()
    reason = check(target_paths(payload), project_root(payload))
    return block(reason) if reason else 0


if __name__ == "__main__":
    sys.exit(main())
