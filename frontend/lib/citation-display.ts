export function hasRenderableInlineCitation(content: string, citationCount: number): boolean {
  if (citationCount <= 0) return false;
  for (const match of content.matchAll(/\[(\d+)\]/g)) {
    const index = Number.parseInt(match[1], 10);
    if (index >= 1 && index <= citationCount) return true;
  }
  return false;
}

export function shouldRenderCitationFallback(content: string, citationCount: number): boolean {
  return citationCount > 0 && !hasRenderableInlineCitation(content, citationCount);
}
