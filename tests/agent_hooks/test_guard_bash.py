"""Tests for .claude/hooks/guard_bash.py (PreToolUse Bash).

Protected-file tests run against `fake_project`, a temp tree with fictitious files,
so the real `.env`, `data/` and `config/` are never touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from guard_bash import check_command

from tests.agent_hooks.conftest import RunHook, git

ENV_NAME = "." + "env"  # avoid a literal mention in commands run by agents


def on(branch: str | None, root: Path, command: str) -> str | None:
    return check_command(command, lambda: branch, root)


@pytest.mark.parametrize(
    "command",
    [
        "git push origin main",
        "git push origin develop",
        "git push origin HEAD:main",
        "git push origin feature/x:develop",
        "git push origin refs/heads/main",
        "git push -u origin develop",
        "git push origin :develop",
        "git push --all origin",
        "git push --mirror origin",
        "git -C /some/repo push origin main",
        "rtk git push origin main",
        "git status && git push origin develop",
        "echo hi; git push origin main",
    ],
)
def test_blocks_push_to_protected_branches(command: str, fake_project: Path) -> None:
    assert on("feature/x", fake_project, command) is not None


@pytest.mark.parametrize(
    "command",
    [
        "git push --force origin feature/x",
        "git push -f origin feature/x",
        "git push -uf origin feature/x",
        "git push --force-with-lease origin feature/x",
        "git push --force-with-lease=feature/x origin feature/x",
        "git push --force-if-includes origin feature/x",
        "git push origin +feature/x",
    ],
)
def test_blocks_forced_push(command: str, fake_project: Path) -> None:
    reason = on("feature/x", fake_project, command)
    assert reason is not None
    assert "forzado" in reason


@pytest.mark.parametrize("branch", ["main", "develop"])
@pytest.mark.parametrize("command", ["git push", "git push origin", "git push -u origin", "git push origin HEAD"])
def test_blocks_implicit_push_while_on_protected_branch(command: str, branch: str, fake_project: Path) -> None:
    assert on(branch, fake_project, command) is not None


@pytest.mark.parametrize(
    "command",
    [
        "git push",
        "git push origin",
        "git push -u origin chore/agent-setup",
        "git push origin feature/block-2-matcher",
        "git push origin HEAD",
        "git push origin main-fix",
        "git push origin feature/develop-notes",
        "git status",
        "git log --oneline -5",
        "echo 'git push origin main'",
        "ls *",
        "cat config/filters.yaml",
        "python3 -c \"print(d['permissions'])\"",
        "curl https://example.com/data/x.json",
    ],
)
def test_allows_safe_commands(command: str, fake_project: Path) -> None:
    assert on("chore/agent-setup", fake_project, command) is None


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
    reason = on("feature/x", fake_project, command)
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
    reason = on("feature/x", fake_project, command)
    assert reason is not None
    assert "protegida" in reason


def test_blocks_absolute_and_home_relative_protected_paths(fake_project: Path) -> None:
    assert on("x", fake_project, f"cat {fake_project}/config/profile.yaml") is not None
    assert on("x", fake_project, f"head {fake_project / 'data' / 'jobs.db'}") is not None


@pytest.mark.parametrize(
    "command",
    [
        f"cat {ENV_NAME}.example",
        f"cp {ENV_NAME}.example {ENV_NAME}.example.bak",
        f"cat {ENV_NAME}rc",
        "pip install python-dotenv",
        f"cat app{ENV_NAME}",
    ],
)
def test_allows_env_example_and_lookalikes(command: str, fake_project: Path) -> None:
    assert on("feature/x", fake_project, command) is None


def test_branch_lookup_is_lazy(fake_project: Path) -> None:
    calls: list[int] = []

    def branch() -> str:
        calls.append(1)
        return "main"

    assert check_command("ls -la", branch, fake_project) is None
    assert calls == []


def test_unbalanced_quotes_do_not_crash(fake_project: Path) -> None:
    assert on("x", fake_project, "git push origin main 'oops") is not None


def test_hook_blocks_push_to_develop_with_exit_2(run_hook: RunHook, temp_repo: Path) -> None:
    payload = {"tool_name": "Bash", "tool_input": {"command": "git push origin develop"}}
    result = run_hook("guard_bash.py", payload, project_dir=temp_repo)
    assert result.returncode == 2
    assert "develop" in result.stderr


def test_hook_uses_real_current_branch(run_hook: RunHook, temp_repo: Path) -> None:
    payload = {"tool_name": "Bash", "tool_input": {"command": "git push"}}
    assert run_hook("guard_bash.py", payload, project_dir=temp_repo).returncode == 0
    git(temp_repo, "checkout", "-q", "-b", "develop")
    assert run_hook("guard_bash.py", payload, project_dir=temp_repo).returncode == 2


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
