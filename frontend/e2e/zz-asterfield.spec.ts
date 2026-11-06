import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";
test("verified sample company is selectable, preserves legacy procurement and replays an actual PDF", async ({
  page,
  request,
}, info) => {
  test.setTimeout(90000);
  const backend = path.resolve(process.cwd(), "../backend");
  const python = path.join(
    backend,
    process.platform === "win32"
      ? ".venv/Scripts/python.exe"
      : ".venv/bin/python",
  );
  const result = JSON.parse(
    execFileSync(python, ["-m", "scripts.install_asterfield_demo"], {
      cwd: backend,
      timeout: 70000,
      encoding: "utf8",
    }),
  );
  expect(result.documents).toBe(21);
  expect(result.outcomes).toEqual({
    VALIDATED: 14,
    BLOCKED: 6,
    NEEDS_REVIEW: 1,
  });
  await page.goto("/");
  await page
    .getByLabel("Workspace", { exact: true })
    .selectOption(result.workspace_id);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("img", { name: /Validated:/ })).toBeVisible();
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await expect(page.getByRole("status", { name: /Loading/ })).toHaveCount(0);
    expect(
      (
        await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze()
      ).violations,
    ).toEqual([]);
    await page.screenshot({
      path: info.outputPath(`asterfield-overview-${width}.png`),
      fullPage: true,
    });
  }
  await page.setViewportSize({ width: 1280, height: 1000 });
  await page.getByRole("link", { name: "Vendors", exact: true }).click();
  await expect(
    page.getByText("Willowbridge Office Supplies", { exact: true }),
  ).toBeVisible();
  const original = result.results.find(
    (r: { file: string }) => r.file === "01-office-supplies.pdf",
  );
  await page.goto("/process");
  await page
    .getByRole("button", { name: "+ New invoice", exact: true })
    .click();
  await page
    .getByLabel("Invoice PDF", { exact: true })
    .setInputFiles(
      path.join(backend, "demo/asterfield-v1/01-office-supplies.pdf"),
    );
  await page
    .getByLabel("Extraction mode", { exact: true })
    .selectOption("FALLBACK");
  const accepted = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/documents") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Upload and process", exact: true })
    .click();
  const receipt = await (await accepted).json();
  expect(receipt.run_id).toBe(original.run_id);
  await expect(
    page.getByRole("heading", { name: "Validated", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Financial decision" }),
  ).toContainText("Next action");
  await expect(page.locator("body")).not.toContainText("[object Object]");
  await expect(page.locator(".technical-details[open]")).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  const orders = await request.get("/api/v1/purchase-orders", {
    headers: { "X-Workspace-ID": result.workspace_id },
  });
  const rows = await orders.json();
  expect(JSON.stringify(rows)).toContain("AF-PO-2026-003");
});
