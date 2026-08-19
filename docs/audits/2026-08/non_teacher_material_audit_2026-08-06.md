# Non-Teacher Material Audit — Andrew Murray books + Derek Prince documents (2026-08-06)

**Type:** Read-only discovery audit. No writes, no schema changes, no new tables.
Nothing was excluded, cleared, or modified. Exclusion decisions are a separate,
later step.

**Purpose:** Find text that is **not the credited teacher's own writing** sitting
inside documents attributed to them — translator's notes, editor/publisher front
matter, third-party appendices, footnotes/quotations from other people, guest
speakers, announcer introductions, etc. Modeled on the already-pinned issue in
Andrew Murray's *The New Life* (front-matter chunks 0–5 already carry
`chunks.quote_ineligible_reason`).

**Scope audited:** the 9 other Andrew Murray books (source_id
`d26f77e7-6ce0-4311-991b-03d9900a6045`); all 496 Derek Prince documents (491
`sermon_transcript` + 5 `magazine_article`; source_id
`17be391b-d025-4178-8543-3e84da675c5d`). *The New Life* itself was only spot-checked
as a control — see §4.

**Mechanism (for reference only):** exclusion is per-chunk via
`chunks.quote_ineligible_reason` (NULL = eligible). The *New Life* precedent set the
convention that a boundary chunk containing **any** non-teacher text is excluded
**whole**, even if it also contains some of the teacher's words. Findings below give
`document_id`, `chunk_index` range, and (for the primary ranges) `chunk_id`s.

**Method + limits:** structural review of every book's head/tail + table of
contents; a marker scan across all chunks (CCEL boilerplate, "translator",
"editor", staff-writer bylines, "related books", speaker labels, announcer
phrasing, copyright, etc.); targeted full reads of every hit. This is **not** an
exhaustive sentence-by-sentence semantic read of all ~1,300 Murray chunks and
~11,000 Prince chunks — an unlabelled block quotation from another author with no
marker word could be missed. Confidence is high on front/back matter and
labelled multi-speaker content; body-embedded quotations are best-effort.

---

## 1. Andrew Murray — front matter (CCEL editorial, all 9 books)

Every book opens with the same CCEL public-domain-edition front matter — catalog
metadata + a CCEL-staff-written "Description", table of contents, CCEL copyright
boilerplate, licensing, and a bibliographic title page — before Murray's own
Preface/text begins. This is the **same class** as *New Life* 0–2
(`ccel_editorial_description_not_teacher_authored`). In several books Murray's own
text begins **mid-chunk** in the last front-matter chunk; per the *New Life*
convention that boundary chunk is listed for whole-chunk exclusion.

| Book | document_id | Front-matter range (chunk_index) | First fully-clean Murray chunk | Notes |
|---|---|---|---|---|
| Absolute Surrender | `1da1afb1-78b2-4eec-be57-01426d676266` | 0–2 | 3 | ch1–2 include "Scanned and corrected by Claude King, September 1999" (third-party scanner note); Murray's sermon heading only at very end of ch2 |
| The Deeper Christian Life | `42098c1c-2ea5-42fc-9d7b-8b4a8f617af4` | 0–2 | 3 | ch2 = title page + "Copyright 1895, Fleming H. Revell" then Murray's ch. I opens mid-chunk |
| The Lord's Table | `6345f2ad-e9ec-4807-9fc1-489f7c828c4a` | 0–3 | 4 | ch0–1 Description signed "Emmalon Davis, CCEL Staff Writer"; ch3 has "[Electronic Text Note: … converted to Arabic numbers …]"; Murray's Preface opens mid-ch3 |
| The Master's Indwelling | `96c648f6-3222-4a66-a465-4eb2812bca75` | 0–2 | 3 | ch2 = end of TOC, then Murray's ch. I opens mid-chunk |
| The School of Obedience | `08b3ccf5-5c95-435e-9884-8f0b433c0487` | 0–2 | 3 | ch2 = title page/publisher + Murray's own dedication (bundled) then text |
| The True Vine | `6daf6671-e386-4103-998e-1fb42914300b` | 0–3 | 4 | ch3 = a frontispiece **poem** + title page (poem authorship = judgment call, §5.1) |
| The Two Covenants | `3645b220-edc5-48bd-b758-e714f19be022` | 0–2 | 3 | ch2 = title page (ISBN/publisher) then Murray's Introduction opens mid-chunk |
| Waiting On God! | `740f915d-0a9e-47f1-b2e8-75ce5e4a5631` | 0–2 **and 5–6** | 3–4 and 7–8 are Murray's | **Scrambled front matter.** 0–2 = metadata/TOC/license; **5–6 = a detailed scripture-by-chapter contents listing**; 3–4 (dedication + Introduction, incl. a poem in ch4 — judgment call) and 7–8 (Murray's Preface, signed "ANDREW MURRAY, Wellington, 3rd March 1896") are Murray's. Needs careful per-chunk review. |
| With Christ in the School of Prayer | `a8e2ead2-7bdf-4f90-9b49-22835800f72a` | 0–3 | 4 | ch3 = license + title page then Murray's Preface opens mid-chunk |

**Front-matter chunk_ids** (index:id):
- Absolute Surrender 0–2: `0:e49532b7-e993-43fd-9934-e934646ebbcb, 1:3461f1e2-a96b-4686-a3de-d9a1784386ea, 2:81ee6445-b225-4a3a-9a13-544245c24044`
- Deeper Christian Life 0–2: `0:573641c2-a805-4a2a-ac7a-95dc46266853, 1:d91ef71a-aa8d-413e-b3eb-38bba43ef77d, 2:7c1518cf-958d-4e08-ad66-620891c1daae`
- Lord's Table 0–3: `0:6933272f-797e-43cd-abf9-04d1b872d5a8, 1:9605a273-7c12-416b-9d86-ad70d39c3d0a, 2:cbc6930a-0cb7-48b9-b98f-93951d707b2b, 3:c016b6fb-e6c6-4227-b545-c5801166bdcd`
- Master's Indwelling 0–2: `0:11583ad6-7e25-480c-a9b7-18717f34d7b9, 1:df01cf26-8d34-49df-ad7e-b47ebd992b64, 2:0e5fb331-70a2-41c8-b6e9-92088b600af1`
- School of Obedience 0–2: `0:434de563-36c0-4577-a6eb-1944c3b5beed, 1:193ee9b7-de62-4244-a36f-4071ac028864, 2:aa30a4a6-833a-473b-9f34-a67d8484ce51`
- True Vine 0–3: `0:3e1270b7-3088-463b-ab5e-7516a44f7f5a, 1:f3c66030-730a-4f4a-9f00-a25898388f85, 2:bdbd8280-661a-43a4-aeb0-c409a683881f, 3:a23b53c3-f73d-4b5b-8fd0-c3410ecd9b68`
- Two Covenants 0–2: `0:3dd7bf41-c1c4-483e-801d-36ad8c56da9a, 1:f76cb467-ece4-49cd-9592-e5bee5ec7eae, 2:334b7693-e4b6-4e1c-8196-51323cf9b54e`
- Waiting On God! 0–2: `0:74edee74-9b9c-42b0-b60e-a1fa6f93ad57, 1:e62f4575-4042-4fa5-a4df-5d80f896a3ee, 2:efa2c3c0-08f6-4b27-96f1-094935b65b2f`; 5–6: `5:62dd8fd1-1e1b-4e55-b45d-78aa6b7442c2, 6:b59cb972-a95d-4b77-92d0-f31c40f94f65`
- School of Prayer 0–3: `0:69b0037e-e6ac-4067-af91-7879be152755, 1:6db1db3a-fe7a-4609-aed7-a7467e78b6ff, 2:fc38e805-c3b0-4c7f-af31-6ce2d7f186e4, 3:cf4b30bf-52fc-4ae8-81af-5de719c40807`

---

## 2. Andrew Murray — back-matter / body third-party material (the substantive finds)

### 2.1 The Lord's Table — back APPENDIX (Heidelberg Catechism + Dutch Reformed Directory)
- **document_id** `6345f2ad-e9ec-4807-9fc1-489f7c828c4a`, **chunk_index 76–77**
  (`76:8e878f1a-becc-4685-a05f-7bc77285dc67, 77:77f9c993-1e7e-41c5-8d62-100e0b044fea`).
- ch76 opens with a **publisher/editor's third-person note** ("Throughout the
  preceding pages *the author* makes such pointed reference … *it has been thought
  of advantage to the reader* to have these passages before him"), then quotes the
  **Dutch Reformed Directory of Public Worship** ("I. Self-Examination") and the
  **Heidelberg Catechism, Question & Answer 76** ("II. Christ in the Supper")
  verbatim. **None of this is Murray's own writing.** Confidence: high.

### 2.2 The Lord's Table — translator's footnote in the body
- **document_id** `6345f2ad-…`, **chunk_index 54** (`6633550a-694c-4a12-8274-5384c54a6210`).
- One-line translator footnote: "The Dutch version has: … — **Translator**". Small,
  embedded in a chunk that is otherwise Murray's — a mixed chunk (see §5).

### 2.3 The School of Obedience — "Note on the morning watch" (John R. Mott quotations)
- **document_id** `08b3ccf5-5c95-435e-9884-8f0b433c0487`, **chunk_index 86–89**
  (`86:201a39f7-…, 87:3ac38f07-…, 88:1cbddd8a-…, 89:2eb28737-…`).
- The note opens with block quotations, and the text itself states: "**These
  quotations are from an address by John R. Mott.**" Murray's own commentary is
  interleaved with the Mott quotes across ch86–88. Mixed boundary — judgment call
  §5.2. Confidence: high that Mott (third party) is quoted here.

### 2.4 With Christ in the School of Prayer — closing "George Müller" chapter (verbatim Müller)
- **document_id** `a8e2ead2-7bdf-4f90-9b49-22835800f72a`, **chunk_index 227–251**
  (`227:21f903c8 … 251:5b838f91`).
- Final chapter "George Müller, and the Secret of his Power in Prayer": Murray's
  biographical framing at ch227–228, then from ch229 ("**He writes:—**") onward it
  is **extensive verbatim quotation from George Müller's own writings** (his four
  rules, journal entries, "Six years and eight months I have been day by day …")
  running to ch251. Müller's quoted words are not Murray's. Mixed with Murray's
  framing — judgment call §5.2. Confidence: high.

### 2.5 With Christ in the School of Prayer — CCEL "Related Books" advertisement (other authors)
- **document_id** `a8e2ead2-…`, **chunk_index 255–256**
  (`255:9a7b4f76-e9bb-4946-a86a-ca62147fd677, 256:c58d2ea3-6a5c-4616-95e6-f64781271cf1`).
- A CCEL "Related Books" promo block advertising **other authors' books** —
  including **E. M. Bounds, *Essentials of Prayer*, blurb signed "Abby Zwart, CCEL
  Staff Writer"**, plus an *Absolute Surrender* blurb. Pure CCEL marketing; **not
  Murray**, and it names a different author. Confidence: high (highest-risk item —
  a quote pulled here would attribute another author / a CCEL ad to Murray).

### 2.6 Auto-generated Scripture indexes (all 9 books) — low quote-risk, consistency item
- Each book ends with "Index of Scripture References" (and, some, "Index of
  Scripture Commentary" / "Index of Pages of the Print Edition") — the last 1–2
  chunks of each book (e.g. Absolute Surrender ch123; Master's Indwelling ch143;
  Two Covenants ch152–153; School of Prayer ch251–254). Auto-generated reference
  lists, not Murray's prose. **The existing *New Life* handling did NOT exclude its
  back index**, so treating these is a consistency decision — judgment call §5.3.

### 2.7 Confirmed **Murray's own** (checked, NOT findings)
- **The Two Covenants** appended "Notes A–F" (incl. "George Müller and his Second
  Conversion", "Canon Battersby") — written in Murray's first-person voice; his own
  notes. (ch145 carries a one-line William Law bibliographic footnote.)
- **Waiting On God!** closing "Note" (ch100–102) recommending William Law's *The
  Power of the Spirit* — Murray's own first-person recommendation ("My publishers
  have just issued …").
- In-body hymn/poem quotations Murray chose to include (e.g. Master's Indwelling
  ch141; Lord's Table ch5 "—Philip Doddridge") — part of Murray's authored
  devotional.

---

## 3. Derek Prince — findings

The 491 transcripts are overwhelmingly Prince's own spoken words; ministry/boilerplate
markers are rare (~11 "Derek Prince Ministries" hits, all but a few are Prince
referring to his own ministry; all 30 "radio program" hits are Prince describing his
own broadcast). Genuine non-Prince material:

### 3.1 Third-party introductions (announcer/introducer before Prince speaks)
- **"The Harvest Just Ahead"** — **chunk_index 0–1**
  (`0:2830a3fa-0a9c-423b-ae46-14b803b958fc, 1:e40da4a7-f74d-4363-9317-962f2b14d433`).
  Opens: "Hello. This is **Dick Leggatt, President of Derek Prince Ministries**, and
  I am thrilled to be giving you the introduction to a very special message by Derek
  Prince…"; continues in third person into ch1. Not Prince.
- **"Prophecy – God's Time Map"** — **chunk_index 0**
  (`e2c4f5ca-b4a3-480d-90b3-840b11e8a6f0`). Editorial intro: "This is a teaching by
  Derek Prince … It was taught in 1971. Derek was 56 at the time …" (third-person).
  Not Prince.

### 3.2 Co-speakers / guest speakers within a session
- **"What The Church Must Become"** — **chunk_index 0** (`f44349c3-10be-418f-a971-962b27d52d2c`).
  After Derek's one-sentence intro, "**RUTH:** Yeah, I just wanted to follow on with
  what David said…" — Ruth Prince's own remarks (and references a "David" who spoke
  earlier). Mixed chunk.
- **"The Bride Prepares Herself"** — document_id `b99b54e9-f5e4-4c23-9272-20bec71ffd5d`
  (max chunk_index 16). A **multi-speaker conference session**: inline "(Derek)/(Gary)"
  dialogue and a handoff to guest **Michael Kilgore** (Director of Operations, DPM),
  who gives a parenting testimony incl. the "Benny" salvation story (~ch12–13); "Gary"
  answers questions (~ch12); "George" referenced (ch0). Substantial non-Derek speech
  interleaved with Derek's — needs careful range review (judgment call §5.4).

### 3.3 Q&A questioner / moderator turns
- **"I'm Glad You Asked That!"** — document_id `698276f7-7e5c-4c9f-966c-592c3fea08c5`
  (max 21). A **moderator** poses questions ("Please ask Brother Derek to deal with
  the two closing questions on Page 20 of the study guide. These are my
  responsibilities, I put them in" — ch16–19). Moderator/question turns are not Prince.
- **"Women In The Church - Question and Answer"** — document_id
  `45adafa8-5cd7-488b-8a8b-278bf76ecf28` (max 28). Audience "QUESTION" turns
  (some labelled "(RUTH)") interspersed with "ANSWER - DEREK"; a third-person
  narrator aside at ch17 ("Derek was asked this question when we were in Germany…").
  Questions are not Prince. (**"Seven Basic Conditions For Answered Prayer" is NOT a
  Q&A** despite its title — ordinary Prince teaching, no third-party turns.)

### 3.4 Study-note / ministry framing (bibliographic)
- **"Deliverance And Demonology"** — a **study-note-outline** document, not a plain
  transcript: **ch0** (`31836717-5693-4558-a789-4f0794896c21`) = header "…by Derek
  Prince / — Study Note Outline — / Six Tape Series / 6001 …"; **ch16 (last)**
  (`ef6503bc-a9bf-4828-8ad7-d8ac5bc62c45`) = "© 1971 — Derek Prince
  Ministries–International" footer. The outline body is Prince's; the header + ©
  footer are editorial framing.
- Minor bibliographic label lines at the top of some transcripts: "Derek Prince
  (Tape # 4076)" (Progressive Commitment ch0), "Derek Prince:" speaker tag (Women In
  The Church ch0), "Tape No. I-4204" (The Exchange Personalized – Part 2 ch0). Trivial.

### 3.5 Magazine articles (5) — clean, with masthead header only
All 5 `magazine_article` docs are genuine single-author Derek Prince *New Wine*
articles (Jan 1970 – Jan 1978): *God's Judgment in the Here-and-Now*; *God's Men on
the Move*; *Health and Healing – It's Up to You! (Part 2)*; *The First Mile*; *Two
Ways of Receiving The Holy Spirit*. **No** editor intros, other-author content, or
mixed-author pages. Only non-authored text = the bracketed running masthead/byline
at the top of each chunk, e.g. "[New Wine | January 1978 | … by Derek Prince]"
(bibliographic; low quote-risk).

---

## 4. Supplementary — *The New Life* (the "already-handled" control) appears only partly handled

*The New Life* already excludes front-matter chunks 0–5. The control spot-check
found the **same class of problem in its body, not covered by that exclusion**:
- **Translator's footnotes** at chunk_index **83–84, 96–97, 100–101, 145–146,
  193–194** (each signed "— Translator", e.g. ch84: "Professor N.J. Hofmeyr is
  senior professor of the Theological College of the Dutch Reformed Church … —
  Translator").
- **Heidelberg Catechism Q&A 76 quoted in the body** at chunk_index **181–184**
  (within Murray's chapter "XLIII. The Lord's Supper").

Flagged because it directly bears on how complete the quote-rail's non-teacher-material
handling is: the existing *New Life* treatment addressed front matter only, and the
translator-footnote pattern also affects *The Lord's Table* (§2.2). Not re-audited in
full — Alex to decide whether the body of *New Life* is in scope for a later pass.

---

## 5. Items needing Alex's judgment (ambiguous — flagged, not decided)

1. **Frontispiece poems** — *The True Vine* ch3 and *Waiting On God!* ch4 each carry a
   short poem in the front matter/introduction. Unclear whether the poem is Murray's
   own or a third party's. (Both fall inside front-matter ranges already, so excluding
   the range covers them regardless — but the authorship question stands.)
2. **Mixed teacher/third-party chunks — how much to exclude:**
   - *School of Obedience* ch86–89 (John R. Mott quotations **interleaved** with
     Murray's commentary): exclude the whole note, or only the Mott block quotes?
   - *With Christ in the School of Prayer* ch227–251 (George Müller **verbatim
     quotations** with Murray's framing at 227–228): exclude the whole chapter, or
     only Müller's quoted passages (≈229–251)?
   - *The Lord's Table* ch54 (a one-line translator footnote inside an otherwise-Murray
     chunk): whole-chunk exclusion loses Murray's words on that page.
3. **Auto-generated Scripture indexes** (§2.6) and **the *New Life* body items** (§4):
   should the exclusion approach extend to (a) back-matter indexes and (b) the
   already-handled *New Life*'s body, for consistency? The current *New Life* handling
   did neither.
4. **Prince multi-voice documents** — *What The Church Must Become* (Ruth), *The Bride
   Prepares Herself* (Michael Kilgore / Gary / George), *I'm Glad You Asked That!* and
   *Women In The Church - Question and Answer* (moderator + audience questions): these
   are genuine non-Derek voices, but brief/contextual and interleaved with Derek's
   answers. Treat as excludable non-teacher material, or accept audience-question /
   co-speaker context as integral? Exact per-chunk boundaries need review if excluding.
5. **Bibliographic headers/footers** — magazine mastheads (§3.5), tape-ID / speaker-tag
   lines (§3.4), study-note header + © footer (§3.4): technically not the teacher's
   authored sentences, but low quote-risk. Include or ignore?

---

*Discovery only. No `chunks.quote_ineligible_reason` values, `document_quote_clearance`
rows, or quote tables were written or changed by this audit.*
