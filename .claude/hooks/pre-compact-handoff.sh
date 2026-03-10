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

PYEOF

exit 0
