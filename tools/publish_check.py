#!/usr/bin/env python3
"""Pre-publication check for the repository.

Walks every file that would be published (everything under the repository root except what .gitignore
excludes and except .venv/, build/, .git/ and __pycache__/) and reports:

* DENYLIST HITS: any line of a text file, any file name and any folder name that matches one of the
  case-insensitive regular expressions in a private denylist file. Phrases that wrap across lines
  (with or without comment markers in between) are caught as well. Binary files are checked by name only.
* REVIEW ITEMS: patterns that are not forbidden words but are almost always provenance or personal
  data and need a human decision: UUIDs, absolute user paths, comments that date a decision with an
  attribution, and any code comment carrying a full date.

The denylist is read from the file named by PAPERDAEMON_DENYLIST, falling back to
../paperdaemon-private/denylist.txt next to the repository. It is deliberately kept outside the
repository: this script never contains, prints a copy of, or caches its contents.

An optional allowlist (PAPERDAEMON_ALLOWLIST, else allowlist.txt beside the denylist; also private) holds
regular expressions for ordinary words that happen to contain a fragment a broad denylist pattern matches:
a denylist hit is dropped only when one allowlist match covers it entirely. Review items a person has already
looked at and accepted are listed in tools/publish_check_reviewed.txt ("path-prefix kind" per line, kind:
uuid); denylist hits can never be waived.

Usage:  python tools/publish_check.py [--root DIR] [--denylist FILE] [--only PREFIX]... [--skip PREFIX]...

Exit status: 0 clean, 1 hits or review items found, 2 no denylist could be read.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALWAYS_SKIP_DIRS = {".git", ".venv", "build", "__pycache__"}
LOCKFILES = {"uv.lock", "package-lock.json", "poetry.lock"}
BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".pdf", ".ttf", ".otf", ".woff", ".woff2",
    ".dll", ".so", ".dylib", ".exe", ".pyd", ".zip", ".gz", ".7z", ".npy", ".npz", ".onnx", ".gguf",
    ".safetensors", ".rm", ".pyc", ".mp3", ".wav", ".ogg", ".mp4", ".webm", ".sqlite", ".db",
}

UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
# the home-folder names are split so that this file does not match its own pattern
USER_PATH_RE = re.compile(
    r"[A-Za-z]:[\\/]{1,4}(?:Users|Documents and Settings)[\\/]|/Us" r"ers/[^/\s]+/|/ho" r"me/[^/\s]+/", re.IGNORECASE
)

_DATE = (
    r"(?:20\d\d[-/.]\d\d(?:[-/.]\d\d)?"
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2}(?:, ?20\d\d)?)"
)
_ATTRIB = (
    r"(?:word|words|said|says|call|calls|asked|ask|decided|decision|verdict|rule|rules|approved|"
    r"go-ahead|wanted|wants|picked|ratified|signed off|sign-off)"
)
# an attribution word next to a parenthesized or bare date, in either order
DATED_ATTRIBUTION_RE = re.compile(
    rf"(?:\b{_ATTRIB}\b[^\n]{{0,40}}\(\s*{_DATE}\s*\)|\(\s*{_DATE}\s*\)[^\n]{{0,40}}\b{_ATTRIB}\b"
    rf"|\b{_ATTRIB}\b[^\n]{{0,12}}\b{_DATE}\b|\b{_DATE}\b[^\n]{{0,12}}\b{_ATTRIB}\b)",
    re.IGNORECASE,
)
# a dated provenance note inside a code comment: a full ISO date after the comment marker of the file's
# own language (so a markdown heading or a date in a string is not mistaken for a comment)
_ISO = r"\b20\d\d-\d\d-\d\d\b"
_HASH = re.compile(r"(?:^|\s)#[^\n]*" + _ISO)
_SLASH = re.compile(r"(?:^|\s)(?://|/\*)[^\n]*" + _ISO + r"|^\s*\*[^\n]*" + _ISO)
_HTML = re.compile(r"<!--[^\n]*" + _ISO)
COMMENT_DATE_BY_SUFFIX = {
    ".py": _HASH, ".toml": _HASH, ".yaml": _HASH, ".yml": _HASH, ".sh": _HASH, ".ps1": _HASH,
    ".js": _SLASH, ".mjs": _SLASH, ".ts": _SLASH, ".c": _SLASH, ".h": _SLASH, ".css": _SLASH,
    ".html": _HTML,
}


# ---------------------------------------------------------------- gitignore


def _pattern_to_regex(pattern: str) -> tuple[re.Pattern[str], bool, bool]:
    """Translate one .gitignore pattern to (regex, dir_only, negated)."""
    negated = pattern.startswith("!")
    if negated:
        pattern = pattern[1:]
    dir_only = pattern.endswith("/")
    pattern = pattern.rstrip("/")
    anchored = pattern.startswith("/") or "/" in pattern
    pattern = pattern.lstrip("/")
    out: list[str] = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*":
            if pattern[i : i + 2] == "**":
                i += 2
                if pattern[i : i + 1] == "/":
                    i += 1
                    out.append("(?:.*/)?")
                else:
                    out.append(".*")
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            j = pattern.find("]", i + 1)
            if j == -1:
                out.append(re.escape(c))
            else:
                out.append(pattern[i : j + 1])
                i = j
        else:
            out.append(re.escape(c))
        i += 1
    body = "".join(out)
    prefix = "^" if anchored else "^(?:.*/)?"
    return re.compile(prefix + body + "$"), dir_only, negated


class GitIgnore:
    def __init__(self, text: str) -> None:
        self.rules: list[tuple[re.Pattern[str], bool, bool]] = []
        for raw in text.splitlines():
            line = raw.rstrip()
            if not line or line.startswith("#"):
                continue
            self.rules.append(_pattern_to_regex(line))

    def ignored(self, rel: str, is_dir: bool) -> bool:
        result = False
        for regex, dir_only, negated in self.rules:
            if dir_only and not is_dir:
                continue
            if regex.match(rel):
                result = not negated
        return result


# ---------------------------------------------------------------- walking


def published_files(root: Path, skip: tuple[str, ...] = ()) -> tuple[list[Path], list[Path]]:
    """Return (files, directories) under root that would be published, as paths relative to root.
    `skip` holds extra relative-path prefixes (posix style) to leave out, for partial runs."""
    gi_path = root / ".gitignore"
    gitignore = GitIgnore(gi_path.read_text(encoding="utf-8", errors="replace")) if gi_path.exists() else GitIgnore("")
    files: list[Path] = []
    dirs: list[Path] = []
    for current, dirnames, filenames in os.walk(root):
        cur = Path(current)
        rel_dir = cur.relative_to(root)
        keep = []
        for name in sorted(dirnames):
            rel = (rel_dir / name).as_posix() if str(rel_dir) != "." else name
            if name in ALWAYS_SKIP_DIRS or gitignore.ignored(rel, True) or _skipped(rel, skip):
                continue
            keep.append(name)
            dirs.append(Path(rel))
        dirnames[:] = keep
        for name in sorted(filenames):
            rel = (rel_dir / name).as_posix() if str(rel_dir) != "." else name
            if gitignore.ignored(rel, False) or _skipped(rel, skip):
                continue
            files.append(Path(rel))
    return files, dirs


def _skipped(rel: str, skip: tuple[str, ...]) -> bool:
    return any(rel == s.rstrip("/") or rel.startswith(s.rstrip("/") + "/") for s in skip)


def is_binary(path: Path) -> bool:
    if path.suffix.lower() in BINARY_SUFFIXES:
        return True
    try:
        with open(path, "rb") as fh:
            return b"\0" in fh.read(8192)
    except OSError:
        return True


# ---------------------------------------------------------------- denylist


class Rules:
    """The denylist patterns plus an optional allowlist. A denylist match is dropped when one allowlist
    match covers it entirely, which lets a pattern that is too broad (it also matches ordinary words)
    keep working for everything else."""

    def __init__(self, deny: list[re.Pattern[str]], allow: list[re.Pattern[str]]) -> None:
        self.deny = deny
        self.allow = allow

    def __len__(self) -> int:
        return len(self.deny)

    def matches(self, text: str) -> list[re.Match[str]]:
        covered = [(m.start(), m.end()) for a in self.allow for m in a.finditer(text)] if self.allow else []
        out = []
        for pat in self.deny:
            for m in pat.finditer(text):
                if m.end() > m.start() and not any(s <= m.start() and m.end() <= e for s, e in covered):
                    out.append(m)
        return out


def _read_patterns(path: Path) -> list[re.Pattern[str]]:
    patterns = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            patterns.append(re.compile(line, re.IGNORECASE))
        except re.error:
            # not a valid regular expression (a Windows path, say): match it literally,
            # with either kind of slash
            literal = re.escape(line).replace("\\\\", r"[\\/]+")
            patterns.append(re.compile(literal, re.IGNORECASE))
    return patterns


def load_rules(explicit: str | None, root: Path) -> tuple[Rules, Path] | None:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    elif os.environ.get("PAPERDAEMON_DENYLIST"):
        candidates.append(Path(os.environ["PAPERDAEMON_DENYLIST"]))
    candidates.append(root.parent / "paperdaemon-private" / "denylist.txt")
    for cand in candidates:
        if cand.is_file():
            allow_path = os.environ.get("PAPERDAEMON_ALLOWLIST")
            allow_file = Path(allow_path) if allow_path else cand.with_name("allowlist.txt")
            allow = _read_patterns(allow_file) if allow_file.is_file() else []
            return Rules(_read_patterns(cand), allow), cand
    return None


_MARKER_RE = re.compile(r"^[\s#/*>\-+\"'`|]+")


def joined_with_offsets(lines: list[str]) -> tuple[str, list[int]]:
    """Join lines into one string (comment markers stripped) and return the line number of each character."""
    parts: list[str] = []
    owner: list[int] = []
    for number, line in enumerate(lines, 1):
        stripped = _MARKER_RE.sub("", line.rstrip("\r\n")).rstrip()
        if parts:
            parts.append(" ")
            owner.append(number)
        parts.append(stripped)
        owner.extend([number] * len(stripped))
    return "".join(parts), owner


# ---------------------------------------------------------------- checking


_REVIEWED_CACHE: dict[Path, list[tuple[str, str]]] = {}


def _reviewed_kinds(root: Path, rel: str) -> set[str]:
    """Kinds of review item a person has already looked at for this file, from tools/publish_check_reviewed.txt:
    one `path-prefix kind` per line (kind: uuid). Denylist hits can never be waived."""
    if root not in _REVIEWED_CACHE:
        entries = []
        path = root / "tools" / "publish_check_reviewed.txt"
        if path.is_file():
            for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
                parts = raw.split()
                if len(parts) == 2 and not raw.lstrip().startswith("#"):
                    entries.append((parts[0], parts[1]))
        _REVIEWED_CACHE[root] = entries
    return {kind for prefix, kind in _REVIEWED_CACHE[root] if rel == prefix or rel.startswith(prefix.rstrip("/") + "/")}


def check(root: Path, rules: Rules, skip: tuple[str, ...] = (), only: tuple[str, ...] = ()) -> tuple[list[str], list[str]]:
    hits: list[str] = []
    review: list[str] = []
    files, dirs = published_files(root, skip)
    if only:
        files = [f for f in files if _skipped(f.as_posix(), only)]
        dirs = [d for d in dirs if _skipped(d.as_posix(), only)]

    for rel in [*dirs, *files]:
        for segment in rel.parts:
            for m in rules.matches(segment):
                hits.append(f"{rel.as_posix()}: (name) {m.group(0)}")

    for rel in files:
        path = root / rel
        if is_binary(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            hits.append(f"{rel.as_posix()}: unreadable ({exc})")
            continue
        lines = text.splitlines()
        shown = rel.as_posix()

        seen: set[tuple[int, str]] = set()
        for number, line in enumerate(lines, 1):
            for m in rules.matches(line):
                seen.add((number, m.group(0).lower()))
                hits.append(f"{shown}:{number}: {m.group(0)}")
        joined, owner = joined_with_offsets(lines)
        for m in rules.matches(joined):
            first, last = owner[m.start()], owner[m.end() - 1]
            if first != last and (first, m.group(0).lower()) not in seen:
                hits.append(f"{shown}:{first}: {m.group(0)} (wraps to line {last})")

        if rel.name in LOCKFILES:
            continue
        reviewed = _reviewed_kinds(root, shown)
        for number, line in enumerate(lines, 1):
            for m in UUID_RE.finditer(line):
                if "uuid" not in reviewed:
                    review.append(f"{shown}:{number}: UUID {m.group(0)}")
            for m in USER_PATH_RE.finditer(line):
                review.append(f"{shown}:{number}: absolute user path {m.group(0)}")
            m = DATED_ATTRIBUTION_RE.search(line)
            if m:
                review.append(f"{shown}:{number}: dated attribution: {m.group(0).strip()}")
            elif (pat := COMMENT_DATE_BY_SUFFIX.get(rel.suffix.lower())) and pat.search(line):
                review.append(f"{shown}:{number}: dated comment: {line.strip()[:100]}")
    return hits, review


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=str(ROOT), help="repository root (default: the folder above tools/)")
    ap.add_argument("--denylist", default=None, help="denylist file (default: $PAPERDAEMON_DENYLIST)")
    ap.add_argument(
        "--skip", action="append", default=[], metavar="PREFIX",
        help="leave out a relative path prefix (repeatable); for partial runs while a clean-up is in progress",
    )
    ap.add_argument(
        "--only", action="append", default=[], metavar="PREFIX",
        help="check only paths under this relative prefix (repeatable); for partial runs",
    )
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    root = Path(args.root).resolve()
    loaded = load_rules(args.denylist, root)
    if loaded is None:
        print(
            "publish_check: no denylist found. Set PAPERDAEMON_DENYLIST to its path, or place it at "
            "../paperdaemon-private/denylist.txt next to the repository.",
            file=sys.stderr,
        )
        return 2
    rules, _where = loaded
    hits, review = check(root, rules, tuple(args.skip), tuple(args.only))

    if hits:
        print(f"DENYLIST HITS ({len(hits)}):")
        for h in hits:
            print("  " + h)
    if review:
        print(f"REVIEW ITEMS ({len(review)}):")
        for r in review:
            print("  " + r)
    if not hits and not review:
        print(f"publish_check: clean ({len(rules)} patterns)")
        return 0
    print(f"publish_check: {len(hits)} hit(s), {len(review)} review item(s)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
