#!/usr/bin/env python3
"""Task JSON schema validation + verification debt count + section-provenance warnings.

Mirrors the field list in .claude/support/reference/task-schema.md.
Any schema change there MUST be mirrored here (flagged for follow-up: task-schema.json
as a single source of truth — deferred per inventory open Q2).
"""
import argparse
import json
import sys
from pathlib import Path

if sys.version_info < (3, 10):  # Python floor (FB-120); see README § Invocation contract
    print(f"error: {Path(__file__).name} needs Python 3.10+; this is Python "
          f"{'.'.join(map(str, sys.version_info[:3]))} ({sys.executable})", file=sys.stderr)
    sys.exit(2)

REQUIRED_FIELDS = {
    "id", "title", "description", "status", "difficulty", "owner",
    "dependencies", "files_affected",
}

VALID_STATUSES = {
    "Pending", "In Progress", "Awaiting Verification", "Blocked",
    "On Hold", "Absorbed", "Broken Down", "Finished",
}

VALID_OWNERS = {"claude", "human", "both"}

BOOLEAN_FIELDS = {
    "cross_phase", "parallel_safe", "out_of_spec", "out_of_spec_rejected",
    "user_review_pending", "spec_unmapped",
}

PROVENANCE_SKIPPED = ("Absorbed", "Broken Down")  # as fingerprint.py's DRIFT_SKIPPED


def validate_task(data: dict, path: Path) -> list[str]:
    errors: list[str] = []

    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"missing required field: {field}")

    if "status" in data and data["status"] not in VALID_STATUSES:
        errors.append(f"invalid status: {data['status']!r}")
    if "owner" in data and data["owner"] not in VALID_OWNERS:
        errors.append(f"invalid owner: {data['owner']!r}")
    if "difficulty" in data:
        d = data["difficulty"]
        if not isinstance(d, int) or not (1 <= d <= 10):
            errors.append(f"difficulty must be int 1-10, got {d!r}")

    for field in BOOLEAN_FIELDS:
        if field in data and not isinstance(data[field], bool):
            errors.append(f"{field} must be boolean, got {type(data[field]).__name__} {data[field]!r}")

    # decisions_pending (FB-129): optional; agent decisions held until the verify pass
    if "decisions_pending" in data:
        dp = data["decisions_pending"]
        if not isinstance(dp, list) or not all(isinstance(e, dict) for e in dp):
            errors.append("decisions_pending must be an array of objects")

    if data.get("status") == "Absorbed" and not data.get("absorbed_into"):
        errors.append("status Absorbed requires non-empty absorbed_into")
    if data.get("status") == "Broken Down" and not data.get("subtasks"):
        errors.append("status Broken Down requires non-empty subtasks array")

    return errors


def check_verification_debt(data: dict) -> str | None:
    """Return a one-line debt description if this Finished task has missing/failed verification."""
    if data.get("status") != "Finished":
        return None
    tv = data.get("task_verification")
    if not tv:
        return "Finished but task_verification is missing"
    if tv.get("result") != "pass":
        return f"Finished but task_verification.result == {tv.get('result')!r}"
    return None


def _blank(value) -> bool:
    return not (isinstance(value, str) and value.strip())


def check_provenance(data: dict) -> str | None:
    """Return a reason when the task's section provenance is missing or contradictory
    (FB-135). Every task has section provenance (spec_section + section_fingerprint),
    or spec_unmapped true, or out_of_spec true; Absorbed and Broken Down tasks are
    not checked. A warning only: it never changes the exit code."""
    if data.get("status") in PROVENANCE_SKIPPED or data.get("out_of_spec") is True:
        return None
    no_fingerprint = _blank(data.get("section_fingerprint"))
    if data.get("spec_unmapped") is True:
        return None if no_fingerprint else "spec_unmapped set on a task with section provenance"
    missing = [name for name, absent in (("spec_section", _blank(data.get("spec_section"))),
                                         ("section_fingerprint", no_fingerprint)) if absent]
    return "no " + ", no ".join(missing) if missing else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate task JSON files and count verification debt."
    )
    parser.add_argument(
        "task_dir",
        type=Path,
        nargs="?",
        default=Path(".claude/tasks"),
        help="Task directory (default: .claude/tasks)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON summary to stdout.")
    args = parser.parse_args()

    if not args.task_dir.is_dir():
        print(f"error: not a directory: {args.task_dir}", file=sys.stderr)
        return 2

    files = sorted(args.task_dir.glob("task-*.json"))
    validation_errors: dict[str, list[str]] = {}
    debt: list[dict] = []
    provenance: list[dict] = []

    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            validation_errors[f.name] = [f"invalid JSON: {e}"]
            continue
        errs = validate_task(data, f)
        if errs:
            validation_errors[f.name] = errs
        d = check_verification_debt(data)
        if d:
            debt.append({"file": f.name, "task_id": data.get("id"), "reason": d})
        p = check_provenance(data)
        if p:
            provenance.append({"file": f.name, "task_id": data.get("id"), "reason": p})

    summary = {
        "task_count": len(files),
        "validation_errors": validation_errors,
        "verification_debt": debt,
        "provenance_warnings": provenance,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Validated {len(files)} task files.")
        if validation_errors:
            print(f"\n{len(validation_errors)} file(s) with schema errors:")
            for fname, errs in validation_errors.items():
                print(f"  {fname}:")
                for e in errs:
                    print(f"    - {e}")
        else:
            print("Schema: OK")
        if debt:
            print(f"\nVerification debt: {len(debt)} Finished task(s) without task_verification.result == 'pass':")
            for d in debt:
                print(f"  - {d['task_id']} ({d['file']}): {d['reason']}")
        else:
            print("Verification debt: none")
        # one line, a warning only: the exit code below ignores it
        without = sum(1 for w in provenance if w["reason"].startswith("no "))
        parts = []
        if without:
            parts.append(f"{without} task(s) without section provenance "
                         "(see /health-check Part 1 check 11)")
        if len(provenance) > without:
            parts.append(f"{len(provenance) - without} task(s) with spec_unmapped set "
                         "despite section provenance")
        print("Provenance: " + ("; ".join(parts) if parts else "OK"))

    return 0 if not validation_errors and not debt else 1


if __name__ == "__main__":
    sys.exit(main())
