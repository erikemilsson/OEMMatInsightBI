# Session Management Rules

How to preserve context, continue work, and manage plans across conversations.

User-facing session operations — resume flags (`--continue`/`--resume`), `/rename`, `/compact`, `/btw`, plan mode, checkpoint rewind — live in `.claude/README.md § "Session Operations"`. This file keeps the parts Claude must act on.

## Ending Sessions

When a `/work` session reaches a natural stopping point (blocking issue, end of day, context getting long):

1. **Run `/work pause`** — writes `.claude/tasks/.handoff.json` with:
   - Active task state and progress
   - Session knowledge (informal decisions, discovered patterns, user preferences)
   - What was promised as the next step
2. The next `/work` in a new conversation reads the handoff and resumes from there
3. **If `/work pause` is not run**, the next session has only task files, dashboard, and auto-memory — no reasoning context

`/work pause` also works as a **mid-session checkpoint** — pausing, continuing to work, and pausing again in the same session is normal use; each pause overwrites the handoff with the newest state.

**When Claude says "next session will..."** — that promise only survives if `/work pause` is run or the user resumes the session with `--continue`/`--resume`.

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

---

## Claude's Responsibilities

When a session is ending (user says goodbye, context is long, blocking issue reached):
- **Suggest `/work pause`** if there's active work context that would be lost
- **Never promise "next session will do X"** without writing a handoff or noting the intent in a durable location (handoff file, task notes, or auto-memory)
- **At session start**, check handoff file AND scan for Blocked/In Progress tasks — don't rely solely on the dashboard
