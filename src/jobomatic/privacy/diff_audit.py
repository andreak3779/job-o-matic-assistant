"""Find personal identifiers in the lines a push would publish (ADR 0032).

``scan.find_pii`` looks at the tracked files at commit time. A leak becomes irreversible when it is
pushed to the public repository, and the commit-time check does not see a commit made with
``--no-verify``, on another machine or before the hook existed. This audits what is actually being
pushed: the *added* lines of each commit, the commits' authors and messages, with every term
matched case-insensitively. It is stricter
than the commit-time scan on purpose; a false alarm costs one look at the line, a miss cannot be
taken back.

Everything here is a pure function over text, so it can be tested without a repository. Findings are
reported as ``path:line (category)``; the matching text is never printed.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass

# A term up to this long must not sit inside a longer word ("Sam" in "Samuel"); a longer one is
# matched anywhere, because a name or an employer inside a longer word is still that name.
_SHORT_TERM = 6


@dataclass(frozen=True)
class AddedLine:
    path: str
    number: int
    text: str


def added_lines(diff: str) -> list[AddedLine]:
    """The lines a unified diff adds, with their line numbers in the new file.

    Meant for ``git diff --unified=0``: with no context lines, every ``+`` line after a hunk
    header is consecutive from the header's start. Deleted files and binary files add nothing.
    """
    found: list[AddedLine] = []
    path: str | None = None
    number = 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:].split("\t")[0]
            path = None if target == "/dev/null" else _unquote(target.removeprefix("b/"))
        elif line.startswith("@@"):
            match = re.match(r"@@ -\S+ \+(\d+)", line)
            number = int(match.group(1)) if match else 0
        elif line.startswith("+") and path is not None:
            found.append(AddedLine(path, number, line[1:]))
            number += 1
    return found


RECORD = "\x1e"  # starts each commit in the ``git log`` format ``COMMIT_FORMAT``
COMMIT_FORMAT = f"{RECORD}%H%n%an <%ae>%n%cn <%ce>%n%B"


def commit_texts(log_output: str) -> list[AddedLine]:
    """The text a commit publishes besides its patch: author, committer and message.

    ``log_output`` is ``git log --format=COMMIT_FORMAT``. Each commit becomes lines under the path
    ``commit <short sha>``: line 1 is the author, line 2 the committer, the rest the message. A
    private email or name written there is as public as one written in a file.
    """
    found: list[AddedLine] = []
    for record in log_output.split(RECORD):
        lines = record.splitlines()
        if not lines:
            continue
        path = f"commit {lines[0][:10]}"
        found.extend(AddedLine(path, n, text) for n, text in enumerate(lines[1:], start=1) if text)
    return found


def _unquote(name: str) -> str:
    """Git wraps a path with unusual characters in double quotes."""
    return name[1:-1] if len(name) >= 2 and name[0] == '"' and name[-1] == '"' else name


def _pattern(category: str, values: Iterable[str]) -> re.Pattern[str] | None:
    parts = []
    for value in sorted({v.strip() for v in values if len(v.strip()) >= 3}, key=len, reverse=True):
        digits = re.sub(r"\D", "", value)
        if category == "phones" and len(digits) == 10:
            # Any separator style between digit groups.
            parts.append(rf"\(?{digits[:3]}\)?[-. ]?{digits[3:6]}[-. ]?{digits[6:]}")
        elif len(value) <= _SHORT_TERM:
            parts.append(rf"(?<!\w){re.escape(value)}(?!\w)")
        else:
            parts.append(re.escape(value))
    return re.compile("|".join(parts), re.IGNORECASE) if parts else None


def audit_added_lines(
    terms: Mapping[str, Iterable[str]],
    added: Iterable[AddedLine],
    allow: Collection[str] = (),
) -> list[str]:
    """``path:line (category)`` for each added line that names a private identifier.

    ``allow`` lists paths exempt from the check (``scripts/pii-allowlist.txt``).
    """
    patterns = {c: p for c, v in terms.items() if (p := _pattern(c, v)) is not None}
    findings: list[str] = []
    for item in added:
        if item.path in allow:
            continue
        for category, pattern in patterns.items():
            if pattern.search(item.text):
                findings.append(f"{item.path}:{item.number} ({category})")
    return findings


@dataclass(frozen=True)
class PushedUpdate:
    """One ref a push would update. ``remote_sha`` is ``None`` when the ref is new on the remote."""

    ref: str
    local_sha: str
    remote_sha: str | None


def _is_null(sha: str) -> bool:
    return bool(sha) and set(sha) == {"0"}


def pushed_updates(lines: Iterable[str]) -> list[PushedUpdate]:
    """Parse what git sends to a pre-push hook on stdin: ``<local ref> <local sha> <remote ref>
    <remote sha>`` per line. A deletion (local sha all zeros) publishes nothing and is dropped;
    a ref that is new on the remote (remote sha all zeros) has no remote commit to compare with."""
    updates: list[PushedUpdate] = []
    for line in lines:
        fields = line.split()
        if len(fields) != 4:
            continue
        local_ref, local_sha, _remote_ref, remote_sha = fields
        if _is_null(local_sha):
            continue
        updates.append(
            PushedUpdate(local_ref, local_sha, None if _is_null(remote_sha) else remote_sha)
        )
    return updates
