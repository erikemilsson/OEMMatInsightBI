#!/usr/bin/env python3
"""Deterministic hash computation for spec drift detection and dashboard freshness.

Mirrors the recipe in .claude/support/reference/drift-reconciliation.md lines 70-84.
Any change to normalization logic here MUST be mirrored in that reference doc.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


def sha256_hex(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def hash_sections(path: Path) -> dict[str, str]:
    """Split on `## ` level headings. Each section = heading line + content until next `## ` or EOF.
    No trailing newline is added before hashing (matches `printf '%s'` behavior)."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    sections: dict[str, str] = {}
    current_heading: str | None = None
    current_lines: list[str] = []

    def flush():
        if current_heading is not None:
            joined = "".join(current_lines).rstrip("\n")
            sections[current_heading] = sha256_hex(joined.encode("utf-8"))

    for line in lines:
        if re.match(r"^## (?!#)", line):
            flush()
            current_heading = line.rstrip("\n")
            current_lines = [line]
        elif current_heading is not None:
            current_lines.append(line)
    flush()
    return sections


def hash_dashboard_rollup(task_dir: Path) -> str:
    """SHA-256 of sorted 'task_id:status\\n' lines across task-*.json files in task_dir.
    Mirrors the formula in commands/status.md line 36."""
    entries = []
    for task_file in sorted(task_dir.glob("task-*.json")):
        try:
            data = json.loads(task_file.read_text(encoding="utf-8"))
            entries.append(f"{data['task_id']}:{data['status']}")
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
    group.add_argument(
        "--dashboard-rollup",
        type=Path,
        help="Hash sorted task_id:status rollup (pass task dir, e.g. .claude/tasks).",
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
        print(json.dumps(hash_sections(args.sections), indent=2))
    elif args.dashboard_rollup:
        if not args.dashboard_rollup.is_dir():
            print(f"error: not a directory: {args.dashboard_rollup}", file=sys.stderr)
            return 2
        print(hash_dashboard_rollup(args.dashboard_rollup))
    return 0


if __name__ == "__main__":
    sys.exit(main())
