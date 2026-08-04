# Feedback Log

Items are captured via `/feedback` and triaged via `/feedback review`.

---

## FB-001: fact_epi_score grain mismatch — gold holds overall EPI only, doc says country×indicator×year

**Status:** refined
**Captured:** 2026-08-04
**Develop:** 2026-08-04 — escalated to `/grill` to interrogate whether the EPI sub-indicator grain (country × indicator × year) is a stated reporting requirement, which decides doc fix (a) vs. implementation gap (b).
**Refined:** 2026-08-04 — `/grill` resolved the fork by reading: this is **(b) implementation gap**, confirmed across four agreeing sources (spec § Data Transformations L507–518, `gold_tables.md` L80–87, DAX library `Weighted EPI Score = SUMMARIZE(fact_epi_score, …, score * RELATED(gold_dim_indicator[weight]))`, and the live TMDL `fact_epi_score.indicator_key → gold_dim_indicator.indicator_key` relationship with `gold_dim_indicator` populated from `silver_epi2024variables`). The doc and spec are correct; the implementation is the outlier.
**Fix locus (upstream of where this item originally placed it):** the 30+ sub-indicator columns are dropped at `bronze-to-silver.Notebook:227` — `df_selected = df_multi_casted.select("code", "iso", "country", "EPI")` — after `clean_and_rename` (L211–222) had carefully preserved them (drops `.old`, strips `.new`). By the time `silver-to-gold2` reads `silver_epi2024results`, only the overall `EPI` survives, so the gold unpivot has nothing to unpivot. Fix = (1) bronze-to-silver selects all 30+ indicator columns into silver, (2) silver-to-gold2 unpivots wide→long into `fact_epi_score` (`country_key, indicator_key, year, score`), joining to `gold_dim_indicator` on abbreviation, (3) deploy `Weighted EPI Score` to the semantic model.
**Latent, not live:** no report visual slices by `gold_dim_indicator`; the three live visuals consume `Avg EPI Score` / `Countries with EPI Data` (both work on overall-EPI-only), and `Weighted EPI Score` lives only in the DAX library doc (not deployed in the TMDL). No live breakage today.
**Decision:** Full sub-indicator grain (user-selected 2026-08-04). Spec is already correct → **no `/iterate` spec change**. Routes to a new **task** (difficulty ~5–6: two notebook edits + one DAX deploy + verify). No active-task conflict — nearest neighbor is task-042 (EPI vintage parameterization), which this does not overlap. Not promoted via `/iterate` (no spec text changes); promoted via task creation in `/work`.

Observed while closing task-036 (EPI/WGI e2e baseline). `fact_epi_score` contains exactly **180 rows, all year=2024** — one row per country holding the overall EPI score only. But `.claude/support/documents/schemas/gold_tables.md` L80–87 documents its grain as **"One row per country × indicator × year"** with columns `country_key, indicator_key, year, score`. The 30+ EPI sub-indicators present in `bronze_epi2024results` (AIR, BIO, CLI, ECO, etc., plus Yale's `.old`/`.new` vintage suffixes) are not unpivoted into the gold fact — only the overall `EPI.new` score lands.

**Open question for triage — which is the bug?**
- (a) **Doc error** — the gold fact was always meant to hold only the overall EPI score and the schema doc overstates the grain → fix `gold_tables.md` L80–87 (and the `### fact_epi_score` grain line) to "one row per country, overall EPI score."
- (b) **Implementation gap** — the sub-indicators were intended to flow to `fact_epi_score` (the `indicator_key` + `gold_dim_indicator` machinery with `source_system='EPI'` rows exists for exactly this) and only the overall score was wired → fix the silver-to-gold EPI transform to unpivot the 30+ indicators.

`gold_dim_indicator` carrying `source_system='EPI'` rows suggests (b) was the design intent, but only the overall score currently lands — so (b) is the more likely reading. Either way the doc and the table currently disagree.

Surfaced as `/feedback` (not a friction marker) because the choice — doc fix vs implementation gap — needs a triage decision, not just a drift correction. If (b), it may also warrant a task (extend the EPI silver-to-gold transform + add sub-indicator rows to `fact_epi_score`) and a spec check on whether the EPI sub-indicator breakdown is a stated reporting requirement.