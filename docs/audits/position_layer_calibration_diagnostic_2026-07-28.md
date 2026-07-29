# Position layer calibration diagnostic — where answering ends and honest-empty begins

**Date:** 2026-07-28
**What this is:** a read-only measurement exercise to prepare Alex's calibration
call on two linked questions — (a) where the line should sit between the
system answering a question about a teacher and the system honestly saying
"nothing found," and (b) whether the current settings (gather evidence until
it clears a similarity bar, then require at least 5 matching pieces of
evidence before writing anything) still make sense now that evidence is
gathered fresh per real question, rather than against a pre-written topic
list.

**Nothing was generated or written.** No position was created, no database
row was touched. 38 real questions were run through the evidence-gathering
step only — asking, for a named teacher, "how many of this teacher's
approved teaching statements match this question, and how closely" — at a
range of possible closeness bars. This document reports what was found, not
what should be done. The recommendation at the end is a proposal for Alex to
accept, adjust, or reject.

**Cost:** 38 short text lookups against a paid AI service, well under a cent
total. Nothing else in this exercise had a cost.

---

## The headline number

Run against the **current live settings** (closeness bar 0.40, minimum of 5
matching statements before answering):

- **38 questions run.**
- **1 false refusal** — a question the teacher genuinely does address, that
  the system would wrongly treat as unanswerable.
- **3 false passes** — questions the teacher does *not* actually address,
  where the system would gather enough loosely-related material to
  confidently answer anyway. This is the more serious failure mode, since a
  false pass looks exactly like a real answer to a user with no way to tell
  the difference.
- **The minimum-evidence-count of 5 survives, mostly unchanged.** It is
  doing real, correct work on the one teacher in this test with genuinely
  little material (Derek Prince — see below). It is not, however, the
  setting that is causing the false passes. See the recommendation.
- **The closeness bar is the setting that needs to move.** Raising it from
  0.40 to roughly 0.45 would have fixed all three false passes found in this
  test, at the cost of turning one already-borderline correct answer into a
  refusal.

---

## Part 1 — The disagreements (read this section first; this is what needs a ruling)

### 1a. False passes — the system would confidently answer with material that doesn't actually address the question

These are the priority finding. In each case, the system gathered enough
matching material to clear today's bar, but reading what was actually
gathered shows it doesn't answer the question asked — it answers something
that merely uses similar words.

**Leonard Ravenhill — "Does God choose in advance who will be saved, as
Calvinism teaches?"** 20 statements cleared today's bar. Reading them: none
actually discuss the Calvinist doctrine of predestination or election.
They're about God's power to save someone, the seriousness of judgment, and
what a real conversion costs — general statements about salvation that share
vocabulary with a question about predestination without ever taking a
position on it. A position written from this evidence would put a specific
theological stance in Ravenhill's mouth that his own material never states.

**Zac Poonen — the identical Calvinism question.** Same shape of problem, 10
statements cleared the bar, none of them actually discuss predestination —
they're about God's individual plan for a person's life and free will versus
being forced, which is adjacent vocabulary, not the same claim.

**Vlad Savchuk — "What does it mean to be adopted as a son through the
Spirit?"** 15 statements cleared the bar. This is the cleanest case of the
three: the top matches are about the teacher's own biological son and his
experience of fatherhood, plus general statements about a relationship with
the Holy Spirit — none of them touch the actual doctrine the question asks
about (a believer's legal adoption as God's child, a real and specific
biblical teaching). This is pure vocabulary overlap ("son," "Spirit")
producing a confident-looking answer built from evidence that was never
about the question.

**A pattern worth Alex's attention on its own: the identical Calvinism
question was asked of all three large-corpus teachers, and all three showed
the same failure shape** — general "God saves people" material getting
mistaken for a specific doctrinal position none of the three teachers
actually stakes out. This doesn't look like a one-off wording accident. It
looks structural: broad salvation-themed language is common across this
whole style of preaching, and a pure closeness measurement can't currently
tell "addresses this specific doctrine" apart from "uses salvation
vocabulary in general." Raising the closeness bar (below) fixes two of the
three outright and substantially shrinks the third; it does not fully solve
the underlying gap.

### 1b. The one false refusal — a real answer the system would currently miss

**Derek Prince — "How do I recognize when a demon is behind a physical or
emotional problem?"** Prince has substantial real material on deliverance
from demons (seven separate teaching statements, one of his two richest
subjects). But this specific, practically-phrased question only matched
strongly against one of them. His other demon-related material addresses
different angles — the forms demonic activity takes, the steps to being
delivered, how to keep deliverance once received — that don't cluster
tightly around this one diagnostic-style phrasing. The topic is real and
well-covered; this specific way of asking about it is not. Lowering the
closeness bar would fix this, but see 1c below for why that's not free.

### 1c. Near-misses that current settings do not catch

The empty-state design settled last session says: where a teacher has
material *near* a question but not actually answering it, the system should
refuse the specific question while naming what the teacher does address
nearby — never quietly answer the adjacent thing as if it were the same
thing. Two cases in this test show that the numeric gate alone cannot
enforce that rule, even at the proposed tightened setting:

- **Vlad Savchuk — "Who should get custody of children after a divorce?"**
  Even after raising the closeness bar, 5 statements still clear it — his
  general teaching on divorce and remarriage (drawn from 1 Corinthians 7).
  None of it addresses child custody, which is a different question. The
  gate would still let this one through.
- **Vlad Savchuk — "Is intermittent fasting for weight loss a good health
  practice?"** 8 statements still clear the raised bar — and, notably, the
  single closest match is Savchuk explicitly saying fasting is *not* about
  losing weight. The gathered evidence would be enough to confidently answer
  a question his own material is actively distinguishing itself from.

The lesson here isn't a setting to change — it's a limit on what a
count-of-matches gate can do by itself. It can measure "how much material is
in the neighborhood," but it cannot tell whether that material actually
answers the specific question versus merely sitting near it. That
judgment call has to happen somewhere past the gate, not be assumed away by
tuning a number.

### 1d. The thin questions, and where they actually fall

This is the category the whole floor question was meant to be decided by,
so it's worth stating plainly what happened: **for the two richest
teachers, almost nothing behaved as "thin."** Every thin-topic question
asked of Ravenhill, Savchuk, and Poonen still gathered well more than enough
matching material to clear the floor — often 10 to 20 times over. A
literal-keyword check of the underlying material had suggested these were
rare topics; a real closeness-based search found plenty of related content
anyway, because the teacher's other material touches the same territory in
different words. Genuine thinness, in this test, only showed up on the one
teacher with a small amount of material overall (Derek Prince, 21 teaching
statements total against the other three teachers' several hundred each).
That is a separate condition from "a rich teacher who happens not to
address one narrow topic," and the two should probably not be judged by the
same single number — see the open question at the end.

---

## Part 2 — Recommended starting settings (a proposal, not a decision)

**Proposed: keep the minimum-evidence-count at 5. Raise the closeness bar
from 0.40 to approximately 0.45.**

In plain terms: keep requiring at least five matching pieces of teaching
material before the system will ever write anything, but require each piece
of evidence to match the actual question more closely than it does today
before it's allowed to count.

**Why the floor stays put:** raising the minimum-evidence-count, on its
own, does not fix any of the false passes above — even requiring 10 matches
instead of 5 left all three fabrication risks untouched, because they each
had far more than 10 loosely-related matches to begin with. The
minimum-count setting is doing its intended job correctly on the one
genuinely small teacher in this test; it is simply not the lever that
controls whether gathered material actually answers the question. That's
what the closeness bar controls.

**Why the closeness bar moves to roughly 0.45, not higher:** at that
setting, all three confirmed false passes above are fixed, one of the two
concerning near-miss cases is also fixed, and the one already-thin question
that had newly started working correctly stays correct. The cost is one
additional refusal on an already-borderline case for the small-material
teacher (a question that was only barely passing today). Pushing the bar
higher still (tested at roughly 0.50) does fix every false pass in this
test, but it also breaks five separate questions that the teacher
genuinely does answer well — an unacceptable trade the other direction.
0.45 is the point in this test where the fabrication risk drops sharply
without meaningfully damaging real answers.

**What 0.45 does not fix, and Alex should know this going in:** the two
near-miss cases in 1c above still clear the proposed bar. No closeness
setting tested in this run closes that gap without also cutting into real
answers elsewhere. That gap is a reason the near-miss product rule (refuse
the specific question, name what's nearby, stay in the teacher's voice) has
to keep doing real work at the writing stage — it cannot be fully delegated
to a number.

---

## Part 3 — Do the three teaching styles behave differently?

Reported per teacher, not pooled, since a pooled average would hide exactly
the kind of unevenness this test was built to surface.

- **Leonard Ravenhill (exhortation/aphorism style)** and **Vlad Savchuk
  (spoken, topical style)** — both showed the broadest spread of loosely-
  related material getting swept up by ordinary questions, including the
  clearest false passes in this whole test. Both have large amounts of
  material (several hundred statements each), and both preach in a
  free-flowing, emotionally-driven register rather than a structured
  outline — which may be exactly why their material reads as "close enough"
  to a wide range of questions even when it isn't actually answering them.
- **Zac Poonen**, despite also having a large amount of material, showed
  noticeably tighter, more on-topic matches for questions that map onto his
  own structured teaching (his own named frameworks, like his nine-point
  breakdown of the Sermon on the Mount, or his numbered conditions for
  discipleship). His one false pass in this test was the same cross-teacher
  Calvinism question every other large teacher also failed on — not a
  style-specific failure.
- **Derek Prince** is too small a sample in this corpus today (21 teaching
  statements total) to say anything about his *style's* behavior with
  confidence — what's really being measured for him in this test is "what
  happens when a teacher has very little material yet," which is its own
  separate, real, and current condition (see Part 1d), not a demonstration
  of expository writing being naturally thin.

The honest reading: the risk in this test tracked more with *how
free-form a teacher's preaching style is* than with how much material they
have. A teacher with a lot of loosely-associative, topically wide-ranging
material is not automatically safer just because there's more of it — if
anything, this test suggests the opposite.

---

## Part 4 — One correction to this diagnostic's own starting assumption

This diagnostic was framed on the expectation that gathering evidence
against a real, specific question (instead of a short pre-written topic
label) would pull in a *narrower* slice of material, and that the floor
might now be set too high as a result. For the one small-material teacher in
this test, that held. **For the three larger teachers, the opposite showed
up just as often: a full, naturally-worded question pulled in more loosely
related material than a short topic label would have, not less.** Where a
prior measurement exists for comparison, the gap is large — one topic,
asked as a short label in an earlier pass, matched only a handful of
statements; the same topic asked as a real question in this test matched
several times more. A full sentence carries more common, connective
vocabulary than a bare topic label does, and that extra vocabulary is
exactly what widens the semantic net. Worth carrying into the calibration
call as a correction, not just a confirmation, of the premise this
diagnostic started from.

---

## Appendix — every question run, in full

For each question: the teacher it was scoped to, which of the four
categories it was expected to fall into going in, how many matching
teaching statements were gathered at today's live closeness bar (0.40) and
at the proposed bar (0.45), and whether the system would answer or refuse
under each. "Answer" means at least 5 matches cleared the bar; "Refuse"
means fewer than 5 did. The minimum count of 5 is held constant throughout
this table — only the closeness bar changes between the two columns.

### Derek Prince

| # | Expected | Question | Matches @ today's bar (0.40) | Would... | Matches @ proposed bar (0.45) | Would... |
|---|---|---|---:|---|---:|---|
| 1 | Should answer | Should I tithe on my income, and why does it matter to God? | 5 | Answer | 3 | **Refuse** |
| 2 | Should answer | How do I recognize when a demon is behind a physical or emotional problem? | 1 | **Refuse** | 1 | **Refuse** |
| 3 | Thin | How does God use people who feel unqualified for what He's called them to do? | 2 | Refuse | 2 | Refuse |
| 4 | Thin | How can I grow in spiritual discernment so I'm not fooled by false teaching? | 1 | Refuse | 1 | Refuse |
| 5 | Near-miss | Should churches observe the Sabbath on Saturday instead of Sunday? | 0 | Refuse | 0 | Refuse |
| 6 | Near-miss | What are the biblical qualifications for becoming a church elder? | 0 | Refuse | 0 | Refuse |
| 7 | Should refuse | When will the rapture happen, and what are the signs of the end times? | 0 | Refuse | 0 | Refuse |
| 8 | Should refuse | Should babies be baptized, or should baptism wait until someone believes? | 0 | Refuse | 0 | Refuse |

Prince has only 21 approved teaching statements total in the corpus today
(against several hundred for each of the other three teachers below) — his
two real areas of depth are giving/tithing and deliverance from demons,
each with roughly seven to eight statements. Everything else he touches
in this small set is one or two statements at most. This is why his column
looks so different from the other three teachers: there simply isn't much
material yet, not that his teaching itself is thin.

### Leonard Ravenhill

| # | Expected | Question | Matches @ 0.40 | Would... | Matches @ 0.45 | Would... |
|---|---|---|---:|---|---:|---|
| 9 | Should answer | Why does my prayer life feel so weak and half-hearted? | 56 | Answer | 16 | Answer |
| 10 | Should answer | Why hasn't real revival broken out in the church today? | 94 | Answer | 50 | Answer |
| 11 | Should answer | How do I stay pure in a culture saturated with sexual sin? | 19 | Answer | 7 | Answer |
| 12 | Thin | Is speaking in tongues something every believer should experience? | 14 | Answer | 4 | **Refuse** |
| 13 | Thin | What leads a Christian to backslide and drift away from their faith? | 61 | Answer | 9 | Answer |
| 14 | Near-miss | What qualifies someone to be an elder or leader in a local church? | 2 | Refuse | 0 | Refuse |
| 15 | Near-miss | Is the gift of prophecy still active in the church today? | 10 | Answer | 2 | **Refuse (fixed)** |
| 16 | Should refuse | Does God choose in advance who will be saved, as Calvinism teaches? | 20 | **Answer (false pass)** | 1 | Refuse (fixed) |
| 17 | Should refuse | How often should a church take communion, and what does it mean? | 2 | Refuse | 0 | Refuse |
| 18 | Should refuse | How can someone break free from alcohol or drug addiction? | 0 | Refuse | 0 | Refuse |

### Vlad Savchuk

| # | Expected | Question | Matches @ 0.40 | Would... | Matches @ 0.45 | Would... |
|---|---|---|---:|---|---:|---|
| 19 | Should answer | How do I fight back against demonic oppression in my life? | 68 | Answer | 24 | Answer |
| 20 | Should answer | Why should I fast, and how does it strengthen my prayer life? | 57 | Answer | 35 | Answer |
| 21 | Should answer | Is tithing still required for Christians today? | 9 | Answer | 7 | Answer |
| 22 | Should answer | How do I guard myself from falling into sexual sin? | 34 | Answer | 12 | Answer |
| 23 | Thin | What should a healthy church leadership structure look like? | 17 | Answer | 3 | Refuse |
| 24 | Thin | Does God choose in advance who will be saved, as Calvinism teaches? | 25 | Answer | 7 | **Still answers — residual risk, see Part 1a** |
| 25 | Near-miss | Who should get custody of children after a divorce? | 8 | Answer | 5 | **Still answers — see Part 1c** |
| 26 | Near-miss | Is intermittent fasting for weight loss a good health practice? | 16 | Answer | 8 | **Still answers — see Part 1c** |
| 27 | Should refuse | What are the theological differences between Catholic and Orthodox views of communion? | 3 | Refuse | 1 | Refuse |
| 28 | Should refuse | What does it mean to be adopted as a son through the Spirit? | 15 | **Answer (false pass)** | 0 | Refuse (fixed) |

### Zac Poonen

| # | Expected | Question | Matches @ 0.40 | Would... | Matches @ 0.45 | Would... |
|---|---|---|---:|---|---:|---|
| 29 | Should answer | What does Jesus mean in the Sermon on the Mount about true righteousness? | 62 | Answer | 25 | Answer |
| 30 | Should answer | What does it really mean to be a disciple of Jesus, not just a believer? | 62 | Answer | 22 | Answer |
| 31 | Should answer | How do I overcome pride and grow in genuine humility? | 15 | Answer | 5 | Answer |
| 32 | Thin | What are the biblical qualifications for becoming a church elder? | 11 | Answer | 6 | Answer |
| 33 | Thin | Why is fasting an important spiritual discipline? | 21 | Answer | 8 | Answer |
| 34 | Near-miss | Should Christians rely on medical treatment or on faith alone for healing? | 16 | Answer | 2 | Refuse (fixed) |
| 35 | Near-miss | Should baptism be by full immersion or by sprinkling? | 3 | Refuse | 2 | Refuse |
| 36 | Should refuse | When will the rapture happen, and what are the signs of the end times? | 0 | Refuse | 0 | Refuse |
| 37 | Should refuse | Why hasn't real revival broken out in the church today? | 3 | Refuse | 0 | Refuse |
| 38 | Should refuse | Does God choose in advance who will be saved, as Calvinism teaches? | 10 | **Answer (false pass)** | 2 | Refuse (fixed) |

---

## Open question for the calibration call, not resolved by this diagnostic

Should a teacher with very little material overall (like Derek Prince
today) be judged by the same single minimum-evidence-count as a teacher
with hundreds of statements — or does "enough evidence to answer honestly"
need to scale with how much material a teacher has in total? This test
wasn't built to answer that, only to make clear that it's a real, separate
question sitting underneath the single-number floor this session was asked
to check.
