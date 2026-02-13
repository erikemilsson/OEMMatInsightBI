# Drift Detection and Reconciliation

Procedures for detecting spec drift, reconciling changes with tasks, managing version transitions, and enforcing drift budgets. These run inline during `/work` Step 1.

---

## Dashboard Freshness Check

Before using dashboard data, verify it's current (runs as `/work` Step 1a):

1. **Compute current task state hash:**
   ```
   task_hash = SHA-256(sorted list of: task_id + ":" + status + ":" + difficulty + ":" + owner for each task-*.json)
   ```

2. **Read dashboard metadata** (if present):
   ```markdown
   <!-- DASHBOARD META
   generated: 2026-01-28T14:30:00Z
   task_hash: sha256:abc123...
   -->
   ```

3. **Compare hashes:**
   ```
   If dashboard has no META block OR task_hash differs:
   ├─ Log: "Dashboard stale — regenerating"
   ├─ Backup user section to .claude/support/workspace/dashboard-notes-backup.md
   ├─ Regenerate dashboard from task JSON files
   └─ Continue with fresh dashboard
   ```

**Why this matters:** Dashboard can become stale if tasks are modified outside `/work`. This check ensures you always work from accurate data.

---

## Spec Drift Detection (Granular)

After reading the spec, perform section-level drift detection (runs as `/work` Step 1b):

1. **Compute current spec fingerprint** - SHA-256 hash of spec file content
2. **Check existing tasks** - Read `spec_fingerprint` and `section_fingerprint` from task files
3. **Compare fingerprints:**

```
If tasks exist with spec_fingerprint:
├─ Full spec fingerprint matches → Continue normally
└─ Full spec fingerprint differs → Perform granular section analysis:
   1. Parse current spec into sections (## level headings)
   2. Load snapshot from section_snapshot_ref (if exists)
   3. Parse snapshot spec into sections
   4. For each section, compare fingerprints
   5. Identify which sections changed
   6. Group affected tasks by changed section
   7. Present granular reconciliation UI
```

**Hash computation:**
```bash
# Use shasum (available on macOS and Linux; sha256sum is Linux-only)
shasum -a 256 .claude/spec_v{N}.md | cut -d' ' -f1
# Prefix with "sha256:" → "sha256:a1b2c3d4..."
```

**Section fingerprint computation:**
```bash
# For each ## section, hash: heading + all content until next ## or EOF
printf '%s' "## Authentication\nContent here..." | shasum -a 256 | cut -d' ' -f1
# Prefix with "sha256:" → "sha256:e5f6g7h8..."
```

**Note:** Tasks without `spec_fingerprint` are treated as legacy (no warning). Tasks without `section_fingerprint` fall back to full-spec comparison.

---

## Substantial Change Detection

Before showing the reconciliation UI, evaluate the magnitude of changes and respond accordingly.

**Heuristic — changes are "substantial" when ANY of:**
- More than 50% of sections have changed fingerprints
- New sections were added (scope expansion)
- Sections were deleted (scope reduction)
- Spec has been `active` for > 7 days AND > 3 sections changed

**If changes are NOT substantial:**

Proceed directly to the Granular Reconciliation UI (below). Small edits are absorbed into the current version via normal drift reconciliation.

**If changes ARE substantial:**

Present a version bump suggestion before reconciliation:

```
Spec has changed significantly since tasks were created:
  - {X} of {Y} sections modified
  - {A} new sections added / {B} sections deleted
  - Estimated {P}% of content changed

This may warrant a new spec version.

[V] Create spec v{N+1} (archives current version, then reconcile)
[C] Continue as v{N} (reconcile changes in place)
```

- **If user picks [V]:** Execute the Version Transition Procedure (see `iterate.md` § "Version Transition Procedure"), then run Task Migration (below), then proceed to reconciliation against the new version.
- **If user picks [C]:** Proceed directly to the Granular Reconciliation UI. Changes are absorbed into the current version.

Either choice preserves the user's edits. The version bump is about organizational clarity, not data safety.

---

## Task Migration on Version Transition

When `/work` detects that existing tasks reference an older spec version (tasks have `spec_version: "spec_v{M}"` but current spec is `spec_v{N}` where N > M), perform task migration:

```
For each task:
  IF status == "Finished" or "Absorbed":
    → Leave provenance unchanged (historical record)
    → These tasks were verified/resolved against the old spec — that's correct

  IF status == "Pending", "In Progress", or "On Hold":
    → Check if task's spec_section heading still exists in new spec
    │
    ├─ Section exists, content matches:
    │  → Update task: spec_version, spec_fingerprint, section_fingerprint
    │  → Task continues normally
    │
    ├─ Section exists, content changed:
    │  → Update spec_version reference
    │  → Flag for reconciliation (handled by Granular Reconciliation UI)
    │
    └─ Section does not exist in new spec:
       → Present to user:
       │
       │  Task {id} "{title}" references section "{spec_section}"
       │  which no longer exists in spec v{N}.
       │
       │  [D] Delete task
       │  [O] Keep as out-of-spec
       │  [R] Reassign to different section
```

**After migration:** Update the decomposed snapshot reference. Create `spec_v{N}_decomposed.md` if decomposition runs, or update `section_snapshot_ref` on migrated tasks to point to the new spec version's snapshot.

---

## Drift Budget Enforcement

To prevent drift from accumulating indefinitely, enforce a drift budget.

**Configuration (in spec frontmatter):**
```yaml
---
version: 1
status: active
drift_policy:
  max_deferred_sections: 3      # Max sections that can be deferred
  max_deferral_age_days: 14     # Max days a deferral can persist
---
```

**Default values (if not configured):** `max_deferred_sections: 3`, `max_deferral_age_days: 14`

**Tracking deferred reconciliations:**

When user selects "Skip section" during reconciliation, record it:
```json
// In .claude/drift-deferrals.json
{
  "deferrals": [
    {
      "section": "## Authentication",
      "deferred_date": "2026-01-20",
      "affected_tasks": ["3", "4", "7"]
    }
  ]
}
```

**Enforcement logic:**
```
On each /work run:
1. Read drift-deferrals.json (if exists)
2. Count active deferrals (not yet reconciled)
3. Check for expired deferrals (older than max_deferral_age_days)

IF active_deferrals > max_deferred_sections:
  ├─ ERROR: Too many deferred sections
  │
  │  You have deferred reconciliation for N sections (max: M).
  │  Must reconcile at least {N - M} section(s) before continuing.
  │
  │  [R] Reconcile now (required)
  │
  └─ Proceed to Granular Reconciliation UI (pre-filtered to deferred sections)

IF any deferral expired (and count is within budget):
  ├─ WARNING: Deferral expired
  │
  │  Deferral for "## SectionName" has expired (deferred N days ago, max: M days).
  │
  │  [R] Reconcile now (recommended)
  │  [X] Reset deferral timers (acknowledges drift risk)
  │
  ├─ If user selects [R]: proceed to Granular Reconciliation UI
  └─ If user selects [X]:
     1. Update each expired deferral's deferred_date to today in drift-deferrals.json
        (deferrals will expire again after max_deferral_age_days)
     2. Log: "⚠️ Drift deferrals reset — {N} sections remain unreconciled. Tasks in these sections may not match the current spec."
     3. Continue with /work (unblock)
```

**Clearing deferrals:** When a section is reconciled (user selects Apply or reviews individually and applies), remove it from `drift-deferrals.json`.

**See also:**
- `.claude/support/reference/workflow.md` § "Spec Change and Feature Addition Workflow" for the end-to-end process (user edits spec → detection → confirmation → task updates → implementation → verification).

---

## Granular Reconciliation UI

When section-level drift is detected, present a targeted UI showing:
- Section name and number of affected tasks
- Diff of changed content
- Table of affected tasks with suggested actions

**Options per section:** `[A]` Apply suggestions, `[R]` Review individually, `[S]` Skip section

**Individual task review options:** `[A]` Apply, `[E]` Edit, `[S]` Skip, `[O]` Mark out-of-spec

**Applying changes to Finished tasks:** When reconciliation applies to a task with `status: "Finished"`, the spec section it was verified against has changed. The existing `task_verification` is stale — it validated against the old acceptance criteria.

**Warning before applying:** When a section contains Finished tasks, warn before applying:
```
⚠️ Section "{section}" contains {N} Finished task(s) that will be reset to Pending:
  - Task {id}: "{title}"
Apply changes? [Y] Yes, reset and re-verify  [N] No, review individually instead
```
If the user selects `[N]`, fall through to `[R] Review individually` for that section (allows per-task decisions).

**On apply (confirmed):**
1. Update `spec_fingerprint` and `section_fingerprint` to current values
2. Clear `task_verification` (remove the field)
3. Set `status` back to `"Pending"`
4. Add note: `"Reset to Pending — spec section changed after verification. Needs re-implementation and re-verification."`

This ensures the structural invariant holds: no Finished task has a verification result that was computed against a different spec version than its current fingerprints.

**Edge cases:** New section → suggest new tasks. Section deleted → flag tasks for out-of-spec or deletion. Section renamed → detected as delete + add. No snapshot → fall back to full-spec comparison.
