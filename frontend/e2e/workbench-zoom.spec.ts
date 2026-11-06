import { captureNativeWindow } from "./native-zoom";
import { test, expect, chromium } from "@playwright/test";

test("actual Chromium browser zoom at 80, 100, 125, 150 and 200 percent on every page", async ({
  baseURL,
}, info) => {
  test.setTimeout(120000);
  // Chrome's own settings API changes browser zoom. No CSS zoom, pinch scaling or extensions.
  // A temporary persistent profile is required for chrome://settings; no user profile is opened.
  const context = await chromium.launchPersistentContext("", {
    headless: true,
    executablePath:
      process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ||
      chromium.executablePath(),
    viewport: null,
    args: ["--window-size=1440,1000"],
  });
  try {
    const page = context.pages()[0];
    const settings = await context.newPage();
    await settings.goto("chrome://settings/appearance");
    for (const route of [
      "/",
      "/process",
      "/email-intake",
      "/reviews",
      "/vendors",
      "/purchase-orders",
      "/settings",
      "/audit",
    ]) {
      await page.goto(baseURL! + route);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      for (const zoom of [0.8, 1, 1.25, 1.5, 2]) {
        await settings.evaluate(
          `chrome.settingsPrivate.setDefaultZoom(${zoom})`,
        );
        const actual = await settings.evaluate(
          "new Promise(resolve => chrome.settingsPrivate.getDefaultZoom(resolve))",
        );
        expect(actual).toBeCloseTo(zoom);
        await expect
          .poll(() => page.evaluate(() => window.devicePixelRatio))
          .toBeCloseTo(zoom);
        expect(await page.evaluate(() => innerWidth)).toBeLessThan(1500 / zoom);
        expect(await page.evaluate(() => innerWidth)).toBeGreaterThan(
          1300 / zoom,
        );
        await expect
          .poll(() =>
            page.evaluate(
              () => document.documentElement.scrollWidth <= window.innerWidth,
            ),
          )
          .toBe(true);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await captureNativeWindow(
          page,
          info.outputPath(
            `${route.replaceAll("/", "") || "overview"}-browser-zoom-${zoom * 100}.png`,
          ),
        );
      }
    }
  } finally {
    await context.close();
  }
});
