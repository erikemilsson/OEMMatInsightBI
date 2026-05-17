# Retired Features

Frozen snapshots of features that have been retired from the live codebase but are preserved in case they're revived.

This directory is the **archive surface** of the feature-retirement workflow. The procedure that lands snapshots here lives in `.claude/rules/feature-retirement.md` (canonical rule + step-by-step procedure + restore path). This README documents the **directory convention + manifest schema** — what a snapshot looks like once it's here.

## Directory Convention

Each retired feature lives in its own kebab-case sub-directory:

```
.claude/support/retired/
├── README.md                                    # this file
├── <feature-slug>/
│   ├── manifest.json                            # required — schema below
│   ├── spec-excerpt.md                          # spec section(s) at retirement SHA
│   └── <mirrored-original-paths>/               # snapshot files
│       ├── src/...
│       ├── .claude/commands/...
│       └── ...
└── <another-feature-slug>/
    └── ...
```

### `<feature-slug>` rules

- kebab-case (lowercase, hyphens between words)
- descriptive — encode what the feature is, not when you retired it or which number you assigned
- examples: `legacy-checkout-flow`, `experiment-dashboard`, `pdf-export-route`
- anti-examples: `feature-1`, `retired-2026-04-29`, `tmp`, `foo`

The slug **must match** `manifest.json::feature_slug` and the parent directory name exactly.

### Mirror-path convention

Snapshot files mirror their original repo paths inside the `<feature-slug>/` directory. If the feature's source-of-truth was at:

```
src/app/checkout/page.tsx
```

then the snapshot file lives at:

```
.claude/support/retired/<feature-slug>/src/app/checkout/page.tsx
```

The mirror convention exists to make restoration mechanical:

```bash
cp -r .claude/support/retired/<feature-slug>/src/. src/
cp -r .claude/support/retired/<feature-slug>/.claude/. .claude/
```

drops the snapshot back into place at the original paths. (Cherry-picking the pinned commit SHA is the other restoration route — see the rule file.)

### What lives in a snapshot

See `.claude/rules/feature-retirement.md` § *Step 1 — Snapshot Capture* for the full list. In brief: routes, API handlers, UI components, slash commands, lib helpers exclusively owned by the feature, the spec excerpt, and (recommended) co-located tests. Shared helpers, application state, build artifacts, and `node_modules` are explicitly excluded.

## `manifest.json` Schema

Every retired feature includes a `manifest.json` at the root of its sub-directory. The manifest is the feature's record-of-retirement: it captures the SHA pin, the rationale, the affected paths, and the restoration cost estimate.

### Schema

| Field | Type | Required | Description |
|---|---|---|---|
| `feature_slug` | string (kebab-case) | yes | Must match the parent directory name. |
| `feature_title` | string | yes | Human-readable title. Typically the user-facing surface name + a short qualifier. |
| `retirement_date` | string (ISO date `YYYY-MM-DD`) | yes | The date the retirement commit landed in `main`. |
| `commit_sha` | string (40-char SHA) | yes | The commit SHA **immediately before retirement** — i.e., the **last commit where the feature was live in main**. This is the SHA you cherry-pick to restore the feature. |
| `rationale` | string (one paragraph) | yes | Why the feature was retired. Reference the driving decision record if one exists. |
| `restore_cost_estimate` | enum: `S` \| `M` \| `L` | yes | Rough estimate of restoration effort. **S** = under 1 hour (clean cherry-pick + small fixups). **M** = 1–4 hours (dependency reinstall, test fixes, helper reconciliation). **L** = full day or more (significant lib drift, schema migration, multiple decision-record reversals). |
| `affected_paths` | string[] (array of repo-relative paths) | yes | The original repo paths of files now in the snapshot. Lists every file, not just the entry point. |
| `spec_excerpt_path` | string | yes | Relative path inside the snapshot to a copy of the spec section(s) describing the feature, captured at the retirement SHA. Conventionally `"spec-excerpt.md"`. |
| `restore_notes` | string | yes | Non-obvious gotchas: dependent helpers that may have moved, dependencies removed at retirement, application state paths the feature read or wrote, schema drift hazards. Be concrete — this is what saves a future restorer from rediscovering pain. |
| `successor_feature` | string \| null | optional | The slug of a feature that replaced this one, if any. `null` if no successor. |
| `dashboard_decision_ref` | string \| null | optional | The decision-record ID (e.g., `"DEC-055"`) that drove the retirement, if one exists. The dashboard's Retired Features sub-section can use this to cross-reference the decision log. |

### Field-by-field guidance

**`commit_sha` directional convention.** The SHA is the **last commit where the feature was live**, not the retirement commit itself. Capture it via `git rev-parse HEAD` *before* the retirement commit lands. If you forget, `git log --oneline <retirement-commit>~1 -1` recovers it.

**`restore_cost_estimate` calibration:**
- **S** — feature is small, dependencies are unchanged, no schema drift expected. Cherry-pick + small spec-marker revert + 30 minutes of test fixes.
- **M** — middle ground. Some dependencies were removed at retirement; tests will need updating; one or two helpers may have moved.
- **L** — package.json deps were removed (e.g., a heavyweight runtime framework); decision records were marked superseded; state schema may have drifted; multiple spec sections need marker reverts.

When in doubt, **estimate up** (M instead of S, L instead of M). The estimate is a planning hint, not a contract.

**`rationale`** should reference the decision record (if one exists) and summarize the *why* in one or two sentences. Don't restate the entire decision — point at the record and let it carry the weight.

**`restore_notes`** is the high-leverage field. Future-you will thank past-you for being concrete. Cover:
- Dependencies removed at retirement (re-install required).
- Application state paths the feature read or wrote (verify schema on restore).
- Helpers shared with other features (still in tree, no restore work needed) vs. helpers exclusive to this feature (in the snapshot, must be restored).
- Decision records that became `superseded` because of this retirement (review before restoring).
- Tests excluded from the snapshot, if any, and why.
- Spec annotation markers that need to be reverted (Step 4 of the retirement procedure).

**`successor_feature`** — set to the slug of the replacement feature when retirement is paired with a new surface. Otherwise `null`.

**`dashboard_decision_ref`** — when a decision record drove the retirement, listing it here lets the dashboard's Retired Features section cross-link to the decision row in the Decisions section.

## Worked Example

A minimum-viable manifest illustrating the required fields:

```json
{
  "feature_slug": "legacy-checkout-flow",
  "feature_title": "Legacy checkout flow (pre-redesign)",
  "retirement_date": "2026-04-29",
  "commit_sha": "<40-char SHA of the last commit where the feature was live in main>",
  "rationale": "Replaced by the redesigned checkout surface (see DEC-NNN). Old flow's session-state assumptions made it brittle to the new state machine; cleaner to retire and restore on demand than to maintain in parallel.",
  "restore_cost_estimate": "M",
  "affected_paths": [
    "src/app/checkout/page.tsx",
    "src/app/checkout/types.ts",
    "src/app/api/checkout/route.ts",
    "src/components/checkout/PaymentForm.tsx",
    "src/components/checkout/OrderSummary.tsx",
    "src/lib/checkout/session.ts"
  ],
  "spec_excerpt_path": "spec-excerpt.md",
  "restore_notes": "Restoration cost is M because: (1) the redesigned checkout removed `stripe-checkout` from package.json (re-install required). (2) The spec § 14 'Retired (2026-04-29)' marker needs to be reverted. (3) src/lib/checkout/session.ts is exclusive to this flow; the redesigned flow uses src/lib/checkout/state-machine.ts. No shared helpers were retired. (4) Tests in __tests__/checkout/ were retired alongside; restoration should validate that the test helpers still compile against the current testing-library version.",
  "successor_feature": "redesigned-checkout-flow",
  "dashboard_decision_ref": "DEC-NNN"
}
```

Notice:
- `commit_sha` placeholder; the retiring agent captures the actual 40-char SHA.
- `restore_cost_estimate: "M"` because of removed dep + spec-marker revert work.
- `restore_notes` is concrete — every gotcha that would slow down a restore is named.
- `successor_feature` and `dashboard_decision_ref` are populated when applicable.

## See Also

- **`.claude/rules/feature-retirement.md`** — the canonical rule (when to retire, how, restore path).
- **`.claude/commands/audit-coherence.md`** — the `retired-features` lens scans manifests in this directory and flags retired features whose spec sections lack a retirement marker.
- **`.claude/support/reference/drift-reconciliation.md`** — explains why spec sections must not be excised at retirement.
