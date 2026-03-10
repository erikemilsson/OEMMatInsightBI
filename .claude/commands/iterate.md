# Iterate Command

Spec review and refinement. Identifies gaps, asks questions, proposes spec changes for user approval.

## Usage

```
/iterate                    # Review spec, focus on weakest area
/iterate {topic}            # Focus on a specific spec area
/iterate distill            # Extract buildable spec from vision document
```

Assesses spec readiness, asks focused questions (max 4), proposes changes as declarations for user approval.

**Scope:** All outputs from this command target the specification. When discussing implementation details, codebase patterns, or repo contents, translate observations into specification-level proposals — never suggest direct code changes. For implementation quality review, use `/review`.

---

## Rules

**Spec editing policy:** `propose_approve_apply` — Claude proposes spec changes as explicit change declarations; the user reviews and approves before Claude applies them. Claude handles the mechanics (versioning, archiving, applying edits) but never modifies spec content without presenting the declaration and receiving approval first. The user can modify, reject, or redirect any proposed change. See "Propose-Approve-Apply Boundary" below for full distinction.

---

## Process

### Step 1: Load Context

Determine the current spec version using the same version discovery as `/work`: glob for `.claude/spec_v*.md`, use the highest N. Read `.claude/spec_v{N}.md` and assess its current state.

### Step 1b: Check Feedback Items

Read `.claude/support/feedback/feedback.md` if it exists. Count items by status.

IF `new` count > 0 OR `refined` count > 0:
  Surface: "📝 {N} feedback items awaiting attention ({X} new, {Y} refined)"
  Options:
  - `[I]` Include refined items as context — load refined entries as context for Step 4 change proposals. After incorporation, mark items as `promoted` with date.
  - `[R]` Run `/feedback review` first — hand off to `/feedback review`, then return to `/iterate`.
  - `[S]` Skip — continue normally without feedback context.

IF no feedback items exist or file doesn't exist: continue silently.

### Step 2: Determine Mode

**If user specified `/iterate distill`:**

Enter distill mode. Extract buildable spec from a vision document.

1. **Locate vision doc:**
   - Check `.claude/vision/` for existing documents
   - If multiple exist, list them and ask which to use
   - If none exist, ask user to provide the document (paste or file path)

2. **Read and summarize the vision:**
   ```
   I've read your vision document: [filename]

   Summary: [2-3 sentence summary of core concept]

   Key themes I see:
   - [theme 1]
   - [theme 2]
   - [theme 3]
   ```

3. **Ask distillation questions:**
   ```
   Let's extract a buildable Phase 1 spec.

   1. What's the core value proposition in one sentence?
      (From your vision, I see: "[extracted summary]" - confirm or refine?)

   2. What must be working for this to be useful at all?
      (Your vision mentions several features - which are essential vs. nice-to-have for Phase 1?)

   3. What's explicitly NOT in Phase 1?
      (Your vision has ambitious ideas - which do we defer?)

   4. Who's the first user and what's their critical path?
   ```

4. **Carry structure through from vision doc:**

   When reading the vision document, recognize and preserve these structures:

   - **Phases:** If the vision describes natural boundaries ("build the pipeline first, then the dashboard"), structure the spec with phase sections (e.g., `## Phase 1: Data Pipeline`, `## Phase 2: Visualization`). Phases become the grouping mechanism for tasks during decomposition.
   - **Key Decisions:** If the vision identifies choices with multiple options, create placeholder sections in the spec noting work is blocked until the decision is resolved. For each decision, note:
     - What options are being considered
     - What depends on this decision
     - Whether it's an **inflection point** (outcome changes what gets built) — if so, don't add premature detail for dependent work
   - **Human Dependencies:** If the vision identifies things only the user can do (set up accounts, configure hosting, get API keys), flag these as human tasks in the spec.

5. **Present spec change declaration:**
   Present the proposed spec content as a change declaration (same format as Step 4):
   - Include `vision_source:` in frontmatter linking to the vision doc
   - Extract concrete requirements from vision's abstract concepts
   - Structure spec sections by phase when phases were identified
   - Add decision placeholders where unresolved choices block work
   - Add "Deferred to Future Phases" section for items not in Phase 1
   - Keep the spec high-level enough to remain a readable project overview, while precise enough for decomposition

6. **Apply on approval:**
   On user approval (`[Y]`, `[M]`, or `[P]`), create or update the spec file:
   - If no spec exists: create `.claude/spec_v1.md` with the approved content
   - If a spec exists: apply changes per the standard Step 5 flow (archive if warranted, then edit)
   ```
   Spec v{N} created/updated. Next steps:

   1. Review the spec file directly — edit anything that doesn't match your intent
   2. Run /iterate to refine specific sections
   3. When the spec passes readiness checks, run /work
   ```

**Re-running distill:** If the vision document is updated:
- Run `/iterate distill` again
- Claude reads the updated vision doc and proposes changes as a declaration
- On approval, Claude applies the changes to the existing spec (with versioning if warranted)
- The user can modify or reject any proposed change before it's applied

**Multiple vision documents:** If `.claude/vision/` contains multiple files, Claude lists them and asks which to use. To combine multiple vision docs, run distill once per document and merge the changes into the spec.

---

**If spec is empty or only has placeholders:**

A vision document is required before spec creation. Do not bootstrap a spec from scratch. Direct the user to brainstorm first:

```
The spec is empty. Before building a spec, you need a vision document.

1. Brainstorm your project in Claude Desktop (or any tool) — explore features,
   phases, key decisions, and constraints
2. Save the result to .claude/vision/
3. Run /iterate distill to extract a buildable spec from it

See .claude/support/reference/desktop-project-prompt.md for project instructions
that guide ideation sessions to produce well-structured vision documents.
```

If `.claude/vision/` already contains documents, suggest `/iterate distill` directly.

**If spec has content (spec review mode):**

Assess readiness and identify the weakest area. Report:

```
Checking spec readiness...

Current state:
- Has clear problem statement: ✓ / ✗
- Users identified: ✓ / ✗
- Core components described: ✓ / ✗
- Key decisions documented: ✓ / ✗
  - Resolved decisions: N (no blocker)
  - Pending decisions not blocking Phase 1: N (noted, not urgent)
  - Pending decisions blocking Phase 1: N ⚠️ (must resolve before /work)
  - Unresolved inflection points: N 🔴 (spec sections may be premature)
- Acceptance criteria defined: ✓ / ✗
- Blocking questions resolved: ✓ / ✗
- Feedback items pending: N new, M refined
- Phase boundaries clear: ✓ / ✗ / N/A
  - Phase dependencies make sense: ✓ / ✗
  - No Phase 2 content mixed into Phase 1: ✓ / ✗

Overall: Ready for /work | Needs more detail | Major gaps

Focusing on: [weakest area]
```

**Implicit decision detection:** When assessing "Key decisions documented," don't just count existing decision records — scan the spec for language that implies unresolved choices. Look for:
- Vague method references ("appropriate methods," "a suitable library," "the chosen approach")
- Unnamed technology choices ("a database," "a charting library," "an auth provider")
- Conditional language ("depending on the analysis method," "if we use X")
- Alternatives mentioned without resolution ("could use X or Y")

For each implicit decision found:
1. Flag it in the readiness check (contributes to `Key decisions documented: ✗`)
2. In Step 3, ask questions that surface whether it's an inflection point or pick-and-go
3. Offer to create a decision record and optionally research options:
   ```
   Implicit decision detected: {description}
     [C] Create decision record and research options (spawns research-agent)
     [D] Document only — create decision record (you'll research later)
     [S] Skip (not a real decision)
   ```
   If `[C]`: Create the decision record (see `support/reference/decisions.md` for the template), then delegate to the research workflow (see `.claude/commands/research.md` Steps 2-4). The research-agent will populate the comparison matrix and option details.
   If `[D]`: Create the decision record only. Decisions need to be trackable so `/work` can gate dependent tasks.

### Step 3: Ask Questions (max 4)

**Conversational context check:** If the conversation already contains clear direction for spec changes (e.g., from a preceding `/work` discussion or user feedback), summarize your understanding in 1-2 sentences and confirm before proposing changes, rather than asking fresh questions. Only ask new questions when genuine ambiguity remains about what the spec change should be.

Generate focused questions for the target area. Questions should:
- Be specific and answerable
- Build on each other logically
- Extract concrete details, not opinions
- Include example answers when helpful

**Wait for user responses before proceeding.**

### Step 4: Propose Changes (Change Declaration)

Based on answers, present an explicit change declaration — not copy-pasteable blocks, but a structured proposal the user can review and approve:

```
## Proposed Spec Changes

Based on your answers, here's what I'd change:

### Change 1: [Section name] — [add | modify | remove]

**Location:** spec_v{N}.md § [section path]
**What changes:** [Brief description of the change and why]
**Proposed text:**

> [The proposed new/modified section content]

### Change 2: [Section name] — [add | modify | remove]

**Location:** spec_v{N}.md § [section path]
**What changes:** [Brief description]
**Proposed text:**

> [The proposed content]

---

Approve these changes? [Y] Apply all | [M] Modify (tell me what to adjust) | [P] Partial (pick which changes) | [N] Skip
```

**Declaration principles:**
- State what changes and where — the user should understand the full impact before approving
- Show the proposed text so the user can judge tone and detail level
- Keep the spec high-level enough to remain readable as a project overview, while precise enough for decomposition and decision-making
- When modifying existing content, briefly note what's being replaced

### Step 5: Apply or Continue

Based on user response:

- **[Y] Apply all:** Execute the changes — archive current spec if warranted (see Spec Versioning below), then apply edits to the spec file. Report what was changed.
- **[M] Modify:** User describes adjustments. Revise the declaration and re-present.
- **[P] Partial:** User indicates which changes to apply. Apply selected, skip others.
- **[N] Skip:** No changes applied.

After applying (or skipping):

```
Changes applied to spec_v{N}.md.

Run /iterate again to continue refining, or /work to start building.
```

---

## Principles for Good Questions

Rather than following a script, Claude should:

1. **Establish fundamentals first** - Who uses it, what problem it solves, before diving into technical details
2. **Match depth to project seriousness** - A prototype doesn't need the same rigor as a production system
3. **Uncover constraints early** - Technology limits, timeline, dependencies shape everything
4. **Push for specificity** - "Users can log in" → "Users log in with email/password; errors shown within 2s"
5. **Identify the critical path** - What must work for this to be useful at all?

---

## Readiness Indicators

A spec is ready for `/work` when:

- [ ] The core problem and users are clear
- [ ] You could explain the system to someone in 2 minutes
- [ ] Key technical decisions are made (not deferred)
- [ ] You know what "done" looks like (acceptance criteria)
- [ ] Remaining questions won't block starting work

The threshold depends on project seriousness:
- **Prototype:** Problem and basic approach clear
- **MVP:** Above + key decisions made, acceptance criteria exist
- **Production:** Above + non-functional requirements, constraints documented

See `.claude/support/reference/spec-checklist.md` for full readiness criteria.

---

## When to Use Each Mode

| Situation | Command | Why |
|-----------|---------|-----|
| Starting from scratch, no docs | Brainstorm first, then `/iterate distill` | Vision document required before spec creation |
| Have a vision/design document | `/iterate distill` | Extracts buildable scope from abstract ideas |
| Spec exists, want to improve | `/iterate` | Auto-detects weakest area |
| Spec exists, specific gap known | `/iterate {topic}` | Focuses on that area |
| Adding a new feature to existing spec | `/iterate {feature}` | Targets the new section |
| Vision doc updated after initial distill | `/iterate distill` | Re-read vision and suggest updates |
| Mid-work discussion surfaced bigger changes | `/iterate` | Translates discussion into spec changes |
| Tasks in progress, want quality check | `/review` | Implementation review (separate command) |

---

## Spec Versioning

### Core Invariant: One Spec File at a Time

There must always be exactly **one** `spec_v{N}.md` file in `.claude/`. Not two during a transition, not zero. One. This is enforced by `/health-check` and validated by `/work` on every run.

### Direct Edits Are Always Safe

You can edit the spec file directly at any time. The system handles this gracefully:

- **The decomposed snapshot** (`spec_v{N}_decomposed.md` in `previous_specifications/`) preserves the state when tasks were created
- **Drift detection** in `/work` compares the current spec against the snapshot and shows exactly what changed
- **No data loss is possible** — the "before" state is always available for comparison

You never need to version before editing. If your edits turn out to be substantial enough for a new version, `/work` will suggest it (see `.claude/support/reference/drift-reconciliation.md` § "Substantial Change Detection").

### Propose-Approve-Apply Boundary

The `propose_approve_apply` policy means Claude proposes spec changes but never applies them without explicit user approval.

**Claude CAN do autonomously (infrastructure):**
- Copy a spec to the archive (preserving content the user wrote)
- Create a new version file as a copy of the current one
- Update the frontmatter version number and dates
- Delete the old version file after archiving

**Claude CAN do after user approval (content):**
- Add new spec sections or requirements
- Modify acceptance criteria, scope, or architecture decisions
- Remove sections

**Claude CANNOT do:**
- Apply any content change without first presenting it as a change declaration and receiving user approval
- Skip the declaration step, even for "obvious" changes

This is the distinction between **infrastructure** (autonomous file operations) and **authorship** (requires declaration → approval → apply). The user controls what the spec says; Claude proposes and executes on approval.

### Version Transition Procedure

When a version bump is warranted, Claude executes this 5-step procedure:

```
1. CONFIRM: "Suggest creating spec v{N+1}. Reason: {reason}. Proceed? [Y/N]"
   → User must approve — this is a checkpoint, not automatic

2. ARCHIVE: Copy .claude/spec_v{N}.md → .claude/support/previous_specifications/spec_v{N}.md

3. CREATE: Copy .claude/spec_v{N}.md → .claude/spec_v{N+1}.md
   → Bump frontmatter: version: {N+1}, status: draft, updated: {today}
   → New version starts in "draft" because new content needs review

4. REMOVE: Delete .claude/spec_v{N}.md
   → Single-spec invariant maintained

5. REPORT:
   "spec_v{N} archived → previous_specifications/spec_v{N}.md
    spec_v{N+1} is now the active spec (status: draft).
    Run /iterate to propose changes, or edit directly and run /work to continue."
```

**After the transition:** The user edits `spec_v{N+1}.md` with their changes (or uses `/iterate` to refine). When they run `/work`, task migration handles the transition (see `.claude/support/reference/drift-reconciliation.md` § "Task Migration on Version Transition").

### When to Create a New Version

| Trigger | Version bump? | Why |
|---------|:---:|-----|
| Phase transition (Phase N complete → N+1) | **Yes** | New work scope, clean baseline |
| Inflection point resolved, major scope change | **Yes** | What gets built changed fundamentally |
| User explicitly requests it | **Yes** | User authority |
| `/work` detects substantial changes (see `drift-reconciliation.md`) | **Suggested** | System offers the choice; user decides |
| Adding detail to existing sections | No | Same scope, more precision |
| Minor clarifications, typos | No | Not substantive |
| Adding a new feature section | Maybe | Claude asks user if scope expansion warrants it |

---

## Working with Vision Documents

Vision documents capture ideation, design philosophy, and future thinking. Common sources:
- Brainstorming sessions in Claude Desktop
- Product thinking documents
- Technical architecture explorations

**Distillation workflow:**
1. Save vision doc to `.claude/vision/`
2. Run `/iterate distill`
3. Answer questions to extract Phase 1 scope
4. Spec links to vision via `vision_source:` frontmatter

**Once a spec exists, the spec is the single source of truth.** Vision docs become historical context only—useful for understanding original intent or planning future phases, but not consulted during implementation.

---

## Post-Inflection-Point Re-Entry

When `/iterate` runs, it automatically checks for recently resolved inflection point decisions. No special subcommand is needed — `/iterate` just notices.

**Detection logic:**
```
1. Read all decision-*.md files in .claude/support/decisions/
2. Find decisions where:
   - inflection_point: true in frontmatter
   - status is "approved" or "implemented"
   - spec_revised is NOT true (spec hasn't been updated for this decision yet)
3. IF any found:
   │
   │  Inflection point resolved: {decision_title}
   │  Selected: {chosen_option}
   │
   │  This decision changes what gets built. Let me review
   │  the spec sections affected by this choice.
   │
   │  Affected sections:
   │  - {section 1} — {how it's affected}
   │  - {section 2} — {how it's affected}
   │
   │  [Presents change declaration per Step 4 format — user approves before changes are applied]

4. After presenting the change declaration, also include updating the decision record:
   │
   │  Also update the decision record frontmatter:
   │  Add `spec_revised: true` and `spec_revised_date: YYYY-MM-DD`
   │
   │  This tells `/work` that the spec now reflects this decision.
```

**Why `spec_revised` instead of time-based detection:** The previous approach used `decided date is recent (within last 7 days)` which breaks across long session gaps and has no durable record of when `/iterate` last ran. The `spec_revised` field is a state-based signal — both `/work` and `/iterate` check it, and it persists until the user explicitly marks the spec as updated. This makes inflection point handling reliable across any number of sessions.

This auto-detection means the user doesn't need to remember which decisions were inflection points or manually trigger a review. Running `/iterate` after `/work` suggests it is sufficient.

---

## Spec Versioning at Phase Transitions

When Phase 1 completes and Phase 2 begins, Claude executes the Version Transition Procedure (above) to create `spec_v{N+1}.md`. Phase transitions always warrant a new version — they represent a clean baseline for new work.

**After the version transition**, `/iterate` should suggest a spec revision if:

- Phase 2 sections are vague or placeholder-level
- Decisions resolved during Phase 1 affect Phase 2 scope
- Phase 1 learnings suggest Phase 2 adjustments

**Process:**
1. `/work` detects Phase 1 completion → executes Version Transition Procedure → suggests running `/iterate`
2. `/iterate` reads the new spec version, focuses on Phase 2 sections
3. Asks targeted questions about Phase 2 scope (now informed by Phase 1 results)
4. Presents change declaration for Phase 2 sections
5. On user approval, applies changes to `spec_v{N+1}.md`, then user runs `/work` to decompose Phase 2 and continue
