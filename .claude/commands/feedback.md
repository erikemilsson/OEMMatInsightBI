# Feedback Command

Quick capture and triage of project improvement ideas. Provides a path from fleeting thoughts to spec integration.

## Usage

```
/feedback [text]              # Quick capture: save an idea
/feedback list                # Show summary counts and item list
/feedback review              # Batch triage: review all new/reviewing items
/feedback review {id}         # Single-item review (e.g., /feedback review FB-003)
```

---

## Rules

- IDs are sequential: `FB-001`, `FB-002`, etc.
- Storage: `.claude/support/feedback/feedback.md` (one `## FB-NNN:` heading per entry)
- Archived items move to `.claude/support/feedback/archive.md`
- Promotion to spec happens via `/iterate`, not within `/feedback`
- Never delete feedback without archiving — always preserve with reason

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

1. Read `.claude/support/feedback/feedback.md`
2. Parse all `## FB-NNN:` entries and their status lines
3. Display summary:

```
Feedback Items:

  new:      N items
  refined:  N items
  promoted: N items
  archived: N items (in archive.md)

Active Items:
  FB-001: [title] (new)
  FB-002: [title] (refined)
  FB-003: [title] (new)
  ...

Use /feedback review to triage new items.
```

**Notes:**
- Count archived items by reading `archive.md`
- Sort by ID within each status group
- If no items exist: "No feedback captured yet. Use `/feedback [text]` to capture an idea."

---

### Mode 3: Batch Review (`/feedback review`)

1. Read `.claude/support/feedback/feedback.md`
2. Collect all entries with status `new` or `reviewing`
3. If none found: "No items to review. All feedback has been triaged."
4. For each item, present the review interface:

```
Reviewing FB-NNN: [title]

> [Original captured text]

Options:
  [R] Relevant — refine this idea
  [N] Not relevant — archive with reason
  [S] Skip — leave for later
  [E] Edit — update the text
```

5. **Wait for user response before proceeding to the next item.**

#### Action: Relevant [R]

1. Set status to `reviewing`
2. Ask 1-2 clarifying questions to distill the core insight:
   - "What specific improvement would this enable?"
   - "Which part of the project does this affect?"
   (Adapt questions to the feedback content — these are examples, not a script)
3. Based on answers, write a `**Refined:**` line capturing the distilled insight
4. Set status to `refined`
5. Confirm: "FB-NNN refined. Will surface in next `/iterate` run."

#### Action: Not Relevant [N]

1. Ask: "Brief reason for archiving?"
2. Move the full entry from `feedback.md` to `archive.md`, adding:
   ```
   **Archived:** YYYY-MM-DD — [reason]
   ```
3. Remove the entry from `feedback.md`
4. Confirm: "FB-NNN archived."

#### Action: Skip [S]

1. Leave the entry unchanged
2. Move to the next item
3. Confirm: "FB-NNN skipped."

#### Action: Edit [E]

1. Ask: "Updated text?"
2. Replace the original text in the entry
3. Return to the options prompt for the same item (re-present [R]/[N]/[S]/[E])

---

### Mode 4: Single Review (`/feedback review {id}`)

Same as batch review but for a single specified item.

1. Parse the ID (accept `FB-NNN` or just the number `NNN`)
2. Find the entry in `feedback.md`
3. If not found: "FB-NNN not found. Use `/feedback list` to see available items."
4. Present the review interface (same as batch review Step 4)
5. Process the user's choice (same actions as batch review)

---

## Promotion (via `/iterate`)

Promotion is NOT handled by `/feedback`. It happens in `/iterate` Step 1b:

1. `/iterate` reads `feedback.md` and counts items by status
2. If refined items exist, offers to include them as context for spec suggestions
3. After incorporation, `/iterate` marks items as `promoted` with date:
   ```
   **Promoted:** YYYY-MM-DD
   ```

This keeps promotion tied to the spec review workflow where it belongs.

---

## Dashboard Integration

When `feedback.md` has entries with status `new` or `refined`, the dashboard's Action Required section includes:

```
- 📝 **{N} feedback items** awaiting attention ({X} new, {Y} refined) → /feedback review
```

This is a derived line — computed during dashboard regeneration, not stored. It appears only when there are actionable items. The count includes both new items (need `/feedback review`) and refined items (need `/iterate` to promote).

---

## Edge Cases

- **Concurrent feedback during `/work`:** Quick capture works at any time — it only appends to `feedback.md`, no conflicts with other operations
- **Empty feedback file:** All modes handle gracefully — capture creates the first entry, list/review report "no items"
- **ID gaps:** If FB-001, FB-002, FB-003 exist and FB-002 is archived, the next capture is FB-004 (IDs are based on the highest existing ID across both files, never reused)
- **Large feedback log:** If `feedback.md` exceeds 50 entries, suggest running `/feedback review` to triage
- **Existing `FEEDBACK:{id}` markers:** No conflict — those use task IDs for per-task inline feedback in the dashboard; this system uses `FB-NNN` IDs for project-level feedback
