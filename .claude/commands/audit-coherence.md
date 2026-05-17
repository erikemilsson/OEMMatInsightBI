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
/audit-coherence                            # full audit, all 6 lenses
/audit-coherence --lens {name}              # run only the listed lens (comma-separated for multiple)
/audit-coherence --since {YYYY-MM-DD}       # restrict to friction register entries / FB items captured after date
/audit-coherence triage [audit-ts]          # interactive walker: per-finding fix/promote/dismiss (default audit-ts: latest)
/audit-coherence promote {audit-ts}         # promote ticked findings → feedback.md (same shape as /audit-ui promote)
/audit-coherence promote {audit-ts} --all   # bulk promote everything in the report
/audit-coherence promote {audit-ts} F-01,F-07
/audit-coherence fix {audit-ts} {C-ID}      # apply a single bundle-eligible finding inline
```

Stage 5 (`/health-check` Part 6) will dispatch this command automatically based on `applies_when`. Until then, invoke directly.

---

## Lenses

Six lenses, each running as a fresh-context sub-agent in parallel:

| Lens | Catches | Detection mode |
|------|---------|---------------|
| `superseded-decisions` | Decisions marked `superseded` / `partially_superseded` whose old language still appears in the active spec | Auto-grep + spec re-read |
| `vocab-drift` | Same concept named with different terms across spec sections, or between spec and on-disk implementation references | Cross-section term frequency + register read |
| `path-drift` | File paths the spec mentions that don't exist on disk; or implementation uses a different canonical path than spec | Glob + spec scan |
| `feedback-decay` | `FB-*` entries open >30 days with no status change | Parse feedback.md status fields |
| `retired-features` | Manifests in `.claude/support/retired/` without a corresponding retirement marker in spec | Filesystem + spec scan |
| `friction-register` | Cluster open `friction.jsonl` entries by `kind` and `source_anchor`, surface high-frequency themes | Read register + thematic grouping |

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
│   └── meta.json                # audit run config: timestamp, lenses requested, --since filter
├── lenses/
│   ├── superseded-decisions.md
│   ├── vocab-drift.md
│   ├── path-drift.md
│   ├── feedback-decay.md
│   ├── retired-features.md
│   └── friction-register.md
├── findings.md                  # full clustered report (Claude-readable)
├── digest.json                  # 4-8 user-facing items with kind classification + eligibility flags
└── synth-input.md               # concatenated lens output passed to synthesizer (audit trail)
```

Project rule (DEC-004): sub-agents cannot write to `.claude/`. The orchestrator (this command, running in the main conversation) handles all writes. Sub-agents return their report as text; the orchestrator saves it.

---

## Workflow

### Phase 1 — Capture (orchestrator drives directly)

1. Compute audit dir: `.claude/support/audits/coherence-{YYYY-MM-DD-HHmm}/`. Create with subdirs `inputs/` and `lenses/`.
2. Write `meta.json` with run config: timestamp, lenses requested (default: all 6), `--since` filter if set.
3. **Capture decisions.** Glob `.claude/support/decisions/decision-*.md`. For each file, parse YAML frontmatter and extract: `id`, `title`, `status`, `superseded_by` (if present), `superseded_date` (if present), `related.tasks` (if present). Write the array to `inputs/decisions.json`.
4. **Capture spec.** Read the active `.claude/spec_v*.md` (exactly one per single-spec invariant). Build a section map: for each `## ` heading, record `{heading_text, section_id (e.g. "5.2"), line_start, line_end, fingerprint: sha256(section_body)}`. Write to `inputs/spec-sections.json`.
5. **Capture friction register.** If `.claude/support/friction.jsonl` exists, read all lines, filter `status == "open"` (and `captured >= --since` if set), write to `inputs/friction-open.jsonl`. If file doesn't exist, write empty file.
6. **Capture feedback statuses.** If `.claude/support/feedback/feedback.md` exists, parse for `## FB-NNN` headers and `**Status:**` + `**Captured:**` lines beneath. For each FB entry, compute age in days from captured date. Write `[{id, status, captured, age_days, title}]` to `inputs/feedback-status.json`.
7. **Capture retired-feature manifests.** Glob `.claude/support/retired/*/manifest.json`. Read each. Write the combined array to `inputs/retired-manifests.json`.
8. **(Optional) Sample task notes for friction-marker prose.** This is a fallback for projects that haven't accumulated friction register entries yet — sample up to 20 most-recently-modified `.claude/tasks/task-*.json`, extract any `notes` containing keywords `"friction"`, `"captured for /iterate"`, `"spec drift"`. Append to `friction-open.jsonl` as synthetic register entries with `id: "FR-SYNTHETIC-{N}"`, `kind: "spec_implementation_gap"`, `captured_in: {agent: "task_notes_sample"}`.

Capture should complete within 30s. If any input source is missing or fails to parse, log a warning to `meta.json` and continue with empty data — lenses handle empty inputs gracefully (return 0 findings).

### Phase 2 — Lenses (6 parallel sub-agents)

Spawn N sub-agents in a **single Task tool message** so they run concurrently. Each:
- Runs as `general-purpose` agent (per `.claude/rules/agents.md` § "Dispatch Convention" — persona-via-prompt-content)
- Receives the audit dir path + ONLY its single lens prompt
- Never sees other lenses' output
- Returns markdown formatted per the **Lens output format** below

Orchestrator:
1. Collect each agent's returned text.
2. Write to `lenses/{lens-name}.md`.
3. Concatenate all into `synth-input.md` for Phase 3.

If `--lens` is set, run only those lenses; if unset, run all 6.

### Phase 3 — Synthesize

Spawn one general-purpose agent with:
- Path to `lenses/`, `inputs/`, and the full `inputs/decisions.json` + `inputs/spec-sections.json`
- The **Synthesizer prompt** below
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

`lens-prefix` = first three letters of the lens name (`sup`, `voc`, `pat`, `fee`, `ret`, `fri`).

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

Read {AUDIT_DIR}/inputs/spec-sections.json and {AUDIT_DIR}/inputs/friction-open.jsonl (open friction register entries with kind=vocab_drift or terminology_mismatch).

What counts:
1. Same concept named with different terms across spec sections — e.g., "sub-tab" in § 9.1 but "section nav" in § 42.5; "personalized principles" in § 5.2 but "maintainer-curated principles" in § 5.5.
2. Spec uses term X but the friction register has open entries reporting that implementation uses term Y for the same concept (cross-reference register entries against spec).
3. Plural / spelling drift on the same noun across spec sections ("outerwears" vs "outerwear", "Bottoms" vs "Trouser") if the same noun appears in multiple sections.

Your method:
1. Open the active spec file. Scan for noun phrases that appear in multiple sections.
2. For each candidate noun phrase, search for synonyms or close variants in the spec. If found in different sections without cross-reference, flag.
3. Read open friction register entries with `kind: vocab_drift` or `kind: terminology_mismatch`. For each, surface the friction's evidence as a finding (it was already flagged by an agent during /work).

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
- Paths to template files that legitimately don't exist in this specific project (`.claude/support/reference/audit-template-pattern.md` if the project hasn't installed the audit family yet).

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

---

## Synthesizer prompt

```
You are merging the output of 6 parallel coherence-audit lens agents into one ranked report. You did not run the lenses yourself. You have:

- {AUDIT_DIR}/lenses/*.md  — 6 lens reports (some may be "Findings: 0")
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
   - **Write `description`** — a plain-English one-line summary suitable for at-a-glance dashboard triage. Derive from the canonical finding's `What` line; expand with `Why` context only if the bare `What` would be opaque without it. Constraints: complete sentence, period-terminated, ~80-140 chars (hard cap 200 to prevent wrap disasters), self-contained (names the artifact / file / section affected so the user doesn't need to open `findings.md`). Distinct from `title` — `title` is a short cluster identifier (used as findings.md cluster header + FB title on promote); `description` is the readable sentence rendered on the dashboard digest. Example: title `"Spec § 5.2 still describes per-user generation; DEC-050 selected maintainer-curated"`, description `"Spec §§ 5.2, 5.3, 5.5 still describe per-user generation, but DEC-050 selected maintainer-curated — 3 unfixed references in the active spec."`

5. **Classify `kind` per cluster (DEC-013 Option C is now an action layer — bundle-eligible classification triggers actual inline-apply at Fix-it time, so be conservative):**
   - **HARD RULE FIRST.** If `files_to_touch` includes ANY of: `.claude/spec_v*.md`, `.claude/support/decisions/decision-*.md`, `.claude/vision/**/*.md` → `kind: decision` (always; no exceptions; this enforces Component 6 hard exclusion). Set `iterate_routing.reason: "spec/decision/vision file modification — read-only outside /iterate"`.
   - If suggested_kind is `design` from any contributing lens (e.g., friction-register cluster of `design_contradiction` entries) → `kind: design`. No [Fix it] action; promote to FB only.
   - **Bundle-eligible classification (DEC-013 Option C — triggers actual inline-apply via [Fix it])** — only when ALL hold:
     a. Implementation-file-only (no spec/decision/vision per HARD RULE above)
     b. Source-confirmed: the fix is a sync from one authoritative source (cited concretely in `source_anchors[]`) to a derived/dependent location. NOT bundle-eligible if the only "source" is the lens's inference.
     c. Reversible: text edit, dep removal, file deletion of clearly-orphaned items
     d. No new judgment: the fix's content is already present somewhere authoritative (audit syncs, doesn't decide)
     e. Bounded scope: ≤3 files
     f. **Orphan-dep removal (special-case per DEC-013 Q3):** still classify as bundle-eligible (it's the canonical case) but set `bundle_eligibility.transitive_consumer_risk: true` so the action layer warns the user to run tests after apply (dynamic require / `importlib.import_module` / string-keyed import patterns aren't statically detectable).
     g. **When in doubt → fix-eligible, not bundle-eligible.** The action layer's at-apply re-read invariant cannot catch semantic mismatches that the synthesizer creates. Conservative classification at synthesis time is the load-bearing safety property.
     Set on bundle-eligible items: `bundle_eligibility.source_confirmed: true`, `reversible: true`, `files_count: {N}`, `touches_spec_or_decisions: false`, `transitive_consumer_risk: {bool}`.
   - Otherwise (implementation-only but doesn't meet ALL bundle-eligible criteria above, or >3 files, or ambiguous fix) → `kind: fix-eligible`. Surfaces on dashboard with the italicized `*(fix-eligible — manual review pending future DEC)*` kind annotation only — no inline `[Fix it]` until a future DEC expands inline-apply per DEC-013 telemetry validation gate. (Promote/Dismiss actions are available via tick + bulk CLI / natural-language to Claude; not rendered per-item — see `dashboard-regeneration.md` § "Audit Findings sub-section".)

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

`{audit dir relative path}` · 6 lenses · {raw} raw findings → {clustered} after dedupe → {items_count} surfaced ({deduped_count} routed to in-flight tasks)

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

Format per `template-maintenance/audit-command-family-proposal.md` Component 2 schema:

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
  "items": [ {full item objects per Component 2 schema} ],
  "annotations": [ {full annotation objects} ]
}
```

Both files MUST be returned. The orchestrator writes both to disk.
```

---

## Promote mode

`/audit-coherence promote {audit-ts} [--all | F-IDs]`

Same shape as `/audit-ui promote`:

1. Read `audit-{ts}/findings.md`. Find the `## Promote to feedback` section.
2. Determine selection (--all, explicit IDs, or ticked boxes).
3. For each selected finding, read its full body from `findings.md`.
4. Read `.claude/support/feedback/feedback.md` and `.claude/support/feedback/archive.md`. Compute next `FB-NNN`.
5. **Dedupe pass.** For each selection, scan both feedback files for entries with matching source / similar title. On match, prompt user `[S]kip / [U]persede / [M]erge / [N]ew anyway`.
6. For each non-deduped selection, append to `feedback.md` an entry shaped per the audit-ui promote-mode template (with `**Source:** audit-coherence-{audit-ts} {C-ID}` line).
7. Update `digest.json` in place: set `items[i].status = "promoted"`, `items[i].resolved_by = {kind: "promote_fb", ref: "FB-NNN", at: now}`.
8. For any friction register entries cited by the promoted findings: update `friction.jsonl` in place to mark `status: resolved`, `resolved_by: {kind: "promote_fb", ref: "FB-NNN", at: now}` per `friction-register.md` § "Status update protocol".
9. Update `findings.md` in place: replace `- [x] C-NN — title` with `- [x] C-NN → FB-NNN promoted {date}`.
10. Print summary.

The existing `/feedback review` → `/iterate` flow is unchanged. The audit just produces feedback-shaped artifacts.

---

## Fix mode (bundle-eligible only — DEC-013 Option C)

`/audit-coherence fix {audit-ts} {C-ID}` — apply a single bundle-eligible finding inline.

Available only for findings with `kind: bundle-eligible`. Other kinds (`fix-eligible`, `decision`, `design`) require manual review or `/iterate` routing — see kind-availability table in `.claude/support/reference/audit-fix-workflow.md` § "Per-kind action availability".

**Mechanism:** see canonical reference at `.claude/support/reference/audit-fix-workflow.md` § "Action protocol — Stage 6 (Option C per DEC-013)" / "[Fix it] — inline apply (bundle-eligible only)". In short:

1. Read finding from this audit's `digest.json` + `findings.md#{C-ID}`
2. Verify kind is `bundle-eligible` (refuse with kind-specific message otherwise)
3. Verify finding `status == "pending"` (not already resolved/dismissed/promoted)
4. Re-read cited `source_anchors[]` to verify finding's claim still holds (refuse if stale)
5. Re-verify hard-exclusion (no spec/decision/vision in `files_to_touch[]` — defense-in-depth against mis-classification)
6. Show concrete change + ask single approval
7. On approval: apply, single commit `audit-fix: {C-ID} — {summary}`, update `digest.json` + `friction.jsonl`

**Important:** after any [Fix it] touching `package.json`, run your test suite to catch transitive consumers static analysis missed (DEC-013 Q3 — orphan-dep removal can break dynamic-require / `importlib` / string-keyed import patterns). Same applies to source-code deletions.

`/audit-coherence fix latest {C-ID}` — convenience: resolves "latest" to the newest `coherence-*` audit dir by `ran_at`.

---

## Triage mode

`/audit-coherence triage [audit-ts]` — interactive walker through the audit's pending findings.

The preferred entry point when an audit has multiple pending findings. The walker iterates each pending non-dismissed finding, presents its `description` + kind + kind-conditional actions, dispatches the user's choice (Fix it / Promote / Dismiss / Skip / Quit), and continues to the next. Closes the dashboard-tick → CLI re-specification courier pattern and the audit-name memory burden (FB-006 sub-issues 1+2).

**Default for `audit-ts`:** `latest` — resolves to the newest `coherence-*` audit dir by `ran_at` (same resolution as `/audit-coherence fix latest`). User never types the audit name unless they want an older audit explicitly.

### Algorithm

1. **Resolve audit dir.** No arg or `latest` → newest `coherence-*` dir by `ran_at`. Explicit `{audit-ts}` → `.claude/support/audits/coherence-{audit-ts}/`.
2. **Empty-state checks** (exit cleanly, no state mutation):
   - Audit dir does not exist → `No coherence audit has run in this project yet. Run /audit-coherence first.`
   - Audit dir exists but no findings have `status: pending` (all resolved/dismissed/promoted) → `No pending findings in latest coherence audit. Nothing to triage.\n(Last audit ran {ran_at date}. Run /audit-coherence to refresh.)`
3. **Read pending findings.** From `digest.json items[]`, filter where `status == "pending"` AND `id NOT IN` sidecar's `audit_digest.dismissed_ids[]`. Preserve digest order. (Sidecar missing → treat `dismissed_ids` as `[]`.)
4. **Print walk header.** `Reading latest coherence audit: coherence-{ts} ({N} pending of {M} total)`.
5. **Per-finding loop** (for each of the `N` pending findings):
   - **Print finding card** — `[{i+1}/{N}] {C-ID} ({kind})` followed by `item.description ?? item.title` (title fallback for pre-v3.18.0 digests), then `Files to touch:` and `Source anchors:` lines, then the kind-conditional `Actions:` prompt (see § "Per-kind action gates" below).
   - **Read user action.** Accept single-letter shorthand (case-insensitive) OR natural-language with a verb (`fix it`, `promote`, `dismiss because X`, `skip`, `quit`). Map to `F` / `P` / `D` / `S` / `Q`.
   - **Kind-action validation.** If the user picks an action the kind doesn't support (e.g., `F` on a `decision` kind), print the kind-specific refuse message from `audit-fix-workflow.md § "Action protocol — Stage 6 (Option C per DEC-013)"` step 3 and re-prompt the same finding.
   - **Dispatch** to the canonical per-action mechanics (no divergence):
     - `F` → `audit-fix-workflow.md § "[Fix it] — inline apply"` steps 4-10 (at-apply re-read + hard-exclusion + show + approve + commit + state update).
     - `P` → `## Promote mode` steps 3-9 (read body, dedupe, append to `feedback.md`, update `digest.json` + `friction.jsonl` + `findings.md`). Single-finding subset of bulk promote.
     - `D` → if user typed bare `D`, follow up with `Reason (optional, blank to skip): ` and read one line. If user typed `dismiss because X`, parse `X` as the reason inline. Then dispatch to `audit-fix-workflow.md § "[Dismiss]"` steps 1-4.
     - `S` → no mutation; advance.
     - `Q` → break loop, jump to step 6.
   - **Auto-advance** after dispatch completes — print a one-line result, then immediately print the next finding's card. No `Continue? [Y/N]` confirmation between findings (the user can `[Q]uit` at any prompt to step out).
6. **End-of-walk summary.** `Triaged {X} of {N} findings. {Z} still pending. Run /audit-coherence triage again later to revisit.` where `Z` = skipped + remainder-after-quit.

### Per-kind action gates

Mirrors `audit-fix-workflow.md § "Per-kind action availability"`:

| Finding kind | Actions prompt |
|--------------|----------------|
| `bundle-eligible` | `[F]ix it · [P]romote to FB · [D]ismiss · [S]kip · [Q]uit` |
| `fix-eligible` | `[P]romote to FB · [D]ismiss · [S]kip · [Q]uit` (no `[F]ix it` — deferred per DEC-013) |
| `decision` | `[P]romote to FB · [D]ismiss · [S]kip · [Q]uit` (no `[F]ix it` — routes via `/iterate`) |
| `design` | `[P]romote to FB · [D]ismiss · [S]kip · [Q]uit` (no `[F]ix it` — promote → `/research`) |

The kind annotation is printed alongside the card header (`{C-ID} ({kind})`) so the reason for the action list is transparent.

### State mutations — atomic per action

Each action's mutation is identical to the existing per-action flow; no divergence:

- **Fix it** → single commit `audit-fix: {C-ID} — {summary}`; `digest.json items[i].status: "resolved"`; `friction.jsonl` cascades.
- **Promote** → next `FB-NNN` computed, dedupe pass, append to `feedback.md`; `digest.json items[i].status: "promoted"`; `friction.jsonl` + `findings.md` cascades.
- **Dismiss** → append id to sidecar's `audit_digest.dismissed_ids[]`; `digest.json items[i].status: "dismissed"` + `dismiss_reason` + `dismissed_at`.
- **Skip** → no mutation.

`Ctrl+C` mid-walk is safe — completed actions stay committed, remaining stay pending. The next `/audit-coherence triage` resumes from whichever findings are still `pending`.

### Edge cases

- **Pre-v3.18.0 digests without `description`** → render `item.title` (same `{description ?? title}` fallback as `dashboard-regeneration.md § "Body field selection"`).
- **Parallel-session collision.** Same caveat as `[Fix it]` (per `audit-fix-workflow.md § "Known limitations"` → "Parallel-session collision"): don't run `/audit-coherence triage` while another session is running `/work` on overlapping files. The at-apply re-read invariant catches stale source for the Fix-it dispatch path, but doesn't lock against concurrent edits.
- **Mixed audit kinds in the project.** Each audit family member has its own `triage` sub-command. No unified `/triage` across audit kinds — run `/audit-coherence triage` and `/audit-ui triage` separately.
- **Re-running `/audit-coherence` mid-triage.** A fresh audit replaces sidecar items at next dashboard regen. The next `triage` invocation walks the new digest; pending items from the older audit are decoupled from the dashboard. Acceptable — `triage` operates on a named digest, not the dashboard.

`/audit-coherence triage latest` (explicit `latest` keyword) is equivalent to the no-arg form.

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
