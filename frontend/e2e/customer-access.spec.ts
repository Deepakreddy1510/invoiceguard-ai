import { test, expect, chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { captureNativeWindow } from "./native-zoom";

test("provider entry offers registration, recovery and PKCE redirect", async ({
  page,
}, info) => {
  await page.route("**/api/v1/config", (r) =>
    r.fulfill({
      json: {
        auth_mode: "oidc",
        issuer: "https://invoiceguard-test.auth0.com/",
        client_id: "public-test-client",
        audience: "invoiceguard-api",
      },
    }),
  );
  // Only the external provider is intercepted. This is not live tenant verification.
  await page.route("https://invoiceguard-test.auth0.com/**", (r) =>
    r.fulfill({
      contentType: "text/html",
      body: "<h1>Provider redirect captured for testing</h1>",
    }),
  );
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Welcome back" }),
  ).toBeVisible();
  await page.screenshot({ path: info.outputPath("login.png"), fullPage: true });
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.getByRole("button", { name: "Forgot password?" }).click();
  await expect(page.getByRole("status")).toContainText("reset email");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await page.screenshot({
    path: info.outputPath("registration.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Create account securely" }).click();
  await expect(page).toHaveURL(/invoiceguard-test.auth0.com\/authorize/);
  const url = new URL(page.url());
  for (const [key, value] of Object.entries({
    response_type: "code",
    code_challenge_method: "S256",
    screen_hint: "signup",
  }))
    expect(url.searchParams.get(key)).toBe(value);
  for (const key of ["code_challenge", "state", "nonce"])
    expect(url.searchParams.get(key)).toBeTruthy();
});

test("sidebar access at native zoom and short window heights", async ({
  baseURL,
}, info) => {
  test.setTimeout(180000);
  const context = await chromium.launchPersistentContext("", {
    headless: true,
    executablePath:
      process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ||
      chromium.executablePath(),
    viewport: null,
    args: ["--window-size=1440,855"],
  });
  try {
    const page = context.pages()[0],
      settings = await context.newPage();
    await settings.goto("chrome://settings/appearance");
    const cdp = await context.newCDPSession(page);
    const { windowId } = await cdp.send("Browser.getWindowForTarget");
    for (const height of [768, 700, 600, 500]) {
      await cdp.send("Browser.setWindowBounds", {
        windowId,
        bounds: { width: 1440, height: height + 87 },
      });
      for (const zoom of [1, 1.25, 1.5, 2]) {
        await settings.evaluate(
          `chrome.settingsPrivate.setDefaultZoom(${zoom})`,
        );
        await page.goto(baseURL! + "/");
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await expect
          .poll(() => page.evaluate(() => devicePixelRatio))
          .toBeCloseTo(zoom);
        const toggle = page.getByRole("button", {
          name: "Open navigation",
          exact: true,
        });
        if (await toggle.isVisible()) await toggle.click();
        const nav = page.getByRole("navigation", { name: "Main navigation" });
        await nav.focus();
        await page.keyboard.press("End");
        await nav.hover();
        await page.mouse.wheel(0, 1200);
        const link = nav.getByRole("link", { name: "Settings", exact: true });
        await link.focus();
        await expect(link).toBeInViewport();
        await expect(link).toBeFocused();
        expect(
          await link.evaluate((n) => getComputedStyle(n).outlineStyle),
        ).not.toBe("none");
        await page.keyboard.press("Enter");
        await expect(page).toHaveURL(/\/settings$/);
        if (zoom === 1 && height === 768)
          await captureNativeWindow(page, info.outputPath("sidebar-100.png"));
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        ).toBe(true);
      }
    }
  } finally {
    await context.close();
  }
});

test("mobile navigation touch scroll and Escape restore focus", async ({
  browser,
  baseURL,
}) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 500 },
    hasTouch: true,
    isMobile: true,
  });
  const page = await context.newPage();
  await page.goto(baseURL!);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "Open navigation" }).tap();
  const box = (await page.locator(".sidebar-scroll").boundingBox())!;
  const cdp = await context.newCDPSession(page);
  await cdp.send("Input.dispatchTouchEvent", {
    type: "touchStart",
    touchPoints: [{ x: box.x + 40, y: box.y + box.height - 20 }],
  });
  await cdp.send("Input.dispatchTouchEvent", {
    type: "touchMove",
    touchPoints: [{ x: box.x + 40, y: box.y + 20 }],
  });
  await cdp.send("Input.dispatchTouchEvent", {
    type: "touchEnd",
    touchPoints: [],
  });
  const settings = page.getByRole("link", { name: "Settings", exact: true });
  await settings.focus();
  await expect(settings).toBeInViewport();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Open navigation" }),
  ).toBeFocused();
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toBeHidden();
  await context.close();
});
