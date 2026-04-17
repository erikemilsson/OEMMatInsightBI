# Feedback Command

Quick capture and triage of project improvement ideas. Provides a structured path from fleeting thoughts to spec integration, with mandatory impact assessment before anything reaches the spec.

## Usage

```
/feedback [text]              # Quick capture: save an idea
/feedback list                # Show summary counts and item list
/feedback review              # 3-phase review: grouping → refinement → impact assessment
/feedback review {id}         # Single-item review (adapts to item's current status)
```

---

## Rules

- IDs are sequential: `FB-001`, `FB-002`, etc.
- Storage: `.claude/support/feedback/feedback.md` (one `## FB-NNN:` heading per entry)
- Terminal items move to `.claude/support/feedback/archive.md`
- `feedback.md` is an inbox — only actionable statuses (`new`, `reviewing`, `refined`, `ready`)
- `archive.md` holds all terminal statuses (`promoted`, `absorbed`, `closed`, `archived`)
- Promotion to spec happens via `/iterate`, not within `/feedback`
- Never delete feedback without archiving — always preserve with reason
- Claude does not make decisions for the user — always ask for input on grouping, refinement, and assessment

---

## Status Lifecycle

```
new → reviewing → refined → ready → promoted (auto-archived via /iterate)
new → absorbed (combined into another, immediately archived)
new → closed (investigated, decided against, archived)
new → archived (not relevant, quick triage)
```

| Status | Location | Meaning |
|--------|----------|---------|
| `new` | feedback.md | Just captured, not yet reviewed |
| `reviewing` | feedback.md | Currently being triaged |
| `refined` | feedback.md | Distilled to core insight, awaiting impact assessment |
| `ready` | feedback.md | Impact assessed and user-approved, eligible for `/iterate` |
| `promoted` | archive.md | Incorporated into spec via `/iterate` |
| `absorbed` | archive.md | Combined into another item (has `absorbed_into` pointer) |
| `closed` | archive.md | Investigated but decided against |
| `archived` | archive.md | Not relevant (quick triage) |

---

## Process

### Mode 1: Quick Capture (`/feedback [text]`)

1. Read `.claude/support/feedback/feedback.md` AND `.claude/support/feedback/archive.md`
2. Parse all `## FB-NNN:` headings in both files to find the highest `FB-NNN` ID
3. Assign next sequential ID: `FB-{N+1}` (zero-padded to 3 digits)
4. Append new entry to `feedback.md`:

```markdown
## FB-NNN: [Brief title derived from text]

**Status:** new
**Captured:** YYYY-MM-DD

[Full text as provided by user]
```

5. Confirm:
```
Captured as FB-NNN: [title]
Use /feedback review to triage, or /feedback list to see all items.
```

**Title derivation:** Extract a brief (3-8 word) title from the user's text. Use the first clause or sentence if short enough; otherwise summarize the core idea.

**Edge cases:**
- If `feedback.md` doesn't exist or has no entries, start with `FB-001`
- If the feedback directory doesn't exist, create it with the template files
- Empty text: ask "What's the idea?" — don't create an empty entry

---

### Mode 2: List (`/feedback list`)

1. Read `.claude/support/feedback/feedback.md` AND `.claude/support/feedback/archive.md`
2. Parse all `## FB-NNN:` entries and their status lines in both files
3. Display summary:

```
Feedback Items:

  Active (in feedback.md):
    new:       N items
    refined:   N items
    ready:     N items

  Resolved (in archive.md):
    promoted:  N items (incorporated into spec)
    absorbed:  N items (combined into other items)
    closed:    N items (decided against)
    archived:  N items (not relevant)

Active Items:
  FB-003: [title] (new)
  FB-004: [title] (refined)
  FB-005: [title] (ready)
  ...

Use /feedback review to triage items.
```

**Notes:**
- Count resolved items by reading `archive.md` and grouping by status
- Sort by ID within each status group
- Only list individual items from `feedback.md` (active inbox)
- If no active items exist: "No active feedback. Use `/feedback [text]` to capture an idea."
- If no items exist in either file: "No feedback captured yet. Use `/feedback [text]` to capture an idea."

---

### Mode 3: Batch Review (`/feedback review`)

A 3-phase process that takes feedback from capture to spec-readiness. Each phase completes before the next begins. The user controls progression.

#### Phase 1: Overview & Grouping

1. Read `.claude/support/feedback/feedback.md`
2. Show ALL non-terminal items with their current status:

```
Feedback Overview:

  FB-003: Agent Teams as future parallel execution mode (new)
  FB-004: Clarify decision ownership (new)
  FB-005: User-facing documents placement (refined)
  FB-007: Early-exit fast path in /work (new)

4 active items.
```

3. Suggest combinations based on shared themes or affected areas:

```
Possible combinations:
  FB-005 + FB-006 → Both address user experience of project structure
    (or keep separate if you prefer)

No other items seem related enough to combine.

[C] Combine suggested items | [A] Adjust grouping | [K] Keep all separate
```

4. **Wait for user response.**

**If combining:**
- Create a new entry with next sequential ID
- Title: derived from the combined theme
- Body: synthesized from both originals, preserving key details
- If any original was `refined`, carry the refined insights into the new entry's body and set status to `reviewing` (the combined insight needs re-confirmation, but the user's thinking is preserved). Otherwise set status to `new`.
- Present the new entry for user confirmation before finalizing
- On confirmation: move originals to `archive.md` with:
  ```
  **Status:** absorbed
  **Absorbed:** YYYY-MM-DD — Combined into FB-NNN
  **Absorbed Into:** FB-NNN
  ```
- Remove originals from `feedback.md`
- Confirm: "FB-00X and FB-00Y absorbed into FB-00Z."

**If no items to combine or user keeps all separate:** proceed to Phase 2.

#### Phase 2: Refinement

1. Collect all items with status `new` or `reviewing` from `feedback.md`
2. Items already `refined` or `ready` skip this phase (noted to user: "FB-NNN already refined, skipping.")
3. If no items need refinement: proceed to Phase 3
4. For each item needing refinement:

```
Refining FB-NNN: [title]

> [Original captured text]

Options:
  [R] Refine — distill this idea
  [C] Close — investigated, decided against
  [N] Not relevant — archive with reason
  [S] Skip — leave for later
  [E] Edit — update the text
```

5. **Wait for user response before proceeding to the next item.**

##### Action: Refine [R]

1. Set status to `reviewing`
2. Ask 1-2 clarifying questions to distill the core insight:
   - "What specific improvement would this enable?"
   - "Which part of the project does this affect?"
   (Adapt questions to the feedback content — these are examples, not a script)
3. Based on answers, write a `**Refined:**` line capturing the distilled insight
4. Set status to `refined`
5. Ask: "Are you done with this one? [Y] Yes | [E] Edit the refined text"
   - `[Y]`: Confirm and move to next item
   - `[E]`: User provides updated refined text, then re-confirm

##### Action: Close [C]

1. Ask: "Brief reason for closing?"
2. Move the full entry from `feedback.md` to `archive.md`, adding:
   ```
   **Closed:** YYYY-MM-DD — [reason]
   ```
3. Set status to `closed`
4. Remove the entry from `feedback.md`
5. Confirm: "FB-NNN closed."

Use `[C] Close` when the idea was investigated or discussed but deliberately decided against. This is different from `[N] Not relevant` which is for quick triage of ideas that don't apply.

##### Action: Not Relevant [N]

1. Ask: "Brief reason for archiving?"
2. Move the full entry from `feedback.md` to `archive.md`, adding:
   ```
   **Archived:** YYYY-MM-DD — [reason]
   ```
3. Remove the entry from `feedback.md`
4. Confirm: "FB-NNN archived."

##### Action: Skip [S]

1. Leave the entry unchanged
2. Move to the next item
3. Confirm: "FB-NNN skipped."

##### Action: Edit [E]

1. Ask: "Updated text?"
2. Replace the original text in the entry
3. Return to the options prompt for the same item (re-present [R]/[C]/[N]/[S]/[E])

#### Phase 3: Impact Assessment

1. After Phase 2 completes, list all `refined` items:

```
Refined items ready for impact assessment:

  FB-003: [title]
  FB-004: [title]
  FB-007: [title]

Which items would you like to assess? [A] All | [#] Specific IDs (e.g., "3, 7") | [S] Skip for now
```

2. **Wait for user response.** The user controls which items to assess — this is not automatic.

3. For each selected item, read the spec (`.claude/spec_v{N}.md`) and active task files (`.claude/tasks/task-*.json`), then present:

```
Impact Assessment — FB-NNN: [title]

  Refined insight: [one-line refined text]

  Spec sections affected:
    - § [section] — [what would change]
    - § [section] — [what would change]

  Active task impact:
    - Task [ID]: [title] ([status]) — [how affected]
    - (or: No active tasks affected)

  Scope change: [additive | corrective | reductive]
    [One sentence explaining the scope impact]

  Decision conflicts:
    - decision-NNN: [conflict description]
    - (or: No conflicts with resolved decisions)

  Phase impact: [current phase | future phase | new phase | cross-phase]
    [One sentence on timing]

Actions: [Y] Approve — mark as ready | [C] Close — decide against | [N] Not relevant — archive | [S] Skip for now
```

4. **Wait for user response.**

**Actions:**
- `[Y]` Approve: Set status to `ready`. Confirm: "FB-NNN is ready for `/iterate`."
- `[C]` Close: Ask for reason. Move to `archive.md` with `**Closed:** YYYY-MM-DD — [reason]`. Confirm: "FB-NNN closed."
- `[N]` Not relevant: Ask for reason. Move to `archive.md` with `**Archived:** YYYY-MM-DD — [reason]`. Confirm: "FB-NNN archived."
- `[S]` Skip: Leave as `refined`. Confirm: "FB-NNN skipped — remains refined."

**Assessment rules:**
- Always read task files to check for in-progress or pending work that would be affected. Don't guess — check the actual task data.
- If no spec exists yet (pre-`/work` project), skip task impact and note that assessment is against the spec only.
- For scope expansions, be explicit about what's being added.
- For conflicts with resolved decisions, reference the decision record by ID.
- If the assessment reveals that a feedback item should be a formal decision (multiple viable approaches, significant trade-offs), say so and offer to create a decision record instead.

---

### Mode 4: Single Review (`/feedback review {id}`)

Adapts to the item's current status rather than running the full 3-phase process.

1. Parse the ID (accept `FB-NNN` or just the number `NNN`)
2. Find the entry in `feedback.md`
3. If not found: check `archive.md`. If found there: "FB-NNN is archived ([status]). No further action needed."
4. If not found in either: "FB-NNN not found. Use `/feedback list` to see available items."
5. Route based on current status:
   - `new` or `reviewing` → Present Phase 2 refinement interface, then offer Phase 3
   - `refined` → Present Phase 3 impact assessment
   - `ready` → "FB-NNN is assessed and ready for `/iterate`." Offer: `[C] Close | [N] Not relevant | [K] Keep as ready`

---

## Promotion (via `/iterate`)

Promotion is NOT handled by `/feedback`. It happens in `/iterate` Step 1b:

1. `/iterate` reads `feedback.md` and checks for `ready` items
2. If `ready` items exist, offers to include them as context for spec change proposals
3. After spec changes are approved and applied, `/iterate` auto-archives promoted items:
   - Set status to `promoted`
   - Add: `**Promoted:** YYYY-MM-DD — Incorporated into spec v{N} § [section]`
   - Move from `feedback.md` to `archive.md`

Only `ready` items are eligible — this ensures every promoted item has gone through grouping, refinement, impact assessment, and user approval before reaching the spec.

---

## Dashboard Integration

When `feedback.md` has entries with actionable statuses, the dashboard's Action Required section includes:

```
- 📝 **{N} feedback items** awaiting attention ({X} new, {Y} refined, {Z} ready) → /feedback review
```

This is a derived line — computed during dashboard regeneration, not stored. It appears only when there are actionable items. The counts tell the user what's needed: `new` items need review, `refined` items need assessment, `ready` items can go to `/iterate`.

---

## Edge Cases

- **Concurrent feedback during `/work`:** Quick capture works at any time — it only appends to `feedback.md`, no conflicts with other operations
- **Empty feedback file:** All modes handle gracefully — capture creates the first entry, list/review report "no items"
- **ID gaps:** If FB-001, FB-002, FB-003 exist and FB-002 is archived, the next capture is FB-004 (IDs are based on the highest existing ID across both files, never reused)
- **Absorption IDs:** When items are absorbed, the new combined entry gets the next sequential ID. Absorbed originals keep their original IDs in `archive.md` for audit trail.
- **Large feedback log:** If `feedback.md` exceeds 50 entries, suggest running `/feedback review` to triage
- **Mixed-state sessions:** Phase 1 shows all items regardless of status. Phase 2 skips already-refined items. Phase 3 only operates on `refined` items. A review session with items at different statuses flows naturally through all three phases.
- **No spec yet:** Impact assessment (Phase 3) works without task files — it assesses against the spec only, noting that no tasks exist yet
- **Existing `FEEDBACK:{id}` markers:** No conflict — those use task IDs for per-task inline feedback in the dashboard; this system uses `FB-NNN` IDs for project-level feedback
