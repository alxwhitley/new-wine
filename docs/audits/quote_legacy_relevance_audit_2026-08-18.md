# Legacy quote relevance audit — approved/pending quotes vs. current passage-level logic

Generated 2026-08-18. Read-only, `rhemata_readonly_analysis` role only. No row
was flagged, revoked, or modified by this script — this report is the
deliverable; what to do about the affected rows is Alex's call.

Methodology: every approved/pending quote is scored against its OWN
currently-assigned `topic` label using the exact passage-level logic
`select_quotes_for_answer()` uses in production today (commit `82ec0f5`) —
`cosine_similarity(embed(topic), embed(quote_text))` against the real,
already-calibrated `QUOTE_PASSAGE_SIMILARITY_THRESHOLD = 0.35`. A quote's
topic label is the only fixed piece of legacy metadata there is to audit
against; under the OLD (retired) design every quote sharing a topic label
scored an identical, meaningless tie for any question resembling that
label, so a score below threshold here means: the OLD design would have
made this quote eligible to be served on that topic; the CURRENT design
would not.

## Scope and cost

- Quotes audited: **793** (636 approved, 157 pending; revoked excluded)
- Distinct topic labels: **113**
- Embedding calls made: 10 (batched, single pass)
- Estimated cost: $0.0010 (ceiling was $50.00)

## Headline finding

**592 of 793 quotes in scope (74.7%) score below the current relevance
threshold against their own topic label** — meaning the old document-tag
design would have made all 592 eligible for selection on that topic; the
current passage-level design would reject every one of them.

## Worst offenders (lowest relevance to their own topic label)

Top 30 by ascending score — least-supported quotes first.

| score | teacher | topic | document | quote_text (truncated) |
|---|---|---|---|---|
| 0.0605 | Derek Prince | Financial Wisdom | The Promises | I believe God answered that prayer and you can find the answer described in Acts 27 and... |
| 0.0633 | Derek Prince | Financial Wisdom | The Promises | It’s the same word. I believe God answered that prayer and you can find the answer desc... |
| 0.0767 | Derek Prince | Financial Wisdom | The Promises | Then, what I like about the King James is the two little words that come last. “By us.”... |
| 0.0825 | Derek Prince | Perseverance | Analysis of Hebrews: Chapter 12 Cont | It was sprinkled on the earth. But the blood of Jesus sprinkled in heaven cries out to ... |
| 0.0831 | Derek Prince | Financial Wisdom | The Promises | I believe God answered that prayer and you can find the answer described in Acts 27 and... |
| 0.0968 | Derek Prince | Overcoming Rejection | Overcoming Guilt, Shame and Rejection | A female Brigadier because in the Salvation Army if your husband dies, you take his ran... |
| 0.1057 | Derek Prince | Character in Leadership | Four More Keys | I understand that in the context to mean that if you cease to rejoice, cease to pray or... |
| 0.1104 | Derek Prince | Holiness | The Church | See, why we proclaim that scripture is because God convinced us, convicted us that it w... |
| 0.1204 | Derek Prince | Overcoming Rejection | Approved In Christ | He’s to be the initiator of everything that happens in the church. Nothing in the churc... |
| 0.1206 | Derek Prince | Pastoral Ministry | The Last Four Of Revelation’s Seven Churches | That, at the name of Jesus every knee shall bow and every tongue shall confess that Jes... |
| 0.1208 | Derek Prince | Overcoming Rejection | Overcoming Guilt, Shame and Rejection | Thank you.”  Now as you stand there after that prayer, I’m going to pray for the Holy S... |
| 0.1208 | Derek Prince | Renewing the Mind | A Man Prepares For Marriage | The husband is related to Christ above and to the wife below. So, as you consider the r... |
| 0.1216 | Derek Prince | Atonement | The Exchange Personalized - Part 1 | Later on I got to know that he had been through a lot of things which made it easy for ... |
| 0.1234 | Derek Prince | Overcoming Rejection | Overcoming Guilt, Shame and Rejection | On the cross Jesus comprehended, took upon Himself, the sins of all humanity from Adam ... |
| 0.1252 | Derek Prince | Holiness | The Church | See, why we proclaim that scripture is because God convinced us, convicted us that it w... |
| 0.1267 | Derek Prince | Financial Wisdom | The Promises | In Romans 1 Paul says, he’s praying that he may have a prosperous journey by the will o... |
| 0.1287 | Derek Prince | Financial Wisdom | The Promises | You know, looking back over a walk with the Lord that has lasted 37 years, I thank God ... |
| 0.1295 | Derek Prince | Financial Wisdom | The Promises | Nevertheless, I do believe that, in a sense, it’s correct. Legally when you came to Chr... |
| 0.1303 | Derek Prince | Breaking Bloodline Curses | Curses - Cure - Part 2 | Nevertheless, facts are facts. I believe that worship is the thing that opens the way f... |
| 0.1310 | Derek Prince | Binding and Loosing | The Right to Judge | It’s not my business tonight to single out exceptions. Basically, I believe, every Chri... |
| 0.1310 | Derek Prince | Overcoming Rejection | Overcoming Guilt, Shame and Rejection | That’s salvation. You know as a boy growing up in the Anglican Church I listened to all... |
| 0.1313 | Derek Prince | Renewing the Mind | A Man Prepares For Marriage | To the best of my knowledge I have never met a Christian who dishonored his parents and... |
| 0.1333 | Derek Prince | Financial Wisdom | The Promises | It’s not by the apostles, it’s not by the early church, it’s not by special Christians,... |
| 0.1343 | Derek Prince | Renewing the Mind | A Man Prepares For Marriage | To the best of my knowledge I have never met a Christian who dishonored his parents and... |
| 0.1363 | Derek Prince | Holiness | Intercession, Fasting | I’ve spent, what, thirty years of my life in the United States, and I’m deeply grateful... |
| 0.1376 | Derek Prince | Renewing the Mind | A Man Prepares For Marriage | So, as you consider the role of Christ you understand the role of the husband. Christ r... |
| 0.1385 | Derek Prince | Tabernacle of Moses | The Tabernacle: A Pattern Of Spirit, Soul And Body | Charismatics have come to believe in the redeeming blood of Jesus. Thank God! But Jesus... |
| 0.1388 | Derek Prince | Tabernacle of Moses | Analysis of Hebrews: Chapter 8 Cont | He does not send him to church or Sunday school or teach him the Golden Rule or how to ... |
| 0.1396 | Derek Prince | Biblical Typology and Symbolism | The Queen God Is Seeking | Sometime near the end of her life when Lydia was struggling for her health she would sa... |
| 0.1399 | Derek Prince | Signs and Wonders | Let Us Honor God’s Holy Spirit | It is wrong to directly address a servant when the master is available for you to speak... |

## Concentration by topic (the direct evidence of the defect)

The document-tag-inheritance defect means one topic label gets stamped
onto every quote pulled from a given document — so the real signature of
the defect is how many DIFFERENT documents share one topic label, not
how many quotes any single document contributes. Sorted by distinct
documents sharing the label, descending.

| topic | quotes | affected | distinct documents sharing this label |
|---|---|---|---|
| End Times | 27 | 24 | 27 |
| Spiritual Warfare | 27 | 17 | 27 |
| The Cross | 42 | 25 | 26 |
| Atonement | 23 | 23 | 23 |
| Biblical Typology and Symbolism | 37 | 36 | 22 |
| Deliverance Ministry | 39 | 28 | 14 |
| Baptism in the Holy Spirit | 14 | 5 | 14 |
| Gifts of the Spirit | 13 | 3 | 13 |
| Holiness | 89 | 77 | 12 |
| Foundations of Christian Doctrine | 24 | 18 | 12 |
| Biblical Hermeneutics | 11 | 11 | 11 |
| Law and Grace | 11 | 8 | 11 |
| Israel and the Church | 22 | 8 | 10 |
| Fivefold Ministry | 25 | 18 | 9 |
| Power of Prayer | 9 | 5 | 9 |
| Identity in Christ | 7 | 4 | 7 |
| Kingdom of God | 7 | 3 | 7 |
| Breaking Bloodline Curses | 6 | 6 | 6 |
| Tabernacle of Moses | 6 | 6 | 6 |
| Church Governance and Structure | 6 | 4 | 6 |
| Eschatology | 6 | 3 | 6 |
| Dying to Self | 6 | 3 | 6 |
| Israel in Bible Prophecy | 19 | 9 | 5 |
| Purpose and Calling | 5 | 4 | 5 |
| Intercessory Prayer | 5 | 4 | 5 |
| Fatherhood | 5 | 4 | 5 |
| Doctrine of the Church | 5 | 4 | 5 |
| Salvation | 5 | 3 | 5 |
| Knowing God | 5 | 3 | 5 |
| Repentance | 5 | 2 | 5 |
| Renewing the Mind | 25 | 25 | 4 |
| Scripture and Authority | 4 | 4 | 4 |
| How to Study the Bible | 4 | 4 | 4 |
| Marriage | 4 | 4 | 4 |
| Biblical Stewardship | 4 | 4 | 4 |
| Revival | 4 | 3 | 4 |
| Gospel | 4 | 3 | 4 |
| Lordship of Christ | 4 | 2 | 4 |
| God's Will and Guidance | 4 | 2 | 4 |
| Hearing God's Voice | 4 | 1 | 4 |
| Fasting and Prayer | 5 | 0 | 4 |
| Overcoming Rejection | 19 | 19 | 3 |
| Unity in the Church | 18 | 18 | 3 |
| Sanctification | 16 | 8 | 3 |
| Apostolic Ministry | 3 | 3 | 3 |
| Discerning Times and Seasons | 3 | 3 | 3 |
| New Covenant | 3 | 3 | 3 |
| Character in Leadership | 3 | 3 | 3 |
| Overcoming Sin | 3 | 3 | 3 |
| Conditions for Revival | 3 | 3 | 3 |
| Great Commission | 3 | 3 | 3 |
| New Creation | 3 | 2 | 3 |
| Prophecy | 3 | 2 | 3 |
| Fear of the Lord | 3 | 2 | 3 |
| Second Coming | 3 | 2 | 3 |
| Justification | 3 | 2 | 3 |
| Encounter with God | 3 | 2 | 3 |
| Spiritual Authority | 3 | 2 | 3 |
| Faith | 3 | 1 | 3 |
| Discipleship | 3 | 1 | 3 |
| Divine Healing | 3 | 0 | 3 |
| Worship | 3 | 0 | 3 |
| Interpreting Scripture | 14 | 14 | 2 |
| Inner Healing | 2 | 2 | 2 |
| Armor of God | 2 | 2 | 2 |
| Faith for Healing | 2 | 2 | 2 |
| Pastoral Ministry | 2 | 2 | 2 |
| Word of God | 2 | 2 | 2 |
| Suffering and Sovereignty | 2 | 2 | 2 |
| Perseverance | 2 | 2 | 2 |
| Servant Leadership | 2 | 2 | 2 |
| Humility | 2 | 2 | 2 |
| Spiritual Growth | 2 | 1 | 2 |
| Weapons of Our Warfare | 2 | 1 | 2 |
| Deep Intimacy with God | 2 | 1 | 2 |
| Trusting God in Hardship | 2 | 1 | 2 |
| Building the Church | 2 | 1 | 2 |
| Water Baptism | 2 | 0 | 2 |

35 additional topic labels are used by only one document each (not shown — no
cross-document tag-sharing to report for those).

## Concentration by source document

Top 25 documents by number of affected (below-threshold) quotes contributed.

| document | teacher | quotes | affected | topics used |
|---|---|---|---|---|
| The Church | Derek Prince | 22 | 22 | 1 |
| A Man Prepares For Marriage | Derek Prince | 22 | 22 | 1 |
| How To Be Delivered | Derek Prince | 26 | 19 | 1 |
| The Promises | Derek Prince | 17 | 17 | 1 |
| Overcoming Guilt, Shame and Rejection | Derek Prince | 17 | 17 | 1 |
| Holiness Outworked | Derek Prince | 17 | 17 | 1 |
| Intercession, Fasting | Derek Prince | 17 | 17 | 1 |
| The Roman Pilgrimage (Part 20) | Derek Prince | 16 | 16 | 1 |
| The Queen God Is Seeking | Derek Prince | 16 | 16 | 1 |
| Mobile Ministries - Apostles | Derek Prince | 17 | 15 | 1 |
| Let Us Honor God’s Holy Spirit | Derek Prince | 15 | 14 | 1 |
| The Roman Pilgrimage (Part 18) | Derek Prince | 13 | 13 | 1 |
| Let Us Go On To Perfection | Derek Prince | 13 | 12 | 1 |
| The Cross Nullifies Witchcraft - Part 2 | Derek Prince | 17 | 11 | 1 |
| What The Church Must Become | Derek Prince | 12 | 11 | 1 |
| Holiness - The Essence of God | Derek Prince | 14 | 8 | 1 |
| Triune Man At Creation | Derek Prince | 14 | 7 | 1 |
| God’s Predetermined Purpose | Derek Prince | 15 | 7 | 1 |
| Israel In The Headlines | Derek Prince | 13 | 4 | 1 |
| Analysis of Hebrews: Chapter 13 Cont | Derek Prince | 1 | 1 | 1 |
| Fasting Brings Restoration | Derek Prince | 1 | 1 | 1 |
| Rejection vs Acceptance | Derek Prince | 1 | 1 | 1 |
| Instruction On Deliverance For Children And Their Parents | Derek Prince | 1 | 1 | 1 |
| Grace vs Law | Derek Prince | 1 | 1 | 1 |
| Analysis of Hebrews: Chapter 9 | Derek Prince | 1 | 1 | 1 |

321 further documents each contribute affected quotes not shown above (321 of
those contribute exactly 1 affected quote each) — 497 distinct documents contain
at least one affected quote in total, out of 497 distinct documents in scope.

## Concentration by teacher

| teacher | quotes | affected | distinct documents | distinct topics |
|---|---|---|---|---|
| Derek Prince | 792 | 592 | 496 | 112 |
| Andrew Murray | 1 | 0 | 1 | 1 |

## What this does and does not show

- This measures a quote's text against the topic label ALREADY attached
  to it, not against any real historical question — there is no stored
  question history to audit against. A quote scoring above threshold
  here is not thereby proven a good match for any real future question;
  it only means it is not a clear document-tag-inheritance false
  positive by this specific test.
- No row's status was changed. No revocation happened. Nothing here
  gates future quote selection — `QUOTE_SELECTION_ENABLED` is untouched
  and this script does not read or write it.

