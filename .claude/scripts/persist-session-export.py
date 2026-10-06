#!/usr/bin/env python3
"""Copy a session export to the template inbox with a deterministic, never-dot-prefixed name.

Mechanizes the inbox copy-with-rename in
`.claude/support/reference/context-transitions.md § "Session Export"` step 6
and the parallel copy in `.claude/support/reference/work-recovery.md
§ "Stale Track 2 Recovery"` step 8 (triggered by work.md Step 0f). Any change to that recipe MUST be mirrored here,
and vice versa — see `.claude/scripts/README.md § "Dual-location risk"`.

Why this script exists (FB-109): the rename rule at context-transitions.md:411
is prose executed by an LLM at three call sites under end-of-session context
pressure, and it kept being violated months after its v4.21.2 patch — the
working filename is dot-prefixed (`.session-export-…json`) and dot-files are
invisible to plain `ls` in the template inbox (19 exports silently accumulated
unseen before the rule was added; 4 of 7 dot-prefixed exports found on
2026-08-12 postdate the rule, one via the Step 0f recovery path the rule names
explicitly). Contrast `.claude/hooks/pre-compact-handoff.sh:239`, which builds
the inbox filename in actual Python and has never produced a dot-prefixed inbox
file. A script cannot forget to rename.

Unlike the other scripts in this directory, this one WRITES a file — the
inbox copy. The destination is a user-configured EXTERNAL path
(`template_inbox_path` in `.claude/version.json`), never a `.claude/` path, so
this does not violate the subagent-write constraint (DEC-004): the script is
orchestrator-invoked, never from an `Agent` subagent. Read-only scripts emit data
for the orchestrator to write; this script performs the copy itself because
the copy-with-rename IS the operation that keeps failing — handing the `cp`
back to the orchestrator would leave the failure surface in place.

Destination filename: `{project-slug}-session-export-{timestamp}{suffix}.json`
  - project-slug: `--project-slug`, else kebab-case of the export's
    `source_project` field, else fallback `project`.
  - timestamp: `--timestamp`, else parsed from the source filename
    (`YYYY-MM-DD-HHMM`), else error.
  - suffix: `--suffix` without a leading hyphen (e.g. `recovered` for Step 0f
    produces `-recovered`), default empty.

Invariant: the destination basename NEVER starts with `.` — enforced. The
script also refuses a destination whose basename lacks the canonical
`session-export` segment, so a misconfigured slug/timestamp cannot silently
produce a malformed inbox filename.

Exit codes: 0 success (incl. no-op when the inbox is unconfigured or missing);
2 usage/runtime error.

Stdout: one JSON object; `"copied": true` only once the inbox file is written.
Callers delete the working copy on exactly that (context-transitions.md
§ "Session Export" step 7, work-recovery.md Step 0f step 9), so keep it stable.
"""
import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

if sys.version_info < (3, 10):  # Python floor (FB-120); see README § Invocation contract
    print(f"error: {Path(__file__).name} needs Python 3.10+; this is Python "
          f"{'.'.join(map(str, sys.version_info[:3]))} ({sys.executable})", file=sys.stderr)
    sys.exit(2)

# Minute-granularity timestamp as used across the Session Export recipe
# (FB-079). Anchored to the `YYYY-MM-DD-HHMM` form embedded in the working
# filename (.session-export-2026-08-12-1402.json).
TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}-\d{4}")
TS_FULL = re.compile(r"\d{4}-\d{2}-\d{2}-\d{4}\Z")

# Destination basename shape. The literal `session-export` segment is the
# anti-malformation guard: a slug or timestamp that ate the hyphen structure
# cannot silently produce an unrecognizable inbox filename.
DEST_RE = re.compile(r"[a-z0-9][a-z0-9-]*-session-export-\d{4}-\d{2}-\d{2}-\d{4}.*\.json\Z")


def kebab(value: str) -> str:
    """Kebab-case short form of a project name (FB-109 derives slug from source_project).

    Lowercase, collapse non-[a-z0-9] runs to a single hyphen, trim edges.
    Empty result falls back to `project` so the destination filename is always
    well-formed even when source_project is blank.
    """
    s = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return s or "project"


def slug_from_export(export: dict) -> str:
    return kebab(str(export.get("source_project") or ""))


def timestamp_from_filename(name: str) -> str | None:
    m = TS_RE.search(name)
    return m.group(0) if m else None


def read_inbox_from_version(version_json: Path) -> str | None:
    """template_inbox_path from .claude/version.json, or None if unset/absent."""
    if not version_json.is_file():
        return None
    try:
        data = json.loads(version_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data.get("template_inbox_path") or None


def build_destination(inbox: Path, slug: str, timestamp: str, suffix: str) -> Path:
    name = f"{slug}-session-export-{timestamp}{suffix}.json"
    return inbox / name


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy a session export to the template inbox with a deterministic, "
                    "never-dot-prefixed filename (FB-109)."
    )
    parser.add_argument("--source", type=Path, required=True,
                        help="Path to the session export file to copy. The dot-prefixed "
                             "working file (.session-export-…json) is the expected input.")
    parser.add_argument("--inbox", type=Path, default=None,
                        help="Destination inbox directory. Default: template_inbox_path "
                             "from --version-json.")
    parser.add_argument("--version-json", type=Path, default=Path(".claude/version.json"),
                        help="Source of template_inbox_path when --inbox is omitted. "
                             "Default: .claude/version.json")
    parser.add_argument("--project-slug", default=None,
                        help="Project slug for the destination filename. Default: "
                             "kebab-case of the export's source_project field.")
    parser.add_argument("--timestamp", default=None,
                        help="YYYY-MM-DD-HHMM timestamp for the destination filename. "
                             "Default: parsed from the source filename.")
    parser.add_argument("--suffix", default="",
                        help="Suffix appended before .json, without a leading hyphen "
                             "(e.g. `recovered` for Step 0f produces `-recovered`). "
                             "A leading hyphen is stripped and re-added, so both forms "
                             "work. Default: empty (no suffix).")
    args = parser.parse_args()

    # --- validate source ---
    if not args.source.is_file():
        print(f"error: source export not found: {args.source}", file=sys.stderr)
        return 2
    try:
        export = json.loads(args.source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"error: source export is not valid JSON ({e})", file=sys.stderr)
        return 2
    if not isinstance(export, dict):
        print("error: source export is not a JSON object", file=sys.stderr)
        return 2

    # --- resolve inbox ---
    inbox = args.inbox
    if inbox is None:
        resolved = read_inbox_from_version(args.version_json)
        if resolved is None:
            # No-op: inbox not configured. Mirror the PreCompact hook's lenient
            # skip — pause must never fail on an unconfigured inbox.
            print(json.dumps({
                "copied": False,
                "reason": "inbox not configured",
                "source": str(args.source),
            }))
            return 0
        inbox = Path(os.path.expanduser(resolved))
    else:
        inbox = Path(os.path.expanduser(str(args.inbox)))

    if not inbox.is_dir():
        # Configured but missing — warn, but still no-op (a stale inbox path
        # must not break the pause flow; the user can fix the path offline).
        print(f"warning: inbox is not a directory: {inbox} — copy skipped",
              file=sys.stderr)
        print(json.dumps({
            "copied": False,
            "reason": "inbox not a directory",
            "inbox": str(inbox),
            "source": str(args.source),
        }))
        return 0

    # --- resolve slug ---
    slug = args.project_slug if args.project_slug is not None else slug_from_export(export)
    if not slug:
        slug = "project"
    # A user-supplied slug must itself be kebab-clean so the destination
    # filename cannot be malformed or dot-prefixed via this route.
    slug = kebab(slug)

    # --- resolve timestamp ---
    timestamp = args.timestamp or timestamp_from_filename(args.source.name)
    if not timestamp:
        print(f"error: could not determine timestamp from source filename "
              f"({args.source.name!r}) — pass --timestamp YYYY-MM-DD-HHMM",
              file=sys.stderr)
        return 2
    if not TS_FULL.match(timestamp):
        print(f"error: timestamp must be YYYY-MM-DD-HHMM, got {timestamp!r}",
              file=sys.stderr)
        return 2

    # Normalize the suffix: strip any leading hyphens the caller supplied, then
    # prepend exactly one. `--suffix recovered` → `-recovered`; `--suffix=-recovered`
    # → `-recovered` (idempotent); empty → empty. This keeps the flag value free of
    # a leading hyphen so argparse never mistakes it for an option.
    suffix = ("-" + args.suffix.lstrip("-")) if args.suffix else ""

    dest = build_destination(inbox, slug, timestamp, suffix)

    # --- invariants (the whole point of FB-109) ---
    if dest.name.startswith("."):
        print(f"error: destination is dot-prefixed ({dest.name}) — refusing; "
              f"this is the exact failure mode FB-109 mechanizes against",
              file=sys.stderr)
        return 2
    if not DEST_RE.match(dest.name):
        print(f"error: destination filename is malformed ({dest.name!r}); "
              f"expected `{{slug}}-session-export-YYYY-MM-DD-HHMM{{suffix}}.json`",
              file=sys.stderr)
        return 2

    # --- copy ---
    if dest.exists():
        print(f"warning: overwriting existing inbox file: {dest}", file=sys.stderr)
    shutil.copy2(args.source, dest)

    print(json.dumps({
        "copied": True,
        "source": str(args.source),
        "destination": str(dest),
        "destination_basename": dest.name,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())