#!/usr/bin/env python3
"""Deterministic hash computation for spec drift detection and dashboard freshness.

Mirrors .claude/support/reference/drift-reconciliation.md § "Spec Drift Detection"
(the hash recipes and the --drift rules). Any change to normalization or drift logic
here MUST be mirrored in that reference doc.

Modes:
  --spec FILE             full-file hash
  --sections FILE         per-`## ` section hashes (JSON map). With `--depth 3`, ALSO
                          emits per-`### ` subsection hashes (additive — the `## `
                          hashes are unchanged, so opting in causes no fingerprint
                          churn). [DEC-021 companion a]
  --index FILE            generated section index (JSON): per-`## ` section heading,
                          1-based line range, fingerprint, deterministic synopsis, plus
                          the full-spec fingerprint for freshness checks. [DEC-021]
  --drift DIR             per-task spec drift check (JSON) for a `.claude` dir: each
                          task's section_fingerprint vs. the current hash of the section
                          it names (a `## ` heading, or a `### ` heading that occurs
                          once), grouped by section, deferrals applied. Computed fresh
                          on every call, never cached; dashboard-render.py reuses
                          compute_drift(). [FB-128]
  --provenance DIR --section HEADING
                          the four provenance fields a new task for that section
                          carries (JSON); exit 1 when HEADING names no current spec
                          heading. [FB-135]
  --baseline DIR          one proposal (JSON) per task without section provenance:
                          the section hash the task was built against, taken from the
                          spec's git history at the task's date. [FB-135]
  --baseline DIR --write --ids ID[,ID...] [--confirm-current]
                          THE ONE WRITE MODE: stamps the listed proposals into their
                          task files (spec_section, section_fingerprint, a prepended
                          note, and spec_version when missing). [FB-135]
  --dashboard-rollup DIR  sorted task_id:status rollup hash

Read-only except `--baseline --write`. Git is only ever read (`rev-parse`, `log
--first-parent`, `show`, with GIT_OPTIONAL_LOCKS=0): never fetched, never written.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

if sys.version_info < (3, 10):  # Python floor (FB-120); see README § Invocation contract
    print(f"error: {Path(__file__).name} needs Python 3.10+; this is Python "
          f"{'.'.join(map(str, sys.version_info[:3]))} ({sys.executable})", file=sys.stderr)
    sys.exit(2)

SYNOPSIS_MAX = 120


def sha256_hex(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def _section_fingerprint(lines: list[str]) -> str:
    """sha256 of joined lines with trailing newlines stripped (matches `printf '%s'`)."""
    joined = "".join(lines).rstrip("\n")
    return sha256_hex(joined.encode("utf-8"))


def _spec_lines(path: Path) -> list[str]:
    """A spec file's lines as every section hash reads them: UTF-8, universal newlines
    (CRLF and lone CR read as LF), line ends kept."""
    return path.read_text(encoding="utf-8").splitlines(keepends=True)


def _lines_from_bytes(data: bytes) -> list[str]:
    """_spec_lines() for content that isn't a file (a spec blob at a git commit): the
    same bytes give the same lines, so the same hashes. Raises UnicodeDecodeError."""
    text = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return text.splitlines(keepends=True)


def hash_sections(path: Path, depth: int = 2) -> dict[str, str]:
    """Split on `## ` level headings. Each section = heading line + content until next
    `## ` or EOF. No trailing newline is added before hashing.

    `depth >= 3` ADDS `### ` subsection hashes (keyed by their heading line). The `## `
    section hashes are unchanged regardless of depth, so enabling depth 3 is purely
    additive — existing `## ` fingerprints never shift (no downstream drift churn)."""
    return _hash_section_lines(_spec_lines(path), depth)


def _hash_section_lines(lines: list[str], depth: int = 2) -> dict[str, str]:
    """hash_sections() on lines already read."""
    sections: dict[str, str] = {}
    current_heading: str | None = None
    current_lines: list[str] = []

    def flush():
        if current_heading is not None:
            sections[current_heading] = _section_fingerprint(current_lines)

    for line in lines:
        if re.match(r"^## (?!#)", line):
            flush()
            current_heading = line.rstrip("\n")
            current_lines = [line]
        elif current_heading is not None:
            current_lines.append(line)
    flush()

    if depth >= 3:
        sections.update(_hash_subsections(lines))
    return sections


def _hash_subsections(lines: list[str]) -> dict[str, str]:
    """Hash each `### ` subsection (heading + content until the next `### `/`## `/EOF).

    Keyed by the `### ` heading line. Two identical `### ` headings under different
    parents collide (last wins) — the same theoretical limit the `## ` map has; rare in
    practice and acceptable for navigational/finer-drift use."""
    subs: dict[str, str] = {}
    current_heading: str | None = None
    current_lines: list[str] = []

    def flush():
        if current_heading is not None:
            subs[current_heading] = _section_fingerprint(current_lines)

    for line in lines:
        if re.match(r"^### (?!#)", line):
            flush()
            current_heading = line.rstrip("\n")
            current_lines = [line]
        elif re.match(r"^## (?!#)", line):
            flush()
            current_heading = None
            current_lines = []
        elif current_heading is not None:
            current_lines.append(line)
    flush()
    return subs


def _synopsis(section_lines: list[str]) -> str:
    """First non-blank, non-heading content line of a section, trimmed + truncated.
    Deterministic (content-derived) so the index stays reproducible."""
    for line in section_lines[1:]:  # skip the heading line itself
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:SYNOPSIS_MAX]
    return ""


def build_index(path: Path) -> dict:
    """Generate the spec section index (DEC-021): per-`## ` section heading, 1-based
    line range, fingerprint, deterministic synopsis, plus the full-spec fingerprint.

    Enables section-scoped reads — a consumer locates the relevant `## ` section by
    heading and `Read`s only its line range instead of loading the whole spec. The
    top-level `spec_fingerprint` drives the freshness check (regenerate when it
    changes). Per-section `fingerprint` values are identical to `hash_sections(depth=2)`
    so the index and the drift map stay consistent."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    sections: list[dict] = []
    current: dict | None = None

    def flush(line_end: int):
        if current is not None:
            sec_lines = current["_lines"]
            sections.append({
                "heading": current["heading"],
                "line_start": current["line_start"],
                "line_end": line_end,
                "char_count": sum(len(l) for l in sec_lines),
                "fingerprint": _section_fingerprint(sec_lines),
                "synopsis": _synopsis(sec_lines),
            })

    for i, line in enumerate(lines, start=1):
        if re.match(r"^## (?!#)", line):
            flush(i - 1)
            current = {"heading": line.rstrip("\n"), "line_start": i, "_lines": [line]}
        elif current is not None:
            current["_lines"].append(line)
    flush(len(lines))

    return {
        "spec_file": path.name,
        "spec_fingerprint": hash_file(path),
        "section_count": len(sections),
        "sections": sections,
    }


def hash_dashboard_rollup(task_dir: Path) -> str:
    """SHA-256 of sorted 'task_id:status\\n' lines across task-*.json files in task_dir.
    Not the dashboard freshness hash: that is dashboard-render.py --task-hash (META task_hash)."""
    entries = []
    for task_file in sorted(task_dir.glob("task-*.json")):
        try:
            data = json.loads(task_file.read_text(encoding="utf-8"))
            entries.append(f"{data['id']}:{data['status']}")
        except (json.JSONDecodeError, KeyError) as e:
            print(f"warning: skipping {task_file.name} ({e})", file=sys.stderr)
    entries.sort()
    joined = "\n".join(entries)
    return sha256_hex(joined.encode("utf-8"))


# ------------------------------------------------------- --drift (FB-128)

DRIFT_SKIPPED = ("Absorbed", "Broken Down")  # their subtasks/absorber carry the provenance


def _natural_key(value) -> list:
    """Natural sort key: digit runs compare as numbers ('2' < '2_1' < '10', 'T9' < 'T10')."""
    parts = re.split(r"(\d+)", str(value))
    return [(0, int(p)) if i % 2 else (1, p) for i, p in enumerate(parts) if p]


def _sorted_naturally(values):
    return sorted(values, key=lambda v: (_natural_key(v), v))


def _text(value) -> str:
    """Stripped string; '' for a missing, blank or non-string value."""
    return value.strip() if isinstance(value, str) else ""


def find_current_spec(claude_dir: Path) -> Path | None:
    """The single `spec_v{N}.md`; with several, the highest N (numeric), as
    dashboard-render.py's load_spec picks it."""
    specs = sorted((p for p in claude_dir.glob("spec_v*.md") if p.is_file()),
                   key=lambda p: _natural_key(p.stem[len("spec_v"):]))
    return specs[-1] if specs else None


def _subsection_hashes(path: Path) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """`### ` hashes (same recipe as `--sections --depth 3`), keyed by stripped heading,
    two ways: grouped under their `## ` section, so a task's spec_subsection resolves
    inside its own section (A3; `### Acceptance Criteria` may repeat per section); and
    spec-wide for the headings that occur exactly once, which is what a `### `
    spec_section must name (A1)."""
    return _subsection_hashes_lines(_spec_lines(path))


def _subsection_hashes_lines(lines: list[str]) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """_subsection_hashes() on lines already read."""
    grouped: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in lines:
        if re.match(r"^## (?!#)", line):
            current = grouped.setdefault(line.strip(), [])
        if current is not None:
            current.append(line)
    scoped = {h: {k.strip(): v for k, v in _hash_subsections(ls).items()}
              for h, ls in grouped.items()}
    counts = Counter(line.strip() for line in lines if re.match(r"^### (?!#)", line))
    unique = {k.strip(): v for k, v in _hash_subsections(lines).items() if counts[k.strip()] == 1}
    return scoped, unique


def _heading_hashes(lines: list[str]) -> dict[str, str]:
    """Stripped `## ` heading → section hash. An exact duplicate heading is already
    last-wins inside the section hashing; setdefault keeps the first of two headings
    that differ only in surrounding whitespace."""
    headings: dict[str, str] = {}
    for heading, fp in _hash_section_lines(lines).items():
        headings.setdefault(heading.strip(), fp)
    return headings


def _match_section(s: str, headings: dict[str, str], unique_subsections: dict[str, str]):
    """Rule 4 for a stripped spec_section: (heading, current hash, is_subsection), or
    None. A `## ` heading matches first (as is, or with "## " prefixed); failing that, a
    `### ` value must name exactly one current `### ` heading (A1)."""
    for heading in (s, "## " + s):
        if heading in headings:
            return heading, headings[heading], False
    if s.startswith("### ") and s in unique_subsections:
        return s, unique_subsections[s], True
    return None


def load_drift_deferrals(claude_dir: Path) -> list[dict]:
    """Usable `drift-deferrals.json` entries. The file holds `{"deferrals": [...]}` or a
    bare list; any other shape, an unreadable file, and entries that aren't objects with
    a string `section` are ignored."""
    try:
        data = json.loads((claude_dir / "drift-deferrals.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = data.get("deferrals") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    return [e for e in items if isinstance(e, dict) and isinstance(e.get("section"), str)]


def _defers(deferral: dict, task_id: str) -> bool:
    """A non-empty `affected_tasks` list defers only those tasks; otherwise all of them."""
    affected = deferral.get("affected_tasks")
    if isinstance(affected, list) and affected:
        return task_id in {str(t) for t in affected}
    return True


def compute_drift(claude_dir: Path) -> dict:
    """Per-task spec drift check (FB-128): each task's `section_fingerprint` against the
    current hash of its `## ` section. Read-only, computed fresh on every call (a
    cached copy would be a second thing to go stale). Rule order, first match wins:
      1. Absorbed / Broken Down, or out_of_spec true → skipped, counted nowhere (A6).
      2. spec_version names another spec → Finished: `historical`; otherwise listed
         in `unmigrated`. Missing, the current stem (spec_v3), its number (3) and v3
         all count as current (A2).
      3. no spec_section or section_fingerprint → `unmapped` when spec_unmapped is
         true (in-spec work that belongs to no single section, FB-135), otherwise
         `no_provenance`. Never flagged either way.
      4. spec_section must equal a current `## ` heading (both stripped), or equal it
         once "## " is prefixed; failing that, a `### ` value matches when exactly one
         current `### ` heading has that text, and is compared with that subsection's
         hash (A1). No match, or several `### ` matches → Finished: `unmatched` (count
         only); otherwise listed in `missing` under the section name.
      5. matched → `checked`; fingerprint equal to the current hash → in sync.
      6. different → `drifted` under the matched heading. `subsection_unchanged` when a
         `## `-matched task's spec_subsection, looked up inside that section only (A3),
         still hashes to its recorded subsection_fingerprint (DEC-021); always false
         for a task matched by its `### ` heading.
    Deferrals in drift-deferrals.json mark drifted tasks `deferred`. A section is
    unreconciled when it has a non-deferred drifted task, or is missing.
    The prose home is drift-reconciliation.md § "Spec Drift Detection"."""
    claude_dir = Path(claude_dir)
    result = {
        "spec": None, "spec_fingerprint": None, "checked": 0,
        "drifted": [], "missing": [], "unmigrated": [],
        "historical": 0, "unmatched": 0, "no_provenance": 0, "unmapped": 0,
        "unreadable": [], "unreconciled_sections": 0,
    }
    spec_path = find_current_spec(claude_dir)
    if spec_path is None:
        return result
    stem = spec_path.stem
    number = stem[len("spec_v"):]
    current_names = {stem, number, "v" + number}  # A2: "spec_v3", "3" and "v3" all name it
    lines = _spec_lines(spec_path)
    headings = _heading_hashes(lines)  # stripped `## ` heading → current hash
    subsections, unique_subsections = _subsection_hashes_lines(lines)
    result["spec"] = stem
    result["spec_fingerprint"] = hash_file(spec_path)

    drifted: dict[str, list[dict]] = {}
    drifted_hash: dict[str, str] = {}  # heading → its current hash
    missing: dict[str, list[dict]] = {}
    tasks_dir = claude_dir / "tasks"
    task_files = sorted(tasks_dir.glob("task-*.json")) if tasks_dir.is_dir() else []
    for path in task_files:  # non-recursive: archive/ is never a candidate
        try:
            task = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            task = None
        if not isinstance(task, dict):
            result["unreadable"].append(path.name)
            continue
        status = task.get("status") if isinstance(task.get("status"), str) else "Pending"
        if status in DRIFT_SKIPPED or task.get("out_of_spec") is True:
            continue  # an out-of-spec task has no section to drift from (A6)
        summary = {
            "id": str(task["id"]) if task.get("id") is not None else path.stem[len("task-"):],
            "title": str(task.get("title") or ""),
            "status": status,
            "owner": task.get("owner") or "claude",
        }
        version = _text(task.get("spec_version"))
        if version and version not in current_names:
            if status == "Finished":
                result["historical"] += 1
            else:
                result["unmigrated"].append(summary["id"])
            continue
        section, fingerprint = _text(task.get("spec_section")), _text(task.get("section_fingerprint"))
        if not section or not fingerprint:
            result["unmapped" if task.get("spec_unmapped") is True else "no_provenance"] += 1
            continue
        match = _match_section(section, headings, unique_subsections)
        if match is None:
            if status == "Finished":
                result["unmatched"] += 1
            else:
                missing.setdefault(section, []).append(summary)
            continue
        heading, current, by_subsection = match
        result["checked"] += 1
        if fingerprint == current:
            continue
        sub, sub_fp = _text(task.get("spec_subsection")), _text(task.get("subsection_fingerprint"))
        summary["deferred"] = False
        summary["subsection_unchanged"] = bool(
            not by_subsection and sub and sub_fp
            and subsections.get(heading, {}).get(sub) == sub_fp)
        drifted.setdefault(heading, []).append(summary)
        drifted_hash[heading] = current

    deferrals = load_drift_deferrals(claude_dir)
    for heading in _sorted_naturally(drifted):
        matching = [e for e in deferrals
                    if heading in (e["section"].strip(), "## " + e["section"].strip())]
        tasks = sorted(drifted[heading], key=lambda t: (_natural_key(t["id"]), t["id"]))
        for t in tasks:
            t["deferred"] = any(_defers(e, t["id"]) for e in matching)
        result["drifted"].append({
            "section": heading, "fingerprint": drifted_hash[heading],
            "deferred": all(t["deferred"] for t in tasks), "tasks": tasks,
        })
    for section in _sorted_naturally(missing):
        result["missing"].append({
            "section": section,
            "tasks": sorted(missing[section], key=lambda t: (_natural_key(t["id"]), t["id"])),
        })
    result["unmigrated"] = _sorted_naturally(result["unmigrated"])
    result["unreadable"] = _sorted_naturally(result["unreadable"])
    result["unreconciled_sections"] = (sum(1 for d in result["drifted"] if not d["deferred"])
                                       + len(result["missing"]))
    return result


# ------------------------------------- --provenance / --baseline (FB-135)

class BaselineError(Exception):
    """An exit-2 condition of --provenance / --baseline; main() prints the message."""


BASELINE_ACTIONS = ("stamp_history", "confirm_current", "needs_section", "report_only")
# `reason` values. Rule 1 (the recorded spec_section doesn't resolve):
REASON_NO_SECTION = "no spec_section"
REASON_UNRESOLVED = "spec_section names no current spec heading"
# Rule 2 (confirm_current), in the order they are tried:
REASON_NO_HISTORY = "the spec has no git history"
REASON_NO_DATE = "the task has no usable date"
REASON_MAY_PREDATE = "the task may predate this spec version"
REASON_NO_COMMIT = "no spec commit on or before the task's date"
REASON_UNREADABLE = "the spec can't be read at the commit for the task's date"
REASON_NOT_AT_COMMIT = "the section is not in the spec at the commit for the task's date"
# The task is older than the spec's history for its section: the current text is not
# what it was built against, and --write --confirm-current says so in its note.
REASONS_OLDER_THAN_HISTORY = (REASON_MAY_PREDATE, REASON_NO_COMMIT, REASON_NOT_AT_COMMIT)
# Rule 3 (stamp_history) when the section was edited on the reference date itself:
REASON_OWN_EDIT = "own spec edit"
REASON_FILED_AFTER = "task filed after the edit"


def compute_provenance(claude_dir: Path, section: str) -> dict | None:
    """The provenance fields of a new task for `section` (FB-135), or None when the
    value resolves to no current heading (rule 4 of compute_drift). `spec_section` is
    the real heading; for a `### ` match `section_fingerprint` is the subsection's hash.
    Raises BaselineError when the directory has no current spec."""
    spec_path = find_current_spec(Path(claude_dir))
    if spec_path is None:
        raise BaselineError(f"no spec_v*.md in {claude_dir}")
    lines = _spec_lines(spec_path)
    match = _match_section(_text(section), _heading_hashes(lines),
                           _subsection_hashes_lines(lines)[1])
    if match is None:
        return None
    return {"spec_version": spec_path.stem, "spec_fingerprint": hash_file(spec_path),
            "spec_section": match[0], "section_fingerprint": match[1]}


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess | None:
    """Run a read-only git command in cwd (stdout/stderr as bytes); None when git can't
    be run. GIT_OPTIONAL_LOCKS=0: no index refresh. GIT_LITERAL_PATHSPECS=1: the spec's
    name after `--` is a literal path."""
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_LITERAL_PATHSPECS="1")
    try:
        return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, env=env)
    except OSError:
        return None


class _SpecHistory:
    """The current spec file's commits and its section hashes at each of them.

    Git runs inside the `.claude` directory and names the spec relative to it (`log --
    spec_vN.md`, `show <commit>:./spec_vN.md`), so a project nested in a larger
    repository resolves to the right repo-relative path. `commits` is `(sha, committer
    date as YYYY-MM-DD)` in `git log --first-parent` order (newest first): a spec edit
    made on a side branch is dated by the merge that brought it in, and a
    fast-forwarded branch can't be told apart. The date is the calendar date in the
    committer's own timezone. Empty when the directory is not in a work tree, the spec
    is untracked, or git is missing. A commit's content is read and hashed at most
    once."""

    def __init__(self, claude_dir: Path, spec_name: str):
        self.claude_dir, self.spec_name = claude_dir, spec_name
        self._maps: dict[str, tuple[dict[str, str], dict[str, str]] | None] = {}
        self.commits: list[tuple[str, str]] = []
        inside = _git(claude_dir, "rev-parse", "--is-inside-work-tree")
        if inside is None or inside.returncode != 0 or inside.stdout.strip() != b"true":
            return
        # %cd with --date=short is the committer date as YYYY-MM-DD on any git version
        commits = [tuple(line.split()) for line in
                   self._log("--date=short", "--format=%H %cd", "--", spec_name)]
        self.commits = [c for c in commits if len(c) == 2 and _iso_date(c[1])]

    def _log(self, *args: str) -> list[str]:
        """Output lines of `git log --first-parent <args>`; none when git fails."""
        log = _git(self.claude_dir, "log", "--first-parent", *args)
        if log is None or log.returncode != 0:
            return []
        return log.stdout.decode("ascii", "replace").splitlines()

    def same_day_evidence(self, ref: str, task_file: str, names_spec: bool) -> list[tuple[str, str]]:
        """Git evidence that orders a task against the spec commits dated on its
        reference date, as `(sha, reason)` candidates, best first:
          (a) own edit: the task's files_affected names the spec (`names_spec`) and a
              spec commit of that day also touches the task's own file: the oldest such
              commit (a later one that touches the file may carry someone else's edit;
              a wrong pick must read as drift, never as in sync).
          (b) filed after the edit: the task file first enters git, not yet Finished,
              in or after a spec commit of that day: the newest of those at or before
              the task file's first commit. A file first committed as Finished proves
              nothing (the work may predate the edit and be committed later).
        Empty for a task file git doesn't track. Two `git log` calls and one
        `git show` at most."""
        path = "tasks/" + task_file
        touching = self._log("--format=%H", "--", path)  # newest first
        if not touching:
            return []
        day = [sha for sha, date in self.commits if date == ref]
        found = []
        own = next((sha for sha in reversed(day) if sha in touching), None) if names_spec else None
        if own:
            found.append((own, REASON_OWN_EDIT))
        order = {sha: i for i, sha in
                 enumerate(self._log("--format=%H", "--", self.spec_name, path))}
        first = order.get(touching[-1])
        filed = None if first is None else \
            next((sha for sha in day if order.get(sha, -1) >= first), None)
        if filed and self._open_at(touching[-1], path):
            found.append((filed, REASON_FILED_AFTER))
        return found

    def _open_at(self, sha: str, path: str) -> bool:
        """True when the task file at a commit parses as a task that is not Finished."""
        show = _git(self.claude_dir, "show", f"{sha}:./{path}")
        if show is None or show.returncode != 0:
            return False
        try:
            task = json.loads(show.stdout.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return False
        return isinstance(task, dict) and task.get("status") != "Finished"

    def _section_maps(self, sha: str):
        """(`## ` hashes, unique `### ` hashes) of the spec at a commit, both keyed by
        stripped heading; empty maps when the commit has no such file (it deleted the
        spec); None when the content is not UTF-8."""
        if sha not in self._maps:
            show = _git(self.claude_dir, "show", f"{sha}:./{self.spec_name}")
            if show is None or show.returncode != 0:
                self._maps[sha] = ({}, {})
            else:
                try:
                    lines = _lines_from_bytes(show.stdout)
                except UnicodeDecodeError:
                    self._maps[sha] = None
                else:
                    self._maps[sha] = (_heading_hashes(lines), _subsection_hashes_lines(lines)[1])
        return self._maps[sha]

    def section_hash(self, sha: str, heading: str, by_subsection: bool) -> tuple[str | None, bool]:
        """(hash of `heading` in the spec at `sha`, readable). The hash is None when the
        heading isn't there (a `### ` heading: isn't there exactly once)."""
        maps = self._section_maps(sha)
        if maps is None:
            return None, False
        return maps[1 if by_subsection else 0].get(heading), True


def _iso_date(value) -> str | None:
    """The leading `YYYY-MM-DD` of a string when it is a real calendar date, else None."""
    head = _text(value)[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", head):
        return None
    try:
        datetime.date.fromisoformat(head)
    except ValueError:
        return None
    return head


def _reference_date(task: dict, status: str) -> tuple[str | None, str | None]:
    """(date, field) a task's baseline is taken at: `completion_date` when Finished,
    falling back to `task_verification.timestamp` then `created_date` when a field is
    missing, null or blank; `created_date` for any other status. `updated_date` is never
    used: later, unrelated writes move it past the day the work was done. The field that
    is used must start with a real `YYYY-MM-DD`, or the task has no reference date (no
    further fallback: a later field would date the task later than it says)."""
    fields = ("completion_date", "task_verification.timestamp", "created_date") \
        if status == "Finished" else ("created_date",)
    for field in fields:
        value = task
        for key in field.split("."):
            value = value.get(key) if isinstance(value, dict) else None
        if value is not None and (not isinstance(value, str) or value.strip()):
            date = _iso_date(value)
            return (date, field) if date else (None, None)
    return None, None


def _no_spec_version(task: dict) -> bool:
    """The task records no spec_version (missing, null or blank)."""
    version = task.get("spec_version")
    return version is None or (isinstance(version, str) and not version.strip())


def _propose(task: dict, status: str, headings: dict[str, str], unique_subsections: dict[str, str],
             history: _SpecHistory, task_file: str) -> dict:
    """The baseline proposal fields for one task (action onward). Rule order as in
    compute_baseline()."""
    out = {"action": "", "spec_section": None, "section_fingerprint": None,
           "reference_date": None, "reference_field": None, "commit": None,
           "commit_date": None, "changed_since": False, "same_day_edit": False, "reason": ""}
    out["reference_date"], out["reference_field"] = _reference_date(task, status)
    recorded = _text(task.get("spec_section"))
    match = _match_section(recorded, headings, unique_subsections) if recorded else None
    if match is None:  # rule 1
        out["action"] = "report_only" if status == "Finished" else "needs_section"
        out["reason"] = REASON_UNRESOLVED if recorded else REASON_NO_SECTION
        return out
    heading, current, by_subsection = match
    out["spec_section"] = heading

    def confirm(reason: str) -> dict:  # rule 2
        out.update(action="confirm_current", section_fingerprint=current, reason=reason)
        return out

    ref = out["reference_date"]
    if not history.commits:
        return confirm(REASON_NO_HISTORY)
    if ref is None:
        return confirm(REASON_NO_DATE)
    commits = history.commits
    if _no_spec_version(task) and ref <= commits[-1][1]:
        # Nothing says the task was built against this spec file, and it is no younger
        # than the file's first commit: it may belong to the version before.
        return confirm(REASON_MAY_PREDATE)
    chosen = next((i for i, c in enumerate(commits) if c[1] <= ref), None)
    if chosen is None:
        return confirm(REASON_NO_COMMIT)
    fingerprint, readable = history.section_hash(commits[chosen][0], heading, by_subsection)
    if fingerprint is None:
        return confirm(REASON_NOT_AT_COMMIT if readable else REASON_UNREADABLE)
    if commits[chosen][1] == ref and chosen + 1 < len(commits):
        # The spec was committed on the reference date itself, and a date can't order
        # that against the task. Compare with the spec as the day began: the newest
        # commit dated before it, or, when the spec's history starts that day, its
        # oldest commit. If the section differs there, git evidence about the task's
        # own file decides (same_day_evidence); without any, take the earlier text.
        earlier = next((i for i in range(chosen + 1, len(commits)) if commits[i][1] < ref),
                       len(commits) - 1)
        before, _ = history.section_hash(commits[earlier][0], heading, by_subsection)
        if before is not None and before != fingerprint:
            out["same_day_edit"] = True
            chosen, fingerprint = earlier, before
            affected = task.get("files_affected")
            names_spec = isinstance(affected, list) and any(
                isinstance(f, str) and Path(f).name == history.spec_name for f in affected)
            for sha, reason in history.same_day_evidence(ref, task_file, names_spec):
                at_commit, _ = history.section_hash(sha, heading, by_subsection)
                if at_commit is not None:
                    chosen = next(i for i, c in enumerate(commits) if c[0] == sha)
                    fingerprint, out["reason"] = at_commit, reason
                    break
    out.update(action="stamp_history", section_fingerprint=fingerprint,
               commit=commits[chosen][0], commit_date=commits[chosen][1],
               changed_since=fingerprint != current)
    return out


def _baseline(claude_dir: Path, also: frozenset = frozenset()) -> tuple[dict, dict[str, list[dict]]]:
    """compute_baseline()'s result, plus, for --write's idempotence check, what the
    proposal would be for each task in `also` that already has section provenance
    (id → [{"task", "proposal", "current": the section's current hash}])."""
    claude_dir = Path(claude_dir)
    result = {"spec": None, "history": "none", "tasks": [],
              "counts": {action: 0 for action in BASELINE_ACTIONS}}
    stamped: dict[str, list[dict]] = {}
    spec_path = find_current_spec(claude_dir)
    if spec_path is None:
        return result, stamped
    stem = spec_path.stem
    number = stem[len("spec_v"):]
    current_names = {stem, number, "v" + number}
    lines = _spec_lines(spec_path)
    headings = _heading_hashes(lines)
    unique_subsections = _subsection_hashes_lines(lines)[1]
    history = _SpecHistory(claude_dir, spec_path.name)
    result["spec"] = stem
    result["history"] = "git" if history.commits else "none"

    tasks_dir = claude_dir / "tasks"
    task_files = sorted(tasks_dir.glob("task-*.json")) if tasks_dir.is_dir() else []
    for path in task_files:
        try:
            task = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(task, dict):
            continue
        # rules 1-3 of compute_drift: which tasks are no-provenance tasks
        status = task.get("status") if isinstance(task.get("status"), str) else "Pending"
        if status in DRIFT_SKIPPED or task.get("out_of_spec") is True:
            continue
        version = _text(task.get("spec_version"))
        if version and version not in current_names:
            continue
        task_id = str(task["id"]) if task.get("id") is not None else path.stem[len("task-"):]
        has_provenance = bool(_text(task.get("spec_section")) and _text(task.get("section_fingerprint")))
        if has_provenance and task_id not in also:
            continue
        if not has_provenance and task.get("spec_unmapped") is True:
            continue
        recorded = task.get("spec_section")
        entry = {"id": task_id, "file": path.name, "status": status,
                 "title": str(task.get("title") or ""),
                 "recorded_section": recorded if isinstance(recorded, str) else None}
        entry.update(_propose(task, status, headings, unique_subsections, history, path.name))
        if has_provenance:
            match = _match_section(_text(task.get("spec_section")), headings, unique_subsections)
            stamped.setdefault(task_id, []).append(
                {"task": task, "proposal": entry, "current": match[1] if match else None})
        else:
            result["tasks"].append(entry)
            result["counts"][entry["action"]] += 1
    result["tasks"].sort(key=lambda t: (_natural_key(t["id"]), t["id"], t["file"]))
    return result, stamped


def compute_baseline(claude_dir: Path) -> dict:
    """One provenance proposal per no-provenance task (FB-135): a task compute_drift()
    counts in `no_provenance` (not the `unmapped` ones). Read-only. The reference date
    is _reference_date(); the spec's history is _SpecHistory. Action, first match wins:
      1. the recorded spec_section is blank or resolves to no current heading (rule 4
         of compute_drift) → `report_only` when Finished, else `needs_section`.
      2. no git history for the spec, no reference date, a task with no spec_version
         dated on or before the spec file's oldest commit (it may predate this spec
         version), no spec commit dated on or before the reference date, or the
         resolved heading missing (a `### ` one: not unique) or the spec unreadable at
         that commit → `confirm_current`, carrying the CURRENT hash; `reason` says
         which.
      3. otherwise `stamp_history`: the section's hash at the newest commit dated on or
         before the reference date. When that commit is dated on the reference date
         and the section's hash differs at the newest commit dated before it (or, when
         there is none, at the spec's oldest commit), `same_day_edit` is true and the
         commit is chosen from git evidence, first match wins: (a) the task's
         files_affected names the spec and a spec commit of that day also touches the
         task's own file → the newest such commit, `reason` "own spec edit"; (b) the
         task file first enters git in or after a spec commit of that day → the newest
         of those at or before the task file's first commit, `reason` "task filed after
         the edit"; (c) otherwise the earlier commit, `reason` "". `changed_since`: the
         stamped hash differs from the current one, so the next drift check reports the
         task.
    History-dated hashes assume the spec was edited on the line the task was built on
    (see _SpecHistory)."""
    return _baseline(claude_dir)[0]


def _stamped_task(task: dict, proposal: dict, stem: str, note: str) -> dict:
    """The task with the baseline applied: spec_section, section_fingerprint, the note
    prepended to notes, and spec_version when missing or blank. Existing keys keep
    their position; a new section_fingerprint goes right after spec_section, a new
    spec_version right before it, new notes last. Raises BaselineError for notes that
    are neither text nor a list."""
    notes = task.get("notes")
    if notes is None or (isinstance(notes, str) and not notes.strip()):
        new_notes = note
    elif isinstance(notes, str):
        new_notes = note + " " + notes  # work-procedures.md: every notes write prepends
    elif isinstance(notes, list):
        new_notes = [note, *notes]
    else:
        raise BaselineError(f"notes is {type(notes).__name__}, not text or a list")
    set_version = _no_spec_version(task)
    new: dict = {}
    for key, value in task.items():
        if key == "spec_section":
            if set_version and "spec_version" not in task:
                new["spec_version"] = stem
            new[key] = proposal["spec_section"]
            if "section_fingerprint" not in task:
                new["section_fingerprint"] = proposal["section_fingerprint"]
        elif key == "section_fingerprint":
            new[key] = proposal["section_fingerprint"]
        elif key == "spec_version" and set_version:
            new[key] = stem
        elif key == "notes":
            new[key] = new_notes
        else:
            new[key] = value
    new["notes"] = new_notes
    return new


def _serialize_like(original: str, data: dict) -> str:
    """`data` as JSON in the layout of `original`: its indent (spaces, tab, or one
    line), line ending, trailing whitespace, and raw vs. escaped non-ASCII."""
    body = original.rstrip()
    indent_match = re.search(r"\n([ \t]+)\S", body)
    indent = indent_match.group(1) if indent_match else None
    if indent is not None and set(indent) == {" "}:
        indent = len(indent)
    text = json.dumps(data, indent=indent, ensure_ascii=original.isascii())
    if "\r\n" in original:
        text = text.replace("\n", "\r\n")
    return text + original[len(body):]


def _replace_file(path: Path, data: bytes) -> None:
    """Atomic write: a temp file beside `path`, then os.replace. Keeps the file mode."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, stat.S_IMODE(path.stat().st_mode))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


CONFIRMED_NOTE = "[BASELINE] section_fingerprint set to the current section text on "


def _unique_keys(pairs: list[tuple]) -> dict:
    """json object_pairs_hook: a dict, or ValueError on a repeated key (json.loads
    keeps only the last one, so re-serialising would drop the others)."""
    data = dict(pairs)
    if len(data) != len(pairs):
        repeated = next(k for k, n in Counter(k for k, _ in pairs).items() if n > 1)
        raise ValueError(f"duplicate key '{repeated}'")
    return data


def _confirmed_before(task: dict, current: str | None) -> bool:
    """The task carries a --confirm-current note and still has the current section
    hash. Such a write may have set spec_version, which changes what would be proposed
    for the task now; a rerun reports it `unchanged` all the same."""
    notes = task.get("notes")
    notes = notes if isinstance(notes, list) else [notes]
    return current is not None and task.get("section_fingerprint") == current and any(
        isinstance(n, str) and CONFIRMED_NOTE in n for n in notes)


def write_baseline(claude_dir: Path, ids: list[str], confirm_current: bool = False,
                   today: str | None = None) -> dict:
    """`--baseline --write`: stamp the proposals for `ids` into their task files. Every
    id is checked and every new file body is built and encoded before the first write;
    any id that can't be written raises BaselineError and nothing is written. Refused
    that way: an id that is not a proposal or is used by two task files, a task file
    that is not a regular file, has more than one hard link, repeats a JSON key, can't
    be encoded, or has notes of an unusable type. The one failure after the first
    write is an I/O error while writing: BaselineError names the ids already written,
    and a rerun finishes. An id whose task already carries exactly the proposed
    spec_section and section_fingerprint is reported `unchanged`. Touches only
    spec_section, section_fingerprint, notes and a missing/blank spec_version; never
    updated_date (a changed updated_date would invalidate a phase-level verification
    result)."""
    claude_dir = Path(claude_dir)
    today = today or datetime.date.today().isoformat()
    wanted = list(dict.fromkeys(ids))
    result, stamped = _baseline(claude_dir, frozenset(wanted))
    proposals: dict[str, list[dict]] = {}
    for entry in result["tasks"]:
        proposals.setdefault(entry["id"], []).append(entry)

    refused: dict[str, list[str]] = {}
    plan: list[tuple[dict, Path, bytes]] = []
    unchanged: list[str] = []
    for task_id in wanted:
        found = proposals.get(task_id, [])
        if len(found) + len(stamped.get(task_id, [])) > 1:
            refused.setdefault("id used by more than one task file", []).append(task_id)
            continue
        if not found:
            done = stamped.get(task_id)
            if (done and done[0]["proposal"]["section_fingerprint"] is not None
                    and done[0]["task"].get("spec_section") == done[0]["proposal"]["spec_section"]
                    and (done[0]["task"].get("section_fingerprint") == done[0]["proposal"]["section_fingerprint"]
                         or _confirmed_before(done[0]["task"], done[0]["current"]))):
                unchanged.append(task_id)
            else:
                refused.setdefault("not a baseline proposal", []).append(task_id)
            continue
        entry = found[0]
        if entry["action"] in ("needs_section", "report_only"):
            refused.setdefault(f"{entry['action']} (no section to stamp)", []).append(task_id)
            continue
        if entry["action"] == "confirm_current":
            if not confirm_current:
                refused.setdefault("confirm_current needs --confirm-current", []).append(task_id)
                continue
            note = CONFIRMED_NOTE + today + (
                ", accepted by the user as the task's baseline."
                if entry["reason"] in REASONS_OLDER_THAN_HISTORY
                else ", confirmed by the user as what the task was built against.")
        else:
            note = ("[BASELINE] section_fingerprint stamped from the spec at "
                    f"{entry['commit'][:7]} ({entry['commit_date']}); the task records no "
                    "hash of its own.")
        path = claude_dir / "tasks" / entry["file"]
        try:
            info = os.lstat(path)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("not a regular file")  # a symlink would be replaced by a file
            if info.st_nlink > 1:
                raise ValueError("more than one hard link")  # the other names would keep the old text
            original = path.read_bytes().decode("utf-8")
            task = json.loads(original, object_pairs_hook=_unique_keys)
            if not isinstance(task, dict):
                raise ValueError("not a JSON object")
            data = _serialize_like(original, _stamped_task(task, entry, result["spec"], note)).encode("utf-8")
        except (OSError, ValueError, BaselineError) as e:  # ValueError: bad JSON, a lone surrogate
            refused.setdefault(f"task file can't be rewritten ({e})", []).append(task_id)
            continue
        plan.append((entry, path, data))
    if refused:
        raise BaselineError("nothing written; " + "; ".join(
            f"{why}: {', '.join(_sorted_naturally(found))}" for why, found in refused.items()))

    written = []
    for entry, path, data in plan:
        try:
            _replace_file(path, data)
        except OSError as e:
            raise BaselineError(
                f"write failed at task {entry['id']} ({e}); already written: "
                f"{', '.join(w['id'] for w in written) or 'none'}; a rerun finishes") from e
        written.append({key: entry[key] for key in
                        ("id", "file", "action", "spec_section", "section_fingerprint", "changed_since")})
    return {"written": written, "unchanged": unchanged}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic hashes for spec drift and dashboard freshness."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--spec", type=Path,
        help="Hash full spec file contents. Prints the BARE 'sha256:...' string "
             "(not JSON — unlike --sections/--index).")
    group.add_argument("--sections", type=Path, help="Hash each ## section; JSON map to stdout.")
    group.add_argument(
        "--index", type=Path,
        help="Emit the spec section index (JSON) to stdout for scoped reads. "
             "Does NOT write the file — redirect to .claude/spec_v{N}.index.json.")
    group.add_argument(
        "--drift", type=Path, metavar="DIR",
        help="Per-task spec drift check for a .claude directory (e.g. .claude); JSON to "
             "stdout. Read-only.")
    group.add_argument(
        "--provenance", type=Path, metavar="DIR",
        help="With --section: the provenance fields of a new task for that spec section "
             "(JSON). Exit 1 when the heading doesn't resolve. Read-only.")
    group.add_argument(
        "--baseline", type=Path, metavar="DIR",
        help="Propose section provenance for the tasks of a .claude directory that have "
             "none, from the spec's git history (JSON). Read-only unless --write is given.")
    group.add_argument(
        "--dashboard-rollup",
        type=Path,
        help="Hash sorted task_id:status rollup (pass task dir, e.g. .claude/tasks).",
    )
    parser.add_argument(
        "--depth", type=int, default=2, choices=(2, 3),
        help="With --sections: 2 = ## only (default); 3 = also emit ### subsection hashes (additive).",
    )
    parser.add_argument("--section", metavar="HEADING",
                        help="With --provenance: the spec heading the new task belongs to.")
    parser.add_argument("--write", action="store_true",
                        help="With --baseline: write the proposals for --ids into their task files.")
    parser.add_argument("--ids", metavar="ID[,ID...]",
                        help="With --baseline --write: the task ids to stamp.")
    parser.add_argument("--confirm-current", action="store_true",
                        help="With --baseline --write: also stamp confirm_current proposals "
                             "(the user confirmed, or accepted, the current section text).")
    args = parser.parse_args()
    if args.provenance is not None and args.section is None:
        parser.error("--provenance needs --section HEADING")
    if args.section is not None and args.provenance is None:
        parser.error("--section only applies to --provenance")
    if (args.write or args.ids is not None or args.confirm_current) and args.baseline is None:
        parser.error("--write, --ids and --confirm-current only apply to --baseline")
    ids = [i.strip() for i in (args.ids or "").split(",") if i.strip()]
    if args.write and not ids:
        parser.error("--write needs --ids ID[,ID...]")
    if not args.write and (args.ids is not None or args.confirm_current):
        parser.error("--ids and --confirm-current need --write")

    if args.spec:
        if not args.spec.is_file():
            print(f"error: not a file: {args.spec}", file=sys.stderr)
            return 2
        print(hash_file(args.spec))
    elif args.sections:
        if not args.sections.is_file():
            print(f"error: not a file: {args.sections}", file=sys.stderr)
            return 2
        print(json.dumps(hash_sections(args.sections, depth=args.depth), indent=2))
    elif args.index:
        if not args.index.is_file():
            print(f"error: not a file: {args.index}", file=sys.stderr)
            return 2
        print(json.dumps(build_index(args.index), indent=2))
    elif args.drift:
        if not args.drift.is_dir():
            print(f"error: not a directory: {args.drift}", file=sys.stderr)
            return 2
        try:
            result = compute_drift(args.drift)
        except (OSError, ValueError) as e:  # e.g. an unreadable spec file
            print(f"error: drift check failed: {e}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2))
    elif args.provenance is not None or args.baseline is not None:
        directory = args.provenance if args.provenance is not None else args.baseline
        if not directory.is_dir():
            print(f"error: not a directory: {directory}", file=sys.stderr)
            return 2
        try:
            if args.provenance is not None:
                result = compute_provenance(directory, args.section)
                if result is None:
                    print(f"error: no current spec heading matches '{args.section}'",
                          file=sys.stderr)
                    return 1
            elif args.write:
                result = write_baseline(directory, ids, args.confirm_current)
            else:
                result = compute_baseline(directory)
        except BaselineError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        except (OSError, ValueError) as e:  # e.g. an unreadable spec file, a failed write
            print(f"error: {'baseline' if args.baseline is not None else 'provenance'} "
                  f"failed: {e}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2))
    elif args.dashboard_rollup:
        if not args.dashboard_rollup.is_dir():
            print(f"error: not a directory: {args.dashboard_rollup}", file=sys.stderr)
            return 2
        print(hash_dashboard_rollup(args.dashboard_rollup))
    return 0


if __name__ == "__main__":
    sys.exit(main())
