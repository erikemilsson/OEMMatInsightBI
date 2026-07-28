"""
Unit tests for the high-water-mark tracking system (task-029).

Covers three layers:
  1. Pure precedence logic (`resolve_effective_watermark`) — no Spark needed.
  2. Metadata row construction (`metadata_row`) — schema-conformance check.
  3. Read path (`get_last_load_date`) — Spark DataFrame fixture substituting for
     the Delta `bronze_load_metadata` table (delta-spark is not installed locally;
     the genuine Delta write path is Erik's Fabric-side test, criterion 5).
  4. Notebook parity: both `bronze-to-silver.Notebook` and `silver-to-gold2.Notebook`
     define these functions inline; this test parses each notebook, extracts its
     own definitions, and asserts they produce identical results to
     `src/transformations/watermark.py` over the same fixtures — divergence fails
     CI by design (reference-implementation contract, task-032).
"""

import ast
from datetime import date, datetime
from pathlib import Path

import pytest
from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, DateType, TimestampType, LongType,
)

from src.transformations.watermark import (
    METADATA_SCHEMA,
    DEFAULT_WATERMARK,
    DEFAULT_SOURCE_TABLE,
    resolve_effective_watermark,
    metadata_row,
    get_last_load_date,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
BRONZE_NOTEBOOK = REPO_ROOT / "fabric" / "bronze-to-silver.Notebook" / "notebook-content.py"
GOLD_NOTEBOOK = REPO_ROOT / "fabric" / "silver-to-gold2.Notebook" / "notebook-content.py"


# ---------------------------------------------------------------------------
# Notebook-function extractor — mirrors tests/test_key_generation.py
# ---------------------------------------------------------------------------

def _load_notebook_functions(notebook_path, names, extra_globals=None):
    """Extract named top-level functions from a Fabric notebook's source.

    Same approach as test_key_generation.load_notebook_functions: parse the
    notebook as Python (markdown cells are `# MARKDOWN` comments), compile only
    the requested FunctionDefs, and return them in a shared namespace so
    inter-function calls resolve to the notebook's own definitions.
    """
    assert notebook_path.exists(), f"Notebook not found: {notebook_path}"
    tree = ast.parse(notebook_path.read_text(encoding="utf-8"), filename=str(notebook_path))
    found = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in set(names)
    }
    missing = [n for n in names if n not in found]
    assert not missing, (
        f"Notebook {notebook_path.name} no longer defines {missing} at top level — "
        f"the parity harness cannot verify src/ against production. Update the "
        f"harness (or restore the notebook definitions) rather than deleting this test."
    )
    module = ast.Module(body=[found[n] for n in names], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"F": F}
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(module, str(notebook_path), "exec"), namespace)  # noqa: S102
    return {n: namespace[n] for n in names}


def _metadata_fixture(spark, rows):
    """Build a Spark DataFrame with METADATA_SCHEMA from row tuples."""
    return spark.createDataFrame(rows, schema=METADATA_SCHEMA)


# ---------------------------------------------------------------------------
# 1. Precedence logic (pure)
# ---------------------------------------------------------------------------

class TestResolveEffectiveWatermark:
    """resolve_effective_watermark — the three-way precedence (criterion 3)."""

    @pytest.mark.unit
    def test_full_load_returns_sentinel(self):
        # p_full_load=true wins over everything, including an explicit override.
        assert resolve_effective_watermark("true", "2024-06-01", date(2024, 5, 1)) == "1900-01-01"

    @pytest.mark.unit
    def test_full_load_case_insensitive(self):
        assert resolve_effective_watermark("TRUE", "1900-01-01", None) == "1900-01-01"
        assert resolve_effective_watermark(" True ", "1900-01-01", None) == "1900-01-01"

    @pytest.mark.unit
    def test_explicit_override_wins_over_auto_retrieve(self):
        # p_from_date != "1900-01-01" is an explicit override; last_load_date is ignored.
        assert resolve_effective_watermark("false", "2024-06-01", date(2024, 5, 1)) == "2024-06-01"

    @pytest.mark.unit
    def test_explicit_override_strips_whitespace(self):
        assert resolve_effective_watermark("false", "  2024-06-01  ", None) == "2024-06-01"

    @pytest.mark.unit
    def test_auto_retrieve_uses_last_load_date(self):
        # p_from_date == sentinel + last_load_date present -> auto-retrieve.
        assert resolve_effective_watermark("false", "1900-01-01", date(2024, 5, 15)) == "2024-05-15"

    @pytest.mark.unit
    def test_auto_retrieve_none_falls_back_to_sentinel(self):
        # No prior SUCCESS row -> default watermark (load from epoch).
        assert resolve_effective_watermark("false", "1900-01-01", None) == "1900-01-01"

    @pytest.mark.unit
    def test_falsey_full_load_string(self):
        # "false" / empty / junk -> not full load.
        assert resolve_effective_watermark("false", "2024-01-01", None) == "2024-01-01"
        assert resolve_effective_watermark("", "2024-01-01", None) == "2024-01-01"
        assert resolve_effective_watermark("nope", "1900-01-01", date(2024, 1, 1)) == "2024-01-01"

    @pytest.mark.unit
    def test_none_inputs_handled(self):
        # None p_full_load / p_from_date should not raise.
        assert resolve_effective_watermark(None, None, None) == "1900-01-01"
        assert resolve_effective_watermark(None, "2024-01-01", None) == "2024-01-01"


# ---------------------------------------------------------------------------
# 2. Metadata row construction
# ---------------------------------------------------------------------------

class TestMetadataRow:
    """metadata_row — schema-conformant tuple for the Delta append."""

    @pytest.mark.unit
    def test_schema_has_six_fields(self):
        fields = [f.name for f in METADATA_SCHEMA.fields]
        assert fields == [
            "source_table", "last_load_date", "load_timestamp",
            "rows_loaded", "load_status", "execution_id",
        ]

    @pytest.mark.unit
    def test_success_row_with_date_object(self):
        now = datetime(2026, 7, 28, 12, 0, 0)
        row = metadata_row("bronze_procurement_transactional", date(2024, 6, 1),
                           1500, "SUCCESS", execution_id="run-123", now=now)
        assert row == ("bronze_procurement_transactional", date(2024, 6, 1), now,
                       1500, "SUCCESS", "run-123")

    @pytest.mark.unit
    def test_success_row_with_string_date(self):
        # The FAILED path passes the effective watermark as a string.
        now = datetime(2026, 7, 28, 12, 0, 0)
        row = metadata_row("bronze_procurement_transactional", "2024-06-01",
                           0, "FAILED", execution_id="run-456", now=now)
        assert row == ("bronze_procurement_transactional", date(2024, 6, 1), now,
                       0, "FAILED", "run-456")

    @pytest.mark.unit
    def test_failed_row_null_rows(self):
        now = datetime(2026, 7, 28, 12, 0, 0)
        row = metadata_row("bronze_procurement_transactional", date(2024, 6, 1),
                           None, "FAILED", execution_id=None, now=now)
        assert row[4] == "FAILED"
        assert row[3] is None  # rows_loaded nullable on FAILED
        assert row[5] is None  # execution_id nullable

    @pytest.mark.unit
    def test_now_defaults_to_current_time(self):
        before = datetime.now()
        row = metadata_row("t", date(2024, 1, 1), 1, "SUCCESS")
        after = datetime.now()
        assert before <= row[2] <= after


# ---------------------------------------------------------------------------
# 3. Read path — get_last_load_date over a Spark fixture
# ---------------------------------------------------------------------------

class TestGetLastLoadDate:
    """get_last_load_date — reads the last SUCCESS watermark from a DataFrame."""

    @pytest.mark.unit
    def test_returns_none_when_table_empty(self, spark):
        df = _metadata_fixture(spark, [])
        assert get_last_load_date(df, DEFAULT_SOURCE_TABLE) is None

    @pytest.mark.unit
    def test_returns_none_when_no_success_rows(self, spark):
        rows = [metadata_row(DEFAULT_SOURCE_TABLE, date(2024, 6, 1), 0, "FAILED",
                             execution_id="r1", now=datetime(2026, 7, 28, 10, 0, 0))]
        df = _metadata_fixture(spark, rows)
        assert get_last_load_date(df, DEFAULT_SOURCE_TABLE) is None

    @pytest.mark.unit
    def test_returns_latest_success_date(self, spark):
        rows = [
            metadata_row(DEFAULT_SOURCE_TABLE, date(2024, 6, 1), 100, "SUCCESS",
                          execution_id="r1", now=datetime(2026, 7, 28, 10, 0, 0)),
            metadata_row(DEFAULT_SOURCE_TABLE, date(2024, 6, 2), 50, "FAILED",
                          execution_id="r2", now=datetime(2026, 7, 28, 11, 0, 0)),
            metadata_row(DEFAULT_SOURCE_TABLE, date(2024, 6, 3), 200, "SUCCESS",
                          execution_id="r3", now=datetime(2026, 7, 28, 12, 0, 0)),
        ]
        df = _metadata_fixture(spark, rows)
        assert get_last_load_date(df, DEFAULT_SOURCE_TABLE) == date(2024, 6, 3)

    @pytest.mark.unit
    def test_filters_by_source_table(self, spark):
        rows = [
            metadata_row("other_table", date(2024, 6, 5), 10, "SUCCESS",
                          execution_id="r1", now=datetime(2026, 7, 28, 10, 0, 0)),
            metadata_row(DEFAULT_SOURCE_TABLE, date(2024, 6, 1), 100, "SUCCESS",
                          execution_id="r2", now=datetime(2026, 7, 28, 11, 0, 0)),
        ]
        df = _metadata_fixture(spark, rows)
        assert get_last_load_date(df, DEFAULT_SOURCE_TABLE) == date(2024, 6, 1)

    @pytest.mark.unit
    def test_exclude_execution_id_skips_current_run(self, spark):
        """Gold coordination: exclude the current run's row to read the PREVIOUS
        watermark — bronze-to-silver has already written its SUCCESS row by the
        time gold starts, so gold must skip it to use the same watermark silver used."""
        rows = [
            metadata_row(DEFAULT_SOURCE_TABLE, date(2024, 6, 1), 100, "SUCCESS",
                          execution_id="prev-run", now=datetime(2026, 7, 28, 10, 0, 0)),
            metadata_row(DEFAULT_SOURCE_TABLE, date(2024, 6, 2), 50, "SUCCESS",
                          execution_id="current-run", now=datetime(2026, 7, 28, 12, 0, 0)),
        ]
        df = _metadata_fixture(spark, rows)
        # Without exclusion: latest SUCCESS is 2024-06-02 (the just-written current run).
        assert get_last_load_date(df, DEFAULT_SOURCE_TABLE) == date(2024, 6, 2)
        # With exclusion: latest SUCCESS from a DIFFERENT run is 2024-06-01 (previous).
        assert get_last_load_date(df, DEFAULT_SOURCE_TABLE,
                                  exclude_execution_id="current-run") == date(2024, 6, 1)

    @pytest.mark.unit
    def test_exclude_execution_id_empty_does_not_filter(self, spark):
        """Empty/None exclude_execution_id means no filtering (manual notebook run)."""
        rows = [
            metadata_row(DEFAULT_SOURCE_TABLE, date(2024, 6, 1), 100, "SUCCESS",
                          execution_id="r1", now=datetime(2026, 7, 28, 10, 0, 0)),
        ]
        df = _metadata_fixture(spark, rows)
        assert get_last_load_date(df, DEFAULT_SOURCE_TABLE,
                                  exclude_execution_id="") == date(2024, 6, 1)
        assert get_last_load_date(df, DEFAULT_SOURCE_TABLE,
                                  exclude_execution_id=None) == date(2024, 6, 1)


# ---------------------------------------------------------------------------
# 4. Notebook parity — bronze-to-silver + silver-to-gold2
# ---------------------------------------------------------------------------

class TestNotebookParity:
    """Both notebooks define these functions inline; they must match src/."""

    @pytest.mark.unit
    def test_bronze_notebook_defines_watermark_functions(self):
        """The bronze notebook must define all four functions at top level."""
        tree = ast.parse(BRONZE_NOTEBOOK.read_text(encoding="utf-8"))
        names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        required = {"resolve_effective_watermark", "metadata_row",
                    "get_last_load_date", "update_load_metadata"}
        missing = required - names
        assert not missing, (
            f"bronze-to-silver.Notebook is missing {missing}; the watermark "
            f"system cannot run without them."
        )

    @pytest.mark.unit
    def test_gold_notebook_defines_watermark_functions(self):
        """The gold notebook must define the three read-side functions at top level."""
        tree = ast.parse(GOLD_NOTEBOOK.read_text(encoding="utf-8"))
        names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        required = {"resolve_effective_watermark", "metadata_row", "get_last_load_date"}
        missing = required - names
        assert not missing, (
            f"silver-to-gold2.Notebook is missing {missing}; the watermark "
            f"system cannot run without them."
        )

    @pytest.mark.unit
    def test_resolve_effective_watermark_parity_bronze(self):
        nb = _load_notebook_functions(BRONZE_NOTEBOOK, ["resolve_effective_watermark"],
                                       extra_globals={"DEFAULT_WATERMARK": DEFAULT_WATERMARK})
        cases = [
            ("true", "2024-06-01", date(2024, 5, 1)),
            ("false", "2024-06-01", date(2024, 5, 1)),
            ("false", "1900-01-01", date(2024, 5, 15)),
            ("false", "1900-01-01", None),
            ("TRUE", "1900-01-01", None),
            ("", "2024-01-01", None),
            (None, None, None),
        ]
        for pfl, pfd, lld in cases:
            assert nb["resolve_effective_watermark"](pfl, pfd, lld) == \
                   resolve_effective_watermark(pfl, pfd, lld), (
                       f"bronze-to-silver diverges from src/ on "
                       f"({pfl!r}, {pfd!r}, {lld!r})"
                   )

    @pytest.mark.unit
    def test_resolve_effective_watermark_parity_gold(self):
        nb = _load_notebook_functions(GOLD_NOTEBOOK, ["resolve_effective_watermark"],
                                       extra_globals={"DEFAULT_WATERMARK": DEFAULT_WATERMARK})
        cases = [
            ("true", "2024-06-01", date(2024, 5, 1)),
            ("false", "2024-06-01", None),
            ("false", "1900-01-01", date(2024, 5, 15)),
            ("false", "1900-01-01", None),
            (None, None, None),
        ]
        for pfl, pfd, lld in cases:
            assert nb["resolve_effective_watermark"](pfl, pfd, lld) == \
                   resolve_effective_watermark(pfl, pfd, lld)

    @pytest.mark.unit
    def test_metadata_row_parity_bronze(self):
        nb = _load_notebook_functions(BRONZE_NOTEBOOK, ["metadata_row"],
                                       extra_globals={"datetime": datetime})
        now = datetime(2026, 7, 28, 12, 0, 0)
        assert (nb["metadata_row"]("t", date(2024, 6, 1), 100, "SUCCESS",
                                  execution_id="r1", now=now)
                == metadata_row("t", date(2024, 6, 1), 100, "SUCCESS",
                                execution_id="r1", now=now))
        assert (nb["metadata_row"]("t", "2024-06-01", 0, "FAILED",
                                  execution_id=None, now=now)
                == metadata_row("t", "2024-06-01", 0, "FAILED",
                                execution_id=None, now=now))

    @pytest.mark.unit
    def test_metadata_row_parity_gold(self):
        nb = _load_notebook_functions(GOLD_NOTEBOOK, ["metadata_row"],
                                       extra_globals={"datetime": datetime})
        now = datetime(2026, 7, 28, 12, 0, 0)
        assert (nb["metadata_row"]("t", date(2024, 6, 1), 100, "SUCCESS",
                                  execution_id="r1", now=now)
                == metadata_row("t", date(2024, 6, 1), 100, "SUCCESS",
                                execution_id="r1", now=now))

    @pytest.mark.unit
    def test_get_last_load_date_parity_bronze(self, spark):
        nb = _load_notebook_functions(BRONZE_NOTEBOOK, ["get_last_load_date"],
                                       extra_globals={"datetime": datetime})
        rows = [
            metadata_row(DEFAULT_SOURCE_TABLE, date(2024, 6, 1), 100, "SUCCESS",
                          execution_id="r1", now=datetime(2026, 7, 28, 10, 0, 0)),
            metadata_row(DEFAULT_SOURCE_TABLE, date(2024, 6, 3), 200, "SUCCESS",
                          execution_id="r3", now=datetime(2026, 7, 28, 12, 0, 0)),
        ]
        df = _metadata_fixture(spark, rows)
        assert (nb["get_last_load_date"](df, DEFAULT_SOURCE_TABLE)
                == get_last_load_date(df, DEFAULT_SOURCE_TABLE))
        assert (nb["get_last_load_date"](df, DEFAULT_SOURCE_TABLE,
                                          exclude_execution_id="r3")
                == get_last_load_date(df, DEFAULT_SOURCE_TABLE,
                                       exclude_execution_id="r3"))

    @pytest.mark.unit
    def test_get_last_load_date_parity_gold(self, spark):
        nb = _load_notebook_functions(GOLD_NOTEBOOK, ["get_last_load_date"],
                                       extra_globals={"datetime": datetime})
        rows = [
            metadata_row(DEFAULT_SOURCE_TABLE, date(2024, 6, 1), 100, "SUCCESS",
                          execution_id="r1", now=datetime(2026, 7, 28, 10, 0, 0)),
        ]
        df = _metadata_fixture(spark, rows)
        assert (nb["get_last_load_date"](df, DEFAULT_SOURCE_TABLE)
                == get_last_load_date(df, DEFAULT_SOURCE_TABLE))