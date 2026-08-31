# CLF held recordings — review and permanent-hold ruling (2026-08-30)

Read-only diagnostic. No database writes, no API cost. Captions fetched with
`yt-dlp` (native `json3`, no key, no billing) and parsed with the repo's own
`youtube_ingest._parse_json3`; one read-only `SELECT` against the live database
for the comparison set.

**Ruling (Alex, 2026-08-30): all 15 held permanently.** `ingest=FALSE` stands on
every row. The governing reason is **content shape and pastoral-privacy
exposure, not runtime** — recorded so a future session does not reopen this as a
length question and "fix" it with a trimming step.

---

## Scope

The 15 rows at `guess='sermon'`, `ingest='FALSE'`, `status='triaged'` on the
`CLF Church` tab of `sources/youtube/ingest_queue.xlsx`. Held during the
2026-08-29 "Sermon Archive" ingest; never ingested.

## Two prior assumptions corrected

**`qFfoGi7Vexs` is not a bad upload.** The prior session's guess is wrong. It is
one continuous 3h14m service: 21,565 words, captions covering 100% of the
runtime, largest internal caption gap 50s, and no second service start anywhere
in the timeline. Speech-density buckets show worship 0:15–0:50 and sustained
speech from 0:50 to the end. It is the longest recording in the set, not a
corrupt one.

**`kegl6A5yjQQ` has no automatic captions at all.** `yt-dlp --list-subs` returns
only `live_chat`. It could not be assessed from captions and is the only row that
would fall through to the Whisper fallback if ingested. Every measurement below
covers the other 14.

## Measurements

`front` / `back` bound the contiguous run of 5-minute buckets at or above 50% of
that video's peak speech density — an approximation of the material a trimming
step would have to remove at each end.

| video | duration | words | wpm | front | back | title |
|---|---|---|---|---|---|---|
| `qFfoGi7Vexs` | 194:01 | 21,565 | 111 | 55:00 | 4:01 | Don't Underestimate the Power of Obedience — Anna Hilton |
| `LnB_JW87V60` | 167:58 | 17,596 | 105 | 35:00 | 0:00 | Planting for a Harvest — Glen Middleton |
| `8O8Vn2_MEpM` | 148:46 | 16,435 | 110 | 55:00 | 18:46 | The Blessing of Obedience — Scott Woodard |
| `kl8F_RWPlgI` | 146:43 | 13,305 | 91 | 60:00 | 1:43 | The Hindrance of Intimidation — Paul Kidd |
| `7B2Wy4vfG1A` | 143:54 | 15,491 | 108 | 55:00 | 0:00 | Christians In Politics — Nelson Masinde |
| `Xgn0oWRVOUw` | 141:49 | 15,098 | 106 | 30:00 | 1:49 | Identity, Life flow, & Legacy — Travis Koeman |
| `Zfgbmv9Yt_U` | 137:26 | 15,128 | 110 | 15:00 | 12:26 | Preparing for the Harvest — Scott Woodard |
| `xCHCx_AVSUY` | 134:14 | 12,838 | 96 | 45:00 | 4:14 | Dropped But Still Here — Ken Oduor |
| `AclLUH0PHIk` | 125:30 | 11,648 | 93 | 45:00 | 10:30 | God Takes Hold With Your Hands — Glen Middleton |
| `huKk3E7u-G0` | 120:12 | 11,418 | 95 | 15:00 | 10:12 | Breaking the Curse of the Orphan Spirit — Paul Kidd |
| `QEKcDwH0yz0` | 117:41 | 12,733 | 108 | 35:00 | 17:41 | God's Love — Capers Johnson |
| `okK0E2_FuNg` | 114:02 | 11,697 | 103 | 35:00 | 24:02 | A Legacy that Lasts — Nelson Masinde |
| `Sm55ELf6db8` | 104:58 | 10,262 | 98 | 40:00 | 4:58 | Apostolic Bases — Paul Kidd |
| `7fNzLbCrf-Q` | 91:41 | 11,097 | 121 | 0:00 | 16:41 | Light & Darkness — Paul Kidd |
| `kegl6A5yjQQ` | 106:22 | — | — | — | — | no auto-captions; not assessed |

Front overhead median 37:30 (range 0:00–60:00); back overhead median 7:35 (range
0:00–24:02). Word-count median 13,072.

## Why length is the wrong discriminator

Live query, 2026-08-30, YouTube documents by source:

| source | docs | min words | median | max |
|---|---|---|---|---|
| Vlad Savchuk | 126 | 815 | 2,757 | 14,978 |
| Leonard Ravenhill | 117 | 61 | 1,081 | 17,782 |
| **CLF Church** | **56** | **4,311** | **8,608** | **12,823** |
| Zac Poonen | 50 | 727 | 4,490 | 14,336 |

Seven of the 14 held recordings carry fewer words than the largest CLF document
already ingested (12,823). A size threshold does not separate the two sets. The
shape of the recording does.

## What actually separates them

Same deterministic marker detector run over both sets — the held set from
captions, the ingested set from stored `documents.full_text`:

| marker | 15 held (14 readable) | 56 ingested |
|---|---|---|
| service start call | 9 | 0 |
| host welcome | 6 | 0 |
| usher/greeter direction | 3 | 1 |
| sound check | 2 | 0 |
| offering appeal | 9 | 11 |
| dismissal | 5 | 1 |
| next-meeting notice | 4 | 4 |
| livestream greeting | 13 | 9 |
| baby dedication | 2 | 0 |
| **at least one marker** | **14/14** | **23/56** |

The held recordings are whole-service uploads. The ingested 56 are message-only
or near-message-only.

## The governing risk: named-congregant pastoral material

This is the finding that makes the hold permanent rather than a scheduling
question. Ingested as `sermon_transcript` under a named minister, this material
becomes retrievable teaching content, and an answer could surface private
pastoral care about a named member of Alex's own church.

- `qFfoGi7Vexs` closes with several minutes of prayer over a founding member by
  name, covering her age, her wayward children, and her physical health.
- `okK0E2_FuNg` contains a baby dedication naming the infant in full, with
  family members named and present.
- `Xgn0oWRVOUw` walks a woman forward for Spirit baptism, describing her and a
  second named person live from the platform.
- `xCHCx_AVSUY` runs a salvation altar call addressing individuals present.

Two further categories in the same vein, lower severity but same mechanism:

- `7B2Wy4vfG1A` ends in explicit partisan political commentary — a named
  president, Supreme Court appointments, and voting instruction — which would be
  retrievable as CLF teaching.
- `LnB_JW87V60` ends in an offering appeal with check-writing instructions and a
  personal giving figure.

## No clean trim boundary exists

The sustained-speech block is not the message. It contains the offering, the
dedications, and the altar calls; the boundaries in the table above bound speech
density, not teaching. A duration- or density-based trim would not isolate the
message, and a model deciding where a message ends is the exact mechanism that
discarded 60–75% of every sermon before `617341c`. Consistent with the standing
rule: no trimming step should be built casually.

## Recorded against the existing corpus, not the held set

11 of the 56 already-ingested CLF documents contain an offering appeal, and one
each carries an usher direction and a dismissal. This is a milder, pre-existing
form of the same issue already in the corpus. Not acted on this session; not a
blocker. Whether to audit those 11 for named-congregant content is open.

## Method

- `yt-dlp` native `json3` auto-captions, cached; parsed with the repo's
  `youtube_ingest._parse_json3` so word counts match what the ingest path would
  actually store.
- Speech density bucketed at 5 minutes from caption event timestamps.
- Marker detection is deterministic regex over lowercased transcript text — no
  model involved in any classification in this audit.
- Comparison set read from the live database via `rhemata_readonly_analysis`-
  equivalent read-only `SELECT`; no writes anywhere in this session.

One flaw found and corrected mid-session in the scratch inspection script (not
repo code): the first pass dropped `aAppend` caption events, gluing words across
cue boundaries and undercounting by roughly 15%. All figures above come from the
repo's own parser, which retains those events. This is the same defect
`_parse_json3`'s docstring warns about.
