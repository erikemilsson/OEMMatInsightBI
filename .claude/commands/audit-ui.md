---
applies_when:
  package_json_has_dep: ["next", "react", "vue", "svelte", "vite", "@angular/core", "remix", "astro", "solid-js"]
estimated_runtime: "5-7 min"
prerequisites: ["dev server reachable at {url}"]
---

# UI Audit Command

Walks the running web app with Playwright, captures per-page artifacts, then dispatches parallel sub-agents — one per quality lens — to evaluate the artifacts. Synthesizes a ranked report and exposes a `promote` mode that lifts findings into `/feedback`.

Bias gain: each lens agent has fresh context and never sees other lenses' output, so findings on one axis don't anchor the next.

This command is part of the audit family (proposal: `template-maintenance/audit-command-family-proposal.md`). It complements `/audit-coherence` (spec/decision/path drift) — UI audit catches user-facing surface quality issues that don't show up in spec or filesystem inspection.

**Hard rule (Component 6 of proposal):** the spec, decision records, and vision documents are read-only outside `/iterate`. Any finding whose `files_to_touch` includes a spec/decision/vision file path is auto-classified `kind: decision` — the synthesizer enforces this. Most UI audit findings are `decision` kind anyway (copy changes, IA decisions), so the hard rule cleanly applies.

**Background-session note:** this command writes only to a gitignored audit dir under `.claude/support/audits/{cmd}-{ts}/`. **Do not enter a worktree before running it** — the worktree dance is wasted overhead and severs access to whatever gitignored state the lenses inspect alongside the running dev server. Run in the main working tree (`cwd` outside `.claude/worktrees/`). The audit dir's timestamp prevents same-second collisions across parallel sessions.

---

## Usage

```
/audit-ui                              # walk + lenses + synth (desktop)
/audit-ui --mobile                     # mobile viewport (390×844), enables `mobile` lens
/audit-ui [url]                        # entry URL (default reads from .claude/audit-ui.config.json or http://localhost:3000)
/audit-ui --vector x,y,z               # run only listed lenses (default: all 7 + mobile)
/audit-ui --depth shallow              # one snapshot per route; skip tabs/expanders
/audit-ui --depth full                 # default — also walks every tab + expander
/audit-ui triage [audit-ts]            # interactive walker: per-finding fix/promote/dismiss (default audit-ts: latest)
/audit-ui promote {audit-ts}           # promote ticked findings → feedback.md
/audit-ui promote {audit-ts} --all     # bulk promote everything in the report
/audit-ui promote {audit-ts} F-01,F-07 # promote specific IDs
/audit-ui fix {audit-ts} {F-ID}        # apply a single bundle-eligible finding inline
```

Stage 5 (`/health-check` Part 6) will dispatch this command automatically based on `applies_when` (web framework deps detected in package.json). Until then, invoke directly.

---

## Vectors

Seven default lenses. The `mobile` lens is only meaningful with `--mobile`.

| Lens | Catches |
|------|---------|
| `gaps` | empty `—` rows, dev placeholders, raw enums, broken routes, exposed filenames |
| `duplications` | same content/data rendered in 2+ places (cross-page or same-page) |
| `rambling` | walls of text, 50-word headings, boilerplate templates, leads buried after 3 clauses |
| `affordance` | dead-end controls, opaque toggles, status pills with no action, expanders showing internal jargon |
| `consistency` | same concept rendered differently — date formats, terminology, badge styles, section numbering |
| `discoverability` | features only reachable by URL, broken empty-state CTAs, redirect-to-wrong-tab, orphaned routes |
| `trust` | counts that don't match reality, filters with no items, claims that exaggerate |
| `mobile` | (only with `--mobile`) touch targets <44px, horizontal scroll, fixed-width content, sidebar reach |

---

## Project config (optional)

`.claude/audit-ui.config.json` — overrides defaults when present:

```json
{
  "default_url": "http://localhost:3000",
  "viewport_desktop": "1440x900",
  "viewport_mobile": "390x844",
  "surface_buckets": {
    "Authentication": ["/auth", "/login", "/signup", "/logout"],
    "Dashboard": ["/dashboard", "/home"],
    "Settings": ["/settings", "/profile", "/account"],
    "Content": ["/posts", "/articles", "/library"]
  },
  "skip_routes": ["/api/", "/admin/internal/"]
}
```

**Field reference:**
- `default_url` — fallback when no `[url]` arg passed. Defaults to `http://localhost:3000`.
- `viewport_desktop` / `viewport_mobile` — `WIDTHxHEIGHT`. Defaults: `1440x900` / `390x844`.
- `surface_buckets` — maps human-readable bucket names to URL-prefix arrays. Used by the synthesizer to group findings by surface (instead of dumping all findings as one flat list). If absent, synthesizer defaults to top-level URL prefix grouping (each `/foo` becomes a `Foo` bucket).
- `skip_routes` — URL prefixes to skip during route discovery. Defaults: `/api/`, `[id]` segments.

If the file is absent, the audit falls back to all defaults.

---

## File layout

```
.claude/support/audits/ui-{YYYY-MM-DD-HHmm}/
├── routes.json                # URL → status, redirect, tabs walked, console errors
├── pages/
│   ├── {slug}.yaml            # accessibility snapshot
│   ├── {slug}.png             # full-page screenshot
│   ├── {slug}.console.log     # console messages at capture time
│   ├── {slug}.meta.json       # title, h1, em-dash count, snake_case strings, viewport overflow
│   ├── {slug}__tab-{name}.yaml          # one set per tab
│   └── {slug}__expanded-{label}.yaml    # one set per "Show all"/"▸" expander
├── lenses/
│   ├── gaps.md
│   ├── duplications.md
│   ├── rambling.md
│   ├── affordance.md
│   ├── consistency.md
│   ├── discoverability.md
│   ├── trust.md
│   └── mobile.md              # only if --mobile
├── synth-input.md             # concatenated lens output passed to synthesizer
├── findings.md                # final ranked report + Promote checklist
└── digest.json                # machine-readable digest (per audit family schema)
```

Project rule (DEC-004): sub-agents cannot write to `.claude/`. The orchestrator (this command, running in the main conversation) handles all writes. Sub-agents return their report as text; the orchestrator saves it.

---

## Workflow

### Phase 1 — Walk (orchestrator drives Playwright directly)

Pre-flight:
1. Read `.claude/audit-ui.config.json` if present; otherwise use defaults.
2. Confirm dev server is reachable at `{url}` (resolved from arg → config → default). If not, **ask the user to start it** — never start dev servers from Claude (per `.claude/rules/agents.md` § "Behavioral Rules").
3. Compute artifact dir: `.claude/support/audits/ui-{YYYY-MM-DD-HHmm}/`. Create it.
4. Write `meta.json` with run config: viewport, depth, vectors, entry URL, timestamp, config used.

Set viewport from config (or defaults: desktop `1440 × 900`, mobile `390 × 844`).

Discover routes:
1. Crawl `<a>` hrefs from the sidebar / nav at `{url}/`.
2. Probe top-level folders under the project's framework-conventional pages directory (Next.js: `src/app/`; Remix/Astro: `app/routes/` or `src/pages/`; Vue/Vite: `src/views/`). Skip `api/` and `[id]` / `[...]` segments. Hit each `/foo` and record HTTP status. Apply `skip_routes` filter from config.
3. Probe the entry URL itself.
4. For each URL: record final URL after redirects, status, console errors.

For each reachable page (200 status):
1. `browser_navigate` → `{url}/{path}`
2. wait for network idle (≤2s)
3. `browser_snapshot` → `pages/{slug}.yaml`
4. `browser_take_screenshot fullPage:true` → `pages/{slug}.png`
5. `browser_console_messages` → `pages/{slug}.console.log`
6. `browser_evaluate` capturing meta → `pages/{slug}.meta.json`. Scope queries to `<main>` so the sidebar / framework `<script>` / inline `<style>` don't pollute results:
   ```js
   () => {
     const main = document.querySelector('main') || document.body;
     const inMain = sel => Array.from(main.querySelectorAll(sel));
     const isText = el => el.children.length === 0
       && el.tagName !== 'SCRIPT'
       && el.tagName !== 'STYLE';
     return {
       url: location.pathname,
       title: document.title,
       h1: main.querySelector('h1')?.textContent.trim(),
       h2s: inMain('h2,h3').slice(0, 30).map(h => h.textContent.trim()),
       emDashRows: inMain('*')
         .filter(el => isText(el) && el.textContent.trim() === '—').length,
       placeholders: inMain('*')
         .filter(el => isText(el) &&
           /renderer pending|not found|unavailable|coming soon|undefined|\[\w+\]/i.test(el.textContent))
         .map(el => el.textContent.trim().slice(0, 200)),
       snakeCaseValues: inMain('*')
         .filter(el => isText(el) && /^[a-z]+(_[a-z]+){1,}$/.test(el.textContent.trim()))
         .map(el => el.textContent.trim()),
       fileRefs: inMain('*')
         .filter(el => isText(el)
           && /\b\w+\.(json|md|tsx?|jsx?|py|rb)\b/.test(el.textContent)
           && el.textContent.length < 300)
         .map(el => el.textContent.trim().slice(0, 200)),
       registryKeySuffixes: inMain('*')
         .filter(el => isText(el) && /^· [a-z]+(_[a-z]+)+$/.test(el.textContent.trim()))
         .map(el => el.textContent.trim()),
       viewportOverflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
       tabs: Array.from(document.querySelectorAll('[role="tab"], [role="tablist"] button'))
         .map(t => t.textContent.trim()),
       smallTouchTargets: Array.from(document.querySelectorAll('button, a, [role="button"]'))
         .map(el => {
           const r = el.getBoundingClientRect();
           return { text: el.textContent.trim().slice(0, 40), w: Math.round(r.width), h: Math.round(r.height) };
         })
         .filter(x => x.w > 0 && (x.w < 44 || x.h < 44)),
       bodyTextLength: main.textContent.length
     };
   }
   ```

   The scoping prevents three first-run bugs: `h1` previously matched sidebar headings; `fileRefs` matched framework JS in `<script>` tags; `placeholders` missed bracketed type names.

For each tab/sub-tab found in step 6:
1. Click tab.
2. Repeat snapshot + screenshot + console + meta into `pages/{slug}__tab-{name}.{ext}`.

For each `Show all`/`▸ Show`/`▾`-style expander on the page (after tabs):
1. Click expander.
2. Single snapshot into `pages/{slug}__expanded-{label}.yaml`.
3. Re-collapse before moving on.

Timebox: walker should complete within 120s for ~12 routes × 3 tabs each. If a navigation hangs >5s, skip and record as `walk-error` in `routes.json`.

When done:
1. Write `routes.json` mapping every probed URL to `{ status, redirectedTo, slug, tabsWalked, consoleErrorCount, walkError }`.
2. Close the browser.

### Phase 2 — Lenses (N parallel sub-agents)

Spawn N sub-agents in a **single Task tool message** so they run concurrently. Each:
- Runs as `general-purpose` agent (per `.claude/rules/agents.md` § "Dispatch Convention")
- Receives the artifact dir path + ONLY its single lens prompt
- Never sees other lenses' output
- Returns markdown formatted per the **Lens output format** below

Orchestrator:
1. Collect each agent's returned text.
2. Write to `lenses/{vector}.md`.
3. Concatenate all into `synth-input.md` for Phase 3.

If `--vector` is set, run only those lenses; if unset, run all that apply (skip `mobile` unless `--mobile`).

### Phase 3 — Synthesize

Spawn one general-purpose agent with:
- The path to `lenses/`, `routes.json`, and `pages/*.meta.json`
- Project config from `meta.json` (surface_buckets if present)
- The **Synthesizer prompt** below
- Instruction to return BOTH `findings.md` (full report) AND `digest.json` (audit family schema)

Orchestrator writes both to disk and prints a 10-line summary to chat:

```
UI audit complete · {desktop|iPhone} · {N} routes · {raw} → {clustered} findings
Bundle-eligible: {K} · Promote-eligible: {L} · Deduped to pending: {Z}
Report:  .claude/support/audits/ui-{ts}/findings.md
Digest:  .claude/support/audits/ui-{ts}/digest.json

Top 5:
  1. {title} ({kind} · {effort} · {impact})
  2. ...

{N} high-signal items (3+ lenses agreed). {M} routes 404.
Promote with: /audit-ui promote {ts}
```

(Stage 6 has shipped — `bundle-eligible` findings surface on the dashboard's `🔍 Audit Findings` section with the inline `[Fix it]` token; other kinds render with an italicized kind annotation. Stage 7 batch UX remains deferred per DEC-013 Q4. Promote/Dismiss are available via tick + `/audit-ui promote {audit-ts}` and natural-language-to-Claude respectively — not rendered per-item; see `dashboard-regeneration.md` § "Audit Findings sub-section". The inline summary + manual review remains a complementary surface.)

### Promote mode

`/audit-ui promote {audit-ts} [--all | F-IDs]`

1. Read `audit-{ts}/findings.md`. Find the `## Promote to feedback` section.
2. Determine selection:
   - `--all` → all `F-NN` in the report
   - explicit IDs → only those
   - default → only ticked checkboxes (`- [x] F-NN — ...`)
3. For each selected finding, read its full body from `findings.md`.
4. Read `.claude/support/feedback/feedback.md` and `.claude/support/feedback/archive.md`. Compute next `FB-NNN`.
5. **Dedupe pass.** For each selection, scan both feedback files for entries whose `**Source:**` line references the same audit (or any prior audit) AND whose title fuzzy-matches (≥0.8 token overlap) OR whose `**Where:**` references the same surface. For each match, prompt the user:
   - `[S] Skip` — already captured as FB-NNN
   - `[U] Supersede` — close existing, create new with `**Supersedes:** FB-NNN`
   - `[M] Merge` — append this finding's evidence to existing entry's body
   - `[N] New anyway` — proceed without dedupe
6. For each non-deduped selection, append to `feedback.md` an entry shaped like:
   ```markdown
   ## FB-NNN: {finding title}

   **Status:** new
   **Captured:** {today YYYY-MM-DD}
   **Source:** audit-ui-{audit-ts} {F-ID}
   **Kind:** {fix | decision | design}
   **Lenses:** {comma-separated lens names}
   **Severity:** {high | med | low}
   **Effort:** {S | M | L} · **Impact:** {S | M | L}

   **Where:** {from finding}

   **Evidence:** {from finding}

   **Why it matters:** {from finding}

   **Fix candidate:** {from finding}
   ```
7. Update `digest.json` in place: set `items[i].status = "promoted"`, `items[i].resolved_by = {kind: "promote_fb", ref: "FB-NNN", at: now}`.
8. For any friction register entries cited by promoted findings: update `friction.jsonl` in place to mark `status: resolved`, `resolved_by: {kind: "promote_fb", ref: "FB-NNN", at: now}` per `.claude/support/reference/friction-register.md` § "Status update protocol".
9. Update `findings.md` in place: replace `- [x] F-NN — title` with `- [x] F-NN → FB-NNN promoted {date}`.
10. Print summary:
    ```
    Promoted {N} findings → FB-{first}…FB-{last}
    Skipped {M} (deduped)
    Run /feedback review to triage.
    ```

The existing `/feedback review` → `/iterate` flow is unchanged. The audit just produces feedback-shaped artifacts.

### Fix mode (bundle-eligible only — DEC-013 Option C)

`/audit-ui fix {audit-ts} {F-ID}` — apply a single bundle-eligible finding inline.

Available only for findings with `kind: bundle-eligible`. Other kinds (`fix-eligible`, `decision`, `design`) require manual review or `/iterate` routing — see kind-availability table in `.claude/support/reference/audit-fix-workflow.md` § "Per-kind action availability".

**Mechanism:** see canonical reference at `.claude/support/reference/audit-fix-workflow.md` § "Action protocol — Stage 6 (Option C per DEC-013)" / "[Fix it] — inline apply (bundle-eligible only)". In short:

1. Read finding from this audit's `digest.json` + `findings.md#{F-ID}`
2. Verify kind is `bundle-eligible` (refuse with kind-specific message otherwise)
3. Verify finding `status == "pending"` (not already resolved/dismissed/promoted)
4. Re-read cited `source_anchors[]` / `files_to_touch[]` to verify finding's claim still holds (refuse if stale)
5. Re-verify hard-exclusion (no spec/decision/vision in `files_to_touch[]` — defense-in-depth)
6. Show concrete change + ask single approval
7. On approval: apply, single commit `audit-fix: {F-ID} — {summary}`, update `digest.json` + `friction.jsonl`

For UI audits, bundle-eligible findings are rare — most UI fixes need copy/IA decisions and route via `[Promote to FB]` → `/iterate`. The typical bundle-eligible UI case is dead-link removal where the link target is a route the spec also dropped, or deletion of a single orphan component file.

`/audit-ui fix latest {F-ID}` — convenience: resolves "latest" to the newest `ui-*` audit dir by `ran_at`.

### Triage mode

`/audit-ui triage [audit-ts]` — interactive walker through the audit's pending findings.

The preferred entry point when a UI audit has multiple pending findings. Walker iterates each pending non-dismissed finding, presents its `description` + kind + kind-conditional actions, dispatches the user's choice (Fix it / Promote / Dismiss / Skip / Quit), and continues to the next. Closes the dashboard-tick → CLI re-specification courier pattern and the audit-name memory burden (FB-006 sub-issues 1+2). Parallel structure to `/audit-coherence triage` — see `commands/audit-coherence.md § "Triage mode"` for the canonical algorithm.

**Default for `audit-ts`:** `latest` — resolves to the newest `ui-*` audit dir by `ran_at` (same resolution as `/audit-ui fix latest`).

**Algorithm:** identical to `/audit-coherence triage` § "Algorithm" with these substitutions:
- Audit dir glob: `.claude/support/audits/ui-*/` (instead of `coherence-*/`).
- Finding ID prefix: `F-NN` (instead of `C-NN`).
- Empty-state messages: `No pending findings in latest ui audit.` / `No ui audit has run in this project yet. Run /audit-ui first.`

**Per-kind action gates:** same as `/audit-coherence triage`. For UI audits, most findings are `decision` or `design` kind (copy/IA changes); `bundle-eligible` is rare (typical case: dead-link removal where the target route is also spec-dropped, or deletion of a single orphan component file). The kind-conditional gate works identically — `[F]ix it` is presented only for `bundle-eligible` items.

**State mutations:** same canonical dispatch (no divergence):
- Fix it → `audit-fix-workflow.md § "[Fix it] — inline apply"` (single commit `audit-fix: {F-ID} — {summary}`; `digest.json` + `friction.jsonl` cascades).
- Promote → `### Promote mode` above (compute next `FB-NNN`, dedupe, append `feedback.md`; cascades).
- Dismiss → `audit-fix-workflow.md § "[Dismiss]"` (sidecar `dismissed_ids[]` + `digest.json status: dismissed`).
- Skip → no mutation.

**Edge cases:** identical to `/audit-coherence triage § "Edge cases"`. Title fallback for pre-v3.18.0 digests; parallel-session collision caveat; per-audit-family scope (no unified `/triage`); re-running `/audit-ui` mid-triage decouples the new digest from in-flight walker state.

`/audit-ui triage latest` (explicit `latest` keyword) is equivalent to the no-arg form.

---

## Walker playbook (orchestrator self-instructions)

When this command is invoked without `promote`:

1. **Pre-flight.** Curl the entry URL. If the connection fails or returns 5xx, print:
   ```
   Dev server unreachable at {url}.
   Start it (e.g., `npm run dev`), then re-run /audit-ui.
   ```
   and stop. Do NOT attempt to start the server.
2. **Track prior kills.** If the user killed a dev server in this session, do not re-probe it without explicit confirmation (`.claude/rules/agents.md` § "Behavioral Rules").
3. **Default depth is `full`.** Run shallow only if explicitly requested.
4. **Be deterministic about slugs.** `slug = path.replace(/^\/+|\/+$/g, '').replace(/\//g, '_') || 'root'`. Tab names: lowercased, spaces → `-`, non-alphanumerics dropped.
5. **One browser session for the whole walk.** Don't close and reopen between pages — state leaks (auth, widget cache) are part of the audit's reality. **MCP-and-parallel-execution rule** (per `.claude/rules/agents.md`): the walker is the orchestrator, not a sub-agent — Playwright MCP cannot be safely fanned out across parallel agents.
6. **Capture mobile menu state on `--mobile`.** Before tab-walking, look for hamburger / menu button. If sidebar is hidden behind it, record that fact in `routes.json` under `mobileMenu: { found: true, opensVia: '...' }`. The mobile lens uses this.
7. **Don't interact beyond clicks.** No form fills, no file uploads. The audit reads existing state; it doesn't author new content.

---

## Lens prompts

Each lens prompt below is passed to a `general-purpose` agent. Replace `{ARTIFACT_DIR}` with the absolute path. The orchestrator passes the same prompt verbatim plus the dir.

### Lens output format (all lenses use this)

```markdown
# Lens: {lens-name}

Findings: {N}

## F-{lens-prefix}-01
- **Title:** {short title, 8 words max}
- **Severity:** high | med | low
- **Page:** {slug, plus tab/state if applicable}
- **Element:** {one of: snapshot ref like e123, CSS selector, or ≤80-char quoted text}
- **Evidence:** {2-4 lines — quote the actual text or describe the actual DOM. Avoid paraphrase.}
- **What:** {one sentence stating the issue}
- **Why:** {one sentence stating why it matters}
- **Suggested fix:** {one sentence — copy edit, hide row, refactor, etc.}
- **Suggested kind:** fix | decision | design
- **Files to touch (potential fix):** {best-guess file paths the fix would modify; CRITICAL for synthesizer kind classification — see hard rule}

## F-{lens-prefix}-02
...
```

`lens-prefix` = first three letters of the lens name (e.g. `gap`, `dup`, `ram`, `aff`, `con`, `dis`, `tru`, `mob`).

If the lens has no findings:
```markdown
# Lens: {lens-name}

Findings: 0

(No findings on this axis.)
```

---

### Lens 1 — `gaps`

```
You are auditing a UI for the GAPS lens only.

Read all files under {ARTIFACT_DIR}/pages/ and {ARTIFACT_DIR}/routes.json.
You may also read {ARTIFACT_DIR}/pages/*.meta.json which lists em-dash rows,
placeholders, snake_case values, and exposed file refs already detected by
the walker.

You are NOT looking at: rambling copy, duplication, inconsistency,
discoverability, claim accuracy, mobile fit. Other lenses cover those.

What counts as a finding for THIS lens:
1. UI rows rendering only an em-dash ("—") — flag in clusters per page-section.
   One finding per section, not one per row. Note the count.
2. Dev / template placeholder text leaking to UI:
   "renderer pending", "report not found", "unavailable",
   square-bracketed type names like "[palette]", "coming soon",
   filenames in body copy ("color-loves.json", "shopping.json").
3. Broken routes — folder exists but page returns 404 or React error.
4. Required onboarding fields shown blank in profile views.
5. Raw enum / snake_case values shown to user
   ("very_dark_brown", "weekly_few", "splurge_thrift_mix").
   The walker pre-detected these in meta.json — confirm by reading the
   surrounding label so you can describe it well.
6. Internal registry-key suffixes shown in checkbox lists
   ("· identity_basics", "· measurements_fit").

What does NOT count:
- Heading too long, copy too dense → that's "rambling".
- Same content rendered twice → that's "duplications".
- Different rendering of same concept → that's "consistency".
- Feature unreachable by IA → that's "discoverability".

Be terse, evidence-first, and quote the actual text. Use the output format
specified by the orchestrator. Set `Files to touch (potential fix)` to your
best guess of which source file would resolve the issue (e.g., a component
file, a copy file, a config file). If the fix would touch the spec or a
decision record, list the spec/decision file path — the synthesizer will
then auto-classify the finding as `kind: decision`.
```

### Lens 2 — `duplications`

```
You are auditing a UI for the DUPLICATIONS lens only.

Read {ARTIFACT_DIR}/pages/ and {ARTIFACT_DIR}/routes.json.

What counts:
1. Identical or near-identical lists/cards rendered in 2+ surfaces
   (e.g., the same priority list on /a and /b).
2. Same data block rendered twice on the SAME page in different framings
   (e.g., a status pill plus a banner plus a header all stating the same thing).
3. Palette/swatch/legend rendered both interactively (toggle) and statically
   (full list) on one page.
4. Item label that just restates accompanying visuals
   (e.g., "Charcoal Blazer + ..." next to thumbnails of Charcoal Blazer + ...).
5. Hint or guidance line copy-pasted across N sibling sections instead of
   stated once at the parent.

What does NOT count:
- Different rendering of same concept (date formats, terminology drift)
  → "consistency".
- Boilerplate phrasing repeated per row → "rambling".
- A feature appearing once but in the wrong place → "discoverability".

For each finding, quote ALL surfaces the duplicate appears on (not just one).
Severity scales with how often it repeats and how prominent each instance is.
Set `Files to touch (potential fix)` to your best guess.
```

### Lens 3 — `rambling`

```
You are auditing a UI for the RAMBLING / NOT-VALUE-FIRST lens only.

Read {ARTIFACT_DIR}/pages/.

What counts:
1. <h*> headings exceeding 12 words — the heading is acting as a paragraph.
2. Body paragraphs >50 words with the verdict at the end. Lead is buried.
3. Boilerplate templates: same sentence structure across N rows with only
   nouns swapped ("Mix of A, B, C creates visual depth" repeated for every row).
4. Lists rendered with trailing "…" ellipses — looks like runaway truncation.
5. Walls of text covering multiple categories that should be 5 bullets.
6. Tooltip/explainer text repeated next to controls that the user has
   already acknowledged (post-onboarding).
7. Multiple consecutive sections that say the same thing in different phrasings.

What does NOT count:
- Same content rendered twice → "duplications".
- Empty/missing content → "gaps".
- Internal jargon leaking → "gaps" (covers placeholders + raw enums).

When flagging, quote the offending heading or first 40 words. Suggest a tighter
version in the "Suggested fix" line — show the win, don't just describe it.
```

### Lens 4 — `affordance`

```
You are auditing a UI for the AFFORDANCE / DEAD-ENDS lens only.

Read {ARTIFACT_DIR}/pages/.

What counts:
1. Status pills/badges with no action — the user can't act on the state.
2. Buttons with opaque verbs ("Clean", "Show", "Mark") that don't tell you
   what tapping will do or what state changed.
3. Pressed/active controls with no obvious way to deactivate.
4. Expanders that, when opened, reveal internal taxonomy or jargon
   (rule categories, registry keys) instead of useful detail.
5. CTAs that point to broken or unreachable destinations
   ("Run /stores in Claude Code" when the route 404s).
6. Counts/badges with no associated drill-in
   ("3 Suggestions" with no way to view them).
7. Toggle/switch UI where the off-state is indistinguishable from the on-state.

What does NOT count:
- Empty data → "gaps".
- Feature exists but isn't reachable → "discoverability".
- Rambling tooltip → "rambling".

For each finding, describe what the user expects and what actually happens.
```

### Lens 5 — `consistency`

```
You are auditing a UI for the CONSISTENCY / DRIFT lens only.

Read {ARTIFACT_DIR}/pages/ and meta.json files.

What counts:
1. Same concept rendered with different formatting across pages:
   - Date formats ("2026-04-30", "Apr 29, 2026, 17:35", "April 30")
   - Section numbering (`§ 01`, `§01`, `§ §`, `Sec 1`)
   - Status badges for the same state styled differently per page
   - Empty-value rendering (`—`, blank, "Not set", "—  —")
   - Pluralization/spelling drift ("outerwears" vs "outerwear")
2. Inconsistent imperative voice across CTAs ("Suggest outfit" vs "Get feedback" vs "Open Evaluate").
3. Mixed unit display ("17 cm", "57.5 cm", "42.5" with no unit).
4. Section headers using both noun and verb forms in the same view.

What does NOT count:
- Two surfaces showing the same content → "duplications".
- A specific term being internal jargon → "gaps".

This lens is the LEAST about correctness and the MOST about cohesion. Findings
here are usually small individually but compound. Group near-identical drift
into one finding with a list, not N findings.
```

### Lens 6 — `discoverability`

```
You are auditing a UI for the DISCOVERABILITY / IA lens only.

Read {ARTIFACT_DIR}/routes.json and {ARTIFACT_DIR}/pages/.

What counts:
1. Features only reachable by typing the URL (no nav link, no in-app link).
2. Sub-tabs/sections invisible from the sidebar or top-level surfaces
   (sidebar advertises 3 nouns, app has 5+).
3. Empty-state CTAs that point to broken routes or unimplemented commands.
4. Redirects that land on the wrong tab or sub-state.
5. Orphaned routes — folder exists, page renders 404, no breadcrumb explains why.
6. Cross-references that link to dead destinations.
7. Banner / chrome that misrepresents the active section (chrome says "§ 04 Evaluate"
   while body shows 404).

What does NOT count:
- The page is empty when you arrive → "gaps".
- The page has rambling copy → "rambling".

For each finding, name the user's path of expectation and where it actually
lands. Use routes.json as the source of truth for status codes.
```

### Lens 7 — `trust`

```
You are auditing a UI for the TRUST / CLAIM ACCURACY lens only.

Read {ARTIFACT_DIR}/pages/.

What counts:
1. Counts that don't match reality:
   - "5 of 24 outfits" but the alternates panel shows 4
   - "8 of 8 pieces still to find" but the rendered list is 7
2. Filters whose buckets are empty for ALL items
   (e.g., a "Full data" filter when no item has full data — filter exists, can't filter anything).
3. Banner claims that exaggerate or misframe state.
4. Progress indicators inconsistent with the data
   ("11/16 required" but checkbox count says 12 are filled).
5. Generated/Updated timestamps that imply freshness the data doesn't have.
6. State that contradicts visible items (badge says "Clean", item is
   archived, etc.).

What does NOT count:
- Missing data → "gaps".
- Confusing copy → "rambling".

For each finding, state the claim and the reality. Read enough of the
snapshot to verify before flagging — this lens has the highest cost of
false positives.
```

### Lens 8 — `mobile` (only when `--mobile`)

```
You are auditing a UI for the MOBILE / iPHONE FITNESS lens only.

Read {ARTIFACT_DIR}/pages/ and meta.json files. Viewport is 390 × 844 (or
config-overridden value).
The walker has pre-detected smallTouchTargets and viewportOverflowX in meta.

What counts:
1. Touch targets <44×44 px (industry baseline). Group by surface, not per-element —
   one finding per page-section that has multiple too-small targets.
2. Horizontal scroll within the content area (viewportOverflowX > 0).
3. Sidebar nav unreachable — no hamburger, no mobile menu, full sidebar pushed
   off-screen with no entry point.
4. Fixed-width tables, grids, or filter rows that overflow.
5. Modals / drawers that don't take full screen on phone.
6. Text that becomes unreadable due to viewport-relative font scaling.
7. Sticky chrome (header/banner/tab strip) that consumes >25% of the 844px
   height before content starts.
8. Buttons stacked too tightly to hit reliably (vertical spacing <8px between).

What does NOT count:
- Anything that's also broken on desktop → that lens caught it.
- Content quality issues (empty/rambling/duplicate) — those lenses caught them.

This lens is gating: a desktop-OK page can fail mobile cleanly. Be specific
about what phone gesture / context fails.
```

---

## Synthesizer prompt

```
You are merging the output of {N} parallel UI-audit lens agents into one
ranked report. You did not see the app yourself. You have:

- {ARTIFACT_DIR}/lenses/*.md  — N lens reports, each a list of findings
- {ARTIFACT_DIR}/routes.json  — URL → status, redirect, slug, tabs walked
- {ARTIFACT_DIR}/pages/*.meta.json — pre-computed per-page diagnostics
- {ARTIFACT_DIR}/meta.json — run config, including surface_buckets if configured

Your job: dedupe, cluster, rank, classify by `kind`, dedupe against in-flight
task work, write findings.md AND digest.json.

## Algorithm

1. Parse every lens report into a flat list of findings. Each finding has
   {id, title, severity, page, element, evidence, what, why, fix, suggested_kind, files_to_touch, lens}.

2. **Pre-cluster within a single lens** (BEFORE cross-lens clustering).
   When one lens emitted N findings that share an anti-pattern on the same
   page or page-family, fold them into one finding for that lens before
   cross-lens clustering. Triggers:
   - Same page slug AND ≥0.6 fix-candidate overlap → fold.
   - Same page slug AND findings reference different sub-sections of the
     same anti-pattern → fold into one finding listing all sub-sections.
   - Same surface family AND fix candidates are the same one-liner → fold.
   When folding, keep the most concrete evidence and append a "Sub-instances:"
   line. Pre-clustering is the difference between a 65-row report and a 30-row
   report. Aim for the latter.

3. **Cross-lens cluster** the (pre-clustered) findings that refer to the
   same atomic UI surface:
   - Strong match: same page slug AND same element ref.
   - Medium match: same page slug AND ≥0.5 token-overlap on evidence text
     OR ≥0.7 token-overlap on the fix-candidate text.
   - Weak match: same page slug AND same surface section — only cluster if
     titles also overlap ≥0.5.

4. For each cluster:
   - canonical = the finding with the most concrete evidence (longest evidence
     text; tie-break by earliest lens alphabetically).
   - lenses_seen = set of all lens names that contributed (pre + cross).
   - severity = max in cluster.
   - Drop the original IDs; assign a fresh `F-NN` sequence in dedupe order.
   - **Write `description`** — a plain-English one-line summary suitable for
     at-a-glance dashboard triage. Derive from the canonical finding's `What`
     line; expand with `Why` context only if the bare `What` would be opaque
     without it. Constraints: complete sentence, period-terminated, ~80-140
     chars (hard cap 200 to prevent wrap disasters), self-contained (names
     the page / element / surface affected so the user doesn't need to open
     `findings.md`). Distinct from `title` — `title` is a short cluster
     identifier (used as findings.md cluster header + FB title on promote);
     `description` is the readable sentence rendered on the dashboard digest.
     Example: title `"Login page has no email-format hint pre-submission"`,
     description `"The /login email field shows no inline format hint before
     submission; users only learn the format requirement from the post-submit
     error, breaking the affordance loop."`

5. **Classify `kind` per cluster (DEC-013 Option C is now an action layer — bundle-eligible classification triggers actual inline-apply at Fix-it time, so be conservative):**
   - **HARD RULE FIRST.** If `files_to_touch` includes ANY of: `.claude/spec_v*.md`,
     `.claude/support/decisions/decision-*.md`, `.claude/vision/**/*.md`
     → `kind: decision` (always; no exceptions; this enforces Component 6
     hard exclusion of the audit family proposal). Set
     `iterate_routing.reason: "spec/decision/vision file modification — read-only outside /iterate"`.
   - If suggested_kind is `design` from any contributing lens → `kind: design`.
     No [Fix it] action; promote to FB only.
   - **Bundle-eligible classification (DEC-013 Option C — triggers actual inline-apply via [Fix it])** — only when ALL hold:
     a. Implementation-file-only (no spec/decision/vision per HARD RULE)
     b. Source-confirmed: the fix is a sync from one authoritative source (cited concretely
        in `source_anchors[]` / `files_to_touch[]`) to a derived/dependent location.
     c. Reversible: text edit, dead-link removal, single-file orphan delete
     d. No new judgment: the fix's content is already established (audit syncs, doesn't decide)
     e. Bounded scope: ≤3 files
     f. **When in doubt → fix-eligible, not bundle-eligible.** The action layer's at-apply
        re-read invariant cannot catch semantic mismatches the synthesizer creates —
        conservative classification at synthesis time is the load-bearing safety property.
     Set on bundle-eligible items: `bundle_eligibility.source_confirmed: true`,
     `reversible: true`, `files_count: {N}`, `touches_spec_or_decisions: false`.
   - Otherwise (implementation-only but doesn't meet ALL bundle-eligible criteria,
     or >3 files, or ambiguous fix) → `kind: fix-eligible`. Surfaces on dashboard with
     the italicized `*(fix-eligible — manual review pending future DEC)*` kind annotation
     only — no inline `[Fix it]` until a future DEC expands inline-apply.
     (Promote/Dismiss actions are available via tick + bulk CLI / natural-language;
     not rendered per-item — see `dashboard-regeneration.md` § "Audit Findings sub-section".)

   Note: most UI audit findings will be `decision` kind because UI fixes
   typically require copy/IA decisions that should route through `/iterate`.
   Bundle-eligible UI findings are rare but real (orphan dead-link removal,
   stale CTA pointing at a 404 the spec also dropped, deletion of a clearly-unused
   component file). Don't force findings into bundle-eligible — DEC-013 Option C's
   inline-apply path is opt-in by classification confidence, not by hopeful inference.

6. Score each canonical:
   - Impact:
     - high — blocks a core flow / wrong claim / inaccessible feature /
       leaks secrets or filesystem refs / 404 on a route the app references
     - med — visible friction, repeated everywhere, mis-affordance with
       no way to recover
     - low — single-page cosmetic, edge case
   - Effort:
     - S — copy/CSS, single file, no logic change
     - M — small refactor across N files, same data model
     - L — design decision needed, schema change, or new state machine
   You don't have the codebase open; estimate effort from the FIX line.
   When in doubt, mark M.

7. quick_wins = canonicals where effort == S AND impact >= med.
8. high_signal = canonicals where len(lenses_seen) >= 3.

9. **Pending-work dedupe.** For each clustered finding, scan
   `.claude/tasks/task-*.json` for tasks with `status` in
   `{Pending, In Progress, Awaiting Verification}`. Match if:
   - The task's `files_affected` overlaps with the finding's `files_to_touch`, OR
   - The task's `description` or `title` mentions the finding's page/route/component

   On match: REMOVE the finding from `items[]` and ADD an entry to
   `annotations[]`:
   ```json
   {
     "type": "covered_by_pending_task",
     "what": "{finding title}",
     "covered_by": "{task_id}",
     "covered_by_status": "{task status}",
     "page": "{slug}",
     "suppressed_finding_id": "F-NN"
   }
   ```

10. **Group by surface** using URL prefix or config-supplied buckets.
    Read `meta.json` for `surface_buckets`. If present, use those mappings
    (e.g., `{"Authentication": ["/auth", "/login"]}` puts /auth findings
    under "Authentication"). If absent, default to top-level URL prefix
    grouping (`/foo` → `Foo` bucket). Always include "Routes & infra"
    as a special bucket for any 404 or non-200 finding.

11. Within each surface, sort by severity desc, then impact desc, then effort asc.

12. Sanity checks:
    - No item in `items[]` has `kind: bundle-eligible` AND `files_to_touch`
      containing any spec/decision/vision path.
    - If raw findings ÷ deduped findings < 1.3, you under-clustered. Re-read
      the lens reports for any pair you missed (especially same-page
      pre-cluster opportunities).
    - If high_signal is 0 across 7 lenses, you over-clustered or the lens
      reports were poorly aligned — flag it in the Notes section.
    - The Promote checklist must list every canonical finding by ID.

## Output

Return TWO artifacts: `findings.md` AND `digest.json`.

### `findings.md`

```markdown
# UI Audit — {today} — {desktop|iPhone}
`{entry-url}` · {N} routes walked · {M} lenses · {raw} findings → {dedup} after dedupe

## Top 5 quick wins
1. **{title}** — {one-line fix} ({lenses}) `S effort · {impact} impact · {kind}`
...

## Findings by surface

### Routes & infra
#### F-01 · {title}  ![lens] {comma list of lenses}
- **Kind:** {kind}  ·  **Severity:** {severity}  ·  **Effort:** {S|M|L}  ·  **Impact:** {S|M|L}
- **Where:** {page slug + tab/state}
- **Files to touch:** {list}
- **Evidence:** {quoted}
- **Why:** {one line}
- **Fix candidate:** {one line}
{If decision: include iterate_routing object}

#### F-02 · ...

### {bucket name}
...

(... continue per surface bucket that has findings)

## High-signal cluster (3+ lenses agreed)
| ID | Title | Lenses | Severity |
|----|-------|--------|----------|
| F-NN | ... | ... | ... |

## Per-lens counts
| Lens | Raw | After dedupe | High-sig |
|------|-----|--------------|----------|
| gaps | ... | ... | ... |
...

## Annotations — already covered by in-flight work
- F-NN ({type}) → {covered_by} ({covered_by_status}) — "{what}"

## Walked
| Route | Status | Tabs walked | Console |
|-------|--------|-------------|---------|
| / | 307 → /home | — | clean |
...

## Promote to feedback

Tick the box, then run `/audit-ui promote {audit-ts}`.

- [ ] F-01 — {title}
- [ ] F-02 — {title}
...

## Notes
- {meta lines: walker timeouts, redirect oddities, mobile-menu detection result, etc.}
```

### `digest.json` — machine-readable digest (audit family schema)

```json
{
  "audit": "ui",
  "ran_at": "{ISO timestamp from meta.json}",
  "viewport": "desktop|mobile",
  "findings_count": {
    "raw": {N},
    "clustered": {M},
    "bundle_eligible": {K},
    "fix_eligible": {L},
    "promote_eligible": {decision + design counts},
    "deduped_to_pending_work": {Z}
  },
  "items": [ {full item objects per audit family Component 2 schema} ],
  "annotations": [ {full annotation objects} ]
}
```

The Promote checklist in findings.md is mandatory and machine-parsed by
the promote mode. Do not omit any finding from it. Default state is unticked.

Both artifacts MUST be returned. The orchestrator writes both.
```

---

## Edge cases

- **Dev server not running.** Stop, ask user to start it. Don't auto-start.
- **Auth-gated app.** This walker assumes the app is accessible without login. If a route 401s, record in routes.json and skip.
- **Snapshot too large.** Some pages exceed Playwright snapshot limits. When a snapshot fails, fall back to `browser_evaluate` returning the H1/H2 outline + body length, plus a screenshot. Save the partial as `pages/{slug}.partial.json`.
- **No findings on a lens.** The lens still emits a report file with `Findings: 0`. The synthesizer should not skip it — it's a positive signal.
- **Re-running the audit.** A second run creates a new `ui-{ts}/` dir. Promote dedupe (step 5 of promote mode) reads ALL prior FB entries to avoid double-promoting the same finding.
- **Walking a feature that requires Playwright form fill.** Out of scope. Audit reads, doesn't author. Note in findings.md "Notes" section if a critical surface is unreachable.
- **`--mobile` on a desktop-only app.** Sidebar may be entirely hidden with no fallback. The mobile lens captures this. Other lenses still run on the mobile snapshots — many findings will overlap with the desktop run, which is expected, and dedupe handles it on a per-run basis.
- **Hard-rule mis-classification.** Synthesizer step 12 catches `kind: bundle-eligible` items whose `files_to_touch` includes a spec/decision/vision path and re-routes to `decision`.

---

## Why this shape

- **One file, multiple modes.** Walk + lenses + synth + promote in one command keeps state colocated. The artifact dir is the only persistence beyond `friction.jsonl` updates (via promote).
- **Walker is the orchestrator, not a sub-agent.** Playwright MCP is a single browser session — parallel walkers would conflict (`.claude/rules/agents.md` § "MCP and Parallel Execution"). Lens parallelism happens AFTER capture, against static artifact files.
- **Lenses cap context.** Each lens agent reads only what it needs (the artifact dir), with sharp in/out-of-scope rules. No anchor bias from other lenses' findings.
- **Synthesizer does not see the live UI.** It only sees lens reports + meta. This forces it to trust the lens evidence, not re-litigate.
- **Synthesizer enforces the hard rule structurally.** The "spec/decision/vision read-only outside /iterate" rule is enforced in step 5 (HARD RULE FIRST) AND in the post-synth sanity check (step 12). Two independent enforcement points.
- **Pending-work dedupe respects existing ownership.** Annotations capture the issue without spawning duplicate work.
- **Promote uses the existing feedback flow.** The audit produces feedback-shaped artifacts; `/feedback review` and `/iterate` work unchanged.
- **Cross-run continuity via dedupe.** Promote-time dedupe means re-running weekly doesn't flood feedback.md — only new or regressed findings land.
- **Project-config-driven bucketing.** `audit-ui.config.json` is optional; default URL-prefix grouping works for projects that don't define custom buckets. Avoids hardcoding any one project's surface vocabulary.
