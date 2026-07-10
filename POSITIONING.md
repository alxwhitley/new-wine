# POSITIONING.md — Rhemata

**Status:** Source of truth. Every feature, every line of copy, every design decision gets checked against this document. If a proposal can't pass the guardrails in Section 10, it doesn't ship.

---

## 1. One-liner

**Rhemata is an AI-assisted Bible study tool that answers from real, named teachers in the Spirit-filled tradition — never from an averaged, anonymous AI voice — and always points you back to the humans behind the answers.**

---

## 2. The Problem

Three pains, in order of sharpness:

**General AI flattens your tradition and softens your convictions.** Ask ChatGPT about the baptism of the Holy Spirit and you get a survey: "some Christians believe... others hold..." — every tradition averaged into one beige, lowest-common-denominator answer, filtered to offend no one. For a Spirit-filled believer, that's not neutrality. It's erasure. The tools everyone else uses treat your convictions as an edge case to be sanded down.

**Discernment anxiety is real and heavy.** The charismatic world has a genuine false-teacher problem, and every young believer in it knows this. YouTube's algorithm surfaces whoever is loudest, not whoever is trustworthy. The question underneath most of this audience's searching isn't "what does this verse mean?" — it's "**who can I trust to tell me?**" No existing tool answers that question. Most make it worse.

**AI is quietly becoming a synthetic oracle.** People are already treating chatbots as spiritual authorities — asking them what God is saying, taking synthesized answers as revelation, substituting a model for a mentor. This is a counterfeit form of discipleship, and it's growing. The pain isn't hypothetical fear of AI; it's that the default AI experience actively pulls people *away* from real teachers and real churches.

The precise pain, in one sentence: *Spirit-filled believers who want to go deeper have nowhere to study that takes their tradition seriously, tells them who's trustworthy, and doesn't quietly replace their teachers with a machine.*

---

## 3. Who It's For

### Primary persona (build for this person first): The Discerning Student

Early-to-mid 20s through 30s. Spirit-filled — grew up in or came into a charismatic church. Genuinely hungry: listens to sermons on YouTube, has questions their small group can't answer, wants to understand tongues, prophecy, healing, spiritual warfare at a real depth. And carrying trust anxiety: they've watched teachers fall, they've seen deconstruction eat their friends, they know the tradition has grifters, and they are quietly terrified of being led astray. They've tried ChatGPT for Bible questions and felt the flattening — the answer was technically fine and spiritually dead.

**Their job-to-be-done:** "Help me go deeper in what I actually believe, from voices I can verify are trustworthy, without handing my faith to an algorithm."

Every default in the product is set for this person: the tone, the citation prominence, the "go to the source" nudges, the vetted-voices framing.

### Secondary personas (served, not built-for)

- **The lay teacher / small-group leader:** preps studies, needs cited material fast, needs to *show* their group where an answer came from. Rhemata serves them well as a byproduct of serving the Discerning Student — citations and named voices are exactly what they need to teach responsibly.
- **The seasoned deep-study believer:** wants Greek/Hebrew, patristic commentary, cross-referenced depth. Study Mode is their home. They come later; they're also the hardest to win and the least anxious — they already have tools and teachers.

**Why the Discerning Student first:** they have the sharpest pain (trust anxiety + flattening), the fewest alternatives (real study tools ignore their tradition; their tradition's content is scattered across YouTube), and they're the person the thesis was written for. Win them and the secondary personas follow. Chase all three and the product speaks to no one.

---

## 4. The Core Belief

**AI is not a counterfeit for discipleship, and Rhemata will never let it become one.**

God disciples people through people. The teacher who has walked with the Spirit for forty years, made mistakes, repented, and kept going carries something no model can synthesize — not because the technology isn't good enough yet, but because authority in the Kingdom is a matter of a life lived, not information retrieved. A machine can organize teaching. It cannot *be* a teacher.

So Rhemata's job is deliberately limited: **find the right teaching, show you exactly whose it is, and send you to the human.** The moment this product starts sounding like a spiritual authority in its own right — the moment a user would rather ask Rhemata than ask their pastor — it has failed at the thing it exists to do, no matter how good the answers are.

The tool serves the teacher. Never the reverse.

---

## 5. What Rhemata Is NOT

This section is a decision filter. If a feature makes Rhemata more like any item on this list, kill it.

- **Not an oracle.** Rhemata never speaks as if it hears from God, never offers "a word," never frames output as revelation or leading. It reports what named teachers have taught. Full stop.
- **Not a replacement pastor.** No spiritual counsel in its own voice. When a question is pastoral rather than informational, the answer points to a human, not deeper into the app.
- **Not "ChatGPT with a Bible."** General AI answers from everything and everyone, averaged. Rhemata answers *only* from a vetted, named corpus. Constraint is the product.
- **Not a source of new revelation.** Nothing Rhemata generates carries authority. Authority lives with the named voices and, above them, the text itself.
- **Not a flattening, filtering general AI.** Rhemata does not average the charismatic tradition into generic Christianity, and it does not apply content filters that treat conviction as a liability. If a cited teacher says demons are real and deliverance is for today, Rhemata says so — with the citation — instead of hedging it into oblivion.
- **Not a content farm.** Rhemata does not manufacture a feed of synthetic teaching to keep users scrolling. It has no interest in maximizing time-in-app at the expense of time-with-teachers.

---

## 6. The Differentiator

**Genuinely defensible:**

- **The vetted, named-voices constraint.** Every answer traceable to a real teacher the user can look in the eye (or at least look up). This is a trust layer no general AI can offer, because general AI's entire architecture is anonymized averaging. It also can't be bolted on later by a competitor without rebuilding their corpus and their legal posture from scratch.
- **Paraphrase-and-cite discipline.** Every answer is built only from retrieved source material and labeled as summary, never presented as a teacher's own words — nothing is invented and pinned to a name after the fact. General AI can hallucinate what a teacher supposedly said; Rhemata is structurally confined to what the corpus actually contains. (Verified-verbatim quoting — machine-checked, character-for-character, before a quote can ever be served — is a planned, gated future layer; not live today.)
- **The refusal to flatten or filter.** Taking the charismatic tradition seriously — tongues, healing, deliverance, prophecy treated as live realities within the corpus, not anthropological curiosities — is a posture the big general tools structurally cannot adopt. Their scale forces them toward the middle. Rhemata's niche *is* the edge.
- **The send-them-back posture.** Every competitor's incentive is retention; Rhemata's stated design goal is connecting users to human teachers. Counterintuitively, this builds the deepest trust — the tool that's willing to send you away is the tool you believe.

**Honestly not defensible:**

- The underlying AI. Retrieval, embeddings, synthesis — commodity parts anyone can assemble.
- Interlinear Greek/Hebrew tools. These exist elsewhere (Blue Letter Bible, Logos). Rhemata's version is table stakes for Study Mode, not a moat.
- Speed to market. A well-funded competitor could build a generic version fast. What they can't fake is the vetting judgment, the tradition-specific corpus, and the credibility of the constraint.

The moat, stated plainly: **trust, expressed as a constraint.** Everything defensible about Rhemata flows from what it refuses to do.

---

## 7. Messaging Pillars

Every piece of copy should ladder to one of these four.

1. **Real voices, not an averaged one.**
   *"Every answer comes from a named teacher you can verify — never from an anonymous AI voice."*

2. **Your tradition, taken seriously.**
   *"Rhemata doesn't flatten Spirit-filled conviction into generic Christianity, and it doesn't filter it down to something safe."*

3. **Always know whose shoulders you're standing on.**
   *"Citations aren't a footnote feature — they're the whole point. You always know who said it, and where."*

4. **The tool that sends you back to the teacher.**
   *"AI can organize teaching. Only people can disciple you. Rhemata is built to hand you off, not hold you in."*

---

## 8. Voice & Tone

**Four words:** Grounded. Convinced. Warm. Unhurried.

Rhemata sounds like a well-read friend from your church who takes both the Word and the Spirit seriously — not a startup, not a seminary lecture, not a hype account.

| Do | Don't |
|---|---|
| Speak with conviction: "Derek Prince taught..." | Hedge into mush: "Some might suggest that possibly..." |
| Use the tradition's own language naturally (baptism in the Spirit, deliverance, the gifts) | Put scare quotes around charismatic vocabulary or explain it apologetically |
| Be plain and direct; short sentences carry weight | Use SaaS-speak: empower, seamless, unlock, revolutionize, supercharge |
| Point outward: "Hear the full teaching here" | Boast inward: "Rhemata's powerful AI has determined..." |
| Reverent about Scripture and the teachers | Stuffy, academic, or performatively pious |
| Admit limits openly: "The corpus doesn't cover this — ask your pastor" | Bluff an answer to avoid looking incomplete |

---

## 9. How Each Surface Expresses the Thesis

**Chat.** The front door. Retrieval with citations — every answer built from the corpus, every claim attributed to its named voice, links out to the original teaching. *Guardrail:* Chat answers in a reporting voice ("Prince taught X; Bevere frames it as Y"), never an authoritative first-person theological voice. When the corpus is thin or the question is pastoral, Chat says so and points to a human rather than improvising. AI-paraphrased material is always framed as summary of a named teacher, never presented as the teacher's own words.

**Study Mode.** The deep room. Greek/Hebrew interlinear plus historical and patristic commentary — the place the Discerning Student goes when a Chat answer opens a door. *Guardrail:* Study Mode presents texts, tools, and named commentary; it does not editorialize conclusions. The interlinear shows what the words are; the named voices say what they mean; Rhemata itself stays out of the pulpit.

**Pastors' Notes (coming).** The human layer, on the roadmap: trusted, vetted pastors and leaders contributing devotional notes attached to the verse in front of you — real shepherds present inside the study experience. *Guardrail:* contributor vetting is the feature. Notes are always bylined, never anonymous, never AI-generated, and the bar for who contributes stays high even when growth pressure says lower it. Until it ships, it is described as coming — never implied to be live.

**Library.** A pointer directory: titles, authors, and topics from the vetted corpus, with links out to where the teaching legally and actually lives — the teacher's channel, book, or site. Metadata and directions; no reproduced text, no synthetic feed. *Guardrail:* Library is the purest expression of "send them back to the teacher," and it stays modest — a well-kept card catalog, not a content destination. It is deliberately low-priority; it must never grow a feed, and copy must never oversell it as a reading experience.

**Admin.** The unseen surface where the thesis is enforced: source vetting, license status, visibility gating, contributor approval. *Guardrail:* fail closed. Unvetted or unlicensed material is invisible by default; nothing reaches a user that hasn't passed the trust layer. The admin tooling exists so that the promise on the landing page is mechanically true, not aspirationally true.

---

## 10. Guardrails — Hard Lines

Stated as rules. No exceptions without rewriting this document first.

1. **Rhemata never speaks as God, for God, or about what God is "saying" to a user.**
2. **Every theological claim is attributed to a named source.** No anonymous synthesis presented as teaching.
3. **AI-generated paraphrase is always labeled as summary — never presented as a teacher's own words.** Answers paraphrase and cite named sources; they do not quote freely today. (Verified-verbatim quoting — machine-checked, character-for-character, before serving — is a planned, gated future capability; not live yet.)
4. **Unvetted and unlicensed content is never served.** Fail closed, always.
5. **No feature ships whose success metric is keeping users away from human teachers.** Time-in-app is not a north star.
6. **Pastoral questions get pointed to people, not answered by the product.**
7. **The tradition's convictions are never filtered, softened, or reframed to seem more palatable.**
8. **Contributor vetting standards do not bend for growth.**
9. **No synthetic content feed, ever.** Library stays a directory; Chat stays an answer surface.
10. **If a proposed feature would make a user say "I don't need my pastor, I have Rhemata" — it dies in this document.**

---

## A Note on the Name

*Rhemata* is the plural of *rhema* — in charismatic usage, the spoken, living word: Scripture that lands with present force, the word for the moment. The name signals the tradition's conviction that God's word is not merely archived but alive. It also carries a quiet discipline for the product: *rhema* comes by the Spirit through people — preached, spoken, taught — never generated. The name is a promise that this tool exists to carry living words from real voices, not to manufacture them.

---

## The 15-Second Version (read this to a skeptical pastor)

"Rhemata is a Bible study tool for Spirit-filled believers, and it's built on one rule: it never answers in its own voice. Every answer comes from real, named teachers in our tradition — cited, checkable, and linked back to the source — and when someone needs a shepherd instead of a search result, it says so and points them to one. It's the opposite of asking ChatGPT about God: no averaged answers, no watered-down convictions, no machine pretending to be a mentor. The AI organizes the teaching. The teachers stay the teachers."
