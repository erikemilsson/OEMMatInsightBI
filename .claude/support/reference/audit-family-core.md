# Audit Family Core

Shared contract for the audit-family commands (`/audit-coherence`, `/audit-ui`, and project-local `audit-{name}` clones). Extracted in v4.17.0 from the two command files, where the promote/fix/triage algorithms and the synthesizer classification rules were duplicated and had begun to drift (the bundle-eligibility criteria already differed by one clause). This file is the single source; the command files delegate here with per-audit substitutions.

**How to consume:**

- **Orchestrator modes** (Promote / Fix / Triage): execute the algorithms below directly, applying the invoking command's substitution row.
- **Synthesizer dispatch:** the orchestrator SPLICES § "Synthesizer shared contract" verbatim into the synthesizer prompt at the `{SPLICE HERE}` marker before dispatching — sub-agents receive inline text, never a read-this-file instruction (execution reliability over indirection; same pattern as lens prompts being passed verbatim).

## Substitution table

| Placeholder | `/audit-coherence` | `/audit-ui` |
|---|---|---|
| `{AUDIT}` | `coherence` | `ui` |
| `{P}` (finding-ID prefix) | `C` | `F` |
| `{DIR-GLOB}` | `.claude/support/audits/coherence-*/` | `.claude/support/audits/ui-*/` |
| `{CMD}` | `/audit-coherence` | `/audit-ui` |

Empty-state and summary messages substitute accordingly (e.g., `No pending findings in latest {AUDIT} audit.`). A project-local audit clone adds its own row.

---

## Promote mode (canonical)

`{CMD} promote {audit-ts} [--all | {P}-IDs]`

1. Read `{audit-dir}/findings.md`. Find the `## Promote to feedback` section.
2. Determine selection: `--all` → every `{P}-NN` in the report; explicit IDs → only those; default → only ticked checkboxes (`- [x] {P}-NN — ...`).
3. For each selected finding, read its full body from `findings.md`.
4. Read `.claude/support/feedback/feedback.md` and `.claude/support/feedback/archive.md`. Compute next `FB-NNN`.
5. **Dedupe pass.** For each selection, scan both feedback files for entries whose `**Source:**` line references the same audit (or any prior audit) AND whose title fuzzy-matches (≥0.8 token overlap) OR whose `**Where:**` / source anchor references the same surface. For each match, prompt the user: `[S] Skip` (already captured as FB-NNN) · `[U] Supersede` (close existing, create new with `**Supersedes:** FB-NNN`) · `[M] Merge` (append this finding's evidence to the existing entry) · `[N] New anyway`.
6. For each non-deduped selection, append to `feedback.md`:
   ```markdown
   ## FB-NNN: {finding title}

   **Status:** new
   **Captured:** {today YYYY-MM-DD}
   **Source:** audit-{AUDIT}-{audit-ts} {P}-{ID}
   **Kind:** {kind}
   **Lenses:** {comma-separated lens names}
   **Severity:** {high | med | low}
   {UI audits also carry: **Effort:** {S|M|L} · **Impact:** {S|M|L}}

   **Where:** {from finding}

   **Evidence:** {from finding}

   **Why it matters:** {from finding}

   **Fix candidate:** {from finding}
   ```
7. Update `digest.json` in place: `items[i].status = "promoted"`, `items[i].resolved_by = {kind: "promote_fb", ref: "FB-NNN", at: now}`.
8. For any friction register entries cited by promoted findings: update `friction.jsonl` in place — `status: resolved`, `resolved_by: {kind: "promote_fb", ref: "FB-NNN", at: now}` per `friction-register.md § "Status update protocol"`.
9. Update `findings.md` in place: replace `- [x] {P}-NN — title` with `- [x] {P}-NN → FB-NNN promoted {date}`.
10. Print summary: `Promoted {N} findings → FB-{first}…FB-{last} · Skipped {M} (deduped) · Run /feedback review to triage.`

The existing `/feedback review` → `/iterate` flow is unchanged — the audit just produces feedback-shaped artifacts.

---

## Fix mode (canonical — bundle-eligible only, DEC-013 Option C)

`{CMD} fix {audit-ts} {P}-{ID}` (and `{CMD} fix latest {P}-{ID}` — `latest` resolves to the newest `{DIR-GLOB}` dir by `ran_at`).

Available only for findings with `kind: bundle-eligible`. Other kinds (`fix-eligible`, `decision`, `design`) require manual review or `/iterate` routing — kind-availability table in `audit-fix-workflow.md § "Per-kind action availability"`.

**Mechanism — canonical reference:** `audit-fix-workflow.md § "Action protocol — Stage 6 (Option C per DEC-013)"` / `"[Fix it] — inline apply (bundle-eligible only)"`. In short:

1. Read finding from the audit's `digest.json` + `findings.md#{P}-{ID}`
2. Verify kind is `bundle-eligible` (refuse with kind-specific message otherwise)
3. Verify finding `status == "pending"` (not already resolved/dismissed/promoted)
4. Re-read cited `source_anchors[]` / `files_to_touch[]` to verify the finding's claim still holds (refuse if stale)
5. Re-verify hard-exclusion (no spec/decision/vision in `files_to_touch[]` — defense-in-depth against mis-classification)
6. Show concrete change + ask single approval
7. On approval: apply, single commit `audit-fix: {P}-{ID} — {summary}`, update `digest.json` + `friction.jsonl`

**After any [Fix it] that removes a dependency or deletes source files:** run the test suite — transitive consumers via dynamic require / `importlib.import_module` / string-keyed imports aren't statically detectable (DEC-013 Q3; pairs with `transitive_consumer_risk` below).

---

## Triage mode (canonical)

`{CMD} triage [audit-ts]` — interactive walker through the audit's pending findings. The preferred entry point when an audit has multiple pending findings; closes the dashboard-tick → CLI re-specification courier pattern and the audit-name memory burden (FB-006 sub-issues 1+2).

**Default for `audit-ts`:** `latest` — newest `{DIR-GLOB}` dir by `ran_at` (same resolution as Fix mode). The explicit `latest` keyword is equivalent to the no-arg form.

### Algorithm

1. **Resolve audit dir.** No arg or `latest` → newest `{DIR-GLOB}` dir by `ran_at`. Explicit `{audit-ts}` → the named dir.
2. **Empty-state checks** (exit cleanly, no state mutation):
   - Audit dir does not exist → `No {AUDIT} audit has run in this project yet. Run {CMD} first.`
   - No findings with `status: pending` → `No pending findings in latest {AUDIT} audit. Nothing to triage.\n(Last audit ran {ran_at date}. Run {CMD} to refresh.)`
3. **Read pending findings.** From `digest.json items[]`, filter `status == "pending"` AND `id NOT IN` sidecar `audit_digest.dismissed_ids[]` (sidecar missing → treat as `[]`). Preserve digest order.
4. **Print walk header.** `Reading latest {AUDIT} audit: {AUDIT}-{ts} ({N} pending of {M} total)`.
5. **Per-finding loop:**
   - **Print finding card** — `[{i+1}/{N}] {P}-{ID} ({kind})`, then `item.description ?? item.title` (title fallback for pre-v3.18.0 digests), then `Files to touch:` and `Source anchors:` lines, then the kind-conditional `Actions:` prompt (table below).
   - **Read user action.** Single-letter shorthand (case-insensitive) OR natural language with a verb (`fix it`, `promote`, `dismiss because X`, `skip`, `quit`). Map to `F`/`P`/`D`/`S`/`Q`.
   - **Kind-action validation.** If the action isn't available for the kind (e.g., `F` on `decision`), print the kind-specific refuse message from `audit-fix-workflow.md` step 3 and re-prompt the same finding.
   - **Dispatch** to the canonical per-action mechanics (no divergence): `F` → Fix mode steps 4-7 above (at-apply re-read + hard-exclusion + show + approve + commit + state update) · `P` → Promote mode steps 3-9 above (single-finding subset of bulk promote) · `D` → if bare `D`, follow up `Reason (optional, blank to skip): `; if `dismiss because X`, parse `X` inline; then `audit-fix-workflow.md § "[Dismiss]"` steps 1-4 · `S` → no mutation; advance · `Q` → break to step 6.
   - **Auto-advance** after dispatch — one-line result, then the next card. No `Continue? [Y/N]` between findings (`[Q]uit` is available at every prompt).
6. **End-of-walk summary.** `Triaged {X} of {N} findings. {Z} still pending. Run {CMD} triage again later to revisit.` (`Z` = skipped + remainder-after-quit.)

### Per-kind action gates

Mirrors `audit-fix-workflow.md § "Per-kind action availability"`:

| Finding kind | Actions prompt |
|--------------|----------------|
| `bundle-eligible` | `[F]ix it · [P]romote to FB · [D]ismiss · [S]kip · [Q]uit` |
| `fix-eligible` | `[P]romote to FB · [D]ismiss · [S]kip · [Q]uit` (no `[F]ix it` — deferred per DEC-013) |
| `decision` | `[P]romote to FB · [D]ismiss · [S]kip · [Q]uit` (no `[F]ix it` — routes via `/iterate`) |
| `design` | `[P]romote to FB · [D]ismiss · [S]kip · [Q]uit` (no `[F]ix it` — promote → `/research`) |

The kind annotation prints in the card header so the action list's reason is transparent.

### State mutations — atomic per action

- **Fix it** → single commit `audit-fix: {P}-{ID} — {summary}`; `digest.json items[i].status: "resolved"`; `friction.jsonl` cascades.
- **Promote** → next `FB-NNN` computed, dedupe pass, append to `feedback.md`; `digest.json items[i].status: "promoted"`; `friction.jsonl` + `findings.md` cascades.
- **Dismiss** → append id to sidecar `audit_digest.dismissed_ids[]`; `digest.json items[i].status: "dismissed"` + `dismiss_reason` + `dismissed_at`.
- **Skip** → no mutation.

`Ctrl+C` mid-walk is safe — completed actions stay committed, remaining stay pending; the next `{CMD} triage` resumes from whatever is still `pending`.

### Edge cases

- **Pre-v3.18.0 digests without `description`** → render `item.title` (same `{description ?? title}` fallback as `dashboard-regeneration.md § "Body field selection"`).
- **Parallel-session collision** — same caveat as `[Fix it]` (`audit-fix-workflow.md § "Known limitations"`): don't run triage while another session runs `/work` on overlapping files.
- **Mixed audit kinds** — each audit family member has its own `triage` sub-command; no unified `/triage`.
- **Re-running the audit mid-triage** — a fresh audit replaces sidecar items at next dashboard regen; the next triage walks the new digest. Acceptable — triage operates on a named digest, not the dashboard.

---

## Synthesizer shared contract

**Spliced verbatim into each audit's synthesizer prompt at its `{SPLICE HERE}` marker by the orchestrator at dispatch time.** Keep this section self-contained — it is read by a sub-agent with no other access to this file.

### Write `description` (per clustered item)

A plain-English one-line summary suitable for at-a-glance dashboard triage. Derive from the canonical finding's `What` line; expand with `Why` context only if the bare `What` would be opaque without it. Constraints: complete sentence, period-terminated, ~80-140 chars (hard cap 200 to prevent wrap disasters), self-contained (names the artifact / file / section / page affected so the user doesn't need to open `findings.md`). Distinct from `title` — `title` is a short cluster identifier (findings.md cluster header + FB title on promote); `description` is the readable sentence rendered on the dashboard digest.

### Classify `kind` per cluster

(DEC-013 Option C is an action layer — `bundle-eligible` classification triggers actual inline-apply at Fix-it time, so be conservative.)

- **HARD RULE FIRST.** If `files_to_touch` includes ANY of `.claude/spec_v*.md`, `.claude/support/decisions/decision-*.md`, `.claude/vision/**/*.md` → `kind: decision` (always; no exceptions — Component 6 hard exclusion). Set `iterate_routing.reason: "spec/decision/vision file modification — read-only outside /iterate"`.
- If `suggested_kind` is `design` from any contributing lens → `kind: design`. No [Fix it]; promote to FB only.
- **Bundle-eligible** — only when ALL hold:
  a. Implementation-file-only (no spec/decision/vision per HARD RULE)
  b. Source-confirmed: the fix is a sync from one authoritative source (cited concretely in `source_anchors[]`) to a derived/dependent location. NOT bundle-eligible if the only "source" is the lens's inference.
  c. Reversible: text edit, dep removal, dead-link removal, deletion of clearly-orphaned files
  d. No new judgment: the fix's content is already present somewhere authoritative (the audit syncs, it doesn't decide)
  e. Bounded scope: ≤3 files
  f. **Orphan-removal special case (DEC-013 Q3):** orphan-dependency removal and orphan-source-file deletion still classify bundle-eligible (the canonical case) but set `bundle_eligibility.transitive_consumer_risk: true` so the action layer warns the user to run tests after apply — dynamic require / `importlib.import_module` / string-keyed import patterns aren't statically detectable.
  g. **When in doubt → fix-eligible, not bundle-eligible.** The action layer's at-apply re-read invariant cannot catch semantic mismatches created at synthesis time. Conservative classification here is the load-bearing safety property.
  Set on bundle-eligible items: `bundle_eligibility.source_confirmed: true`, `reversible: true`, `files_count: {N}`, `touches_spec_or_decisions: false`, `transitive_consumer_risk: {bool}`.
- Otherwise (implementation-only but failing ANY bundle criterion, >3 files, or ambiguous fix) → `kind: fix-eligible`. Renders on the dashboard with the italicized `*(fix-eligible — manual review pending future DEC)*` annotation only — no inline `[Fix it]` until a future DEC expands inline-apply per DEC-013's telemetry gate.

### Hard-rule sanity check (before returning)

- No `items[]` entry has `kind: bundle-eligible` AND `files_to_touch` containing any spec/decision/vision path. Finding one means you mis-classified — re-apply the HARD RULE.
- Every cluster appears in either `items[]` or `annotations[]`. Nothing dropped silently.

---

## digest.json schema (shipped canonical)

This section is the canonical schema home for projects (the original design doc lives in the template repo's `template-maintenance/audit-command-family-proposal.md § "2. Audit command interface"`, which does not ship).

```json
{
  "audit": "{AUDIT}",
  "ran_at": "{ISO timestamp from meta.json}",
  "viewport": "desktop|mobile",
  "findings_count": {
    "raw": 23,
    "clustered": 8,
    "bundle_eligible": 3,
    "fix_eligible": 2,
    "promote_eligible": 5,
    "deduped_to_pending_work": 2
  },
  "items": [
    {
      "id": "{P}-04",
      "title": "Orphan dep react-native-pager-view in package.json (per T647)",
      "description": "react-native-pager-view is listed in package.json but no import or require reference exists anywhere in src/ — task T647 retired the only consumer.",
      "kind": "bundle-eligible",
      "fix_one_liner": "Remove react-native-pager-view from package.json dependencies",
      "source_anchors": ["task-647.json#verification_history", "package.json"],
      "files_to_touch": ["package.json"],
      "evidence_path": ".claude/support/audits/{AUDIT}-{ts}/findings.md#{P}-04",
      "bundle_eligibility": {
        "source_confirmed": true,
        "reversible": true,
        "files_count": 1,
        "touches_spec_or_decisions": false,
        "transitive_consumer_risk": true,
        "kind_classification": "orphan_dep_removal"
      },
      "status": "pending"
    },
    {
      "id": "{P}-01",
      "title": "Spec § 5.2 still describes per-user generation; DEC-050 selected maintainer-curated",
      "description": "Spec §§ 5.2, 5.3, 5.5 still describe per-user generation, but DEC-050 selected maintainer-curated — 3 unfixed references in the active spec.",
      "kind": "decision",
      "fix_one_liner": "Spec amendment via /iterate (3 occurrences in § 5.2)",
      "source_anchors": ["spec_v13.md § 5.2.1", "decision-050-*.md"],
      "files_to_touch": [".claude/spec_v13.md"],
      "evidence_path": ".claude/support/audits/{AUDIT}-{ts}/findings.md#{P}-01",
      "iterate_routing": { "reason": "spec file modification — read-only outside /iterate" },
      "status": "pending"
    }
  ],
  "annotations": [
    {
      "type": "covered_by_pending_task",
      "what": "{finding title}",
      "covered_by": "{task_id}",
      "covered_by_status": "{task status}",
      "source_anchors": ["..."],
      "suppressed_finding_id": "{P}-09"
    }
  ]
}
```

Notes:
- `viewport` — `/audit-ui` only; omit for audits without a viewport concept.
- `status` per item: `pending` | `resolved` | `dismissed` | `promoted` | `escalated_to_iterate` | `escalated_to_work`. Updated atomically by Fix it / Promote / Dismiss.
- UI audit items additionally carry `effort` (`S|M|L`) and `impact` (`S|M|L`); annotation objects may carry `page` instead of `source_anchors` where the surface is a route.
- `description` vs `title` (v3.18.0, FB-006): `title` = terse cluster identifier; `description` = self-contained dashboard sentence. Older digests without `description` render `title` (back-compat).

## See Also

- `audit-fix-workflow.md` — the full [Fix it]/[Dismiss] action protocol the modes above dispatch into
- `dashboard-regeneration.md § "Audit Findings sub-section"` — how digest items render on the dashboard
- `friction-register.md § "Status update protocol"` — the cascade Promote/Fix apply to cited FR entries
