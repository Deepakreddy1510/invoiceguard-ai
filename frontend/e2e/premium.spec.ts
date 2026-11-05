import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("workspace rename, archive and restore persist without changing order balances", async ({
  page,
  request,
}) => {
  await page.goto("/settings");
  const before = await (await request.get("/api/v1/purchase-orders")).json();
  let card = page
    .locator(".workspace-card")
    .filter({ hasText: "My Workspace" });
  await card.getByRole("button", { name: "Rename", exact: true }).click();
  await page.getByLabel("Workspace name").fill("Clarity Finance");
  await page.getByRole("button", { name: "Save name", exact: true }).click();
  await expect(
    page
      .getByLabel("Workspace", { exact: true })
      .locator("option")
      .filter({ hasText: "Clarity Finance" }),
  ).toHaveCount(1);
  card = page.locator(".workspace-card").filter({ hasText: "Clarity Finance" });
  await card.getByRole("button", { name: "Archive", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "Archive workspace?" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Archive workspace", exact: true })
    .click();
  await expect(card.getByText("Archived", { exact: true })).toBeVisible();
  await expect(
    page
      .getByLabel("Workspace", { exact: true })
      .locator("option")
      .filter({ hasText: "Clarity Finance" }),
  ).toHaveCount(0);
  await page.reload();
  await expect(card.getByText("Archived", { exact: true })).toBeVisible();
  await card.getByRole("button", { name: "Restore", exact: true }).click();
  await page
    .getByRole("button", { name: "Restore workspace", exact: true })
    .click();
  await expect(
    card.getByRole("button", { name: "Archive", exact: true }),
  ).toBeVisible();
  await card.getByRole("button", { name: "Rename", exact: true }).click();
  await page.getByLabel("Workspace name").fill("My Workspace");
  await page.getByRole("button", { name: "Save name", exact: true }).click();
  await expect(
    page.locator(".workspace-card").filter({ hasText: "My Workspace" }),
  ).toBeVisible();
  const after = await (await request.get("/api/v1/purchase-orders")).json();
  expect(after).toEqual(before);
});

test("all customer pages reflow at required widths and zoom without overflow or unsupported branding", async ({
  page,
}, info) => {
  test.setTimeout(120000);
  const widths = [1920, 1440, 1280, 1024, 768, 390];
  const routes = [
    "/",
    "/process",
    "/email-intake",
    "/vendors",
    "/purchase-orders",
    "/reviews",
    "/settings",
    "/audit",
  ];
  for (const width of widths) {
    await page.setViewportSize({ width, height: 1000 });
    for (const route of routes) {
      await page.goto(route);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await expect(page.getByRole("status", { name: /Loading/ })).toHaveCount(
        0,
        { timeout: 10000 },
      );
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
        `${route} at ${width}`,
      ).toBeLessThanOrEqual(width);
      await expect(page.locator("body")).not.toContainText("[object Object]");
      await expect(page.locator(".environment-tag")).toHaveCount(0);
      expect(
        await page
          .locator(".rules li")
          .evaluateAll((nodes) => nodes.some((n) => !n.textContent?.trim())),
      ).toBe(false);
      await page.screenshot({
        path: info.outputPath(
          `${route.replaceAll("/", "") || "overview"}-${width}.png`,
        ),
        fullPage: true,
      });
    }
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/");
  await page.evaluate(() => {
    document.documentElement.style.zoom = "1.5";
  });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(1280);
  await page.screenshot({
    path: info.outputPath("overview-150-percent-zoom.png"),
    fullPage: true,
  });
  await page.evaluate(() => {
    document.documentElement.style.zoom = "";
  });
  for (const route of routes) {
    await page.goto(route);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("status", { name: /Loading/ })).toHaveCount(0);
    const scan = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(
      scan.violations.map((v) => ({
        id: v.id,
        nodes: v.nodes.map((n) => n.target),
      })),
      route,
    ).toEqual([]);
  }
});
