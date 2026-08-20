"""
Unit tests for bronze_ingest_wgi's retry classification and completeness guards.

Follows the reference-implementation contract used by test_error_categorization.py
and test_key_generation.py: the functions are extracted from the *live* notebook
text via `ast`, so editing the notebook's retry policy is what these tests guard.

ANCHOR CASE (task-066). Over the 9 scheduled runs between 2026-08-05 and 2026-08-13,
bronze_wgi failed the whole run on 2 of them (2026-08-07 run a80a0c3c, 2026-08-09 run
7e3f55df), each exhausting all 3 notebook attempts with:

    RuntimeError: World Bank API call failed for GOV_WGI_PV.EST (page 3) after 5
    attempts: 502 Server Error: Bad Gateway for url: https://api.worldbank.org/...

Two properties are pinned here, and they pull in opposite directions on purpose:

  1. A transient upstream 5xx must be RETRIED (that 502 is a gateway wobble — the
     same URL returned HTTP 200 in 3.2s on 2026-08-13, and a 40-request burst across
     all 6 indicators returned 40x 200).

  2. A permanent error must NOT be retried and must NOT produce a partial load. The
     World Bank API reports bad input IN-BAND — HTTP 200 with a one-element body
     `[{"message":[{"id":"120","key":"Invalid value",...}]}]`, verified live
     2026-08-13 — so the 200 path is where the permanent failures actually arrive.
     That branch used to `break` out of pagination and let the run go GREEN with an
     indicator silently missing, over a mode("overwrite") write.

SECOND ANCHOR CASE (task-075). On the 2026-08-17 04:00 scheduled run
(cb9be8a4-4067-4045-a9cd-35d391e2ed55) bronze_wgi attempt 1 Failed at 04:00:03 raising
task-066's own permanent path on an HTTP 400 for GOV_WGI_CC.EST page 1 — and attempt 2
Succeeded at 04:03:22 on the byte-identical URL. Two defects at once:

  3. A 400 that succeeds on retry is transient by definition. Because this API reports
     bad input in-band as HTTP 200 (property 2), a 400 here cannot mean "malformed
     request" — task-066's premise was sound and is falsified by the replay. 400 and 408
     therefore join 5xx/429/transport; 401/403/404 stay permanent; everything else fails
     closed as permanent, because retrying ALL 4xx would restore the unbounded retry
     task-066 removed.

  4. The classification was INERT. The bronze_wgi activity carried policy.retry=2, so the
     notebook's "not retried, this needs a human" was overridden one layer up (the ~31s
     inter-attempt gap matches retryIntervalInSeconds=30 exactly). Retry ownership now
     sits with the notebook and the activity's retry is 0 — pinned below by reading
     pipeline-content.json, because the notebook's failure message asserts it in prose.

Canonical budget documentation: docs/epi_wgi_ingestion.md § "Retry ownership and the
total attempt budget".
"""

import ast
import json
from pathlib import Path

import pytest
import requests as real_requests

from tests._notebook_loader import load_notebook_functions

REPO_ROOT = Path(__file__).resolve().parents[1]
WGI_NOTEBOOK = REPO_ROOT / "fabric" / "bronze_ingest_wgi.Notebook" / "notebook-content.py"

FUNCS = ["is_transient_request_error", "retry_delay", "fetch_indicator"]


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise real_requests.exceptions.HTTPError(
                f"{self.status_code} Server Error: for url: https://api.worldbank.org/v2/x",
                response=self,
            )


class RequestsShim:
    """Real exception classes (the classifier branches on them), swappable .get."""

    exceptions = real_requests.exceptions

    def __init__(self, responses):
        # responses: list of FakeResponse or Exception, consumed in order
        self._responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {}), timeout))
        if not self._responses:
            raise AssertionError("fake requests.get called more times than scripted")
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


class NoSleep:
    def __init__(self):
        self.slept = []

    def sleep(self, seconds):
        self.slept.append(seconds)


def notebook_constants():
    """Read the notebook's module-level tuning constants without executing cells.

    `literal_eval` rather than `.value` so the policy SET (HTTP_TRANSIENT_STATUSES,
    task-075) is readable here too, not just the scalar API_* knobs — that set is the
    classification decision, so the tests must be pinned to the notebook's own copy of
    it rather than to a duplicate maintained in this file.
    """
    tree = ast.parse(WGI_NOTEBOOK.read_text(encoding="utf-8"), filename=str(WGI_NOTEBOOK))
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.startswith(("API_", "HTTP_")):
                try:
                    out[target.id] = ast.literal_eval(node.value)
                except ValueError:
                    pass  # not a literal (e.g. a computed expression) — not a knob
    return out


def load(requests_shim=None, time_shim=None, **overrides):
    consts = notebook_constants()
    globs = {
        "requests": requests_shim if requests_shim is not None else real_requests,
        "time": time_shim if time_shim is not None else NoSleep(),
        "random": _NoJitter(),
        "API_BASE": consts.get("API_BASE", "https://api.worldbank.org/v2"),
        "API_PAGE_SIZE": consts["API_PAGE_SIZE"],
        "API_READ_TIMEOUT": consts["API_READ_TIMEOUT"],
        "API_MAX_RETRIES": consts["API_MAX_RETRIES"],
        "API_BACKOFF_BASE": consts["API_BACKOFF_BASE"],
        "API_BACKOFF_CAP": consts["API_BACKOFF_CAP"],
        "API_BACKOFF_JITTER": consts["API_BACKOFF_JITTER"],
        "HTTP_TRANSIENT_STATUSES": consts["HTTP_TRANSIENT_STATUSES"],
    }
    globs.update(overrides)
    return load_notebook_functions(WGI_NOTEBOOK, FUNCS, extra_globals=globs)


class _NoJitter:
    @staticmethod
    def uniform(a, b):
        return 0.0


def page(entries, page_no, pages, total):
    return FakeResponse(
        200,
        [{"page": page_no, "pages": pages, "per_page": 1000, "total": total}, entries],
    )


def entry(country="Sweden", iso="SWE", year="2022", value=1.5):
    return {"country": {"value": country}, "countryiso3code": iso,
            "date": year, "value": value}


# --------------------------------------------------------------------------
# 1. Classification — the whole point of task-066
# --------------------------------------------------------------------------

@pytest.mark.parametrize("status", [500, 502, 503, 504, 599])
def test_5xx_is_transient(status):
    """The observed failure was a 502. Every 5xx from this host is gateway-level."""
    assert load()["is_transient_request_error"](_http_error(status)) is True


def _http_error(status):
    return real_requests.exceptions.HTTPError(
        f"{status} Server Error", response=FakeResponse(status)
    )


def test_429_is_transient():
    """Rate limiting is retryable — but only because retry_delay honours Retry-After."""
    assert load()["is_transient_request_error"](_http_error(429)) is True


@pytest.mark.parametrize("status", [401, 403, 404])
def test_auth_and_not_found_stay_permanent(status):
    """The deliberately-kept permanent set (task-075). 401/403 need a human; 404 is a
    retired or renamed indicator path, and no amount of waiting resurrects a removed
    route. These must fail NOW, not after the backoff budget, and must not be reported
    as an exhausted-retry outage."""
    assert load()["is_transient_request_error"](_http_error(status)) is False


@pytest.mark.parametrize("status", [409, 418, 422, 451])
def test_unclassified_status_fails_closed_as_permanent(status):
    """task-075 widened the transient set to 400/408 — it did NOT open all 4xx. Any
    status we have not explicitly reasoned about stays permanent, which is what keeps
    the unbounded-retry behaviour task-066 removed from creeping back."""
    assert load()["is_transient_request_error"](_http_error(status)) is False


def test_400_is_transient():
    """THE task-075 anchor: on 2026-08-17 GOV_WGI_CC.EST page 1 returned 400 at 04:00
    and HTTP 200 on the byte-identical URL at 04:03. Since this API reports bad input
    in-band as HTTP 200 (see test_in_band_200_error_body_... below), a 400 from this
    host is gateway noise, not a malformed request."""
    assert load()["is_transient_request_error"](_http_error(400)) is True


def test_408_is_transient():
    """A request timeout is a timeout that happens to carry a status line — same class
    as the transport-level Timeout, which was already transient."""
    assert load()["is_transient_request_error"](_http_error(408)) is True


def test_transient_status_set_is_exactly_the_decided_policy():
    """Pin the DECISION itself, not just its consequences (task-075, Erik 2026-08-20).
    Widening this set is a policy change and must be a deliberate edit here too."""
    assert notebook_constants()["HTTP_TRANSIENT_STATUSES"] == {400, 408, 429}


@pytest.mark.parametrize("exc", [
    real_requests.exceptions.Timeout("read timed out"),
    real_requests.exceptions.ConnectionError("connection reset"),
    real_requests.exceptions.ChunkedEncodingError("truncated"),
])
def test_transport_failures_are_transient(exc):
    """task-050's original case: the API is slow/flaky, not wrong."""
    assert load()["is_transient_request_error"](exc) is True


def test_unknown_request_exception_is_not_retried():
    """Fail closed: an exception we cannot classify is not assumed transient."""
    fn = load()["is_transient_request_error"]
    assert fn(real_requests.exceptions.URLRequired("no url")) is False


# --------------------------------------------------------------------------
# 2. Backoff policy
# --------------------------------------------------------------------------

def test_backoff_is_exponential_and_capped():
    consts = notebook_constants()
    retry_delay = load()["retry_delay"]
    delays = [retry_delay(a) for a in range(1, consts["API_MAX_RETRIES"] + 1)]
    assert delays[0] == consts["API_BACKOFF_BASE"]
    assert delays[1] == consts["API_BACKOFF_BASE"] * 2
    assert max(delays) <= consts["API_BACKOFF_CAP"]
    assert delays == sorted(delays), "backoff must be non-decreasing"


def test_retry_after_header_wins_over_exponential():
    """A 429/503 that names its own delay must be obeyed, not overridden by our
    exponential schedule — otherwise a rate limit gets hammered."""
    retry_delay = load()["retry_delay"]
    resp = FakeResponse(429, headers={"Retry-After": "17"})
    assert retry_delay(1, resp) == 17.0


def test_retry_after_is_capped():
    retry_delay = load()["retry_delay"]
    consts = notebook_constants()
    resp = FakeResponse(503, headers={"Retry-After": "99999"})
    assert retry_delay(1, resp) == consts["API_BACKOFF_CAP"]


def test_http_date_retry_after_falls_back_to_exponential():
    retry_delay = load()["retry_delay"]
    resp = FakeResponse(503, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})
    assert retry_delay(1, resp) == notebook_constants()["API_BACKOFF_BASE"]


def test_retry_budget_covers_an_isolated_gateway_wobble():
    """Regression on the measured failure: the old 5-attempt / 60s-cap policy spent
    only 75s before killing the run, while the degraded window ran 35-60 min with
    most requests succeeding. Pin the widened budget."""
    consts = notebook_constants()
    assert consts["API_MAX_RETRIES"] >= 8
    assert consts["API_BACKOFF_CAP"] >= 120
    retry_delay = load()["retry_delay"]
    total = sum(retry_delay(a) for a in range(1, consts["API_MAX_RETRIES"]))
    assert total >= 300, f"total backoff {total}s is below the task-066 floor"


# --------------------------------------------------------------------------
# 3. fetch_indicator — retry behaviour end to end
# --------------------------------------------------------------------------

def test_transient_502_is_retried_then_succeeds():
    """THE anchor case: a 502 mid-pagination must not kill the run."""
    shim = RequestsShim([
        _http_error(502),
        page([entry()], 1, 1, 1),
    ])
    sleeper = NoSleep()
    fetch = load(shim, sleeper)["fetch_indicator"]
    records = fetch("GOV_WGI_PV.EST", "PV.EST", "Political Stability", "1996", "2023")
    assert len(records) == 1
    assert len(shim.calls) == 2, "the 502 should have been retried exactly once"
    assert sleeper.slept, "a retry must back off"


def test_permanent_404_fails_immediately_without_burning_retries():
    shim = RequestsShim([_http_error(404)])
    sleeper = NoSleep()
    fetch = load(shim, sleeper)["fetch_indicator"]
    with pytest.raises(RuntimeError, match="PERMANENT"):
        fetch("GOV_WGI_PV.EST", "PV.EST", "Political Stability", "1996", "2023")
    assert len(shim.calls) == 1, "a permanent error must not be retried"
    assert sleeper.slept == [], "a permanent error must not sleep"


def test_transient_502_still_fails_loudly_when_budget_exhausts():
    """Bounded means bounded — a real outage stays a red run."""
    attempts = notebook_constants()["API_MAX_RETRIES"]
    shim = RequestsShim([_http_error(502)] * attempts)
    fetch = load(shim, NoSleep())["fetch_indicator"]
    with pytest.raises(RuntimeError, match=f"after {attempts} attempts"):
        fetch("GOV_WGI_PV.EST", "PV.EST", "Political Stability", "1996", "2023")
    assert len(shim.calls) == attempts


# --------------------------------------------------------------------------
# 4. Completeness guards — no silent partial load
# --------------------------------------------------------------------------

def test_in_band_200_error_body_raises_instead_of_silently_truncating():
    """The live-probed shape (2026-08-13): HTTP 200, one-element body. This is how
    the World Bank reports an invalid indicator code — and it re-coded WGI once
    already. Must fail, not return a short list."""
    shim = RequestsShim([FakeResponse(200, [{"message": [
        {"id": "120", "key": "Invalid value",
         "value": "The provided parameter value is not valid"}]}])])
    fetch = load(shim, NoSleep())["fetch_indicator"]
    with pytest.raises(RuntimeError, match="in-band error"):
        fetch("GOV_WGI_NOPE.EST", "NOPE.EST", "Bogus", "1996", "2023")


def test_null_record_set_raises():
    shim = RequestsShim([page(None, 1, 1, 0)])
    fetch = load(shim, NoSleep())["fetch_indicator"]
    with pytest.raises(RuntimeError, match="no record set"):
        fetch("GOV_WGI_PV.EST", "PV.EST", "Political Stability", "1996", "2023")


def test_short_pagination_raises():
    """API declares total=2000 but only 1000 entries are walked -> refuse to return."""
    shim = RequestsShim([page([entry()] * 1000, 1, 1, 2000)])
    fetch = load(shim, NoSleep())["fetch_indicator"]
    with pytest.raises(RuntimeError, match="Incomplete pagination"):
        fetch("GOV_WGI_PV.EST", "PV.EST", "Political Stability", "1996", "2023")


def test_full_pagination_succeeds_and_skips_null_values():
    """Null `value` entries are legitimately skipped (a country with no score that
    year), so records < entries is normal and must NOT trip the completeness check —
    the check counts ENTRIES against the API's declared total, not kept records."""
    p1 = page([entry(), {"country": {"value": "X"}, "countryiso3code": "XXX",
                         "date": "2022", "value": None}], 1, 2, 3)
    p2 = page([entry(country="Japan", iso="JPN")], 2, 2, 3)
    shim = RequestsShim([p1, p2])
    fetch = load(shim, NoSleep())["fetch_indicator"]
    records = fetch("GOV_WGI_PV.EST", "PV.EST", "Political Stability", "1996", "2023")
    assert len(records) == 2, "the null-valued entry should be skipped, not counted"
    assert {r["indicator_code"] for r in records} == {"PV.EST"}
    assert {r["indicator_name"] for r in records} == {"Political Stability"}


def test_canonical_short_code_is_stored_not_the_api_code():
    """The bronze_wgi contract is the classic code; the API code is an implementation
    detail of the 2026-07-26 re-code."""
    shim = RequestsShim([page([entry()], 1, 1, 1)])
    fetch = load(shim, NoSleep())["fetch_indicator"]
    records = fetch("GOV_WGI_CC.EST", "CC.EST", "Control of Corruption", "1996", "2023")
    assert records[0]["indicator_code"] == "CC.EST"


# --------------------------------------------------------------------------
# 5. Retry OWNERSHIP across the two layers (task-075)
#
# The notebook owns the budget; the pipeline activity retries zero times. These tests
# are the local stand-in for the Fabric-side demonstration: the pipeline cannot be run
# from here, so the notebook's own classification and the activity's declared policy are
# each exercised directly, and the arithmetic that joins them is asserted rather than
# observed. The live confirmation is Erik's half of task-075's AC5.
# --------------------------------------------------------------------------

BOGUS_INDICATOR_BODY = [{"message": [
    {"id": "120", "key": "Invalid value",
     "value": "The provided parameter value is not valid"}]}]

PIPELINE_JSON = (REPO_ROOT / "fabric"
                 / "orchestrator_pipeline_bronze_to_gold.DataPipeline"
                 / "pipeline-content.json")


def bronze_wgi_activity():
    activities = json.loads(PIPELINE_JSON.read_text(encoding="utf-8"))["properties"]["activities"]
    matches = [a for a in activities if a["name"] == "bronze_wgi"]
    assert len(matches) == 1, f"expected exactly one bronze_wgi activity, got {len(matches)}"
    return matches[0]


def test_pipeline_activity_adds_no_attempts_of_its_own():
    """AC3. The activity carried policy.retry=2 until task-075, which silently overrode
    the notebook's classification: on 2026-08-17 the notebook raised "not retried" and
    the activity retried 31s later anyway (matching retryIntervalInSeconds=30) and
    succeeded. Retry ownership now sits with the notebook alone."""
    assert bronze_wgi_activity()["policy"]["retry"] == 0, (
        "bronze_wgi's activity retry is back above 0 — the notebook's permanent-error "
        "message claims 'not retried by the pipeline activity (policy.retry=0)', which "
        "would now be false, and the in-notebook classification would be inert again. "
        "See docs/epi_wgi_ingestion.md § 'Retry ownership and the total attempt budget'."
    )


def test_notebook_failure_message_matches_the_deployed_activity_policy():
    """The notebook asserts the activity's retry count in PROSE, inside the error a
    human will read at 04:00. Prose drifts silently; pin it to the JSON."""
    retry = bronze_wgi_activity()["policy"]["retry"]
    notebook_text = WGI_NOTEBOOK.read_text(encoding="utf-8")
    assert f"policy.retry={retry}" in notebook_text, (
        f"the notebook's failure message does not name the deployed retry count "
        f"({retry})"
    )


@pytest.mark.parametrize("scripted,match,label", [
    ([_http_error(404)], "PERMANENT", "retired indicator path -> 404"),
    ([_http_error(401)], "PERMANENT", "access rule -> 401"),
    ([FakeResponse(200, BOGUS_INDICATOR_BODY)], "in-band error",
     "bogus indicator code -> in-band HTTP 200"),
])
def test_permanent_failure_goes_red_on_the_first_attempt(scripted, match, label):
    """AC4, demonstrated locally (the Fabric pipeline cannot be driven from here).

    A genuinely permanent failure — the retired/bogus indicator code task-066 built this
    path for — must surface as a red run on attempt 1, not after a 30+ minute retry
    parade. Zero HTTP retries and zero backoff sleeps inside the notebook; zero further
    attempts outside it, pinned by test_pipeline_activity_adds_no_attempts_of_its_own.

    The bogus-code case is the one that matters most in practice: this API reports an
    unknown indicator IN-BAND as HTTP 200, so that is the route a future WGI re-code
    actually takes."""
    shim = RequestsShim(scripted)
    sleeper = NoSleep()
    fetch = load(shim, sleeper)["fetch_indicator"]
    with pytest.raises(RuntimeError, match=match):
        fetch("GOV_WGI_NOPE.EST", "NOPE.EST", "Bogus", "1996", "2023")
    assert len(shim.calls) == 1, f"{label}: must not be retried"
    assert sleeper.slept == [], f"{label}: must not spend any backoff"


def test_transient_400_replays_the_2026_08_17_shape_in_one_activity_attempt():
    """The 08-17 event, now handled entirely inside the notebook: the 400 is retried
    here instead of by the activity, so the run stays green without the pipeline having
    to paper over a classification the notebook got wrong."""
    shim = RequestsShim([_http_error(400), page([entry()], 1, 1, 1)])
    sleeper = NoSleep()
    fetch = load(shim, sleeper)["fetch_indicator"]
    records = fetch("GOV_WGI_CC.EST", "CC.EST", "Control of Corruption", "1996", "2023")
    assert len(records) == 1
    assert len(shim.calls) == 2, "the spurious 400 should have been retried exactly once"
    assert sleeper.slept, "a retry must back off"


def test_total_attempt_budget_is_the_documented_one():
    """AC3's readability requirement, as an assertion: total attempts = notebook budget
    x activity attempts. Permanent failures get exactly 1. Both numbers are stated in
    docs/epi_wgi_ingestion.md § 'Retry ownership and the total attempt budget'."""
    notebook_attempts = notebook_constants()["API_MAX_RETRIES"]
    activity_attempts = bronze_wgi_activity()["policy"]["retry"] + 1
    assert activity_attempts == 1
    assert notebook_attempts * activity_attempts == notebook_attempts == 8
