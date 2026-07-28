# Lens: friction-register

Findings: 4

Four open entries; no 3+ cluster sharing both `kind` and overlapping `source_anchor` (two `design_contradiction` entries FR-025 and FR-029 sit in unrelated files — one in a notebook, the other in `fabric_workspace.md` vs `expressions.tmdl`). No entry is >60 days old (max age 5 days). Each entry describes a structural problem, so all four pass through as single-instance findings.

## F-fri-01
- **Title:** Bronze WGI schema contradiction (DQ vs bronze-to-silver)
- **Severity:** high
- **Source anchor:** `fabric/data_quality_checks.Notebook/notebook-content.py` § schema_checks / completeness_checks (oem_lh.bronze_WGI)
- **Files affected (read-only):** `fabric/data_quality_checks.Notebook/notebook-content.py`, `fabric/bronze-to-silver.Notebook/notebook-content.py`
- **Files to touch (potential fix):** `fabric/data_quality_checks.Notebook/notebook-content.py` (absorb DQ contract update per task-035)
- **Evidence:** "bronze-to-silver HARD-REQUIRES ['Indicator Code','Year','Value']; data_quality_checks.Notebook asserts schema {'Country Name','Country Code','Series Name','Percentile Rank 2023'} with required fields ['Country Name','Country Code','Series Name']"
- **What:** Two notebooks hold contradictory schema expectations for the same `bronze_WGI` table.
- **Why:** The DQ schema check is not in BLOCKING_CHECKS, so the mismatch stays latent until bronze-to-silver succeeds and the DQ activity runs, then logs an advisory fail.
- **Suggested fix:** Resolve FR-025 by having task-035 absorb the DQ contract update to match bronze-to-silver's `['Indicator Code','Year','Value']` shape.
- **Suggested kind:** fix-eligible

## F-fri-02
- **Title:** Spec § Data Sources #2 contradicts live pipeline (EPI ingestion)
- **Severity:** high
- **Source anchor:** `spec_v1.md` § Data Sources #2 (line 208; checkbox at line 822)
- **Files affected (read-only):** `.claude/spec_v1.md`
- **Files to touch (potential fix):** `.claude/spec_v1.md` (line 208 + checkbox at line 822, via `/iterate`)
- **Evidence:** "spec_v1 § Data Sources #2 line 208 states the EPI ingestion method is EPI_file2table.Dataflow while line 238 of the same section and the live pipeline both use bronze_ingest_epi.Notebook. Matching stale checkbox at line 822."
- **What:** The spec names a Dataflow as the EPI ingestion method while the spec's own line 238 and the live pipeline both use a notebook.
- **Why:** Spec drift between two adjacent lines plus a stale acceptance checkbox misleads any reader or agent using the spec as the source of truth.
- **Suggested fix:** Resolve FR-027 via `/iterate` to align line 208 and the line 822 checkbox with the notebook ingestion method actually used.
- **Suggested kind:** decision

## F-fri-03
- **Title:** DQ analysis notebook references retired World Bank table
- **Severity:** med
- **Source anchor:** `fabric/data_quality_analysis.Notebook/notebook-content.py:421`
- **Files affected (read-only):** `fabric/data_quality_analysis.Notebook/notebook-content.py`
- **Files to touch (potential fix):** `fabric/data_quality_analysis.Notebook/notebook-content.py` (line 421)
- **Evidence:** "fabric/data_quality_analysis.Notebook line 421 still reads oem_lh.silver_WB, a table the retired World Bank ESG lineage produced and which no longer exists."
- **What:** A latent notebook still reads a table dropped when the World Bank ESG lineage retired.
- **Why:** Not a pipeline activity so it fails only if the notebook is run manually — a stale reference waiting to bite.
- **Suggested fix:** Resolve FR-028 by removing or repointing the `silver_WB` read at line 421, or retire the notebook section if the analysis is obsolete.
- **Suggested kind:** fix-eligible

## F-fri-04
- **Title:** Semantic model doc claims warehouse; TMDL declares DirectLake lakehouse
- **Severity:** high
- **Source anchor:** `fabric_workspace.md` § Semantic Model vs `fabric/OEMInsightBI_v2.SemanticModel/definition/expressions.tmdl:1`
- **Files affected (read-only):** `fabric_workspace.md`, `fabric/OEMInsightBI_v2.SemanticModel/definition/expressions.tmdl`
- **Files to touch (potential fix):** `fabric_workspace.md` § Semantic Model
- **Evidence:** "fabric_workspace.md described the semantic model as connected to the oem_wh warehouse while expressions.tmdl declares DirectLake against the oem_lh lakehouse. The mismatch is what made the never-populated warehouse look load-bearing across several docs."
- **What:** Documentation says warehouse; the actual TMDL connection is DirectLake to the lakehouse — the warehouse was never populated and is not load-bearing.
- **Why:** The doc/contract mismatch propagated into multiple docs treating a dead warehouse as a real dependency.
- **Suggested fix:** Resolve FR-029 by correcting `fabric_workspace.md` § Semantic Model to reflect the DirectLake-against-`oem_lh` connection declared in `expressions.tmdl`.
- **Suggested kind:** fix-eligible