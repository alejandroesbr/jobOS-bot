"""Tests for .claude/hooks/guard_paths.py (PreToolUse Edit|Write|MultiEdit|NotebookEdit)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from _common import project_root
from guard_paths import check, target_paths

from tests.agent_hooks.conftest import HOOKS_DIR, REPO_ROOT, RunHook

BLOCKED = [
    "src/x.py",
    "src/domain/models.py",
    "src",
    "cli.py",
    ".env",
    "data/jobs.db",
    "data/nested/deep/file.json",
    "config/profile.yaml",
    "config/cv_base.md",
    "config/cv.pdf",
    "config/CV_Final.PDF",
    "./src/../src/x.py",
]

ALLOWED = [
    "tests/test_new.py",
    "AGENTS.md",
    "CLAUDE.md",
    ".claude/settings.json",
    "docs/audits/block-1-round1.md",
    ".env.example",
    "config/filters.yaml",
    "config/profile.example.yaml",
    "config/sub/cv.pdf",
    "srcs/x.py",
    "cli.py.bak",
    "database/x.sql",
]


@pytest.mark.parametrize("rel", BLOCKED)
def test_check_blocks_production_and_protected_paths(rel: str) -> None:
    assert check([rel], REPO_ROOT) is not None


@pytest.mark.parametrize("rel", ALLOWED)
def test_check_allows_claude_owned_paths(rel: str) -> None:
    assert check([rel], REPO_ROOT) is None


def test_check_resolves_absolute_paths() -> None:
    assert check([str(REPO_ROOT / "src" / "x.py")], REPO_ROOT) is not None
    assert check([str(REPO_ROOT / "tests" / "x.py")], REPO_ROOT) is None


def test_check_ignores_paths_outside_the_repo(tmp_path: Path) -> None:
    assert check([str(tmp_path / "src" / "x.py")], REPO_ROOT) is None


def test_check_follows_symlinks_into_src(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "real.py").write_text("", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "alias.py").symlink_to(repo / "src" / "real.py")
    assert check(["tests/alias.py"], repo.resolve()) is not None


def test_target_paths_reads_all_known_keys() -> None:
    payload = {"tool_input": {"file_path": "a.py", "notebook_path": "b.ipynb"}}
    assert target_paths(payload) == ["a.py", "b.ipynb"]
    assert target_paths({"tool_input": "garbage"}) == []
    assert target_paths({}) == []


def test_project_root_uses_file_location_over_wrong_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("JOBOS_HOOK_ROOT", raising=False)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert project_root({}) == REPO_ROOT


def test_hook_blocks_edit_of_src_even_with_wrong_project_dir(tmp_path: Path) -> None:
    """Regression: $CLAUDE_PROJECT_DIR pointing elsewhere (e.g. after /cd) must not disable the guard."""
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(REPO_ROOT / "src" / "x.py")}}
    env = {k: v for k, v in os.environ.items() if k != "JOBOS_HOOK_ROOT"}
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "guard_paths.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )
    assert result.returncode == 2


def test_hook_blocks_edit_of_src_with_exit_2(run_hook: RunHook) -> None:
    result = run_hook("guard_paths.py", {"tool_name": "Edit", "tool_input": {"file_path": "src/x.py"}})
    assert result.returncode == 2
    assert "src/x.py" in result.stderr
    assert "Antigravity" in result.stderr


@pytest.mark.parametrize(
    ("tool", "key"),
    [("Write", "file_path"), ("MultiEdit", "file_path"), ("NotebookEdit", "notebook_path")],
)
def test_hook_blocks_every_write_tool(run_hook: RunHook, tool: str, key: str) -> None:
    result = run_hook("guard_paths.py", {"tool_name": tool, "tool_input": {key: "cli.py"}})
    assert result.returncode == 2


def test_hook_blocks_protected_path_with_privacy_reason(run_hook: RunHook) -> None:
    result = run_hook("guard_paths.py", {"tool_name": "Write", "tool_input": {"file_path": ".env"}})
    assert result.returncode == 2
    assert "privacidad" in result.stderr


def test_hook_allows_tests(run_hook: RunHook) -> None:
    result = run_hook("guard_paths.py", {"tool_name": "Write", "tool_input": {"file_path": "tests/test_a.py"}})
    assert result.returncode == 0
    assert result.stderr == ""


@pytest.mark.parametrize("raw", ["", "not json", "[]"])
def test_hook_tolerates_malformed_payload(run_hook: RunHook, raw: str) -> None:
    assert run_hook("guard_paths.py", raw).returncode == 0
