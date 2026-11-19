"""Tests for .claude/hooks/stop_gate.py (Stop hook)."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

from stop_gate import build_checks, changed_python_files, default_runner, is_test_file, run_gate

from tests.agent_hooks.conftest import RunHook, git


class FakeRunner:
    """Delegates git to the real runner; every other tool returns a canned result."""

    def __init__(self, failing: frozenset[str] = frozenset()) -> None:
        self.failing = failing
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if argv[0] == "git":
            return default_runner(argv, cwd)
        self.calls.append(tuple(argv))
        joined = " ".join(argv)
        failed = any(marker in joined for marker in self.failing)
        return subprocess.CompletedProcess(list(argv), 1 if failed else 0, "boom details" if failed else "", "")


def _write(repo: Path, rel: str, content: str = "x = 1\n") -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _fake_tools(repo: Path, exit_codes: dict[str, int] | None = None) -> None:
    codes = {"ruff": 0, "mypy": 0, "python": 0, **(exit_codes or {})}
    bin_dir = repo / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    for name, code in codes.items():
        tool = bin_dir / name
        tool.write_text(f"#!/bin/sh\necho fake-{name}-output\nexit {code}\n", encoding="utf-8")
        tool.chmod(0o755)
    # keep the fake venv out of "changed files"
    (repo / ".git" / "info" / "exclude").write_text(".venv/\n", encoding="utf-8")


def test_is_test_file() -> None:
    assert is_test_file("tests/test_a.py")
    assert is_test_file("tests/agent_hooks/test_b.py")
    assert is_test_file("tests/x_test.py")
    assert not is_test_file("tests/conftest.py")
    assert not is_test_file("test_root.py")


def test_changed_files_include_untracked_and_modified_but_skip_src(temp_repo: Path) -> None:
    _write(temp_repo, "tests/test_new.py")
    _write(temp_repo, "src/domain/x.py")
    _write(temp_repo, "cli.py")
    _write(temp_repo, "notes.md", "# x\n")
    assert changed_python_files(default_runner, temp_repo) == ["tests/test_new.py"]


def test_changed_files_include_modified_tracked(temp_repo: Path) -> None:
    _write(temp_repo, "tests/test_old.py")
    git(temp_repo, "add", ".")
    git(temp_repo, "commit", "-qm", "add")
    _write(temp_repo, "tests/test_old.py", "x = 2\n")
    assert changed_python_files(default_runner, temp_repo) == ["tests/test_old.py"]


def test_changed_files_skip_deleted(temp_repo: Path) -> None:
    _write(temp_repo, "tests/test_gone.py")
    git(temp_repo, "add", ".")
    git(temp_repo, "commit", "-qm", "add")
    (temp_repo / "tests" / "test_gone.py").unlink()
    assert changed_python_files(default_runner, temp_repo) == []


def test_build_checks_runs_pytest_only_for_changed_tests(temp_repo: Path) -> None:
    _fake_tools(temp_repo)
    checks, missing = build_checks([".claude/hooks/a.py", "tests/test_a.py"], temp_repo)
    assert [check.name for check in checks] == ["ruff check", "ruff format", "mypy --strict", "pytest"]
    assert missing == []
    assert "tests/test_a.py" in checks[-1].argv
    assert ".claude/hooks/a.py" not in checks[-1].argv
    assert "--strict" in checks[2].argv


def test_build_checks_without_tests_skips_pytest(temp_repo: Path) -> None:
    _fake_tools(temp_repo)
    checks, _ = build_checks(["tests/conftest.py"], temp_repo)
    assert "pytest" not in [check.name for check in checks]


def test_run_gate_passes_with_no_changes(temp_repo: Path) -> None:
    runner = FakeRunner()
    assert run_gate(temp_repo, runner) == (0, "")
    assert runner.calls == []


def test_run_gate_passes_when_all_checks_pass(temp_repo: Path) -> None:
    _fake_tools(temp_repo)
    _write(temp_repo, "tests/test_ok.py")
    assert run_gate(temp_repo, FakeRunner()) == (0, "")


def test_run_gate_fails_with_summary(temp_repo: Path) -> None:
    _fake_tools(temp_repo)
    _write(temp_repo, "tests/test_bad.py")
    code, summary = run_gate(temp_repo, FakeRunner(failing=frozenset({"--strict"})))
    assert code == 2
    assert "mypy --strict" in summary
    assert "boom details" in summary
    assert "1 check(s)" in summary


def test_hook_respects_stop_hook_active(run_hook: RunHook, temp_repo: Path) -> None:
    _fake_tools(temp_repo, {"ruff": 1})
    _write(temp_repo, "tests/test_bad.py")
    result = run_hook("stop_gate.py", {"stop_hook_active": True}, project_dir=temp_repo)
    assert result.returncode == 0
    assert result.stderr == ""


def test_hook_exits_0_on_clean_tree(run_hook: RunHook, temp_repo: Path) -> None:
    result = run_hook("stop_gate.py", {"stop_hook_active": False}, project_dir=temp_repo)
    assert result.returncode == 0


def test_hook_blocks_when_a_real_check_fails(run_hook: RunHook, temp_repo: Path) -> None:
    _fake_tools(temp_repo, {"ruff": 1})
    _write(temp_repo, "tests/test_x.py")
    result = run_hook("stop_gate.py", {"stop_hook_active": False}, project_dir=temp_repo)
    assert result.returncode == 2
    assert "ruff check" in result.stderr
    assert "fake-ruff-output" in result.stderr
