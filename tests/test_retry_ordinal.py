"""
Unit tests for pipeline_error_handler's retry-attempt derivation.

Follows the reference-implementation contract used by test_error_categorization.py
and test_key_generation.py: derive_retry_attempt is extracted from the *live*
notebook text via `ast`, so editing the notebook's harvest logic is what these
tests guard.

The anchor case is a real Fabric run. Orchestrator run 742ff1ff retried
bronzecopy_GlobalSupplyShares four times (retry 3, retryIntervalInSeconds 300),
and queryactivityruns returned retryAttempt: null on every row - so the
attempt ordinal must be derived by ranking same-activity rows by
activityRunStart, not read off the API field. These tests pin that derivation
against the verbatim start timestamps the run emitted, so a regression that
goes back to trusting retryAttempt (and logging every attempt as 0) cannot
recurcur silently. Without the ordinal, get_retry_effectiveness() filters
`retry_attempt > 0` and always returns empty - the exact dead-reporting-function
problem task-041 exists to remove.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HANDLER_NOTEBOOK = (
    REPO_ROOT / "fabric" / "pipeline_error_handler.Notebook" / "notebook-content.py"
)

RUN_ID = "742ff1ff-42d8-4fb6-9845-8c7a183c060d"

# Verbatim activityRunStart values for the four retried Copy attempts, captured
# from gold_pipeline_execution_log rows written by the run (the four FAILED
# bronzecopy_GlobalSupplyShares rows, start_ts column). Fabric emits 7
# fractional-second digits in activityRunStart; the SQL endpoint rounds to 6,
# so the trailing 0 is restored here to match the API's actual output shape.
COPY_STARTS = [
    "2026-07-27T22:46:58.3920860Z",  # attempt 0 (first try)
    "2026-07-27T22:52:18.7587080Z",  # attempt 1 (retry, +5:20)
    "2026-07-27T22:57:38.3710460Z",  # attempt 2 (retry, +5:20)
    "2026-07-27T23:02:57.1480680Z",  # attempt 3 (retry, +5:19)
]

# Four activities that succeeded on their only attempt, all started in the same
# second as the first Copy attempt (they run in parallel with it).
SUCCESS_STARTS = {
    "bronzecopy_EUSupplyShares": "2026-07-27T22:46:58.3892290Z",
    "bronze_WGI": "2026-07-27T22:46:58.3883040Z",
    "bronze_EPI": "2026-07-27T22:46:58.4037650Z",
    "bronze_procurement": "2026-07-27T22:46:58.3837880Z",
}


def load_derive_retry_attempt():
    """Extract derive_retry_attempt from the live notebook."""
    assert HANDLER_NOTEBOOK.exists(), f"Notebook not found: {HANDLER_NOTEBOOK}"
    tree = ast.parse(
        HANDLER_NOTEBOOK.read_text(encoding="utf-8"), filename=str(HANDLER_NOTEBOOK)
    )
    func = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "derive_retry_attempt":
            func = node
            break
    assert func is not None, "derive_retry_attempt not found in notebook"
    module = ast.Module(body=[func], type_ignores=[])
    ast.fix_missing_locations(module)
    ns = {}
    exec(compile(module, filename=str(HANDLER_NOTEBOOK), mode="exec"), ns)
    return ns["derive_retry_attempt"]


def load_parse_activity_ts():
    """Extract _parse_activity_ts (the production timestamp parser) from the live
    notebook. Fabric emits 7 fractional-second digits in activityRunStart;
    datetime.fromisoformat (pre-3.11) accepts at most 6, so the notebook truncates
    the fraction. Reusing that parser here — rather than reimplementing the parse
    inline — keeps this test pinned to the notebook's actual handling. The prior
    inline `datetime.fromisoformat(s.replace("Z", "+00:00"))` raised ValueError
    on Python 3.10 (CI matrix lower bound) and only passed on 3.11.
    """
    assert HANDLER_NOTEBOOK.exists(), f"Notebook not found: {HANDLER_NOTEBOOK}"
    tree = ast.parse(
        HANDLER_NOTEBOOK.read_text(encoding="utf-8"), filename=str(HANDLER_NOTEBOOK)
    )
    func = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_parse_activity_ts":
            func = node
            break
    assert func is not None, "_parse_activity_ts not found in notebook"
    module = ast.Module(body=[func], type_ignores=[])
    ast.fix_missing_locations(module)
    from datetime import datetime
    ns = {"datetime": datetime}
    exec(compile(module, filename=str(HANDLER_NOTEBOOK), mode="exec"), ns)
    return ns["_parse_activity_ts"]


@pytest.fixture(scope="module")
def derive():
    return load_derive_retry_attempt()


def _row(name, start, status="Failed"):
    return {
        "activityName": name,
        "pipelineRunId": RUN_ID,
        "activityRunStart": start,
        "status": status,
    }


def _starts_by_key(rows):
    """Reproduce the harvest's precompute, so the helper is exercised in isolation."""
    starts = {}
    for r in rows:
        key = (r.get("pipelineRunId"), r.get("activityName"))
        starts.setdefault(key, []).append(r.get("activityRunStart") or "")
    return starts


class TestRealRetriedCopy:
    """Anchored on the four retried Copy attempts from run 742ff1ff."""

    def test_four_attempts_get_ordinals_zero_through_three(self, derive):
        """The core regression: four attempts must log 0, 1, 2, 3 - not 0, 0, 0, 0."""
        rows = [_row("bronzecopy_GlobalSupplyShares", s) for s in COPY_STARTS]
        starts = _starts_by_key(rows)
        ordinals = sorted(derive(r, starts) for r in rows)
        assert ordinals == [0, 1, 2, 3]

    def test_ordinal_tracks_start_time_not_api_field(self, derive):
        """A null retryAttempt must not force the ordinal to 0.

        Every real row carries retryAttempt: null; the ordinal is derived from
        start_time ranking, so a retried row with null retryAttempt still gets
        a non-zero ordinal. This is the exact failure mode the fix removes.
        """
        rows = [_row("bronzecopy_GlobalSupplyShares", s) for s in COPY_STARTS]
        for r in rows:
            r["retryAttempt"] = None  # the API's actual value
        starts = _starts_by_key(rows)
        # The third attempt (by start time) must be ordinal 2 despite null.
        third = rows[2]
        assert derive(third, starts) == 2

    def test_iteration_order_does_not_affect_ordinal(self, derive):
        """queryactivityruns returns rows DESC by activityRunStart; a row's
        ordinal must depend only on its start time, not on loop order."""
        rows = [_row("bronzecopy_GlobalSupplyShares", s) for s in COPY_STARTS]
        starts = _starts_by_key(rows)
        forward = {r["activityRunStart"]: derive(r, starts) for r in rows}
        reverse = {r["activityRunStart"]: derive(r, starts) for r in reversed(rows)}
        assert forward == reverse
        assert forward == dict(zip(COPY_STARTS, [0, 1, 2, 3]))

    def test_spacing_matches_retry_interval(self):
        """Documents *why* the start times are distinct: retryIntervalInSeconds=300.

        Guards against someone 'normalising' the timestamps and collapsing the
        attempts. The ~5:20 spacing (300s retry interval + the failed attempt's
        own duration) is what makes each attempt a distinct activityRunStart.

        Parses via the notebook's own _parse_activity_ts (Fabric emits 7
        fractional-second digits; pre-3.11 datetime.fromisoformat rejects them).
        """
        parse = load_parse_activity_ts()
        parsed = [parse(s) for s in COPY_STARTS]
        gaps = [(b - a).total_seconds() for a, b in zip(parsed, parsed[1:])]
        assert all(300 <= g <= 360 for g in gaps), gaps


class TestSingleAttemptActivities:
    """Activities that ran once (the clean-run case) must map to ordinal 0."""

    @pytest.mark.parametrize("name,start", list(SUCCESS_STARTS.items()))
    def test_success_activities_are_attempt_zero(self, derive, name, start):
        rows = [_row(name, start, status="Succeeded")]
        starts = _starts_by_key(rows)
        assert derive(rows[0], starts) == 0

    def test_parallel_activities_do_not_inflate_each_other(self, derive):
        """Four activities starting in the same second must each be ordinal 0.

        They are different activityName values, so they never share a key - the
        ordinal is per-activity, not per-run. A bug that keyed on run_id alone
        would rank them 0..3 by microsecond and log phantom retries.
        """
        rows = [
            _row(name, start, status="Succeeded")
            for name, start in SUCCESS_STARTS.items()
        ]
        starts = _starts_by_key(rows)
        assert all(derive(r, starts) == 0 for r in rows)


class TestMixedRun:
    """The full harvest shape: 4 retried failures + 4 single-attempt successes."""

    def test_every_activity_gets_a_correct_ordinal(self, derive):
        rows = [_row("bronzecopy_GlobalSupplyShares", s) for s in COPY_STARTS]
        rows += [
            _row(name, start, status="Succeeded")
            for name, start in SUCCESS_STARTS.items()
        ]
        starts = _starts_by_key(rows)
        copy_ordinals = {
            r["activityRunStart"]: derive(r, starts)
            for r in rows
            if r["activityName"] == "bronzecopy_GlobalSupplyShares"
        }
        assert copy_ordinals == dict(zip(COPY_STARTS, [0, 1, 2, 3]))
        success_ordinals = {
            r["activityName"]: derive(r, starts)
            for r in rows
            if r["activityName"] in SUCCESS_STARTS
        }
        assert success_ordinals == {name: 0 for name in SUCCESS_STARTS}

# =============================================================================
# Final-outcome collapsing (task-051)
# =============================================================================
# queryactivityruns returns one row PER ATTEMPT. The handler's re-raise
# originally fired on the presence of any Failed row, so an activity the
# pipeline retried into success reported the whole run as Failed. These tests
# pin the corrected semantics: the raise keys off each activity's FINAL attempt,
# while every attempt stays in the log for get_retry_effectiveness().


def load_summarize_final_outcomes():
    """Extract summarize_final_outcomes from the live notebook.

    _TERMINAL_STATUS is pulled from the notebook too rather than restated here,
    so the mapping stays single-sourced (same reasoning as load_parse_activity_ts
    reusing the production timestamp parser).
    """
    assert HANDLER_NOTEBOOK.exists(), f"Notebook not found: {HANDLER_NOTEBOOK}"
    tree = ast.parse(
        HANDLER_NOTEBOOK.read_text(encoding="utf-8"), filename=str(HANDLER_NOTEBOOK)
    )
    func = None
    terminal_assign = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "summarize_final_outcomes":
            func = node
        elif isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_TERMINAL_STATUS" for t in node.targets
        ):
            terminal_assign = node
    assert func is not None, "summarize_final_outcomes not found in notebook"
    assert terminal_assign is not None, "_TERMINAL_STATUS not found in notebook"
    module = ast.Module(body=[terminal_assign, func], type_ignores=[])
    ast.fix_missing_locations(module)
    ns = {}
    exec(compile(module, filename=str(HANDLER_NOTEBOOK), mode="exec"), ns)
    return ns["summarize_final_outcomes"]


@pytest.fixture(scope="module")
def summarize():
    return load_summarize_final_outcomes()


SELF_NAME = "pipeline_error_handler"

# The 2026-08-03 14:08 orchestrator run: bronze_WGI failed on GOV_WGI_GE.EST
# (pages 3 then 4) and succeeded on the third attempt. Durations 16m47s, 3m54s
# and 4m7s are as recorded in task-036's WGI RELIABILITY FINDING note; the start
# timestamps below are RECONSTRUCTED from those durations rather than captured
# verbatim from the API, since only the durations were recorded at the time.
# Only their ordering is load-bearing for these tests.
WGI_ATTEMPTS = [
    ("2026-08-03T14:08:00.0000000Z", "Failed"),
    ("2026-08-03T14:24:50.0000000Z", "Failed"),
    ("2026-08-03T14:28:47.0000000Z", "Succeeded"),
]


def _outcome_row(name, start, status, message=None):
    """A queryactivityruns row. `error` is present even on success, as a dict of
    empty strings - the notebook's cell header records this; branching on a
    truthy `error` is exactly the bug that shape causes."""
    return {
        "activityName": name,
        "pipelineRunId": RUN_ID,
        "activityRunStart": start,
        "status": status,
        "error": {"message": message or "", "errorCode": "", "failureType": ""},
    }


class TestRetriedThenSucceeded:
    """The regression this function exists to prevent."""

    def test_retried_into_success_is_not_a_run_failure(self, summarize):
        rows = [_outcome_row("bronze_WGI", s, st) for s, st in WGI_ATTEMPTS]
        final_failures, recovered = summarize(rows, SELF_NAME)
        assert final_failures == []
        assert recovered == [("bronze_WGI", 2)]

    def test_iteration_order_does_not_change_the_verdict(self, summarize):
        rows = [_outcome_row("bronze_WGI", s, st) for s, st in WGI_ATTEMPTS]
        for ordering in (rows[::-1], [rows[1], rows[2], rows[0]]):
            final_failures, recovered = summarize(ordering, SELF_NAME)
            assert final_failures == []
            assert recovered == [("bronze_WGI", 2)]

    def test_a_green_run_reports_nothing(self, summarize):
        rows = [
            _outcome_row(name, start, "Succeeded")
            for name, start in SUCCESS_STARTS.items()
        ]
        assert summarize(rows, SELF_NAME) == ([], [])


class TestGenuineFailure:
    """A real failure must still fail the run - the DQ gate depends on it."""

    def test_single_failed_attempt_is_a_final_failure(self, summarize):
        rows = [_outcome_row("data_quality_checks", COPY_STARTS[0], "Failed", "DQ gate")]
        final_failures, recovered = summarize(rows, SELF_NAME)
        assert final_failures == [("data_quality_checks", "DQ gate")]
        assert recovered == []

    def test_exhausted_retries_are_a_final_failure(self, summarize):
        rows = [
            _outcome_row("bronzecopy_GlobalSupplyShares", s, "Failed", "timeout")
            for s in COPY_STARTS
        ]
        final_failures, recovered = summarize(rows, SELF_NAME)
        assert final_failures == [("bronzecopy_GlobalSupplyShares", "timeout")]
        assert recovered == []

    def test_success_before_a_later_failure_still_fails(self, summarize):
        """Ordering, not mere presence of a Succeeded row, decides the outcome."""
        rows = [
            _outcome_row("bronze_WGI", COPY_STARTS[0], "Succeeded"),
            _outcome_row("bronze_WGI", COPY_STARTS[1], "Failed", "late failure"),
        ]
        final_failures, _ = summarize(rows, SELF_NAME)
        assert final_failures == [("bronze_WGI", "late failure")]

    def test_empty_error_message_becomes_none_not_blank(self, summarize):
        rows = [_outcome_row("bronze_EPI", COPY_STARTS[0], "Failed")]
        assert summarize(rows, SELF_NAME) == ([("bronze_EPI", None)], [])

    def test_a_real_failure_alongside_a_recovery_is_still_raised(self, summarize):
        rows = [_outcome_row("bronze_WGI", s, st) for s, st in WGI_ATTEMPTS]
        rows.append(_outcome_row("data_quality_checks", COPY_STARTS[3], "Failed", "DQ"))
        final_failures, recovered = summarize(rows, SELF_NAME)
        assert final_failures == [("data_quality_checks", "DQ")]
        assert recovered == [("bronze_WGI", 2)]


class TestRowFiltering:
    def test_self_activity_is_excluded(self, summarize):
        """The handler sees itself mid-run; without the skip it logs a phantom."""
        rows = [
            _outcome_row(SELF_NAME, COPY_STARTS[0], "Failed", "self"),
            _outcome_row("bronze_EPI", COPY_STARTS[1], "Succeeded"),
        ]
        assert summarize(rows, SELF_NAME) == ([], [])

    @pytest.mark.parametrize("status", ["InProgress", "Queued", "Skipped", "Cancelled"])
    def test_non_terminal_rows_are_ignored(self, summarize, status):
        rows = [_outcome_row("bronze_EPI", COPY_STARTS[0], status)]
        assert summarize(rows, SELF_NAME) == ([], [])

    def test_non_terminal_last_row_does_not_mask_an_earlier_failure(self, summarize):
        """A Cancelled row after a Failed one must not read as recovery."""
        rows = [
            _outcome_row("bronze_EPI", COPY_STARTS[0], "Failed", "boom"),
            _outcome_row("bronze_EPI", COPY_STARTS[1], "Cancelled"),
        ]
        final_failures, recovered = summarize(rows, SELF_NAME)
        assert final_failures == [("bronze_EPI", "boom")]
        assert recovered == []
