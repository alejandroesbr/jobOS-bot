"""Tests for .claude/hooks/ruff_post_edit.py (PostToolUse Edit|Write on *.py)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from _common import find_tool
from ruff_post_edit import edited_python_file

from tests.agent_hooks.conftest import REPO_ROOT, RunHook

RUFF = find_tool(REPO_ROOT, "ruff")
needs_ruff = pytest.mark.skipif(RUFF is None, reason="ruff not installed")


def _with_venv_ruff(project: Path) -> None:
    """Expose the repo's ruff inside a temp project via .venv/bin/ruff + the repo's config."""
    assert RUFF is not None
    bin_dir = project / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "ruff").symlink_to(RUFF)
    shutil.copy(REPO_ROOT / "pyproject.toml", project / "pyproject.toml")


def test_edited_python_file_filters_non_python(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert edited_python_file({"tool_input": {"file_path": "a.md"}}, tmp_path) is None
    assert edited_python_file({"tool_input": {"file_path": "missing.py"}}, tmp_path) is None
    assert edited_python_file({"tool_input": {"file_path": "a.py"}}, tmp_path) == tmp_path / "a.py"


def test_hook_ignores_non_python_files(run_hook: RunHook, tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("# x\n", encoding="utf-8")
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "notes.md")}}
    result = run_hook("ruff_post_edit.py", payload, project_dir=tmp_path)
    assert result.returncode == 0


@needs_ruff
def test_hook_formats_and_fixes_python_file(run_hook: RunHook, tmp_path: Path) -> None:
    _with_venv_ruff(tmp_path)
    target = tmp_path / "messy.py"
    target.write_text("import os\nimport sys\nx=[1,2,  3]\nprint(sys.argv,x)\n", encoding="utf-8")
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(target)}}
    result = run_hook("ruff_post_edit.py", payload, project_dir=tmp_path)
    assert result.returncode == 0, result.stderr
    content = target.read_text(encoding="utf-8")
    assert "import os" not in content  # F401 fixed
    assert "x = [1, 2, 3]" in content  # formatted


@needs_ruff
def test_hook_reports_unfixable_errors_with_exit_2(run_hook: RunHook, tmp_path: Path) -> None:
    _with_venv_ruff(tmp_path)
    target = tmp_path / "broken.py"
    target.write_text("def f() -> None:\n    return undefined_name\n", encoding="utf-8")
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(target)}}
    result = run_hook("ruff_post_edit.py", payload, project_dir=tmp_path)
    assert result.returncode == 2
    assert "F821" in result.stderr
