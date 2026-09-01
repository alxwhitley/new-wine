// Shared types + client-side verse-reference detection for the Inline Study
// Panel (SP2 shell — docs/inline-study-panel-spec.md).
//
// Fail-quiet is a hard rule from the spec: "an underline that opens to
// nothing is treated as a trust failure." This detector is deliberately
// conservative — only a recognized book name/abbreviation immediately
// followed by chapter:verse counts as a match. No vague references
// ("verse 26", "that chapter"), no bare numbers, no guessing.
//
// Teacher-reference detection (SP4): unlike verses, teacher names aren't a
// generic regex-detectable pattern — detectTeacherReferences instead does a
// literal search against the small, known curated-teacher list (fetched
// once via GET /study/teachers), then isTeacherVerified gates each match
// against SP1's backend-verified pointers by source_id, exactly like verses
// gate by identity.

import { ABBREV_TO_NAME } from "./generated/book-maps.ts";

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
      source_id: string;
    };

export function verseId(ref: Extract<StudyReference, { type: "verse" }>): string {
  return `${ref.code}.${ref.chapter}.${ref.verseStart}`;
}

export function verseIdToReferenceLabel(verseId: string): string | null {
  const match = /^([A-Z0-9]{3})\.(\d+)\.(\d+)$/.exec(verseId.trim());
  if (!match) return null;
  const book = ABBREV_TO_NAME[match[1]];
  if (!book) return null;
  return `${book} ${match[2]}:${match[3]}`;
}

export function referenceLabel(ref: StudyReference): string {
  if (ref.type === "teacher") return ref.name;
  return ref.raw;
}

export function referenceKey(ref: StudyReference): string {
  return ref.type === "verse" ? `verse:${verseId(ref)}` : `teacher:${ref.source_id}`;
}

// Book name/abbreviation -> canonical 3-letter code, matching the same
// codes already live in the `verses` table. The (code, full name) identity
// below is imported from the generated shared module (backend/app/
// constants.py's ABBREV_TO_NAME, via frontend/lib/generated/book-maps.ts)
// so it can never drift from app/study/page.tsx or app/library/page.tsx.
//
// BOOK_ABBREVS below is deliberately NOT sourced from the shared module and
// stays hand-curated here. Two reasons this is not full-union duplication:
//   1. This file's own detector is "deliberately conservative" by design
//      (see the file-top comment) — it scans free-form generated answer
//      prose, not an isolated search-box string, so it accepts a narrower
//      set of short/compact forms (e.g. no bare "Jos", "Act", "Ezr") than
//      the search-box parsers in app/study/page.tsx and
//      backend/app/constants.py accept. Widening this list is a detection-
//      policy decision, not a de-duplication, and needs its own sign-off.
//   2. The ordinal-literal forms here ("1st Samuel", "2nd Corinthians",
//      "3rd John") are NOT BOOK_MAP keys on the backend at all — the
//      backend instead strips the ordinal suffix before lookup
//      (app.routers.study.parse_ref / reference_verifier._parse_verse_or_
//      range). This file has no such strip-first step, so these literal
//      forms are load-bearing here specifically (confirmed still true by
//      the 2026-07-28 ordinal/spelled/Roman-numeral fix commit, ee267d4).
// A pre-existing, unrelated asymmetry found while consolidating (not
// changed here, since this task is a de-dup, not a behavior change): this
// file accepts "Jn" but not "Jhn"; the backend accepts "jhn" but has no
// "jn" key — so "Jn 3:16" and "Jhn 3:16" resolve on only one side each.
const BOOK_ABBREVS: Record<string, string[]> = {
  GEN: ["Gen"],
  EXO: ["Exod", "Exo"],
  LEV: ["Lev"],
  NUM: ["Num"],
  DEU: ["Deut", "Deu"],
  JOS: ["Josh"],
  JDG: ["Judg"],
  RUT: [],
  "1SA": ["1 Sam", "1st Samuel", "First Samuel", "I Samuel"],
  "2SA": ["2 Sam", "2nd Samuel", "Second Samuel", "II Samuel"],
  "1KI": ["1 Kgs", "1st Kings", "First Kings", "I Kings"],
  "2KI": ["2 Kgs", "2nd Kings", "Second Kings", "II Kings"],
  "1CH": ["1 Chr", "1st Chronicles", "First Chronicles", "I Chronicles"],
  "2CH": ["2 Chr", "2nd Chronicles", "Second Chronicles", "II Chronicles"],
  EZR: [],
  NEH: ["Neh"],
  EST: ["Esth"],
  JOB: [],
  PSA: ["Psalm", "Ps"],
  PRO: ["Prov"],
  ECC: ["Eccl"],
  SNG: ["Song of Songs", "Song"],
  ISA: ["Isa"],
  JER: ["Jer"],
  LAM: ["Lam"],
  EZK: ["Ezek"],
  DAN: ["Dan"],
  HOS: ["Hos"],
  JOL: [],
  AMO: [],
  OBA: ["Obad"],
  JON: [],
  MIC: [],
  NAM: ["Nah"],
  HAB: [],
  ZEP: ["Zeph"],
  HAG: [],
  ZEC: ["Zech"],
  MAL: [],
  MAT: ["Matt"],
  MRK: ["Mrk"],
  LUK: ["Luk"],
  JHN: ["Jn"],
  ACT: [],
  ROM: ["Rom"],
  "1CO": ["1 Cor", "1st Corinthians", "First Corinthians", "I Corinthians"],
  "2CO": ["2 Cor", "2nd Corinthians", "Second Corinthians", "II Corinthians"],
  GAL: ["Gal"],
  EPH: ["Eph"],
  PHP: ["Phil"],
  COL: ["Col"],
  "1TH": ["1 Thess", "1st Thessalonians", "First Thessalonians", "I Thessalonians"],
  "2TH": ["2 Thess", "2nd Thessalonians", "Second Thessalonians", "II Thessalonians"],
  "1TI": ["1 Tim", "1st Timothy", "First Timothy", "I Timothy"],
  "2TI": ["2 Tim", "2nd Timothy", "Second Timothy", "II Timothy"],
  TIT: ["Tit"],
  PHM: ["Phlm"],
  HEB: ["Heb"],
  JAS: ["Jas"],
  "1PE": ["1 Pet", "1st Peter", "First Peter", "I Peter"],
  "2PE": ["2 Pet", "2nd Peter", "Second Peter", "II Peter"],
  "1JN": ["1 Jn", "1st John", "First John", "I John"],
  "2JN": ["2 Jn", "2nd John", "Second John", "II John"],
  "3JN": ["3 Jn", "3rd John", "Third John", "III John"],
  JUD: [],
  REV: ["Rev"],
};

const BOOKS: Array<{ code: string; full: string; abbrevs: string[] }> = Object.entries(
  ABBREV_TO_NAME
).map(([code, full]) => ({ code, full, abbrevs: BOOK_ABBREVS[code] ?? [] }));

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
const REFERENCE_SOURCE = `(?<![A-Za-z])\\b${REFERENCE_CORE}\\b`;
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
    // Do not fall through from an unrecognized single-letter book prefix to
    // an embedded valid book name (for example, "I Genesis 1:1"). Recognized
    // prefixes such as "II Timothy" are already part of the longest match.
    const precedingText = text.slice(0, m.index);
    if (/(?:^|[^A-Za-z])[A-Za-z]\s+$/.test(precedingText)) continue;
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
// Both shapes are consumed as of SP4 — see isVerified (verse) and
// isTeacherVerified (teacher) below.
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

// The finite, known set of curated teachers (GET /study/teachers) — small
// enough that literal substring search is the right tool, unlike verse
// detection's regex-over-arbitrary-text problem.
export interface CuratedTeacher {
  name: string;
  source_id: string;
}

export function detectTeacherReferences(
  text: string,
  curatedTeachers: CuratedTeacher[]
): Array<Extract<StudyReference, { type: "teacher" }> & { index: number }> {
  const results: Array<Extract<StudyReference, { type: "teacher" }> & { index: number }> = [];
  for (const teacher of curatedTeachers) {
    const escaped = teacher.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const re = new RegExp(`\\b${escaped}\\b`, "g");
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      results.push({
        type: "teacher",
        name: teacher.name,
        source_id: teacher.source_id,
        index: m.index,
      });
    }
  }
  return results;
}

// Allowlist by source_id, not name string: a curated-teacher candidate the
// client detected only renders as an underline if SP1 independently
// verified the same source_id for this message. Simpler than isVerified's
// identity-parsing since both sides already carry the same source_id.
export function isTeacherVerified(
  ref: Extract<StudyReference, { type: "teacher" }>,
  verifiedRefs: VerifiedReference[]
): boolean {
  return verifiedRefs.some((v) => v.type === "teacher" && v.source_id === ref.source_id);
}
