# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "488fb9f8-e635-4683-90c4-ba4fee9dfadb",
# META       "default_lakehouse_name": "oem_lh",
# META       "default_lakehouse_workspace_id": "99e4cc6d-6ec3-49a7-aed9-b69b04a97aa9",
# META       "known_lakehouses": [
# META         {
# META           "id": "488fb9f8-e635-4683-90c4-ba4fee9dfadb"
# META         }
# META       ]
# META     }
# META   }
# META }

# MARKDOWN ********************

# # bronze_ingest_wgi
# # Automated ingestion of World Governance Indicators (WGI) data from the World Bank API.
# Replaces manual CSV upload via WGI_file2table.Dataflow.
# # **Source:** World Bank API v2 (https://api.worldbank.org/v2/)
# **Target:** bronze_wgi (Delta table, overwrite)
# **License:** World Bank Open Data (commercial use permitted)
# **Update frequency:** Annual (typically September)
# # Retrieves all 6 WGI dimensions (estimate scores):
# - CC.EST: Control of Corruption
# - GE.EST: Government Effectiveness
# - PV.EST: Political Stability and Absence of Violence
# - RL.EST: Rule of Law
# - RQ.EST: Regulatory Quality
# - VA.EST: Voice and Accountability
# # Attribution: Worldwide Governance Indicators, The World Bank Group

# CELL ********************

# Ingestion window — HARDCODED. These are NOT pipeline parameters and nothing overrides
# them at runtime; changing the window means editing this file.
#
# task-072 (verified 2026-08-18, two independent checks):
#   1. This notebook has no Fabric parameters cell. A parameter cell serializes as a cell
#      delimiter of the form "# PARAMETERS CELL" + asterisks, at column 0, in place of the
#      usual "# CELL" delimiter. Probe with the ANCHORED pattern '^# PARAMETERS CELL' --
#      it returns 0 here and 1 in bronze_ingest_epi.Notebook/notebook-content.py (its
#      positive control). Do NOT probe unanchored: this comment mentions the marker by
#      name, so a loose match now hits this very block and inverts the answer.
#   2. The orchestrator pipeline passes this notebook nothing. In
#      orchestrator_pipeline_bronze_to_gold.DataPipeline/pipeline-content.json the
#      `bronze_wgi` activity carries no `parameters` block at all. Positive control: the
#      sibling `bronze_epi` activity does pass `p_epi_year`.
#
# So bronze_epi IS parameterized and bronze_wgi is not. The previous comment here claimed
# these were "overridden by Fabric pipeline at runtime", which would have led a maintainer
# to change a pipeline parameter and see no effect on the WGI window.
#
# Consequence worth knowing: because p_end_year is pinned to 2023, a newly published WGI
# vintage does NOT flow in on its own — someone has to edit this line. bronze_wgi's
# row-count DQ band (see data_quality_checks) is derived on that assumption.
p_start_year = "1996"
p_end_year = "2023"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

import requests
import json
import time
import random
from pyspark.sql import functions as F
from pyspark.sql import Row
from pyspark.sql.types import StructType, StructField, StringType, DoubleType
from datetime import datetime

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Configuration

# CELL ********************

# WGI indicator codes — all 6 governance dimensions (estimate scores).
# NOTE (2026-07-26): the World Bank re-coded WGI in the API. The classic CC.EST / GE.EST / …
# codes were ARCHIVED to source 57 ("WDI Database Archives") and now return
# "indicator not found"; the LIVE estimate series under source 3 are GOV_WGI_*.EST.
# We fetch with the new API codes but STORE the classic short code + name, so the bronze_wgi
# contract (Indicator Code, Series Name) is unchanged for every downstream layer.
# Map: API code -> (canonical Indicator Code, canonical Series Name)
WGI_INDICATORS = {
    "GOV_WGI_CC.EST": ("CC.EST", "Control of Corruption: Estimate"),
    "GOV_WGI_GE.EST": ("GE.EST", "Government Effectiveness: Estimate"),
    "GOV_WGI_PV.EST": ("PV.EST", "Political Stability and Absence of Violence/Terrorism: Estimate"),
    "GOV_WGI_RL.EST": ("RL.EST", "Rule of Law: Estimate"),
    "GOV_WGI_RQ.EST": ("RQ.EST", "Regulatory Quality: Estimate"),
    "GOV_WGI_VA.EST": ("VA.EST", "Voice and Accountability: Estimate"),
}

# World Bank API v2 base URL
API_BASE = "https://api.worldbank.org/v2"

# Retry tuning (task-050). The World Bank API degrades intermittently: on 2026-08-03 it
# timed out on roughly half of all requests for over 75 minutes, and bronze_wgi could not
# complete in either a pipeline run or a standalone probe. The old policy was
# max_retries=3 with `time.sleep(2 * attempt)` — a 2s then 4s wait after a 60s read
# timeout, i.e. it retried straight back into the same congestion and gave the remote side
# no time to recover.
#
# One run fetches 6 indicators x ~6 pages (~5,150 records each at per_page=1000) = ~36
# requests, so at a 50% per-request failure rate a clean run was effectively impossible.
#
# These constants govern the FAILURE PATH ONLY. A run in which nothing times out issues the
# identical request sequence in the identical time, which is what keeps the task-012_1
# performance baseline (bronze_wgi 73s) comparable for the task-012_5 retest.
#
# DO NOT RAISE API_PAGE_SIZE. Tried and measured 2026-08-03 (task-052), on the theory that
# fewer requests means fewer chances to hit the intermittent read timeout. That is wrong for
# this API, in both directions:
#   * SLOWER. At per_page=10000 the API does return pages=1 per indicator (~6 requests per
#     run instead of ~36), but each request cost ~53s against ~0.4-3.9s at per_page=1000.
#     The fetch cell went 265s -> 496s. Serialising one large page costs the server far more
#     than six small ones, and that swamps the request-count saving.
#   * MORE FRAGILE, not less. At ~53s against a 120s read timeout every request sits at ~44%
#     of its budget; at per_page=1000 each uses under 3%. Large pages move every request
#     close to the ceiling rather than reducing exposure - which is how VA.EST page 1 timed
#     out during the very run meant to demonstrate the improvement.
# Data was identical either way (31,122 records; per-indicator counts unchanged), so this is
# purely a latency and robustness finding. Reverted the same day. task-050's backoff is what
# actually fixed the degraded-API case.
API_PAGE_SIZE = 1000     # measured optimum - read the note above before changing
API_READ_TIMEOUT = 120   # was 60 — the server is slow, not absent; give it room to answer
API_MAX_RETRIES = 8      # was 5 (task-066); see the 502 note below
API_BACKOFF_BASE = 5     # seconds; doubles per attempt -> 5, 10, 20, 40, 80, 120, 120
API_BACKOFF_CAP = 120    # seconds; ceiling on any single wait (was 60, task-066)
API_BACKOFF_JITTER = 0.25  # +/- fraction added to each wait, to de-synchronise retries

# --- HTTP 502 from the World Bank API (task-066, measured 2026-08-13) ----------------
# MEASUREMENT. Over the 9 scheduled runs since the 06:00 schedule went live (2026-08-05
# 20:20 test firing through 2026-08-13), bronze_wgi failed the run on 2 of them:
#   2026-08-07 run a80a0c3c  and  2026-08-09 run 7e3f55df
# Both failed all three notebook attempts (1 original + the activity's 2 pipeline
# retries) with the SAME shape:
#   RuntimeError: World Bank API call failed for GOV_WGI_PV.EST (page 3) after 5
#   attempts: 502 Server Error: Bad Gateway for url: https://api.worldbank.org/...
#
# ORIGIN — upstream, not us, and not Fabric. Three independent lines of evidence:
#   1. bronze_wgi is a NOTEBOOK activity issuing a direct `requests.get` from the Spark
#      driver. There is no Fabric HTTP connector / Copy activity anywhere in the path,
#      so the 502 cannot be a Fabric connector artefact — it is the status line the
#      upstream host returned to `raise_for_status()`.
#   2. The failing request is well-formed. Replaying the exact failing URL (PV.EST
#      page 3) on 2026-08-13 returned HTTP 200 in 3.2s with pages=6, total=5400, and a
#      40-request burst across all 6 indicators returned 40x HTTP 200, none slower than
#      10s. The request is fine; the gateway was not.
#   3. The failing indicator/page DIFFERS per attempt (PV p3, CC p3, PV p3 on 08-09;
#      GE p1, RQ p5, GE p1 on 08-07). A malformed request would fail deterministically
#      on the same page every time.
#
# WHY A RETRY IS THE RIGHT FIX HERE — and why that is not a general licence to retry:
# this API signals BAD INPUT IN-BAND, as HTTP 200 with a one-element body
# `[{"message":[{"id":"120","key":"Invalid value", ...}]}]` (probed live 2026-08-13
# with a bogus indicator code). It does NOT use 4xx for bad input. The requests carry
# no credential (World Bank Open Data is unauthenticated), so an auth expiry cannot
# present here at all. A 5xx from this host is therefore necessarily gateway /
# infrastructure level, i.e. genuinely transient. The in-band 200-error case is handled
# separately below, as a PERMANENT failure — see fetch_indicator.
#
# WHY THE BUDGET GREW. The old policy spent 5+10+20+40 = 75s of backoff before giving
# up. That was not enough: on 08-07 attempt 2 ran 41 MINUTES and reached the 5th of 6
# indicators, so the great majority of requests were succeeding throughout the degraded
# window — isolated requests 502'd, and each one burned the whole 75s budget and then
# killed the entire run. 8 attempts with a 120s cap spends 5+10+20+40+80+120+120 = 395s
# (~6.6 min) per request before declaring defeat, which covers an isolated gateway
# wobble while staying hard-bounded. Worst case per run is bounded by the activity's
# 12-hour timeout; a healthy run is unaffected because this is the FAILURE PATH ONLY.
#
# NOT A CURE-ALL. A multi-hour upstream outage will still fail this run, loudly and by
# design — see the completeness guards in fetch_indicator and before the write.

# Date range from parameters
start_year = p_start_year.strip()
end_year = p_end_year.strip()

print(f"WGI Ingestion: Fetching {len(WGI_INDICATORS)} indicators for {start_year}-{end_year}")
for api_code, (short_code, name) in WGI_INDICATORS.items():
    print(f"  - {short_code} (API {api_code}): {name}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Fetch data from World Bank API

# CELL ********************

def is_transient_request_error(exc):
    """Is this requests exception worth retrying? (task-066)

    Retrying a permanent error is not resilience — it delays a loud failure by the
    whole backoff budget and then reports it as an exhausted-retry message, which
    reads like an outage when it is actually a broken request. So classify first.

    TRANSIENT (retry):
      * HTTP 5xx — for this host, necessarily gateway/infrastructure level. See the
        502 note in the config cell: the World Bank API reports bad input in-band as
        HTTP 200, never as 4xx/5xx, and the requests are unauthenticated, so neither
        a malformed request nor an auth expiry can surface here as a 5xx.
      * HTTP 429 — rate limiting. Retryable, but only while honouring Retry-After
        (see retry_delay); hammering a 429 on a blind exponential schedule is exactly
        the papering-over this classification exists to prevent.
      * Transport-level failures with no HTTP response at all: read/connect timeout,
        connection reset, truncated body.

    PERMANENT (raise immediately):
      * Any other 4xx. Nothing this notebook can wait out — the request itself, the
        URL, or an access rule is wrong, and it needs a human.
    """
    response = getattr(exc, "response", None)
    if response is not None:
        status = response.status_code
        if status == 429 or 500 <= status <= 599:
            return True
        return False  # 4xx and anything else with a real status line: permanent
    return isinstance(
        exc,
        (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
        ),
    )


def retry_delay(attempt, response=None):
    """Backoff for one retry: capped exponential + jitter, or the server's Retry-After.

    Doubling gives the remote side progressively more room to recover; the cap stops a
    single dead page stalling the notebook; the jitter de-synchronises retries so
    successive pages don't re-hit the API in lockstep (task-050).

    If the server sent Retry-After (429/503), that instruction wins — it is the one
    number the remote side actually told us, and ignoring it is how a polite retry
    turns into a hammer (task-066).
    """
    if response is not None:
        header = response.headers.get("Retry-After")
        if header:
            try:
                # Retry-After is delta-seconds in every form this API would send.
                return min(max(float(header), 0.0), API_BACKOFF_CAP)
            except ValueError:
                pass  # http-date form — fall through to exponential backoff
    delay = min(API_BACKOFF_BASE * (2 ** (attempt - 1)), API_BACKOFF_CAP)
    delay += random.uniform(-API_BACKOFF_JITTER, API_BACKOFF_JITTER) * delay
    return max(delay, 0.0)


def fetch_indicator(api_code, short_code, series_name, start_year, end_year,
                    max_retries=API_MAX_RETRIES):
    """
    Fetch all country data for a single WGI indicator from the World Bank API.
    Uses JSON format with pagination. Queries the live API code (api_code, e.g.
    GOV_WGI_CC.EST) but records the canonical short_code / series_name so the bronze
    contract stays stable for downstream.

    Returns a list of dicts with keys: country_name, country_code, indicator_code,
    indicator_name, year, value.
    """
    records = []
    page = 1
    total_pages = 1  # Will be updated from API response
    # Completeness accounting (task-066): the API declares how many entries exist for
    # this indicator; we verify we actually walked all of them before returning.
    entries_seen = 0
    declared_total = None

    while page <= total_pages:
        url = f"{API_BASE}/country/all/indicator/{api_code}"
        params = {
            "source": "3",  # WGI source ID
            "format": "json",
            "date": f"{start_year}:{end_year}",
            "per_page": str(API_PAGE_SIZE),
            "page": str(page),
        }

        for attempt in range(1, max_retries + 1):
            try:
                response = requests.get(url, params=params, timeout=API_READ_TIMEOUT)
                response.raise_for_status()
                break
            except requests.exceptions.RequestException as e:
                # Classify BEFORE retrying (task-066). A permanent error must fail now
                # and say so, not 6 minutes later disguised as an exhausted retry.
                if not is_transient_request_error(e):
                    status = getattr(getattr(e, "response", None), "status_code", None)
                    raise RuntimeError(
                        f"World Bank API returned a PERMANENT error for {api_code} "
                        f"(page {page}) — HTTP {status}; not retried, this needs a human: {e}"
                    ) from e
                if attempt == max_retries:
                    raise RuntimeError(
                        f"World Bank API call failed for {api_code} "
                        f"(page {page}) after {max_retries} attempts: {e}"
                    ) from e
                delay = retry_delay(attempt, getattr(e, "response", None))
                print(
                    f"  Retry {attempt}/{max_retries} for {api_code} page {page} "
                    f"in {delay:.1f}s: {e}"
                )
                time.sleep(delay)

        data = response.json()

        # World Bank API returns [metadata, records] on success.
        #
        # It reports BAD INPUT IN-BAND, as HTTP 200 with a ONE-element body:
        #   [{"message":[{"id":"120","key":"Invalid value","value":"..."}]}]
        # (probed live 2026-08-13 with a bogus indicator code). This is a PERMANENT
        # error wearing a 200, and it is not hypothetical: the World Bank already
        # re-coded WGI once (see the WGI_INDICATORS note above, 2026-07-26) and the
        # next re-code lands here. This branch used to `break`, which silently
        # returned however many records had accumulated and let the run go GREEN with
        # an indicator missing — the write below is mode("overwrite"), so that would
        # have destroyed the good snapshot and quietly degraded the governance half of
        # gold_supply_risk. Fail loudly instead (task-066).
        if not isinstance(data, list) or len(data) < 2:
            detail = ""
            if isinstance(data, list) and data and isinstance(data[0], dict):
                detail = f" — upstream said: {data[0].get('message', data[0])}"
            raise RuntimeError(
                f"World Bank API returned an in-band error (HTTP 200, unexpected body) "
                f"for {api_code} page {page}{detail}. This is a PERMANENT error — the "
                f"indicator code or a parameter is no longer valid. Not retried."
            )

        metadata = data[0]
        entries = data[1]

        # Likewise a null record set. A page past the end returns [], not None, so
        # None means the indicator itself yielded nothing — never true for the 6 WGI
        # series (each declares total=5400). Previously a silent `break`.
        if entries is None:
            raise RuntimeError(
                f"World Bank API returned no record set (null) for {api_code} page "
                f"{page}. Expected data for every WGI indicator; refusing to write a "
                f"partial snapshot."
            )

        total_pages = metadata.get("pages", 1)
        if declared_total is None:
            declared_total = metadata.get("total")
        entries_seen += len(entries)

        for entry in entries:
            # Skip entries with no value
            value = entry.get("value")
            if value is None:
                continue

            records.append({
                "country_name": entry.get("country", {}).get("value", ""),
                "country_code": entry.get("countryiso3code", ""),
                "indicator_code": short_code,
                "indicator_name": series_name,
                "year": entry.get("date", ""),
                "value": float(value),
            })

        page += 1

    # Pagination completeness (task-066). `total` is the upstream's own count of
    # entries for this indicator, so this is an exact "did I get everything" test
    # rather than a guess at a plausible floor. A short read here means pagination
    # stopped early — write nothing rather than a truncated snapshot.
    if declared_total is not None and entries_seen != declared_total:
        raise RuntimeError(
            f"Incomplete pagination for {api_code}: walked {entries_seen} entries but "
            f"the API declared {declared_total} across {total_pages} pages. Refusing "
            f"to write a partial snapshot."
        )

    return records


# Fetch all indicators
all_records = []
per_indicator_counts = {}
for api_code, (short_code, series_name) in WGI_INDICATORS.items():
    print(f"  Fetching {short_code} (API {api_code})...")
    indicator_records = fetch_indicator(api_code, short_code, series_name, start_year, end_year)
    # An indicator that yields zero usable records is a failure, not an empty result:
    # every WGI series has data for this window. Catching it here names the culprit,
    # instead of letting a 1-of-6 shortfall vanish into a still-plausible total
    # (task-066 — when this guard was written the bronze_wgi DQ row-count band was
    # 50..500,000, so losing a whole indicator, ~5,000 rows out of ~31,000, sailed through
    # it. task-073 has since tightened that band to 28,000..45,000, which does catch the
    # same loss, so this guard is now the source-side half of a two-layer defence rather
    # than the only thing between a partial fetch and a silent overwrite).
    if len(indicator_records) == 0:
        raise RuntimeError(
            f"No usable records returned for {short_code} (API {api_code}). Every WGI "
            f"indicator must yield data for {start_year}-{end_year}; refusing to write "
            f"a partial snapshot."
        )
    per_indicator_counts[short_code] = len(indicator_records)
    all_records.extend(indicator_records)
    print(f"    -> {len(indicator_records)} records")
    # Brief pause between indicators to be a good API citizen
    time.sleep(0.5)

print(f"\n  Total records fetched: {len(all_records):,}")
print(f"  Per-indicator: {per_indicator_counts}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Write to bronze layer
# # The downstream `bronze-to-silver` notebook reads `bronze_wgi` and expects columns:
# `Country Name`, `Country Code`, `Series Name`.
# # We write the full API data to `bronze_wgi` with those columns plus additional
# fields (indicator_code, year, value) that enrich the dataset beyond what the
# manual CSV upload provided.

# CELL ********************

if len(all_records) == 0:
    raise RuntimeError(
        "No WGI records fetched from API. Check network connectivity, "
        "API availability, and date range parameters."
    )

# Last gate before an OVERWRITE (task-066). The write below replaces bronze_wgi
# wholesale, so anything short of a complete snapshot must stop here — a partial
# overwrite is worse than no run at all: it destroys the good data, reports success,
# and silently degrades the governance half of gold_supply_risk. That degradation
# would be indistinguishable from the project's one LEGITIMATE governance gap
# (Taiwan, which has no WGI data by permanent design), which is precisely why this
# must fail loudly rather than shrink quietly.
fetched_indicators = {r["indicator_code"] for r in all_records}
expected_indicators = {short for short, _ in WGI_INDICATORS.values()}
missing_indicators = expected_indicators - fetched_indicators
if missing_indicators:
    raise RuntimeError(
        f"Refusing to overwrite bronze_wgi with a partial snapshot: "
        f"{len(missing_indicators)} of {len(expected_indicators)} indicators missing "
        f"({sorted(missing_indicators)}). Fetched: {sorted(fetched_indicators)}."
    )

# Define schema matching downstream expectations
# Column names match what bronze-to-silver expects: "Country Name", "Country Code", "Series Name"
schema = StructType([
    StructField("Country Name", StringType(), True),
    StructField("Country Code", StringType(), True),
    StructField("Series Name", StringType(), True),
    StructField("Indicator Code", StringType(), True),
    StructField("Year", StringType(), True),
    StructField("Value", DoubleType(), True),
])

# Build rows
rows = [
    Row(
        **{
            "Country Name": r["country_name"],
            "Country Code": r["country_code"],
            "Series Name": r["indicator_name"],
            "Indicator Code": r["indicator_code"],
            "Year": r["year"],
            "Value": r["value"],
        }
    )
    for r in all_records
]

spark_df = spark.createDataFrame(rows, schema)

# Write to bronze layer (overwrite — WGI is a full snapshot refresh)
table_name = "bronze_wgi"
spark_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(table_name)

row_count = spark.sql(f"SELECT COUNT(*) as cnt FROM oem_lh.{table_name}").first()["cnt"]
print(f"  Written to {table_name}: {row_count:,} rows")
print(f"  Ingestion complete at {datetime.now().isoformat()}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Validation

# CELL ********************

# Quick validation: show sample data and coverage stats
print("Sample records:")
df_sample = spark.sql("""
    SELECT `Country Name`, `Country Code`, `Series Name`, `Indicator Code`, `Year`, `Value`
    FROM oem_lh.bronze_wgi
    WHERE `Country Code` IN ('USA', 'CHN', 'DEU', 'SWE', 'JPN')
    AND `Year` = '2022'
    ORDER BY `Country Name`, `Indicator Code`
""")
display(df_sample)

# Coverage summary
print("\nCoverage by indicator:")
df_coverage = spark.sql("""
    SELECT
        `Indicator Code`,
        `Series Name`,
        COUNT(DISTINCT `Country Code`) as countries,
        COUNT(DISTINCT `Year`) as years,
        COUNT(*) as total_records,
        ROUND(MIN(`Value`), 2) as min_value,
        ROUND(MAX(`Value`), 2) as max_value
    FROM oem_lh.bronze_wgi
    GROUP BY `Indicator Code`, `Series Name`
    ORDER BY `Indicator Code`
""")
display(df_coverage)

# Check for null country codes
null_check = spark.sql("""
    SELECT
        SUM(CASE WHEN `Country Name` IS NULL OR `Country Name` = '' THEN 1 ELSE 0 END) as null_country_name,
        SUM(CASE WHEN `Country Code` IS NULL OR `Country Code` = '' THEN 1 ELSE 0 END) as null_country_code,
        SUM(CASE WHEN `Series Name` IS NULL OR `Series Name` = '' THEN 1 ELSE 0 END) as null_series_name,
        COUNT(*) as total_rows
    FROM oem_lh.bronze_wgi
""")
display(null_check)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
