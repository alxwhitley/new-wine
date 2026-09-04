import { expect, test } from "@playwright/test";

const phases = [
  "Searching the corpus",
  "Reading relevant sources",
  "Building from the evidence",
  "Checking names and attributions",
  "Verifying source references",
] as const;

test("answer wait shows one phase at a time", async ({ page }) => {
  await page.route("**/async-chat/submit", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ job_id: "loader-preview-job" }),
    });
  });
  await page.route("**/async-chat/result/loader-preview-job", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 6_000));
    await route.fulfill({
      contentType: "text/event-stream",
      body: [
        'data: {"answer":"A tested answer.","citations":[]}',
        "",
        "data: [DONE]",
        "",
      ].join("\n"),
    });
  });

  await page.goto("/");
  await page
    .getByLabel("Ask a question about Scripture or theology")
    .pressSequentially("Test the loader");
  await page.getByRole("button", { name: "Send message" }).click();

  const status = page.getByRole("status");
  await expect(status).toHaveText(phases[0]);
  await expect(status.locator("span")).toHaveCount(1);
  await expect(status).toHaveText(phases[1], { timeout: 4_000 });

  for (const phase of phases) {
    await expect(page.getByText(phase, { exact: true })).toHaveCount(
      phase === phases[1] ? 1 : 0,
    );
  }

  await expect(status).toBeHidden({ timeout: 8_000 });
  await expect(page.getByText("A tested answer.", { exact: true })).toBeVisible();
});
