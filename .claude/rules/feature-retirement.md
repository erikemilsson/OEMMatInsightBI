---
paths:
  - ".claude/support/retired/**"
---
# Feature Retirement Workflow

How to retire a feature in a **frozen, restorable** state — the snapshot lives at the retirement commit, the spec keeps a "Retired (YYYY-MM-DD)" marker, and the directory convention makes restoration mechanical.

Use this when the answer to *"do I want this code back later?"* is *"maybe"*.

## When to Use This Workflow

- Feature is shipped + working, but conviction in it has faded.
- A clearer architecture replaces it but the old surface might still teach something on revisit.
- The feature can't be sustained against the evolving codebase but the implementation work is too costly to forget.

**Do NOT use it for:**
- **Permanent deletion.** If you're sure you'll never want it back, use `git rm` and let git history hold it. The retirement workflow is overhead for the "park-and-revisit" case.
- **Live A/B toggles.** This workflow ships a snapshot at a SHA — it's not a feature flag. If you want the feature reachable to some users at runtime, build a feature flag instead.
- **Refactoring a single helper.** Helpers don't get retired; their callsites get refactored.

## Pre-Retirement Engine-Consumer Audit

Before running the procedure, verify the field has no engine consumers. A snake_case-only grep gives false confidence — fields surface in multiple naming derivatives, and an incomplete audit ships a retirement that silently degrades runtime behavior (engine reads return `undefined` post-data-migration).

Search across all these patterns before declaring "no consumer":

- **snake_case** — original field name (e.g., `price_quality_philosophy`)
- **CamelCase derivatives** — types and constants derived from it (e.g., `PriceQualityPhilosophy`, `PHILOSOPHY_WEIGHTS`)
- **Shortened forms** — engine-side abbreviations (e.g., `RankerSignals.philosophy` for a field named `price_quality_philosophy`)
- **String literals** — quoted references in dispatch tables, JSON loaders, on-disk schemas

If any pattern matches, the retirement either needs an engine-consumer migration step first, or is premature (the field is still load-bearing). Either way, surface as a precondition before running the procedure.

## Procedure

Five steps, in order. Each step has an artifact you can point at when verifying acceptance.

### Step 1 — Snapshot Capture

Copy the feature's source-of-truth files into the retirement archive. The snapshot must be **complete enough that a reasonably-skilled developer can restore the feature to a buildable state from the snapshot + the pinned commit SHA + the manifest's `restore_notes`** without needing to crawl git archaeology.

**What to copy** (include all that apply — multi-file features mirror all paths):

- **Routes / pages / handlers** — server-side route handlers, page components, layouts, and any framework-specific entry points uniquely owned by the surface.
- **UI components** — components used only by the retired surface. Shared components stay where they are (see *shared helper* edge case below).
- **Slash commands** — `.claude/commands/<name>.md` if the retired feature is a Claude Code surface.
- **Spec excerpt** — when the spec described the feature, copy the section(s) describing it, as they read at `commit_sha`. Save as `<feature-slug>/spec-excerpt.md` (`manifest.json::spec_excerpt_path`, which is `null` when no spec section described the feature). This insulates the snapshot against later spec rewrites.
- **Dependent helpers / lib code** — anything exclusively owned by the feature.
- **Tests (recommended, optional)** — co-located unit / behavior tests so a buildable-state restoration can verify itself. If tests are excluded for size or staleness reasons, note this in `restore_notes`.

**What NOT to copy:**
- Shared helpers used by other features (they stay in place; `restore_notes` calls out shared dependencies).
- `node_modules`, build artifacts, generated files.
- User data the feature read or wrote (it's user data, not code; see *application state* edge case below).
- Tests for helpers the retired feature doesn't uniquely own.

**Mirror the original repo paths.** If the feature lives at `src/app/checkout/page.tsx`, the snapshot path is `<feature-slug>/src/app/checkout/page.tsx`, so a deleted file can be copied straight back when git history is unavailable.

### Step 2 — Commit Pin

Record the **last commit where the feature was live** as `commit_sha`, before the retirement commit lands:

```
manifest.commit_sha = git rev-parse HEAD   # while the feature is still in the tree
```

Retire in **one commit** that removes the feature and adds its manifest and snapshot, one feature per commit where practical, with nothing unrelated in it. That *retirement commit* is what a restore undoes. After committing, check the pin: `git rev-parse HEAD^` must equal `commit_sha`; if it doesn't, correct `commit_sha` in a follow-up commit.

### Step 3 — Archive Directory Placement

The snapshot lives at:

```
.claude/support/retired/<feature-slug>/
├── manifest.json                    # required — see schema in .claude/support/retired/README.md
├── spec-excerpt.md                  # when the spec described the feature (Step 1)
├── <mirrored-original-paths>/       # the snapshot files, mirroring repo structure
│   ├── src/...
│   ├── .claude/commands/...
│   └── ...
```

**`<feature-slug>` naming convention:**
- kebab-case
- descriptive — encode what the feature is, not what number you assigned it
- examples: `legacy-checkout-flow`, `experiment-dashboard`, `pdf-export-route`
- anti-examples: `feature-1`, `retired-2026-04-29`, `foo`

The slug must match the manifest's `feature_slug` field and the directory name exactly.

### Step 4 — Spec Annotation (do NOT excise)

At the spec section originally describing the retired feature, **add a marker line** at the top of the section, through `/iterate` like any spec edit (DEC-016). Do **not** delete the section content.

**Pattern:**

```markdown
### 13.1 Checkout Flow

**Retired (2026-04-29)** — see `.claude/support/retired/legacy-checkout-flow/manifest.json`.

[original section content remains below, unchanged]
```

**Why keep the original content:**

Drift detection (per `.claude/support/reference/drift-reconciliation.md`) hashes each spec section. Excising the section reads as a substantial change: a deleted section suggests a version bump, and its tasks drop into the missing-section prompt. The marker is an annotation-only edit. It does change the section's hash, so `/work`'s drift check flags the section's tasks; keep them with `[K]` Keep, since the marker doesn't change what was built. The marker itself signals that the section is now informational/historical rather than a build target.

It also preserves the **historical scope** of the feature for anyone reading the spec retrospectively — they can see what was built without traversing git history.

If the retirement spans multiple spec sub-sections (a top-level section plus its acceptance criteria, plus a related cross-reference elsewhere), annotate **each** sub-section with the same marker. Cross-reference all of them from the manifest's `spec_excerpt_path` document so a reader following the pointer sees the full historical scope.

If the spec section content is later deemed *misleading* (e.g., describes a behavior that would be wrong if someone tried to rebuild against the current codebase), add a brief in-line note clarifying what's stale — but still don't excise.

### Step 5 — Discoverability

Retired features must surface in organizational memory so future-you can find them.

**Pattern: a "Retired Features" list in the dashboard's Notes card.** The card renders the sidecar's `user_notes` (`.claude/dashboard-state.json`), so the list is text in that field:

```markdown
**Retired Features:**
- **2026-04-29** — `<feature-title>` (`<feature-slug>`) — driving rationale. See `.claude/support/retired/<feature-slug>/manifest.json`.
```

**Why the Notes card:** scannability. One list shows every retirement at a glance instead of scattering them across the dashboard.

This rule **documents the pattern** — the orchestrator adds the entry to `user_notes` when a retirement lands (starting the list with the first one), then regenerates the dashboard. Retiring agents don't write the sidecar; they note the new manifest in their return report.

Decision records that drive a retirement link to the retirement entry via the manifest's optional `dashboard_decision_ref` field. The dashboard's `📋 Decisions` section continues to surface the decision in its own row; the Retired Features list is a parallel organizational-memory surface, not a duplicate of the decision log.

## Restore Path

A restore undoes the **retirement commit**: the commit that added the feature's manifest. Don't cherry-pick `commit_sha`: `git cherry-pick "$SHA"` replays that commit's own diff (whatever the last pre-retirement commit changed), not the feature.

```bash
SLUG=<feature-slug>
RETIRE=$(git log --diff-filter=A --format=%H -1 -- .claude/support/retired/$SLUG/manifest.json)
git diff --name-status "$RETIRE^" "$RETIRE" -- <affected_paths>  # the removals (deleted files as D)
git rev-parse "$RETIRE^"                                        # pin check: should equal commit_sha
```

- **Removal check.** If the diff shows none of the feature's removals, the manifest landed apart from the removal: set `RETIRE` to the commit that deleted the files (`git log --diff-filter=D --format=%H -1 -- <a deleted path>`, in the repository that held them). An empty `affected_paths` is a spec-only retirement: restoring it means removing the marker and the snapshot.
- **Pin check.** When `$RETIRE^` differs from `commit_sha`, trust `$RETIRE^` as the last-live state and say so.
- **Route.** `git show --stat "$RETIRE"` shows which manifests the commit added and what else it holds.

1. **Revert** (default) — `$RETIRE` retired only this feature: `git checkout -b restore/$SLUG && git revert --no-commit "$RETIRE"`. This undoes what the retirement changed: deleted files, fragments cut from shared files, dependency lines and the snapshot. Before committing, put back anything that isn't the feature (spec files, decision records, task files, the friction register, unrelated work) with `git checkout HEAD -- <path>`.
2. **Scoped inverse diff** — `$RETIRE` retired several features (or is mostly other work): on a `restore/$SLUG` branch, with `<paths>` = this feature's `affected_paths`, run `git diff --binary --no-ext-diff --no-color --src-prefix=a/ --dst-prefix=b/ "$RETIRE" "$RETIRE^" -- <paths> | git apply --3way`, then remove this feature's snapshot directory by hand. Keep the flags: without them a binary file, `diff.noprefix`, `diff.external` or `color.ui=always` makes `git apply` reject the whole patch. A shared file the other features were also cut from gets their fragments back too; delete those by hand.
3. **Files only, or no git history** — for each `affected_paths` entry absent from the tree, `git checkout "$RETIRE^" -- <path>` (no history: copy the snapshot file back). A path that still exists was partly retired: never copy over it; re-apply the removed fragment by hand from `git diff "$RETIRE^" "$RETIRE" -- <path>` (or the snapshot copy).

Every route ends the same way:
- The snapshot directory is gone: `git rm -rq .claude/support/retired/$SLUG` if it is still there (this also settles a revert conflict on a manifest edited after the retirement).
- Git has changed no spec file or decision record (both DEC-016-gated): if the revert or apply touched one, put it back with `git checkout HEAD -- <path>`: `.claude/spec_v*.md`, an archived copy under `.claude/support/previous_specifications/`, or `.claude/support/decisions/decision-*.md`. The marker comes out through `/iterate` (gotchas below); a decision change goes through `/research`.

Then check the gotchas and run the tests and build.

**Restore gotchas — check each before declaring the restore complete:**

- **Dependent helpers may have moved or refactored** since retirement. Restored files land at their original paths; if `src/lib/` has reorganized, the feature may import from paths that no longer exist. The manifest's `restore_notes` should call this out per-feature.
- **Tests may need updating** — test helpers, mock shapes, and snapshot fixtures rot independently of feature code. Plan to fix tests after the buildable-state landing.
- **Spec marker** — the "Retired (YYYY-MM-DD)" marker from Step 4 must leave the current spec, or the spec describes a live feature as retired (confusing drift detection and readers). Remove it through `/iterate` (`.claude/rules/spec-workflow.md § "Direct edits to spec, decision, and vision files"`), never by reverting: a revert edits the spec outside `/iterate`, and after a spec version change it edits the archived copy and leaves the current spec's marker in place.
- **Retired Features note** — remove the feature's entry from `user_notes` in `.claude/dashboard-state.json`, if there is one, and regenerate the dashboard.
- **Application state paths** — if the feature read or wrote project-level state files (foundation data, configs, datastore schemas), verify those paths still exist and the schema hasn't drifted. The manifest's `restore_notes` lists the paths the feature touched.
- **Dependencies removed at retirement** — a restored `package.json` line still needs `npm install`. If `package.json` isn't in `affected_paths`, routes 2 and 3 leave the line out: compare with `git show "$RETIRE^":package.json` and re-add it deliberately.
- **Later commits** — work since the retirement may have changed the same files; the revert and the `--3way` apply report that as conflicts. Resolve them against today's code rather than taking the old version wholesale.

A project that restores often may wrap these steps in its own `/restore <slug>` command (not template-shipped); prefer it when one exists in `.claude/commands/`.

## Out of Scope

- **Feature-flag-style runtime toggles.** If you need a flag, build a flag — the retirement workflow is the wrong tool.
- **Permanent deletion.** Use `git rm`. This workflow is overhead for the park-and-revisit case.
- **Maintaining shelved code against the evolving codebase.** Snapshots are frozen; they will not compile against `main` after enough drift. That's the trade — restoration is a deliberate act with a real cost.
- **Live monitoring of the retired surface.** Once retired, the feature has zero observability — no production tests, no error reporting, no analytics. It is gone from runtime.

## Edge Cases

### 1. The feature read or wrote application state

Application state (foundation data, datastore files, user configs) is **state**, not code. It does not move into the snapshot — it stays in its original location. The manifest's `restore_notes` lists the state paths the feature read or wrote.

On restoration, verify those paths still exist and that the schema hasn't drifted. If schema drift makes the original feature incompatible with the current state shape, the restore work expands to include schema migration — flag this in `restore_notes` for foreseeable cases.

### 2. The feature spans multiple files

Mirror **all** original paths in the snapshot. List **every** original path in `manifest.affected_paths[]`. Don't shortcut by listing only the entry-point file — restoration mechanics rely on the full enumeration.

### 3. The spec section has been merged with adjacent sections since the feature was authored

The spec excerpt captured at `commit_sha` (`<feature-slug>/spec-excerpt.md`) is the **historical truth**. The in-spec annotation marker (Step 4) handles forward references — it lives at whatever section the feature's content is currently in, and the marker says "see manifest" which points at the historical excerpt.

If the merge happened **after** retirement and the marker now lives in a section whose content has evolved, add a brief clarifying note alongside the marker so a reader doesn't conflate the current section content with the retired feature's behavior.

### 4. A dependent feature shares helpers the retired feature also used

This is a **shared helper** case. The helper is **not** retired — only the feature surface is. The helper continues to live in `src/lib/...` and serve the dependent feature.

Document this in the manifest's `restore_notes`: "Helpers `foo`, `bar` in `src/lib/baz/` are shared with `<other-feature>`; they were not retired and remain in tree. On restore, no helper-restoration work is needed."

If a helper IS exclusive to the retired feature and the retirement removes it from `src/lib/`, the snapshot must include it (mirroring the path), and `affected_paths[]` must list it.

### 5. The user wants permanent deletion (vs retirement)

That is a different operation. Just `git rm` the files, optionally remove the spec section, commit. This workflow is for "park and possibly revisit"; permanent deletion does not need a manifest, a snapshot, or a discoverability surface. Use plain git.

If a previously-retired feature is later **graduated to permanent deletion**, the snapshot can be removed (`git rm -r .claude/support/retired/<feature-slug>/`) and its Retired Features entry deleted from `user_notes`. The spec annotation marker can also be removed at that point, through `/iterate`. Document the graduation reason in the commit message.

## See Also

- **`.claude/support/retired/README.md`** — directory convention + manifest.json schema (sibling document to this rule; the schema lives there).
- **`.claude/support/reference/drift-reconciliation.md`** — how section fingerprints drive drift detection, and `[K]` Keep for annotation-only edits such as a retirement marker (why sections are marked, not excised: Step 4).
- **`.claude/commands/audit-coherence.md`** — the `retired-features` lens scans `.claude/support/retired/*/manifest.json` and flags retired features whose spec sections lack a retirement marker.
