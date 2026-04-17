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

# Read all active task files
tasks = []
for path in glob.glob(os.path.join(tasks_dir, "task-*.json")):
    try:
        with open(path) as f:
            tasks.append(json.load(f))
    except (json.JSONDecodeError, IOError):
        continue

if not tasks:
    sys.exit(0)

# Identify in-flight work
active_work = []
for t in tasks:
    status = t.get("status", "")
    if status == "In Progress":
        active_work.append({
            "task_id": t.get("id", "?"),
            "task_title": t.get("title", "Unknown"),
            "agent": "implement",
            "agent_step": "Unknown (captured from disk state)",
            "partial": True,
            "partial_notes": t.get("notes", ""),
            "files_modified_this_session": [],
            "ready_for_verify": False
        })
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

# Write handoff
with open(handoff_path, "w") as f:
    json.dump(handoff, f, indent=2)

# --- Cross-project interaction log export (Track 1 only) ---
# Compile friction markers into a markers-only session export.
# Track 2 (Claude assessment) requires conversation context, so it's null here.

workspace_dir = os.path.join(project_dir, ".claude", "support", "workspace")
session_log_path = os.path.join(workspace_dir, ".session-log.jsonl")
version_path = os.path.join(project_dir, ".claude", "version.json")

markers = []
if os.path.exists(session_log_path):
    with open(session_log_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    markers.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

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

    # Verification pass rate
    verified = [t for t in tasks if t.get("task_verification", {}).get("result")]
    passed = [t for t in verified if t["task_verification"]["result"] == "pass"]
    pass_rate = len(passed) / len(verified) if verified else 0.0

    export_data = {
        "export_version": 1,
        "source_project": os.path.basename(project_dir),
        "template_version": template_version,
        "session_date": today,
        "automated_markers": markers,
        "session_metrics": {
            "tasks_completed": completed_today,
            "verification_pass_rate": round(pass_rate, 2),
            "recovery_events": 0
        },
        "claude_assessment": None,
        "export_quality": "markers_only"
    }

    export_path = os.path.join(workspace_dir, f".session-export-{today}.json")
    with open(export_path, "w") as f:
        json.dump(export_data, f, indent=2)

    # Copy to template inbox if configured
    if template_inbox_path and os.path.isdir(template_inbox_path):
        import shutil
        dest = os.path.join(template_inbox_path, f"{os.path.basename(project_dir)}-{today}.json")
        shutil.copy2(export_path, dest)

    # Clean up session log (data is now in the export)
    os.remove(session_log_path)

PYEOF

exit 0
