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
- **Spec excerpt** — copy the spec section(s) describing the feature, captured at the retirement SHA. Save as `<feature-slug>/spec-excerpt.md` (referenced by `manifest.json::spec_excerpt_path`). This insulates the snapshot against later spec rewrites.
- **Dependent helpers / lib code** — anything exclusively owned by the feature.
- **Tests (recommended, optional)** — co-located unit / behavior tests so a buildable-state restoration can verify itself. If tests are excluded for size or staleness reasons, note this in `restore_notes`.

**What NOT to copy:**
- Shared helpers used by other features (they stay in place; `restore_notes` calls out shared dependencies).
- `node_modules`, build artifacts, generated files.
- User data the feature read or wrote (it's user data, not code; see *application state* edge case below).
- Tests for helpers the retired feature doesn't uniquely own.

**Mirror the original repo paths.** If the feature lives at `src/app/checkout/page.tsx`, the snapshot path is `<feature-slug>/src/app/checkout/page.tsx`. The mirror convention makes restoration via `cp -r` or cherry-pick mechanical.

### Step 2 — Commit Pin

Record the commit SHA at the moment of retirement. The SHA refers to the commit **immediately before retirement** — i.e., the **last commit where the feature was live** in the main branch. This directional convention matters: cherry-picking that SHA restores the feature to its last-shipping state.

```
manifest.commit_sha = git rev-parse HEAD   # AT THE LAST COMMIT WHERE THE FEATURE WAS LIVE
```

Run this command **before** the retirement commit lands (i.e., capture the SHA from `HEAD` while the feature is still in tree). The retirement commit itself removes the feature; you don't want the manifest pointing at the removal commit.

If you forget and capture the SHA after the retirement commit, recover it: `git log --oneline <removal-commit>~1 -1` gives the immediately-prior commit, which is the correct pin.

### Step 3 — Archive Directory Placement

The snapshot lives at:

```
.claude/support/retired/<feature-slug>/
├── manifest.json                    # required — see schema in .claude/support/retired/README.md
├── spec-excerpt.md                  # spec section(s) describing the feature, captured at SHA
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

At the spec section originally describing the retired feature, **add a marker line** at the top of the section. Do **not** delete the section content.

**Pattern:**

```markdown
### 13.1 Checkout Flow

**Retired (2026-04-29)** — see `.claude/support/retired/legacy-checkout-flow/manifest.json`.

[original section content remains below, unchanged]
```

**Why keep the original content:**

Drift detection (per `.claude/support/reference/drift-reconciliation.md`) hashes spec sections. Excising a section would register as a substantial change and trigger a version bump or reconciliation prompt for adjacent unchanged sections — noisy and incorrect. Keeping the content with a marker preserves section fingerprints; the marker itself is the signal that the section is now informational/historical rather than a build target.

It also preserves the **historical scope** of the feature for anyone reading the spec retrospectively — they can see what was built without traversing git history.

If the retirement spans multiple spec sub-sections (a top-level section plus its acceptance criteria, plus a related cross-reference elsewhere), annotate **each** sub-section with the same marker. Cross-reference all of them from the manifest's `spec_excerpt_path` document so a reader following the pointer sees the full historical scope.

If the spec section content is later deemed *misleading* (e.g., describes a behavior that would be wrong if someone tried to rebuild against the current codebase), add a brief in-line note clarifying what's stale — but still don't excise.

### Step 5 — Discoverability

Retired features must surface in organizational memory so future-you can find them.

**Pattern: a dedicated "Retired Features" sub-section in the dashboard's Notes section.** Render it like:

```markdown
### Retired Features

- **2026-04-29** — `<feature-title>` (`<feature-slug>`) — driving rationale. See `.claude/support/retired/<feature-slug>/manifest.json`.
```

**Why dashboard's Notes over inline phase notes:** scannability. A dedicated section gives a one-look list of every retirement; inline phase notes scatter retirements across the dashboard and the reader has to know which section to look in.

This rule **documents the pattern** — the actual sub-section is added by the orchestrator during dashboard regeneration when the first retirement lands. Retiring agents do not modify the dashboard structurally themselves; they note the new manifest in their return report and the orchestrator surfaces it at the next regen.

Decision records that drive a retirement link to the retirement entry via the manifest's optional `dashboard_decision_ref` field. The dashboard's `📋 Decisions` section continues to surface the decision in its own row; the "Retired Features" section is a parallel organizational-memory surface, not a duplicate of the decision log.

## Restore Path

Two routes. The manual cherry-pick is always available; a `/restore` command is a possible project-side capability.

### Manual cherry-pick (always available)

For a one-commit restore from the pinned SHA:

```bash
SHA=$(jq -r '.commit_sha' .claude/support/retired/<feature-slug>/manifest.json)
git checkout -b restore/<feature-slug>
git cherry-pick "$SHA"
# Resolve conflicts as the surrounding code has evolved.
# Run tests / build to verify a buildable state.
```

For a multi-file or selectively-restored case, copy snapshot files back into place:

```bash
SLUG=<feature-slug>
SNAPSHOT=.claude/support/retired/$SLUG
cp -r $SNAPSHOT/src/. src/
cp -r $SNAPSHOT/.claude/commands/. .claude/commands/   # if applicable
# Adjust any helpers per manifest.restore_notes.
# Revert the spec annotation marker (Step 4 of the retirement procedure).
# Rebuild + test.
```

**Common restore gotchas — always check before declaring restore complete:**

- **Dependent helpers may have moved or refactored** since retirement. The mirror-path copy lays files in their original locations; if `src/lib/` has reorganized, the restored feature may import from paths that no longer exist. The manifest's `restore_notes` should call this out per-feature.
- **Tests may need updating** — test helpers, mock shapes, and snapshot fixtures rot independently of feature code. Plan to fix tests after the buildable-state landing.
- **Spec annotation needs reverting** — the "Retired (YYYY-MM-DD)" marker added in Step 4 should be removed when the feature returns. (Don't forget; otherwise the spec describes a live feature as retired, which confuses both drift detection and future readers.)
- **Application state paths** — if the feature read or wrote project-level state files (foundation data, configs, datastore schemas), verify those paths still exist and the schema hasn't drifted. The manifest's `restore_notes` lists the paths the feature touched.
- **Dependencies removed at retirement** — if retirement removed `package.json` deps, `npm install` after the cherry-pick will not restore them automatically; review the pinned-SHA `package.json` and re-add deliberately.
- **The retirement commit itself** — the cherry-pick lands the feature, but the *retirement* commit that removed it is still in history. Anything that ran between retirement and restore (other commits) may need reconciliation in the restore branch. This is normal git, not a workflow gap.

### `/restore <slug>` command (project-side capability)

A project may choose to implement a higher-level wrapper that reads `manifest.json`, fetches the snapshot, opens a restore branch, and runs the cherry-pick + spec-annotation revert in one step. This is **not template-shipped** — projects that retire features regularly and want an ergonomic restore path can add it to their own `.claude/commands/`. If `/restore` exists in the project's `.claude/commands/`, prefer it over manual cherry-pick — it codifies the gotchas above so the restorer doesn't have to remember them.

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

The spec excerpt captured at the retirement SHA (`<feature-slug>/spec-excerpt.md`) is the **historical truth**. The in-spec annotation marker (Step 4) handles forward references — it lives at whatever section the feature's content is currently in, and the marker says "see manifest" which points at the historical excerpt.

If the merge happened **after** retirement and the marker now lives in a section whose content has evolved, add a brief clarifying note alongside the marker so a reader doesn't conflate the current section content with the retired feature's behavior.

### 4. A dependent feature shares helpers the retired feature also used

This is a **shared helper** case. The helper is **not** retired — only the feature surface is. The helper continues to live in `src/lib/...` and serve the dependent feature.

Document this in the manifest's `restore_notes`: "Helpers `foo`, `bar` in `src/lib/baz/` are shared with `<other-feature>`; they were not retired and remain in tree. On restore, no helper-restoration work is needed."

If a helper IS exclusive to the retired feature and the retirement removes it from `src/lib/`, the snapshot must include it (mirroring the path), and `affected_paths[]` must list it.

### 5. The user wants permanent deletion (vs retirement)

That is a different operation. Just `git rm` the files, optionally remove the spec section, commit. This workflow is for "park and possibly revisit"; permanent deletion does not need a manifest, a snapshot, or a discoverability surface. Use plain git.

If a previously-retired feature is later **graduated to permanent deletion**, the snapshot can be removed (`git rm -r .claude/support/retired/<feature-slug>/`) and the dashboard's "Retired Features" entry deleted. The spec annotation marker can also be removed at that point. Document the graduation reason in the commit message.

## See Also

- **`.claude/support/retired/README.md`** — directory convention + manifest.json schema (sibling document to this rule; the schema lives there).
- **`.claude/support/reference/drift-reconciliation.md`** — explains why spec sections must not be excised at retirement (section_fingerprint hashes drive drift detection).
- **`.claude/commands/audit-coherence.md`** — the `retired-features` lens scans `.claude/support/retired/*/manifest.json` and flags retired features whose spec sections lack a retirement marker.
