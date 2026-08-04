# Archived Feedback

Items triaged as not relevant during `/feedback review`, or promoted and applied via `/iterate`. Preserved for reference.

---

## FB-001: Spec references obsolete `clean_columnsAndHeaders.Notebook` (renamed to `bronze-to-silver`)

**Status:** promoted
**Captured:** 2026-05-17
**Promoted:** 2026-05-17 — Incorporated into spec v1 §§ Data Transformations, Pipeline Stage 2, Current State Assessment, Naming Conventions
**Source:** audit-coherence-2026-05-17-1436 C-01

Spec referenced `clean_columnsAndHeaders.Notebook` in four places; on-disk the cleaning notebook is `bronze-to-silver.Notebook` (no archive entry of the old name). All four references swapped. The deeper `[purpose]_[source]to[target].Notebook` naming-convention rule on line 1000 was kept unchanged — line 1004's existing caveat ("Inconsistency: Uses both underscores and hyphens") carries the drift acknowledgement.

Side-effect: `task-012_3.json` `files_affected` array also updated to swap the stale notebook path.

---

## FB-002: Spec lists `semantic_model_oeminsightbi`; active model is `OEMInsightBI_v2`

**Status:** promoted
**Captured:** 2026-05-17
**Promoted:** 2026-05-17 — Incorporated into spec v1 §§ Technical Architecture, Semantic Model & Reporting
**Source:** audit-coherence-2026-05-17-1436 C-02

Spec updated to name the active semantic model `OEMInsightBI_v2`. Line 82 also notes the old name is archived in `fabric/archive/` for historical traceability.

---

## FB-003: Spec names `report.Report`; active artifact is `report2.Report`

**Status:** promoted
**Captured:** 2026-05-17
**Promoted:** 2026-05-17 — Incorporated into spec v1 §§ Semantic Model & Reporting, Dependencies & External Systems
**Source:** audit-coherence-2026-05-17-1436 C-03

Both references updated to `report2.Report`. Line 1429 also notes the old name is archived in `fabric/archive/`.

---

## FB-004: Spec locates Azure SQL setup scripts in `azure/`; actual path is `secure/` (gitignored)

**Status:** promoted
**Captured:** 2026-05-17
**Promoted:** 2026-05-17 — Incorporated into spec v1 §§ Data Architecture / Azure SQL Database, Security & Access
**Source:** audit-coherence-2026-05-17-1436 C-04

`user_creation.sql` and `grant_permissions.sql` references moved to `secure/`. The Setup Scripts list was split into "Credential scripts (in `/secure` — gitignored)" and "Schema scripts (in `/azure` — tracked)", because `procurement.sql` and `supplier_info.sql` remain under `azure/` (schema-only, no secrets). Resolved as `[NEEDS APPROVAL] D2` during /iterate.

---

## FB-005: Inconsistent "DQ" vs "data quality" terminology across spec sections

**Status:** promoted
**Captured:** 2026-05-17
**Promoted:** 2026-05-17 — Incorporated into spec v1 §§ Development Workflow, Data Quality & Validation, Implementation Status
**Source:** audit-coherence-2026-05-17-1436 C-05

Canonicalized on "data quality" (dropping "DQ" entirely) across four lines: 980, 983, 1088, 1499. Matches the long-form usage already present 17+ times in the spec. Resolved as `[NEEDS APPROVAL] D3` during /iterate.

---

## FB-006: "Quality observability tables" vs "data quality observability tables" within § Current State Assessment

**Status:** promoted
**Captured:** 2026-05-17
**Promoted:** 2026-05-17 — Incorporated into spec v1 § Current State Assessment
**Source:** audit-coherence-2026-05-17-1436 C-06

Line 898 updated to "Data quality observability tables added to semantic model" to match line 884. Line 947 deliberately left untouched — the shorter form flows naturally with the preceding "data quality visibility" phrase in the same sentence. Resolved as `[NEEDS APPROVAL] D4` during /iterate.

---

## FB-007: dashboard-render.py mermaid edge sources skip mermaid_id() sanitization

**Status:** obsolete (superseded upstream)
**Captured:** 2026-06-14
**Archived:** 2026-07-28 — superseded by DEC-024 (template v5.0.0, 2026-06-24), which deleted the mermaid renderer entirely; the bug cannot exist at template 5.x. This project synced to 5.4.0 on 2026-07-22; the dashboard is now generated HTML with an inline-SVG dependency graph (no mermaid), so the hand-workaround is no longer needed and a `/work` regen no longer reintroduces broken edges. Template-side triage: `harvest-2026-07-19-triage.md` ("superseded — DEC-024/v5.0.0 deleted the mermaid renderer; the bug can't exist at 5.x; action: sync to 5.x; archive the bridge"). Note: the template's own FB-007 is an unrelated item (spec-edit guardrail, DEC-016) — this downstream item never landed as a template FB; the mermaid issue was tracked only via the interaction-logs bridge (`interaction-logs/processed/OEMMatInsightBI-feedback-FB-007-2026-06-14.json`).

In `render_mermaid()`, `resolve_dep()` returned the raw `f"T{dep}"` without passing it through `mermaid_id()`, so task-dependency edge *sources* kept hyphens while node definitions and edge *targets* were underscore-sanitized — every dependency edge pointed from a phantom node and the Project Overview graph rendered disconnected. The 70-test script suite passed despite the bug. Code path no longer exists.

---

## FB-008: dashboard-render.py --html writes to stdout; docs omit the redirect step

**Status:** addressed (template v5.4.1)
**Captured:** 2026-07-22
**Archived:** 2026-07-28 — addressed upstream in template v5.4.1 (2026-07-28). The reference doc `dashboard-regeneration.md § 3 "Generate Dashboard"` already stated the redirect ("run `dashboard-render.py --html ...` and `Write` its stdout to `.claude/dashboard.html`"); v5.4.1 sharpened the `rules/dashboard.md § Regeneration Strategy` summary to the explicit `python3 .claude/scripts/dashboard-render.py --html > .claude/dashboard.html` form with a note on the silent-stale failure mode (omitting the redirect leaves `dashboard.html` stale with no error). The suggested `--write`/`-o` flag was not added — the explicit-redirect doc clarification closes the gap at zero script change. Template-side bridge file moved from `interaction-logs/inbox/` to `processed/` (`OEMMatInsightBI-feedback-FB-008-2026-07-22.json`). Note: the template's own FB-008 is an unrelated item ("/work fails to restore context at session boundaries"); this downstream item was tracked only via the interaction-logs bridge.

`dashboard-render.py --html` renders the full dashboard HTML to **stdout** (`print(render_full_html(...))`) — the on-disk `dashboard.html` only updates when the caller redirects. Observed here during `/health-check` 2026-07-22: a regen piped to `tail -15` for inspection left `dashboard.html` stale until a second pass with an explicit `> .claude/dashboard.html` redirect. The `--task-hash` mode is correctly stdout-only, so the asymmetry was easy to misread.

---

## FB-009: Remove leftover laptop firewall rule on the Azure SQL server

**Status:** addressed
**Captured:** 2026-08-01
**Archived:** 2026-08-02 — addressed by direct action (commit `c0fcb3a`, 2026-08-01): the `erik-laptop` firewall rule (`37.247.31.201/32`) was deleted from the `procurement-supplier` Azure SQL server. The rule was a task-046 diagnostic leftover (added 2026-07-31 so the laptop could reach the DB for a credential reset) and became obsolete once task-048 retired the `bronze_azureSQLdb2table` dataflow — the Azure SQL path now runs through the Fabric Connection `oem_azuresql_procurement` in the Fabric runtime, not from the laptop. Not promoted to a spec change (a one-off security cleanup, not a workflow change).

During task-046 diagnostics (2026-07-31) a firewall rule `erik-laptop` = `37.247.31.201/32` was added to the `procurement-supplier` Azure SQL server so the laptop could reach the DB for credential reset/testing. The pipeline no longer needs it — task-048 retired the bronze_azureSQLdb2table dataflow and the Azure SQL path now runs through the Fabric Connection `oem_azuresql_procurement` (executes in the Fabric runtime, not from the laptop). An allow-listed laptop IP on a production SQL server is a security loose end. Remove via Azure portal or `az sql server firewall-rule delete -g <rg> -s procurement-supplier -n erik-laptop`.

**Why it surfaced:** task-046 close-out review of leftover diagnostic state. The pipeline's SPN/Connection path makes the laptop rule obsolete.

---

## FB-010: fact_epi_score grain mismatch — gold holds overall EPI only, doc says country×indicator×year

**Status:** closed
**Captured:** 2026-08-04
**Closed:** 2026-08-04 — Delivered via task-054: sub-indicator grain live in `fact_epi_score` (12,196 rows / 73 indicators, country × indicator × year), committed `df18ba1` (with `979d902`), verified `pass`. Spec was already correct at L507–520 (`fact_epi_score` grain = country × indicator × year, unpivot 30+ columns); `/iterate` 2026-08-04 aligned the stale L356 (Bronze→Silver EPI cleaning — "select only EPI") to match the live behavior. No `/iterate` promotion needed — the resolution was a task, not a spec change.
**Originally captured as FB-001** (2026-08-04) — renumbered to FB-010 on close to avoid colliding with the archived FB-001 (`clean_columnsAndHeaders.Notebook` rename, promoted 2026-05-17). Historical prose in task-054 and the 2026-08-04 session handoff refers to this item as "FB-001"; that alias points here.
**Develop:** 2026-08-04 — escalated to `/grill` to interrogate whether the EPI sub-indicator grain (country × indicator × year) is a stated reporting requirement, which decides doc fix (a) vs. implementation gap (b).
**Refined:** 2026-08-04 — `/grill` resolved the fork by reading: this is **(b) implementation gap**, confirmed across four agreeing sources (spec § Data Transformations L507–518, `gold_tables.md` L80–87, DAX library `Weighted EPI Score = SUMMARIZE(fact_epi_score, …, score * RELATED(gold_dim_indicator[weight]))`, and the live TMDL `fact_epi_score.indicator_key → gold_dim_indicator.indicator_key` relationship with `gold_dim_indicator` populated from `silver_epi2024variables`). The doc and spec are correct; the implementation is the outlier.
**Fix locus (upstream of where this item originally placed it):** the 30+ sub-indicator columns are dropped at `bronze-to-silver.Notebook:227` — `df_selected = df_multi_casted.select("code", "iso", "country", "EPI")` — after `clean_and_rename` (L211–222) had carefully preserved them (drops `.old`, strips `.new`). By the time `silver-to-gold2` reads `silver_epi2024results`, only the overall `EPI` survives, so the gold unpivot has nothing to unpivot. Fix = (1) bronze-to-silver selects all 30+ indicator columns into silver, (2) silver-to-gold2 unpivots wide→long into `fact_epi_score` (`country_key, indicator_key, year, score`), joining to `gold_dim_indicator` on abbreviation, (3) deploy `Weighted EPI Score` to the semantic model.
**Latent, not live:** no report visual slices by `gold_dim_indicator`; the three live visuals consume `Avg EPI Score` / `Countries with EPI Data` (both work on overall-EPI-only), and `Weighted EPI Score` lives only in the DAX library doc (not deployed in the TMDL). No live breakage today.
**Decision:** Full sub-indicator grain (user-selected 2026-08-04). Spec is already correct → **no `/iterate` spec change**. Routes to a new **task** (difficulty ~5–6: two notebook edits + one DAX deploy + verify). No active-task conflict — nearest neighbor is task-042 (EPI vintage parameterization), which this does not overlap. Not promoted via `/iterate` (no spec text changes); promoted via task creation in `/work`. Delivered as task-054 (Finished + verified pass 2026-08-04).

Observed while closing task-036 (EPI/WGI e2e baseline). `fact_epi_score` contains exactly **180 rows, all year=2024** — one row per country holding the overall EPI score only. But `.claude/support/documents/schemas/gold_tables.md` L80–87 documents its grain as **"One row per country × indicator × year"** with columns `country_key, indicator_key, year, score`. The 30+ EPI sub-indicators present in `bronze_epi2024results` (AIR, BIO, CLI, ECO, etc., plus Yale's `.old`/`.new` vintage suffixes) are not unpivoted into the gold fact — only the overall `EPI.new` score lands.

**Open question for triage — which is the bug?**
- (a) **Doc error** — the gold fact was always meant to hold only the overall EPI score and the schema doc overstates the grain → fix `gold_tables.md` L80–87 (and the `### fact_epi_score` grain line) to "one row per country, overall EPI score."
- (b) **Implementation gap** — the sub-indicators were intended to flow to `fact_epi_score` (the `indicator_key` + `gold_dim_indicator` machinery with `source_system='EPI'` rows exists for exactly this) and only the overall score was wired → fix the silver-to-gold EPI transform to unpivot the 30+ indicators.

`gold_dim_indicator` carrying `source_system='EPI'` rows suggests (b) was the design intent, but only the overall score currently lands — so (b) is the more likely reading. Either way the doc and the table currently disagree.

Surfaced as `/feedback` (not a friction marker) because the choice — doc fix vs implementation gap — needs a triage decision, not just a drift correction. If (b), it may also warrant a task (extend the EPI silver-to-gold transform + add sub-indicator rows to `fact_epi_score`) and a spec check on whether the EPI sub-indicator breakdown is a stated reporting requirement.
