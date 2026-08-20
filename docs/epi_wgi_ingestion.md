# External Data Source Automation - OEMMatInsightBI

**Status:** Implementation Complete
**Last Updated:** 2026-04-05
**Owner:** Claude Code

## Executive Summary

This document provides comprehensive research findings on automating the ingestion of external ESG data sources (EPI and WGI) into the OEMMatInsightBI pipeline. Both data sources are **feasible for automation** with different approaches.

**Key Findings:**
- ✅ **EPI (Yale):** Direct CSV downloads available, no API required
- ✅ **WGI (World Bank):** REST API with CSV export capability
- ⚠️ **License:** EPI is non-commercial only (CC BY-NC-SA 4.0)
- 🔄 **Update Frequency:** Both annual updates (sufficient for use case)

**Implementation (2026-04-05):**
- ✅ **EPI notebook:** `fabric/bronze_ingest_epi.Notebook/` — downloads CSV via `requests`, writes to `bronze_epi2024results` and `bronze_epi2024weights` (task-056: the weights file is the source for `silver_epi2024variables` → `gold_dim_indicator.weight`, which the `Weighted EPI Score` DAX measure consumes)
- ✅ **WGI notebook:** `fabric/bronze_ingest_wgi.Notebook/` — calls World Bank API v2 (JSON), writes to `bronze_wgi`
- ✅ **Pipeline wiring:** done (task-035, 2026-07-26) — `bronze_EPI` and `bronze_wgi` are
  TridentNotebook activities in `orchestrator_pipeline_bronze_to_gold`
- ✅ **Dataflows decommissioned:** the `EPI_file2table` / `WGI_file2table` items were
  deleted from the workspace 2026-08-10 after two weeks orphaned. Snapshot:
  `.claude/support/retired/epi-wgi-file2table-dataflows/manifest.json`

---

## 1. Environmental Performance Index (EPI) - Yale

### Data Source Overview
- **Provider:** Yale Center for Environmental Law & Policy
- **URL:** https://epi.yale.edu/
- **Latest Version:** 2024 (published June 2024)
- **Update Frequency:** Annual (typically June)
- **Coverage:** 180+ countries, 58 environmental indicators

### Available Data Downloads

#### CSV Files (Direct HTTP Access)

| File Name | URL | Size | Purpose |
|-----------|-----|------|---------|
| **2024 Results** | `https://epi.yale.edu/downloads/epi2024results.csv` | ~50 KB | Current and baseline aggregated scores |
| **2024 Variables** | `https://epi.yale.edu/downloads/epi2024variables2024-12-11.csv` | ~20 KB | Field definitions and abbreviations |
| **2024 Weights** | `https://epi.yale.edu/downloads/epi2024weights.csv` | ~5 KB | Indicator weighting methodology |
| **2024 Targets** | `https://epi.yale.edu/downloads/epi2024targets.csv` | ~10 KB | Performance targets |

#### ZIP Archives (Manual Processing)

| File Name | URL | Size | Contents |
|-----------|-----|------|----------|
| **2024 Raw Data** | `https://epi.yale.edu/downloads/epi2024raw.zip` | ~5 MB | Unprocessed source data files |
| **2024 Indicator Scores** | `https://epi.yale.edu/downloads/epi2024indicators.zip` | ~2 MB | Individual indicator scores |

### Automation Feasibility: ✅ HIGH

**Recommended Approach:** HTTP Download via Copy Activity

#### Implementation Plan

**Option 1: Fabric Copy Activity (Recommended)**
```json
{
  "source": {
    "type": "HttpSource",
    "httpRequestTimeout": "00:05:00"
  },
  "sourceSettings": {
    "requestMethod": "GET",
    "additionalHeaders": "User-Agent: OEMMatInsightBI-Pipeline/1.0"
  },
  "inputs": [{
    "type": "HttpDataset",
    "linkedService": {
      "type": "HttpServer",
      "baseUrl": "https://epi.yale.edu/downloads/"
    },
    "relativeUrl": "epi2024results.csv"
  }],
  "sink": {
    "type": "LakehouseSink",
    "tableName": "bronze_epi2024results"
  }
}
```

**Option 2: Python Notebook (Alternative)**
```python
import requests
import pandas as pd

def download_epi_data():
    """Download EPI data directly to lakehouse"""

    urls = {
        "results": "https://epi.yale.edu/downloads/epi2024results.csv",
        "variables": "https://epi.yale.edu/downloads/epi2024variables2024-12-11.csv",
        "weights": "https://epi.yale.edu/downloads/epi2024weights.csv"
    }

    for name, url in urls.items():
        # Download CSV
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        # Parse CSV
        df = pd.read_csv(io.StringIO(response.text))

        # Write to lakehouse
        spark_df = spark.createDataFrame(df)
        spark_df.write.format("delta").mode("overwrite").saveAsTable(f"bronze_epi_{name}")

        print(f"✓ Downloaded {name}: {len(df)} rows")
```

> **Implementation status (task-056, 2026-08-04):** `bronze_ingest_epi.Notebook` now
> downloads **both** `epi{year}results.csv` (→ `bronze_epi{year}results`) **and**
> `epi{year}weights.csv` (→ `bronze_epi{year}weights`). The `variables` URL above is
> still **not** ingested — the weights file alone provides the hierarchy + absolute
> `EPI Percent` weights that `silver_to_gold.Notebook` builds `silver_epi{year}variables`
> from (mapped `weight` ← `EPI Percent`). The `bronze_epi_{name}` table-naming shown
> in this sketch is illustrative; the live notebook uses `bronze_epi{year}results` /
> `bronze_epi{year}weights` (year-suffixed, per task-028's parameterised coupling).

### Data Structure

**EPI Results Schema (2024):**
```
iso3 (String)           # Country ISO3 code
country_name (String)   # Country name
region (String)         # Geographic region
epi_score (Double)      # Overall EPI score (0-100)
epi_rank (Integer)      # Global ranking
[58 indicator scores]   # Individual environmental indicators
```

### Licensing & Usage Restrictions

**License:** Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)

**Restrictions:**
- ❌ **Commercial use prohibited** (SwiftBike Tech use case is compliant if internal only)
- ✅ **Attribution required** ("Source: Yale Environmental Performance Index 2024")
- ✅ **Share-alike** (derivatives must use same license)
- ✅ **Educational/research use** fully permitted

**Compliance for OEMMatInsightBI:**
- ✅ Internal analytics dashboard: **COMPLIANT**
- ✅ Portfolio project (non-commercial): **COMPLIANT**
- ⚠️ Client-facing product for sale: **NOT COMPLIANT**

### Update Strategy

**Historical Versions:**
- 2022, 2020, 2018, 2016... (biennial until 2020)
- All versions available at SEDAC: https://sedac.ciesin.columbia.edu/data/collection/epi

**Automation Trigger:**
- Manual trigger annually (June each year)
- Check for new version: monitor https://epi.yale.edu/ for announcements
- URL pattern: `epi{YYYY}results.csv`

---

## 2. Worldwide Governance Indicators (WGI) - World Bank

### Data Source Overview
- **Provider:** World Bank Group
- **URL:** https://www.worldbank.org/en/publication/worldwide-governance-indicators
- **Latest Version:** 2024 update (covers 2022-2023 data)
- **Update Frequency:** Annual (typically September)
- **Coverage:** 200+ countries, 6 governance dimensions

### Available Access Methods

#### Method 1: World Bank API (Recommended)

**Base URL:** `https://api.worldbank.org/v2/`

**API Structure:**
```
GET /v2/country/{countries}/indicator/{indicator}?source=3&downloadformat=csv
```

**WGI Indicator Codes:**

| Dimension | Estimate Code | Std Error | Percentile Rank | No. Sources |
|-----------|---------------|-----------|-----------------|-------------|
| Control of Corruption | `CC.EST` | `CC.STD.ERR` | `CC.PER.RNK` | `CC.NO.SRC` |
| Government Effectiveness | `GE.EST` | `GE.STD.ERR` | `GE.PER.RNK` | `GE.NO.SRC` |
| Political Stability | `PV.EST` | `PV.STD.ERR` | `PV.PER.RNK` | `PV.NO.SRC` |
| Rule of Law | `RL.EST` | `RL.STD.ERR` | `RL.PER.RNK` | `RL.NO.SRC` |
| Regulatory Quality | `RQ.EST` | `RQ.STD.ERR` | `RQ.PER.RNK` | `RQ.NO.SRC` |
| Voice and Accountability | `VA.EST` | `VA.STD.ERR` | `VA.PER.RNK` | `VA.NO.SRC` |

**Example API Calls:**
```bash
# All countries, all governance indicators (estimates only)
https://api.worldbank.org/v2/country/all/indicator/CC.EST;GE.EST;PV.EST;RL.EST;RQ.EST;VA.EST?source=3&downloadformat=csv&date=2022:2023

# Specific countries, control of corruption
https://api.worldbank.org/v2/country/USA;CHN;DEU;JPN/indicator/CC.EST?source=3&downloadformat=csv&date=2020:2023

# All WGI data with metadata
https://api.worldbank.org/v2/country/all/indicator/CC.EST?source=3&format=json&per_page=1000
```

#### Method 2: DataBank Interface (Manual)

**URL:** https://databank.worldbank.org/source/worldwide-governance-indicators

**Process:**
1. Select countries (all or specific)
2. Select indicators (6 dimensions × 4 metrics = 24 series)
3. Select years (1996-2023 available)
4. Download → CSV/Excel

### Automation Feasibility: ✅ HIGH

**Recommended Approach:** HTTP API via Fabric Copy Activity or Python

#### Implementation Plan

**Option 1: Fabric HTTP Linked Service**
```json
{
  "name": "WGI_API_Download",
  "type": "Copy",
  "inputs": [{
    "type": "HttpDataset",
    "linkedService": {
      "type": "HttpServer",
      "baseUrl": "https://api.worldbank.org/v2/"
    },
    "relativeUrl": "country/all/indicator/CC.EST;GE.EST;PV.EST;RL.EST;RQ.EST;VA.EST",
    "requestMethod": "GET",
    "additionalHeaders": "Accept: text/csv",
    "queryParameters": {
      "source": "3",
      "downloadformat": "csv",
      "date": "2022:2023"
    }
  }],
  "sink": {
    "type": "LakehouseSink",
    "tableName": "bronze_wgi_latest"
  }
}
```

**Option 2: Python Notebook (Flexible)**
```python
import requests
import pandas as pd
from io import StringIO

def download_wgi_data(start_year=2020, end_year=2023):
    """
    Download WGI data from World Bank API

    Args:
        start_year: First year to download
        end_year: Last year to download
    """

    # WGI indicator codes (estimates only for simplicity)
    indicators = [
        "CC.EST",  # Control of Corruption
        "GE.EST",  # Government Effectiveness
        "PV.EST",  # Political Stability
        "RL.EST",  # Rule of Law
        "RQ.EST",  # Regulatory Quality
        "VA.EST"   # Voice and Accountability
    ]

    # Build API URL
    indicator_string = ";".join(indicators)
    base_url = "https://api.worldbank.org/v2"
    url = f"{base_url}/country/all/indicator/{indicator_string}"

    params = {
        "source": "3",           # WGI source ID
        "downloadformat": "csv",
        "date": f"{start_year}:{end_year}",
        "per_page": "20000"     # Ensure all records returned
    }

    # Download data
    print(f"Downloading WGI data for {start_year}-{end_year}...")
    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()

    # Parse CSV (World Bank returns ZIP with metadata + data CSV)
    # Handle ZIP extraction if needed
    df = pd.read_csv(StringIO(response.text))

    # Transform to lakehouse format
    spark_df = spark.createDataFrame(df)

    # Write to bronze layer
    spark_df.write.format("delta").mode("overwrite").saveAsTable("oem_lh.bronze_wgi_raw")

    print(f"✓ Downloaded {len(df)} rows")
    return df
```

### Data Structure

**WGI API Response Schema:**
```
Country Name (String)
Country Code (String)         # ISO3 code
Series Name (String)          # Indicator name
Series Code (String)          # Indicator code (CC.EST, etc.)
2022 [YR2022] (Double)       # Year-specific columns
2023 [YR2023] (Double)
```

**Recommended Transformation:**
```python
# Pivot from wide to long format
df_long = df.melt(
    id_vars=["Country Name", "Country Code", "Series Name", "Series Code"],
    var_name="year_column",
    value_name="value"
)

# Clean year column
df_long["year"] = df_long["year_column"].str.extract(r"(\d{4})").astype(int)

# Result schema:
# country_code, country_name, indicator_code, indicator_name, year, value
```

### Licensing & Usage Restrictions

**License:** Open Data (World Bank Terms of Use)

**Restrictions:**
- ✅ **Commercial use permitted**
- ✅ **No attribution required** (but recommended)
- ✅ **Redistribution allowed**
- ✅ **Modification allowed**

**Compliance:** Fully compliant for all use cases.

### Update Strategy

**Historical Data:**
- Full time series: 1996-2023 available
- Annual updates typically September

**Automation Trigger:**
- Check for new year: Query API with `date=2024` (will fail if not available)
- Incremental download: Only fetch latest year after September

**Error Handling:**
```python
def check_wgi_update_available(year):
    """Check if WGI data is available for a given year"""
    test_url = f"https://api.worldbank.org/v2/country/USA/indicator/CC.EST"
    params = {"source": "3", "format": "json", "date": year}

    response = requests.get(test_url, params=params)
    data = response.json()

    # Check if data exists for that year
    if len(data) > 1 and len(data[1]) > 0:
        return True
    return False

# Usage
if check_wgi_update_available(2024):
    download_wgi_data(2024, 2024)
else:
    print("2024 data not yet available")
```

### Failure Handling in `bronze_ingest_wgi` (task-066, 2026-08-13)

**Measured failure rate.** Across the 9 scheduled runs from 2026-08-05 to 2026-08-13,
`bronze_wgi` failed the pipeline run on **2 of 9** — runs `a80a0c3c` (2026-08-07) and
`7e3f55df` (2026-08-09). Each burned all three notebook attempts (1 original + the
activity's 2 pipeline retries) on `502 Server Error: Bad Gateway` from
`api.worldbank.org`. The four most recent scheduled runs (08-10 → 08-13) were all green.

**The 502 is upstream, not Fabric and not a bad request.** `bronze_wgi` is a *Notebook*
activity issuing a direct `requests.get` from the Spark driver — there is no Fabric HTTP
connector in the path, so the 502 is the status line the World Bank's gateway returned.
Replaying the exact failing URL on 2026-08-13 gave HTTP 200 in 3.2 s, and a 40-request
burst across all 6 indicators returned 40× 200. The failing indicator/page also *differs
per attempt* (PV p3, CC p3, PV p3 on 08-09; GE p1, RQ p5, GE p1 on 08-07), which a
malformed request would not do.

**Why a retry is the right fix for this particular 5xx.** The World Bank API reports bad
input **in-band** — HTTP 200 with a one-element body
`[{"message":[{"id":"120","key":"Invalid value",...}]}]` — not as 4xx. The requests carry
no credential (World Bank Open Data is unauthenticated), so an auth expiry cannot present
here either. A 5xx from this host is therefore necessarily gateway/infrastructure level.

> **Partly superseded (task-075, 2026-08-20).** The paragraph above is unchanged and still
> correct about 5xx. What it *also* implied — that a 4xx must therefore be a genuinely
> malformed request, and so permanent — was falsified by measurement on 2026-08-17. The
> live classification table and the total attempt budget now live in **§ Retry ownership
> and the total attempt budget**, immediately below; read that, not this section, for
> current policy.

The widened per-request budget dates from here: on 08-07 attempt 2 ran **41 minutes** and
reached the 5th of 6 indicators, so most requests were succeeding throughout the degraded
window and isolated 502s were each killing the whole run inside the old 75 s budget.

**No silent partial load.** The write is `mode("overwrite")`, so a partial fetch would
destroy a good snapshot, report success, and quietly degrade the governance half of
`gold_supply_risk` — indistinguishable from the project's one *legitimate* governance gap
(Taiwan, which has no WGI data by permanent design). Four guards now make an incomplete
fetch fail loudly instead:

1. **In-band 200 error body** → raise (previously a `break` that silently returned
   whatever had accumulated). This is the path a future WGI re-code will take — the World
   Bank already re-coded these series once, in 2026-07.
2. **Null record set** → raise (previously a `break`).
3. **Pagination completeness** → the API declares `total` per indicator; if the walked
   entry count differs, raise.
4. **All-indicators check before the write** → every one of the 6 canonical codes must be
   present, or refuse to overwrite.

Guard 4 mattered because, at the time it was written, the bronze DQ row-count band for
`bronze_wgi` was 50–500,000: losing a whole indicator (~5,000 of ~31,000 rows) passed that
check comfortably, so the DQ layer would *not* have caught it. task-073 has since tightened
that band to **28,000–45,000** (derivation in `docs/data_quality_framework.md` § 2.1), which
does catch the same loss. Guard 4 is therefore now the source-side half of a two-layer
defence — it names the culprit indicator at fetch time and refuses the overwrite, while the
DQ band is the backstop if a shortfall ever reaches the table by another route.

Regression tests: `tests/test_wgi_retry.py`, which extracts the notebook's own
`is_transient_request_error` / `retry_delay` / `fetch_indicator` via `ast` under the
reference-implementation contract, so editing the retry policy fails CI by design.

### Retry ownership and the total attempt budget (task-075, 2026-08-20)

**This subsection is the single canonical answer to "how many attempts does a failing
`bronze_wgi` actually get?"** The notebook and the pipeline JSON both point here; neither
restates the arithmetic. If you change either layer, change this table in the same commit.

**What forced this.** On the 2026-08-17 04:00 scheduled run (`cb9be8a4-4067-4045-a9cd-35d391e2ed55`,
re-read from `queryactivityruns` 2026-08-20; the run itself finished **Completed**, so
nothing surfaced anywhere else):

| Attempt | Outcome | Start | Duration | Detail |
|---|---|---|---|---|
| 1 | **Failed** (errorCode 2451, UserError) | 04:00:03 | 168 s | task-066's own path: `World Bank API returned a PERMANENT error for GOV_WGI_CC.EST (page 1) — HTTP 400; not retried, this needs a human` |
| 2 | **Succeeded** | 04:03:22 | 968 s | **byte-identical URL**, unchanged |

The ~31 s gap between attempt 1 ending and attempt 2 starting matches the activity's
`retryIntervalInSeconds: 30` exactly, which pins the second attempt on the **activity
policy**, not on anything inside the notebook. (`retryAttempt` is `null` on both rows —
that is the documented `queryactivityruns` contract, not a missing retry.) So two things
were wrong at once: a 400 was declared permanent when it demonstrably was not, and the
notebook's deliberate "do not retry this" was being overridden one layer up anyway.

**Ownership decision: the notebook owns the retry budget; the activity retries zero times.**
`policy.retry` on the `bronze_wgi` activity went **2 → 0** (`retryIntervalInSeconds: 30`
left in place but now inert). Only the notebook can tell a gateway wobble from a retired
indicator code, so the budget belongs where the semantic knowledge is; a blind activity
retry is precisely what made the in-notebook classification inert. **Accepted trade-off:**
a notebook-*infrastructure* failure (Spark session start, driver OOM) now gets no retry
either, where previously it got two. That is a deliberate exchange of infrastructure
resilience for correct, fast failure on real API errors — not an oversight.

**Classification** (failure path only — a clean run issues the identical request sequence
in the identical time):

| Condition | Treatment | Why |
|---|---|---|
| HTTP 5xx | **Transient** → retry, capped exponential backoff + jitter | Gateway/infrastructure only; this host never reports bad input as 5xx |
| HTTP 429 | **Transient** → retry, but **`Retry-After` wins** over the exponential schedule | Hammering a rate limit is the papering-over the classifier exists to prevent |
| HTTP 400 | **Transient** → retry | Measured spurious 2026-08-17: identical URL succeeded 3 min later. Because this API reports bad input in-band as HTTP 200, a 400 here cannot mean "malformed request" — it is gateway noise |
| HTTP 408 | **Transient** → retry | A timeout that happens to carry a status line |
| Timeout / connection reset / truncated body | **Transient** → retry | No HTTP response at all — task-050's original case |
| HTTP 401 / 403 | **Permanent** → raise immediately | Auth genuinely needs a human, and waiting cannot fix it. Unreachable today (the API is unauthenticated) |
| HTTP 404 | **Permanent** → raise immediately | A retired or renamed indicator path. WGI was re-coded once already (2026-07-26); a retry cannot resurrect a removed route |
| Any other status | **Permanent** → raise immediately | Fail closed. Retrying *all* 4xx would restore the unbounded-retry behaviour task-066 removed |
| HTTP 200 with the in-band error body | **Permanent** → raise, naming the upstream message | This is how the World Bank actually reports a bad indicator code |

**Total attempts, both layers:**

| Failure class | Notebook attempts | Activity attempts | **Total** | Wall clock to red |
|---|---|---|---|---|
| Transient (5xx / 429 / 400 / 408 / transport) | up to 8 per request | 1 (no retry) | **8** | **~4.9–8.2 min** of backoff per request — see the note below; bounded above by the activity's 12 h timeout |
| Permanent (401 / 403 / 404 / unclassified / in-band 200) | **1** — raises on the first response | 1 (no retry) | **1** | **~3 min** if the failing indicator is the *first* fetched (essentially Spark session start); ~16 min if it is the *last*, since the earlier indicators must be fetched to reach it |

**Backoff arithmetic, stated exactly** (the figure here was previously given as
"≤ ~6.6 min", which was wrong in both directions and is corrected as of 2026-08-21):

- The **nominal** schedule between 8 attempts is 7 sleeps — 5→10→20→40→80→120→120 s
  (`API_BACKOFF_BASE` 5, doubling, `API_BACKOFF_CAP` 120) = **395 s ≈ 6.6 min**. That is a
  *midpoint*, not a ceiling.
- `API_BACKOFF_JITTER` is `0.25`, applied multiplicatively per sleep
  (`delay += uniform(-0.25, +0.25) * delay`), so each wait lands in `[0.75d, 1.25d]` and the
  total lands in **296–494 s ≈ 4.9–8.2 min**. An instrumented exhaustion run measured
  441.7 s (7.4 min) — inside that band, and *above* the old "≤ 6.6 min" claim.
- **Absolute ceiling: ~14 min.** `Retry-After` wins over the exponential schedule (see the
  classification table) and is clamped to the same 120 s cap, so a server sending it at or
  above the cap on all 7 retries yields 7 × 120 s = 840 s. Rare, but it is the real bound.

Before task-075 the permanent row read *3 total attempts and ~35 min to red*. Comparing that
to the ~3 min above would be **best case against worst case** — the honest pairing is
**~3 → ~10 min** for a first-indicator failure, or **~16 → ~50 min** for a last-indicator one,
because the activity re-ran the whole notebook each time. The unambiguous figure is the
attempt count: **3 → 1** on the permanent path, and **24 → 8** requests on the transient one.
The exact scenario task-066 built the permanent path for — a retired indicator code — was
still being retried twice before anyone was told.

Regression tests: `tests/test_wgi_retry.py` pins both halves — the classification table
above against the notebook's own extracted functions, **and** `policy.retry == 0` read out
of `pipeline-content.json`, because the notebook's "not retried" failure message is only
truthful while that stays 0.

---

## 3. Implementation Roadmap

### Phase 1: Replace Manual Dataflows (Quick Win)

> **Implemented 2026-07-26 (task-035):** the pipeline now runs `bronze_ingest_epi` and
> `bronze_ingest_wgi` TridentNotebook activities. The "Target State" below (Copy
> activities) was the original 2026-04-05 design; the shipped solution uses notebooks
> instead, which avoid the dataflow credential-stripping problem. The original Phase 1
> text is retained as historical design context.

**Current State (pre-task-035, historical):**
- `EPI_file2table.Dataflow` - Manual file upload
- `WGI_file2table.Dataflow` - Manual file upload (was WB_file2table)

**Target State (original 2026-04-05 design — superseded by notebooks):**
- `EPI_HTTP_download.CopyActivity` - Automated download from Yale
- `WGI_API_download.CopyActivity` - Automated download from World Bank API

**Estimated Effort:** 0.5-1 day

#### Step 1: Create HTTP Linked Services (30 minutes)

**EPI Linked Service:**
```json
{
  "name": "LS_HTTP_EPI_Yale",
  "type": "HttpServer",
  "typeProperties": {
    "url": "https://epi.yale.edu/downloads/",
    "authenticationType": "Anonymous"
  }
}
```

**WGI Linked Service:**
```json
{
  "name": "LS_HTTP_WGI_WorldBank",
  "type": "HttpServer",
  "typeProperties": {
    "url": "https://api.worldbank.org/v2/",
    "authenticationType": "Anonymous"
  }
}
```

#### Step 2: Create Copy Activities (1 hour)

**Copy EPI Data:**
- Source: HTTP (epi2024results.csv)
- Sink: Lakehouse table (bronze_epi2024results)
- Schedule: Annual (June)

**Copy WGI Data:**
- Source: HTTP API (with query parameters)
- Sink: Lakehouse table (bronze_wgi_raw)
- Schedule: Annual (September)

#### Step 3: Update Pipeline (30 minutes)

Add new activities to `orchestrator_pipeline_bronze_to_gold`:
```
[New Stage: External Data Download]
├─ EPI_HTTP_download (Copy Activity)
└─ WGI_API_download (Copy Activity)

[Existing Stage: Bronze Ingestion]
├─ Continue with existing bronze transformations
```

#### Step 4: Test & Validate (1 hour)

- Run EPI download → Verify row count (~180 countries)
- Run WGI download → Verify row count (~200 countries × 6 indicators × 2 years = ~2,400 rows)
- Check data quality (no nulls in country codes)
- Validate schema matches existing bronze tables

### Phase 2: Version Management (Enhancement)

**Goal:** Handle multiple EPI/WGI versions for historical analysis

**Implementation:**
```python
# Parameterize download by year
def download_epi_by_year(year):
    """Download specific EPI version"""
    url = f"https://epi.yale.edu/downloads/epi{year}results.csv"
    # Download and version with year column
    df["epi_year"] = year
    spark_df.write.format("delta").mode("append").saveAsTable("bronze_epi_historical")

# Download multiple years
for year in [2020, 2022, 2024]:
    download_epi_by_year(year)
```

### Phase 3: Monitoring & Alerts (Production-Ready)

**Goal:** Automated checks for data availability

**Features:**
- Check for new EPI version (June each year)
- Check for new WGI version (September each year)
- Email alert when new data available
- Automatic pipeline trigger

**Implementation:**
```python
# In a scheduled notebook (monthly)
def check_for_updates():
    """Check if new external data is available"""

    # Check EPI (expected June)
    epi_response = requests.head("https://epi.yale.edu/downloads/epi2025results.csv")
    if epi_response.status_code == 200:
        send_alert("New EPI 2025 data available!")
        trigger_pipeline("EPI_HTTP_download")

    # Check WGI (expected September)
    if check_wgi_update_available(2024):
        send_alert("New WGI 2024 data available!")
        trigger_pipeline("WGI_API_download")
```

---

## 4. Risk Assessment & Mitigation

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **URL structure changes** | Medium | High | Version URLs, monitor for 404 errors, maintain historical URLs |
| **Data schema changes** | Low | Medium | Schema validation in bronze layer, fail pipeline on mismatch |
| **Rate limiting (WGI API)** | Low | Low | Implement retry logic with exponential backoff |
| **License violation (EPI)** | Low | High | Document non-commercial use, add license notice to reports |
| **Yale server downtime** | Low | Medium | Retry logic, fallback to manual download if automation fails |
| **World Bank API deprecation** | Very Low | Medium | Monitor API documentation, have DataBank manual process as backup |

### Mitigation Strategies

**URL Monitoring:**
```python
def validate_url_accessible(url):
    """Check if URL is accessible before download"""
    try:
        response = requests.head(url, timeout=10)
        return response.status_code == 200
    except requests.RequestException:
        return False

# Pre-flight check
if not validate_url_accessible(epi_url):
    raise ValueError(f"EPI URL not accessible: {epi_url}")
```

**Schema Validation:**
```python
def validate_epi_schema(df):
    """Validate EPI data has expected columns"""
    required_cols = ["iso3", "country_name", "epi_score"]
    missing = set(required_cols) - set(df.columns)

    if missing:
        raise ValueError(f"Missing required columns: {missing}")
```

---

## 5. Cost & Performance Considerations

### Data Volume

| Source | File Size | Row Count | Update Frequency | Annual Data Volume |
|--------|-----------|-----------|------------------|-------------------|
| **EPI Results** | ~50 KB | ~180 | Annual | 50 KB/year |
| **WGI API** | ~500 KB | ~2,400 | Annual | 500 KB/year |
| **Total** | ~550 KB | ~2,580 | Annual | **< 1 MB/year** |

**Verdict:** Negligible storage and bandwidth costs.

### Pipeline Performance

> **Note:** the "Current (Manual Upload)" state below is the pre-task-035 baseline.
> Since task-035 (2026-07-26) the pipeline runs the `bronze_ingest_epi` and
> `bronze_ingest_wgi` TridentNotebook activities directly — the "Automated" column is
> the shipped state.

**Current (Manual Upload, pre-task-035):**
- User downloads files manually
- User uploads to Fabric
- Dataflow ingests from uploaded files
- **Total time:** ~15 minutes (mostly manual)

**Automated (HTTP Download):**
- Pipeline triggers HTTP copy activity
- Direct download to lakehouse
- **Total time:** ~2 minutes (fully automated)

**Performance Gain:** 85% time reduction + zero manual effort

---

## 6. Compliance & Attribution

### Attribution Requirements

**EPI Attribution (CC BY-NC-SA 4.0):**
```
Data Source: Environmental Performance Index 2024
Yale Center for Environmental Law & Policy
https://epi.yale.edu/
Licensed under CC BY-NC-SA 4.0 International
```

**WGI Attribution (Recommended):**
```
Data Source: Worldwide Governance Indicators 2024
The World Bank Group
https://www.worldbank.org/en/publication/worldwide-governance-indicators
```

**Implementation:** Add attribution to:
- Power BI report footer
- Documentation (README.md)
- Data lineage metadata

---

## 7. Implementation Status

### Completed (2026-04-05)

✅ **Research Complete** - Data sources documented, feasibility confirmed
✅ **EPI Notebook Created** - `fabric/bronze_ingest_epi.Notebook/`
  - Downloads `epi{YYYY}results.csv` from Yale via HTTP
  - Parameterized by year (`p_epi_year`, default: 2024)
  - Schema validation (checks for `code`, `iso`, `country`, `EPI` columns)
  - Retry logic (3 attempts) with specific 404 handling
  - Writes to `bronze_epi{YYYY}results` Delta table (overwrite)
  - **task-056 (2026-08-04):** also downloads `epi{YYYY}weights.csv` → `bronze_epi{YYYY}weights`,
    preserving the `Type`/`Abbreviation`/`Variable`/`Weight`/`NextLevel`/`IssueCategory`/
    `PolicyObjective`/`EPI Percent` columns. `silver_to_gold.Notebook` builds
    `silver_epi{YYYY}variables` from this (mapping `weight` ← `EPI Percent`), which
    `gold_dim_indicator`'s primary path selects from — so `Weighted EPI Score` renders
    a 0-100 value instead of BLANK.
✅ **WGI Notebook Created** - `fabric/bronze_ingest_wgi.Notebook/`
  - Calls World Bank API v2 (JSON format) for all 6 WGI indicators
  - Fixed ingestion window 1996-2023 — `p_start_year`/`p_end_year` are **hardcoded**, not
    pipeline parameters. The notebook has no Fabric parameters cell and the orchestrator
    passes it none (task-072); widening the window requires editing the notebook.
  - Pagination support for large result sets
  - Retry logic with exponential backoff
  - **task-066 (2026-08-13):** transient/permanent classification before any retry (5xx and
    429 retried, `Retry-After` honoured, other 4xx raised immediately), budget widened to
    8 attempts / 120 s cap, and four completeness guards so an incomplete fetch can no
    longer silently overwrite `bronze_wgi`. See § *Failure Handling in `bronze_ingest_wgi`*.
  - **task-075 (2026-08-20):** the 4xx half of that classification corrected against a
    measured counter-example — 400 and 408 are transient, only 401/403/404 stay permanent —
    and retry ownership settled: the `bronze_wgi` activity's `policy.retry` went 2 → 0, so
    the notebook's budget is the only budget. See § *Retry ownership and the total attempt
    budget*, which is the canonical answer to how many attempts a failure gets.
  - Writes to `bronze_wgi` Delta table with columns matching downstream expectations
  - Enriches data with `Indicator Code`, `Year`, and `Value` columns beyond original schema
✅ **Documentation Updated** - This document updated with implementation details

### Remaining (Erik in Fabric UI)

✅ **Pipeline Wiring** - Done (task-035, 2026-07-26): `bronze_EPI` and `bronze_wgi` are
TridentNotebook activities in `orchestrator_pipeline_bronze_to_gold` pointing at
`bronze_ingest_epi` / `bronze_ingest_wgi`. No RefreshDataflow activities remain on the
pipeline (task-048 later retired the `bronze_procurement` RefreshDataflow too).
✅ **Test End-to-End** - Done (task-035): live pipeline run green end-to-end with both
notebooks succeeding.
✅ **Decommission Dataflows** - Done (2026-08-10). The `EPI_file2table.Dataflow` and
`WGI_file2table.Dataflow` workspace items were deleted once the notebook lineage had run
clean for two weeks. Their auto-created staging artifacts
(`StagingLakehouseForDataflows_*`, `StagingWarehouseForDataflows_*`, both empty) went with
them. Snapshot: `.claude/support/retired/epi-wgi-file2table-dataflows/manifest.json`.

### Future Enhancements

- **Historical Data Loading:** Download multiple EPI/WGI versions for trend analysis
- **Change Detection:** Only trigger downstream transformations if data changed
- **Metadata Tracking:** Log download timestamps, data versions, row counts
- **Automated Testing:** Validate data quality automatically after download

---

## 8. References

### EPI Resources
- **Main Site:** https://epi.yale.edu/
- **Downloads:** https://epi.yale.edu/downloads
- **Technical Appendix:** https://epi.yale.edu/downloads/2024epitechnicalappendix20241207.pdf
- **License:** https://creativecommons.org/licenses/by-nc-sa/4.0/

### WGI Resources
- **Main Site:** https://www.worldbank.org/en/publication/worldwide-governance-indicators
- **DataBank:** https://databank.worldbank.org/source/worldwide-governance-indicators
- **API Documentation:** https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-call-structures
- **Interactive Access:** https://www.worldbank.org/en/publication/worldwide-governance-indicators/interactive-data-access

### Contact Information
- **EPI Questions:** epi@yale.edu
- **WGI Questions:** wgi@worldbank.org

---

**Document Status:** Complete and ready for implementation
**Next Task:** Task 06 (Incremental Load Strategy Design)
