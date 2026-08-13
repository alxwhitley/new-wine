# New Wine magazine — raw PDF inventory

**Scope:** read-only inventory of `sources/magazine/01_to_extract/`.
No ingestion, no pipeline changes, no database writes.

**Generated:** 2026-08-08

---

## Summary

| Metric | Count |
|---|---:|
| Total PDF files in `01_to_extract` | **167** |
| Already-ingested residual still in folder | **1** (`Issue 03-1973`, byte-identical to `05_archived/`) |
| Byte-identical duplicate groups | **3** groups (3 redundant files) |
| Files involved in same-issue duplicates | **6** |
| Flagged broken / unreadable / empty | **0** (all 167 open as valid PDFs) |
| Flagged thin / size-review (not corrupt) | **2** |
| Odd / inconsistent naming (vs standard `Issue_MM-YYYY`) | **20** |
| Unresolved naming (date/number not a clean month-year) | **2** |
| Unique content files after dropping exact dupes + ingested residual | **163** |

### Size / page stats (batch)

- Total size: **1.67 GB**
- Median size: **9.0 MB** · mean ≈ **10.0 MB** · range **1.0–55.9 MB**
- Median page count: **36** · range **8–99**
- Scan provenance: nearly all produced via I.R.I.S. / 3-Heights PDF (2006–2015 digitization), not original born-digital issues.

### Clarification vs “167 − 9 = 158”

The folder currently holds **167** PDFs. The **9 fully ingested issues** live under `04_ingested/` (markdown) with source PDFs in `05_archived/`:

| Ingested issue | Still present in `01_to_extract`? |
|---|---|
| `NewWineMagazine_Issue_01-1970` | no (PDF in `05_archived/` only) |
| `NewWineMagazine_Issue_01-1971` | no (PDF in `05_archived/` only) |
| `NewWineMagazine_Issue_01-1972` | no (PDF in `05_archived/` only) |
| `NewWineMagazine_Issue_01-1974` | no (PDF in `05_archived/` only) |
| `NewWineMagazine_Issue_01-1975` | no (PDF in `05_archived/` only) |
| `NewWineMagazine_Issue_01-1977` | no (PDF in `05_archived/` only) |
| `NewWineMagazine_Issue_01-1978` | no (PDF in `05_archived/` only) |
| `NewWineMagazine_Issue_01-1979` | no (PDF in `05_archived/` only) |
| `NewWineMagazine_Issue_03-1973` | **yes** — residual PDF, byte-identical to archived |

So this inventory covers **all 167 files still sitting in the raw folder**. Only **1** of them is an already-ingested residual (`03-1973`). The other 8 ingested issues are not among the 167.

Also already past the raw stage (not in this list, not re-inventoried here):

- **`03_approved` (9):** 01-1973, 01-1976, 01-1980, 01-1981, 01-1982, 01-1984, 06-1974, 06-1976, 06-1979
- **`02_extracted` (5):** 02-1976 … 02-1980
- **`06_failed` (5):** 02-1971 … 02-1975

---

## Duplicates

### Exact byte-identical pairs (MD5 match)

Safe to drop the `(1)` copy in each pair before any future ingest:

| Issue | Keep | Drop (identical) | Size | Pages |
|---|---|---|---:|---:|
| Issue 06-1985 | `NewWineMagazine_Issue_06-1985.pdf` | `NewWineMagazine_Issue_06-1985 (1).pdf` | 9.14 MB | 42 |
| Issue 10-1969 | `NewWineMagazine_Issue_10-1969.pdf` | `NewWineMagazine_Issue_10-1969 (1).pdf` | 6.18 MB | 24 |
| Issue 10-1970 | `NewWineMagazine_Issue_10-1970.pdf` | `NewWineMagazine_Issue_10-1970 (1).pdf` | 8.03 MB | 32 |

### Same-issue key, not byte-identical

None found beyond the three pairs above. Specials that *sound* related but are different files:

| File A | File B | Notes |
|---|---|---|
| `Issue_Summer1979.pdf` (8 pp, 1.9 MB) | `Issue_07_08-1979.pdf` (36 pp, 10.7 MB) | Different content; Summer is a thin special/newsletter-like scan, not the combined Jul/Aug issue |
| `Issue_08-1980_News.pdf` (23 pp, 6.0 MB) | `Issue_07_08-1980.pdf` (36 pp, 10.7 MB) | Different content; `_News` is a separate “News” edition |
| `Newsletter_08-1981.pdf` (8 pp, 1.0 MB) | *(no regular `Issue_08-1981`)* | First-page text: *“NEW WINE MAGAZINE Vol. 13, No.8 SUMMER 1981 NEWSLETTER”* |

### Already-ingested residual

| Filename | Issue | Status |
|---|---|---|
| `NewWineMagazine_Issue_03-1973.pdf` | 03-1973 | **Leave alone** — already in `04_ingested/`; PDF matches `05_archived/` byte-for-byte |

---

## Flagged: thin / size review (not corrupted)

Every file in the batch:
- Starts with a valid `%PDF` header
- Has a `%%EOF` trailer
- Opens with `pypdf` without error
- Is **not** empty (minimum ~1.0 MB)

Two files are **much thinner** than the batch median (~36 pages / ~9 MB). Treat as review items, not corruption:

| Filename | Apparent ID | Size | Pages | Why flagged |
|---|---|---:|---:|---|
| `NewWineMagazine_Issue_Summer1979.pdf` | Summer 1979 | 1.9 MB | 8 | Far below median; OCR text badly garbled; may be a partial or special insert, not a full issue |
| `NewWineMagazine_Newsletter_08-1981.pdf` | Newsletter 08-1981 | 1.0 MB | 8 | Expected for a newsletter format; distinct product type (`Newsletter_` prefix) |

Large outliers (high page count — look like year-end / bound scans, not broken):

| Filename | Size | Pages |
|---|---:|---:|
| `NewWineMagazine_Issue_12-1972.pdf` | 55.9 MB | 92 |
| `NewWineMagazine_Issue_12-1975.pdf` | 35.4 MB | 99 |
| `NewWineMagazine_Issue_12-1974.pdf` | 35.1 MB | 98 |
| `NewWineMagazine_Issue_12-1973.pdf` | 28.1 MB | 83 |
| `NewWineMagazine_Issue_10-1977.pdf` | 17.3 MB | 64 |
| `NewWineMagazine_Issue_07_1986.pdf` | 22.1 MB | 66 |
| `NewWineMagazine_Issue_10_1986.pdf` | 22.3 MB | 61 |

---

## Odd / inconsistent naming

Canonical pattern for the batch (**150 / 167** files):

```
NewWineMagazine_Issue_MM-YYYY.pdf
```

Deviations:

### 1. Underscore before year (8 files) — 1986 cluster

`Issue_MM_YYYY` instead of `Issue_MM-YYYY`. Issue number and year still clear.

| Filename | Interpreted as |
|---|---|
| `NewWineMagazine_Issue_04_1986.pdf` | Issue 04-1986 |
| `NewWineMagazine_Issue_05_1986.pdf` | Issue 05-1986 |
| `NewWineMagazine_Issue_06_1986.pdf` | Issue 06-1986 |
| `NewWineMagazine_Issue_07_1986.pdf` | Issue 07-1986 |
| `NewWineMagazine_Issue_09_1986.pdf` | Issue 09-1986 |
| `NewWineMagazine_Issue_10_1986.pdf` | Issue 10-1986 |
| `NewWineMagazine_Issue_11_1986.pdf` | Issue 11-1986 |
| `NewWineMagazine_Issue_12_1986.pdf` | Issue 12-1986 |

### 2. Combined / double-month issues (6 files)

| Filename | Interpreted as | Pages |
|---|---|---:|
| `NewWineMagazine_Issue_05_06-1971.pdf` | Issues 05–06 / 1971 (combined) | 32 |
| `NewWineMagazine_Issue_07_08-1973.pdf` | Issues 07–08 / 1973 (combined) | 32 |
| `NewWineMagazine_Issue_07_08-1975.pdf` | Issues 07–08 / 1975 (combined) | 36 |
| `NewWineMagazine_Issue_07_08-1976.pdf` | Issues 07–08 / 1976 (combined) | 36 |
| `NewWineMagazine_Issue_07_08-1979.pdf` | Issues 07–08 / 1979 (combined) | 36 |
| `NewWineMagazine_Issue_07_08-1980.pdf` | Issues 07–08 / 1980 (combined) | 36 |

### 3. Finder copy suffix `(1)` (3 files) — also exact dupes

| Filename | Pair |
|---|---|
| `NewWineMagazine_Issue_10-1969 (1).pdf` | Drop; identical to non-`(1)` twin |
| `NewWineMagazine_Issue_10-1970 (1).pdf` | Drop; identical to non-`(1)` twin |
| `NewWineMagazine_Issue_06-1985 (1).pdf` | Drop; identical to non-`(1)` twin |

### 4. `_News` suffix (1 file)

| Filename | Notes |
|---|---|
| `NewWineMagazine_Issue_08-1980_News.pdf` | Separate from combined `07_08-1980`; 23 pages |

### 5. Seasonal / newsletter (2 files) — **unresolved as pure MM-YYYY**

| Filename | Apparent ID | Notes |
|---|---|---|
| `NewWineMagazine_Issue_Summer1979.pdf` | Summer 1979 | No month number; 8 pages; see thin-scan flag |
| `NewWineMagazine_Newsletter_08-1981.pdf` | Newsletter Vol.13 No.8 / Summer 1981 | Different basename (`Newsletter_` not `Issue_`); confirmed from page-1 text |

---

## Coverage gaps (from filenames in this folder only)

Months with **no** PDF in `01_to_extract` (does not mean the magazine never published — many sit in other pipeline stages or were never acquired):

| Year | Present (month nums) | Missing in this folder | Notes |
|---|---|---|---|
| 1969 | 10, 11, 12 | 01, 02, 03, 04, 05, 06, 07, 08, 09 | several 01-/02-/06- issues already in later pipeline stages |
| 1970 | 03, 05, 06, 07, 08, 09, 10, 12 | 01, 02, 04, 11 | several 01-/02-/06- issues already in later pipeline stages |
| 1971 | 03, 04, 05, 06, 07, 08, 09, 10, 11 | 01, 02, 12 | several 01-/02-/06- issues already in later pipeline stages |
| 1972 | 03, 04, 05, 06, 07, 08, 09, 10, 11, 12 | 01, 02 | several 01-/02-/06- issues already in later pipeline stages |
| 1973 | 03, 04, 05, 06, 07, 08, 09, 10, 11, 12 | 01, 02 | several 01-/02-/06- issues already in later pipeline stages |
| 1974 | 03, 04, 05, 07, 09, 10, 11, 12 | 01, 02, 06, 08 | several 01-/02-/06- issues already in later pipeline stages |
| 1975 | 03, 04, 05, 06, 07, 08, 09, 10, 11, 12 | 01, 02 | several 01-/02-/06- issues already in later pipeline stages |
| 1976 | 03, 04, 05, 07, 08, 09, 10, 11, 12 | 01, 02, 06 | several 01-/02-/06- issues already in later pipeline stages |
| 1977 | 03, 04, 05, 06, 07, 09, 10, 11, 12 | 01, 02, 08 | several 01-/02-/06- issues already in later pipeline stages |
| 1978 | 03, 04, 05, 06, 07, 09, 10, 11, 12 | 01, 02, 08 | several 01-/02-/06- issues already in later pipeline stages |
| 1979 | 03, 04, 05, 07, 08, 09, 10, 11, 12 | 01, 02, 06 | specials: Summer 1979; several 01-/02-/06- issues already in later pipeline stages |
| 1980 | 03, 04, 05, 06, 07, 08, 09, 10, 11, 12 | 01, 02 | specials: Issue 08-1980 (News); several 01-/02-/06- issues already in later pipeline stages |
| 1981 | 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12 | 01 | specials: Newsletter 08-1981; several 01-/02-/06- issues already in later pipeline stages |
| 1982 | 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12 | 01 | several 01-/02-/06- issues already in later pipeline stages |
| 1983 | 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12 | 01 | several 01-/02-/06- issues already in later pipeline stages |
| 1984 | 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12 | 01 | several 01-/02-/06- issues already in later pipeline stages |
| 1985 | 02, 03, 04, 05, 06, 08, 09, 10, 11, 12 | 01, 07 |  |
| 1986 | 02, 03, 04, 05, 06, 07, 09, 10, 11, 12 | 01, 08 |  |

Notable holes **inside this raw set** (not explained by the 9 ingested or the approved/extracted/failed lists):

- **1969:** only Oct–Dec present (magazine launch era — earlier months may not exist)
- **1970:** missing 02, 04, 11 (01 ingested elsewhere)
- **1974:** missing 08 (06 is in `03_approved`)
- **1977–1978:** missing 08
- **1981:** no regular `Issue_08` (only the Newsletter); 01 in approved
- **1985:** missing 07
- **1986:** missing 01, 08

---

## Full sorted list

Sorted by year → month → variant. Status flags:

- `OK` — standard name, valid PDF, unique issue key
- `DUP` — exact byte-identical twin of another file in this list
- `INGESTED` — already fully ingested; leave alone
- `NAME` — non-standard naming (still date-readable unless also `UNRESOLVED`)
- `UNRESOLVED` — cannot map to a clean single MM-YYYY issue id from the name alone
- `THIN` — valid PDF but far below batch median size/pages
- `LARGE` — valid PDF, unusually high page count (year-end / bound-looking)

| # | Sort date | Filename | Issue ID (from name) | Size (MB) | Pages | Status | Notes |
|---:|---|---|---|---:|---:|---|---|
| 1 | 1969-10 | `NewWineMagazine_Issue_10-1969.pdf` | 10-1969 | 6.18 | 24 | DUP | has exact (1) twin |
| 2 | 1969-10 | `NewWineMagazine_Issue_10-1969 (1).pdf` | 10-1969 copy(1) | 6.18 | 24 | DUP, NAME | exact copy of non-(1) twin — drop |
| 3 | 1969-11 | `NewWineMagazine_Issue_11-1969.pdf` | 11-1969 | 6.26 | 24 | OK |  |
| 4 | 1969-12 | `NewWineMagazine_Issue_12-1969.pdf` | 12-1969 | 7.27 | 28 | OK |  |
| 5 | 1970-03 | `NewWineMagazine_Issue_03-1970.pdf` | 03-1970 | 7.48 | 28 | OK |  |
| 6 | 1970-05 | `NewWineMagazine_Issue_05-1970.pdf` | 05-1970 | 7.62 | 32 | OK |  |
| 7 | 1970-06 | `NewWineMagazine_Issue_06-1970.pdf` | 06-1970 | 8.27 | 32 | OK |  |
| 8 | 1970-07 | `NewWineMagazine_Issue_07-1970.pdf` | 07-1970 | 7.93 | 32 | OK |  |
| 9 | 1970-08 | `NewWineMagazine_Issue_08-1970.pdf` | 08-1970 | 7.52 | 32 | OK |  |
| 10 | 1970-09 | `NewWineMagazine_Issue_09-1970.pdf` | 09-1970 | 7.81 | 32 | OK |  |
| 11 | 1970-10 | `NewWineMagazine_Issue_10-1970.pdf` | 10-1970 | 8.03 | 32 | DUP | has exact (1) twin |
| 12 | 1970-10 | `NewWineMagazine_Issue_10-1970 (1).pdf` | 10-1970 copy(1) | 8.03 | 32 | DUP, NAME | exact copy of non-(1) twin — drop |
| 13 | 1970-12 | `NewWineMagazine_Issue_12-1970.pdf` | 12-1970 | 8.29 | 32 | OK |  |
| 14 | 1971-03 | `NewWineMagazine_Issue_03-1971.pdf` | 03-1971 | 8.22 | 32 | OK |  |
| 15 | 1971-04 | `NewWineMagazine_Issue_04-1971.pdf` | 04-1971 | 8.24 | 32 | OK |  |
| 16 | 1971-05/06 | `NewWineMagazine_Issue_05_06-1971.pdf` | 05–06-1971 | 8.47 | 32 | NAME | combined double-month issue |
| 17 | 1971-07 | `NewWineMagazine_Issue_07-1971.pdf` | 07-1971 | 9.21 | 32 | OK |  |
| 18 | 1971-08 | `NewWineMagazine_Issue_08-1971.pdf` | 08-1971 | 8.8 | 32 | OK |  |
| 19 | 1971-09 | `NewWineMagazine_Issue_09-1971.pdf` | 09-1971 | 8.37 | 32 | OK |  |
| 20 | 1971-10 | `NewWineMagazine_Issue_10-1971.pdf` | 10-1971 | 8.77 | 32 | OK |  |
| 21 | 1971-11 | `NewWineMagazine_Issue_11-1971.pdf` | 11-1971 | 9.15 | 32 | OK |  |
| 22 | 1972-03 | `NewWineMagazine_Issue_03-1972.pdf` | 03-1972 | 9.03 | 32 | OK |  |
| 23 | 1972-04 | `NewWineMagazine_Issue_04-1972.pdf` | 04-1972 | 9.37 | 32 | OK |  |
| 24 | 1972-05 | `NewWineMagazine_Issue_05-1972.pdf` | 05-1972 | 9.16 | 32 | OK |  |
| 25 | 1972-06 | `NewWineMagazine_Issue_06-1972.pdf` | 06-1972 | 9.69 | 32 | OK |  |
| 26 | 1972-07 | `NewWineMagazine_Issue_07-1972.pdf` | 07-1972 | 9.12 | 32 | OK |  |
| 27 | 1972-08 | `NewWineMagazine_Issue_08-1972.pdf` | 08-1972 | 9.08 | 32 | OK |  |
| 28 | 1972-09 | `NewWineMagazine_Issue_09-1972.pdf` | 09-1972 | 8.41 | 32 | OK |  |
| 29 | 1972-10 | `NewWineMagazine_Issue_10-1972.pdf` | 10-1972 | 9.04 | 32 | OK |  |
| 30 | 1972-11 | `NewWineMagazine_Issue_11-1972.pdf` | 11-1972 | 8.5 | 32 | OK |  |
| 31 | 1972-12 | `NewWineMagazine_Issue_12-1972.pdf` | 12-1972 | 55.92 | 92 | LARGE |  |
| 32 | 1973-03 | `NewWineMagazine_Issue_03-1973.pdf` | 03-1973 | 8.5 | 32 | INGESTED | byte-identical to 05_archived; leave alone |
| 33 | 1973-04 | `NewWineMagazine_Issue_04-1973.pdf` | 04-1973 | 9.06 | 32 | OK |  |
| 34 | 1973-05 | `NewWineMagazine_Issue_05-1973.pdf` | 05-1973 | 8.58 | 32 | OK |  |
| 35 | 1973-06 | `NewWineMagazine_Issue_06-1973.pdf` | 06-1973 | 8.44 | 32 | OK |  |
| 36 | 1973-07/08 | `NewWineMagazine_Issue_07_08-1973.pdf` | 07–08-1973 | 8.89 | 32 | NAME | combined double-month issue |
| 37 | 1973-09 | `NewWineMagazine_Issue_09-1973.pdf` | 09-1973 | 8.82 | 32 | OK |  |
| 38 | 1973-10 | `NewWineMagazine_Issue_10-1973.pdf` | 10-1973 | 9.47 | 32 | OK |  |
| 39 | 1973-11 | `NewWineMagazine_Issue_11-1973.pdf` | 11-1973 | 10.56 | 36 | OK |  |
| 40 | 1973-12 | `NewWineMagazine_Issue_12-1973.pdf` | 12-1973 | 28.15 | 83 | LARGE |  |
| 41 | 1974-03 | `NewWineMagazine_Issue_03-1974.pdf` | 03-1974 | 9.51 | 32 | OK |  |
| 42 | 1974-04 | `NewWineMagazine_Issue_04-1974.pdf` | 04-1974 | 9.21 | 32 | OK |  |
| 43 | 1974-05 | `NewWineMagazine_Issue_05-1974.pdf` | 05-1974 | 9.81 | 32 | OK |  |
| 44 | 1974-07 | `NewWineMagazine_Issue_07-1974.pdf` | 07-1974 | 10.16 | 36 | OK |  |
| 45 | 1974-09 | `NewWineMagazine_Issue_09-1974.pdf` | 09-1974 | 8.77 | 32 | OK |  |
| 46 | 1974-10 | `NewWineMagazine_Issue_10-1974.pdf` | 10-1974 | 9.14 | 32 | OK |  |
| 47 | 1974-11 | `NewWineMagazine_Issue_11-1974.pdf` | 11-1974 | 10.29 | 36 | OK |  |
| 48 | 1974-12 | `NewWineMagazine_Issue_12-1974.pdf` | 12-1974 | 35.14 | 98 | LARGE |  |
| 49 | 1975-03 | `NewWineMagazine_Issue_03-1975.pdf` | 03-1975 | 9.42 | 32 | OK |  |
| 50 | 1975-04 | `NewWineMagazine_Issue_04-1975.pdf` | 04-1975 | 9.21 | 32 | OK |  |
| 51 | 1975-05 | `NewWineMagazine_Issue_05-1975.pdf` | 05-1975 | 9.58 | 32 | OK |  |
| 52 | 1975-06 | `NewWineMagazine_Issue_06-1975.pdf` | 06-1975 | 9.38 | 32 | OK |  |
| 53 | 1975-07/08 | `NewWineMagazine_Issue_07_08-1975.pdf` | 07–08-1975 | 10.29 | 36 | NAME | combined double-month issue |
| 54 | 1975-09 | `NewWineMagazine_Issue_09-1975.pdf` | 09-1975 | 10.44 | 32 | OK |  |
| 55 | 1975-10 | `NewWineMagazine_Issue_10-1975.pdf` | 10-1975 | 9.89 | 32 | OK |  |
| 56 | 1975-11 | `NewWineMagazine_Issue_11-1975.pdf` | 11-1975 | 10.66 | 36 | OK |  |
| 57 | 1975-12 | `NewWineMagazine_Issue_12-1975.pdf` | 12-1975 | 35.37 | 99 | LARGE |  |
| 58 | 1976-03 | `NewWineMagazine_Issue_03-1976.pdf` | 03-1976 | 12.17 | 40 | OK |  |
| 59 | 1976-04 | `NewWineMagazine_Issue_04-1976.pdf` | 04-1976 | 9.6 | 32 | OK |  |
| 60 | 1976-05 | `NewWineMagazine_Issue_05-1976.pdf` | 05-1976 | 9.75 | 32 | OK |  |
| 61 | 1976-07/08 | `NewWineMagazine_Issue_07_08-1976.pdf` | 07–08-1976 | 10.82 | 36 | NAME | combined double-month issue |
| 62 | 1976-09 | `NewWineMagazine_Issue_09-1976.pdf` | 09-1976 | 9.4 | 32 | OK |  |
| 63 | 1976-10 | `NewWineMagazine_Issue_10-1976.pdf` | 10-1976 | 9.36 | 32 | OK |  |
| 64 | 1976-11 | `NewWineMagazine_Issue_11-1976.pdf` | 11-1976 | 9.86 | 32 | OK |  |
| 65 | 1976-12 | `NewWineMagazine_Issue_12-1976.pdf` | 12-1976 | 8.93 | 32 | OK |  |
| 66 | 1977-03 | `NewWineMagazine_Issue_03-1977.pdf` | 03-1977 | 13.59 | 48 | OK |  |
| 67 | 1977-04 | `NewWineMagazine_Issue_04-1977.pdf` | 04-1977 | 9.41 | 32 | OK |  |
| 68 | 1977-05 | `NewWineMagazine_Issue_05-1977.pdf` | 05-1977 | 8.77 | 32 | OK |  |
| 69 | 1977-06 | `NewWineMagazine_Issue_06-1977.pdf` | 06-1977 | 8.6 | 32 | OK |  |
| 70 | 1977-07 | `NewWineMagazine_Issue_07-1977.pdf` | 07-1977 | 11.5 | 48 | OK |  |
| 71 | 1977-09 | `NewWineMagazine_Issue_09-1977.pdf` | 09-1977 | 8.66 | 32 | OK |  |
| 72 | 1977-10 | `NewWineMagazine_Issue_10-1977.pdf` | 10-1977 | 17.28 | 64 | LARGE |  |
| 73 | 1977-11 | `NewWineMagazine_Issue_11-1977.pdf` | 11-1977 | 9.66 | 36 | OK |  |
| 74 | 1977-12 | `NewWineMagazine_Issue_12-1977.pdf` | 12-1977 | 8.55 | 32 | OK |  |
| 75 | 1978-03 | `NewWineMagazine_Issue_03-1978.pdf` | 03-1978 | 9.23 | 36 | OK |  |
| 76 | 1978-04 | `NewWineMagazine_Issue_04-1978.pdf` | 04-1978 | 8.45 | 32 | OK |  |
| 77 | 1978-05 | `NewWineMagazine_Issue_05-1978.pdf` | 05-1978 | 8.79 | 32 | OK |  |
| 78 | 1978-06 | `NewWineMagazine_Issue_06-1978.pdf` | 06-1978 | 9.02 | 32 | OK |  |
| 79 | 1978-07 | `NewWineMagazine_Issue_07-1978.pdf` | 07-1978 | 9.11 | 32 | OK |  |
| 80 | 1978-09 | `NewWineMagazine_Issue_09-1978.pdf` | 09-1978 | 8.71 | 32 | OK |  |
| 81 | 1978-10 | `NewWineMagazine_Issue_10-1978.pdf` | 10-1978 | 9.7 | 32 | OK |  |
| 82 | 1978-11 | `NewWineMagazine_Issue_11-1978.pdf` | 11-1978 | 9.75 | 32 | OK |  |
| 83 | 1978-12 | `NewWineMagazine_Issue_12-1978.pdf` | 12-1978 | 9.37 | 32 | OK |  |
| 84 | 1979-03 | `NewWineMagazine_Issue_03-1979.pdf` | 03-1979 | 9.47 | 32 | OK |  |
| 85 | 1979-04 | `NewWineMagazine_Issue_04-1979.pdf` | 04-1979 | 9.09 | 32 | OK |  |
| 86 | 1979-05 | `NewWineMagazine_Issue_05-1979.pdf` | 05-1979 | 10.95 | 36 | OK |  |
| 87 | 1979-Summer | `NewWineMagazine_Issue_Summer1979.pdf` | Summer 1979 | 1.9 | 8 | NAME, UNRESOLVED, THIN | seasonal label, no month number |
| 88 | 1979-07/08 | `NewWineMagazine_Issue_07_08-1979.pdf` | 07–08-1979 | 10.7 | 36 | NAME | combined double-month issue |
| 89 | 1979-09 | `NewWineMagazine_Issue_09-1979.pdf` | 09-1979 | 10.17 | 36 | OK |  |
| 90 | 1979-10 | `NewWineMagazine_Issue_10-1979.pdf` | 10-1979 | 9.97 | 36 | OK |  |
| 91 | 1979-11 | `NewWineMagazine_Issue_11-1979.pdf` | 11-1979 | 10.24 | 36 | OK |  |
| 92 | 1979-12 | `NewWineMagazine_Issue_12-1979.pdf` | 12-1979 | 10.3 | 36 | OK |  |
| 93 | 1980-03 | `NewWineMagazine_Issue_03-1980.pdf` | 03-1980 | 11.07 | 36 | OK |  |
| 94 | 1980-04 | `NewWineMagazine_Issue_04-1980.pdf` | 04-1980 | 10.65 | 36 | OK |  |
| 95 | 1980-05 | `NewWineMagazine_Issue_05-1980.pdf` | 05-1980 | 11.06 | 36 | OK |  |
| 96 | 1980-06 | `NewWineMagazine_Issue_06-1980.pdf` | 06-1980 | 10.98 | 36 | OK |  |
| 97 | 1980-07/08 | `NewWineMagazine_Issue_07_08-1980.pdf` | 07–08-1980 | 10.73 | 36 | NAME | combined double-month issue |
| 98 | 1980-08 | `NewWineMagazine_Issue_08-1980_News.pdf` | 08-1980 (News) | 6.0 | 23 | NAME | News edition suffix |
| 99 | 1980-09 | `NewWineMagazine_Issue_09-1980.pdf` | 09-1980 | 10.85 | 36 | OK |  |
| 100 | 1980-10 | `NewWineMagazine_Issue_10-1980.pdf` | 10-1980 | 10.96 | 36 | OK |  |
| 101 | 1980-11 | `NewWineMagazine_Issue_11-1980.pdf` | 11-1980 | 10.94 | 36 | OK |  |
| 102 | 1980-12 | `NewWineMagazine_Issue_12-1980.pdf` | 12-1980 | 10.91 | 36 | OK |  |
| 103 | 1981-02 | `NewWineMagazine_Issue_02-1981.pdf` | 02-1981 | 7.93 | 36 | OK |  |
| 104 | 1981-03 | `NewWineMagazine_Issue_03-1981.pdf` | 03-1981 | 7.17 | 36 | OK |  |
| 105 | 1981-04 | `NewWineMagazine_Issue_04-1981.pdf` | 04-1981 | 6.9 | 36 | OK |  |
| 106 | 1981-05 | `NewWineMagazine_Issue_05-1981.pdf` | 05-1981 | 7.09 | 36 | OK |  |
| 107 | 1981-06 | `NewWineMagazine_Issue_06-1981.pdf` | 06-1981 | 6.95 | 36 | OK |  |
| 108 | 1981-07 | `NewWineMagazine_Issue_07-1981.pdf` | 07-1981 | 6.81 | 36 | OK |  |
| 109 | 1981-08 | `NewWineMagazine_Newsletter_08-1981.pdf` | Newsletter 08-1981 | 1.01 | 8 | NAME, UNRESOLVED, THIN | Newsletter_ prefix; page1 confirms Vol.13 No.8 Summer 1981 |
| 110 | 1981-09 | `NewWineMagazine_Issue_09-1981.pdf` | 09-1981 | 7.24 | 36 | OK |  |
| 111 | 1981-10 | `NewWineMagazine_Issue_10-1981.pdf` | 10-1981 | 7.13 | 36 | OK |  |
| 112 | 1981-11 | `NewWineMagazine_Issue_11-1981.pdf` | 11-1981 | 6.51 | 36 | OK |  |
| 113 | 1981-12 | `NewWineMagazine_Issue_12-1981.pdf` | 12-1981 | 5.58 | 36 | OK |  |
| 114 | 1982-02 | `NewWineMagazine_Issue_02-1982.pdf` | 02-1982 | 7.37 | 36 | OK |  |
| 115 | 1982-03 | `NewWineMagazine_Issue_03-1982.pdf` | 03-1982 | 7.51 | 36 | OK |  |
| 116 | 1982-04 | `NewWineMagazine_Issue_04-1982.pdf` | 04-1982 | 6.87 | 36 | OK |  |
| 117 | 1982-05 | `NewWineMagazine_Issue_05-1982.pdf` | 05-1982 | 6.93 | 36 | OK |  |
| 118 | 1982-06 | `NewWineMagazine_Issue_06-1982.pdf` | 06-1982 | 6.77 | 36 | OK |  |
| 119 | 1982-07 | `NewWineMagazine_Issue_07-1982.pdf` | 07-1982 | 7.87 | 36 | OK |  |
| 120 | 1982-08 | `NewWineMagazine_Issue_08-1982.pdf` | 08-1982 | 7.86 | 36 | OK |  |
| 121 | 1982-09 | `NewWineMagazine_Issue_09-1982.pdf` | 09-1982 | 7.47 | 36 | OK |  |
| 122 | 1982-10 | `NewWineMagazine_Issue_10-1982.pdf` | 10-1982 | 6.59 | 36 | OK |  |
| 123 | 1982-11 | `NewWineMagazine_Issue_11-1982.pdf` | 11-1982 | 7.31 | 36 | OK |  |
| 124 | 1982-12 | `NewWineMagazine_Issue_12-1982.pdf` | 12-1982 | 6.57 | 36 | OK |  |
| 125 | 1983-02 | `NewWineMagazine_Issue_02-1983.pdf` | 02-1983 | 7.18 | 36 | OK |  |
| 126 | 1983-03 | `NewWineMagazine_Issue_03-1983.pdf` | 03-1983 | 7.7 | 36 | OK |  |
| 127 | 1983-04 | `NewWineMagazine_Issue_04-1983.pdf` | 04-1983 | 9.05 | 36 | OK |  |
| 128 | 1983-05 | `NewWineMagazine_Issue_05-1983.pdf` | 05-1983 | 9.16 | 36 | OK |  |
| 129 | 1983-06 | `NewWineMagazine_Issue_06-1983.pdf` | 06-1983 | 9.97 | 36 | OK |  |
| 130 | 1983-07 | `NewWineMagazine_Issue_07-1983.pdf` | 07-1983 | 9.18 | 36 | OK |  |
| 131 | 1983-08 | `NewWineMagazine_Issue_08-1983.pdf` | 08-1983 | 7.44 | 36 | OK |  |
| 132 | 1983-09 | `NewWineMagazine_Issue_09-1983.pdf` | 09-1983 | 8.4 | 36 | OK |  |
| 133 | 1983-10 | `NewWineMagazine_Issue_10-1983.pdf` | 10-1983 | 9.08 | 36 | OK |  |
| 134 | 1983-11 | `NewWineMagazine_Issue_11-1983.pdf` | 11-1983 | 8.76 | 36 | OK |  |
| 135 | 1983-12 | `NewWineMagazine_Issue_12-1983.pdf` | 12-1983 | 9.25 | 36 | OK |  |
| 136 | 1984-02 | `NewWineMagazine_Issue_02-1984.pdf` | 02-1984 | 8.74 | 36 | OK |  |
| 137 | 1984-03 | `NewWineMagazine_Issue_03-1984.pdf` | 03-1984 | 8.97 | 36 | OK |  |
| 138 | 1984-04 | `NewWineMagazine_Issue_04-1984.pdf` | 04-1984 | 8.59 | 36 | OK |  |
| 139 | 1984-05 | `NewWineMagazine_Issue_05-1984.pdf` | 05-1984 | 8.92 | 36 | OK |  |
| 140 | 1984-06 | `NewWineMagazine_Issue_06-1984.pdf` | 06-1984 | 9.91 | 44 | OK |  |
| 141 | 1984-07 | `NewWineMagazine_Issue_07-1984.pdf` | 07-1984 | 8.33 | 36 | OK |  |
| 142 | 1984-08 | `NewWineMagazine_Issue_08-1984.pdf` | 08-1984 | 8.43 | 36 | OK |  |
| 143 | 1984-09 | `NewWineMagazine_Issue_09-1984.pdf` | 09-1984 | 8.75 | 36 | OK |  |
| 144 | 1984-10 | `NewWineMagazine_Issue_10-1984.pdf` | 10-1984 | 8.94 | 36 | OK |  |
| 145 | 1984-11 | `NewWineMagazine_Issue_11-1984.pdf` | 11-1984 | 9.44 | 36 | OK |  |
| 146 | 1984-12 | `NewWineMagazine_Issue_12-1984.pdf` | 12-1984 | 9.01 | 36 | OK |  |
| 147 | 1985-02 | `NewWineMagazine_Issue_02-1985.pdf` | 02-1985 | 7.83 | 36 | OK |  |
| 148 | 1985-03 | `NewWineMagazine_Issue_03-1985.pdf` | 03-1985 | 8.63 | 40 | OK |  |
| 149 | 1985-04 | `NewWineMagazine_Issue_04-1985.pdf` | 04-1985 | 7.46 | 40 | OK |  |
| 150 | 1985-05 | `NewWineMagazine_Issue_05-1985.pdf` | 05-1985 | 8.42 | 40 | OK |  |
| 151 | 1985-06 | `NewWineMagazine_Issue_06-1985.pdf` | 06-1985 | 9.14 | 42 | DUP | has exact (1) twin |
| 152 | 1985-06 | `NewWineMagazine_Issue_06-1985 (1).pdf` | 06-1985 copy(1) | 9.14 | 42 | DUP, NAME | exact copy of non-(1) twin — drop |
| 153 | 1985-08 | `NewWineMagazine_Issue_08-1985.pdf` | 08-1985 | 7.69 | 44 | OK |  |
| 154 | 1985-09 | `NewWineMagazine_Issue_09-1985.pdf` | 09-1985 | 8.12 | 44 | OK |  |
| 155 | 1985-10 | `NewWineMagazine_Issue_10-1985.pdf` | 10-1985 | 7.29 | 40 | OK |  |
| 156 | 1985-11 | `NewWineMagazine_Issue_11-1985.pdf` | 11-1985 | 6.94 | 40 | OK |  |
| 157 | 1985-12 | `NewWineMagazine_Issue_12-1985.pdf` | 12-1985 | 7.62 | 44 | OK |  |
| 158 | 1986-02 | `NewWineMagazine_Issue_02-1986.pdf` | 02-1986 | 15.32 | 44 | OK |  |
| 159 | 1986-03 | `NewWineMagazine_Issue_03-1986.pdf` | 03-1986 | 17.16 | 47 | OK |  |
| 160 | 1986-04 | `NewWineMagazine_Issue_04_1986.pdf` | 04-1986 | 17.1 | 48 | NAME | underscore year separator |
| 161 | 1986-05 | `NewWineMagazine_Issue_05_1986.pdf` | 05-1986 | 14.61 | 40 | NAME | underscore year separator |
| 162 | 1986-06 | `NewWineMagazine_Issue_06_1986.pdf` | 06-1986 | 14.96 | 40 | NAME | underscore year separator |
| 163 | 1986-07 | `NewWineMagazine_Issue_07_1986.pdf` | 07-1986 | 22.09 | 66 | NAME, LARGE | underscore year separator |
| 164 | 1986-09 | `NewWineMagazine_Issue_09_1986.pdf` | 09-1986 | 18.96 | 52 | NAME, LARGE | underscore year separator |
| 165 | 1986-10 | `NewWineMagazine_Issue_10_1986.pdf` | 10-1986 | 22.31 | 61 | NAME, LARGE | underscore year separator |
| 166 | 1986-11 | `NewWineMagazine_Issue_11_1986.pdf` | 11-1986 | 16.45 | 46 | NAME | underscore year separator |
| 167 | 1986-12 | `NewWineMagazine_Issue_12_1986.pdf` | 12-1986 | 16.71 | 48 | NAME | underscore year separator |

---

## Recommended handoff for a future ingestion session

1. **Skip** `NewWineMagazine_Issue_03-1973.pdf` (already ingested).
2. **Delete or quarantine** the three `(1)` copies (byte-identical).
3. **Normalize names** (optional, pre-ingest): rename `Issue_MM_YYYY` → `Issue_MM-YYYY` for the 1986 cluster.
4. **Decide policy** for specials before bulk extract:
   - Combined Jul/Aug (and May/Jun 1971) as one document vs. two
   - `Summer1979` and `Newsletter_08-1981` as magazine issues vs. separate source kinds
   - `08-1980_News` vs. regular/combined August material
5. **Work list size after cleanup:** 167 − 1 ingested residual − 3 exact dupes = **163 unique content files** still waiting in `01_to_extract`.

---

## Method

- Filename parse for issue month/year / combined / seasonal / newsletter patterns
- Full MD5 of every file for exact-duplicate detection
- PDF header + `%%EOF` check; page count via `pypdf`
- Spot first-page text extraction on specials (OCR quality varies; Newsletter 08-1981 was clear)
- Cross-check stems against `02_extracted`, `03_approved`, `04_ingested`, `05_archived`, `06_failed`

