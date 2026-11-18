"""PreToolUse hook for Bash.

Blocks (exit 2):
- ANY `git push`, whatever the remote, branch or flags: pushing is done by the human, never by
  Claude Code. Also detected behind wrappers (`env`, `xargs`, `rtk`, `/usr/bin/git`,
  `git -C dir`) and inside `bash|sh|zsh|fish|dash -c "..."` and `eval "..."`;
- any command that references a protected path: `.env`, `data/**`, `config/profile.yaml`,
  `config/cv_base.md`, `config/*.pdf` (case-insensitive extension). Path-like fragments are
  resolved against the repo root (relative, absolute, `~`, `..`, symlinks) and globs are
  expanded, so `cat config/profile.yaml`, `strings config/CV_*.pdf` or `ls data` are blocked.

Known limits (defense in depth, not a sandbox): it cannot see paths reached after a `cd`,
via recursive tools on a parent dir (`grep -r .`), or built from variables at runtime;
git aliases that expand to push (e.g. `git p`) are not resolved.
"""

from __future__ import annotations

import glob
import re
import shlex
import sys
from collections.abc import Iterator
from pathlib import Path

from _common import block, project_root, protected_reason, read_payload, relative_to_root

SEPARATORS: frozenset[str] = frozenset({";", "&&", "||", "|", "&", "\n", "(", ")", "|&"})
# `.env` not preceded/followed by a filename character: matches `.env`, `./.env`, `'.env'`,
# `<.env`, `.env*`; ignores `.env.example`, `.envrc`, `foo.env`, `dotenv`.
ENV_FILE = re.compile(r"(?:^|[^\w.-])\.env(?:$|[^\w.-])")
GIT_OPTS_WITH_VALUE: frozenset[str] = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace"})
SHELLS: frozenset[str] = frozenset({"bash", "sh", "zsh", "fish", "dash"})
MAX_NESTING = 3
# Characters that delimit path-like fragments inside a shell command (quotes, redirections,
# assignments, separators, python call syntax such as open('x')).
FRAGMENT_SPLIT = re.compile(r"[\s=:'\"`(),;<>|&{}\[\]]+")
GLOB_CHARS = re.compile(r"[*?]")
MAX_GLOB_MATCHES = 200
PUSH_REASON = "Claude Code no ejecuta 'git push'; el push lo hace el humano desde su terminal"


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


def is_git_push(segment: list[str]) -> bool:
    """True if the segment invokes `git [global options] push`."""
    for index, token in enumerate(segment):
        if token != "git" and not token.endswith("/git"):
            continue
        cursor = index + 1
        while cursor < len(segment) and segment[cursor].startswith("-"):
            cursor += 2 if segment[cursor] in GIT_OPTS_WITH_VALUE else 1
        if cursor < len(segment) and segment[cursor] == "push":
            return True
    return False


def nested_scripts(segment: list[str]) -> Iterator[str]:
    """Command strings executed by `<shell> -c "..."` or `eval ...` inside the segment."""
    for index, token in enumerate(segment):
        name = token.rsplit("/", 1)[-1]
        if name in SHELLS and segment[index + 1 : index + 2] == ["-c"] and index + 2 < len(segment):
            yield segment[index + 2]
        elif name == "eval" and index + 1 < len(segment):
            yield " ".join(segment[index + 1 :])


def contains_git_push(command: str, depth: int = 0) -> bool:
    for segment in segments(tokenize(command)):
        if is_git_push(segment):
            return True
        if depth < MAX_NESTING and any(contains_git_push(script, depth + 1) for script in nested_scripts(segment)):
            return True
    return False


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


def check_command(command: str, root: Path) -> str | None:
    """Return a blocking reason or None."""
    if ENV_FILE.search(command):
        return "el comando referencia '.env' (ruta protegida; solo .env.example es público)"
    reason = protected_path_in(command, root)
    if reason:
        return f"el comando referencia una ruta protegida: {reason}"
    if contains_git_push(command):
        return PUSH_REASON
    return None


def main() -> int:
    payload = read_payload()
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not command.strip():
        return 0
    reason = check_command(command, project_root(payload))
    if reason:
        return block(f"Bloqueado por .claude/hooks/guard_bash.py: {reason}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
