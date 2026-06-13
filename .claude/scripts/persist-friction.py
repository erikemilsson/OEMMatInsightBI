#!/usr/bin/env python3
"""Compute the friction-marker dual-write payload + collision-safe FR-NNN ids.

Mechanizes the orchestrator-side bookkeeping in
`.claude/support/reference/work-procedures.md § "State Persistence Protocol"`
step 2 (the friction-marker dual-write + audit-register projection) and
`.claude/support/reference/friction-register.md § "Write protocol"`. Any change
to that recipe MUST be mirrored here, and vice versa — see
`.claude/scripts/README.md § "Dual-location risk"`.

READ-ONLY: like every script under `.claude/scripts/`, this never writes to
`.claude/`. It reads the existing register (+ optional --scan paths), assigns
collision-safe ids, and emits the records to stdout as JSON. The ORCHESTRATOR
performs the actual appends:

  - `markers`      → append each line to BOTH
                     `.claude/support/workspace/.pending-markers.jsonl` AND
                     `.claude/support/workspace/.session-log.jsonl`
                     (DEC-011 Option ABp dual-write).
  - `register`     → append each line to `.claude/support/friction.jsonl`.
  - `assigned_ids` → echo into the relevant task notes.

Collision-safe FR-NNN: the next id is one past the max of BOTH the existing
`friction.jsonl` `id` fields AND every textual `FR-<n>` reference found in the
`--scan` paths (task notes, handoff, dashboard, ...). A naive max-over-register
alone has produced duplicate ids when an FR number was referenced in prose
before its register line existed (observed: flirty-gym FR-001, styler FR-031).

Input: a JSON array of friction markers (stdin, or --markers-file). Each marker
is an agent-report object: `type` (kind), `details`, optional `source_anchor`,
optional `timestamp`, plus optional context (`task_id`, `agent`, `command`).
CLI flags supply defaults for markers missing context.

Exit codes: 0 success (warnings still 0), 2 usage/runtime error.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Audit-eligible kinds get the friction.jsonl projection (with an FR-NNN id).
# Must match friction-register.md § Schema "kind" enum and work-procedures.md step 2.
AUDIT_ELIGIBLE = frozenset({
    "vocab_drift",
    "path_drift",
    "design_contradiction",
    "terminology_mismatch",
    "spec_implementation_gap",
})

FR_RE = re.compile(r"FR-(\d+)")


def fr_id(n: int) -> str:
    return f"FR-{n:03d}"


def max_fr_in_text(text: str) -> int:
    return max((int(m) for m in FR_RE.findall(text)), default=0)


def max_existing_id(register_path: Path) -> int:
    """Max FR-NNN among `id` fields of an existing friction.jsonl (0 if absent)."""
    if not register_path.is_file():
        return 0
    hi = 0
    for line in register_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            # Tolerate a malformed line, but still scan it textually so a
            # half-written id can't be silently reused.
            hi = max(hi, max_fr_in_text(line))
            continue
        ident = obj.get("id", "")
        if isinstance(ident, str):
            m = FR_RE.fullmatch(ident)
            if m:
                hi = max(hi, int(m.group(1)))
    return hi


def max_fr_in_scan(paths: list[Path]) -> int:
    """Max textual FR-<n> reference across --scan files/dirs (0 if none)."""
    hi = 0
    for p in paths:
        if p.is_dir():
            files = [f for f in p.rglob("*") if f.is_file()]
        elif p.is_file():
            files = [p]
        else:
            print(f"warning: scan path does not exist: {p}", file=sys.stderr)
            files = []
        for f in files:
            try:
                hi = max(hi, max_fr_in_text(f.read_text(encoding="utf-8", errors="replace")))
            except OSError as e:
                print(f"warning: cannot read scan path {f} ({e})", file=sys.stderr)
    return hi


def process(markers, *, next_n, default_task, default_agent, command, now_iso):
    out_markers = []
    register = []
    assigned = []
    warnings = []
    for i, marker in enumerate(markers):
        if not isinstance(marker, dict):
            warnings.append(f"marker[{i}] is not an object — skipped")
            continue
        m = dict(marker)
        if "task_id" not in m and default_task is not None:
            m["task_id"] = default_task
        out_markers.append(m)

        kind = m.get("type")
        if kind in AUDIT_ELIGIBLE:
            anchor = m.get("source_anchor")
            if not anchor:
                warnings.append(
                    f"marker[{i}] kind '{kind}' is audit-eligible but has no source_anchor "
                    f"— register projection skipped (the dual-write to markers still applies)"
                )
                continue
            entry = {
                "id": fr_id(next_n),
                "captured": m.get("timestamp") or now_iso,
                "captured_in": {
                    "agent": m.get("agent", default_agent),
                    "task": m.get("task_id"),
                    "command": m.get("command", command),
                },
                "kind": kind,
                "what": m.get("details", ""),
                "source_anchor": anchor,
                "status": "open",
            }
            register.append(entry)
            assigned.append({"marker_index": i, "task": m.get("task_id"), "id": entry["id"]})
            next_n += 1
    return out_markers, register, assigned, warnings, next_n


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute friction-marker dual-write payload + collision-safe FR-NNN ids (read-only)."
    )
    parser.add_argument("--markers-file", type=Path,
                        help="JSON array of friction markers. Default: read from stdin.")
    parser.add_argument("--friction-register", type=Path,
                        default=Path(".claude/support/friction.jsonl"),
                        help="Existing audit register (read for max id). Default: .claude/support/friction.jsonl")
    parser.add_argument("--scan", type=Path, action="append", default=[],
                        help="Extra file/dir to scan for textual FR-<n> references (repeatable).")
    parser.add_argument("--task-id", default=None, help="Default task_id for markers lacking one.")
    parser.add_argument("--agent", default="implement-agent",
                        help="Default captured_in.agent. Default: implement-agent.")
    parser.add_argument("--command", default="/work", help="captured_in.command. Default: /work.")
    parser.add_argument("--now", default=None,
                        help="Fallback ISO timestamp for markers missing one. Default: current UTC.")
    args = parser.parse_args()

    raw = (args.markers_file.read_text(encoding="utf-8") if args.markers_file else sys.stdin.read()).strip()
    if not raw:
        markers = []
    else:
        try:
            markers = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"error: marker input is not valid JSON ({e})", file=sys.stderr)
            return 2
    if not isinstance(markers, list):
        print("error: marker input must be a JSON array", file=sys.stderr)
        return 2

    now_iso = args.now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    next_n = max(max_existing_id(args.friction_register), max_fr_in_scan(args.scan)) + 1

    out_markers, register, assigned, warnings, next_after = process(
        markers,
        next_n=next_n,
        default_task=args.task_id,
        default_agent=args.agent,
        command=args.command,
        now_iso=now_iso,
    )

    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)

    print(json.dumps({
        "markers": out_markers,      # dual-write: append each to .pending-markers.jsonl AND .session-log.jsonl
        "register": register,        # append each to .claude/support/friction.jsonl
        "assigned_ids": assigned,
        "warnings": warnings,
        "next_fr_after": next_after,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
