import { expect, test } from "@playwright/test";

const ANSWER = Array.from(
  { length: 14 },
  (_, i) =>
    `Paragraph ${i + 1}. The gospel of the kingdom is an announcement before it is a doctrine, ` +
    `and the word kingdom carries the whole weight of it.`,
).join("\n\n");

type Metrics = {
  scroller: DOMRect;
  fade: DOMRect;
  composer: DOMRect;
  scrollerPaddingBottom: number;
  composerHeightVar: string;
  scrollHeight: number;
};

function boxes(page: import("@playwright/test").Page): Promise<Metrics | null> {
  return page.evaluate(() => {
    const scroller = document.querySelector<HTMLElement>(".overflow-y-auto.overscroll-contain");
    const fade = document.querySelector<HTMLElement>(".composer-fade");
    const composer = fade?.nextElementSibling as HTMLElement | null;
    if (!scroller || !fade || !composer) return null;
    return {
      scroller: scroller.getBoundingClientRect().toJSON(),
      fade: fade.getBoundingClientRect().toJSON(),
      composer: composer.getBoundingClientRect().toJSON(),
      scrollerPaddingBottom: parseFloat(getComputedStyle(scroller).paddingBottom),
      composerHeightVar: getComputedStyle(scroller).getPropertyValue("--composer-h").trim(),
      scrollHeight: scroller.scrollHeight,
    };
  });
}

/**
 * One thread, every geometry assertion. Deliberately a single test: each setup
 * is a page load plus a paced answer reveal, and running several in parallel
 * against one dev server made them race.
 *
 * The unit tests pin the wiring; this pins the geometry that wiring is supposed
 * to produce -- that the composer really does overlay the thread, and that the
 * reservation really is big enough for the last line to clear it.
 */
test("the floating composer overlays the thread without hiding its last line", async ({ page }) => {
  await page.route("**/study/teachers", (route) => route.fulfill({ json: { teachers: [] } }));
  await page.route("**/study/pins", (route) => route.fulfill({ json: { pins: [] } }));
  await page.route("**/async-chat/submit", (route) =>
    route.fulfill({ json: { job_id: "job-test-1" } }),
  );
  await page.route("**/async-chat/result/**", (route) =>
    route.fulfill({
      contentType: "text/event-stream",
      body:
        `data: ${JSON.stringify({
          answer: ANSWER,
          citations: [],
          conversation_id: null,
          message_id: "m1",
          verified_references: [],
          quote_ids: [],
        })}\n\n` + "data: [DONE]\n\n",
    }),
  );

  await page.goto("/");
  const textarea = page.getByLabel("Ask a question about Scripture or theology");
  const send = page.getByRole("button", { name: "Send message" });
  // Re-fill until it sticks: a fill that lands before React hydrates sets the
  // DOM value only, and the controlled re-render then wipes it, leaving Send
  // permanently disabled. Waiting on the button alone would just time out.
  await expect
    .poll(async () => {
      await textarea.fill("What is the gospel?");
      return send.isEnabled();
    }, { timeout: 15_000 })
    .toBe(true);
  await send.click();

  const lastLine = page.getByText("Paragraph 14.");
  await expect(lastLine).toBeVisible({ timeout: 20_000 });

  const m = await boxes(page);
  expect(m).not.toBeNull();

  // The change itself: the scroller extends BEHIND the composer, and the
  // composer sits flush to its bottom rather than below it.
  expect(m!.composer.top).toBeLessThan(m!.scroller.bottom - 1);
  expect(Math.round(m!.composer.bottom)).toBeLessThanOrEqual(Math.round(m!.scroller.bottom) + 1);

  // --composer-h must be a real measurement, not the 5rem CSS fallback, or the
  // reservation silently stops tracking a grown textarea.
  expect(m!.composerHeightVar).toMatch(/^\d+(\.\d+)?px$/);
  expect(parseFloat(m!.composerHeightVar)).toBeGreaterThan(40);
  expect(m!.scrollerPaddingBottom).toBeGreaterThanOrEqual(m!.composer.height);

  // Taller than the composer: the extra height is the dissolve above it.
  expect(m!.fade.height).toBeGreaterThan(m!.composer.height);
  expect(Math.round(m!.fade.bottom)).toBe(Math.round(m!.composer.bottom));

  // Mid-scroll is the only place the fade is visible -- at the end of a thread
  // the reservation means nothing is left behind the composer to dissolve.
  await page.evaluate(() => {
    const scroller = document.querySelector<HTMLElement>(".overflow-y-auto.overscroll-contain")!;
    scroller.scrollTop = scroller.scrollHeight * 0.45;
  });
  await page.screenshot({ path: "test-results/chat-fade-midscroll.png" });

  // Scrolled fully to the end, the reservation must clear the composer.
  // Scroll and measure in ONE evaluate: the paced reveal keeps re-rendering the
  // markdown, so a locator resolved in one call can be detached by the next,
  // which surfaced as an intermittent null bounding box.
  await expect
    .poll(
      () =>
        page.evaluate(() => {
          const scroller = document.querySelector<HTMLElement>(
            ".overflow-y-auto.overscroll-contain",
          )!;
          scroller.scrollTop = scroller.scrollHeight;
          const fade = document.querySelector<HTMLElement>(".composer-fade")!;
          const composer = fade.nextElementSibling as HTMLElement;
          const last = Array.from(document.querySelectorAll("p")).find((node) =>
            node.textContent?.startsWith("Paragraph 14."),
          );
          if (!last) return Number.POSITIVE_INFINITY;
          // Overlap of the last line into the composer. Must not be positive.
          return last.getBoundingClientRect().bottom - composer.getBoundingClientRect().top;
        }),
      { timeout: 10_000 },
    )
    .toBeLessThanOrEqual(1);

  await page.screenshot({ path: "test-results/chat-fade-bottom.png" });
});
