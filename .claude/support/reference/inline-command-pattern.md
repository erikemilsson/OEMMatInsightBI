# Inline Command Pattern

**Pattern reference, not enforced behavior.** The template does not ship inline-capable slash commands. This doc describes the canonical pattern for downstream projects that compose slash commands — when a child command (e.g., `/coloring`, `/grooming`, `/wardrobe`) can run **standalone** OR be **inline-invoked from a parent command** (e.g., `/onboard`).

The pattern emerged from styler's composable-command architecture (2026-04-27). Capturing it here lets future inline-capable commands inherit a single reference instead of re-deriving the shape from a peer.

---

## When This Pattern Applies

- A child command can run on its own (`/coloring` from the prompt)
- A parent command can invoke the same child mid-flow (`/onboard` runs `/coloring` as a step)
- The child has deterministic outputs that the parent depends on
- Re-running the child with the same inputs should not regenerate (idempotency required)

If a command runs **only** standalone or **only** as a step inside another, this pattern is overkill. Use it when the same logic genuinely needs to serve both call sites.

---

## Section Header

Use a consistent section header in the child command's markdown so reviewers can scan for the inline contract:

```
## Inline Invocation from /{parent}
```

Place this section **after** the standalone Usage section and **before** the Process section. The parent command's documentation should also reference this header by name.

---

## Named-Subroutine Contract Table

Document the inline call site with a four-column contract table:

| Column | Purpose | Example |
|--------|---------|---------|
| **Inputs** | Arguments the parent must pass at the call site | `selfie_path: string, capture_date: ISO date` |
| **Outputs** | What the child returns to the parent (and where they're persisted) | `coloring_analysis.json in /docs/style/coloring/{date}/` |
| **Standalone wrapper** | What happens additionally when run standalone (e.g., prompt for missing inputs, write progress to disk) | `Prompts user for selfie if not provided; writes /progress/coloring.json` |
| **Inline call site** | The exact prompt/invocation shape the parent uses | `/coloring selfie=$selfie_path date=$today` |

The parent's process step refers to the child by command name and trusts the contract: "Step 4: `/coloring` → reads `coloring_analysis.json` from `Outputs`."

---

## Idempotency Contract

Inline commands MUST be idempotent — running them twice with the same inputs in the same wall-clock window produces the same output. The parent might re-run the child during retry or resumption.

Document the **dedup tuple** explicitly:

```
**Idempotency Contract**

This command is keyed on (selfie_path, capture_date). Re-running with the
same tuple on the same day SHALL NOT regenerate outputs — the existing
analysis is returned. The dedup tuple is computed at the start of the
Process section.
```

**Choosing the dedup tuple:** pick the smallest stable identity that uniquely identifies a "run." Common choices:

- **Content + date:** for analyses that vary by user-provided artifact + day (e.g., `selfie_path + capture_date`)
- **File path:** for analyses keyed on a single user-provided file (e.g., `item_file_path`)
- **Composite ID:** for analyses keyed on a known entity ID (e.g., `wardrobe_item_id`)

**What NOT to use:**

- Timestamps with sub-day precision (will never dedup)
- Session IDs (each session is a new run by definition)
- Random or generated IDs that re-derive on each call

When the dedup tuple drifts between sibling inline commands (e.g., one uses `selfie+date`, another uses `selfie+session_id`), the parent's retry behavior becomes inconsistent. Pick the tuple shape early and keep all siblings aligned.

---

## Standalone-Only Step Flag

Steps that run **only when standalone** (e.g., prompt the user for missing inputs, ask follow-up questions, write progress files) must be flagged so the inline invocation knows to skip them:

```
### Step 2: Confirm selfie path

**Standalone-only.** Skipped in inline invocation — the parent passes
`selfie_path` directly.

Ask the user for the selfie path if not provided as an argument.
```

The parent does NOT need to read these steps to know they're skipped — the flag is sufficient. The child handles its own conditional logic based on call-site context.

**Detection inside the child:** typical implementations check whether all required inputs were passed as arguments (inline) vs needing prompts (standalone). The check happens once at the start; the standalone-only steps are then skipped via a single conditional.

---

## Retirement Callout

When a command **used to** be a delegate-and-stop step (parent dispatched the child, child took over the conversation) but has been refactored into an inline subroutine (parent stays in control, child returns outputs), document the retirement to keep prior users oriented:

```
## ⚠️ Retirement Notice: Delegate-and-Stop Framing

Earlier versions of /coloring used a delegate-and-stop pattern — the
parent (/onboard) handed off control and the user finished /coloring
before returning. As of YYYY-MM-DD this command is inline only: the
parent retains control and /coloring returns outputs at the call site.

Old behavior referenced in:
  - docs/style/onboard-flow-v1.md (historical)
  - any project notes mentioning "/coloring takes over"

If you're integrating an old reference, treat /coloring's outputs as
return values, not as a session takeover.
```

Place this callout once, near the top of the child's markdown (right after the Usage section). Remove the callout when the old framing is no longer cited anywhere.

---

## Progress-State Vestigial Keys

If the child writes progress state to disk (`/progress/coloring.json` etc.), and the schema evolves between command versions, downstream projects may have older state files on disk. Document the vestigial keys explicitly:

```
**Progress State Compatibility**

Reads progress JSON with the following backward-compat handling:

  - `legacy_session_id` (string): present in pre-2026-04 sessions.
    Ignored — replaced by `(selfie_path, capture_date)` keying.
  - `delegate_started_at` (timestamp): present in delegate-and-stop
    sessions. Ignored — no parent handoff.

Newer keys take precedence. Vestigial keys are not removed during
re-runs — they're left in place so older tooling can still parse the
file.
```

The child's read logic explicitly tolerates the vestigial keys; it does NOT error on their presence. Newer keys override.

---

## Worked Example Outline

A typical inline-capable command markdown has these sections, in order:

```
# /coloring

[One-line description]

## Usage

[Standalone usage shape: /coloring [selfie_path] [date]]

## ⚠️ Retirement Notice: Delegate-and-Stop Framing  (optional)

[Only if a prior framing existed]

## Inline Invocation from /onboard

[Four-column contract table]
[Idempotency Contract block]
[Progress State Compatibility block, if state files are involved]

## Process

[Step 1 — runs in both modes]
[Step 2 — Standalone-only flagged]
[Step 3 — runs in both modes]
[...]

## Examples

[Show standalone invocation + parent-invocation flow]
```

---

## Multi-Sibling Coordination

When a parent has multiple inline-capable children (e.g., `/onboard` runs `/coloring`, `/grooming`, `/wardrobe` in sequence), align the four-column contract shape, the Idempotency Contract structure, and the Standalone-only flag convention across all siblings. Drift between siblings is a foot-gun: a parent's retry logic that works for two siblings may break on the third if the dedup tuple shape differs.

Audit cue: when adding a new inline sibling, diff its `## Inline Invocation from /{parent}` section against an existing sibling. The structure should be near-identical; only the table rows and dedup-tuple specifics should vary.

---

## References

- The pattern emerged from styler's `/coloring`, `/grooming`, `/wardrobe` inline commands (2026-04-27). Capture in this doc replaces correctness-by-precedent — future inline commands inherit the pattern by reference, not by copy.
- For parent-command structure when composing inline children, see the parent's `Process` section conventions (project-specific; not template-owned).
