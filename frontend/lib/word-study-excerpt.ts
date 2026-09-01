// Teaser extraction for Precept Austin word-study articles. Moved out of
// app/study/page.tsx so the standalone page and the inline Study Panel share
// one implementation instead of two copies drifting apart.

export function extractTeaser(content: string): string {
  const plain = content
    .split("\n")
    .filter((line) => !line.trimStart().startsWith("#"))
    .join(" ")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/\*(.+?)\*/g, "$1")
    .replace(/_(.+?)_/g, "$1")
    .replace(/`(.+?)`/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
  const sentences = plain.match(/[^.!?]+[.!?]+/g) ?? [];
  return sentences.slice(0, 2).join(" ").trim();
}
