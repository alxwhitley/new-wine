import { expect, test } from "@playwright/test";

const routes = ["/", "/study", "/library"];

for (const route of routes) {
  test(`account footer remains reachable on ${route}`, async ({ page }) => {
    await page.goto(route);

    const viewportWidth = page.viewportSize()?.width ?? 0;
    const tabletHeader = page.locator('[data-testid="tablet-app-header"]');
    if (viewportWidth >= 768 && viewportWidth < 1024) {
      await expect(tabletHeader).toBeVisible();
      const mainBox = await page.locator("main").boundingBox();
      expect(mainBox).not.toBeNull();
      expect(mainBox?.x ?? 999).toBeLessThanOrEqual(10);
    } else {
      await expect(tabletHeader).toBeHidden();
    }

    if (viewportWidth < 1024) {
      await page
        .locator(
          'button[aria-label="Open sidebar"]:visible, button[aria-label="Open menu"]:visible',
        )
        .first()
        .click();
    }

    const footer = page.locator('[data-testid="sidebar-account-footer"]:visible');
    await expect(footer).toHaveCount(1);
    await expect(footer).toBeVisible();

    if (viewportWidth < 1024) {
      await expect
        .poll(async () => (await footer.boundingBox())?.x ?? -999)
        .toBeGreaterThanOrEqual(-1);
    }

    const geometry = await footer.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      const viewport = window.visualViewport;
      const viewportTop = viewport?.offsetTop ?? 0;
      const viewportLeft = viewport?.offsetLeft ?? 0;
      const viewportBottom = viewportTop + (viewport?.height ?? window.innerHeight);
      const viewportRight = viewportLeft + (viewport?.width ?? window.innerWidth);

      return {
        top: rect.top,
        left: rect.left,
        bottom: rect.bottom,
        right: rect.right,
        viewportTop,
        viewportLeft,
        viewportBottom,
        viewportRight,
      };
    });

    expect(geometry.top).toBeGreaterThanOrEqual(geometry.viewportTop - 1);
    expect(geometry.left).toBeGreaterThanOrEqual(geometry.viewportLeft - 1);
    expect(geometry.bottom).toBeLessThanOrEqual(geometry.viewportBottom + 1);
    expect(geometry.right).toBeLessThanOrEqual(geometry.viewportRight + 1);

    const accountControl = footer.locator("button").first();
    const controlBox = await accountControl.boundingBox();
    expect(controlBox).not.toBeNull();
    expect(controlBox?.height ?? 0).toBeGreaterThanOrEqual(44);

    const hasDocumentOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    );
    expect(hasDocumentOverflow).toBe(false);
  });
}
