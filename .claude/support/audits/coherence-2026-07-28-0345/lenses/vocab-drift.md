# Lens: vocab-drift

Findings: 2

## F-voc-01
- **Title:** WGI items drift across "governance dimensions" / "WGI dimensions" / "indicators"
- **Severity:** med
- **Source anchor:** spec_v1.md § Business Logic & Calculations (line 1302) — pick one canonical term; § Data Architecture (lines 256, 280), § Data Transformations (line 376), § Data Quality & Validation (line 1101) all drift
- **Files affected (read-only):** .claude/spec_v1.md
- **Files to touch (potential fix):** .claude/spec_v1.md
- **Evidence:**
  - § Data Architecture line 256: "Country-level governance quality metrics across **6 governance dimensions**"
  - § Data Architecture line 280: "Six **indicators** are ingested, not five. Coverage rules must test against six."
  - § Data Transformations line 376: "Coverage rules test against six **indicators** (not five)"
  - § Data Quality & Validation line 1101: "6 **governance dimensions**, years 1996-2023 (annual from 2002; biennial before)"
  - § Business Logic line 1302: "the rescaled inverse of the mean of all six **WGI dimensions**"
- **What:** The same six WGI items are referred to as "governance dimensions", "WGI dimensions", and "indicators" across four sections, with no cross-reference establishing them as the same concept.
- **Why:** "Indicators" is overloaded — EPI also has indicators (30+ of them, line 216/552) — so using "indicators" unqualified for WGI is ambiguous, and a reader cross-referencing § Data Architecture § 3 with § Business Logic has to infer that "governance dimensions" = "WGI dimensions" = "indicators".
- **Suggested fix:** Spec amendment via /iterate to standardize on "WGI dimensions" (per § Business Logic & Calculations line 1302) across § Data Architecture (lines 256, 280), § Data Transformations (line 376), and § Data Quality & Validation (line 1101); reserve "indicators" for EPI, or qualify as "WGI indicators" when used.
- **Suggested kind:** decision

## F-voc-02
- **Title:** "fact table" count: 3 vs 4 across sections
- **Severity:** low
- **Source anchor:** spec_v1.md § Semantic Model & Reporting (line 708) — the "Fact Tables" list includes `gold_supply_risk`; § Current State Assessment (line 844) excludes it
- **Files affected (read-only):** .claude/spec_v1.md
- **Files to touch (potential fix):** .claude/spec_v1.md
- **Evidence:**
  - § Semantic Model line 708-716: lists **4 items under "Fact Tables:"** — `fact_epi_score`, `fact_procurement`, `fact_supply_share`, and `gold_supply_risk` (the last named `gold_*`, not `fact_*`)
  - § Current State line 844: "**3 fact tables created** (procurement, supply_share, epi_score)"
  - § Business Logic line 1306: "Computed over two supply mixes and exposed in `gold_supply_risk`" — describes it as a derived/computed table, not a primary fact
- **What:** The term "fact table" includes `gold_supply_risk` in § Semantic Model but excludes it in § Current State, where only the three `fact_*`-prefixed tables are counted.
- **Why:** A reader checking phase-1 acceptance ("3 fact tables created") against the semantic model's fact-table list sees 4 and cannot tell whether `gold_supply_risk` is a primary fact table or a derived exposure table without reading § Business Logic.
- **Suggested fix:** Spec amendment via /iterate to standardize on "fact table" — either update § Current State line 844 to "4 fact tables (procurement, supply_share, epi_score, supply_risk)" matching § Semantic Model, or relabel `gold_supply_risk` in § Semantic Model as a "derived table" / "calculated table" distinct from primary fact tables.
- **Suggested kind:** decision
