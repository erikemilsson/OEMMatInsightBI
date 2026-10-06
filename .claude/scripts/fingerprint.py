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
  --dashboard-rollup DIR  sorted task_id:status rollup hash
"""
import argparse
import hashlib
import json
import re
import sys
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


def hash_sections(path: Path, depth: int = 2) -> dict[str, str]:
    """Split on `## ` level headings. Each section = heading line + content until next
    `## ` or EOF. No trailing newline is added before hashing.

    `depth >= 3` ADDS `### ` subsection hashes (keyed by their heading line). The `## `
    section hashes are unchanged regardless of depth, so enabling depth 3 is purely
    additive — existing `## ` fingerprints never shift (no downstream drift churn)."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
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
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
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
      3. no spec_section or section_fingerprint → `no_provenance` (never flagged).
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
        "historical": 0, "unmatched": 0, "no_provenance": 0,
        "unreadable": [], "unreconciled_sections": 0,
    }
    spec_path = find_current_spec(claude_dir)
    if spec_path is None:
        return result
    stem = spec_path.stem
    number = stem[len("spec_v"):]
    current_names = {stem, number, "v" + number}  # A2: "spec_v3", "3" and "v3" all name it
    # stripped `## ` heading → current hash. An exact duplicate heading is already
    # last-wins inside hash_sections; setdefault keeps the first of two headings that
    # differ only in surrounding whitespace.
    headings: dict[str, str] = {}
    for heading, fp in hash_sections(spec_path).items():
        headings.setdefault(heading.strip(), fp)
    subsections, unique_subsections = _subsection_hashes(spec_path)
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
            result["no_provenance"] += 1
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
        "--dashboard-rollup",
        type=Path,
        help="Hash sorted task_id:status rollup (pass task dir, e.g. .claude/tasks).",
    )
    parser.add_argument(
        "--depth", type=int, default=2, choices=(2, 3),
        help="With --sections: 2 = ## only (default); 3 = also emit ### subsection hashes (additive).",
    )
    args = parser.parse_args()

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
    elif args.dashboard_rollup:
        if not args.dashboard_rollup.is_dir():
            print(f"error: not a directory: {args.dashboard_rollup}", file=sys.stderr)
            return 2
        print(hash_dashboard_rollup(args.dashboard_rollup))
    return 0


if __name__ == "__main__":
    sys.exit(main())
