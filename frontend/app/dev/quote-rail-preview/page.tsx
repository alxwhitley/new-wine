"use client";

import { notFound } from "next/navigation";
import { ChatMessage, QuoteRailView } from "@/components/newwine/chat-message";
import type { ResolvedQuote } from "@/lib/api";

/**
 * Local-only visual sign-off surface for Settled #28 QuoteRail presentation.
 * Uses live gold pending row text as fixtures (no resolve API — pending
 * rows do not resolve until approved). Flag stays off; no DB writes.
 */
const FIXTURE_QUOTES: ResolvedQuote[] = [
  {
    id: "09170f3a-b566-4e31-913e-d2c3248e674d",
    quote_text:
      "Romans 5:17 says that we shall reign in life by one Jesus Christ. Not after death, but here in life. We are to reign with him. We are to share his authority.",
    topic: "Kingdom of God",
    topic_ids: ["Kingdom of God", "Spiritual Authority", "Identity in Christ"],
    teacher_name: "Derek Prince",
    work_title: "A Kingdom of Priests",
    restated_point:
      "Christians are called to reign with Christ in this present life, not merely in the afterlife.",
    approved_at: "preview",
  },
  {
    id: "1455e141-1cd8-4f28-9a68-7281bd787273",
    quote_text:
      "We are dealing with strongholds that have been built in the mind of humanity. We alone have the weapons that can break through those strongholds and expose their minds to the truth of the gospel, and bring them out of the captivity of Satan into the captivity of obedience to Jesus Christ.",
    topic: "Spiritual Warfare",
    topic_ids: ["Spiritual Warfare", "Strongholds in the Mind", "Evangelism"],
    teacher_name: "Derek Prince",
    work_title: "A Kingdom of Priests",
    restated_point:
      "Christians possess unique spiritual weapons capable of dismantling mental strongholds and liberating people from Satan's influence into obedience to Christ through the gospel.",
    approved_at: "preview",
  },
];

const SAMPLE_ANSWER = `## Reigning with Christ

Believers are not waiting until heaven to share in Christ's authority. The New Testament speaks of reigning *in life* through Jesus Christ — present-tense participation in his victory, not merely a future hope.

That reign is exercised in spiritual conflict as well. The weapons God gives his people are aimed at strongholds in the mind, so that captives can be brought into the obedience of Christ.`;

const EDGE_CASE_QUOTES: ResolvedQuote[] = [
  {
    id: "edge-long-title",
    quote_text:
      "Faith is the currency of the kingdom of heaven. Without it, it is impossible to please God, because whoever comes to Him must believe that He exists and that He rewards those who diligently seek Him.",
    topic: "Faith",
    topic_ids: ["Faith and Works", "Prayer and Persistence", "The Nature of God"],
    teacher_name: "Andrew Murray",
    work_title:
      "With Christ in the School of Prayer: A Study of the Lord's Teaching Concerning Prayer and Its Answer",
    restated_point: "Faith is the means by which believers access God's promises and please Him.",
    approved_at: "preview",
  },
  {
    id: "edge-no-work-title",
    quote_text: "Obedience is the mother of all the virtues.",
    topic: "Obedience",
    topic_ids: ["Obedience"],
    teacher_name: "Zac Poonen",
    work_title: null,
    restated_point: null,
    approved_at: "preview",
  },
  {
    id: "edge-no-topic",
    quote_text:
      "The Holy Spirit is not given to make us feel good. He is given to make us more like Jesus, whatever the cost.",
    topic: "",
    topic_ids: [],
    teacher_name: "Jack Deere",
    work_title: "Surprised by the Power of the Spirit",
    restated_point: "The Spirit's work aims at Christlikeness, not comfort.",
    approved_at: "preview",
  },
];

export default function QuoteRailPreviewPage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }

  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-2xl px-4 py-8 space-y-6">
        <header className="space-y-2 border-b border-border pb-4">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            Dev preview · QuoteRail visual sign-off
          </p>
          <h1 className="text-lg font-semibold">Settled #28 checklist</h1>
          <ul className="text-sm text-muted-foreground list-disc pl-5 space-y-1">
            <li>Quote visually separated from answer prose</li>
            <li>Teacher name + work title on the quote itself</li>
            <li>Topic chip = primary taxonomy tag (not work title)</li>
          </ul>
        </header>

        <section aria-label="In-answer placement">
          <p className="text-xs text-muted-foreground mb-2">
            As it appears under an assistant answer
          </p>
          <div className="rounded-xl border border-border bg-card px-4 py-2">
            <ChatMessage role="user" content="What does it mean to reign with Christ in this life?" />
            {/* QuoteRail inside ChatMessage needs resolved IDs; preview injects
                QuoteRailView directly so pending gold text can be reviewed. */}
            <div className="mb-4 border-t border-border pt-3">
              <div className="max-w-none text-sm text-foreground leading-relaxed space-y-3 whitespace-pre-wrap">
                {SAMPLE_ANSWER}
              </div>
              <QuoteRailView quotes={FIXTURE_QUOTES} />
            </div>
          </div>
        </section>

        <section aria-label="Rail alone">
          <p className="text-xs text-muted-foreground mb-2">Rail alone (two quotes)</p>
          <div className="rounded-xl border border-border bg-card px-4 py-2">
            <QuoteRailView quotes={FIXTURE_QUOTES} />
          </div>
        </section>

        <section aria-label="Edge cases">
          <p className="text-xs text-muted-foreground mb-2">
            Edge cases: long work title + 3 topics, no work title / no paraphrase, no topic
          </p>
          <div className="rounded-xl border border-border bg-card px-4 py-2">
            <QuoteRailView quotes={EDGE_CASE_QUOTES} />
          </div>
        </section>
      </div>
    </main>
  );
}
