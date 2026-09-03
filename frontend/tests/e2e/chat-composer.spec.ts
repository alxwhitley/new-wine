import { expect, test } from "@playwright/test";

test("multiline composer stays usable through visible viewport changes", async ({ page }) => {
  await page.goto("/");

  const textarea = page.getByLabel("Ask a question about Scripture or theology");
  const sendButton = page.getByRole("button", { name: "Send message" });
  await textarea.focus();
  await textarea.fill(
    Array.from(
      { length: 28 },
      (_, index) => `Line ${index + 1}: a longer prompt that should scroll inside the composer.`,
    ).join("\n"),
  );

  await expect.poll(() => textarea.evaluate((element) => element.style.overflowY)).toBe("auto");
  const expanded = await textarea.evaluate((element) => {
    const viewportHeight = window.visualViewport?.height ?? window.innerHeight;
    return {
      height: element.getBoundingClientRect().height,
      maxHeight: Math.min(192, Math.max(96, Math.floor(viewportHeight * 0.32))),
      scrollHeight: element.scrollHeight,
      clientHeight: element.clientHeight,
    };
  });
  expect(expanded.height).toBeLessThanOrEqual(expanded.maxHeight + 1);
  expect(expanded.scrollHeight).toBeGreaterThan(expanded.clientHeight);

  const initialViewport = page.viewportSize();
  expect(initialViewport).not.toBeNull();
  await page.setViewportSize({
    width: initialViewport!.width,
    height: Math.max(320, Math.floor(initialViewport!.height * 0.55)),
  });

  await expect.poll(async () => {
    return textarea.evaluate((element) => {
      const rect = element.closest("form")!.getBoundingClientRect();
      const viewport = window.visualViewport;
      const viewportBottom = (viewport?.offsetTop ?? 0) + (viewport?.height ?? window.innerHeight);
      return rect.bottom <= viewportBottom + 1;
    });
  }).toBe(true);

  await expect(sendButton).toBeVisible();
  const sendBox = await sendButton.boundingBox();
  expect(sendBox).not.toBeNull();
  expect(sendBox?.height ?? 0).toBeGreaterThanOrEqual(44);

  await page.setViewportSize(initialViewport!);
  await expect(textarea).toBeFocused();
});
