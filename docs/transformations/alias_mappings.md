# Alias Mappings Reference

## The notebook is canonical — this document is policy, not a copy

The live alias seed lives in **`fabric/silver-to-gold2.Notebook/notebook-content.py`**,
in the cell under `## Mapping Tables for Data Standardization`:

| Seed | Symbol in the notebook | Written to |
|---|---|---|
| Country aliases | `country_aliases_with_confidence` | `mapping_country_aliases_confidence` |
| Material aliases | `MATERIAL_ALIASES` → `material_aliases_with_confidence` | `mapping_material_aliases_confidence` |

**This document deliberately does NOT reproduce the rows.** An earlier version did, and
drifted: it listed aliases that never existed in code (`Cote d'Ivoire`, `Macau`,
`Puerto Rico`, ISO3 self-mappings, case-only material variants) while omitting the ones
that carry real remediation weight (the Congo set, the Korea set, the corrupted-Türkiye
set, `Electronic Components`). Because the seed is edited by ordinary tasks — task-025
added the supply-shares gaps and corrected the Russia direction, task-028 removed three
unreachable material rows and added `Phosphorus` — a verbatim copy here is a second
surface to keep in sync with no CI guard behind it. Read the notebook for the rows; read
this file for the rules the rows must obey.

To see the *live* contents without opening the notebook:

```sql
SELECT match_type, confidence, COUNT(*) AS rows
FROM oem_lh.mapping_country_aliases_confidence
GROUP BY match_type, confidence ORDER BY confidence DESC;

SELECT * FROM oem_lh.mapping_material_aliases_confidence ORDER BY confidence DESC;
```

---

## Country aliases

### Confidence tiers and `match_type` taxonomy

Every seed row is `(alias, standard_name, confidence, match_type)`. `match_type` is the
*reason* for the confidence, and it is carried all the way into
`gold_dim_country_lookup`, so it must stay honest — it is what makes a questionable
mapping auditable instead of laundered.

| Confidence | `match_type` | Meaning | Illustrative row (not the full set) |
|---|---|---|---|
| 1.00 | `exact_match` | The standard name mapped to itself. Only needed where a self-row is not otherwise generated. | `"United Kingdom" → "United Kingdom"` |
| 0.95 | `standard_alias` | Unambiguous, widely-published alternative name or abbreviation. | `"UK" → "United Kingdom"` |
| 0.90 | `encoding_variant` | Correct native spelling that differs from the dimension's spelling. | `"Türkiye" → "Turkey"` |
| 0.90 | `partial_country` | A constituent country standing in for the sovereign state. | `"England" → "United Kingdom"` |
| 0.90 | `ambiguous` | The source name maps to more than one real country; one is chosen. | `"Congo" → "Republic of Congo"` |
| 0.85 | `territory` | A dependency/territory rolled up to its sovereign state. | `"Hong Kong" → "China"` |
| 0.85 | `typo` | A recognisable misspelling in source data. | `"Turkyie" → "Turkey"` |
| 0.85 | `with_notation` | A country name with a parenthetical annotation attached by the source. | `"DRC (HQ in South Africa)" → "Dem. Rep. Congo"` |
| 0.80 | `corrupted_encoding` | Mojibake — UTF-8 read as Latin-1, sometimes twice. | the `TÃ¼rkiye` family → `"Turkey"` |
| 0.60 | `source_error` | The source value is factually not a country. Mapped anyway, at a confidence low enough to keep it visible. | `"Brasilia"` (a capital city) → `"Brazil"` |

**Policy on `source_error`:** map it, do not silently clean it. The low confidence keeps
the row inside `gold_low_confidence_audit` (< 0.95) so the underlying source defect stays
reportable rather than disappearing into a clean-looking dimension.

### Groups that must be edited as a set

These are the clusters where a partial edit produces a *wrong answer* rather than a miss:

- **Congo.** `Dem. Rep. Congo` and `Republic of Congo` are two different countries. Every
  DRC spelling must resolve to `Dem. Rep. Congo`; the bare `"Congo"` is deliberately
  `ambiguous` at 0.90 rather than being guessed into the DRC.
- **Korea.** North and South are separate countries; no row may collapse them.
- **Türkiye.** One correct native spelling plus a family of mojibake variants and one
  typo, all resolving to `Turkey`.

### Direction rule (the orphaned-alias trap)

`standard_name` **must be a name that `gold_dim_country` actually carries**, because
`gold_dim_country_lookup` is built with an *inner* join from the alias seed to the
dimension. An alias pointing at a spelling no dimension row uses is silently dropped, and
the source spelling it was meant to rescue stays unmapped.

This has bitten twice, both fixed in task-025:

- `Russia → Russian Federation` was backwards. EPI 2024 names RUS `Russia`, so `Russia`
  is the dimension spelling; the alias now runs `Russian Federation → Russia`.
- `Cape Verde` had to target `Cabo Verde`, the EPI 2024 spelling.

**Before adding a country alias, confirm the target exists:**

```sql
SELECT country_name_std FROM oem_lh.gold_dim_country
WHERE country_name_std = '<your standard_name>';
```

### How the lookup is assembled

`gold_dim_country_lookup` = every dimension row as an exact self-lookup
(`match_confidence = 1.0`, `match_type = 'exact'`) **UNION** the alias seed joined to the
dimension. Where a name appears on both sides, the exact self-lookup wins the tie-break —
so a Tier-1 `exact_match` seed row is redundant with, and never overrides, the
self-lookup.

---

## Material aliases

Material names are `initcap(trim(...))`-normalised *before* every alias join and before
every fact join.

### Reachability contract (task-028) — enforced

> **Every left-hand side must satisfy `initcap(lhs) == lhs`.**

Spark's `initcap` lowercases everything after the first letter of each
whitespace-delimited word: `"High-Tensile" → "High-tensile"`, `"(ABS)" → "(abs)"`. An LHS
that is not its own `initcap` **can never be matched by any input** — it is dead weight
that reads like a live mapping. Three such rows were removed in task-028.

The contract is enforced in two places: an assertion in the notebook next to the
commodity-group map, and `tests/test_material_mapping.py`. Add rows only after checking
them against that guard.

**Corollary: case-only variants never need an alias row.** `"COPPER"`, `"copper"` and
`"Copper"` all collapse to `"Copper"` for free. (The old version of this document listed
them as mappings, and additionally listed `"CoPoER" → "Copper"`, which `initcap` turns
into `"Copoer"` — it would not have matched even if it had been seeded.)

### Material tiers

| Confidence | `match_type` | Meaning | Illustrative row |
|---|---|---|---|
| 0.95 | `spelling_variant` | Regional spelling of the same substance; the non-US spelling is canonical. | `"Aluminum" → "Aluminium"` |
| 0.90 | `unit_removed` | A unit suffix stripped from the material name. Note the source form is parenthesised, e.g. `(t)` — not `[t]`. | `"Copper (kg)" → "Copper"` |
| 0.85 | `generalized` | A broad source term folded into a specific dimension member. | `"Electronic Components" → "Electronics (controllers, Sensors)"` |

---

## Adding a new alias

1. **Edit the notebook seed** — `country_aliases_with_confidence` or `MATERIAL_ALIASES` in
   `fabric/silver-to-gold2.Notebook`. This is the only supported edit point; the
   `mapping_*_confidence` tables are overwritten from it on every gold run, so appending
   to them directly is lost on the next run.
2. **Pick `confidence` + `match_type` from the tables above.** Do not invent a
   confidence — the tiers are what `gold_low_confidence_audit` (< 0.95) and the
   `data_quality_score` are calibrated against.
3. **Countries:** verify `standard_name` exists in `gold_dim_country` (direction rule
   above). **Materials:** verify `initcap(lhs) == lhs` (reachability contract above).
4. Re-run `/run-gold`, then confirm the value left the gap registry:

```sql
SELECT gap_natural_key, gap_type, current_status, total_occurrences
FROM oem_lh.gold_gap_registry
WHERE gap_natural_key = '<the source value>';
```

## Where unmapped values surface

| Table | What it tells you |
|---|---|
| `gold_unmapped_procurement_audit` | One row per unmapped value **occurrence** — which dimension failed, and the spend on that transaction |
| `gold_unmapped_supply_audit` | The same, for the supply-share fact |
| `gold_gap_registry` | One row per distinct unmapped value, with lifecycle (`first_seen`, `last_seen`, `current_status`) |
| `gold_low_confidence_audit` | Matches that *succeeded* below 0.95 — the aliases worth double-checking |

`/view-unmapped` reads the first two. See `data_quality_architecture.md` for the full
shape of each.
