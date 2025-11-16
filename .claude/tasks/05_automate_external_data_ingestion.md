# Task: Automate External Data Ingestion

**Priority:** P2 (Medium)
**Status:** ✅ Research Phase Complete
**Completion Date:** 2025-11-03 (Research & Documentation)
**Actual Effort:** 2 hours (research phase)
**Owner:** Claude Code

## Problem Statement

Three external datasets are currently ingested via manual CSV file uploads:
1. **EPI (Environmental Performance Index)** - Annual release, file-based dataflow
2. **WGI (World Governance Indicators)** - Annual World Bank release
3. **EU CRM Supply Shares** - Already automated via HTTP copy job ✅

Per project_definition.md:
- Line 228: "Manual CSV file upload. (Task created to investigate automating ingestion)."
- Line 277: "Manual CSV file upload. (Task created to investigate automating ingestion)."
- Line 316: EU Supply Shares already automated via GitHub CSV (good example!)

Goal: Automate EPI and WGI ingestion to eliminate manual file upload steps.

## Current State

### EPI Dataset
- **Source:** Yale Center for Environmental Law & Policy
- **Ingestion:** `EPI_file2table.Dataflow` (file-based)
- **Update Frequency:** Annual (typically Q2-Q3)
- **Current Year:** 2024
- **Status:** ❌ Manual CSV upload

### WGI Dataset
- **Source:** World Bank (World Governance Indicators)
- **Ingestion:** `WGI_file2table.Dataflow` (file-based)
- **Update Frequency:** Annual (typically Q3-Q4)
- **Current Year:** 2020 (filtered in transformation)
- **Status:** ❌ Manual CSV upload

### EU CRM Supply Shares (Already Automated) ✅
- **Source:** GitHub repository CSV
- **Ingestion:** `bronzecopy_EUSupplyShares` (Copy Activity with HTTP source)
- **Status:** ✅ Automated

## Acceptance Criteria

### Must Have: Investigation Phase

1. **Research Data Sources:**
   - Find official EPI data download URLs (API or direct CSV links)
   - Find World Bank WGI data download URLs (API or direct CSV links)
   - Document authentication requirements (if any)
   - Verify data format consistency across years

2. **Document Findings:**
   - Create `/.claude/reference/external_data_sources.md`
   - Include URLs, API documentation, update schedules
   - Note any limitations or rate limits
   - Document fallback plan if automation not possible

### Must Have: Implementation (if feasible)

3. **Update Dataflows:**
   - Modify `EPI_file2table.Dataflow` to use HTTP source (like EU CRM example)
   - Modify `WGI_file2table.Dataflow` to use HTTP source or API
   - Test with current year data
   - Verify schema matches expectations

4. **Update Pipeline:**
   - Ensure `orchestrator_pipeline_bronze_to_gold` still works
   - Test end-to-end data refresh
   - Validate data quality after automated ingestion

5. **Documentation:**
   - Update `project_definition.md` to reflect automated sources
   - Document refresh process in `/.claude/context/data_sources.md`

### Nice to Have:
- Scheduled refresh (weekly/monthly check for new data)
- Version detection (only ingest if new year available)
- Email notification when new data is ingested

## Technical Approach

### Phase 1: Research (1 day)

**EPI Data Source Investigation:**
```
1. Visit epi.yale.edu
2. Find data download section
3. Identify direct CSV/Excel download links
4. Test download URL stability (do URLs change yearly?)
5. Check for API availability
```

**WGI Data Source Investigation:**
```
1. Visit databank.worldbank.org/source/worldwide-governance-indicators
2. Find bulk download options
3. Test World Bank API (api.worldbank.org)
4. Identify stable endpoint for WGI data
```

### Phase 2: Proof of Concept (1 day)

**Test HTTP Download:**
```python
# In notebook, test HTTP download
import requests
url = "https://example.com/epi_data.csv"
response = requests.get(url)
df = pd.read_csv(io.StringIO(response.text))
```

**Verify Schema:**
- Compare downloaded data to existing bronze tables
- Check column names, data types
- Identify any schema changes

### Phase 3: Implementation (1-2 days)

**Option A: Modify Dataflow (if Power Query supports HTTP)**
- Change source from File to Web
- Update Power Query M code in `mashup.pq`
- Test dataflow refresh

**Option B: Create Pipeline Copy Activity (like EU CRM)**
- Create new Copy Activity for EPI
- Create new Copy Activity for WGI
- Use HTTP source (like `bronzecopy_EUSupplyShares`)
- Replace existing dataflow activities in pipeline

**Option C: Notebook-Based Ingestion**
- Create new notebook: `bronze_ingestion_external.Notebook`
- Use Python requests library to download CSV
- Write to bronze tables directly
- Add to pipeline before silver transformation

## Data Source Details

### EPI Data
**Known URLs (to verify):**
- Main site: https://epi.yale.edu/
- Downloads: https://epi.yale.edu/downloads
- Possible CSV: https://epi.yale.edu/epi-results/2024/...

**Schema Notes:**
- Wide format (30+ indicator columns)
- Columns: code, iso, country, EPI, [indicators]
- No authentication typically required for public data

### WGI Data
**Known URLs (to verify):**
- World Bank API: https://api.worldbank.org/v2/
- WGI indicator codes: CC.EST, GE.EST, PV.EST, RL.EST, RQ.EST, VA.EST
- Bulk download: https://databank.worldbank.org/...

**Schema Notes:**
- Wide format with year columns (y_2000, y_2001, ...)
- Columns: Country Name, Country Code, Indicator Name, Indicator Code, year columns
- API requires no authentication for public indicators

## Dependencies
- Access to dataflow definitions in `/fabric`
- Pipeline edit permissions
- Network access from Fabric to external URLs
- No firewall restrictions blocking HTTP downloads

## Success Metrics
- ✅ EPI data source URL identified and documented
- ✅ WGI data source URL identified and documented
- ✅ Automated ingestion working for both datasets
- ✅ Pipeline runs end-to-end without manual file upload
- ✅ Documentation updated

## Related Files
- `/fabric/EPI_file2table.Dataflow/` - EPI dataflow to modify
- `/fabric/WGI_file2table.Dataflow/` - WGI dataflow to modify
- `/fabric/bronzecopy_EUSupplyShares.CopyJob/` - Example to follow
- `/project_definition.md` - Lines 191-278 (Data Sources section)

## Notes
- Start with investigation - automation may not be feasible if data requires manual download
- Consider data licensing and terms of use
- If automation fails, document manual process clearly
- This is lower priority than P1 tasks - defer if time-constrained
- Success = either automation OR clear documentation of why it's not possible

---

## Completion Summary (2025-11-03)

### Phase 1: Research Phase ✅ COMPLETE

**Investigation Results:**

✅ **EPI Data Sources Identified:**
- Direct CSV downloads available at https://epi.yale.edu/downloads/
- Files: epi2024results.csv, epi2024variables.csv, epi2024weights.csv, epi2024targets.csv
- License: CC BY-NC-SA 4.0 (non-commercial only)
- Versioned URLs allow for annual updates
- No API available, HTTP download is the automation method

✅ **WGI Data Sources Identified:**
- World Bank REST API: https://api.worldbank.org/v2/
- CSV export via API with indicator codes (CC.EST, GE.EST, PV.EST, RL.EST, RQ.EST, VA.EST)
- License: Open Data (commercial use permitted)
- Stable API endpoints with parameter-based filtering
- No authentication required for public indicators

✅ **Documentation Created:**
- Comprehensive document: `.claude/context/external_data_automation.md` (8 sections)
- Detailed implementation plans for both Option A (Fabric Copy Activity) and Option B (Python Notebook)
- URL patterns, API examples, error handling strategies
- License compliance notes

### Key Findings

**Automation Feasibility:** ✅ Both datasets can be fully automated

**Recommended Approach:**
1. **EPI:** HTTP Copy Activity (like EU CRM example) or Python notebook with requests
2. **WGI:** Python notebook preferred (API requires parameter construction)

**Implementation Checklist Created:**
- Bronze layer ingestion logic
- Pipeline integration steps
- Error handling and validation
- Documentation updates

### What's Next (Phase 2-3 - Implementation)

⏭️ **Implementation Phase** (requires Fabric workspace access)
- Modify or create dataflows/notebooks for HTTP/API ingestion
- Test automated downloads
- Update orchestrator pipeline
- Validate schema compatibility
- Update project_definition.md

**Status:** Research complete. Implementation deferred until Fabric workspace access is available.

### Files Created

```
.claude/context/external_data_automation.md (comprehensive research document)
```

### Portfolio Value

This research demonstrates:
✅ **Data Engineering:** Understanding external data source automation
✅ **API Research:** Investigated REST APIs and HTTP download options
✅ **License Compliance:** Documented usage restrictions (CC BY-NC-SA vs Open Data)
✅ **Implementation Planning:** Created actionable implementation guide
✅ **Documentation:** Comprehensive reference material for future implementation
