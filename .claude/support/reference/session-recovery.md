# Session Recovery

Procedure for detecting and recovering tasks left in inconsistent states by a previous session. Run as `/work` Step 0.

---

## Session Sentinel

A lightweight file at `.claude/tasks/.last-clean-exit.json` tracks whether the previous `/work` session ended cleanly.

**Schema:**
```json
{
  "timestamp": "2026-01-28T14:30:00Z",
  "task_count": 15,
  "in_progress_tasks": ["5", "8"]
}
```

**Written by:** `/work` at the end of a successful run (after Step 6).
**Read by:** `/work` at the start of Step 0.

### Fast-Path: Skip Recovery Scan

```
1. Read .claude/tasks/.last-clean-exit.json
2. IF file exists AND timestamp is within last 24 hours:
   → Skip full recovery scan
   → Only check the specific tasks listed in in_progress_tasks
     (verify they're still in expected states)
   → Proceed to Step 1
3. IF file missing OR stale (>24h):
   → Run full recovery scan below
```

---

## Full Recovery Scan

Scan all non-archived `task-*.json` files and check for recoverable states:

```
1. STATUS: "Awaiting Verification"
   (Agent crashed after implementation, before verification completed)

   → Auto-recover: spawn verify-agent for this task
   → Log: "⚡ Recovering task {id} — spawning verification (previous session incomplete)"
   → Continue to Step 1 after recovery spawns complete

2. STATUS: "Blocked" WITH notes containing "[VERIFICATION TIMEOUT]"
   AND verification_attempts < 3
   (Verify-agent ran out of turns — implementation is done, verification needs retry)

   → Auto-recover: set status to "Awaiting Verification", spawn verify-agent with max_turns: 40 (extended from 30)
   → Clear the [VERIFICATION TIMEOUT] note
   → Log: "⚡ Retrying verification for task {id} with extended turn limit"

3. STATUS: "Blocked" WITH notes containing "[VERIFICATION TIMEOUT]"
   AND verification_attempts >= 3
   (Verify-agent failed 3 times — needs human review)

   → Replace note: "[VERIFICATION ESCALATED] 3 verification attempts exhausted — requires human review"
   → Log: "Task {id} escalated to human review after 3 failed verification attempts"

4. STATUS: "Blocked" WITH notes containing "[AGENT TIMEOUT]"
   (Parallel agent timed out — task may be too complex or need breakdown)

   → Present to user:
   │  Task {id} "{title}" timed out in a previous session.
   │  [R] Retry (set to Pending for next dispatch)
   │  [B] Break down (run /breakdown {id})
   │  [S] Skip (stays Blocked)

5. STATUS: "Blocked" WITH notes containing "[VERIFICATION ESCALATED]"
   (Intentional escalation — already surfaced, no auto-action)

   → Report only: "Task {id} awaiting human review (3 verification attempts exhausted)"

6. STATUS: "In Progress" WITH updated_date older than 24 hours
   AND no agent currently running for this task
   (Abandoned by a crashed implement-agent)

   → Present to user:
   │  Task {id} "{title}" has been In Progress for {N} days without activity.
   │  [C] Continue (keep In Progress, /work will route to implement-agent)
   │  [P] Reset to Pending (start fresh)
   │  [H] Put On Hold
```

**After recovery actions complete, proceed to Step 1.**

**Note:** Cases 1 and 2 are auto-recovered because the implementation is already done — we only need to run verification. Cases 4 and 6 present options because the implementation state is uncertain.

**Malformed files during scan:** If a task file fails to parse during Step 0, skip it and continue scanning other files. The malformed file will be reported in Step 1 (see work.md "Malformed task file handling").
