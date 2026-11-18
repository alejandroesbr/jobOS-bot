"""Stop hook: fast quality gate over files changed in the working tree.

- Respects `stop_hook_active` to avoid loops (exit 0 on the re-entry).
- Changed files = `git diff --name-only HEAD` + untracked, *.py only, still existing,
  excluding production code (src/**, cli.py) that Claude Code does not own.
- Runs ruff check, ruff format --check and mypy --strict on those files,
  and pytest only on changed test files. The full suite runs in CI.
- Exit 2 with a summary on stderr if any check fails.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from _common import find_tool, production_reason, project_root, read_payload

MAX_OUTPUT_LINES = 30

Runner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    argv: tuple[str, ...]


def default_runner(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )


def _git_lines(runner: Runner, root: Path, *args: str) -> list[str]:
    result = runner(["git", *args], root)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_python_files(runner: Runner, root: Path) -> list[str]:
    tracked = _git_lines(runner, root, "diff", "--name-only", "--diff-filter=d", "HEAD")
    untracked = _git_lines(runner, root, "ls-files", "--others", "--exclude-standard")
    seen: dict[str, None] = {}
    for rel in [*tracked, *untracked]:
        if rel.endswith(".py") and production_reason(rel) is None and (root / rel).is_file():
            seen[rel] = None
    return list(seen)


def is_test_file(rel: str) -> bool:
    name = Path(rel).name
    return rel.startswith("tests/") and (name.startswith("test_") or name.endswith("_test.py"))


def build_checks(files: list[str], root: Path) -> tuple[list[Check], list[str]]:
    """Return the checks to run plus warnings for missing tools."""
    checks: list[Check] = []
    missing: list[str] = []
    ruff = find_tool(root, "ruff")
    mypy = find_tool(root, "mypy")
    python = find_tool(root, "python") or sys.executable
    if ruff:
        checks.append(Check("ruff check", (ruff, "check", *files)))
        checks.append(Check("ruff format", (ruff, "format", "--check", *files)))
    else:
        missing.append("ruff")
    if mypy:
        checks.append(Check("mypy --strict", (mypy, "--strict", "--follow-imports=silent", *files)))
    else:
        missing.append("mypy")
    tests = [rel for rel in files if is_test_file(rel)]
    if tests:
        checks.append(Check("pytest", (python, "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests)))
    return checks, missing


def run_gate(root: Path, runner: Runner) -> tuple[int, str]:
    files = changed_python_files(runner, root)
    if not files:
        return 0, ""
    checks, missing = build_checks(files, root)
    failures: list[str] = []
    for check in checks:
        result = runner(check.argv, root)
        if result.returncode != 0:
            lines = (result.stdout + result.stderr).strip().splitlines()[-MAX_OUTPUT_LINES:]
            failures.append(f"## {check.name} (exit {result.returncode})\n" + "\n".join(lines))
    if not failures:
        return 0, ""
    header = f"stop_gate: {len(failures)} check(s) fallaron sobre {len(files)} archivo(s) modificados."
    if missing:
        header += f" Herramientas ausentes: {', '.join(missing)}."
    return 2, header + "\n\n" + "\n\n".join(failures)


def main() -> int:
    payload = read_payload()
    if payload.get("stop_hook_active") is True:
        return 0
    code, summary = run_gate(project_root(payload), default_runner)
    if code:
        print(summary, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
