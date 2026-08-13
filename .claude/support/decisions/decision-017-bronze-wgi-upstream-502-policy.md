---
id: DEC-017
title: bronze_wgi upstream-502 policy — classified bounded retry plus fail-closed completeness guards
status: approved
category: architecture
created: 2026-08-13
decided: 2026-08-13
decided_by: implement-agent
related:
  tasks: ["066"]
  decisions: []
implementation_anchors:
  - file: "fabric/bronze_ingest_wgi.Notebook/notebook-content.py"
    description: "is_transient_request_error() classifies before any retry (5xx/429/transport transient, all other 4xx permanent and raised immediately); retry_delay() honours Retry-After; budget widened 5→8 attempts, cap 60→120s; four completeness guards added before the mode('overwrite') write"
inflection_point: false
spec_revised: false
blocks: []
---

# bronze_wgi upstream-502 policy — classified bounded retry plus fail-closed completeness guards

## Select an Option

Mark your selection by checking one box:

- [x] Option A: Classified bounded retry (5xx/429/transport retried, other 4xx raised immediately, Retry-After honoured) + 8 attempts/120s cap + four completeness guards before the overwrite
- [ ] Option B: Keep-last-good-snapshot — on fetch failure, leave the existing bronze_wgi table in place and let the pipeline continue green
- [ ] Option C: Leave the task-050 retry logic as-is and accept the ~2-in-9 scheduled-run failure rate as upstream noise

*Decided by implement-agent during task-066, 2026-08-13 — an implementation-time decision per `.claude/agents/implement-agent.md § "Decisions Made During Implementation"`, not a pre-research checkbox decision. Flagged to Erik for awareness; not blocking.*

## Background

task-066 was opened to diagnose intermittent HTTP 502s on `bronze_wgi` scheduled runs (reported as "2 of the last 5" on 2026-08-11, explicitly flagged as an unverified session observation). The task required (a) re-measuring the real failure rate with a positive control against Fabric's `queryactivityruns` API, (b) establishing the 502's origin with evidence before proposing any fix, and (c) ensuring a genuinely permanent failure still fails the pipeline loudly rather than being papered over by a retry.

Re-measurement over the 9 scheduled runs since the pipeline's 06:00 schedule went live confirmed the count was accurate at the time it was recorded (2 failures in the 5 runs 08-07..08-11), with a positive control proving the query call can distinguish "genuinely no rows" from "probe is broken" (same call with/without the mandatory date window returns 9-10 activity rows vs. an empty 200, respectively). Origin was established as the World Bank API's own gateway — not Fabric's HTTP path and not the notebook's request construction — via three independent lines of evidence: no Fabric HTTP connector sits in the path (it's a direct `requests.get` from the notebook's Spark driver), the exact failing URL replays successfully minutes later, and the failing indicator/page differs on every occurrence (a malformed request would fail deterministically on the same page every time). Auth expiry and rate limiting were both ruled out as alternative 5xx-presenting causes (the API is unauthenticated; a rate limit would present as 429, never observed).

While instrumenting the loud-failure requirement (AC4), the investigation surfaced a second, independent defect: two `break`-on-anomaly code paths in `fetch_indicator` could exit pagination early on an unexpected response shape and let the run complete GREEN over a `mode("overwrite")` write — silently destroying a good snapshot. This is reachable (the World Bank API reports invalid input in-band as HTTP 200, and WGI's indicator codes were already renamed once, 2026-07-26) and invisible to the existing DQ layer (bronze_wgi's row-count band is 50–500,000 against a normal load of ~31,000 rows — losing one of six indicators, ~5,000 rows, stays inside the band).

## Options Comparison

| Criterion | A (classified retry + guards) | B (keep-last-good-snapshot) | C (leave as-is) |
|-----------|---|---|---|
| Matches AC4 ("permanent failure fails loudly, no silent partial load") | **Yes — the whole point** | **No — the opposite design** | No — the pre-existing gap remains |
| Matches AC3 ("retry only if genuinely transient upstream 5xx") | **Yes — classifies before retrying** | N/A (no retry logic change) | No — old code retried indiscriminately, including permanent 4xx |
| Handles the annual-cadence argument (WGI updates yearly; a same-day snapshot is functionally identical) | Does not exploit this — every failure still fails the run | **Exploits it directly** — an outage day just serves yesterday's data | N/A |
| Risk of silent data staleness | None introduced | **Real** — a genuine multi-day upstream outage could go unnoticed | Unchanged (retry-budget risk only) |
| Scope | Retry classifier + backoff tuning + 4 guards, in-scope for task-066 | A design reversal of "fail loudly" — arguably contradicts the task's own AC4 | Zero implementation, but leaves both defects live |

## Option Details

### Option A: Classified bounded retry + completeness guards (SELECTED)

**Description:** `is_transient_request_error()` classifies the response before any retry — 5xx, 429, and transport-level errors (timeout, connection reset, truncated body) are transient; every other 4xx is permanent and raised immediately with a distinct message. `retry_delay()` honours a `Retry-After` header when present rather than a blind exponential schedule. The retry budget widens from 5 attempts/60s cap to 8 attempts/120s cap (measured against an observed 41-minute degraded window where most requests were still succeeding). Four completeness guards run before the `mode("overwrite")` write: raise on an in-band HTTP-200 error body, raise on a null record set, verify pagination completeness against the API's own declared `total` per indicator, and verify all 6 indicators are present immediately before the overwrite.

**Strengths:**
- Directly satisfies AC3 (retry only transient causes) and AC4 (permanent failure fails loudly, no silent partial load) as literally specified in the task
- Closes the independently-discovered `break`-on-anomaly hole, which is a real latent risk regardless of the 502 investigation
- Retry budget is justified by measurement (the 41-minute window), not guesswork

**Weaknesses:**
- Does not reduce nuisance failures from a genuine multi-day upstream outage — the pipeline still fails loudly every day until the API recovers, even though WGI itself hasn't changed
- Adds code complexity (classifier + guards) to a notebook that previously had a simpler (if less correct) retry loop

**Research Notes:** Live-measured against the actual World Bank API and Fabric run history during task-066 (2026-08-13) — see task-066's `verification_history` / implementation notes for the full evidence trail.

### Option B: Keep-last-good-snapshot

**Description:** On a fetch failure (after exhausting retries), leave the existing `bronze_wgi` Delta table untouched instead of failing the run, and let the pipeline continue as green. Justified by WGI's annual update cadence — a snapshot that is one day "stale" during an outage is functionally identical to the correct data.

**Strengths:**
- Eliminates nuisance pipeline failures during multi-day upstream outages, since WGI rarely changes day to day
- Arguably the more "production-grade" behavior for a slowly-changing reference dataset

**Weaknesses:**
- Directly contradicts this task's AC4 ("a permanent failure must still fail the run loudly... do not let a bounded retry turn a real outage into a silent partial load") — this is a design reversal, not an implementation detail, and converts any outage (transient or permanent) into a silent green run
- A genuinely permanent upstream change (e.g., another indicator rename) would be masked indefinitely rather than surfaced
- Changes user-facing pipeline semantics (a real failure now looks identical to success) — judged to need Erik's explicit sign-off rather than being an implementation-time call

**Research Notes:** Not implemented. Recorded here because it is a real, defensible alternative that a future session might reasonably propose — see `issues_discovered` in task-066's implementation report (flagged for human, not auto-actioned).

### Option C: Leave as-is

**Description:** Ship no retry/guard changes; treat the ~2-in-9 measured failure rate as acceptable upstream noise given task-050's existing (indiscriminate) retry.

**Strengths:**
- Zero implementation risk

**Weaknesses:**
- Leaves the task's own AC2/AC3 unmet (fix must match diagnosis; old code retried 4xx indiscriminately, which the investigation showed is wrong)
- Leaves the independently-discovered silent-partial-load hole live and undetected by the DQ layer
- Does not close task-066, which explicitly required either a fix or a demonstrated honest null result — and this was not a null result

## Your Notes & Constraints

*Add any constraints, preferences, or context that should inform this decision. This section is yours — Claude reads it but never overwrites it.*

**Constraints:**
-

**Questions:**
-

## Decision

**Selected:** Option A — Classified bounded retry (5xx/429/transport retried, other 4xx raised immediately, Retry-After honoured) + 8 attempts/120s cap + four completeness guards before the overwrite.

**Rationale:**
The measured evidence supports retrying this specific 502 (it is provably gateway-level: unauthenticated API, bad input reported in-band as HTTP 200, failing page differs per attempt, same URL healthy on replay), and the old 75-second budget demonstrably under-covered a window in which most requests were succeeding. Option B is attractive because WGI is annual data, so a day-old snapshot is functionally identical — but it directly contradicts this task's requirement that a permanent failure fail loudly, and would convert a real upstream outage into a silent green run, so it is Erik's design decision rather than an implementation detail (see `issues_discovered`, flagged for human, in task-066's report). Option C was rejected because the same investigation surfaced a genuine silent-partial-load hole (the two break-on-anomaly paths over a `mode("overwrite")` write) that is independent of the 502 and would have degraded `gold_supply_risk`'s governance half indistinguishably from the legitimate Taiwan gap.

## Trade-offs

**Gaining:**
- A retry policy that only retries what's genuinely worth retrying, and fails immediately (with a clear message) on anything else
- A structural guard against a previously-undetected silent-partial-load defect, independent of the 502 investigation that found it
- A widened, measurement-justified retry budget instead of one that was empirically too small

**Giving Up:**
- Immunity to nuisance pipeline failures during a genuine multi-day upstream outage — Option B's benefit was explicitly not taken, so the pipeline will keep failing loudly (correctly, but noisily) for as long as the outage lasts

## Impact

**Implementation Notes:**
Shipped in task-066 as uncommitted working-tree changes (not committed or pushed, per the task's constraint). Erik's half is to deploy and observe subsequent scheduled runs to confirm the failure no longer recurs (or now surfaces correctly if the underlying cause were ever non-transient).

**Affected Areas:**
- `fabric/bronze_ingest_wgi.Notebook/notebook-content.py`
- `docs/epi_wgi_ingestion.md` (new "Failure Handling in bronze_ingest_wgi" section)
- `tests/test_wgi_retry.py` (new, 29 assertions)
- Related tasks: task-066

**Risks:**
- If a future upstream outage genuinely spans multiple days, the pipeline will fail every scheduled run until it resolves — by design under Option A, but worth Erik knowing in advance rather than discovering during an incident
- The DQ row-count band (50–500,000) that failed to catch the original silent-partial-load risk is unchanged by this decision — task-066's `issues_discovered` flags it as a candidate follow-up task
