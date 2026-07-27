"""
Unit tests for pipeline_error_handler's categorize_error().

Follows the reference-implementation contract used by test_key_generation.py:
the function is extracted from the *live* notebook text via `ast`, so editing
the notebook's pattern lists is what these tests are guarding.

The anchor case is a real Fabric error string, captured from orchestrator run
742ff1ff-42d8-4fb6-9845-8c7a183c060d on 2026-07-27 (task-041 criterion 4). That
run is the first time the transient/permanent lists were ever exercised against
live Fabric output, and they failed: a textbook-permanent 404 categorised as
"Unknown", because the list said "404 not found" while Fabric emits
"404 NotFound" and "(404) Not Found". These tests exist so that regression
cannot recur silently.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HANDLER_NOTEBOOK = (
    REPO_ROOT / "fabric" / "pipeline_error_handler.Notebook" / "notebook-content.py"
)

# Verbatim from the run's Copy-activity Output. Do not paraphrase - the whole
# point is that paraphrased error text is what produced the original bug.
REAL_404 = (
    "ErrorCode=HttpRequestFailedWithClientError,"
    "'Type=Microsoft.DataTransfer.Common.Shared.HybridDeliveryException,"
    "Message=Http request failed with client error, status code 404 NotFound, "
    "please check your activity settings. If you configured a baseUrl that "
    "includes path, please make sure it ends with '/'.,"
    "Source=Microsoft.DataTransfer.ClientLibrary,"
    "''Type=System.Net.WebException,"
    "Message=The remote server returned an error: (404) Not Found.,Source=System,'"
)


def load_categorize_error():
    """Extract categorize_error + its pattern lists from the live notebook."""
    assert HANDLER_NOTEBOOK.exists(), f"Notebook not found: {HANDLER_NOTEBOOK}"
    tree = ast.parse(
        HANDLER_NOTEBOOK.read_text(encoding="utf-8"), filename=str(HANDLER_NOTEBOOK)
    )

    wanted_assigns = {"TRANSIENT_ERROR_PATTERNS", "PERMANENT_ERROR_PATTERNS"}
    nodes = []
    seen_assigns = set()
    func = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in wanted_assigns:
                    nodes.append(node)
                    seen_assigns.add(target.id)
        elif isinstance(node, ast.FunctionDef) and node.name == "categorize_error":
            func = node

    assert seen_assigns == wanted_assigns, f"missing pattern lists: {wanted_assigns - seen_assigns}"
    assert func is not None, "categorize_error not found in notebook"
    nodes.append(func)

    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    ns = {}
    exec(compile(module, filename=str(HANDLER_NOTEBOOK), mode="exec"), ns)
    return ns["categorize_error"], ns


@pytest.fixture(scope="module")
def categorize():
    fn, _ = load_categorize_error()
    return fn


class TestRealFabricErrors:
    """Anchored on strings a live Fabric run actually emitted."""

    def test_real_404_is_permanent_not_unknown(self, categorize):
        """The regression this file exists for.

        A broken Copy source is not retryable; categorising it Unknown tells the
        operator to 'retry once cautiously' for a URL that will never resolve.
        """
        assert categorize(REAL_404) == "Permanent"

    def test_both_404_phrasings_match_independently(self, categorize):
        """Either half of the nested exception must be enough on its own.

        Fabric sometimes surfaces only the outer HybridDeliveryException and
        sometimes only the inner WebException, so neither can be relied on.
        """
        outer = "Http request failed with client error, status code 404 NotFound"
        inner = "The remote server returned an error: (404) Not Found."
        assert categorize(outer) == "Permanent"
        assert categorize(inner) == "Permanent"

    def test_naive_pattern_would_have_missed_it(self, categorize):
        """Documents *why* the original list failed, so nobody 'simplifies' it back.

        Neither real phrasing contains the literal '404 not found'.
        """
        assert "404 not found" not in REAL_404.lower()
        assert "404 notfound" in REAL_404.lower()
        assert "(404) not found" in REAL_404.lower()


class TestHttpStatusSemantics:
    """4xx is the caller's fault (permanent); 5xx and 429 are worth retrying."""

    @pytest.mark.parametrize("code", ["400", "401", "403", "404", "409"])
    def test_client_errors_are_permanent(self, categorize, code):
        assert categorize("status code %s Whatever" % code) == "Permanent"
        assert categorize("returned an error: (%s) Whatever." % code) == "Permanent"

    @pytest.mark.parametrize("code", ["500", "502", "503", "504"])
    def test_server_errors_are_transient(self, categorize, code):
        assert categorize("status code %s Whatever" % code) == "Transient"
        assert categorize("returned an error: (%s) Whatever." % code) == "Transient"

    def test_429_is_transient_despite_being_a_client_error(self, categorize):
        """429 is throttling - the one 4xx that should be retried.

        It is matched by the TRANSIENT list, which categorize_error checks first;
        that ordering is load-bearing, because the permanent list also carries
        'http request failed with client error', which Fabric emits for all 4xx.
        """
        assert categorize("status code 429 TooManyRequests") == "Transient"
        assert categorize("returned an error: (429) Too Many Requests.") == "Transient"
        fabric_429 = (
            "ErrorCode=HttpRequestFailedWithClientError,Message=Http request failed "
            "with client error, status code 429 TooManyRequests"
        )
        assert categorize(fabric_429) == "Transient"


class TestUnchangedBehaviour:
    """The original cases still classify as before."""

    def test_timeout_is_transient(self, categorize):
        assert categorize("Connection timeout after 30s") == "Transient"

    def test_auth_failure_is_permanent(self, categorize):
        assert categorize("401 Unauthorized: invalid credentials") == "Permanent"

    def test_unrecognised_is_unknown(self, categorize):
        assert categorize("Something unexpected happened") == "Unknown"

    def test_empty_is_unknown(self, categorize):
        assert categorize("") == "Unknown"
        assert categorize(None) == "Unknown"
