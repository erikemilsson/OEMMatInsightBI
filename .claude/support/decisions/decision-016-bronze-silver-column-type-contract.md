---
id: DEC-016
title: Bronze/silver column-type contract — does the repo match the live table, or does silver stop inheriting it?
status: approved
category: data-architecture
created: 2026-08-12
decided: 2026-08-12
decided_by: Erik
related:
  tasks: ["069", "064", "059"]
  decisions: ["DEC-015"]
implementation_anchors:
  - file: "azure/procurement.sql"
    description: "Declares Quantity / UnitPriceEUR as DECIMAL(18,2) (L27, L29) — the contract in dispute"
  - file: "fabric/bronze_to_silver.Notebook/notebook-content.py"
    description: "Three unprotected write paths (L538 full-load, L543 first-load, L560 incremental append); zero casts on quantity/unitpriceeur"
  - file: "fabric/silver_to_gold.Notebook/notebook-content.py"
    description: "unitprice_eur (L1832) and spend_eur (L1673) exposed; quantity_base already insulated by an explicit cast (L1779-1780)"
  - file: "fabric/OEMInsightBI.SemanticModel/definition/tables/fact_procurement.tmdl"
    description: "unitprice_eur (L88-89) and spend_eur (L99-100) pinned to dataType: double under a DirectLake partition"
inflection_point: false
spec_revised: false
blocks: ["task-069"]
---

# Bronze/silver column-type contract — does the repo match the live table, or does silver stop inheriting it?

> **Disambiguation.** This is the *project's* DEC-016. The template's rules files also reference a "DEC-016" — the spec/decision/vision edit gate. They are unrelated records in overlapping namespaces (the collision already exists at DEC-003/004/005/010/011/013). Where this project's docs say "DEC-016-gated", they mean the template's gate, not this record.

## Select an Option

Mark your selection by checking one box:

- [ ] Option A: Change `azure/procurement.sql` to `SMALLINT` / `FLOAT` — the repo matches live
- [ ] Option B: Keep `DECIMAL(18,2)`, cast at the silver boundary — as framed in task-069 (three layers move)
- [x] Option B-minimal: Keep `DECIMAL(18,2)`, cast at silver **and** pin gold back to `double` (one layer moves)

*Decided by Erik, 2026-08-12, with the full research payload in hand.*

## Decision

**B-minimal.** `azure/procurement.sql` keeps `DECIMAL(18,2)`. The silver boundary stops inheriting the source's physical type, and gold's types are pinned so nothing downstream of silver moves.

**Why this and not the other two.** The actual defect is that `silver_procurement`'s schema is a function of an upstream physical type — Option A ratifies that coupling rather than fixing it, and pays for zero code with ~11 documentation line-ranges, a permanently self-contradicting quality check, and a 32,767 `quantity` ceiling promoted from accident to contract. Option B fixes the defect but is, at unchanged scope, the three-layer migration already declined on 2026-08-06; re-presenting it as new work because the justification improved would have been dishonest about what was being asked. B-minimal fixes the same defect **one layer deep**, which is precisely the scoping the 2026-08-06 objection ("a THREE-LAYER SCHEMA MIGRATION") leaves open.

**Accepted cost, stated plainly:** money is stored as `double` in `gold_fact_procurement` rather than as decimal — a real anti-pattern kept one layer down. It is mitigated by *where* the rounding happens: the multiplication is performed exactly in decimal and only then cast, so the result is the nearest double to the true cent value rather than a product of float-image inputs. Gold already uses exactly this pattern for `quantity_base` (explicit `.cast("double")`, L1779-1780), so this is the established local convention, not a new concession.

**Scope of work:**

1. `fabric/bronze_to_silver.Notebook` — cast `quantity` / `unitpriceeur` at the silver boundary; add `.option("overwriteSchema","true")` to **both** overwrite branches (L538 full-load **and** L543 first-load — the second is the branch task-069's framing missed).
2. `fabric/silver_to_gold.Notebook` — pin gold: cast `spend_eur_expr` (L1673) and `unitprice_eur` (L1832) back to `double`. **This is what keeps the TMDL untouched and the `decimal(37,4)` DirectLake risk off the table** — it is not optional polish.
3. AC4's five `4-byte float` / `float32` / `REAL -> double` sites corrected.
4. One `p_full_load = true` run, then the repo DDL re-run for real, then a normal scheduled run to prove the incremental append survives. **Live Fabric only** — local verification is structurally incapable of reproducing `DELTA_FAILED_TO_MERGE_FIELDS`.

**Supersedes** the 2026-08-06 documented acceptance recorded in task-059 / `docs/data_quality_framework.md § 7.3`, but only for `data_type_consistency`'s two procurement columns and only at the silver layer. That section must be updated to say the acceptance was revisited, why (a reproducibility-contract failure, not a change of mind about precision), and what remains accepted.

**Expected consequence to verify, not assume:** `data_type_consistency` moves 75.00 → 100.00, and it does so for the reason migration step 5 demands — the layer now implements the declared intent, rather than the expectation being bent to fit. `Total Spend EUR` should move only by recovered precision against the task-024 baseline `sum_spend_eur = 3273776.03`.

## Background

`azure/procurement.sql` declares `Quantity` and `UnitPriceEUR` as `DECIMAL(18,2)`, matching the spec (L190, L194) and `docs/schemas/bronze_tables.md`. The live `dbo.procurement_transactional` it replaced was hand-created outside the repo as `Quantity` → Spark `short`, `UnitPriceEUR` → Spark `double`.

Running the repo rebuild on 2026-08-12 changed bronze's Delta schema to `decimal(18,2)`, and `bronze_to_silver` could no longer write into `silver_procurement` — `DELTA_FAILED_TO_MERGE_FIELDS` on `quantity`, three consecutive failures. Operationally rolled back (live table recreated as `SMALLINT` / `FLOAT`, re-seeded, pipeline green end to end), but **the rollback DDL was never committed**. The repo still disagrees with the live table, so re-running the DDL reproduces the outage.

The default scheduled path is the one that breaks: `p_full_load` defaults to `"false"` (L41), so a scheduled run reaches the unprotected append at L560.

## ⚠ The prior decision this fork re-opens

**On 2026-08-06, with the full measurement in hand, Erik decided NOT to fix these exact column types.** Recorded in task-059:

> RESOLUTION = DOCUMENTED ACCEPTANCE (Erik's decision, 2026-08-06). Rationale: fixing the types is a **THREE-LAYER SCHEMA MIGRATION** on a live scheduled pipeline, not a cast edit.

A 5-step migration path was recorded at `docs/data_quality_framework.md:1181-1187`. Mapping **Option B as task-069 frames it** onto that path:

| Step | Does B require it? |
|------|--------------------|
| 1. Decide the intended contract per column | **Partially** — B inherits `DECIMAL(18,2)` for both columns without re-opening step 1's own flag that `quantity` is a count and `integer` is "arguably more correct than decimal" |
| 2. Casts in `bronze_to_silver` + `overwriteSchema` on the full-load write | **Yes, in full** — B is literally step 2 |
| 3. Run once with `p_full_load = true` | **Yes, in full** |
| 4. Verify `fact_procurement`'s types, update TMDL if shifted | **Yes — and not a no-op.** Two TMDL lines must change |
| 5. Confirm `data_type_consistency` reaches 100.0 for the right reason | **Yes, in full** |

**Verdict: Option B as framed is the same migration Erik already declined — steps 2 through 5 in full. It is not a strict subset and not materially narrower. The scope is unchanged; only the justification is new.**

What genuinely changed since 2026-08-06:

1. **The trigger.** In August the only reason to migrate was sub-cent precision noise on 132 synthetic rows — correctly judged the wrong trade. Today the reason is that *the repo's own committed DDL cannot be run against the live database without an outage*. A reproducibility-contract failure is a different and stronger argument for the same work.
2. **Half the migration is already paid for.** In August it would also have required changing the Azure DDL. task-064 already committed `DECIMAL(18,2)` there. So B = the declined migration, minus the Azure-DDL change (done), plus an outage to un-break.
3. **The bronze half is now empirically proven.** The 2026-08-12 Copy activity *did* land `decimal(18,2)` in bronze Delta. In August that was untested.

**Option B-minimal exists precisely because Erik's recorded objection was "three-layer".** B-minimal moves **one** layer: silver. Gold's types are pinned back to `double` by two casts, so the TMDL is untouched and migration step 4 becomes a verified no-op. It is the only formulation of B that does not ask Erik to reverse a decision he already made.

## Options Comparison

| Criterion | A | B | B-minimal |
|-----------|---|---|-----------|
| Repo reproduces the live table | **Immediately, by construction** | After the DDL is re-run for real | After the DDL is re-run for real |
| Pipeline safe to run today | **Already the deployed state** | Needs code change + full load first | Needs code change + full load first |
| Code sites changed | **0** | 1 file + 1 TMDL | 2 files, **0 TMDL** |
| Documentation/contract sites changed | ~11 line-ranges across 7 files | **~3** | **~3** |
| `data_type_consistency` check | Frozen at 75.00 permanently, **and its justification breaks** | **100.00, for the right reason** | **100.00** |
| float32 noise (§ 7.3 finding 1) | Money-as-binary-float persists | **Eliminated by construction** | Eliminated through the arithmetic; storage stays `double` in gold |
| 16-bit `quantity` ceiling (§ 7.3 finding 2) | **Enshrines a 32,767 cap as the contract** (observed max 3,293) | Removed | Removed |
| Silver decoupled from source physical type | Coupling retained and blessed | **Yes** | **Yes** |
| Layers whose schema moves | **0** | 3 — *exactly the 2026-08-06 objection* | **1** |
| DirectLake / TMDL risk | **None** | Moderate-to-high, **unquantified** | **None** |
| Relation to the declined decision | Consistent — A is "documented acceptance" made permanent | **Reverses it at unchanged scope** | **Genuinely narrower than what was declined** |
| Enshrines a hand-creation accident as contract | **Yes** — the live types were never designed | No | No |

## Option Details

### Option A — repo matches live (`SMALLINT` / `FLOAT`)

Zero code, immediate safety, and truest to what is actually deployed. Three costs the task's original framing did not name:

- **It does not merely keep `data_type_consistency` failing at 75.00 — it retires the intent the check asserts.** § 7.3's root-cause narrative rests on "the check's expectation of `decimal` describes an *intent* that no layer implements." Under A there is no such intent, because the contract itself becomes short/double. The expectation is then neither an unmet intent nor a tautology but an assertion of something the project decided against — and the notebook's own do-not-relabel block (L1200-1216) explicitly forbids the obvious escape: *"An expectation edited to match whatever exists is a tautology that carries no information."* A leaves a permanent self-contradicting artifact in the quality suite.
- **It converts a latent ceiling into a chosen one.** `short` caps at 32,767 against an observed max of 3,293. Under A that becomes the deliberate contract.
- **It is the *larger documentation* change, roughly 3:1** — ~11 line-ranges across 7 files, including two gated spec lines (190, 194) declaring the column types, plus DEC-015. B and B-minimal leave all of those **true as written**.

One stated cost of A is **probably already false**: "keeps the float32 noise story alive." The 2026-08-12 re-seed wrote clean 2-decimal literals (measured in `azure/procurement_seed.sql`: 133 two-decimal lines vs 1 three-plus-decimal line, and that one is the header's own `18.670000076293945` example) into a `FLOAT(53)`/double column. Each value now stores as the nearest double to the intended cent (~1e-16 relative error), not the nearest float32 (~1e-7, which is what produced the visible noise). The `124 of 132` figure at `docs/data_quality_framework.md:1171` is therefore likely stale. **Needs one live read (L1) to settle.**

**Precondition:** AC4 must close *before* A's DDL is written. If the DDL is regenerated from DEC-015's "4-byte float" premise it will say `REAL` = `FLOAT(24)` → Spark `float`, which still mismatches a `double` silver column — breaking silver from the opposite side. Only `FLOAT` = `FLOAT(53)` lands as `double`. Verified against Microsoft Learn (`float and real (Transact-SQL)`: *"The ISO synonym for real is float(24)"*).

### Option B — as framed in task-069

Casts at the silver boundary plus `overwriteSchema` on the full-load write, then re-run the repo DDL for real. The right engineering answer to the actual defect: a silver schema should not be a function of an upstream physical type.

Two serious counts against it:

1. **It is the migration declined on 2026-08-06, at unchanged scope** (see above).
2. **An unquantified DirectLake risk that A does not carry.** Under B, `spend_eur = quantity × unitpriceeur` becomes `decimal(18,2) × decimal(18,2)`. Spark's decimal-multiply rule yields `DECIMAL(p1+p2+1, s1+s2)` = **`decimal(37,4)`** — a type nobody chose. Power BI's fixed-decimal type is `decimal(19,4)`, and Microsoft Learn's DirectLake guidance states the semantic-model type must match the lakehouse type. Representability of `decimal(37,4)` is **not established by any document I could verify**, it is invisible to every local test, and it would surface only in the report layer *after* both notebooks succeeded.

Also incomplete as written: the fix names L538, but the **first-load branch at L543 is a second unprotected overwrite** in the same `try` block.

### Option B-minimal — the scoping that resolves the tension

Keep `DECIMAL(18,2)` in Azure. Cast `quantity` / `unitpriceeur` at the silver boundary and add `overwriteSchema` to **both** overwrite branches (L538 **and** L543). **Additionally** cast gold back to `double` — `spend_eur_expr` (L1673) and `unitprice_eur` (L1832).

- **One layer moves: silver.** Gold does not, the TMDL does not, DirectLake does not. Erik's verbatim "three-layer" objection does not apply.
- Migration step 4 becomes a **verified no-op** instead of two TMDL edits.
- The `decimal(37,4)` DirectLake risk is **eliminated entirely**.
- The precision benefit is still **fully realised**: the multiplication happens exactly in decimal and only *then* casts to double, so the result is ~10⁸ times closer to the intended cent than the current float-image inputs produce.
- `data_type_consistency` reaches **100.00** — the check reads `silver_procurement` only.
- Cost: two extra casts, and money is stored as `double` in gold rather than decimal — a real anti-pattern retained one layer down. Note gold already does exactly this for `quantity_base` (explicit `.cast("double")`, L1779-1780), so it is the established local pattern rather than a new concession.

## What only a live Fabric run can settle

Local verification is **structurally incapable** of settling any of these — `delta-spark` is not installed and local Spark never invokes a Delta writer, so `DELTA_FAILED_TO_MERGE_FIELDS` cannot be reproduced. Same hazard family as `DELTA_INVALID_CHARACTERS_IN_COLUMN_NAMES`. task-069 AC2 already states a local pass is explicitly insufficient.

| # | Question | Bears on |
|---|----------|----------|
| L1 | Is the float32 noise already gone post-rollback? Count `unitpriceeur` values with >2dp (predicted 0 of 132; was 124 of 132) | Whether A's stated cost is real at all; whether § 7.3:1171 is stale |
| L2 | Confirm live `dbo.procurement_transactional` is currently `SMALLINT` / `FLOAT` | A's entire premise — the rollback DDL was never committed, only task-069's prose survives |
| L3 | Under B/B-minimal: what Delta type does bronze land after a real Copy run? | task-069 AC3 (must be read, not inferred) |
| L4 | Under B-as-framed: what does `fact_procurement.spend_eur` become, and does DirectLake accept it? | **Highest-risk unknown in B.** B-minimal removes this question entirely |
| L5 | Under B/B-minimal: does the incremental append succeed on the first scheduled run after the full-load rewrite? | A partial rewrite reproduces the outage one layer down |
| L6 | Under B/B-minimal: does `Total Spend EUR` move only by recovered precision? Baseline `sum_spend_eur = 3273776.03` (task-024) | Migration step 5 — movement beyond sub-cent means semantics changed, not just precision |

## Required irrespective of direction

- **AC4 has FIVE sites, not the one FR-080 names.** DEC-015 L84 (`4-byte float` → `double`), DEC-015 L85 (`int16/float32` → `int16/float64`), `fabric/data_quality_checks.Notebook:1204-1206` (*"UnitPriceEUR REAL -> double"* — a mapping Microsoft's own table contradicts), `azure/procurement.sql:18`, `azure/procurement_seed.sql:30`. Only the first two are gated; the rest are direct edits. **None is in task-069's `files_affected`.**
- **AC5** — spec L1142 and L1337 ("reproducible from the repo") must be narrowed or made true under both directions, via the merge queue.
- **`docs/architecture/data_sources.md:23,25`** carries the same `DECIMAL(18,2)` declaration as `docs/schemas/bronze_tables.md` and is **absent from task-069's `files_affected`**. Under A it would be left stale. FR-079 already records this file being missed once by MQ-002.
- **`docs/data_quality_framework.md:1171`**'s "124 of 132" figure should be re-measured, not carried forward.

## Where the evidence leans (not a selection)

- **On engineering merit: toward B/B-minimal.** Silver inheriting an upstream physical type *is* the defect; A ratifies it rather than fixing it.
- **On repo coherence: also toward B/B-minimal**, which is the counterintuitive finding. A is the zero-code option but the large-documentation option, and it leaves the quality suite carrying an expectation the project has both decided against and forbidden itself from relabelling.
- **Against B specifically:** it is work already declined once at the same scope, and it carries an unquantified DirectLake risk invisible to local testing.
- **B-minimal is the only formulation that is genuinely narrower than what was declined.** Presenting this fork as A vs B alone would ask Erik to re-decide something he has already decided; A vs B vs B-minimal is the honest framing.
