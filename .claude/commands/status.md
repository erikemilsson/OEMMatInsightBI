# Status Command

Quick, read-only view of project state without starting any work.

## Usage

```
/status              # Full status overview
/status --brief      # One-line summary only
/status --tasks      # Focus on task status
```

## What It Does

1. **Read-only** - Never modifies files, never starts work
2. **Fast** - Quick scan, no agent invocation
3. **Informative** - Shows exactly what you need to know

**Key difference from `/work`:** The `/status` command only reads and displays. It never creates tasks, invokes agents, or modifies any files.

---

## Process

### Step 1: Gather State

Read (but don't modify):
- `.claude/dashboard.md` - Current status (progress summary, decisions, recent activity)
- `.claude/tasks/task-*.json` - Task data for phase detection, status counts, and verification result validation
- `.claude/spec_v{N}.md` - Spec version and fingerprint for verification validation
- `.claude/drift-deferrals.json` - Drift deferral count (if exists)
- `.claude/verification-result.json` - Phase-level verification result (if exists)

**Scale optimization (50+ tasks):** For large projects, use a lightweight freshness check first: glob for `task-*.json` files and compare the count against dashboard metadata `task_count`. If counts match, the dashboard is likely fresh — use dashboard data for finished task totals and only read non-Finished task JSON files for active-task details. If counts differ, fall back to full hash computation below.

**Dashboard freshness check:** Compute `SHA-256(sorted list of task_id + ":" + status)` from task JSON files and compare against the `task_hash` in the dashboard's `<!-- DASHBOARD META -->` block. If the hash differs or no metadata exists, flag the dashboard as stale in the Health Indicators output. At scale (50+ tasks), this full check only runs when the lightweight count check above detects a discrepancy. Task counts always come from JSON files regardless of freshness.

### Step 2: Determine Phase

| Condition | Phase |
|-----------|-------|
| No spec exists | Pre-spec |
| Spec incomplete | Spec (in progress) |
| Spec complete, no tasks | Ready for decomposition |
| Tasks exist, any in "Awaiting Verification" | Execute (verification pending) |
| Tasks exist, not all finished (none awaiting verification) | Execute |
| All non-Absorbed tasks finished, no valid phase-level verification result | Ready for verification |
| All non-Absorbed tasks finished, phase-level verification result exists and is valid | Complete |

**Verification result check:**
Read `.claude/verification-result.json` if it exists. A result is **valid** when:
- `result` is `"pass"`
- `spec_fingerprint` matches the current spec's fingerprint (spec hasn't changed since verification)
- No tasks have been added or changed status since the `timestamp`

If the file doesn't exist or the result is `"fail"` or invalidated, the phase is "Ready for verification."

### Step 3: Format Output

Display the appropriate output format based on mode.

---

## Output Formats

### Full Mode (default: `/status`)

```markdown
## Project Status

**Phase:** Execute (12/18 tasks finished)
**Current:** Task 5_3 "Add Redis caching layer" - In Progress

### Quick Numbers
| Finished | In Progress | Awaiting Verification | Pending | Blocked | On Hold |
|----------|-------------|-----------------------|---------|---------|---------|
| 12       | 1           | 0                     | 4       | 0       | 1       |

**Human tasks ready:** 2 · **Decisions pending:** 1

### Health Indicators
- ✓ Dashboard current
- ✓ No verification debt
- ⚠️ 1 drift deferral (run /health-check for details)

### Attention Needed
- Decision pending: Auth approach (decision-001)
- Human task ready: Configure LDAP credentials (Task 7)

### Recent Activity (last 24h)
- ✅ Task 5_1 completed
- ✅ Task 5_2 completed
- 🚀 Task 5_3 started
```

### Brief Mode (`/status --brief`)

Single line for quick check:

```
Execute phase: 12/18 finished | 1 in progress | 2 need human
```

If health indicators have issues, append them:

```
Execute phase: 12/18 finished | 1 in progress | 2 need human | ⚠️ 1 drift deferral
```

### Tasks Mode (`/status --tasks`)

Focus on task breakdown:

```markdown
## Task Status

**By Status:**
- Finished: 12
- In Progress: 1 (Task 5_3)
- Awaiting Verification: 0
- Pending: 3
- Blocked: 0
- On Hold: 1
- Absorbed: 0
- Broken Down: 2

**By Owner (non-finished):**
- Claude: 4
- Human: 2
- Both: 1

**Next Up:**
1. Task 5_4 "Create drill-down endpoints" (blocked by 5_3)
2. Task 6 "Build React dashboard" (ready)
3. Task 7 "Add authentication" (needs human input)
```

---

## Status Icons

| Icon | Meaning |
|------|---------|
| ✅ | Complete |
| 🔄 | In Progress |
| ⏳ | Pending / Not started |
| ⚠️ | At Risk (approaching or past due) |
| 🔴 | Overdue or Critical |
| 🚀 | Just started |

---

## Examples

```
# Quick check before a meeting
/status --brief
→ Execute phase: 12/18 finished | 1 in progress | 2 need human

# Full status report
/status
→ (full formatted output)

# See what tasks need attention
/status --tasks
→ (task-focused output)
```

---

## Health Indicators

Computed from task JSON files, `drift-deferrals.json`, and `verification-result.json`:

| Indicator | Healthy | Unhealthy |
|-----------|---------|-----------|
| Dashboard freshness | `✓ Dashboard current` | `⚠️ Dashboard stale — run /work to refresh` |
| Verification debt | `✓ No verification debt` | `⚠️ N tasks with verification debt` |
| Drift deferrals | `✓ Spec aligned` | `⚠️ N drift deferrals` |

**Verification debt** = count of Finished tasks where `task_verification` is missing, has `result == "fail"`, or has `result != "pass"`.

**Drift deferrals** = count of active entries in `drift-deferrals.json`.

These are read-only indicators. Use `/health-check` for full validation with auto-fixes, or `/work` to address issues.

---

## Notes

- `/status` is purely informational — use `/work` to actually do work
- Task counts come from task JSON files directly (not the dashboard), ensuring accuracy even if the dashboard is stale
- Phase detection and verification validation also read task files and spec directly
- Brief mode is ideal for quick context before starting work
