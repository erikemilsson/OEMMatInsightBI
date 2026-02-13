# Research Command

Investigate options for decisions, technology choices, or architectural questions. Spawns the research-agent to gather evidence and populate decision records.

## Usage

```
/research {topic}           # Research a topic (creates decision record if needed)
/research {DEC-NNN}         # Research options for an existing decision
/research                   # Auto-detect: find draft/proposed decisions needing research
```

## What It Does

1. **Identifies the investigation target** — a decision record, topic, or auto-detected gap
2. **Gathers context** — reads spec, related tasks, existing decisions, project learnings
3. **Spawns research-agent** — delegates investigation to a specialist agent
4. **Reports results** — presents findings and next steps

---

## Rules

**Authority boundary:** The research agent populates options and evidence. It does NOT make decisions. The user selects the option via the decision record's checkbox mechanism.

**Research agent CAN:** populate comparison matrices, write research archives, update status to `proposed`, add questions, state recommendations.

**Research agent CANNOT:** check selection checkboxes, approve decisions, write to spec or task files.

---

## Process

### Step 1: Identify Target

**If a decision ID was provided** (`/research DEC-001` or `/research 001`):
1. Find the decision record: glob `.claude/support/decisions/decision-*{id}*.md`
2. If not found: report error and stop
3. Read frontmatter: check `status`
4. If status is `approved` or `implemented`: report that the decision is already resolved. Offer to research validation of the chosen option instead.
5. If status is `superseded`: report and stop

**If a topic was provided** (`/research OAuth libraries for Node.js`):
1. Scan existing decision records for a match (title or background contains relevant keywords)
2. If match found: confirm with user — "Found DEC-{NNN}: {title}. Research this? [Y] Yes [N] No, create new"
3. If no match or user says new:
   - Determine category: `architecture`, `technology`, `process`, `scope`, `methodology`, `vendor`
   - Create a new decision record using the template from `.claude/support/reference/decisions.md`
   - Pre-fill: title, category, `created` date, background (from the topic description)
   - Set status to `draft`
   - Assign next available ID (glob existing records, increment)

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
Task tool call:
  subagent_type: "general-purpose"
  model: "opus"
  max_turns: 25
  description: "Research {decision title or topic}"
  prompt: |
    You are the research-agent. Read `.claude/agents/research-agent.md` and follow
    the Research Workflow (Steps R1-R5).

    Decision record: {path to decision-*.md, or "none — topic-based research"}
    Topic: {topic description}
    Spec file: .claude/spec_v{N}.md
    Related tasks: {list of task file paths}
    Related decisions: {list of decision file paths}

    Investigate options, populate the decision record, and write a research
    archive document. Do NOT select an option — populate evidence for the
    user to decide.
```

### Step 4: Handle Result

After the research agent completes:

1. **Read the updated decision record** (or suggested content if no record existed)

2. **Present findings to user:**
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

3. **If research was incomplete** (agent hit turn limit):
   ```
   Research partially complete. {N} options evaluated so far.
   Run /research {id} again for deeper analysis, or review what's available.
   ```

4. **If questions were added:**
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

If user selects `[R]`: `/work` delegates to this command's Step 2-4 flow (skipping Step 1 — the decision is already identified).

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
