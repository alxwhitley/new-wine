import Link from "next/link";
import {
  ArticlePage,
  ArticleH1,
  ArticleDek,
  ArticleDivider,
  ArticleH2,
  ArticleP,
  ArticleOl,
} from "@/components/marketing/article";

export const metadata = {
  title: "How Rhemata Handles Sources",
  description: "Transparency about where Rhemata's content comes from, how it's used, and how we protect the people who wrote it.",
};

export default function SourcesPage() {
  return (
    <ArticlePage>
      <ArticleH1>How Rhemata Handles Sources</ArticleH1>
      <ArticleDek>
        Transparency about where our content comes from, how it&rsquo;s used, and how we protect the people who wrote it.
      </ArticleDek>
      <ArticleDivider />

      <ArticleH2>Rhemata is not trained on this content</ArticleH2>
      <ArticleP>
        Rhemata does not train an AI model on the books, sermons, and commentaries in its library. There is no model that has absorbed these works and learned to imitate them.
      </ArticleP>
      <ArticleP>
        Instead, Rhemata is a{" "}<strong className="font-semibold text-card-foreground">retrieval and citation system</strong>.{" "}When you ask a question, Rhemata searches its indexed library for relevant passages, retrieves them, and presents an answer built on those passages — with every claim traced back to a named author and source. The original works remain intact, attributed, and pointed back to. Nothing is absorbed, blended, or anonymized into a model.
      </ArticleP>
      <ArticleP>
        This distinction is the foundation of everything we do. AI tools that flatten a thousand voices into one synthetic answer erase the people who did the work. Rhemata exists to do the opposite: put named voices in front of you, with receipts.
      </ArticleP>

      <ArticleH2>Every quote is verified — by code, not trust</ArticleH2>
      <ArticleP>
        A quotation cannot appear in Rhemata unless our software confirms it is an{" "}<strong className="font-semibold text-card-foreground">exact, character-for-character match</strong>{" "}against the source text. If the words don&rsquo;t exist verbatim in the original, they cannot be displayed as a quote. This is enforced mechanically, not editorially. No paraphrase wearing quotation marks. No AI-invented citations.
      </ArticleP>

      <ArticleH2>How content enters the library</ArticleH2>
      <ArticleP>Every source in Rhemata passes through the same pipeline:</ArticleP>
      <ArticleOl>
        <li>
          <strong className="font-semibold text-card-foreground">Classification.</strong>{" "}Before anything is served, each source is assigned a rights status: public domain, owned, licensed, or unverified.
        </li>
        <li>
          <strong className="font-semibold text-card-foreground">Hidden by default.</strong>{" "}New content is not visible to users until its rights status has been reviewed. Our system fails closed — if we haven&rsquo;t cleared it, you can&rsquo;t retrieve it.
        </li>
        <li>
          <strong className="font-semibold text-card-foreground">Attribution at ingest.</strong>{" "}Every document is tied to its author or rights-holder at the moment it enters the system, so attribution can never be lost downstream.
        </li>
        <li>
          <strong className="font-semibold text-card-foreground">Theological review.</strong>{" "}Featured voices are selected against our theological foundations (see{" "}
          <Link href="/beliefs" className="text-primary underline-offset-4 hover:underline">Our Theological Lens</Link>) — not scraped indiscriminately.
        </li>
      </ArticleOl>

      <ArticleH2>What we prioritize</ArticleH2>
      <ArticleP>
        The heart of Rhemata&rsquo;s library is{" "}<strong className="font-semibold text-card-foreground">public domain literature</strong>{" "}— the writers of past centuries whose works belong to everyone: R.A. Torrey, Andrew Murray, Charles Finney, the voices of the early Pentecostal outpouring, and many more. These works are freely quotable, and Rhemata&rsquo;s mission is to put them back in front of a generation that has never read them.
      </ArticleP>
      <ArticleP>
        For contemporary voices, we pursue{" "}<strong className="font-semibold text-card-foreground">direct permission from authors, estates, and ministries</strong>.{" "}Where content carries open licenses (such as Creative Commons), we honor the license terms, including attribution requirements.
      </ArticleP>

      <ArticleH2>For authors and rights holders</ArticleH2>
      <ArticleP>
        If you are an author, publisher, or rights holder and believe your content appears in Rhemata improperly — or if you&rsquo;d like to discuss how your work is represented — contact us directly:
      </ArticleP>
      <p className="font-serif font-semibold text-card-foreground mb-4">[contact email]</p>
      <ArticleP>
        We respond to every rights inquiry. If content is identified as improperly included, we will remove it from retrieval promptly while the matter is reviewed. We would rather lose a source than misuse one.
      </ArticleP>
      {/* SLOT: Once DMCA agent registration is complete, replace the paragraph
          above with formal DMCA notice-and-takedown language and the
          registered agent's contact information. */}

      <ArticleH2>Why we built it this way</ArticleH2>
      <ArticleP>
        Rhemata&rsquo;s audience carries a healthy suspicion of AI — and we share it. An AI that invents quotes, launders sources, or speaks as an anonymous oracle is not a tool for serious theological study. Every safeguard on this page exists for one reason: so that when Rhemata shows you what Torrey or Murray said, you can trust that they actually said it — and go read them yourself.
      </ArticleP>
      <ArticleP>
        Rhemata is not a substitute for the sources. It is a doorway to them.
      </ArticleP>
    </ArticlePage>
  );
}
