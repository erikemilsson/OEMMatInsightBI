# EPI 2024 source files (pinned copy)

`bronze_ingest_epi` downloads these two files over HTTPS from
`https://raw.githubusercontent.com/erikemilsson/OEMMatInsightBI/main/reference_data/epi/`.
They are Yale's original EPI 2024 release files, unmodified.

| File | Bytes | sha256 | Original URL (retired) |
|---|---|---|---|
| `epi2024results.csv` | 123,308 | `9d0b98d9fecf0ac37926224885045bad12e5d68b2597de1dc3bf49e68fb937ab` | `https://epi.yale.edu/downloads/epi2024results.csv` |
| `epi2024weights.csv` | 6,756 | `b4d3dee9d357070fe6f8897377698c2eea992cf087f0e7648a1285749371f332` | `https://epi.yale.edu/downloads/epi2024weights.csv` |

## Why they are here

Yale retired its 2024 CSV download paths when EPI 2026 was released (September 2026). The old
URLs now return HTTP 200 with an HTML page instead of the file, so every scheduled pipeline run
failed at `bronze_epi` from 2026-09-25 until these copies were pinned (task-082, 2026-10-16).
Background and the pre-parse guard: `docs/epi_wgi_ingestion.md`, "Source pinning and the
pre-parse guard".

## Provenance

Recovered from the Internet Archive's Wayback Machine on 2026-10-16, served as `text/csv`:

- `https://web.archive.org/web/20260901000000id_/https://epi.yale.edu/downloads/epi2024results.csv`
  (resolves to snapshot `20260424222356`)
- `https://web.archive.org/web/20260901000000id_/https://epi.yale.edu/downloads/epi2024weights.csv`
  (resolves to snapshot `20260814071704`)

`tests/test_epi_source_guard.py` checks both hashes, so an edited or re-saved copy fails the
test suite. Don't open and save these files in Excel or in an editor that rewrites line endings:
`epi2024weights.csv` uses CRLF line endings and `epi2024results.csv` uses LF.

## Keeping the source reachable

- The repo must stay public. raw.githubusercontent.com returns 404 for a private repo, and the
  notebook reports that as "No pinned EPI 2024 ... file".
- The files must be on `main`. If you move or rename them, update `EPI_SOURCE_BASE_URL` in
  `fabric/bronze_ingest_epi.Notebook/notebook-content.py` in the same commit.
- Only the 2024 vintage is pinned. Another vintage needs its CSVs added here, in the same
  schema, before `p_epi_year` changes.

## License and attribution

These files are Yale's data. They are not covered by this repository's MIT license. They are
licensed under Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International
(CC BY-NC-SA 4.0, https://creativecommons.org/licenses/by-nc-sa/4.0/), and are redistributed
here unmodified for non-commercial use.

> Environmental Performance Index 2024. Yale Center for Environmental Law & Policy,
> https://epi.yale.edu/
