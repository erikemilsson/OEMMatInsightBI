---
id: DEC-019
title: Only HTTP 401/403/404 stay permanent for the World Bank API; 400 and 408 are transient
status: approved
category: architecture
created: 2026-08-20
decided: 2026-08-20
decided_by: user
related:
  tasks: ["075", "066"]
  decisions: ["DEC-017", "DEC-018"]
implementation_anchors:
  - file: "fabric/bronze_ingest_wgi.Notebook/notebook-content.py"
    description: "HTTP_TRANSIENT_STATUSES = {400, 408, 429} plus 5xx in is_transient_request_error(); every other status with a status line fails closed as permanent"
  - file: "tests/test_wgi_retry.py"
    description: "Per-status coverage: 404/401/403 raise with exactly 1 HTTP call and zero backoff sleeps; 400/408 retry within budget; exhausted-budget path still raises"
inflection_point: false
spec_revised: true
spec_revised_date: 2026-08-21
blocks: []
---

# Only HTTP 401/403/404 stay permanent for the World Bank API; 400 and 408 are transient

## Select an Option

Mark your selection by checking one box:

- [x] Option A: Only 401/403/404 permanent; 400 and 408 transient; unclassified fails closed
- [ ] Option B: Retry all 4xx
- [ ] Option C: Keep task-066's rule (any 4xx other than 429 is permanent)

## Background

task-066 classified "any 4xx other than 429" as permanent. The reasoning was sound at the time: the World Bank API reports bad input **in-band** as HTTP 200 with a one-element message body, so a 4xx status ought to mean a genuinely malformed request that retrying cannot fix.

That premise is now falsified by observation. On the **2026-08-17 04:00 scheduled run**, `bronze_wgi` received HTTP 400 on `GOV_WGI_CC.EST` page 1 and raised the permanent-error path. The identical URL, unchanged, succeeded three minutes later. A 400 that succeeds on replay is by definition transient — it is gateway noise, not malformed input. The message "this needs a human" was wrong in the only case it has ever fired.

The correction must not overshoot: retrying *all* 4xx would restore the unbounded-retry behaviour task-066 deliberately removed.

## Options Comparison

| Criteria | Option A | Option B (all 4xx) | Option C (status quo) |
|----------|----------|--------------------|-----------------------|
| Handles the observed spurious 400 | Yes | Yes | No — the defect |
| Fails fast on unrecoverable errors | Yes (401/403/404) | No | Yes |
| Restores unbounded-retry behaviour | No | Yes — regression | No |
| Unclassified statuses | Fail closed | Retried | Permanent |
| Overall | **Selected** | Rejected | Rejected |

## Option Details

### Option A: Only 401/403/404 permanent; 400 and 408 transient

**Description:** `HTTP_TRANSIENT_STATUSES = {400, 408, 429}` alongside `500 <= status <= 599`. Everything else carrying a status line fails closed as permanent.

**Strengths:**
- Targets the falsified premise precisely, without widening the retry surface
- 401/403 stay permanent: auth genuinely needs a human and waiting cannot fix it (and this API is unauthenticated, so they should be unreachable at all)
- 404 stays permanent: a retired or renamed indicator path is not recoverable by retry — the World Bank re-coded WGI once already, in 2026-07
- Unclassified statuses (409/418/422/451) fail closed, preserving task-066's bounded-retry guarantee

**Weaknesses:**
- A genuine malformed-request 400, were one ever possible from this host, would now burn the full 8-attempt budget before going red

### Option B: Retry all 4xx

**Weaknesses:**
- Restores exactly the unbounded-retry behaviour task-066 removed
- An auth failure or retired indicator would consume the full budget every run

### Option C: Keep task-066's rule

**Weaknesses:**
- This *is* the defect. Its premise is falsified by the 08-17 replay.

## Your Notes & Constraints

*Add any constraints, preferences, or context that should inform this decision. This section is yours — Claude reads it but never overwrites it.*

**Constraints:**
-

**Questions:**
-

## Decision

**Selected:** Option A — Only 401/403/404 permanent; 400 and 408 transient; unclassified fails closed.

**Rationale:**
The World Bank API reports bad input in-band as HTTP 200, so a 400 from this host cannot mean "malformed request" — which is what makes the 08-17 replay decisive rather than merely suggestive. 401/403 and 404 remain permanent on the same reasoning that survives the falsification: they name conditions retrying cannot change. Failing closed on unclassified statuses keeps the bounded-retry property task-066 established, so the fix corrects the premise without reverting the guarantee.

## Trade-offs

**Gaining:**
- The observed spurious-400 class of failure no longer produces a false "needs a human" page
- Classification is grounded in measured API behaviour rather than inference

**Giving Up:**
- If this host ever returns a true malformed-request 400, it now costs the full 8-attempt budget before going red

## Impact

**Implementation Notes:**
Shipped in task-075. Verified locally: `tests/test_wgi_retry.py` grew 29 → 40 tests, asserting exactly 1 HTTP call and zero backoff sleeps on the permanent statuses, and bounded retry on the transient ones. A negative control (temporarily reverting the status set) failed the expected tests, so the pins are load-bearing rather than vacuous.

**Affected Areas:**
- `fabric/bronze_ingest_wgi.Notebook/notebook-content.py`
- `tests/test_wgi_retry.py`
- `docs/epi_wgi_ingestion.md` (classification table)
- Related tasks: task-075, task-066

**Risks:**
- Low. The change narrows what is called permanent; the bounded budget still caps every retried path.
