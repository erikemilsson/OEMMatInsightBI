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
"""

import ast
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
    """Read the notebook's module-level tuning constants without executing cells."""
    tree = ast.parse(WGI_NOTEBOOK.read_text(encoding="utf-8"), filename=str(WGI_NOTEBOOK))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.startswith("API_"):
                    out[target.id] = node.value.value
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


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422])
def test_4xx_is_permanent(status):
    """A malformed request or an auth failure must fail NOW, not after the backoff
    budget, and must not be reported as an exhausted-retry outage."""
    assert load()["is_transient_request_error"](_http_error(status)) is False


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
