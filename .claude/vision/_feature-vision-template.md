---
# FEATURE VISION SCAFFOLD — copy to `.claude/vision/<feature-slug>.md`, fill in, delete these comment lines.
# `_`-prefixed files are scaffolds, not visions: `/iterate distill` and other consumers skip them.
# A vision is the development HUB for a larger feature: develop it broadly here (repeated /grill + /shakedown
# passes) until tight, then graduate to the spec via /iterate. See DEC-023 + .claude/rules/spec-workflow.md.
status: vision            # lifecycle: vision → distilled-to-spec → historical
captured: YYYY-MM-DD
author:                   # you (+ "(dictated)" if relevant)
supersedes:               # vision(s) this replaces — keeps the vision graph acyclic, no orphans
predecessors:             # complementary visions this builds on (NOT superseded)
scope_in:                 # one line: what this feature IS
scope_out:                # one line: what it deliberately is NOT (the boundary)
---

# <Feature name>

## Thesis

<One-line north-star — the single sentence this whole feature serves.>

**The gap it closes:** <what's missing / wrong today.>
**Non-negotiables:** <hard constraints this must respect.>

<!-- GENERAL-FIRST: keep this section conceptual — the "what & why" lives here; mechanism and repo-specifics go in
     the §-sections below and deepen as the vision matures. Don't dive into file/field internals before the frame is set. -->

## §1 — <Subsystem / thread name>

**Maturity:** 🟡 DRAFTED
<!-- ladder: 🟡 DRAFTED (sketched, not probed) · 🔵 RESEARCHED (grilled/shaken-down, scope settled, not yet specced) · 🟢 SHIPPED (in spec + built + verified) -->
**Evidence:** <what justifies the banner — corpus refs / commits / test counts. Citable facts, not a feeling. (blank while DRAFTED)>

<What this thread is. One conceptual paragraph first; specifics below only as the thread matures.>

## §2 — <Subsystem / thread name>

**Maturity:** 🟡 DRAFTED
**Evidence:**

<…>

## Open forks

<!-- THE SINGLE canonical place for unresolved questions. Don't scatter forks across sections — one fork = one row.
     Kind: [structure] = changes the model · [calibration] = a tuning/dose question within the model. -->

| # | Fork (the open question) | Thread | Kind | Probe tool | Status |
|---|---|---|---|---|---|
| F1 | <question> | §1 | [structure] | `/shakedown` | ⏳ pending |
| F2 | <question> | §2 | [calibration] | `/grill` | ✅ resolved → DEC-### (YYYY-MM-DD) |

## Status map

| Thread | Maturity | Next step | Tool |
|---|---|---|---|
| §1 | 🟡 DRAFTED | probe the open forks | `/shakedown` |
| §2 | 🟡 DRAFTED | sharpen scope | `/grill` |

## Evidence index

<!-- Where each thread LIVES. Cite corpora / decisions / code — never copy their contents in here. -->

| Thread | Vision § | Spec § | Code / config | Corpus / Decision |
|---|---|---|---|---|
| §1 | §1 | — (not yet specced) | — | `shakedowns/<slug>-YYYY-MM-DD.md` |

## Amendments

<!-- Structured refinement log — one row per pass (replaces prose amendment blocks). -->

| Date | By | Change | Verified | Source |
|---|---|---|---|---|
| YYYY-MM-DD | <you> | <what changed, specifically> | <test/shakedown evidence, or —> | `<corpus / DEC ref>` |

---

<!-- IMMUTABILITY (DEC-016 as amended by DEC-023): a vision is EDITABLE while developing (maturity 🟡/🔵).
     Once a thread graduates to spec (maturity 🟢), it is READ-ONLY here — further changes route through /iterate
     against the spec, not by editing this vision. Set `status: distilled-to-spec` when fully graduated. -->
