---
id: DEC-005
title: gold_gap_registry lifecycle and occurrence semantics — set-to-current, reopen-as-Open, coarse gap_type
status: proposed
category: architecture
created: 2026-07-23
decided:
recommended_by: implement-agent
recommendation_date: 2026-07-23
related:
  tasks: [task-027, task-033]
  decisions: []
implementation_anchors:
  - fabric/silver-to-gold2.Notebook/notebook-content.py
inflection_point: false
spec_revised:
spec_revised_date:
blocks: []
---

# gold_gap_registry lifecycle and occurrence semantics

> **Why one record and not three.** implement-agent surfaced three separate decisions while executing
> task-027. They are recorded together because they are one contract on one table — the registry's
> lifecycle — and they interact: set-to-current only makes sense because the audit source is a
> snapshot, the reopen path only works because `Open` stays the single sweepable status, and the
> coarse `gap_type` is what keeps one remediation closing one row. Splitting them would hide those
> couplings. Each is tagged below with **whether task-027 delegated the choice**, because that
> determines how much of this actually needs your attention.
>
> **Only sub-decision 3 needs a real look.** Sub-decisions 1 and 2 were explicitly delegated by
> task-027's own acceptance criteria — the criteria enumerate the options and instruct the
> implementer to pick and document one. Ratifying those is a formality. Sub-decision 3 was not
> delegated and is the one genuine judgement call here.

## Select an Option

Mark your selection by checking one box:

- [ ] Ratify all three as implemented  *(recommended)*
- [ ] Ratify 1 and 2, revisit 3 (registry `gap_type` granularity)
- [ ] Revisit — I want to change one or more

*Check one box above, then fill in the Decision section below.*

---

## Sub-decision 1 — `total_occurrences` means current-run occurrences, not lifetime cumulative

**Delegated by task-027 criterion 4** ("either store per-run occurrence count keyed by run, or
set-to-current instead of increment, or increment only when a new refresh_timestamp is involved AND
document that it counts run-sightings. Chosen semantics stated in a code comment").

**Selected:** set-to-current on every MERGE. Reasoning recorded in a block comment above the MERGE.

**Why:** `gold_unmapped_*_audit` are rebuilt from all silver data on every run, so incrementing
re-adds the same rows each time — ten runs over a ten-occurrence value reported 100, i.e.
occurrences × runs, and it broke the medallion doc's idempotency claim. Set-to-current is the only
honest reading of a snapshot source and is idempotent across re-runs on unchanged data, which is
what criterion 6 tests.

**Rejected:** the append model (changes the registry grain and the 11-column TMDL contract);
increment-on-new-timestamp ("run sightings" is a number nobody asked a business question about,
while gap *age* — the doc's actual business question — is already tracked losslessly by
`first_seen`/`last_seen`).

**Doc consequence:** `data_quality_architecture.md` line ~298 still says "cumulative count". Routed
to task-033 (FR-017).

---

## Sub-decision 2 — a reopened gap returns to `Open` with a note, rather than getting a `Reopened` status

**Delegated by task-027 criterion 3** ("transitions to 'Reopened' (or back to 'Open' with a note)").

**Selected:** return to `Open`, clear `resolution_date`, write a dated reopen note preserving the
prior resolution text (truncated to 180 chars so repeated cycles cannot grow unbounded).

**Why:** `Reopened` would be a new enum value outside the documented set (Open / In Progress /
Resolved / Excluded), requiring a docs change — and *every* existing consumer filters
`current_status = 'Open'`, including the auto-resolve sweep in this same function, the "Oldest Open
Gaps" report query and the DAX layer. A `Reopened` gap would never be swept again and would sit in
that status forever unless all of them were updated too. Reusing `Open` keeps one lifecycle path;
the dated note plus preserved prior resolution text is what distinguishes a reopened gap from a
never-resolved one.

---

## Sub-decision 3 — registry `gap_type` is keyed on the coarse dimension  ⚠️ **not delegated — your call**

**Not covered by any acceptance criterion.** This is an inferred design choice.

**Selected:** the audit tables emit *both* a fine-grained `unmapped_type`
(`material` / `hq_country` / `prod_country`) and a coarse `gap_dimension` (`material` / `country`);
the registry reads `gap_dimension` as `gap_type`. So an hq_country miss and a prod_country miss of
the *same value* collapse into one registry gap.

**Why:** the remediation for a bad country name is one country alias regardless of which column it
appeared in, so fine-grained keying would create two registry rows that a single fix closes —
double-counting open gaps. `data_quality_architecture.md` also keys `gap_type` on the coarse
dimension. Emitting `gap_dimension` from the audit tables rather than deriving it in the registry
keeps criterion 2 intact: the registry still reads columns directly and infers nothing, and the
audit table stays the single place that knows which dimension failed. The fine-grained
`unmapped_type` is retained on the audit rows because criterion 1 requires it and triage needs it.

**The case against, so you can weigh it:** if you ever want to know *"is this country name failing
on the HQ side, the production side, or both?"* at registry level, that question now requires
joining back to the audit table. The information is not lost, but it is one level further away.

## Your Notes & Constraints

*This section is yours — Claude reads it but never overwrites it.*

**Constraints:**
-

**Questions:**
-

## Decision

**Selected:** *(awaiting ratification)*

**Rationale:**


## Trade-offs

**Gaining:**
- An idempotent registry whose occurrence count survives re-runs, a working reopen path, and one
  registry row per remediation.

**Giving Up:**
- Lifetime occurrence totals (recoverable only from `first_seen`/`last_seen` plus per-run history,
  which is not stored).
- Registry-level visibility into *which* country column failed (available via the audit table).

## Impact

**Implementation Notes:**
Implemented under task-027 ahead of ratification; task-027 is Awaiting Verification. Sub-decisions 1
and 3 both have doc consequences routed to task-033 (FR-017, FR-018).
