---
id: DEC-009
title: "WGIᶜ vintage selection: latest year with a complete six-dimension set"
status: approved
category: methodology
created: 2026-07-30
decided: 2026-07-30
decided_by: implement-agent
recommended_by: implement-agent
recommendation_date: 2026-07-30
related:
  tasks: [task-038_3, task-038_4]
  decisions: [DEC-001]
implementation_anchors:
  - src/transformations/supply_risk.py
  - fabric/silver-to-gold2.Notebook/notebook-content.py
inflection_point: false
spec_revised:
spec_revised_date:
blocks: []
---

# WGIᶜ vintage selection: latest year with a complete six-dimension set

## Select an Option

- [ ] Option A: each country's absolute MAX(year); NULL if that year is incomplete
- [x] Option B: each country's latest year carrying all six dimensions, falling back to an older complete vintage; NULL if none exists
- [ ] Option C: average whatever dimensions the latest year happens to carry (partial mean)
- [ ] Option D: one global MAX(year) across all countries

## Decision

**Selected: Option B** — WGIᶜ uses the latest year in which a country carries all six WGI dimensions, falling back to an older complete vintage when the newest year is partial, and yielding NULL when no complete year exists in any vintage.

## Background

`spec_v1.md § Business Logic & Calculations → Supply Risk` (line 1313) defines the governance weight as:

```
WGIᶜ = clamp( (2.5 − mean₆(WGI estimates for c, latest year available)) / 5 , 0, 1 )
```

The phrase "latest year available" is per-country, but the spec does not say what happens when a country's latest year carries fewer than all six dimensions. `silver_wgi` filters NULL `value` rows out at the silver boundary (`bronze-to-silver.Notebook` lines 563–574), so "fewer than six dimensions in a given year" is a real, reachable state rather than a theoretical one.

task-038_3 acceptance criterion 4 requires this case be "handled explicitly (documented rule, not an accidental partial mean)" — this record is that documentation.

## Options Comparison

| Criteria | A: absolute MAX(year) | B: latest complete year | C: partial mean | D: global MAX(year) |
|----------|----------------------|------------------------|-----------------|---------------------|
| `mean₆` is literally a mean over six dimensions | Yes (or NULL) | Yes | **No** | Yes (or NULL) |
| Honors the spec's per-country "latest year available" | Yes | Yes | Yes | **No** |
| Survives a truncated newest-year API fetch | **No** | Yes | Degrades silently | No |
| Reports genuine gaps as gaps (NULL, not a number) | Yes | Yes | **No** | Yes |
| Overall | Rejected | **Selected** | Rejected | Rejected |

## Option Details

### Option B: latest complete year per country, NULL when no complete year exists *(selected)*

**Description:** Per country, choose the greatest year for which all six WGI dimensions are present; compute `mean₆` over that year. If no year has all six, WGIᶜ is NULL.

**Strengths:**
- Makes `mean₆` literally true — the average is always over exactly six dimensions.
- Degrades only on *genuine* coverage gaps. A single truncated API fetch of the newest year falls back to the prior complete vintage rather than nulling the country.
- A missing weight surfaces as NULL, which the join reports through `check_unmapped`, rather than as a plausible-looking number.

**Weaknesses:**
- Countries may sit on different vintages. This is inherent in the spec's own per-country phrasing, and the vintage actually used is now reported per run.

### Option A: absolute MAX(year), NULL if incomplete

Identical to B for a country genuinely missing a dimension in every vintage — both yield NULL. But A *additionally* collapses to NULL whenever a single API fetch truncates the newest year, which is a fetch artifact rather than a real coverage gap.

### Option C: partial mean over whatever the latest year carries

This is precisely what criterion 4 exists to forbid. A mean over four dimensions is numerically indistinguishable from a real one downstream, so it would silently mis-rank a country instead of reporting a gap.

### Option D: one global MAX(year)

Contradicts the spec's "latest year available **per country**" and would drop every country whose series ends earlier. The local smoke test exercises exactly this case (one country resolves to 2022 while another resolves to 2023), so D would have been caught by the suite.

## Deliberate divergence from the Data Gaps coverage rule

`create_data_gaps_table` in `silver-to-gold2.Notebook` (find it by the `WGI_REQUIRED_INDICATORS = 6` symbol, not a line number — the file shifts on every edit) counts a country as governance-covered when it has six *distinct indicators across any years* (`COUNT(DISTINCT indicator_name) >= 6`). That is a **different question** — "do we hold governance data for this country at all?" — and the vintage-agnostic form is correct for it.

A mean mixing 2019's rule-of-law with 2023's voice-and-accountability is not a measurement of any year, so WGIᶜ cannot use the same rule. The two are documented as divergent in both implementations rather than reconciled by weakening either, and **the coverage rule was left unmodified**. The pre-existing `NOTE for task-038` comment sitting immediately above the coverage rule anticipated this split; task-038_3 rewrote it to point back at this record and to state explicitly that the rules must **not** be reconciled by weakening either one.

## Consequences

- `wgi_year` is written alongside `wgi_weight` on `fact_supply_share`, so the vintage used is auditable per row rather than implicit.
- Countries with no complete vintage carry `wgi_weight = NULL` and are surfaced via `check_unmapped`, not dropped.
- task-038_4's dual HHI must treat a NULL `wgi_weight` deliberately — this decision guarantees NULL means "no complete governance vintage", never "perfectly governed".
