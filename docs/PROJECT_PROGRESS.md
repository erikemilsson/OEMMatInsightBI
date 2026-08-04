# Project Progress

> Generated 2026-08-04 from terminal task records (75 archived, 2 active).

| Task ID | Status | Title | Completion Date |
|---|---|---|---|
| task-001 | Finished | Data Gaps Visibility Dashboard | 2026-01-16 |
| task-002 | Finished | Redesign Semantic Model & DAX Measures | 2025-11-03 (Design Phase) |
| task-003 | Finished | Redesign Power BI Report | 2026-01-16 |
| task-004 | Finished | Design & Implement Row-Level Security (RLS) | 2025-11-03 (Design Phase) |
| task-005 | Finished | Automate External Data Ingestion | 2026-04-05 |
| task-006 | Finished | Implement Incremental Load Logic | 2025-11-03 (Design Phase) |
| task-006_1a | Finished | Bronze: Add date-parameter filtering to procurement dataflow |  |
| task-006_1b | Finished | Silver: Implement Delta MERGE in cleaning notebook |  |
| task-006_1c | Finished | Gold: Implement incremental fact_procurement updates |  |
| task-006_2 | Finished | Wire pipeline parameters to all notebook activities |  |
| task-006_3 | Finished | Test incremental load: full + incremental runs, verify no duplicates |  |
| task-007 | Finished | Add Comprehensive Data Quality Checks | 2026-04-05 |
| task-008 | Finished | Create Unit Tests for Transformation Functions | 2026-01-16 |
| task-009 | Finished | Document Existing DAX Measures | 2025-11-03 |
| task-010 | On Hold | Configure Pipeline Scheduling |  |
| task-011 | Finished | Implement Error Handling & Retry Logic | 2026-04-05 |
| task-012 | Finished | Optimize Pipeline Performance |  |
| task-012_1 | Finished | Establish performance baseline |  |
| task-012_2 | Absorbed | Implement partitioning on fact tables |  |
| task-012_3 | Finished | Enable V-Order and add broadcast join hints |  |
| task-012_4 | Finished | Physical clustering for warehouse gold tables (CLUSTER BY, replacing the rejected index DDL) |  |
| task-012_5 | Finished | Performance retest and validation |  |
| task-013 | Finished | Create Portfolio-Ready Power BI Visualizations (Streamlined) | 2025-11-16 |
| task-014 | Finished | Deploy Enhanced Semantic Model & Build Power BI Visuals | 2026-01-16 |
| task-015 | Finished | Fix Semantic Model Relationships for Cross-Table Visuals | 2026-01-16 |
| task-016 | Finished | Guided Power BI Dashboard Building (User-Claude Collaboration) | 2026-01-16 |
| task-017 | Finished | Populate Quality History & Gap Registry with Sample Data | 2026-01-20 |
| task-018 | Finished | Implement Quality Observability Tables in Notebook | 2026-01-20 |
| task-019 | Finished | Add Quality Observability Tables to Semantic Model | 2026-01-20 |
| task-020 | Finished | Add remaining bronze/silver data quality checks |  |
| task-021 | Finished | Sweep stale Fabric artifact names across portfolio docs (3 renames) |  |
| task-021_1a | Finished | Rename sweep — root + portfolio-facing docs (the front door) |  |
| task-021_1b | Finished | Rename sweep — docs/architecture + guides/setup |  |
| task-021_1c | Finished | Rename sweep — .claude/ domain commands |  |
| task-021_1d | Finished | Rename sweep — .claude/support/documents (judgment-heaviest) |  |
| task-021_2 | Finished | Verify rename sweep is complete + resolve FR-001 + add regression guard |  |
| task-022 | Finished | Fix global supply-shares lineage — wire fact_GlobalSupplyShares CSV into the pipeline (replaces 22x-duplicated bronze) |  |
| task-023 | Finished | Fix lookup-table join fan-out — duplicate lookup_name rows and fact_epi_score iso3 join inflate fact tables and spend |  |
| task-024 | Finished | Fix procurement incremental MERGE grain — silver and gold merges collide on non-unique keys (crash or silent transaction loss) |  |
| task-025 | Finished | Make dim_country construction deterministic — duplicate iso3 rows (Turkey et al.) resolved by arbitrary dropDuplicates, breaking alias resolution run-to-run |  |
| task-026 | Finished | Wire data quality checks into the orchestrator and make them able to fail — checks are unwired, advisory-only, and the one reconciliation check is dead |  |
| task-027 | Finished | Fix quality observability tables — gap registry mislabels every gap, resolved gaps never reopen, occurrences double-count, low-confidence snapshot goes stale |  |
| task-028 | Finished | Gold notebook correctness cleanups — initcap-dead material mappings, Phosphorus/Phosphorous dup, fact_supply_share double-write, misleading coverage matrix, EPI year hardcodes |  |
| task-029 | Finished | Implement the documented high-water-mark system (bronze_load_metadata + parameter flow) — or formally descope it via /iterate |  |
| task-030 | Finished | Harden fact_procurement inputs — NULL date_key rows leak into the fact, unknown units silently pass through as kg, unitpriceeur semantics unverified |  |
| task-031 | Finished | Silver WGI drops the governance scores it ingests — preserve Year/Value (or descope), fix the 5-of-6 coverage rule |  |
| task-032 | Finished | Align src/ testable modules with notebook production logic — tests currently certify the OPPOSITE key-generation contract |  |
| task-033 | Finished | Documentation drift sweep — align architecture/DQ/alias/schema docs with pipeline reality after audit fixes land |  |
| task-034 | Absorbed | Build Data Gaps page in Power BI following DQ_PAGE_GUIDE.md |  |
| task-035 | Finished | Replace RefreshDataflow activities with TridentNotebook activities in the orchestrator pipeline (EPI/WGI automation) |  |
| task-036 | Finished | Test end-to-end automated external-data ingestion (EPI + WGI through bronze to gold, no manual upload) |  |
| task-037 | Finished | Test pipeline error handling and retry logic with simulated failures |  |
| task-038 | Broken Down | Build gold_supply_risk — governance- & trade-weighted dual HHI (global + EU sourcing) per DEC-001 Option B |  |
| task-038_1 | Finished | Silver: stop dropping `t` and wire the EU sourcing table into silver |  |
| task-038_2 | Finished | Gold fact: add `supply_mix` + `t` to fact_supply_share and migrate the global-only consumers |  |
| task-038_3 | Finished | Join the WGI governance weight onto the supply fact with the spec'd clamp formula |  |
| task-038_4 | Finished | Build gold_supply_risk — dual HHI, contrast_ratio and is_bottleneck |  |
| task-038_5 | Finished | Expose the SR measures in the semantic model and rewrite dax_measure_library.md §6.1 |  |
| task-038_6 | Finished | Report framing as gross supply risk, plus the before/after weighting comparison |  |
| task-039 | Finished | Designate real Fabric parameter cells — pipeline notebook parameters have never been injected |  |
| task-040 | Finished | Make the DQ gate outcome durably observable — gold_quality_history cannot answer 'did the gate pass on run X' |  |
| task-041 | Finished | Wire pipeline_error_handler into the orchestrator — the execution log exists but no pipeline run has ever written to it |  |
| task-042 | Finished | Single-source the EPI vintage — bronze_to_silver still hardcodes bronze_epi2024results while both ends now derive the year |  |
| task-043 | Finished | Register Azure AD app and grant the Service Principal Fabric workspace access |  |
| task-044 | Finished | Author parameter.yml for fabric-cicd environment-specific configuration |  |
| task-045 | Finished | Author the GitHub Actions workflow that deploys Fabric artifacts via fabric-cicd on merge to main |  |
| task-046 | Finished | Configure GitHub repository secrets and validate the first automated Fabric deployment end to end |  |
| task-047 | Absorbed | Harden deploy-fabric.yml dry-run against fabric-cicd private-API churn once a public resolve-only API exists |  |
| task-048 | Finished | Retire bronze_azureSQLdb2table — replace the last RefreshDataflow with a Copy activity so the pipeline is SPN-safe |  |
| task-049 | Finished | Close out documentation drift for retired and migrated pipeline mechanisms (task-048 + task-035 + decision-004) |  |
| task-050 | Finished | Harden bronze_ingest_wgi retry against World Bank API degradation |  |
| task-051 | Finished | Fix pipeline_error_handler reporting a retried-then-succeeded activity as a run failure |  |
| task-052 | Finished | Evaluate raising bronze_ingest_wgi per_page — measured, rejected, reverted |  |
| task-053 | Finished | Investigate the data_quality_checks runtime regression (+43% vs baseline) |  |
| task-054 | Finished | Land EPI sub-indicator grain in fact_epi_score — unpivot the 30+ indicators wide→long |  |
| task-055 | Finished | task-054 follow-ups: FR-050 DAX-doc column-name fix, countries_with_epi abbrev filter, Weighted EPI Score SUMX double-count fix |  |
| task-056 | Finished | Source EPI indicator weights — ingest epi2024weights.csv and rebuild gold_dim_indicator so Weighted EPI Score renders a 0-100 value |  |
