import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";
const backend = path.resolve(process.cwd(), "../backend");
function pdf(settings: Record<string, unknown>) {
  return execFileSync(
    process.platform === "win32"
      ? path.join(backend, ".venv/Scripts/python.exe")
      : path.join(backend, ".venv/bin/python"),
    [
      "-c",
      "from scripts.generate_samples import invoice_pdf;import json,sys;sys.stdout.buffer.write(invoice_pdf(**json.loads(sys.argv[1])))",
      JSON.stringify(settings),
    ],
    { cwd: backend },
  );
}
async function upload(page: Page, settings: Record<string, unknown>) {
  await page.goto("/process");
  await page
    .getByRole("button", { name: "+ New invoice", exact: true })
    .click();
  await page.getByLabel("Invoice PDF", { exact: true }).setInputFiles({
    name: "brand-new-document.pdf",
    mimeType: "application/pdf",
    buffer: pdf(settings),
  });
  const accepted = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/documents") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Upload and process", exact: true })
    .click();
  const receipt = await (await accepted).json();
  await expect(page.getByTestId("run-id")).toHaveText(receipt.run_id, {
    timeout: 15000,
  });
}
test("reviewer corrects a fresh missing identifier and sees persisted revalidation and audit", async ({
  page,
}, info) => {
  test.setTimeout(90000);
  await upload(page, {
    number: "UI-REVIEW-001",
    missing: true,
    quantity: "3",
    subtotal: "60",
    tax: "6",
    total: "66",
  });
  await expect(
    page.getByRole("heading", { name: "Needs review", exact: true }),
  ).toBeVisible({ timeout: 30000 });
  const original = await page.getByTestId("run-id").textContent();
  await page
    .getByRole("link", { name: "Open in Exception review", exact: true })
    .click();
  await page.setViewportSize({ width: 1920, height: 1080 });
  await expect(
    page
      .getByRole("complementary", { name: "Review source document" })
      .getByText("Page 1 of 1", { exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("complementary", { name: "Review source document" })
      .locator(".document-canvas"),
  ).toHaveAttribute("aria-busy", "false");
  await page.screenshot({
    path: info.outputPath("review-workbench-1920.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page
    .getByRole("textbox", { name: "Correct invoice number", exact: true })
    .fill("UI-REVIEW-001");
  await page
    .getByRole("textbox", { name: "Reviewer comment", exact: true })
    .fill(
      "Invoice number confirmed against the synthetic vendor source record.",
    );
  await page.getByRole("checkbox", { name: /I checked this revision/ }).check();
  await page
    .getByRole("button", {
      name: "Save correction and revalidate",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("heading", { name: "Validated", exact: true }),
  ).toBeVisible({ timeout: 30000 });
  const revised = await page.getByTestId("run-id").textContent();
  expect(revised).not.toBe(original);
  await expect(page.locator(".operational-events")).toContainText(
    "Human correction loaded",
  );
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Validated", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await page
    .getByRole("link", { name: "Activity history", exact: true })
    .click();
  await expect(
    page.getByText("Invoice details corrected", { exact: true }).first(),
  ).toBeVisible();
  await page.goto("/runs/" + original);
  await expect(
    page.getByRole("heading", { name: "Needs review", exact: true }),
  ).toBeVisible();
});
test("partial invoices enforce cumulative balance and all operational pages load", async ({
  page,
}) => {
  test.setTimeout(90000);
  const common = {
    vendor_name: "Harbor IT Services (Synthetic)",
    vendor_code: "SYN-002",
    vendor_tax_id: "SYNTHETIC-TAX-2",
    po: "PO-2026-002",
    sku: "IT-SUPPORT",
    unit_price: "500",
    tax_rate: "0",
    tax: "0",
  };
  for (const [number, quantity, total, outcome] of [
    ["UI-PART-1", "2", "1000", "Validated"],
    ["UI-PART-2", "3", "1500", "Validated"],
    ["UI-PART-3", "8", "4000", "Blocked"],
  ]) {
    await upload(page, { ...common, number, quantity, subtotal: total, total });
    await expect(
      page.getByRole("heading", { name: outcome, exact: true }),
    ).toBeVisible({ timeout: 30000 });
  }
  await page
    .getByRole("tab", { name: "Financial checks", exact: true })
    .click();
  await expect(page.locator(".rules")).toContainText("remaining USD 3500");
  await page
    .getByRole("link", { name: "Purchase orders", exact: true })
    .click();
  const row = page.getByRole("row").filter({ hasText: "PO-2026-002" });
  await expect(row.getByRole("cell").nth(2)).toHaveText("USD 2,500.00");
  await expect(row.getByRole("cell").nth(3)).toHaveText("USD 3,500.00");
  await page.getByRole("button", { name: "PO-2026-002", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Commitment history", exact: true }),
  ).toBeVisible();
  await page.reload();
  await page
    .getByRole("button", { name: "Close purchase order details", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Every order. Within budget.",
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Your invoices. Under control.",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /^Unique invoices/ }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Exception review", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Resolve uncertainty with evidence.",
      exact: true,
    }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
});
