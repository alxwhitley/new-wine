import { useEffect, useState } from "react";
import type { WordToken } from "@/components/rhemata/interlinear-blocks";

// SP2 Phase 6: extracted verbatim out of app/study/page.tsx's inline fetch
// effect — see PLAN.md Task 20. Only the tokens/loading/isNT fetch logic
// moved; selectedStrongs stays page-level (shared by other features too),
// reset by a separate effect in the caller keyed on the same verseId.

const NT_BOOKS = new Set([
  "MAT", "MRK", "LUK", "JHN", "ACT", "ROM", "1CO", "2CO",
  "GAL", "EPH", "PHP", "COL", "1TH", "2TH", "1TI", "2TI",
  "TIT", "PHM", "HEB", "JAS", "1PE", "2PE", "1JN", "2JN",
  "3JN", "JUD", "REV",
]);
const OT_BOOKS = new Set([
  "GEN", "EXO", "LEV", "NUM", "DEU", "JOS", "JDG", "RUT",
  "1SA", "2SA", "1KI", "2KI", "1CH", "2CH", "EZR", "NEH",
  "EST", "JOB", "PSA", "PRO", "ECC", "SNG", "ISA", "JER",
  "LAM", "EZK", "DAN", "HOS", "JOL", "AMO", "OBA", "JON",
  "MIC", "NAM", "HAB", "ZEP", "HAG", "ZEC", "MAL",
]);
const INTERLINEAR_BOOKS = new Set([...NT_BOOKS, ...OT_BOOKS]);

export function useInterlinear(verseId: string | null): {
  tokens: WordToken[];
  loading: boolean;
  isNT: boolean;
} {
  const [tokens, setTokens] = useState<WordToken[]>([]);
  const [loading, setLoading] = useState(false);

  const isNT = !!verseId && NT_BOOKS.has(verseId.split(".")[0]);

  useEffect(() => {
    setTokens([]);

    if (!verseId) return;

    const book = verseId.split(".")[0];
    if (!INTERLINEAR_BOOKS.has(book)) return;

    setLoading(true);
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/interlinear?verse_id=${encodeURIComponent(verseId)}`)
      .then((res) => { if (!res.ok) throw new Error("interlinear fetch failed"); return res.json(); })
      .then((data: Array<{ original_word: string; transliteration: string; strongs_number: string; english_gloss: string; morphology: string; word_position: number }>) => {
        const mapped = data.map((w) => ({
          greek: w.original_word, transliteration: w.transliteration || "",
          english: w.english_gloss || "", strongs: w.strongs_number || "", morph: w.morphology || "",
        }));
        setTokens(mapped);
      })
      .catch(() => setTokens([]))
      .finally(() => setLoading(false));
  }, [verseId]);

  return { tokens, loading, isNT };
}
