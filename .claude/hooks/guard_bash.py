"""PreToolUse hook for Bash.

Blocks (exit 2):
- any `git push` to main/develop (explicit refspec, HEAD, --all/--mirror, or no refspec
  while the current branch is main/develop);
- any forced push (--force, -f, --force-with-lease, --force-if-includes, +refspec);
- any command that references a protected path: `.env`, `data/**`, `config/profile.yaml`,
  `config/cv_base.md`, `config/*.pdf` (case-insensitive extension). Path-like fragments are
  resolved against the repo root (relative, absolute, `~`, `..`, symlinks) and globs are
  expanded, so `cat config/profile.yaml`, `strings config/CV_*.pdf` or `ls data` are blocked.

Known limits (defense in depth, not a sandbox): it cannot see paths reached after a `cd`,
via recursive tools on a parent dir (`grep -r .`), or built from variables at runtime.
"""

from __future__ import annotations

import glob
import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

from _common import block, project_root, protected_reason, read_payload, relative_to_root

PROTECTED_BRANCHES: frozenset[str] = frozenset({"main", "develop"})
SEPARATORS: frozenset[str] = frozenset({";", "&&", "||", "|", "&", "\n", "(", ")", "|&"})
# `.env` not preceded/followed by a filename character: matches `.env`, `./.env`, `'.env'`,
# `<.env`, `.env*`; ignores `.env.example`, `.envrc`, `foo.env`, `dotenv`.
ENV_FILE = re.compile(r"(?:^|[^\w.-])\.env(?:$|[^\w.-])")
FORCE_LONG: tuple[str, ...] = ("--force", "--force-with-lease", "--force-if-includes")
PUSH_OPTS_WITH_VALUE: frozenset[str] = frozenset(
    {"--repo", "-o", "--push-option", "--receive-pack", "--exec"},
)
GIT_OPTS_WITH_VALUE: frozenset[str] = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace"})
# Characters that delimit path-like fragments inside a shell command (quotes, redirections,
# assignments, separators, python call syntax such as open('x')).
FRAGMENT_SPLIT = re.compile(r"[\s=:'\"`(),;<>|&{}\[\]]+")
GLOB_CHARS = re.compile(r"[*?]")
MAX_GLOB_MATCHES = 200


def tokenize(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError:  # unbalanced quotes: fall back to a plain split
        return command.split()


def segments(tokens: list[str]) -> Iterator[list[str]]:
    current: list[str] = []
    for token in tokens:
        if token in SEPARATORS:
            if current:
                yield current
            current = []
        else:
            current.append(token)
    if current:
        yield current


def push_args(segment: list[str]) -> list[str] | None:
    """If the segment is a `git ... push ...` invocation, return the args after `push`."""
    for index, token in enumerate(segment):
        if token != "git" and not token.endswith("/git"):
            continue
        cursor = index + 1
        while cursor < len(segment) and segment[cursor].startswith("-"):
            option = segment[cursor]
            cursor += 2 if option in GIT_OPTS_WITH_VALUE else 1
        if cursor < len(segment) and segment[cursor] == "push":
            return segment[cursor + 1 :]
    return None


def _is_force(arg: str) -> bool:
    if any(arg == flag or arg.startswith(flag + "=") for flag in FORCE_LONG):
        return True
    return arg.startswith("-") and not arg.startswith("--") and "f" in arg[1:]


def _branch_of(refspec: str, current_branch: str | None) -> str:
    target = refspec.lstrip("+")
    if ":" in target:
        target = target.split(":", 1)[1]
    if target == "HEAD" and current_branch:
        target = current_branch
    return target.removeprefix("refs/heads/")


def check_push(args: list[str], current_branch: str | None) -> str | None:
    positionals: list[str] = []
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if _is_force(arg):
            return f"push forzado prohibido ('{arg}')"
        if arg in ("--all", "--mirror"):
            return f"'git push {arg}' incluye main/develop"
        if arg in PUSH_OPTS_WITH_VALUE:
            skip_next = True
            continue
        if arg.startswith("-"):
            continue
        positionals.append(arg)
    refspecs = positionals[1:]
    for refspec in refspecs:
        if refspec.startswith("+"):
            return f"push forzado prohibido (refspec '{refspec}')"
        branch = _branch_of(refspec, current_branch)
        if branch in PROTECTED_BRANCHES:
            return f"push directo a '{branch}' prohibido; usa una rama y PR"
    if not refspecs and current_branch in PROTECTED_BRANCHES:
        return f"push sin refspec estando en '{current_branch}' prohibido"
    return None


def protected_path_in(command: str, root: Path) -> str | None:
    """Return the protection reason of the first protected path the command references."""
    for fragment in FRAGMENT_SPLIT.split(command):
        if not fragment or fragment.startswith("-") or "://" in fragment:
            continue
        candidates = [fragment]
        if GLOB_CHARS.search(fragment):
            # Glob matches only count when they are files: `config/*` or `data/*` are blocked,
            # but a bare `*` (e.g. inside a permission rule string) that merely matches the
            # `data/` directory is not. Explicitly naming `data` is still blocked above.
            pattern = fragment if Path(fragment).is_absolute() else str(root / fragment)
            matches = glob.glob(pattern)[:MAX_GLOB_MATCHES]
            candidates.extend(match for match in matches if Path(match).is_file())
        for candidate in candidates:
            try:
                rel = relative_to_root(candidate, root)
            except (OSError, RuntimeError, ValueError):
                continue
            if rel is None:
                continue
            reason = protected_reason(rel)
            if reason:
                return reason
    return None


def check_command(
    command: str,
    current_branch: Callable[[], str | None],
    root: Path,
) -> str | None:
    """Return a blocking reason or None. current_branch is only called when needed."""
    if ENV_FILE.search(command):
        return "el comando referencia '.env' (ruta protegida; solo .env.example es público)"
    reason = protected_path_in(command, root)
    if reason:
        return f"el comando referencia una ruta protegida: {reason}"
    for segment in segments(tokenize(command)):
        args = push_args(segment)
        if args is None:
            continue
        reason = check_push(args, current_branch())
        if reason:
            return reason
    return None


def git_current_branch(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    branch = result.stdout.strip()
    return branch if result.returncode == 0 and branch else None


def main() -> int:
    payload = read_payload()
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not command.strip():
        return 0
    root = project_root(payload)
    reason = check_command(command, lambda: git_current_branch(root), root)
    if reason:
        return block(f"Bloqueado por .claude/hooks/guard_bash.py: {reason}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
