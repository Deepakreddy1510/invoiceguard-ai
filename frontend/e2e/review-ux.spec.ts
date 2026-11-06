import { test, expect, chromium } from "@playwright/test";
import { captureNativeWindow } from "./native-zoom";
import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

type Fixture = Record<
  "one" | "multiple" | "empty",
  {
    workspace_id: string;
    records: { task_id: string; run_id: string; number: string }[];
  }
>;
function fixtures(): Fixture {
  if (process.env.REVIEW_QA_FIXTURE_PATH)
    return JSON.parse(
      fs.readFileSync(process.env.REVIEW_QA_FIXTURE_PATH, "utf8"),
    );
  const backend = path.resolve(process.cwd(), "../backend");
  return JSON.parse(
    execFileSync(
      path.join(
        backend,
        process.platform === "win32"
          ? ".venv/Scripts/python.exe"
          : ".venv/bin/python",
      ),
      ["-m", "tests.browser_review_fixture"],
      { cwd: backend, encoding: "utf8", timeout: 45000 },
    ),
  );
}

test("real review selection, evidence, correction, queue identity, empty/error/loading and responsive layout", async ({
  page,
  request,
}, info) => {
  test.setTimeout(150000);
  page.setDefaultTimeout(10000);
  const f = fixtures();
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/reviews");
  async function workspace(id: string) {
    await page.getByLabel("Workspace", { exact: true }).selectOption(id);
    await page
      .getByRole("link", { name: "Exception review", exact: true })
      .click();
  }
  const detail = page.getByRole("region", {
    name: "Scrollable review details",
    exact: true,
  });
  const queue = page.getByRole("region", {
    name: "Scrollable exception queue",
    exact: true,
  });
  const source = page.getByRole("complementary", {
    name: "Review source document",
    exact: true,
  });
  const screenshot = async (name: string) =>
    page.screenshot({ path: info.outputPath(name + ".png"), fullPage: true });
  await workspace(f.one.workspace_id);
  await expect(page).toHaveURL(new RegExp(f.one.records[0].task_id));
  await expect(
    detail.getByRole("heading", { name: /RC-261111/ }),
  ).toBeVisible();
  await expect(queue.locator(".review-queue-row")).toHaveCount(1);
  await expect(source.getByText("Page 1 of 1", { exact: true })).toBeVisible();
  await expect(source.locator(".document-canvas")).toHaveAttribute(
    "aria-busy",
    "false",
  );
  await screenshot("review-one-source-correction-1920");
  await workspace(f.multiple.workspace_id);
  await expect(queue.locator(".review-queue-row")).toHaveCount(3);
  const long = f.multiple.records[1];
  await queue.getByRole("link", { name: new RegExp(long.number) }).focus();
  await page.keyboard.press("Enter");
  await expect(
    detail.getByRole("heading", { name: new RegExp(long.number) }),
  ).toBeVisible();
  await expect(detail).toBeFocused();
  await expect(queue.locator(".selected")).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(queue.getByText(long.number, { exact: true })).toHaveAttribute(
    "title",
    long.number,
  );
  await detail
    .getByLabel("Correct invoice number", { exact: true })
    .fill(long.number + "-DRAFT");
  await page.getByRole("tab", { name: "History", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Review history", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("tab", { name: "Review & correct", exact: true })
    .click();
  await expect(
    detail.getByLabel("Correct invoice number", { exact: true }),
  ).toHaveValue(long.number + "-DRAFT");
  await expect(
    detail.getByRole("button", {
      name: "Save correction and revalidate",
      exact: true,
    }),
  ).toBeDisabled();
  // Wait for a real poll rather than manufacturing a run event; unsaved edits and selection must survive it.
  await page.waitForResponse(
    (r) => r.url().endsWith("/reviews/" + long.task_id) && r.ok(),
  );
  await expect(page).toHaveURL(new RegExp(long.task_id));
  await expect(
    detail.getByLabel("Correct invoice number", { exact: true }),
  ).toHaveValue(long.number + "-DRAFT");
  const real = await (
    await request.get("/api/v1/reviews/" + long.task_id, {
      headers: { "X-Workspace-ID": f.multiple.workspace_id },
    })
  ).json();
  expect(real.run.invoice_number).toBe(long.number);
  await expect(queue.getByText("EUR 44.00", { exact: true })).toBeVisible();
  await page
    .getByRole("switch", { name: "Include resolved reviews", exact: true })
    .check();
  await expect(queue.locator(".review-queue-row")).toHaveCount(4);
  await queue.getByRole("link", { name: /RESOLVED-REVIEW-004/ }).click();
  await expect(detail.getByText("Resolved", { exact: true })).toBeVisible();
  await expect(
    detail.getByRole("button", {
      name: "Save correction and revalidate",
      exact: true,
    }),
  ).toBeDisabled();
  await screenshot("review-resolved-included");
  await queue.getByRole("link", { name: new RegExp(long.number) }).click();
  await page
    .getByRole("switch", { name: "Include resolved reviews", exact: true })
    .uncheck();
  await page
    .getByLabel("Search exception queue", { exact: true })
    .fill("EMAIL-ONLY");
  await expect(queue.locator(".review-queue-row")).toHaveCount(1);
  await page.getByLabel("Search exception queue", { exact: true }).fill("");
  await expect(queue.locator(".review-queue-row")).toHaveCount(3);
  for (const width of [1920, 1440, 1280, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page
      .getByRole("tab", { name: "Review & correct", exact: true })
      .click();
    await expect(
      detail.getByRole("heading", { name: new RegExp(long.number) }),
    ).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    if (width > 650) {
      expect((await queue.boundingBox())!.width).toBeGreaterThanOrEqual(240);
      const q = await page.locator(".review-queue").boundingBox(),
        d = await page.locator(".review-detail").boundingBox();
      expect(d!.x).toBeGreaterThan(q!.x + q!.width - 1);
      if (width >= 1600) {
        const s = await source.boundingBox();
        expect(s!.x).toBeGreaterThan(d!.x + d!.width - 1);
      }
    }
    await screenshot("review-selected-" + width);
    if (width < 1600) {
      await page.getByRole("tab", { name: "Document", exact: true }).click();
      await expect(
        page.getByRole("tabpanel").getByText("Page 1 of 1", { exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("tabpanel").locator(".document-canvas"),
      ).toHaveAttribute("aria-busy", "false");
      await screenshot("review-document-" + width);
    }
    if (width === 390) {
      await page
        .getByRole("button", { name: "Back to exception queue", exact: false })
        .click();
      await expect(queue).toBeVisible();
      await screenshot("review-mobile-list");
      await queue.getByRole("link", { name: new RegExp(long.number) }).click();
      await expect(detail).toBeVisible();
    }
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page
    .getByRole("tab", { name: "Review & correct", exact: true })
    .click();
  const scan = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(
    scan.violations.map((v) => ({
      id: v.id,
      nodes: v.nodes.map((n) => n.target),
    })),
  ).toEqual([]);
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(page.locator(".attention-invoice-row")).toHaveCount(3);
  const attention = page
    .locator(".attention-invoice-row")
    .filter({ hasText: long.number });
  await expect(attention.locator(".invoice-document-mark")).toBeVisible();
  await expect(
    attention.getByText("Needs review", { exact: true }),
  ).toBeVisible();
  for (const width of [1920, 1440, 1280, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    const id = await attention.locator(".invoice-identifier").boundingBox(),
      badge = await attention.locator(".status").boundingBox();
    expect(id!.x + id!.width).toBeLessThanOrEqual(badge!.x);
    await screenshot("overview-attention-" + width);
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await workspace(f.empty.workspace_id);
  await expect(
    page.getByText("No open exceptions", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Exception details", exact: true }),
  ).toHaveCount(0);
  await screenshot("review-empty");
  await workspace(f.multiple.workspace_id);
  await page.goto("/reviews/00000000-0000-0000-0000-000000000099");
  await expect(
    page.getByText("This review could not be opened", { exact: true }),
  ).toBeVisible();
  await screenshot("review-not-found");
  // Hold a real response to verify a truthful loading skeleton, then release it unchanged.
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/v1/reviews/" + long.task_id, async (route) => {
    await gate;
    await route.continue();
  });
  await page.goto("/reviews/" + long.task_id);
  await expect(
    page.getByRole("status", {
      name: "Loading review and evidence",
      exact: true,
    }),
  ).toBeVisible();
  await screenshot("review-loading");
  release();
  await page.unrouteAll({ behavior: "wait" });
  await expect(
    detail.getByRole("heading", { name: new RegExp(long.number) }),
  ).toBeVisible();
});

test("selected real review remains usable at native browser zoom 80 through 200 percent", async ({
  baseURL,
}, info) => {
  test.setTimeout(60000);
  const f = fixtures();
  const context = await chromium.launchPersistentContext("", {
    headless: true,
    executablePath:
      process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ||
      chromium.executablePath(),
    viewport: null,
    args: ["--window-size=1440,1000"],
  });
  try {
    const page = context.pages()[0],
      settings = await context.newPage();
    await page.goto(baseURL! + "/reviews");
    await page
      .getByLabel("Workspace", { exact: true })
      .selectOption(f.one.workspace_id);
    await page
      .getByRole("link", { name: "Exception review", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: /RC-261111/ }),
    ).toBeVisible();
    await settings.goto("chrome://settings/appearance");
    for (const zoom of [0.8, 1, 1.25, 1.5, 2]) {
      await settings.evaluate(`chrome.settingsPrivate.setDefaultZoom(${zoom})`);
      await expect
        .poll(() => page.evaluate(() => devicePixelRatio))
        .toBeCloseTo(zoom);
      expect(await page.evaluate(() => innerWidth)).toBeLessThan(1500 / zoom);
      expect(await page.evaluate(() => innerWidth)).toBeGreaterThan(
        1300 / zoom,
      );
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await expect(
        page.getByRole("tab", { name: "Document", exact: true }),
      ).toBeVisible();
      await captureNativeWindow(
        page,
        info.outputPath("selected-review-native-zoom-" + zoom * 100 + ".png"),
      );
      const documentTab = page.getByRole("tab", {
        name: "Document",
        exact: true,
      });
      await documentTab.focus();
      await expect(documentTab).toBeFocused();
      const bounds = await documentTab.boundingBox();
      expect(bounds!.x).toBeGreaterThanOrEqual(0);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(
        await page.evaluate(() => innerWidth),
      );
    }
  } finally {
    await context.close();
  }
});
