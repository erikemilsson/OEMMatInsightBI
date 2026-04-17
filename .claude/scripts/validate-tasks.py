#!/usr/bin/env python3
"""Task JSON schema validation + verification debt count.

Mirrors the field list in .claude/support/reference/task-schema.md.
Any schema change there MUST be mirrored here (flagged for follow-up: task-schema.json
as a single source of truth — deferred per inventory open Q2).
"""
import argparse
import json
import sys
from pathlib import Path

REQUIRED_FIELDS = {
    "task_id", "title", "description", "status", "difficulty", "owner",
    "dependencies", "files_affected",
}

VALID_STATUSES = {
    "Pending", "In Progress", "Awaiting Verification", "Blocked",
    "On Hold", "Absorbed", "Broken Down", "Finished",
}

VALID_OWNERS = {"claude", "human", "both"}

BOOLEAN_FIELDS = {
    "cross_phase", "parallel_safe", "out_of_spec", "out_of_spec_rejected",
    "user_review_pending",
}


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
            debt.append({"file": f.name, "task_id": data.get("task_id"), "reason": d})

    summary = {
        "task_count": len(files),
        "validation_errors": validation_errors,
        "verification_debt": debt,
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

    return 0 if not validation_errors and not debt else 1


if __name__ == "__main__":
    sys.exit(main())
