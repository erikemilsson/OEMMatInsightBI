---
applies_when:
  any_file_exists: [".claude/spec_v*.md"]
estimated_runtime: "2-3 min"
prerequisites: []
---

# Coherence Audit Command

Detects spec-vs-reality drift in a project — superseded decisions still referenced in the active spec, vocabulary inconsistencies, path divergences, retired features missing spec markers, decayed feedback items, and clustered friction-register entries. Surfaces findings as a small bundled digest the user can chew through async to active `/work` (per the audit family proposal).

This command is the first audit shipped by the audit family (proposal: `template-maintenance/audit-command-family-proposal.md`). Stage 3 produces the digest and a full clustered report. Stages 6 (dashboard digest + [Fix it] mechanism) and 7 (bundled-apply UX) extend the action surfaces.

**Hard rule (Component 6 of proposal):** the spec, decision records, and vision documents are read-only outside `/iterate`. Any finding whose `files_to_touch` includes a spec/decision/vision file path is auto-classified `kind: decision` — Stage 3 surfaces it for promotion to `/iterate`; Stages 6/7 will route [Fix it] to `/iterate` for these without ever editing the file inline.

**Background-session note:** this command reads gitignored project state (spec, decisions, feedback, friction register, tasks, retired manifests) and writes only to a gitignored audit dir under `.claude/support/audits/{cmd}-{ts}/`. **Do not enter a worktree before running it** — the worktree's HEAD will not contain the gitignored inputs, and the command's reads will fail. Run in the main working tree (`cwd` outside `.claude/worktrees/`). The audit dir's timestamp prevents same-second collisions across parallel sessions, so worktree isolation is unnecessary.

---

## Usage

```
/audit-coherence                            # full audit, all 7 lenses
/audit-coherence --lens {name}              # run only the listed lens (comma-separated for multiple)
/audit-coherence --since {YYYY-MM-DD}       # restrict to friction register entries / FB items captured after date
/audit-coherence triage [audit-ts]          # interactive walker: per-finding fix/promote/dismiss (default audit-ts: latest)
/audit-coherence promote {audit-ts}         # promote ticked findings → feedback.md (same shape as /audit-ui promote)
/audit-coherence promote {audit-ts} --all   # bulk promote everything in the report
/audit-coherence promote {audit-ts} C-01,C-07
/audit-coherence fix {audit-ts} {C-ID}      # apply a single bundle-eligible finding inline
```

Stage 5 (`/health-check` Part 6) will dispatch this command automatically based on `applies_when`. Until then, invoke directly.

---

## Lenses

Seven lenses, each running as a fresh-context sub-agent in parallel:

| Lens | Catches | Detection mode |
|------|---------|---------------|
| `superseded-decisions` | Decisions marked `superseded` / `partially_superseded` whose old language still appears in the active spec | Auto-grep + spec re-read |
| `vocab-drift` | Same concept named with different terms across spec sections, or between spec and on-disk implementation references | Cross-section term frequency + register read |
| `path-drift` | File paths the spec mentions that don't exist on disk; or implementation uses a different canonical path than spec | Glob + spec scan |
| `feedback-decay` | `FB-*` entries open >30 days with no status change | Parse feedback.md status fields |
| `retired-features` | Manifests in `.claude/support/retired/` without a corresponding retirement marker in spec | Filesystem + spec scan |
| `friction-register` | Cluster open `friction.jsonl` entries by `kind` and `source_anchor`, surface high-frequency themes | Read register + thematic grouping |
| `acceptance-reconciliation` | Spec inline `- [ ]` acceptance boxes unticked despite a verified phase PASS, across **all completed phases** — DEC-022 | Spec box scan + verification-result (latest, authoritative) + per-phase task-verification rollup (history, proxy); advisory |

Bias preservation: each lens runs with no knowledge of other lenses' output, mirroring `audit-ui`'s context-separation pattern.

---

## File layout

```
.claude/support/audits/coherence-{YYYY-MM-DD-HHmm}/
├── inputs/
│   ├── decisions.json           # extracted frontmatter from all decision-*.md files
│   ├── spec-sections.json       # spec heading map + per-section fingerprints
│   ├── friction-open.jsonl      # open entries from friction.jsonl
│   ├── feedback-status.json     # parsed FB-* entries with status + age
│   ├── retired-manifests.json   # contents of all .claude/support/retired/*/manifest.json
│   ├── verification-result.json # copy of .claude/verification-result.json (LATEST phase criteria[]) if present
│   ├── phase-verification.json  # per-phase task-verification rollup (historical proxy — DEC-022 v4.27.0)
│   └── meta.json                # audit run config: timestamp, lenses requested, --since filter
├── lenses/
│   ├── superseded-decisions.md
│   ├── vocab-drift.md
│   ├── path-drift.md
│   ├── feedback-decay.md
│   ├── retired-features.md
│   ├── friction-register.md
│   └── acceptance-reconciliation.md
├── findings.md                  # full clustered report (Claude-readable)
├── digest.json                  # 4-8 user-facing items with kind classification + eligibility flags
└── synth-input.md               # concatenated lens output passed to synthesizer (audit trail)
```

Project rule (DEC-004): sub-agents cannot write to `.claude/`. The orchestrator (this command, running in the main conversation) handles all writes. Sub-agents return their report as text; the orchestrator saves it.

---

## Workflow

### Phase 1 — Capture (orchestrator drives directly)

1. Compute audit dir: `.claude/support/audits/coherence-{YYYY-MM-DD-HHmm}/`. Create with subdirs `inputs/` and `lenses/`.
2. Write `meta.json` with run config: timestamp, lenses requested (default: all 7), `--since` filter if set.
3. **Capture decisions.** Glob `.claude/support/decisions/decision-*.md`. For each file, parse YAML frontmatter and extract: `id`, `title`, `status`, `superseded_by` (if present), `superseded_date` (if present), `related.tasks` (if present). Write the array to `inputs/decisions.json`.
4. **Capture spec.** Read the active `.claude/spec_v*.md` (exactly one per single-spec invariant). Build a section map: for each `## ` heading, record `{heading_text, section_id (e.g. "5.2"), line_start, line_end, fingerprint: sha256(section_body)}`. Write to `inputs/spec-sections.json`.
5. **Capture friction register.** If `.claude/support/friction.jsonl` exists, read all lines, filter `status == "open"` (and `captured >= --since` if set), write to `inputs/friction-open.jsonl`. If file doesn't exist, write empty file.
6. **Capture feedback statuses.** If `.claude/support/feedback/feedback.md` exists, parse for `## FB-NNN` headers and `**Status:**` + `**Captured:**` lines beneath. For each FB entry, compute age in days from captured date. Write `[{id, status, captured, age_days, title}]` to `inputs/feedback-status.json`.
7. **Capture retired-feature manifests.** Glob `.claude/support/retired/*/manifest.json`. Read each. Write the combined array to `inputs/retired-manifests.json`.
8. **(Optional) Sample task notes for friction-marker prose.** This is a fallback for projects that haven't accumulated friction register entries yet — sample up to 20 most-recently-modified `.claude/tasks/task-*.json`, extract any `notes` containing keywords `"friction"`, `"captured for /iterate"`, `"spec drift"`. Append to `friction-open.jsonl` as synthetic register entries with `id: "FR-SYNTHETIC-{N}"`, `kind: "spec_implementation_gap"`, `captured_in: {agent: "task_notes_sample"}`.
9. **Capture verification state (for the `acceptance-reconciliation` lens).** Two artifacts:
   - **Latest phase-level result:** if `.claude/verification-result.json` exists, copy it to `inputs/verification-result.json` (the authoritative latest-phase `criteria[]` PASS/FAIL). If absent, write `{}`.
   - **Per-phase task-verification rollup (historical proxy):** glob `.claude/tasks/task-*.json`, group by `phase`, and for each phase write `{phase, phase_name, task_count, finished, verified_pass, phase_complete, task_ids}` to `inputs/phase-verification.json` — where `phase_complete` = every non-`Absorbed`, non-`On Hold` task in the phase has `status == "Finished"` AND `task_verification.result == "pass"` (the phase gate's own completion condition). This lets the lens reconcile *every completed phase*, not just the latest. If no task files exist, write `[]`.

Capture should complete within 30s. If any input source is missing or fails to parse, log a warning to `meta.json` and continue with empty data — lenses handle empty inputs gracefully (return 0 findings).

### Phase 2 — Lenses (7 parallel sub-agents)

Spawn N sub-agents in a **single Task tool message** so they run concurrently. Each:
- Runs as `general-purpose` agent (per `.claude/rules/agents.md` § "Dispatch Convention" — persona-via-prompt-content)
- Receives the audit dir path + ONLY its single lens prompt
- Never sees other lenses' output
- Returns markdown formatted per the **Lens output format** below

Orchestrator:
1. Collect each agent's returned text.
2. Write to `lenses/{lens-name}.md`.
3. Concatenate all into `synth-input.md` for Phase 3.

If `--lens` is set, run only those lenses; if unset, run all 7.

### Phase 3 — Synthesize

Spawn one general-purpose agent with:
- Path to `lenses/`, `inputs/`, and the full `inputs/decisions.json` + `inputs/spec-sections.json`
- The **Synthesizer prompt** below, with the shared contract spliced in: read `.claude/support/reference/audit-family-core.md` §§ "Synthesizer shared contract" + "digest.json schema (shipped canonical)" and insert their verbatim text at the prompt's `{SPLICE HERE}` marker before dispatching (sub-agents get inline text, never a read-this-file instruction)
- Instruction to return both `findings.md` (full clustered report) and `digest.json` (machine-readable digest)

Orchestrator writes both files to the audit dir and prints a summary to chat:

```
Coherence audit complete — {N} routes scanned · {raw} raw findings → {clustered} clustered

Top findings:
  C-01  {title} (kind: {kind})
  C-02  {title} (kind: {kind})
  ...

Bundle-eligible: {N} (implementation-only, source-confirmed)
Promote-eligible: {M} (require /iterate or judgment)
Deduped to pending tasks: {K} (already covered by in-flight work)

Report: .claude/support/audits/coherence-{ts}/findings.md
Digest: .claude/support/audits/coherence-{ts}/digest.json

Promote findings to feedback: /audit-coherence promote {ts}
```

(Stage 6 has shipped — `bundle-eligible` items render on the dashboard's `🔍 Audit Findings` section with the inline `[Fix it]` token; other kinds render with an italicized kind annotation. Promote/Dismiss actions are available via tick + `/audit-coherence promote {audit-ts}` and natural-language-to-Claude respectively — not rendered per-item; see `dashboard-regeneration.md` § "Audit Findings sub-section". The inline summary + manual review of `findings.md` remains a complementary surface for context beyond what the dashboard digest shows.)

---

## Lens output format (all lenses use this)

```markdown
# Lens: {lens-name}

Findings: {N}

## F-{lens-prefix}-01
- **Title:** {short title, ≤8 words}
- **Severity:** high | med | low
- **Source anchor:** {file + section, e.g., "spec_v13.md § 5.2.1"; or decision id, e.g., "DEC-050"; or on-disk path}
- **Files affected (read-only):** {list of files where the issue is observable — for evidence, not necessarily for fix}
- **Files to touch (potential fix):** {list of files a fix would modify; CRITICAL for kind classification — see synthesizer rules}
- **Evidence:** {2-4 lines — quote actual text or describe actual structure. No paraphrase.}
- **What:** {one sentence stating the issue}
- **Why:** {one sentence stating why it matters}
- **Suggested fix:** {one sentence — what would resolve it}
- **Suggested kind:** bundle-eligible | fix-eligible | decision | design (synthesizer re-classifies; this is your first guess)

## F-{lens-prefix}-02
...
```

`lens-prefix` = first three letters of the lens name (`sup`, `voc`, `pat`, `fee`, `ret`, `fri`, `acc`).

If the lens has no findings:
```markdown
# Lens: {lens-name}

Findings: 0

(No findings on this axis.)
```

---

## Lens prompts

Each prompt below is passed to a `general-purpose` agent. Replace `{AUDIT_DIR}` with the absolute path. The orchestrator passes the prompt verbatim plus the dir.

### Lens 1 — `superseded-decisions`

```
You are auditing a project for the SUPERSEDED-DECISIONS lens only.

Read {AUDIT_DIR}/inputs/decisions.json (extracted frontmatter from all decision-*.md files in the project) and {AUDIT_DIR}/inputs/spec-sections.json (the active spec's section map with fingerprints).

For each decision with status `superseded` or `partially_superseded`:

1. Open the decision's full file at `.claude/support/decisions/decision-{NNN}-*.md`.
2. Read the Selected option / Decision section to understand what the SUPERSEDED decision originally chose.
3. Extract 2-3 distinctive phrases or terms from the OLD selected option (not the supersession note).
4. Grep the active spec for those phrases. If the spec text still describes the OLD decision's behavior — without a clear "[Superseded by DEC-XXX]" marker pointing forward — that's a finding.

What counts:
1. Spec section still describes the superseded decision's chosen behavior verbatim, without supersession marker.
2. Spec section references the superseded decision by ID (e.g., "per DEC-010") in a context that implies the decision is still authoritative.
3. Implementation anchor in the SUPERSEDED decision's frontmatter still exists in the codebase (the file is doing what the superseded decision specified — implementation hasn't caught up to the supersession).

What does NOT count:
- Decision is correctly marked superseded AND spec was updated to reflect the new direction → no finding (working as intended).
- Spec mentions the OLD decision in a clearly historical / dated context (e.g., "Originally per DEC-010 (2026-04-10); see DEC-050 for current treatment") → no finding.
- Decision has status `superseded` but the spec was already updated and the old prose is gone → no finding.

For each finding, set:
- **Source anchor:** the spec section that needs updating (or the decision file if the spec is OK and the decision needs an implementation-anchor cleanup)
- **Files to touch (potential fix):** spec_v*.md (likely) — note this means the synthesizer will classify as `kind: decision` (read-only outside /iterate)
- **Suggested fix:** "Spec amendment via /iterate to align § X.Y with DEC-{NEWER}'s selected option, OR add explicit supersession marker pointing forward"

Be evidence-first. Quote the spec text and the decision text. Use the lens output format the orchestrator provided.
```

### Lens 2 — `vocab-drift`

```
You are auditing a project for the VOCAB-DRIFT lens only.

Read {AUDIT_DIR}/inputs/spec-sections.json and {AUDIT_DIR}/inputs/friction-open.jsonl (open friction register entries with kind=vocab_drift or terminology_mismatch). Also read `./CONTEXT.md` at the project root if it exists — it is the canonical domain glossary populated by `/grill` (project-owned, lazy-created; absent for projects that haven't run `/grill`).

What counts:
1. Same concept named with different terms across spec sections — e.g., "sub-tab" in § 9.1 but "section nav" in § 42.5; "personalized principles" in § 5.2 but "maintainer-curated principles" in § 5.5.
2. Spec uses term X but the friction register has open entries reporting that implementation uses term Y for the same concept (cross-reference register entries against spec).
3. Plural / spelling drift on the same noun across spec sections ("outerwears" vs "outerwear", "Bottoms" vs "Trouser") if the same noun appears in multiple sections.
4. **CONTEXT.md violation (only when present)**: spec text uses an alias listed in CONTEXT.md's `_Avoid:` field (the term should be the canonical), OR spec text introduces a load-bearing domain noun absent from CONTEXT.md's Language section (signal: appears 3+ times across 2+ sections — load-bearing enough to belong in the glossary; surface as "missing glossary entry; consider `/grill` to add it"). When CONTEXT.md exists, it is the canonical naming reference — overrides per-section voting heuristics for items #1 and #3.

Your method:
1. Open the active spec file. Scan for noun phrases that appear in multiple sections.
2. **If `./CONTEXT.md` exists:** load its glossary terms + `_Avoid:` aliases. For each candidate noun phrase, check: (a) is it the canonical term? (b) is it an `_Avoid:` alias? (c) is it absent from CONTEXT.md but load-bearing? Flag (b) as "alias used in place of canonical: should be {canonical}" and (c) as "missing glossary entry: load-bearing term {term} not in CONTEXT.md".
3. **If `./CONTEXT.md` is absent:** for each candidate noun phrase, search for synonyms or close variants in the spec. If found in different sections without cross-reference, flag.
4. Read open friction register entries with `kind: vocab_drift` or `kind: terminology_mismatch`. For each, surface the friction's evidence as a finding (it was already flagged by an agent during /work).

What does NOT count:
- Same word used in genuinely different contexts (e.g., "session" in spec § 3 means HTTP session; in § 12 means user session — distinct concepts that happen to share a word).
- Vocabulary differences that are clearly intentional (e.g., spec uses "user-facing copy" but admin-facing surface uses "internal label" — different audiences).
- Vocabulary differences flagged by friction register that were already resolved (status != open — those are filtered out before you see the file).

For each finding, set:
- **Source anchor:** the spec section that should be the canonical naming (or all sections if it's a "decide which is canonical" issue)
- **Files to touch (potential fix):** spec_v*.md — synthesizer will classify as `kind: decision`
- **Suggested fix:** "Spec amendment via /iterate to standardize on '{term-A}' (per § {N.M}) across § {others}"

If the friction register source ALREADY has a clear canonical (e.g., implementation has settled on one term and the friction register entry says "spec § X says Y but reality is Z"), name the canonical in your suggested fix.

Cluster aggressively: if 5 sections drift on the same vocab pair, that's ONE finding listing all 5 sections, not 5 findings.
```

### Lens 3 — `path-drift`

```
You are auditing a project for the PATH-DRIFT lens only.

Read {AUDIT_DIR}/inputs/spec-sections.json and use Bash/Glob to inspect the actual on-disk filesystem.

What counts:
1. Spec mentions a file path or directory that doesn't exist on disk (likely renamed or removed without spec update).
2. Spec references a path that exists but the canonical path used by implementation is different (e.g., spec says `foundation/coloring/` but on-disk is `foundation/user/coloring/`).
3. Spec references a path with stale Phase-N migration anchors (e.g., spec written before Phase 28 migration consolidated paths).

Your method:
1. Open the active spec file. Grep for path-shaped strings: anything matching `[a-z][a-z0-9-_/]+\.(json|md|tsx?|jsx?|py|sh)` or `\bsrc/`, `\bfoundation/`, `\b\.claude/`, etc.
2. For each unique path mentioned in the spec, check if it exists on disk via Glob.
3. If it doesn't exist, search for nearby paths (same basename, different parent dir) — if found, that's a path-drift finding (the spec is stale).
4. If it exists, check if there are siblings with the same basename in a different directory tree (suggests implementation moved but spec didn't).
5. Cross-reference open friction register entries with `kind: path_drift`.

What does NOT count:
- Paths in code blocks intended as illustrative examples (e.g., `path/to/your/file.ts` placeholders).
- Generic patterns (e.g., `**/*.test.ts`, `src/components/`) without specific filenames — too vague to verify.
- Paths to template files that legitimately don't exist in this specific project (e.g., `.claude/support/reference/audit-fix-workflow.md` if the project hasn't installed the audit family).

For each finding, set:
- **Source anchor:** the spec section containing the stale path
- **Files to touch (potential fix):** spec_v*.md — synthesizer will classify as `kind: decision`
- **Suggested fix:** "Spec amendment via /iterate: replace path '{old}' with '{new}' in § {N.M} (and N other sections if applicable)"

Cluster paths that share the same root migration: if Phase 28 moved `foundation/X/` → `foundation/user/X/` and 5 sections still reference the old root, that's ONE finding with 5 sub-instances.
```

### Lens 4 — `feedback-decay`

```
You are auditing a project for the FEEDBACK-DECAY lens only.

Read {AUDIT_DIR}/inputs/feedback-status.json (parsed FB-* entries with status + age_days).

What counts:
1. FB entries with status `new`, `refined`, or `ready` whose `age_days >= 30` and no status change is visible in the entry body.
2. FB entries with status `deferred` whose deferral condition has lapsed (e.g., "deferred until Phase 27 retirement workflow ships" but Phase 27 is now complete).
3. FB entries that lack any status field entirely (drafted but not classified).

Your method:
1. Filter the feedback-status.json array for entries meeting criteria 1 (age + status). Group by status: how many `new` >30d, how many `refined` >30d, etc.
2. For criteria 2 (lapsed deferrals): for each `deferred` entry, look for the deferral reason in the entry body (you may need to read `.claude/support/feedback/feedback.md` for the relevant entry). Cross-check whether the named gating condition still applies.
3. For criteria 3: count entries missing status; usually a documentation hygiene issue, not a coherence drift issue — flag as low severity.

What does NOT count:
- FB entries with status `wont_fix`, `closed`, `archived`, or `resolved` regardless of age.
- FB entries explicitly tagged with a future date that hasn't passed yet (e.g., "review on 2026-12-01").
- FB entries with status `new` <30 days old — they're in normal triage window.

For each finding, set:
- **Source anchor:** `.claude/support/feedback/feedback.md` (the file containing the FB entries)
- **Files to touch (potential fix):** feedback.md — implementation file (NOT spec/decision/vision), so synthesizer can classify as `bundle-eligible` if the action is just a status update OR `fix-eligible` if it requires a decision
- **Suggested fix:** "Triage N FB entries via /feedback review (see feedback.md § {FB-IDs})" OR "Update status of FB-XXX (deferral condition has lapsed)"

Cluster aggressively: if 12 entries are decayed, that's ONE finding with a list of IDs, not 12 findings.
```

### Lens 5 — `retired-features`

```
You are auditing a project for the RETIRED-FEATURES lens only.

Read {AUDIT_DIR}/inputs/retired-manifests.json (parsed contents of .claude/support/retired/*/manifest.json) and {AUDIT_DIR}/inputs/spec-sections.json.

What counts:
1. A retired-feature manifest exists in `.claude/support/retired/{slug}/manifest.json`, but the spec doesn't mention the feature with a "Retired" / "Superseded" marker in the section that originally defined it.
2. The spec mentions a retired feature in a way that implies it's still active (no retirement context).
3. The spec mentions a feature that has been retired (per manifest) but uses present tense or active framing.

Your method:
1. For each manifest, extract `slug`, `retirement_date`, `retirement_reason`, `replaced_by` (if any).
2. Search the spec for the feature name (slug → human-readable name) or for distinctive phrases from the manifest's description.
3. If found, check whether the surrounding text includes a retirement marker (look for "Retired", "Superseded", "[Retired YYYY-MM-DD]", a strikethrough, or a clear forward-reference to the replacement).
4. If no marker, flag as a finding.

What does NOT count:
- Manifests for features retired >12 months ago (history; spec readers don't need ongoing reminders).
- Spec sections that have already been removed (no current spec mention of the retired feature) — that's correct cleanup, not a finding.
- Spec sections that mention the feature ONLY in a clearly historical context (e.g., "originally we had X, but..." in a phase-history sub-section).

For each finding, set:
- **Source anchor:** the spec section needing a retirement marker
- **Files to touch (potential fix):** spec_v*.md — synthesizer will classify as `kind: decision`
- **Suggested fix:** "Spec amendment via /iterate: add retirement marker to § {N.M} for feature '{name}' (retired {date} per .claude/support/retired/{slug}/manifest.json)"

If multiple sections reference the same retired feature, cluster into ONE finding listing all sections.
```

### Lens 6 — `friction-register`

```
You are auditing a project for the FRICTION-REGISTER lens only.

Read {AUDIT_DIR}/inputs/friction-open.jsonl (open friction register entries; one JSON object per line).

Your job: cluster the open entries by `kind` and `source_anchor`, surface high-frequency themes as findings, and pass through the most distinctive single-instance entries individually.

What counts:
1. **Themed cluster:** 3+ open entries sharing the same `kind` AND overlapping `source_anchor` (e.g., 4 entries about path drift on `foundation/`-rooted paths). Surface as one cluster finding citing the FR-IDs.
2. **High-severity single entry:** a single entry whose `what` describes a structural problem (e.g., "spec § 4.1 contradicts vision § 2.3") even if it's only one entry. Pass through as a finding.
3. **Stale entry (age check):** entries with `captured` >60 days old and `status: open`. Worth surfacing — either resolve, dismiss, or escalate.

What does NOT count:
- Entries already with `status: resolved` or `dismissed` — those are filtered out before you see the file (the orchestrator only writes open entries to friction-open.jsonl).
- Entries whose `kind` is template-improvement (`workflow_deviation`, `template_gap`, etc.) — those write to .session-log.jsonl, not friction.jsonl, so they shouldn't appear here. If you see one, ignore (orchestrator routing bug).

For each finding, set:
- **Source anchor:** the canonical source the cluster references (or `.claude/support/friction.jsonl` if the cluster spans multiple anchors)
- **Files to touch (potential fix):** depends on the cluster — typically spec_v*.md (decision kind) or implementation files (fix-eligible kind). Use the entries' source_anchor field to decide.
- **Suggested fix:** "Resolve N friction register entries (FR-{ids}) about '{theme}' via {action — /iterate, code change, or dismissal}"

If the register is empty or has <3 open entries, return `Findings: 0` — no premature clustering.
```

### Lens 7 — `acceptance-reconciliation`

```
You are auditing a project for the ACCEPTANCE-RECONCILIATION lens only (DEC-022).

Read:
- {AUDIT_DIR}/inputs/verification-result.json — the LATEST phase-level verification result (`criteria[]` of `{name, status, notes}`; may be `{}` if absent). AUTHORITATIVE for the phase it covers.
- {AUDIT_DIR}/inputs/phase-verification.json — a per-phase task-verification rollup `[{phase, phase_name, task_count, finished, verified_pass, phase_complete, task_ids}]` (may be `[]`). `phase_complete: true` means every non-Absorbed / non-On-Hold task in that phase is Finished with passing verification — a PROXY for "this phase's work is done".
- the active `.claude/spec_v*.md`.

**This lens only applies when the project renders acceptance criteria as inline `- [ ]` / `- [x]` checkboxes in the spec.** If the spec has no inline acceptance checkboxes, return `Findings: 0` — there is nothing to reconcile (inline boxes are an optional project convention).

Background (DEC-022): the AUTHORITATIVE acceptance-*status* surface is `verification-result.json` `criteria[]` (rendered as the dashboard's `### Acceptance Criteria`). Inline spec `- [ ]` boxes are authored input and are NOT auto-ticked on phase PASS — so they can read stale. This lens surfaces that staleness ADVISORILY across ALL completed phases; it never edits the spec.

**Two evidence tiers (DEC-022 v4.27.0 — full historical reconciliation).** `verification-result.json` is overwritten each phase, so it only holds the latest phase's `criteria[]`. To reconcile earlier phases too:
- **Authoritative (the latest phase):** use `verification-result.json`'s real `criteria[]` PASS/FAIL.
- **Proxy (earlier completed phases):** use `phase-verification.json` — a phase with `phase_complete: true` is done, so its unticked acceptance boxes are stale. There is no persisted `criteria[]` for these phases, so label the finding as a per-task proxy.

What counts:
1. A phase the spec renders inline boxes for, whose boxes are unticked (`- [ ]`) AND the phase is verified done — either (a) it is the latest phase and `verification-result.json` records `result: "pass"` (authoritative), or (b) `phase-verification.json` marks it `phase_complete: true` (proxy). This is the flirty-gym symptom, now caught for every completed phase, not only the latest.
2. Lower severity: a box ticked `- [x]` while the matching `criteria[]` entry is `status: "fail"` (latest phase), or while the phase is NOT complete per the rollup — an over-claim.

Your method:
1. Scan the active spec for inline acceptance checkboxes (`- [ ]` / `- [x]`), grouping by the phase / section they sit under. If none, return Findings: 0.
2. For each phase that renders boxes, determine its verified status: the latest phase → `verification-result.json` (`result` + `criteria[]`); any other phase → look up `phase_complete` in `phase-verification.json` by `phase`.
3. For the latest phase, match boxes to `criteria[]` entries ADVISORILY by fuzzy text similarity (free-text names, re-segmented, no ID link — DEC-022 Q2). Treat a match as a *suspected* correspondence; when you cannot confidently match a box to a criterion, say so rather than guessing. For proxy phases there is no `criteria[]` to match — flag at phase granularity ("all N boxes unticked for a completed phase").
4. Flag divergence per phase, naming the tier: e.g. "Phase 2 (authoritative): 0/4 boxes ticked but verification-result.json records result=pass (7/7)." or "Phase 1 (proxy): 0/3 boxes ticked but all 6 tasks Finished+verified (phase_complete)."

What does NOT count:
- Specs with no inline acceptance checkboxes (the common case).
- Phases that are NOT complete — the current / in-progress phase, or any phase with `phase_complete: false` that the latest `verification-result.json` does not record as passed. Unticked boxes there are legitimate (the work isn't done).
- A box/criterion pair you cannot match with reasonable confidence (latest phase) — note the ambiguity; do not assert divergence on a guess.

For each finding, set:
- **Source anchor:** the spec phase / section whose boxes diverge (e.g., "spec_v2.md § Phase 2 — Acceptance Criteria")
- **Files to touch (potential fix):** spec_v*.md — synthesizer will classify as `kind: decision` (reconciliation routes via /iterate; boxes are spec body)
- **Evidence:** state the tier (authoritative / proxy) and the numbers (boxes ticked vs phase status).
- **Suggested fix:** "Reconcile via /iterate: spec § {phase} acceptance boxes are stale vs verified status (DEC-022 — boxes are authored input; the dashboard `### Acceptance Criteria` is the live status). Tick to match, or drop the inline boxes and rely on the dashboard."

Cluster per phase: one finding per phase (listing its unticked boxes), never one per box. If several completed phases are stale with the same root, you may emit a single clustered finding ("Phases 1–3 acceptance boxes never ticked despite completion"). The match is advisory — never edit the spec; only surface.
```

---

## Synthesizer prompt

```
You are merging the output of 7 parallel coherence-audit lens agents into one ranked report. You did not run the lenses yourself. You have:

- {AUDIT_DIR}/lenses/*.md  — 7 lens reports (some may be "Findings: 0")
- {AUDIT_DIR}/inputs/*     — the raw inputs (decisions, spec-sections, friction-open, feedback-status, retired-manifests, meta)
- Read access to project files for verification (especially `.claude/spec_v*.md`, `.claude/support/decisions/decision-*.md`, `.claude/tasks/task-*.json`)

Your job: dedupe, cluster, classify by `kind`, dedupe against in-flight task work, and write findings.md + digest.json.

## Algorithm

1. **Parse every lens report** into a flat list of findings. Each finding has {id, title, severity, source_anchor, files_affected, files_to_touch, evidence, what, why, fix, suggested_kind, lens}.

2. **Pre-cluster within lens** (BEFORE cross-lens). When one lens emitted N findings sharing the same source_anchor or fix candidate (e.g., 5 superseded-decisions findings all citing DEC-010 in spec § 5.2 / 5.3 / 5.5), fold into one finding listing all sub-instances.

3. **Cross-lens cluster** the (pre-clustered) findings that refer to the same atomic surface:
   - Strong match: same `source_anchor` AND same `files_to_touch`
   - Medium match: same `source_anchor` AND ≥0.5 token overlap on the fix-candidate text
   - Weak match: same canonical concept (e.g., `superseded-decisions` flags DEC-010 spec drift; `vocab-drift` flags "personalized" vs "maintainer-curated"; both are about DEC-010 → DEC-050 supersession on § 5.2) — cluster only if titles also overlap.

4. **For each cluster:**
   - canonical = the finding with the most concrete evidence (longest evidence text; tie-break by alphabetical lens name)
   - lenses_seen = set of all contributing lens names
   - severity = max in cluster
   - Drop the original IDs; assign a fresh `C-NN` sequence in cluster order
   - **Write `description`** — per § "Write `description`" in the spliced shared contract below. Example: title `"Spec § 5.2 still describes per-user generation; DEC-050 selected maintainer-curated"`, description `"Spec §§ 5.2, 5.3, 5.5 still describe per-user generation, but DEC-050 selected maintainer-curated — 3 unfixed references in the active spec."`

5. **Classify `kind` per cluster** — apply § "Classify `kind` per cluster" from the spliced shared contract below (DEC-013 Option C; HARD RULE FIRST; bundle-eligible only when ALL criteria hold; when in doubt → fix-eligible). Promote/Dismiss actions for `fix-eligible` items are available via tick + bulk CLI / natural-language to Claude; not rendered per-item — see `dashboard-regeneration.md` § "Audit Findings sub-section".

6. **Pending-work dedupe.** For each clustered finding, scan `.claude/tasks/task-*.json` for tasks with `status` in `{Pending, In Progress, Awaiting Verification}`. Match if:
   - The task's `files_affected` overlaps with the finding's `files_to_touch`, OR
   - The task's `description` or `title` mentions the finding's `source_anchor` (spec section, decision id, or path)
   - For friction register entries cited in the cluster: if the entry's `captured_in.task` exists and that task is still Pending / In Progress / Awaiting Verification, it's already owned.

   On match: REMOVE the finding from `items[]` and ADD an entry to `annotations[]`:
   ```json
   {
     "type": "covered_by_pending_task",
     "what": "{finding title}",
     "covered_by": "{task_id}",
     "covered_by_status": "{task status}",
     "source_anchors": [...],
     "suppressed_finding_id": "C-NN"
   }
   ```

7. **Target ≤8 user-facing items in `items[]`.** If after pending-work dedupe you still have >8, cluster more aggressively. The point is decision support, not exhaustive listing.

8. **Sanity checks before returning:**
   - No item in `items[]` has `kind: bundle-eligible` AND `files_to_touch` containing any spec/decision/vision path. If you find one, you mis-classified — re-check the hard rule.
   - Every cluster appears in either `items[]` or `annotations[]`. Nothing dropped silently.
   - `findings_count.raw` = total findings across all lens reports; `findings_count.clustered` = items + annotations count.

## Output

Return TWO artifacts:

### 1. `findings.md` — full clustered report

```markdown
# Coherence Audit — {today} — {project name from CLAUDE.md or directory name}

`{audit dir relative path}` · 7 lenses · {raw} raw findings → {clustered} after dedupe → {items_count} surfaced ({deduped_count} routed to in-flight tasks)

## Top findings

(Render `items[]` here, severity desc within each kind, in this kind order: bundle-eligible, fix-eligible, decision, design)

### C-01 · {title}
- **Kind:** {kind} · **Severity:** {severity} · **Lenses:** {comma list}
- **Source anchor:** {source_anchor}
- **Files to touch:** {comma list}
- **Evidence:** {quoted}
- **Why:** {one line}
- **Suggested fix:** {one line}
- **Action:** [Promote to feedback] (Stage 6 will add [Fix it] here for bundle-eligible / fix-eligible)
{If bundle-eligible: include bundle_eligibility object inline}
{If decision: include iterate_routing object inline}

### C-02 · ...
(repeat per item)

## Annotations — already covered by in-flight work

(Render `annotations[]` here, one per line)

- C-NN ({type}) → {covered_by} ({covered_by_status}) — "{what}"

## Per-lens raw counts

| Lens | Raw | After cluster |
|------|-----|---------------|
| superseded-decisions | ... | ... |
| ...                  | ... | ... |

## Promote to feedback

Tick the box, then run `/audit-coherence promote {audit-ts}`.

- [ ] C-01 — {title}
- [ ] C-02 — {title}
...
```

### 2. `digest.json` — machine-readable digest

Format per the spliced § "digest.json schema (shipped canonical)" below — set `"audit": "coherence"`, omit `viewport`. Envelope:

```json
{
  "audit": "coherence",
  "ran_at": "{ISO timestamp from meta.json}",
  "findings_count": {
    "raw": {N},
    "clustered": {M},
    "bundle_eligible": {K},
    "fix_eligible": {L},
    "promote_eligible": {decision + design counts},
    "deduped_to_pending_work": {Z}
  },
  "items": [ {full item objects per the canonical item schema} ],
  "annotations": [ {full annotation objects} ]
}
```

Both files MUST be returned. The orchestrator writes both to disk.

## Shared contract

{SPLICE HERE — the orchestrator inserts the verbatim text of `.claude/support/reference/audit-family-core.md` §§ "Synthesizer shared contract" and "digest.json schema (shipped canonical)" at dispatch time.}
```

---

## Promote mode

`/audit-coherence promote {audit-ts} [--all | C-IDs]`

**Canonical algorithm:** `.claude/support/reference/audit-family-core.md § "Promote mode (canonical)"` — execute it with this command's substitution row (`{AUDIT}: coherence` · `{P}: C` · `{DIR-GLOB}: coherence-*` · `{CMD}: /audit-coherence`). The FB-entry template, dedupe options, and `digest.json` / `friction.jsonl` / `findings.md` cascades are all defined there; no divergence.

---

## Fix mode (bundle-eligible only — DEC-013 Option C)

`/audit-coherence fix {audit-ts} {C-ID}` · `/audit-coherence fix latest {C-ID}` — apply a single bundle-eligible finding inline.

**Canonical algorithm:** `.claude/support/reference/audit-family-core.md § "Fix mode (canonical)"` (kind gate, staleness re-read, hard-exclusion re-check, single-approval apply, commit + state cascade, and the run-tests-after-removal rule) — execute with this command's substitution row. Full mechanism: `audit-fix-workflow.md § "[Fix it] — inline apply"`.

---

## Triage mode

`/audit-coherence triage [audit-ts]` — interactive walker through the audit's pending findings; the preferred entry point when an audit has multiple pending findings. Closes the dashboard-tick → CLI re-specification courier pattern and the audit-name memory burden (FB-006 sub-issues 1+2).

**Canonical algorithm, per-kind action gates, state mutations, and edge cases:** `.claude/support/reference/audit-family-core.md § "Triage mode (canonical)"` — execute with this command's substitution row (`{AUDIT}: coherence` · `{P}: C` · `{DIR-GLOB}: coherence-*` · `{CMD}: /audit-coherence`). `latest` (or no arg) resolves to the newest `coherence-*` audit dir by `ran_at`; the user never types the audit name unless they want an older audit explicitly.

---

## Edge cases

- **No spec file found.** This command's `applies_when` filters this out, but defensively: if no `.claude/spec_v*.md` exists, abort with `Coherence audit requires a spec file. None found at .claude/spec_v*.md`.
- **No decisions yet.** `decisions.json` will be `[]`; lens `superseded-decisions` returns 0 findings; other lenses still run.
- **Empty friction register.** `friction-open.jsonl` is empty; lens `friction-register` returns 0 findings; other lenses still run.
- **No retired features.** `retired-manifests.json` is `[]`; lens `retired-features` returns 0 findings.
- **First-run on a young project.** Most lenses return 0; `feedback-decay` may be the only signal source. Acceptable — the audit's value grows as the project accumulates state.
- **Re-running the audit.** A second run creates a new `coherence-{ts}/` dir. Open Question 3 (proposal) is resolved as: dedupe against the prior digest at synthesizer-time, badging persistent findings as `(unchanged)` and fresh ones as `(new)`. Initial implementation can defer dedupe — each run is fresh; user manages by re-running and comparing.
- **Hard-rule mis-classification.** If the synthesizer puts a `kind: bundle-eligible` finding whose `files_to_touch` includes a spec path, the orchestrator's post-synth validation catches it (sanity check 1) and either (a) re-routes to `kind: decision`, or (b) stops with an error if the mis-classification is systemic.

---

## Why this shape

- **One file, multiple modes.** Capture + lenses + synth + promote in one command keeps state colocated. The audit dir is the only persistence beyond `friction.jsonl` updates.
- **Capture is orchestrator-side, lenses are sub-agents.** The capture step reads filesystem state into structured JSON; lens agents consume the JSON without re-walking the filesystem (cheaper, deterministic). Sub-agents only fan out where independence + parallelism matters.
- **Lenses cap context.** Each lens reads only its specific input slice with sharp in/out-of-scope rules. No anchor bias.
- **Synthesizer enforces the hard rule structurally.** The "spec/decision/vision read-only outside /iterate" rule is enforced in synthesizer step 5 (HARD RULE FIRST) AND in the post-synth sanity check. Two independent enforcement points; classification cannot leak.
- **Pending-work dedupe respects existing ownership.** Annotations capture the issue without spawning duplicate work — same pattern as audit-ui's promote-mode dedupe against existing FB entries, applied earlier in the pipeline.
- **Promote uses the existing feedback flow.** The audit produces feedback-shaped artifacts; `/feedback review` and `/iterate` work unchanged.
- **Status updates atomic.** When a finding resolves (via promote, future [Fix it], or future bundled-apply), `digest.json` and `friction.jsonl` are updated in place by id. No state drift.
