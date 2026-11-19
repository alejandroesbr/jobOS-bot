"""Shared fixtures for the Claude Code hook tests (no network, no real repo mutation)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"

if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

RunHook = Callable[..., subprocess.CompletedProcess[str]]


@pytest.fixture
def run_hook() -> RunHook:
    """Run a hook script as Claude Code does: JSON payload on stdin.

    JOBOS_HOOK_ROOT points the hook at an isolated project dir; by default the real repo.
    """

    def _run(
        script: str,
        payload: dict[str, Any] | str,
        project_dir: Path = REPO_ROOT,
    ) -> subprocess.CompletedProcess[str]:
        stdin = payload if isinstance(payload, str) else json.dumps(payload)
        env = {**os.environ, "JOBOS_HOOK_ROOT": str(project_dir), "CLAUDE_PROJECT_DIR": str(project_dir)}
        return subprocess.run(
            [sys.executable, str(HOOKS_DIR / script)],
            input=stdin,
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            check=False,
        )

    return _run


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """An isolated git repo with one commit on branch 'feature/x'."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "feature/x")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Hook Test")
    git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-q", "-m", "init")
    return repo.resolve()


@pytest.fixture
def fake_project(tmp_path: Path) -> Path:
    """A fake project tree containing dummy (fictitious) protected files."""
    root = tmp_path / "proj"
    for rel in ("data/jobs.db", "config/profile.yaml", "config/cv_base.md", "config/CV_Test.PDF"):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fictitious\n", encoding="utf-8")
    (root / "config" / "filters.yaml").write_text("x: 1\n", encoding="utf-8")
    (root / "tests").mkdir()
    return root.resolve()
