"""
Tests for bronze_ingest_epi's pre-parse download guard and its pinned source (task-082).

ANCHOR CASE. All 22 scheduled orchestrator runs from 2026-09-25 to 2026-10-16 failed at
bronze_epi with

    ParserError: Error tokenizing data. C error: Expected 1 fields in line 15, saw 2

Yale retired https://epi.yale.edu/downloads/epi2024results.csv (and ...weights.csv) when
EPI 2026 shipped in September 2026. Those paths do not 404. They answer HTTP 200,
`text/html; charset=UTF-8`, with a 30,621-byte "EPI Downloads | Environmental Performance
Index" page (measured 2026-10-16). The notebook passed response.text straight to
pd.read_csv, and its 404 branch never fired on a soft-404. Feeding that page to pandas
reproduces the exact live error.

Two things are pinned here:

  1. The guard. assert_csv_response(), the notebook's own function extracted from the
     live notebook text, rejects a non-CSV Content-Type or an HTML body with the notebook's
     own EpiSourceNotCsvError, naming the URL and the content type. It accepts a real CSV
     under both the header Yale used (text/csv) and the one raw.githubusercontent.com uses
     (text/plain). It is also wired in: each of the notebook's two pd.read_csv calls comes
     after a guard call on the same response.

  2. The pin. Erik chose (2026-10-16) to keep the 2024 vintage and serve Yale's original
     files from this repo. The notebook's source URL must resolve to files in the working
     tree that are byte-identical to the Wayback Machine copies of Yale's originals and have
     the columns and row counts the notebook's own validation expects.

No src/ mirror: like bronze_ingest_wgi (tests/test_wgi_retry.py), this notebook's logic has
no src/transformations counterpart, so the tests target the notebook's code directly.
"""

import ast
import csv
import hashlib
from pathlib import Path

import pytest
import requests

from tests._notebook_loader import load_notebook_functions

REPO_ROOT = Path(__file__).resolve().parents[1]
EPI_NOTEBOOK = REPO_ROOT / "fabric" / "bronze_ingest_epi.Notebook" / "notebook-content.py"

RAW_PREFIX = "https://raw.githubusercontent.com/erikemilsson/OEMMatInsightBI/main/"

# sha256 of Yale's original files as archived by the Wayback Machine:
#   https://web.archive.org/web/20260901000000id_/https://epi.yale.edu/downloads/epi2024results.csv
#   https://web.archive.org/web/20260901000000id_/https://epi.yale.edu/downloads/epi2024weights.csv
#     (the weights request resolves to snapshot 20260814071704)
# Both were served as text/csv (123,308 B and 6,756 B), re-fetched and hashed 2026-10-16.
WAYBACK_SHA256 = {
    "epi2024results.csv": "9d0b98d9fecf0ac37926224885045bad12e5d68b2597de1dc3bf49e68fb937ab",
    "epi2024weights.csv": "b4d3dee9d357070fe6f8897377698c2eea992cf087f0e7648a1285749371f332",
}

# The head of the page Yale's retired CSV URL actually returned on 2026-10-16 (HTTP 200,
# text/html; charset=UTF-8), copied from the live response, leading newline included.
YALE_SOFT_404_BODY = (
    "\n<!DOCTYPE html>\n"
    '<html lang="en" dir="ltr" prefix="og: https://ogp.me/ns#">\n'
    "  <head>\n"
    '    <meta charset="utf-8" />\n'
    '<link rel="canonical" href="https://epi.yale.edu/downloads/epi2024results.csv" />\n'
    '<meta property="og:type" content="website" />\n'
    '<meta property="og:title" content="EPI Downloads" />\n'
    "<title>EPI Downloads | Environmental Performance Index</title>\n"
    "  </head>\n  <body></body>\n</html>\n"
)
YALE_URL = "https://epi.yale.edu/downloads/epi2024results.csv"

CSV_BODY = 'code,iso,country,EPI.old,EPI.new\n4,AFG,Afghanistan,25.1,26.0\n8,ALB,Albania,45.0,47.1\n'


def notebook_constants():
    """The notebook's top-level literal assignments, read without executing any cell."""
    tree = ast.parse(EPI_NOTEBOOK.read_text(encoding="utf-8"), filename=str(EPI_NOTEBOOK))
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                try:
                    out[target.id] = ast.literal_eval(node.value)
                except ValueError:
                    pass  # not a literal (an f-string or a computed value)
    return out


def load():
    consts = notebook_constants()
    return load_notebook_functions(
        EPI_NOTEBOOK,
        ["EpiSourceNotCsvError", "assert_csv_response"],
        extra_globals={"CSV_CONTENT_TYPES": consts["CSV_CONTENT_TYPES"]},
    )


def make_response(body, content_type, status=200, url=YALE_URL):
    """A real requests.Response, decoded the way requests.get decodes one.

    A real object rather than a fake keeps the header lookup case-insensitive and keeps
    .text on requests' own charset rules, which is what the notebook sees in Fabric.
    """
    response = requests.models.Response()
    response.status_code = status
    response._content = body if isinstance(body, bytes) else body.encode("utf-8")
    response.url = url
    if content_type is not None:
        response.headers["Content-Type"] = content_type
    response.encoding = requests.utils.get_encoding_from_headers(response.headers)
    return response


# --------------------------------------------------------------------------
# 1. The guard
# --------------------------------------------------------------------------

def test_yale_soft_404_raises_named_error_citing_url_and_content_type():
    """THE anchor case: HTTP 200 + an HTML page must fail as a named error, not a
    pandas ParserError, and the message must say which URL and what it answered with."""
    fns = load()
    response = make_response(YALE_SOFT_404_BODY, "text/html; charset=UTF-8")
    with pytest.raises(fns["EpiSourceNotCsvError"]) as excinfo:
        fns["assert_csv_response"](response, YALE_URL)
    message = str(excinfo.value)
    assert YALE_URL in message
    assert "text/html; charset=UTF-8" in message
    assert "HTTP 200" in message
    assert "HTML page" in message


def test_named_error_is_a_value_error_with_a_stable_name():
    """The class name is what the pipeline's activity error shows. It subclasses
    ValueError, like the notebook's other bad-source errors (bad year, 404, schema)."""
    error_cls = load()["EpiSourceNotCsvError"]
    assert error_cls.__name__ == "EpiSourceNotCsvError"
    assert issubclass(error_cls, ValueError)


@pytest.mark.parametrize("content_type", [
    "text/plain; charset=utf-8",  # what raw.githubusercontent.com sends
    "text/csv",
])
def test_html_body_is_rejected_even_under_a_csv_content_type(content_type):
    """The header alone is not trusted: an HTML page served as text/plain (the type the
    pinned host uses for every file) must still be caught by the body check."""
    fns = load()
    response = make_response(YALE_SOFT_404_BODY, content_type)
    with pytest.raises(fns["EpiSourceNotCsvError"], match="HTML page"):
        fns["assert_csv_response"](response, YALE_URL)


@pytest.mark.parametrize("prefix", ["\ufeff", "\ufeff\r\n  ", "\n\n\t"])
def test_html_body_behind_a_bom_or_whitespace_is_still_caught(prefix):
    """The sniff skips a UTF-8 byte-order mark and leading whitespace before looking for
    the HTML start (Yale's page itself opens with a newline). The body omits the optional
    <html> tag, so only the doctype check can catch it, and that check sees the doctype
    only if the prefix was stripped."""
    fns = load()
    body = prefix + "<!DOCTYPE html>\n<head><title>EPI Downloads</title></head>\n<body></body>\n"
    response = make_response(body, "text/plain; charset=utf-8")
    with pytest.raises(fns["EpiSourceNotCsvError"], match="HTML page"):
        fns["assert_csv_response"](response, YALE_URL)


@pytest.mark.parametrize("content_type", [
    "application/json",
    "application/octet-stream",
    # Yale's EPI 2026 release ships XLSX, not CSV.
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
])
def test_non_csv_content_type_is_rejected_even_with_a_csv_body(content_type):
    fns = load()
    response = make_response(CSV_BODY, content_type)
    with pytest.raises(fns["EpiSourceNotCsvError"]) as excinfo:
        fns["assert_csv_response"](response, YALE_URL)
    message = str(excinfo.value)
    assert content_type in message
    assert "Content-Type is not one of" in message
    assert "HTML page" not in message


def test_missing_content_type_fails_closed():
    fns = load()
    response = make_response(CSV_BODY, None)
    with pytest.raises(fns["EpiSourceNotCsvError"], match=r"\(missing\)"):
        fns["assert_csv_response"](response, YALE_URL)


def test_empty_body_is_rejected():
    fns = load()
    response = make_response("", "text/plain; charset=utf-8")
    with pytest.raises(fns["EpiSourceNotCsvError"], match="empty"):
        fns["assert_csv_response"](response, YALE_URL)


@pytest.mark.parametrize("content_type", [
    "text/plain; charset=utf-8",  # raw.githubusercontent.com, measured 2026-10-16
    "text/csv;charset=UTF-8",     # the Wayback Machine copy of Yale's original response
    "text/csv",
    "application/csv",
    "TEXT/CSV",                   # media types are case-insensitive
])
def test_valid_csv_passes(content_type):
    fns = load()
    response = make_response(CSV_BODY, content_type)
    assert fns["assert_csv_response"](response, YALE_URL) is None


@pytest.mark.parametrize("filename", sorted(WAYBACK_SHA256))
def test_pinned_files_pass_the_guard_as_github_serves_them(filename):
    """The real pinned bytes, under the header raw.githubusercontent.com sends for them."""
    fns = load()
    path = pinned_dir() / filename
    response = make_response(path.read_bytes(), "text/plain; charset=utf-8",
                             url=notebook_constants()["EPI_SOURCE_BASE_URL"] + "/" + filename)
    assert fns["assert_csv_response"](response, response.url) is None


def test_accepted_content_types_are_exactly_the_decided_policy():
    """Pin the allowlist itself. Widening it (e.g. to application/octet-stream) weakens
    the guard and should be a deliberate edit here too."""
    assert notebook_constants()["CSV_CONTENT_TYPES"] == {"text/csv", "application/csv", "text/plain"}


def _call_name(call):
    func = call.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    if isinstance(func, ast.Name):
        return func.id
    return None


def test_guard_runs_between_each_download_and_its_parse():
    """A guard that is defined but not called fixes nothing. The notebook parses exactly
    two downloads; each parse must come after a guard call on that download's response,
    and each guard call after the request that produced it."""
    tree = ast.parse(EPI_NOTEBOOK.read_text(encoding="utf-8"), filename=str(EPI_NOTEBOOK))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]

    parses = sorted(c.lineno for c in calls if _call_name(c) == "pd.read_csv")
    assert len(parses) == 2, (
        f"expected exactly 2 pd.read_csv calls (results, weights), found {len(parses)}: "
        f"a new parse needs its own assert_csv_response call and an update here"
    )

    guards = {
        tuple(arg.id for arg in c.args): c.lineno
        for c in calls
        if _call_name(c) == "assert_csv_response"
    }
    assert set(guards) == {("response", "epi_url"), ("weights_response", "weights_url")}

    gets = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                and _call_name(node.value) == "requests.get"):
            gets[node.targets[0].id] = node.lineno

    results_parse, weights_parse = parses
    assert gets["response"] < guards[("response", "epi_url")] < results_parse
    assert results_parse < gets["weights_response"]
    assert gets["weights_response"] < guards[("weights_response", "weights_url")] < weights_parse


# --------------------------------------------------------------------------
# 2. The pinned source
# --------------------------------------------------------------------------

def pinned_dir():
    base = notebook_constants()["EPI_SOURCE_BASE_URL"]
    assert base.startswith(RAW_PREFIX), (
        f"EPI_SOURCE_BASE_URL {base!r} does not point at this repo's main branch"
    )
    return REPO_ROOT / base[len(RAW_PREFIX):]


def test_source_url_resolves_to_files_in_this_repo():
    """A path typo here is a 404 in Fabric that no local run would show. Check the URL
    the notebook builds, for the vintage its parameters cell defaults to, maps to real
    files in the working tree."""
    consts = notebook_constants()
    year = consts["p_epi_year"]
    assert "epi.yale.edu" not in consts["EPI_SOURCE_BASE_URL"]
    for kind in ("results", "weights"):
        path = pinned_dir() / f"epi{year}{kind}.csv"
        assert path.is_file(), f"{path.relative_to(REPO_ROOT)} is missing from the repo"


@pytest.mark.parametrize("filename", sorted(WAYBACK_SHA256))
def test_pinned_files_are_yales_original_bytes(filename):
    """The pin is a copy of Yale's release, not an edited one. A re-save (Excel, an
    editor that rewrites line endings, a git autocrlf conversion) changes the hash."""
    digest = hashlib.sha256((pinned_dir() / filename).read_bytes()).hexdigest()
    assert digest == WAYBACK_SHA256[filename]


def _read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    return rows[0], rows[1:]


def test_pinned_results_satisfy_the_notebooks_schema_check():
    """The same required-column rule the notebook applies (plain or '.new'-suffixed),
    read from the notebook, plus the 180-country count the DQ row-count range expects."""
    required = notebook_constants()["required_columns"]
    header, rows = _read_csv(pinned_dir() / "epi2024results.csv")
    missing = [c for c in required if c not in header and f"{c}.new" not in header]
    assert missing == []
    assert len(header) == 149
    assert len(rows) == 180
    iso = [row[header.index("iso")] for row in rows]
    assert len(set(iso)) == 180


def test_pinned_weights_header_is_the_notebooks_contract():
    """Exactly the 8 columns the notebook requires, including Yale's spaced 'EPI Percent'
    header, which the notebook renames to epi_percent at write time for Delta."""
    required = notebook_constants()["required_weights_columns"]
    header, rows = _read_csv(pinned_dir() / "epi2024weights.csv")
    assert header == required
    assert "EPI Percent" in header
    assert len(rows) == 73
    types = [row[header.index("Type")] for row in rows]
    assert types.count("Indicator") == 58
