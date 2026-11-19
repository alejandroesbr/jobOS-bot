"""PreToolUse hook for Antigravity implementer (stdlib only).

Blocks (decision: "deny") any attempt by Antigravity to:
1. Read or edit privacy-protected paths (.env, data/**, config/profile.yaml, config/cv_base.md, config/*.pdf).
2. Edit Claude Code owned paths (tests/**, AGENTS.md, CLAUDE.md, .claude/**, docs/agents/**,
   docs/audits/**, docs/blocks/block-N.md, .github/workflows/**).
3. Edit [tool.*] or [dependency-groups] sections in pyproject.toml.
4. Execute bash commands that reference .env, push to main/develop, or force-push.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import Any

PROTECTED_EXACT: frozenset[str] = frozenset(
    {".env", "config/profile.yaml", "config/cv_base.md"},
)
PROTECTED_DIRS: tuple[str, ...] = ("data",)
PROTECTED_GLOBS: tuple[str, ...] = ("config/*.pdf",)

CLAUDE_EXACT: frozenset[str] = frozenset({"AGENTS.md", "CLAUDE.md"})
CLAUDE_DIRS: tuple[str, ...] = (
    "tests",
    ".claude",
    "docs/agents",
    "docs/audits",
    ".github/workflows",
)
BLOCK_SPEC_RE = re.compile(r"^docs/blocks/block-\d+\.md$")
PYPROJECT_FORBIDDEN_HEADER_RE = re.compile(
    r"^\s*\[(?:tool\.|dependency-groups\b)",
    re.MULTILINE,
)

EDIT_TOOLS: frozenset[str] = frozenset(
    {
        "edit_file",
        "write_file",
        "replace_file_content",
        "multi_replace_file_content",
        "write_to_file",
        "edit",
        "write",
        "multiedit",
    },
)
READ_TOOLS: frozenset[str] = frozenset(
    {"read_file", "view_file", "view_file_outline", "view_code_item", "read"},
)
COMMAND_TOOLS: frozenset[str] = frozenset({"run_command", "bash"})

PROTECTED_BRANCHES: frozenset[str] = frozenset({"main", "develop"})
SEPARATORS: frozenset[str] = frozenset({";", "&&", "||", "|", "&", "\n", "(", ")", "|&"})
ENV_FILE_RE = re.compile(r"(?:^|[^\w.-])\.env(?:$|[^\w.-])")
FORCE_LONG: tuple[str, ...] = ("--force", "--force-with-lease", "--force-if-includes")
PUSH_OPTS_WITH_VALUE: frozenset[str] = frozenset(
    {"--repo", "-o", "--push-option", "--receive-pack", "--exec"},
)
GIT_OPTS_WITH_VALUE: frozenset[str] = frozenset(
    {"-C", "-c", "--git-dir", "--work-tree", "--namespace"},
)


def read_payload() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def resolve_root(payload: dict[str, Any]) -> Path:
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd:
        p = Path(cwd).resolve()
        if (p / "AGENTS.md").exists() or (p / ".git").exists():
            return p
    ws = payload.get("workspacePaths")
    if isinstance(ws, list):
        for item in ws:
            if isinstance(item, str) and item:
                candidate = Path(item).resolve()
                if (candidate / "AGENTS.md").exists():
                    return candidate
    return Path(__file__).resolve().parents[2]


def relative_to_root(file_path: str, root: Path) -> str | None:
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
    if rel in PROTECTED_EXACT:
        return f"'{rel}' es una ruta protegida por privacidad"
    for directory in PROTECTED_DIRS:
        if _in_dir(rel, directory):
            return f"'{rel}' está dentro de '{directory}/', ruta protegida por privacidad"
    for pattern in PROTECTED_GLOBS:
        if fnmatch(rel, pattern) and rel.count("/") == pattern.count("/"):
            return f"'{rel}' coincide con '{pattern}', ruta protegida por privacidad"
    return None


def claude_owned_reason(rel: str, args: dict[str, Any]) -> str | None:
    if rel in CLAUDE_EXACT:
        return f"'{rel}' pertenece a Claude Code (docs/agents/ownership.md)"
    for directory in CLAUDE_DIRS:
        if _in_dir(rel, directory):
            return f"'{rel}' está en '{directory}/', ruta propiedad de Claude Code"
    if BLOCK_SPEC_RE.match(rel):
        return f"'{rel}' es una especificación de bloque propiedad de Claude Code"
    if rel == "pyproject.toml":
        for key in ("Target", "Replacement", "Content", "TargetContent", "ReplacementContent"):
            val = args.get(key)
            if isinstance(val, str) and PYPROJECT_FORBIDDEN_HEADER_RE.search(val):
                return (
                    "las secciones [tool.*] y [dependency-groups] de 'pyproject.toml' "
                    "pertenecen a Claude Code"
                )
    return None


def extract_paths(args: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for key in ("Path", "path", "TargetFile", "file_path", "notebook_path"):
        val = args.get(key)
        if isinstance(val, str) and val:
            found.append(val)
    return found


def check_command(command: str, root: Path) -> str | None:
    if ENV_FILE_RE.search(command):
        return "el comando referencia '.env' (ruta protegida; solo .env.example es público)"
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        tokens = list(lexer)
    except ValueError:
        tokens = command.split()

    current: list[str] = []
    segments: list[list[str]] = []
    for tok in tokens:
        if tok in SEPARATORS:
            if current:
                segments.append(current)
            current = []
        else:
            current.append(tok)
    if current:
        segments.append(current)

    for seg in segments:
        for idx, tok in enumerate(seg):
            if tok != "git" and not tok.endswith("/git"):
                continue
            cur = idx + 1
            while cur < len(seg) and seg[cur].startswith("-"):
                opt = seg[cur]
                cur += 2 if opt in GIT_OPTS_WITH_VALUE else 1
            if cur < len(seg) and seg[cur] in {"push", "merge"}:
                subcmd = seg[cur]
                sub_args = seg[cur + 1 :]
                if subcmd == "push":
                    reason = _check_git_push(sub_args, root)
                    if reason:
                        return reason
    return None


def _git_current_branch(root: Path) -> str | None:
    try:
        res = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    branch = res.stdout.strip()
    return branch if res.returncode == 0 and branch else None


def _check_git_push(args: list[str], root: Path) -> str | None:
    positionals: list[str] = []
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if any(arg == flag or arg.startswith(flag + "=") for flag in FORCE_LONG) or (
            arg.startswith("-") and not arg.startswith("--") and "f" in arg[1:]
        ):
            return f"git push forzado prohibido ('{arg}')"
        if arg in ("--all", "--mirror"):
            return f"'git push {arg}' incluye main/develop"
        if arg in PUSH_OPTS_WITH_VALUE:
            skip_next = True
            continue
        if arg.startswith("-"):
            continue
        positionals.append(arg)
    cur_branch = _git_current_branch(root)
    refspecs = positionals[1:]
    for refspec in refspecs:
        if refspec.startswith("+"):
            return f"git push forzado prohibido (refspec '{refspec}')"
        target = refspec.lstrip("+")
        if ":" in target:
            target = target.split(":", 1)[1]
        if target == "HEAD" and cur_branch:
            target = cur_branch
        branch = target.removeprefix("refs/heads/")
        if branch in PROTECTED_BRANCHES:
            return f"push directo a '{branch}' prohibido"
    if not refspecs and cur_branch in PROTECTED_BRANCHES:
        return f"push sin refspec estando en '{cur_branch}' prohibido"
    return None


def emit(decision: str, reason: str | None = None) -> int:
    out: dict[str, Any] = {"decision": decision}
    if reason:
        out["reason"] = reason
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()
    return 0


def main() -> int:
    payload = read_payload()
    tool_call = payload.get("toolCall")
    if not isinstance(tool_call, dict):
        return emit("allow")

    tool_name = str(tool_call.get("name", "")).lower()
    args = tool_call.get("args")
    if not isinstance(args, dict):
        args = {}

    root = resolve_root(payload)

    if tool_name in READ_TOOLS or tool_name in EDIT_TOOLS:
        for raw_path in extract_paths(args):
            rel = relative_to_root(raw_path, root)
            if rel is None:
                continue
            p_reason = protected_reason(rel)
            if p_reason:
                return emit(
                    "deny",
                    f"Bloqueado por .agents/hooks/guard_implementer.py: {p_reason}.",
                )
            if tool_name in EDIT_TOOLS:
                c_reason = claude_owned_reason(rel, args)
                if c_reason:
                    return emit(
                        "deny",
                        f"Bloqueado por .agents/hooks/guard_implementer.py: {c_reason}. "
                        "Anótalo en docs/blocks/block-N-questions.md o en el handoff.",
                    )

    if tool_name in COMMAND_TOOLS:
        cmd = args.get("CommandLine") or args.get("command")
        if isinstance(cmd, str) and cmd.strip():
            cmd_reason = check_command(cmd, root)
            if cmd_reason:
                return emit(
                    "deny",
                    f"Bloqueado por .agents/hooks/guard_implementer.py: {cmd_reason}.",
                )

    return emit("allow")


if __name__ == "__main__":
    sys.exit(main())
