# Historical Commentary Attribution & Copyright Audit

**Date:** 2026-07-31
**Scope:** The 307 documents ingested from the "HistoricalChristianFaith Commentaries Database" source (`sources.id = 2ec56c5f-8670-4824-ac2e-e9aa7485b03d`). Read-only session — no rows, files, or governed docs were modified. All findings below are from live queries against the production database and the current repo code, run 2026-07-31.

---

## Summary (plain English)

Two things were checked. The first — whether these 307 documents are secretly being shown to users without credit even though the database says they should be credited — turned out **not to be true anymore**. The database currently says "don't credit these by name" for all 307, and the code correctly honors that in the main chat answers. Something fixed this between the original 2026-07-22 finding and today, but there's no record in git or the migration files of who did it or when — worth asking about, but not urgent.

The second thing — copyright — is the real finding. All 307 documents, covering everyone from 1st-century writers to C.S. Lewis, share **one single license record** in the database, and that record says "public domain, safe to show." That's true for the vast majority of these writers (ancient and medieval church fathers), but it is **not true for three of them**: **C.S. Lewis** (died 1963, work protected until roughly 2033), **J.R.R. Tolkien** (died 1973, protected until roughly 2043), and **Douglas Wilson** (a living author, still writing today). Because licensing is recorded once per source rather than per author, the database has no way to treat these three differently from Origen or Augustine — they're all flagged "public domain" together.

On top of that, there's a separate screen in the app ("Study Mode") that shows commentary content **with the author's name always visible**, regardless of the citation setting that protects the main chat. So if a user browses Study Mode and lands on a Lewis, Tolkien, or Wilson passage, they see it with the real name attached — the one context where the citation-mode fix doesn't apply at all, by design.

**The combination worth flagging first:** three authors whose work is very likely still under copyright are sitting inside a source marked "public domain," retrievable by the app, and — specifically in Study Mode — shown by name. Nothing about the citable/silent distinction protects against this, because that's a chat-answer-only mechanism; it doesn't touch whether the content is retrievable at all, which is what the source-level license record controls.

---

## Goal A — citation_mode reality check

### What citation_mode actually controls

Traced the live code path (not assumed from the field name):

- `documents.citation_mode` is returned unmodified as `d.citation_mode` by both retrieval RPCs (`match_chunks`, `search_chunks_fts` — confirmed against the **live deployed function**, migration `049_seal_null_source_id.sql`, no drift found).
- `backend/app/routers/chat.py::_is_citable()` is the single function that decides attribution in the main `/chat` answer: `citation_mode == 'citable'` → the chunk is labeled `[Source N]`, its author name is attached, and it's added to the `citations` array sent to the frontend (which is what renders the visible "Sources" attribution to the user). `citation_mode == 'silent_context'` (or anything else) → labeled `[Background]`, no author shown, excluded from `citations`.
- This is the *only* mechanism that gates attribution in the main chat path. There is no separate override for `source_kind == 'commentary'` anywhere near this logic — it depends entirely on the stored field.

### What the database actually contains today

```sql
SELECT citation_mode, count(*) FROM documents
WHERE source_id = '2ec56c5f-8670-4824-ac2e-e9aa7485b03d' GROUP BY citation_mode;
```
```
citation_mode   | n
silent_context  | 307
```

**This contradicts this audit's own starting premise.** All 307 rows currently have `citation_mode = 'silent_context'`, not `'citable'`. Per the code path above, that means these documents — when they appear in a chat answer — are correctly shown as unattributed background material today, matching the design intent stated in `backend/app/routers/study.py`'s own comment: *"Commentary docs use citation_mode='silent_context' for chat (to prevent inline citations)."*

Verified directly (not just at the field level) by pulling one real document per author for a 9-author sample spanning the full range of concern — ancient (Augustine, Chrysostom, Desert Fathers, Thomas Aquinas), Reformation (John Wesley), and the modern/at-risk names (C.S. Lewis, Douglas Wilson, G.K. Chesterton, J.R.R. Tolkien) — and running the actual `_is_citable()` logic against each:

| Author | citation_mode | `_is_citable()` result |
|---|---|---|
| CS Lewis | silent_context | **False** — served as `[Background]`, no attribution |
| Augustine of Hippo | silent_context | False |
| John Chrysostom | silent_context | False |
| John Wesley | silent_context | False |
| Douglas Wilson | silent_context | **False** |
| GK Chesterton | silent_context | False |
| JRR Tolkien | silent_context | **False** |
| Thomas Aquinas | silent_context | False |
| Desert Fathers | silent_context | False |

All nine, uniformly, confirm the DB field and are correctly treated as non-attributed in the main chat path.

### Root cause of the discrepancy with the 2026-07-22 finding

The 2026-07-22 finding was correct **at the time** — traced via git history. The (now-deleted) importer script `scripts/ingest_commentaries.py` hardcoded `"citation_mode": "citable"` at insert time, in every version of that script across its history, including its last version before retirement (commit `d4826dc`). That confirms the original bug: the importer really did write `'citable'` for all 307 rows.

**What is not traceable:** how or when the field changed from `'citable'` to the `'silent_context'` value it holds today. Searched:
- Every migration file (`migrations/*.sql`) for an `UPDATE documents SET citation_mode` touching this source or `source_kind='commentary'` — none found. The only migration that sets `citation_mode = 'silent_context'` (`059_silent_context_unattributed_sentinel_docs.sql`) targets two specific, unrelated sentinel documents by ID, not this source.
- Git history (`git log --all -S`) for any committed Python script performing this update — none found.
- The `documents` table has no `updated_at` column, so there's no way to determine the exact date of the change from the row itself.

**Conclusion: someone corrected this, correctly, but not through a migration file or a committed script** — most likely a manual, undocumented Supabase SQL Editor `UPDATE`, outside this repo's normal migration convention. The correction itself appears to be fully and consistently applied (307/307), but there's no audit trail for it. This is a minor process gap worth a mention, not a live problem.

---

## Goal B — full author roster and copyright check

**307 documents, 307 distinct authors — every author has exactly one document.** Confirmed live: `SELECT count(*) FROM documents WHERE source_id = ... GROUP BY author` returns `n=1` for all 307 rows, no exceptions. These are not per-work entries; each is a single (sometimes very large — up to several million words, per a prior corpus-quality pass) compiled document per named author or per source text.

### Methodology (read this before the table)

Doing an individual live web search for all 307 names was judged impractical and not proportionate to the actual decision this data needs to support: the copyright question is binary (safely PD vs. not), and the overwhelming majority of this roster are canonically documented Ante-Nicene through Reformation-era Christian writers, named or anonymous ancient/medieval texts, or church councils — centuries away from any plausible life-plus-70 boundary, not close calls.

What was actually done:
1. **Every one of the 307 names was reviewed** against standard patristics/church-history reference knowledge to identify anyone whose era placement was not immediately, obviously many centuries pre-copyright.
2. **Five names cleared that bar and were individually verified via live web search** (cited below): C.S. Lewis, Douglas Wilson, G.K. Chesterton, J.R.R. Tolkien, J.B. Lightfoot.
3. **Four additional names were spot-checked via live web search** to validate the reliability of the "obviously ancient" classification itself, rather than taking it purely on assumption: Josephus, "Oresiesis-Heru-sa Ast" (an unusual transliteration that turned out to be a real, verifiable 4th-century monk — Orsisius, successor to Pachomius), "John of Cressy" (a 13th-century French cardinal, not a modern figure despite the ambiguous-sounding name), and Pseudo-Dionysius the Areopagite (an anonymous text from c. 500 AD). All four confirmed the classification.
4. The remaining ~298 names are categorized by broad era bucket only (not an individually re-verified exact death year), on the same basis as point 1.

**This is a real simplification, stated plainly per the task's own instruction.** Life-plus-70 is a US/EU baseline, not a universal rule — actual public-domain status also depends on jurisdiction, publication date, and (for older works) whether formalities were met under now-superseded law. If Alex wants every one of the ~298 unflagged names individually re-verified rather than era-bucketed, that's a defined, boundable follow-up — flag it and it can be run as its own pass.

### Authors NOT safely public domain under life-plus-70

| Author | Docs | Death year / status | Life+70 clears in | DB license_status (source-level) | DB visibility |
|---|---|---|---|---|---|
| **C.S. Lewis** | 1 | Died 1963 | ~2033 | `public_domain` | `shown` |
| **J.R.R. Tolkien** | 1 | Died 1973 | ~2043 | `public_domain` | `shown` |
| **Douglas Wilson** | 1 | Living (b. 1953) | N/A — living author | `public_domain` | `shown` |

All three currently sit under the exact same source-level `license_status='public_domain'` / `visibility='shown'` as every other author in this set — see Goal C below for why that matters.

### Two names checked and cleared (already safely PD, despite being modern enough to warrant a real check)

| Author | Death year | Life+70 clears in | Flagged? |
|---|---|---|---|
| G.K. Chesterton | 1936 | 2006 | No — 20 years past the clearance date already |
| J.B. Lightfoot | 1889 | 1959 | No — safely cleared decades ago |

### Everything else (298 names)

Reviewed and found to be canonically ancient, medieval, or Reformation-era — no additional modern individuals identified beyond the three flagged above. Breakdown by category (full author-by-author list in the Appendix):

| Category | Count (approx.) | Notes |
|---|---|---|
| Named ancient/medieval/Reformation-era individual (1st–17th c.) | ~248 | Church fathers, desert fathers, medieval scholastics, Reformation writers — e.g. Augustine, Chrysostom, Origen, Bede, Aquinas, Calvin, Luther. All centuries past any copyright concern. |
| Anonymous ancient/medieval text (no individual author) | ~24 | e.g. Didache, Book of Enoch, Shepherd of Hermas, Muratorian Fragment, Epistle of Barnabas. Not subject to individual-author copyright at all. |
| Pseudonymous ("Pseudo-X") ancient/medieval text | ~19 | Genuinely old regardless of the true (unknown) author — e.g. Pseudo-Dionysius the Areopagite (spot-checked, c. 500 AD). |
| Institutional (church council) | ~6 | e.g. Council of Ephesus, Second Council of Constantinople — not an individual, no copyright question. |
| Collective/group | 1 | "Desert Fathers" as a catch-all attribution. |
| Unclear/unnamed individual attribution | ~2 | "Ambrosian Hymn Writer," "Ancient Greek Expositor" — self-described as ancient in the name itself; no identifiable individual, no death year determinable, not flagged as a risk. |
| **Flagged — not safely PD** | **3** | C.S. Lewis, J.R.R. Tolkien, Douglas Wilson (table above). |
| **Checked and cleared** | **2** | G.K. Chesterton, J.B. Lightfoot (table above). |

One data-quality aside, unrelated to copyright: "Adamnan" and "Adamnán of Iona" appear as two separate author entries (likely the same 7th-century abbot, split by spelling variant) — a cataloging duplicate, not a licensing issue. Not investigated further; noted for whoever next touches this source's metadata.

---

## Goal C — cross-check: where A and B interact

This is the headline finding, not a footnote.

1. **Licensing is recorded once per source, not per document or per author.** The `sources` table has exactly one row for this entire 307-document collection (`license_status='public_domain'`, `visibility='shown'`). There is no per-document or per-author override column anywhere in the schema — `documents` has no `license_status`/`visibility` fields of its own. Structurally, the retrieval gate (`(s.license_status IN ('public_domain','owned') OR ...)`, migration 049) cannot distinguish Augustine from C.S. Lewis within this source. Both are retrievable, right now, under a `license_status` value that is factually accurate for one and factually wrong for the other.

2. **The `citation_mode` fix (Goal A) only protects the main chat-answer path.** It does not gate retrievability at all — that's the source-level license check's job, and that check has no author-level granularity (point 1). So even with `citation_mode` correctly set to `silent_context` today, Lewis/Tolkien/Wilson content is still fully retrievable and usable as background context for chat answers — just not name-attributed there.

3. **Study Mode's dedicated commentary browsing panel structurally ignores `citation_mode` entirely and always shows the author name.** Read directly in `backend/app/routers/study.py` (lines ~674–676): *"Commentary docs use citation_mode='silent_context' for chat (to prevent inline citations) but are always shown in Study Mode. Do not add a citation_mode filter here."* The code does exactly that — no `citation_mode` check anywhere in that endpoint's filtering, and every result includes `"author": chunk.get("author", "")`. Confirmed the frontend actually renders this: `frontend/components/rhemata/commentary-accordion-row.tsx:62` renders `{r.author}` as a visible label on every commentary card.

**Put together:** any user who reaches C.S. Lewis, J.R.R. Tolkien, or Douglas Wilson content through Study Mode sees it with the real author's name attached to real excerpted text, from a source the database currently — and incorrectly, for these three — certifies as public domain. This is true right now, independent of whether the citation_mode fix (Goal A) is working correctly, because Study Mode was explicitly built to bypass that exact mechanism.

One mitigating, worth-noting fact: the admin panel already has a `source_toggles` row for this exact source (`source_kind='commentary'`, label "Historical Commentaries"), currently `enabled=True` — so there is already a one-click admin lever to pull all 307 documents (including the 3 flagged ones) out of live retrieval entirely, without needing a schema change, if that's the fastest interim mitigation Alex wants while a per-author fix is designed.

---

## Discrepancies from this task's stated premise

Per the instruction to trust the repo/database over the prompt's description:

- **The prompt states all 307 rows currently have `citation_mode='citable'`.** Confirmed false — all 307 currently have `citation_mode='silent_context'`. The bug was real as of 2026-07-22 (confirmed via the deleted importer's source code) but has since been corrected at the database level, through a change with no traceable migration, commit, or script — see Goal A above.

---

## Open questions for Alex

1. **Is the source-level-only license model (one `license_status`/`visibility` per source, no per-document/per-author override) something you want changed** — at minimum for collection-style sources like this one that bundle many distinct rights-holders under one umbrella row? Right now there's no schema mechanism to mark Lewis/Tolkien/Wilson differently from Augustine within this source.
2. **For C.S. Lewis, J.R.R. Tolkien, and Douglas Wilson specifically** — do you want these three pulled from retrieval now (e.g., via the existing `source_toggles` "Historical Commentaries" switch, or a more targeted per-author fix), pending a real decision, or is there a reason to believe they're covered some other way (e.g., a licensing arrangement not reflected in this database) that this audit wouldn't have visibility into?
3. **Do you want the ~298 unflagged authors individually re-verified via live search** (rather than era-bucketed as done here), or is the bucketed methodology sufficient given the multi-century safety margin for that group?
4. **Does the undocumented citation_mode correction (Goal A) need to be traced further** — e.g., checking Supabase's own change history/logs if any exist outside this repo — or is "it's correct now and verified" sufficient, with the process gap (no migration record) just noted for the future?
5. **Is the "Adamnan" / "Adamnán of Iona" apparent duplicate worth a cleanup pass**, or is that low-priority enough to fold into a future general metadata pass on this source?

---

## Appendix — full 307-author roster

Every author has exactly 1 document (`n=1` throughout — confirmed live, no exceptions). Category legend: **ANC** = named ancient/medieval/Reformation-era individual (1st–17th c.) · **TXT** = anonymous ancient/medieval text · **PSD** = pseudonymous ("Pseudo-X") ancient/medieval text · **INST** = institutional council · **COL** = collective/group · **UNC** = unclear/unnamed individual, no risk · **FLAG** = not safely public domain · **CLR** = modern enough to check, verified clear.

| Author | Category |
|---|---|
| Abba Poemen | ANC |
| Abercius | ANC |
| Abraham of Nathpar | ANC |
| Acacius of Beroea | ANC |
| Acacius of Caesarea | ANC |
| Acts of Peter | TXT |
| Acts of Peter and Paul | TXT |
| Adamantius | ANC |
| Adamnan | ANC |
| Adamnán of Iona | ANC |
| Agapius of Hierapolis | ANC |
| Alcuin of York | ANC |
| Alexander of Alexandria | ANC |
| Alexander of Jerusalem | ANC |
| Ambrose of Milan | ANC |
| Ambrosian Hymn Writer | UNC |
| Ambrosiaster | ANC |
| Ammon of Hadrianopolis | ANC |
| Ammonas of Egypt | ANC |
| Ammonius of Alexandria | ANC |
| Amphilochius of Iconium | ANC |
| Ancient Greek Expositor | UNC |
| Andreas of Caesarea | ANC |
| Andrew of Crete | ANC |
| Anselm of Canterbury | ANC |
| Anselm of Laon | ANC |
| Anthony the Great | ANC |
| Aphrahat the Persian Sage | ANC |
| Apollinaris of Laodicea | ANC |
| Aponius | ANC |
| Apostolic Constitutions | TXT |
| Apringius of Beja | ANC |
| Arator | ANC |
| Archelaus of Carrhae | ANC |
| Arethas of Caesarea | ANC |
| Arius | ANC |
| Arnobius of Sicca | ANC |
| Arnobius the Younger | ANC |
| Asterius of Cappadocia | ANC |
| Athanasius of Alexandria | ANC |
| Athenagoras of Athens | ANC |
| Augustine of Hippo | ANC |
| Aurelius Prudentius Clemens | ANC |
| Basil of Caesarea | ANC |
| Basil of Seleucia | ANC |
| Bede | ANC |
| Benedict of Nursia | ANC |
| Berengaudus | ANC |
| Bernard of Clairvaux | ANC |
| Besa The Copt | ANC |
| Book of Biblical Antiquities | TXT |
| Book of Enoch | TXT |
| Book of Jubilees | TXT |
| Book of Steps | TXT |
| Braulio of Zaragoza | ANC |
| Caesarius of Arles | ANC |
| Caius Presbyter of Rome | ANC |
| Callistus I of Rome | ANC |
| Cassiodorus | ANC |
| Chromatius of Aquileia | ANC |
| Clement of Alexandria | ANC |
| Clement of Rome | ANC |
| Commodian | ANC |
| Cosmas of Maiuma | ANC |
| Council of Carthage of 411 | INST |
| Council of Carthage of 419 | INST |
| Council of Constantinople of 381 | INST |
| Council of Ephesus | INST |
| **CS Lewis** | **FLAG — died 1963, protected to ~2033** |
| Cyprian | ANC |
| Cyril of Alexandria | ANC |
| Cyril of Jerusalem | ANC |
| Desert Fathers | COL |
| Dhuoda of Septimania | ANC |
| Diadochos of Photiki | ANC |
| Didache | TXT |
| Didascalia Apostolorum | TXT |
| Didymus the Blind | ANC |
| Diodorus of Tarsus | ANC |
| Dionysius of Alexandria | ANC |
| Dionysius of Corinth | ANC |
| Dorotheos of Gaza | ANC |
| **Douglas Wilson** | **FLAG — living author, b. 1953** |
| Ephrem the Syrian | ANC |
| Epiphanius of Salamis | ANC |
| Epiphanius Scholasticus | ANC |
| Epistle of Barnabas | TXT |
| Epistle to Diognetus | TXT |
| Erasmus of Rotterdam | ANC |
| Eucherius of Lyon | ANC |
| Eugippius | ANC |
| Eusebius of Caesarea | ANC |
| Eusebius of Emesa | ANC |
| Eusebius of Gaul | ANC |
| Eusebius of Vercelli | ANC |
| Eustathius of Antioch | ANC |
| Evagrius Ponticus | ANC |
| Eznik of Kolb | ANC |
| Fabian of Rome | ANC |
| Facundus of Hermiane | ANC |
| Fastidius | ANC |
| Faustinus of Lyon | ANC |
| Faustus of Riez | ANC |
| Fructuosus of Braga | ANC |
| Fulgentius of Ruspe | ANC |
| Gaius Marius Victorinus | ANC |
| Gaudentius of Brescia | ANC |
| Gaudentius of Rimini | ANC |
| Gennadius of Constantinople | ANC |
| Gennadius of Massilia | ANC |
| **GK Chesterton** | **CLR — died 1936, cleared 2006** |
| Glossa Ordinaria | TXT |
| Gospel of the Hebrews | TXT |
| Gregory of Elvira | ANC |
| Gregory of Nazianzus | ANC |
| Gregory of Neocaesarea | ANC |
| Gregory of Nyssa | ANC |
| Gregory Palamas | ANC |
| Gregory the Dialogist | ANC |
| Haimo of Auxerre | ANC |
| Haymo of Halberstadt | ANC |
| Hegemonius | ANC |
| Hegesippus | ANC |
| Heracleon | ANC |
| Hesychius of Jerusalem | ANC |
| Hilary of Arles | ANC |
| Hilary of Poitiers | ANC |
| Hippolytus of Rome | ANC |
| Horsiesios | ANC |
| Hugh of Saint-Cher | ANC |
| Ignatius of Antioch | ANC |
| Ildefonsus of Toledo | ANC |
| Irenaeus | ANC |
| Isaac of Nineveh | ANC |
| Isaiah the Solitary | ANC |
| Ishodad of Merv | ANC |
| Isidore of Pelusium | ANC |
| Isidore of Seville | ANC |
| Jacob Bar-Salibi | ANC |
| Jacob of Edessa | ANC |
| Jacob of Serugh | ANC |
| **JB Lightfoot** | **CLR — died 1889, cleared 1959** |
| Jerome | ANC |
| John Calvin | ANC |
| John Cassian | ANC |
| John Chrysostom | ANC |
| John Damascene | ANC |
| John I of Antioch | ANC |
| John of Cressy | ANC (spot-checked: 13th-c. French cardinal, d. 1313) |
| John of Dalyatha | ANC |
| John of Karpathos | ANC |
| John of the Cross | ANC |
| John the Solitary | ANC |
| John Wesley | ANC |
| Josephus | ANC (spot-checked: d. c. 100 AD) |
| **JRR Tolkien** | **FLAG — died 1973, protected to ~2043** |
| Julian of Eclanum | ANC |
| Julian of Toledo | ANC |
| Julianus Pomerius | ANC |
| Julius Africanus | ANC |
| Julius Firmicus Maternus | ANC |
| Justin Martyr | ANC |
| Lanfranc of Canterbury | ANC |
| Lateran Council of 649 | INST |
| Leander of Seville | ANC |
| Leo the Great | ANC |
| Liturgy of Addai and Mari | TXT |
| Liturgy of Saint Mark | TXT |
| Lucifer of Cagliari | ANC |
| Lucius Caecilius Firmianus Lactantius | ANC |
| Macarius of Egypt | ANC |
| Macrina the Younger | ANC |
| Magnus Felix Ennodius | ANC |
| Malchion | ANC |
| Marcus Eremita | ANC |
| Marcus Minucius Felix | ANC |
| Martin Luther | ANC |
| Martin of Braga | ANC |
| Martyrdom Of Polycarp | TXT |
| Maximus of Turin | ANC |
| Maximus the Confessor | ANC |
| Melito of Sardis | ANC |
| Methodius of Olympus | ANC |
| Muratorian fragment | TXT |
| Nemesius of Emesa | ANC |
| Nerses of Lambron | ANC |
| Nicetas of Remesiana | ANC |
| Nicholas of Gorran | ANC |
| Nicholas of Lyra | ANC |
| Nilus of Sinai | ANC |
| Novatian | ANC |
| Odes of Solomon | TXT |
| Oecumenius | ANC |
| Olympiodorus of Alexandria | ANC |
| Optatus of Milevis | ANC |
| Oresiesis-Heru-sa Ast | ANC (spot-checked: = Orsisius, 4th-c. Pachomian monk) |
| Origen of Alexandria | ANC |
| Pachomius the Great | ANC |
| Pacian of Barcelona | ANC |
| Palladius of Antioch | ANC |
| Palladius of Galatia | ANC |
| Pamphilus of Caesarea | ANC |
| Papias of Hierapolis | ANC |
| Papias the Lexicographer | ANC |
| Paschasius of Dumium | ANC |
| Paschasius Radbertus | ANC |
| Paterius | ANC |
| Patrick of Ireland | ANC |
| Paulinus of Milan | ANC |
| Paulinus of Nola | ANC |
| Paulus Orosius | ANC |
| Pelagius | ANC |
| Peter Chrysologus | ANC |
| Peter of Alexandria | ANC |
| Peter Olivi | ANC |
| Petrus Alphonsi | ANC |
| Philastrius of Brescia | ANC |
| Phileas of Thmuis | ANC |
| Philo of Alexandria | ANC |
| Philoxenus of Mabbug | ANC |
| Photios I of Constantinople | ANC |
| Polycarp of Smyrna | ANC |
| Polycrates Of Ephesus | ANC |
| Pope Anterus | ANC |
| Pope Dionysius | ANC |
| Pope Pontian | ANC |
| Pope Urban I | ANC |
| Pope Zephyrinus | ANC |
| Possidius | ANC |
| Potamius of Lisbon | ANC |
| Primasius of Hadrumetum | ANC |
| Proclus of Constantinople | ANC |
| Procopius of Gaza | ANC |
| Prosper of Aquitaine | ANC |
| Protoevangelium of James | TXT |
| Prudentius | ANC |
| Pseudo-Ambrose | PSD |
| Pseudo-Athanasius | PSD |
| Pseudo-Augustine | PSD |
| Pseudo-Barnabas | PSD |
| Pseudo-Basil | PSD |
| Pseudo-Chrysostom | PSD |
| Pseudo-Clement | PSD |
| Pseudo-Cyprian | PSD |
| Pseudo-Cyril | PSD |
| Pseudo-Dionysius the Areopagite | PSD (spot-checked: c. 500 AD) |
| Pseudo-Ephrem | PSD |
| Pseudo-Hegesippus | PSD |
| Pseudo-Hippolytus | PSD |
| Pseudo-Ignatius | PSD |
| Pseudo-Jerome | PSD |
| Pseudo-Justin | PSD |
| Pseudo-Macarius | PSD |
| Pseudo-Origen | PSD |
| Pseudo-Tertullian | PSD |
| Quodvultdeus | ANC |
| Rabanus Maurus | ANC |
| Remigius of Rheims | ANC |
| Richard of Saint Victor | ANC |
| Robert of Tombelaine | ANC |
| Romanos the Melodist | ANC |
| Sahdona the Syrian | ANC |
| Salvian the Presbyter | ANC |
| Second Council of Constantinople | INST |
| Severian of Gabala | ANC |
| Severus of Antioch | ANC |
| Shenoute the Archimandrite | ANC |
| Shepherd of Hermas | TXT |
| Sibylline Oracles | TXT |
| Socrates Scholasticus | ANC |
| Sophronius of Jerusalem | ANC |
| Sulpicius Severus | ANC |
| Symeon the New Theologian | ANC |
| Syncletica of Alexandria | ANC |
| Tatian the Assyrian | ANC |
| Tertullian | ANC |
| The Liturgy Of The Blessed Apostles | TXT |
| The Passing of Mary | TXT |
| The Passion of Saints Perpetua and Felicity | TXT |
| Theodore of Mopsuestia | ANC |
| Theodore Stratelates | ANC |
| Theodoret of Cyrus | ANC |
| Theodorus of Tabennese | ANC |
| Theodotus of Ancyra | ANC |
| Theognostus Of Alexandria | ANC |
| Theonas of Alexandria | ANC |
| Theophanes of Nicaea | ANC |
| Theophilus of Alexandria | ANC |
| Theophilus of Antioch | ANC |
| Theophylact of Ohrid | ANC |
| Thietland of Einsiedeln | ANC |
| Thomas Aquinas | ANC |
| Ticonius | ANC |
| Titus of Bostra | ANC |
| Tyrannius Rufinus | ANC |
| Ulrich Zwingli | ANC |
| Valentinus | ANC |
| Valerian of Cimiez | ANC |
| Venerable Barsanuphius and John the Prophet | ANC |
| Verecundus of Junca | ANC |
| Victor of Cartenna | ANC |
| Victor Vitensis | ANC |
| Victorinus of Pettau | ANC |
| Vigilius of Thapsus | ANC |
| Vincent of Lérins | ANC |
| Walafrid Strabo | ANC |
| Zephyrinus | ANC |
