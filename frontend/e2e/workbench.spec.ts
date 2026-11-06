import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";
import path from "node:path";

test("real paginated invoice workbench, private PDF controls, outcomes, tabs and responsive zoom", async ({
  page,
  request,
}, info) => {
  test.setTimeout(150000);
  const backend = path.resolve(process.cwd(), "../backend");
  const python = path.join(
    backend,
    process.platform === "win32"
      ? ".venv/Scripts/python.exe"
      : ".venv/bin/python",
  );
  const fixture = JSON.parse(
    execFileSync(python, ["-m", "tests.browser_workbench_fixture"], {
      cwd: backend,
      encoding: "utf8",
      timeout: 45000,
    }),
  );
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/process");
  await page
    .getByLabel("Workspace", { exact: true })
    .selectOption(fixture.workspace_id);
  await page
    .getByRole("link", { name: "Invoice processing", exact: true })
    .click();
  await expect(page.locator(".history-run")).toHaveCount(20);
  const paged = page.waitForResponse(
    (r) => r.url().includes("/runs?offset=20&limit=20") && r.ok(),
  );
  await page.getByRole("button", { name: "Older", exact: true }).click();
  expect((await (await paged).json()).runs).toHaveLength(7);
  await expect(page.locator(".history-run")).toHaveCount(7);
  await page.locator(".history-run").first().click();
  const selected = await page.getByTestId("run-id").textContent();
  await page.reload();
  await expect(page.getByTestId("run-id")).toHaveText(selected!);
  await expect(
    page.getByRole("heading", { name: "Validated", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("complementary", { name: "Source document panel" }),
  ).toBeVisible();
  const source = page.getByRole("complementary", {
    name: "Source document panel",
  });
  await expect(source.getByText("Page 1 of 2", { exact: true })).toBeVisible();
  await source.getByRole("button", { name: "Next PDF page" }).click();
  await expect(source.getByText("Page 2 of 2", { exact: true })).toBeVisible();
  await source.getByLabel("PDF zoom", { exact: true }).selectOption("1.5");
  await expect(source.locator("canvas")).toHaveAttribute("width", /^[1-9]\d+$/);
  await source.getByRole("button", { name: "Expand PDF" }).click();
  await expect(
    page.getByRole("dialog", { name: "Original invoice PDF", exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page
    .getByRole("tab", { name: "Financial checks", exact: true })
    .click();
  await expect(page.locator(".po-comparison")).toBeVisible();
  await page.getByRole("tab", { name: "Activity", exact: true }).click();
  const actual = await (
    await request.get(`/api/v1/runs/${selected}`, {
      headers: { "X-Workspace-ID": fixture.workspace_id },
    })
  ).json();
  await expect(page.locator(".business-execution > li")).toHaveCount(
    actual.events.length,
  );
  await page
    .getByRole("button", { name: "Collapse navigation", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Expand navigation", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "Workspace", exact: true }),
  ).toHaveValue(fixture.workspace_id);
  await page.screenshot({
    path: info.outputPath("collapsed-navigation.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole("button", { name: "Open navigation", exact: true })
    .click();
  await expect(
    page.getByRole("combobox", { name: "Workspace", exact: true }),
  ).toHaveValue(fixture.workspace_id);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page
    .getByRole("button", { name: "Close navigation", exact: true })
    .click();
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page
    .getByRole("button", { name: "Expand navigation", exact: true })
    .click();
  await page.getByRole("tab", { name: "Overview", exact: true }).click();
  const denied = await request.get(
    `/api/v1/documents/${actual.document_id}/content`,
    { headers: { "X-Workspace-ID": "00000000-0000-0000-0000-000000000001" } },
  );
  expect(denied.status()).toBe(404);
  for (const [index, outcome] of [
    [24, "VALIDATED"],
    [25, "BLOCKED"],
    [26, "NEEDS_REVIEW"],
  ] as const) {
    const record = fixture.records[index];
    await page.goto(`/runs/${record.id}`);
    await expect(page.getByTestId("run-id")).toHaveText(record.id);
    const detail = await (
      await request.get(`/api/v1/runs/${record.id}`, {
        headers: { "X-Workspace-ID": fixture.workspace_id },
      })
    ).json();
    expect(detail.decision.outcome).toBe(outcome);
    await expect(
      page.getByRole("region", { name: "Financial decision", exact: true }),
    ).toBeVisible();
    await expect(
      page
        .getByRole("complementary", { name: "Source document panel" })
        .getByText("Page 1 of 2", { exact: true }),
    ).toBeVisible();
    await expect(
      page
        .getByRole("complementary", { name: "Source document panel" })
        .locator(".document-canvas"),
    ).toHaveAttribute("aria-busy", "false");
    await page.screenshot({
      path: info.outputPath(`workbench-${outcome.toLowerCase()}-1920.png`),
      fullPage: true,
    });
  }
  for (const width of [1920, 1440, 1280, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.getByRole("tab", { name: "Overview", exact: true }).click();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    await page.screenshot({
      path: info.outputPath(`selected-invoice-${width}.png`),
      fullPage: true,
    });
    if (width < 1600) {
      await page.getByRole("tab", { name: "Document", exact: true }).click();
      await expect(
        page.getByRole("tabpanel").getByText("Page 1 of 2", { exact: true }),
      ).toBeVisible();
      await page.screenshot({
        path: info.outputPath(`source-document-${width}.png`),
        fullPage: true,
      });
    }
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("tab", { name: "Overview", exact: true }).click();
  for (const zoom of [0.8, 1, 1.25, 1.5, 2]) {
    await page.evaluate((z) => {
      document.documentElement.style.zoom = String(z);
    }, zoom);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(1440);
    await expect(
      page.getByRole("button", { name: "+ New invoice", exact: true }),
    ).toBeVisible();

    await page.screenshot({
      path: info.outputPath(`workbench-zoom-${zoom * 100}.png`),
      fullPage: true,
    });
  }
  await page.evaluate(() => {
    document.documentElement.style.zoom = "";
  });
  await page
    .getByRole("button", { name: "+ New invoice", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "New invoice", exact: true }),
  ).toBeVisible();
  expect(
    (await page
      .getByRole("dialog", { name: "New invoice", exact: true })
      .locator(".dropzone")
      .boundingBox())!.width,
  ).toBeGreaterThan(500);
  expect(
    (await page
      .getByRole("dialog", { name: "New invoice", exact: true })
      .locator(".extraction-mode p")
      .boundingBox())!.width,
  ).toBeGreaterThan(500);
  await page.screenshot({
    path: info.outputPath("upload-dialog.png"),
    fullPage: true,
  });
  await page.keyboard.press("Escape");
  await page
    .getByRole("tab", { name: "Financial checks", exact: true })
    .focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "Activity", exact: true }),
  ).toBeFocused();
  const scan = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(
    scan.violations.map((v) => ({
      id: v.id,
      nodes: v.nodes.map((n) => n.target),
    })),
  ).toEqual([]);
  await page
    .getByLabel("Search invoice history", { exact: true })
    .fill("WB-INVOICE-2026-0024");
  await expect(page.locator(".history-run")).toHaveCount(1);
  await page.getByRole("link", { name: "Vendors", exact: true }).click();
  await expect(page.locator("tbody > tr")).toHaveCount(20);
  await page.getByRole("button", { name: "Next page", exact: true }).click();
  await expect(page.locator("tbody > tr")).toHaveCount(5);
  await page
    .getByRole("link", { name: "Purchase orders", exact: true })
    .click();
  await expect(page.locator("tbody > tr")).toHaveCount(20);
  await page.getByRole("button", { name: "Next page", exact: true }).click();
  await expect(page.locator("tbody > tr")).toHaveCount(5);
});
