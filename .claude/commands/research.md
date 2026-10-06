---
disable-model-invocation: true
---

# Research Command

Investigate options for decisions, technology choices, or architectural questions. Spawns the research-agent to gather evidence, then writes its findings into decision records.

## Usage

```
/research {topic}           # Research a topic (creates decision record if needed)
/research {DEC-NNN}         # Research options for an existing decision (a `recorded` one: confirm, then reconsider)
/research                   # Auto-detect: find draft/proposed decisions needing research
```

## What It Does

1. **Identifies the investigation target** — a decision record, topic, or auto-detected gap
2. **Gathers context** — reads spec, related tasks, existing decisions, project learnings
3. **Spawns research-agent** — delegates investigation to a specialist agent
4. **Persists and reports results** — writes the artifacts the agent returns, presents findings and next steps

---

## Rules

**Authority boundary:** The research agent populates options and evidence. It does NOT make decisions. The user selects the option via the decision record's checkbox mechanism.

**Research agent CAN:** populate comparison matrices, draft the research archive, propose `status: proposed`, add questions, state recommendations — all returned in its report. Subagents can't write `.claude/` paths (DEC-004, `rules/agents.md § State Ownership`); this command writes them in Step 4.

**Research agent CANNOT:** write files, check selection checkboxes, approve decisions, touch spec or task files.

---

## Process

### Step 1: Identify Target

**If a decision ID was provided** (`/research DEC-001` or `/research 001`):
1. Find the decision record: glob `.claude/support/decisions/decision-*{id}*.md`
2. If not found: say so and offer to create the record under that ID, taking the topic from the blocked task's context (or asking the user for one line). On yes, create it as the topic branch's item 3 does, then go to Step 2; on no, stop
3. Read frontmatter: check `status`
4. If status is `approved` or `implemented`: report that the decision is already resolved. Offer to research validation of the chosen option instead.
5. If status is `superseded`: report and stop
6. If status is `recorded` (`decisions.md § "Agent-recorded decisions"`): tell the user and confirm — "DEC-{NNN} is an agent-recorded decision: it is already built and verified (task {related.tasks}). Researching it reopens it. [Y] Reconsider and research | [N] Leave as recorded". On `[N]`, stop. On `[Y]`, reconsider it as `/work reconsider DEC-NNN` does (`status: proposed`; if an older record has a `## Select an Option` box the agent ticked, untick it in the same edit and say so, or the next `/work` or `/iterate` approves it; the task stays Finished), then continue
7. If the record has no `## Select an Option` section (a reconsidered agent-recorded decision): insert the template sections it lacks, so the agent's edits and the user's selection have a place to land — `## Select an Option` directly under the title with one unchecked box per option the record already names, and empty `## Option Details` and `## Your Notes & Constraints` after `## Options Comparison`. Leave `## Decision` as it is (it records what was built) until the user selects

**If a topic was provided** (`/research OAuth libraries for Node.js`) — or `/work` Step 2b's `[R]` reaches a decision with no record yet (a task's `decision_dependencies` names a DEC-NNN with no record file):
1. Scan existing decision records for a match (title or background contains relevant keywords)
2. If match found: confirm with user — "Found DEC-{NNN}: {title}. Research this? [Y] Yes [N] No, create new" (if a task references the decision under a different ID, `/work` re-points its `decision_dependencies` to DEC-{NNN})
3. If no match or user says new:
   - Determine category: `architecture`, `technology`, `process`, `scope`, `methodology`, `vendor`
   - Create a new decision record using the template from `.claude/support/reference/decisions.md`
   - Pre-fill: title, category, `created` date, background (from the topic description)
   - Set status to `draft`
   - Assign the ID already named (by `/research DEC-NNN` or a task's `decision_dependencies`), if any; else the next available ID (glob existing records, increment)

**If no argument provided** (auto-detect mode):
1. Scan all `decision-*.md` files for status `draft` or `proposed`
2. Filter to decisions with empty or incomplete comparison matrices
3. If multiple found: present list and ask which to research
4. If one found: confirm and proceed
5. If none found: "No decisions need research. Use `/research {topic}` to start a new investigation."

### Step 2: Gather Context

Read (all reads, no modifications):
- The target decision record (full content)
- `.claude/spec_v{N}.md` — use version discovery (glob, highest N)
- Related task files (from decision's `blocks` and `related.tasks` fields)
- Related decision records (from `related.decisions` field)
- `.claude/support/learnings/` — project-specific patterns
- `.claude/support/decisions/.archive/` — existing research for this or related decisions

### Step 3: Spawn Research Agent

```
Agent tool call:
  subagent_type: "general-purpose"
  model: "opus"  # canonical value: .claude/CLAUDE.md § Model Requirement
  description: "Research {decision title or topic}"
  prompt: |
    You are the research-agent. Read `.claude/agents/research-agent.md` and follow
    the Research Workflow (Steps R1-R5).

    Decision record: {path to decision-*.md, or "none — topic-based research"}
    Topic: {topic description}
    Spec file: .claude/spec_v{N}.md
    Related tasks: {list of task file paths}
    Related decisions: {list of decision file paths}

    Investigate options and return the research archive and the decision-record
    edits in your report (Step R4). Don't write files — /research writes them.
    Do NOT select an option — populate evidence for the user to decide.

    Turn budget: about 25 tool calls. If you get close, stop and return your report with what you have, marked partial.
```

### Step 4: Handle Result

After the research agent returns its report:

1. **Persist the returned artifacts** (the agent can't write `.claude/` paths — DEC-004):
   - Write the research archive to the path the report gives (`.claude/support/decisions/.archive/YYYY-MM-DD_{decision-slug}.md`).
   - Apply each anchored edit to the decision record: find the anchor verbatim and replace what it covers with the replacement — for a line anchor, that line. For a heading anchor, the replacement is the body beneath it, up to the next heading of the same or higher level; the heading line itself stays. An anchor that doesn't match exactly once is not applied — don't guess; tell the user and show the edit.
   - Apply the frontmatter change, if any (`status: proposed` replaces `draft` only).
   - Skip any edit that checks a selection box or rewrites user text in `## Your Notes & Constraints` (authority boundary, § Rules).
   - The record edits trigger DEC-016's `permissions.ask` prompt. That's expected: this is the sanctioned route for decision-record edits (`rules/spec-workflow.md § "Direct edits to spec, decision, and vision files (DEC-016)"`).
   - If no record existed, the report carries suggested record content instead of edits: write the archive and present the suggestion to the user.

2. **Read the updated decision record** (or suggested content if no record existed)

3. **Present findings to user:**
   ```
   Research complete: {title}

   Options found:
   1. {Option A} — {one-line summary}
   2. {Option B} — {one-line summary}
   {3. Option C — if present}

   Recommendation: {agent's recommendation or "No clear winner — see comparison"}

   Decision record: .claude/support/decisions/{filename}
   Research archive: .claude/support/decisions/.archive/{filename}

   Next steps:
   - Review the decision record and research archive
   - Check your selection in the "Select an Option" section
   - Run /work to continue (tasks blocked by this decision will unblock)
   ```

4. **If research was incomplete** (report marked partial — the agent hit its turn budget): item 1 persists the partial archive and edits the same way. Then:
   ```
   Research partially complete. {N} options evaluated so far.
   Run /research {id} again for deeper analysis, or review what's available.
   ```

5. **If questions were added:**
   ```
   The research raised questions that would help narrow the analysis:
   {list of questions from decision record}

   Answer these in the decision record's "Your Notes & Constraints" section,
   then run /research {id} again for a more targeted investigation.
   ```

---

## Integration Points

### From `/work` Step 2b (Decision Gate)

When `/work` finds an unresolved decision blocking a task, it offers research as an option:

```
Decision DEC-001 is unresolved and blocks Task {id}.
  [R] Research options (spawns research-agent)
  [S] Skip (you'll research manually)
```

If user selects `[R]`: `/work` delegates to this command's Step 2-4 flow, skipping Step 1 only when the decision record already exists; with no record yet (e.g. a task's `decision_dependencies` names a DEC-NNN with no record file), Step 1's topic branch runs first.

### From `/iterate` (Implicit Decision Detection)

When `/iterate` detects vague language implying an unresolved choice, it can offer:

```
Implicit decision detected: {description}
  [C] Create decision record and research options
  [D] Document only — create decision record (research later)
  [S] Skip (not a real decision)
```

If user selects `[C]`: `/iterate` creates the decision record, then delegates to this command's Steps 2-4 flow (skipping Step 1 — the decision record already exists).

---

## Examples

```
# Research a specific decision
/research DEC-003

# Research a topic (finds or creates decision record)
/research "Best approach for real-time notifications"

# Auto-detect decisions needing research
/research
```
