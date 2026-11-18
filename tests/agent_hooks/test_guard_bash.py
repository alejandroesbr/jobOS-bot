"""Tests for .claude/hooks/guard_bash.py (PreToolUse Bash).

Protected-file tests run against `fake_project`, a temp tree with fictitious files,
so the real `.env`, `data/` and `config/` are never touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from guard_bash import PUSH_REASON, check_command, contains_git_push

from tests.agent_hooks.conftest import RunHook

ENV_NAME = "." + "env"  # avoid a literal mention in commands run by agents


# --- git push: always blocked -------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        # plain pushes to any branch, including the agent's own work branch
        "git push",
        "git push origin",
        "git push -u origin chore/agent-setup",
        "git push origin feature/block-2-matcher",
        "git push origin HEAD",
        "git push --set-upstream origin feature/x",
        "git push --tags",
        "git push --dry-run origin feature/x",
        # protected branches and forced variants
        "git push origin main",
        "git push origin HEAD:develop",
        "git push --force origin feature/x",
        "git push -f origin feature/x",
        "git push --force-with-lease origin feature/x",
        "git push origin +feature/x",
        "git push --all origin",
        "git push --mirror origin",
        "git push origin :develop",
        # global options and wrappers
        "git -C /some/repo push origin x",
        "git -c push.default=current push",
        "git --no-pager push",
        "/usr/bin/git push",
        "rtk git push origin x",
        "env GIT_TRACE=1 git push",
        "echo origin | xargs git push",
        # chained commands
        "git status && git push",
        "git add -A; git commit -m wip; git push",
        "git fetch || git push",
        "(cd /tmp && git push)",
        # nested shells
        "bash -c 'git push origin x'",
        'sh -c "git status && git push"',
        "/bin/zsh -c 'git push'",
        "bash -c \"bash -c 'git push'\"",
        "eval git push",
        "eval 'git push origin x'",
    ],
)
def test_blocks_every_git_push(command: str, fake_project: Path) -> None:
    assert check_command(command, fake_project) == PUSH_REASON


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git log --oneline -5",
        "git log --grep push",
        "git fetch origin",
        "git pull --ff-only",
        "git commit -m 'block git push in hook'",
        'git commit -m "docs: explain why git push is human-only"',
        "echo 'git push origin main'",
        "grep -rn 'git push' docs",
        "git stash push -m wip",
        "git branch --show-current",
        "bash -c 'git status'",
    ],
)
def test_allows_non_push_git_commands(command: str, fake_project: Path) -> None:
    assert check_command(command, fake_project) is None


def test_contains_git_push_stops_at_max_nesting() -> None:
    deep = "git push"
    for _ in range(6):
        deep = f"bash -c {deep!r}"
    assert contains_git_push(deep) is False  # beyond MAX_NESTING: documented limit
    assert contains_git_push("bash -c 'bash -c \"git push\"'") is True


# --- protected paths ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        f"cat {ENV_NAME}",
        f"cat ./{ENV_NAME}",
        f"less /home/user/project/{ENV_NAME}",
        f"grep KEY {ENV_NAME}",
        f"source {ENV_NAME}",
        f"head -n1 < {ENV_NAME}",
        f"cat {ENV_NAME}*",
        f"python -c \"print(open('{ENV_NAME}').read())\"",
        f"docker run --env-file={ENV_NAME} image",
        f"cp {ENV_NAME} /tmp/x",
    ],
)
def test_blocks_any_reference_to_env_file(command: str, fake_project: Path) -> None:
    reason = check_command(command, fake_project)
    assert reason is not None
    assert ENV_NAME in reason


@pytest.mark.parametrize(
    "command",
    [
        "cat config/profile.yaml",
        "cat ./config/../config/cv_base.md",
        "strings config/CV_*.pdf",
        "strings config/*.PDF",
        "file config/CV_Test.PDF",
        "cat config/*",
        "ls data",
        "ls data/",
        "sqlite3 data/jobs.db .tables",
        "cp -r data /tmp/x",
        "python3 -c \"open('config/profile.yaml').read()\"",
        "tar czf x.tgz data/*",
        "grep -n name < config/profile.yaml",
    ],
)
def test_blocks_other_protected_paths(command: str, fake_project: Path) -> None:
    reason = check_command(command, fake_project)
    assert reason is not None
    assert "protegida" in reason


def test_blocks_absolute_protected_paths(fake_project: Path) -> None:
    assert check_command(f"cat {fake_project}/config/profile.yaml", fake_project) is not None
    assert check_command(f"head {fake_project / 'data' / 'jobs.db'}", fake_project) is not None


@pytest.mark.parametrize(
    "command",
    [
        f"cat {ENV_NAME}.example",
        f"cp {ENV_NAME}.example {ENV_NAME}.example.bak",
        f"cat {ENV_NAME}rc",
        "pip install python-dotenv",
        f"cat app{ENV_NAME}",
        "ls *",
        "cat config/filters.yaml",
        "python3 -c \"print(d['permissions'])\"",
        "curl https://example.com/data/x.json",
    ],
)
def test_allows_lookalikes_and_safe_paths(command: str, fake_project: Path) -> None:
    assert check_command(command, fake_project) is None


def test_unbalanced_quotes_do_not_crash(fake_project: Path) -> None:
    assert check_command("git push origin main 'oops", fake_project) == PUSH_REASON


# --- hook end to end (stdin JSON -> exit code) --------------------------------------------


def test_hook_blocks_push_of_feature_branch_with_exit_2(run_hook: RunHook, temp_repo: Path) -> None:
    payload = {"tool_name": "Bash", "tool_input": {"command": "git push -u origin feature/x"}}
    result = run_hook("guard_bash.py", payload, project_dir=temp_repo)
    assert result.returncode == 2
    assert "git push" in result.stderr
    assert "humano" in result.stderr


def test_hook_allows_commit(run_hook: RunHook, temp_repo: Path) -> None:
    payload = {"tool_name": "Bash", "tool_input": {"command": "git commit -m 'mention git push'"}}
    assert run_hook("guard_bash.py", payload, project_dir=temp_repo).returncode == 0


def test_hook_blocks_reading_env(run_hook: RunHook, temp_repo: Path) -> None:
    payload = {"tool_name": "Bash", "tool_input": {"command": f"cat {ENV_NAME}"}}
    result = run_hook("guard_bash.py", payload, project_dir=temp_repo)
    assert result.returncode == 2
    assert ENV_NAME in result.stderr


def test_hook_blocks_reading_profile(run_hook: RunHook, fake_project: Path) -> None:
    payload = {"tool_name": "Bash", "tool_input": {"command": "cat config/profile.yaml"}}
    result = run_hook("guard_bash.py", payload, project_dir=fake_project)
    assert result.returncode == 2
    assert "profile.yaml" in result.stderr


def test_hook_ignores_missing_command(run_hook: RunHook) -> None:
    assert run_hook("guard_bash.py", {"tool_name": "Bash", "tool_input": {}}).returncode == 0
