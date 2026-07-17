// Shared types + client-side verse-reference detection for the Inline Study
// Panel (SP2 shell — docs/inline-study-panel-spec.md).
//
// Fail-quiet is a hard rule from the spec: "an underline that opens to
// nothing is treated as a trust failure." This detector is deliberately
// conservative — only a recognized book name/abbreviation immediately
// followed by chapter:verse counts as a match. No vague references
// ("verse 26", "that chapter"), no bare numbers, no guessing.
//
// Teacher-reference detection is not implemented yet — the spec's real
// mechanism (SP1's backend hidden-pointer generation) doesn't exist. Verse
// detection is the one genuinely real trigger for this session; see
// rhemata-status.md for what's deferred.

export type StudyReference =
  | {
      type: "verse";
      raw: string;
      book: string;
      code: string;
      chapter: number;
      verseStart: number;
      verseEnd: number | null;
    }
  | {
      type: "teacher";
      name: string;
    };

export function verseId(ref: Extract<StudyReference, { type: "verse" }>): string {
  return `${ref.code}.${ref.chapter}.${ref.verseStart}`;
}

export function referenceLabel(ref: StudyReference): string {
  if (ref.type === "teacher") return ref.name;
  return ref.raw;
}

export function referenceKey(ref: StudyReference): string {
  return ref.type === "verse" ? `verse:${verseId(ref)}` : `teacher:${ref.name}`;
}

// Book name/abbreviation -> canonical 3-letter code, matching the same
// codes already live in the `verses` table (see app/study/page.tsx's
// BOOK_MAP/ABBREV_TO_NAME, which this intentionally mirrors rather than
// imports — that file is spec-mandated read-only this session).
const BOOKS: Array<{ code: string; full: string; abbrevs: string[] }> = [
  { code: "GEN", full: "Genesis", abbrevs: ["Gen"] },
  { code: "EXO", full: "Exodus", abbrevs: ["Exod", "Exo"] },
  { code: "LEV", full: "Leviticus", abbrevs: ["Lev"] },
  { code: "NUM", full: "Numbers", abbrevs: ["Num"] },
  { code: "DEU", full: "Deuteronomy", abbrevs: ["Deut", "Deu"] },
  { code: "JOS", full: "Joshua", abbrevs: ["Josh"] },
  { code: "JDG", full: "Judges", abbrevs: ["Judg"] },
  { code: "RUT", full: "Ruth", abbrevs: [] },
  { code: "1SA", full: "1 Samuel", abbrevs: ["1 Sam"] },
  { code: "2SA", full: "2 Samuel", abbrevs: ["2 Sam"] },
  { code: "1KI", full: "1 Kings", abbrevs: ["1 Kgs"] },
  { code: "2KI", full: "2 Kings", abbrevs: ["2 Kgs"] },
  { code: "1CH", full: "1 Chronicles", abbrevs: ["1 Chr"] },
  { code: "2CH", full: "2 Chronicles", abbrevs: ["2 Chr"] },
  { code: "EZR", full: "Ezra", abbrevs: [] },
  { code: "NEH", full: "Nehemiah", abbrevs: ["Neh"] },
  { code: "EST", full: "Esther", abbrevs: ["Esth"] },
  { code: "JOB", full: "Job", abbrevs: [] },
  { code: "PSA", full: "Psalms", abbrevs: ["Psalm", "Ps"] },
  { code: "PRO", full: "Proverbs", abbrevs: ["Prov"] },
  { code: "ECC", full: "Ecclesiastes", abbrevs: ["Eccl"] },
  { code: "SNG", full: "Song of Solomon", abbrevs: ["Song of Songs", "Song"] },
  { code: "ISA", full: "Isaiah", abbrevs: ["Isa"] },
  { code: "JER", full: "Jeremiah", abbrevs: ["Jer"] },
  { code: "LAM", full: "Lamentations", abbrevs: ["Lam"] },
  { code: "EZK", full: "Ezekiel", abbrevs: ["Ezek"] },
  { code: "DAN", full: "Daniel", abbrevs: ["Dan"] },
  { code: "HOS", full: "Hosea", abbrevs: ["Hos"] },
  { code: "JOL", full: "Joel", abbrevs: [] },
  { code: "AMO", full: "Amos", abbrevs: [] },
  { code: "OBA", full: "Obadiah", abbrevs: ["Obad"] },
  { code: "JON", full: "Jonah", abbrevs: [] },
  { code: "MIC", full: "Micah", abbrevs: [] },
  { code: "NAM", full: "Nahum", abbrevs: ["Nah"] },
  { code: "HAB", full: "Habakkuk", abbrevs: [] },
  { code: "ZEP", full: "Zephaniah", abbrevs: ["Zeph"] },
  { code: "HAG", full: "Haggai", abbrevs: [] },
  { code: "ZEC", full: "Zechariah", abbrevs: ["Zech"] },
  { code: "MAL", full: "Malachi", abbrevs: [] },
  { code: "MAT", full: "Matthew", abbrevs: ["Matt"] },
  { code: "MRK", full: "Mark", abbrevs: ["Mrk"] },
  { code: "LUK", full: "Luke", abbrevs: ["Luk"] },
  { code: "JHN", full: "John", abbrevs: ["Jn"] },
  { code: "ACT", full: "Acts", abbrevs: [] },
  { code: "ROM", full: "Romans", abbrevs: ["Rom"] },
  { code: "1CO", full: "1 Corinthians", abbrevs: ["1 Cor"] },
  { code: "2CO", full: "2 Corinthians", abbrevs: ["2 Cor"] },
  { code: "GAL", full: "Galatians", abbrevs: ["Gal"] },
  { code: "EPH", full: "Ephesians", abbrevs: ["Eph"] },
  { code: "PHP", full: "Philippians", abbrevs: ["Phil"] },
  { code: "COL", full: "Colossians", abbrevs: ["Col"] },
  { code: "1TH", full: "1 Thessalonians", abbrevs: ["1 Thess"] },
  { code: "2TH", full: "2 Thessalonians", abbrevs: ["2 Thess"] },
  { code: "1TI", full: "1 Timothy", abbrevs: ["1 Tim"] },
  { code: "2TI", full: "2 Timothy", abbrevs: ["2 Tim"] },
  { code: "TIT", full: "Titus", abbrevs: ["Tit"] },
  { code: "PHM", full: "Philemon", abbrevs: ["Phlm"] },
  { code: "HEB", full: "Hebrews", abbrevs: ["Heb"] },
  { code: "JAS", full: "James", abbrevs: ["Jas"] },
  { code: "1PE", full: "1 Peter", abbrevs: ["1 Pet"] },
  { code: "2PE", full: "2 Peter", abbrevs: ["2 Pet"] },
  { code: "1JN", full: "1 John", abbrevs: ["1 Jn"] },
  { code: "2JN", full: "2 John", abbrevs: ["2 Jn"] },
  { code: "3JN", full: "3 John", abbrevs: ["3 Jn"] },
  { code: "JUD", full: "Jude", abbrevs: [] },
  { code: "REV", full: "Revelation", abbrevs: ["Rev"] },
];

// Longest-name-first so multi-word names ("1 Corinthians") aren't cut short
// by a shorter alternative earlier in the list.
const NAME_TO_CODE = new Map<string, string>();
for (const b of BOOKS) {
  NAME_TO_CODE.set(b.full, b.code);
  for (const a of b.abbrevs) NAME_TO_CODE.set(a, b.code);
}
const CODE_TO_NAME = new Map<string, string>();
for (const b of BOOKS) CODE_TO_NAME.set(b.code, b.full);
const ALL_NAMES = Array.from(NAME_TO_CODE.keys())
  .sort((a, b) => b.length - a.length)
  .map((name) => name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));

const REFERENCE_CORE = `(${ALL_NAMES.join("|")})\\.?\\s(\\d{1,3}):(\\d{1,3})(?:[-\\u2013](\\d{1,3}))?`;
const REFERENCE_SOURCE = `\\b${REFERENCE_CORE}\\b`;
const REFERENCE_ANCHORED = new RegExp(`^${REFERENCE_CORE}$`);

export interface VerseIdentity {
  code: string;
  chapter: number;
  verseStart: number;
  verseEnd: number | null;
}

// The one place that turns a raw string like "Romans 8:26-28" into a verse
// identity. detectVerseReferences (scanning free text) and isVerified
// (matching SP1's already-isolated `raw` strings) both call this — do not
// duplicate the book-name/range parsing anywhere else.
export function parseVerseIdentity(raw: string): VerseIdentity | null {
  const m = REFERENCE_ANCHORED.exec(raw.trim());
  if (!m) return null;
  const code = NAME_TO_CODE.get(m[1]);
  if (!code) return null; // shouldn't happen — alternation is built from the map itself
  return {
    code,
    chapter: parseInt(m[2], 10),
    verseStart: parseInt(m[3], 10),
    verseEnd: m[4] ? parseInt(m[4], 10) : null,
  };
}

export function detectVerseReferences(
  text: string
): Array<Extract<StudyReference, { type: "verse" }> & { index: number }> {
  const re = new RegExp(REFERENCE_SOURCE, "g");
  const results: Array<Extract<StudyReference, { type: "verse" }> & { index: number }> = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const identity = parseVerseIdentity(m[0]);
    if (!identity) continue;
    results.push({
      type: "verse",
      raw: m[0],
      book: m[1],
      ...identity,
      index: m.index,
    });
  }
  return results;
}

// SP1's hidden pointers, as attached to the SSE meta event's
// verified_references array (backend/app/services/reference_verifier.py).
// Only the verse shape is consumed here — SP2 has no teacher underlines
// (see the plan's Global Constraints).
export interface VerifiedReference {
  type: string;
  raw: string;
  positions?: number[];
  position?: number;
  source_id?: string;
}

// Reconstructs a full verse reference from a persisted verse_id string
// (e.g. "ROM.8.28" — the same code.chapter.verse shape the `verses` table
// and study_pins use). Pins fetched from the server only carry this compact
// identity, not the full StudyReference shape, so the pin dropdown/panel
// need this to render a real book name and reference text.
export function referenceFromVerseId(
  verseIdStr: string
): Extract<StudyReference, { type: "verse" }> | null {
  const parts = verseIdStr.split(".");
  if (parts.length !== 3) return null;
  const [code, chapterStr, verseStr] = parts;
  const chapter = parseInt(chapterStr, 10);
  const verseStart = parseInt(verseStr, 10);
  const book = CODE_TO_NAME.get(code);
  if (!book || Number.isNaN(chapter) || Number.isNaN(verseStart)) return null;
  return {
    type: "verse",
    raw: `${book} ${chapter}:${verseStart}`,
    book,
    code,
    chapter,
    verseStart,
    verseEnd: null,
  };
}

// Allowlist by identity, not by position: a candidate the client-side
// detector found only renders as an underline if SP1 independently verified
// the same verse identity for this message. This sidesteps aligning the
// backend's raw-text character offsets with rendered-DOM text entirely.
export function isVerified(
  ref: Extract<StudyReference, { type: "verse" }>,
  verifiedRefs: VerifiedReference[]
): boolean {
  return verifiedRefs.some((v) => {
    if (v.type !== "verse") return false;
    const identity = parseVerseIdentity(v.raw);
    return (
      identity !== null &&
      identity.code === ref.code &&
      identity.chapter === ref.chapter &&
      identity.verseStart === ref.verseStart &&
      identity.verseEnd === ref.verseEnd
    );
  });
}
