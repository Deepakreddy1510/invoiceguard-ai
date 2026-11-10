import { test, expect, chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { captureNativeWindow } from "./native-zoom";

// Real app and Supabase SDK; provider responses are controlled, not live registration.
test("Supabase signup, confirmation, login errors and recovery", async ({
  page,
}, info) => {
  await page.route("**/api/v1/config", (r) =>
    r.fulfill({
      json: {
        auth_mode: "supabase",
        supabase_url: "https://invoiceguard-test.supabase.co",
        supabase_publishable_key: "sb_publishable_test",
      },
    }),
  );
  await page.route("https://invoiceguard-test.supabase.co/auth/v1/**", (r) => {
    if (r.request().url().includes("token"))
      return r.fulfill({
        status: 400,
        headers: {
          "x-supabase-api-version": "2024-01-01",
          "access-control-expose-headers": "X-Supabase-Api-Version",
          "access-control-allow-origin": "*",
        },
        json: { code: "invalid_credentials", msg: "Invalid login credentials" },
      });
    return r.fulfill({ json: {} });
  });
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
  await page.getByLabel("Email address").fill("new@example.invalid");
  await page
    .getByLabel("Password", { exact: true })
    .fill("secure-password-123");
  await page.screenshot({
    path: info.outputPath("signin-hidden.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Show password" }).focus();
  await page.keyboard.press("Space");
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute(
    "type",
    "text",
  );
  await expect(page.getByLabel("Password", { exact: true })).toBeFocused();
  await page.screenshot({
    path: info.outputPath("signin-visible.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Hide password" }).click();
  await page.getByRole("button", { name: "Sign in securely" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Invalid email or password. Please try again.",
  );
  await page.screenshot({
    path: info.outputPath("signin-invalid.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await page.screenshot({
    path: info.outputPath("registration.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Create account securely" }).click();
  await expect(page.getByRole("status")).toContainText("confirm your email");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("button", { name: "Forgot password?" }).click();
  await page.getByRole("button", { name: "Send reset email" }).click();
  await expect(page.getByRole("status")).toContainText("password reset email");
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
      for (const zoom of [0.9, 1, 1.25, 1.5, 2]) {
        await test.step(`${height}px window at ${zoom * 100}% native zoom`, async () => {
          await settings.evaluate(
            `chrome.settingsPrivate.setDefaultZoom(${zoom})`,
          );
          await page.goto(baseURL! + "/");
          await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
          await expect
            .poll(() => page.evaluate(() => devicePixelRatio))
            .toBeCloseTo(zoom);
          // Native zoom applies viewport/media-query changes across animation frames.
          // Wait for layout before deciding whether the responsive menu needs opening.
          await page.evaluate(async () => {
            await document.fonts.ready;
            await new Promise((resolve) =>
              requestAnimationFrame(() => requestAnimationFrame(resolve)),
            );
          });
          const nav = page.getByRole("navigation", {
            name: "Main navigation",
            includeHidden: true,
          });
          if (!(await nav.isVisible())) {
            await page.locator(".nav-toggle").click();
          }
          await expect(nav).toBeVisible();
          await nav.focus();
          await page.keyboard.press("End");
          await page.locator(".sidebar-scroll").hover();
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
        });
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
