# Session Management Rules

How to preserve context, continue work, and manage plans across conversations.

## Ending Sessions

When a `/work` session reaches a natural stopping point (blocking issue, end of day, context getting long):

1. **Run `/work pause`** — writes `.claude/tasks/.handoff.json` with:
   - Active task state and progress
   - Session knowledge (informal decisions, discovered patterns, user preferences)
   - What was promised as the next step
2. The next `/work` in a new conversation reads the handoff and resumes from there
3. **If `/work pause` is not run**, the next session has only task files, dashboard, and auto-memory — no reasoning context

**When Claude says "next session will..."** — that promise only survives if `/work pause` is run or the user resumes the session with `--continue`/`--resume`.

## Resuming Sessions

| Method | What you get | When to use |
|--------|-------------|-------------|
| `claude --continue` | Full conversation context from last session | Picking up exactly where you left off |
| `claude --resume` | Pick from session list, full context | Returning to a specific past session |
| Fresh `/work` | Task state + handoff (if exists) + auto-memory | Starting a new work session on the same project |
| `/clear` then `/work` | Task state + auto-memory only | Clean slate, no prior conversation context |

**Naming sessions with `/rename`:** By default sessions are listed by timestamp + first message. For long-running projects or multiple concurrent threads, run `/rename {descriptive-name}` to give the session a findable name (e.g., `oauth-migration`, `debugging-memory-leak`). Named sessions surface by name in `claude --resume` pickers.

## Which Persistence Mechanism When

Three mechanisms serve three different needs. Choose based on what you're trying to preserve:

| I want to... | Do this | Why this one |
|--------------|---------|-------------|
| Stop for the day, continue with `/work` | `/work pause` | Handoff is auto-read by `/work`, captures routing context |
| Stop for the day, continue with `--continue` | Just close the terminal | Conversation is preserved natively by Claude Code |
| Execute a plan with fresh context | Write plan to workspace → `/clear` → read and execute | Plan file is durable, human-readable, editable |
| Record a hazard or preference | Let auto-memory handle it | Memory is permanent, loaded every session |
| Resume from a crash | Nothing — automatic | PreCompact hook + session recovery pipeline |

**Key distinction:** Handoff = ephemeral, machine-consumed, auto-deleted. Plan file = persistent, human-reviewable, explicitly managed. Memory = permanent, knowledge-level. They don't overlap — they serve different time horizons.

## Managing Context Pressure

As conversations grow long, context gets compressed automatically. To manage this proactively:

- **`/compact focus on [topic]`** — guided summarization that preserves what you specify
- **`/clear`** — full reset; use when switching to unrelated work
- **`/btw {question}`** — ask a quick side question without polluting conversation history. The answer appears in a dismissible overlay and is NOT added to the transcript. Useful when you want to check something (e.g., "what's the syntax for ...") mid-work without derailing the current thread or bloating context.
- **CLAUDE.md and rules files** survive compaction automatically (re-read from disk)
- **Auto-memory** survives across sessions (stored on disk, loaded at start)

## Plans and Fresh Execution

The old "compact with plan" feature no longer exists. The replacement workflow:

### Explore → Plan → Execute with Fresh Context

1. **Explore:** Discuss the problem, research options, iterate on approach
2. **Plan:** Ask Claude to write the plan to a file:
   ```
   Write this plan to .claude/support/workspace/plan-[name].md
   ```
3. **Fresh context:** Run `/clear` (same session) or start a new conversation
4. **Execute:** Tell Claude to read and execute the plan:
   ```
   Read .claude/support/workspace/plan-[name].md and execute it
   ```

The plan file is durable — it survives `/clear`, compaction, and new sessions. Unlike conversation context, it can be reviewed, edited, and versioned.

### When to Use Plan Mode

Plan mode (`Shift+Tab` twice, or `/plan`) is for **read-only exploration** — Claude can read files and reason but not edit. Use it when:
- You want to understand something before committing to changes
- You want Claude to propose an approach without executing it
- You want to review what Claude would do before giving permission

Plan mode is about exploration, not persistence. For durable plans, write to a file.

## What Survives What

| Mechanism | Survives `/compact` | Survives `/clear` | Survives new session |
|-----------|:---:|:---:|:---:|
| Conversation context | Summarized | No | No (unless `--continue`) |
| CLAUDE.md / rules | Yes (re-read) | Yes (re-read) | Yes (re-read) |
| Auto-memory | Yes | Yes | Yes |
| Handoff file | Yes | Yes | Yes (consumed on read) |
| Plan in workspace file | Yes | Yes | Yes |
| Task JSON state | Yes | Yes | Yes |
| Dashboard | Yes | Yes | Yes |

## Checkpointing and Rewind

Every Claude action creates a checkpoint. Two ways to access them:

- **`Esc+Esc`** — opens the rewind menu immediately (press Escape twice)
- **`/rewind`** — opens the rewind menu as a slash command

From the rewind menu, you can restore:
- **Conversation only** — Claude forgets what it said, code changes preserved
- **Code only** — conversation preserved, file changes rolled back
- **Both** — full time-travel to the selected checkpoint

Checkpoints persist across sessions, so you can rewind even after closing and reopening. This is the complementary recovery mechanism to `/work pause` and handoff files: use handoff for planned wind-downs, checkpoints for recovering from an agent misstep or a wrong turn.

---

## Claude's Responsibilities

When a session is ending (user says goodbye, context is long, blocking issue reached):
- **Suggest `/work pause`** if there's active work context that would be lost
- **Never promise "next session will do X"** without writing a handoff or noting the intent in a durable location (handoff file, task notes, or auto-memory)
- **At session start**, check handoff file AND scan for Blocked/In Progress tasks — don't rely solely on the dashboard
