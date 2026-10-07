#!/bin/bash
# Pre-compact handoff: writes a best-effort handoff file from task state on disk.
#
# This is the automatic safety net for context transitions. It runs before
# Claude Code auto-compacts or when the user runs /compact. Since hooks can't
# access conversation context, the handoff captures only what's on disk:
# task statuses, in-progress work, phase position.
#
# The user-initiated path (/work pause) produces a richer handoff that includes
# session_knowledge and recovery_action from conversation. This hook produces
# a structural-only handoff as a fallback.
#
# See: .claude/support/reference/context-transitions.md

set -euo pipefail

# Read event JSON from stdin
INPUT=$(cat)
TRIGGER=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('trigger','unknown'))" 2>/dev/null || echo "unknown")

# Determine project root
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
TASKS_DIR="$PROJECT_DIR/.claude/tasks"
HANDOFF_FILE="$TASKS_DIR/.handoff.json"

# Skip if no tasks directory exists (project not yet decomposed)
if [ ! -d "$TASKS_DIR" ]; then
    exit 0
fi

# Skip if a handoff already exists (user already ran /work pause — don't overwrite)
if [ -f "$HANDOFF_FILE" ]; then
    exit 0
fi

# Gather task state from disk
# Uses python3 for reliable JSON parsing (already in settings.local.json permissions)
python3 << 'PYEOF'
import json
import glob
import os
import sys
from datetime import datetime, timezone

project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
tasks_dir = os.path.join(project_dir, ".claude", "tasks")
handoff_path = os.path.join(tasks_dir, ".handoff.json")
trigger = sys.argv[1] if len(sys.argv) > 1 else "unknown"

# Read all active task files. A file that can't be read as a JSON object
# (bad JSON, not UTF-8, a list/string/null at the top level) is skipped.
tasks = []
for path in glob.glob(os.path.join(tasks_dir, "task-*.json")):
    try:
        with open(path) as f:
            data = json.load(f)
    except (ValueError, OSError):
        continue
    if isinstance(data, dict):
        tasks.append(data)

if not tasks:
    sys.exit(0)

NOTES_LIMIT = 600   # characters of a task's notes carried as partial_notes
TITLE_KEEP = 60     # a title is cut to this before recently_completed is touched
MAX_BYTES = 2560    # whole-handoff bound (context-transitions.md, "Bounds and Overflow")

def head(text, limit):
    """First `limit` characters of `text`, plus an ellipsis when cut."""
    return text if len(text) <= limit else text[:limit] + "\u2026"

def notes_head(t, limit=NOTES_LIMIT):
    """Head of a task's notes (newest entries first)."""
    notes = t.get("notes") or ""
    if not isinstance(notes, str):
        notes = str(notes)
    return head(notes, limit)

# Identify in-flight work
active_work = []
noted = []  # (entry, task) for each entry that carries a notes head
for t in tasks:
    status = t.get("status", "")
    if status == "In Progress":
        entry = {
            "task_id": t.get("id", "?"),
            "task_title": t.get("title", "Unknown"),
            "agent": "implement",
            "agent_step": "Unknown (captured from disk state)",
            "partial": True,
            "partial_notes": notes_head(t),
            "files_modified_this_session": [],
            "ready_for_verify": False
        }
        active_work.append(entry)
        noted.append((entry, t))
    elif status == "Awaiting Verification":
        active_work.append({
            "task_id": t.get("id", "?"),
            "task_title": t.get("title", "Unknown"),
            "agent": "verify",
            "agent_step": "Unknown (captured from disk state)",
            "partial": True,
            "ready_for_verify": True
        })

# Determine phase from tasks
phases = set()
for t in tasks:
    p = t.get("phase")
    if p and t.get("status") not in ("Finished", "Absorbed", "Broken Down"):
        phases.add(str(p))
current_phase = min(phases) if phases else "1"

# Find recently completed (finished today)
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
recently_completed = [
    t.get("id", "?") for t in tasks
    if t.get("status") == "Finished" and t.get("completion_date", "") == today
]

# Find next planned task
pending = [
    t for t in tasks
    if t.get("status") == "Pending" and t.get("phase", "1") == current_phase
]
pending.sort(key=lambda t: t.get("priority", "medium") == "critical", reverse=True)
next_planned = pending[0].get("id") if pending else None

# Discover spec version
spec_version = "unknown"
for path in glob.glob(os.path.join(project_dir, ".claude", "spec_v*.md")):
    name = os.path.basename(path).replace(".md", "")
    spec_version = name

# Build handoff
handoff = {
    "version": 1,
    "trigger": "pre_compact",
    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "spec_version": spec_version,
    "position": {
        "phase": current_phase,
        "recently_completed": recently_completed,
        "next_planned": next_planned
    },
    "active_work": active_work,
    "parallel_state": None,
    "decisions_in_flight": [],
    "session_knowledge": "",
    "recovery_action": ""
}

# Total check: the file is at most MAX_BYTES. Nothing here can be moved to an
# overflow file, and everything cut is still whole in the task files, so the
# hook cuts. The order and the floor are specified in context-transitions.md,
# "Path B" step 3; an active_work entry is never dropped.
def serialize():
    return json.dumps(handoff, indent=2)

def size():
    return len(serialize().encode("utf-8"))

if size() > MAX_BYTES:
    handoff["truncated"] = True

    def fit(low, high, apply):
        """Apply the largest value in [low, high] that fits (else `low`); True when the handoff fits."""
        while low < high:
            mid = (low + high + 1) // 2
            apply(mid)
            if size() <= MAX_BYTES:
                low = mid
            else:
                high = mid - 1
        apply(low)
        return size() <= MAX_BYTES

    # One ceiling over all values of a kind: the longest are cut first, and a
    # value shorter than the ceiling is left alone.
    def set_notes(limit):
        for entry, task in noted:
            entry["partial_notes"] = notes_head(task, limit)

    titles = [(entry, entry["task_title"]) for entry in active_work
              if isinstance(entry["task_title"], str)]
    longest_title = max([len(title) for _, title in titles] or [0])

    def set_titles(limit):
        for entry, title in titles:
            entry["task_title"] = head(title, limit)

    def set_recent(count):
        handoff["position"]["recently_completed"] = recently_completed[:count]

    if not (fit(0, NOTES_LIMIT, set_notes)                # 1. notes heads
            or fit(TITLE_KEEP, longest_title, set_titles)  # 2. overlong titles,
            or fit(0, len(recently_completed), set_recent) #    recently_completed,
            or fit(0, TITLE_KEEP, set_titles)):            #    the rest of the titles
        # 3. Every entry down to its id and flag, then titles (at most
        #    TITLE_KEEP characters) put back for as many entries as fit,
        #    counted from the front of active_work. Still over with no title
        #    back (dozens of tasks in flight): written as it is, `truncated`
        #    already set.
        def set_titled(count):
            reduced = []
            for i, entry in enumerate(active_work):
                slim = {"task_id": entry["task_id"]}
                if i < count and isinstance(entry["task_title"], str):
                    slim["task_title"] = entry["task_title"]
                slim["ready_for_verify"] = entry["ready_for_verify"]
                reduced.append(slim)
            handoff["active_work"] = reduced

        set_titles(TITLE_KEEP)
        fit(0, len(active_work), set_titled)

# Write handoff
with open(handoff_path, "w") as f:
    f.write(serialize())

# --- Cross-project interaction log export (Track 1 only) ---
# Compile friction markers into a markers-only session export.
# Track 2 (Claude assessment) requires conversation context, so it's null here.

workspace_dir = os.path.join(project_dir, ".claude", "support", "workspace")
session_log_path = os.path.join(workspace_dir, ".session-log.jsonl")
pending_markers_path = os.path.join(workspace_dir, ".pending-markers.jsonl")
version_path = os.path.join(project_dir, ".claude", "version.json")

# DEC-011 Option ABp: friction-marker catchup before reading the canonical log.
# Merge any entries from the pending buffer that didn't reach the session log
# (covers the sub-second window between agent return and dual-write completion).
import hashlib

def _marker_key(entry):
    """Composite dedup key: (task_id, timestamp, type, sha256(details))."""
    task_id = entry.get("task_id", "")
    timestamp = entry.get("timestamp", "")
    mtype = entry.get("type", "")
    details = entry.get("details", "")
    if task_id and timestamp and mtype:
        return (task_id, timestamp, mtype, hashlib.sha256(str(details).encode()).hexdigest())
    return hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()

def _read_jsonl(path):
    entries = []
    if not os.path.exists(path):
        return entries
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries

if os.path.exists(pending_markers_path):
    session_entries = _read_jsonl(session_log_path)
    pending_entries = _read_jsonl(pending_markers_path)
    seen = {_marker_key(e) for e in session_entries}
    new_entries = [e for e in pending_entries if _marker_key(e) not in seen]
    if new_entries:
        with open(session_log_path, "a") as f:
            for entry in new_entries:
                f.write(json.dumps(entry) + "\n")
    # Truncate pending buffer after successful merge
    open(pending_markers_path, "w").close()

markers = _read_jsonl(session_log_path)

# Only write export if there are markers
if markers:
    template_version = "unknown"
    template_inbox_path = None
    if os.path.exists(version_path):
        try:
            with open(version_path) as f:
                vdata = json.load(f)
                template_version = vdata.get("template_version", "unknown")
                template_inbox_path = vdata.get("template_inbox_path")
        except (json.JSONDecodeError, IOError):
            pass

    # Count tasks completed today
    completed_today = len([
        t for t in tasks
        if t.get("status") == "Finished" and t.get("completion_date", "") == today
    ])

    # Verification pass rate: null when no task has a verification result
    # (0.0 would read as "every verification failed")
    verified = [t for t in tasks if (t.get("task_verification") or {}).get("result")]
    passed = [t for t in verified if t["task_verification"]["result"] == "pass"]
    pass_rate = len(passed) / len(verified) if verified else None

    export_data = {
        "export_version": 1,
        "source_project": os.path.basename(project_dir),
        "template_version": template_version,
        "session_date": today,
        "automated_markers": markers,
        "session_metrics": {
            "tasks_completed": completed_today,
            "verification_pass_rate": round(pass_rate, 2) if verified else None,
            "recovery_events": 0
        },
        "claude_assessment": None,
        "export_quality": "markers_only"
    }

    # Minute-granularity timestamp prevents same-day pause collisions (FB-079)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    export_path = os.path.join(workspace_dir, f".session-export-{timestamp}.json")
    with open(export_path, "w") as f:
        json.dump(export_data, f, indent=2)

    # Copy to template inbox if configured
    if template_inbox_path and os.path.isdir(template_inbox_path):
        import shutil
        dest = os.path.join(template_inbox_path, f"{os.path.basename(project_dir)}-{timestamp}.json")
        shutil.copy2(export_path, dest)

    # Clean up session log (data is now in the export)
    os.remove(session_log_path)

PYEOF

exit 0
