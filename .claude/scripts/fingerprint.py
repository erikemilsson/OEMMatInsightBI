#!/usr/bin/env python3
"""Deterministic hash computation for spec drift detection and dashboard freshness.

Mirrors the recipe in .claude/support/reference/drift-reconciliation.md lines 70-84.
Any change to normalization logic here MUST be mirrored in that reference doc.

Modes:
  --spec FILE             full-file hash
  --sections FILE         per-`## ` section hashes (JSON map). With `--depth 3`, ALSO
                          emits per-`### ` subsection hashes (additive — the `## `
                          hashes are unchanged, so opting in causes no fingerprint
                          churn). [DEC-021 companion a]
  --index FILE            generated section index (JSON): per-`## ` section heading,
                          1-based line range, fingerprint, deterministic synopsis, plus
                          the full-spec fingerprint for freshness checks. [DEC-021]
  --dashboard-rollup DIR  sorted task_id:status rollup hash
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

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
    Mirrors the formula in commands/status.md line 36."""
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic hashes for spec drift and dashboard freshness."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--spec", type=Path, help="Hash full spec file contents.")
    group.add_argument("--sections", type=Path, help="Hash each ## section; JSON map to stdout.")
    group.add_argument("--index", type=Path, help="Emit the spec section index (JSON) for scoped reads.")
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
    elif args.dashboard_rollup:
        if not args.dashboard_rollup.is_dir():
            print(f"error: not a directory: {args.dashboard_rollup}", file=sys.stderr)
            return 2
        print(hash_dashboard_rollup(args.dashboard_rollup))
    return 0


if __name__ == "__main__":
    sys.exit(main())
