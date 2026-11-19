"""PostToolUse hook for Edit|Write on *.py: `ruff format` + `ruff check --fix` on that file.

Exit 2 (stderr shown to Claude) when ruff still reports errors after fixing.
Exit 0 silently when ruff is not installed or the file is not Python.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from _common import find_tool, project_root, read_payload

MAX_OUTPUT_LINES = 40


def edited_python_file(payload: dict[str, Any], root: Path) -> Path | None:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw = tool_input.get("file_path")
    if not isinstance(raw, str) or not raw.endswith(".py"):
        return None
    path = Path(raw) if Path(raw).is_absolute() else root / raw
    return path if path.is_file() else None


def run_ruff(ruff: str, path: Path, root: Path) -> subprocess.CompletedProcess[str]:
    subprocess.run(
        [ruff, "format", "--quiet", str(path)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return subprocess.run(
        [ruff, "check", "--fix", "--quiet", str(path)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def main() -> int:
    payload = read_payload()
    root = project_root(payload)
    path = edited_python_file(payload, root)
    if path is None:
        return 0
    ruff = find_tool(root, "ruff")
    if ruff is None:
        print("ruff_post_edit: ruff no está instalado; se omite el formateo.", file=sys.stderr)
        return 0
    result = run_ruff(ruff, path, root)
    if result.returncode == 0:
        return 0
    output = (result.stdout + result.stderr).strip().splitlines()[:MAX_OUTPUT_LINES]
    print(f"ruff check sigue fallando en {path}:\n" + "\n".join(output), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
