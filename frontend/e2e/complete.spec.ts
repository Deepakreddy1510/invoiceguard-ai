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
}) => {
  await upload(page, {
    number: "UI-REVIEW-001",
    missing: true,
    quantity: "3",
    subtotal: "60",
    tax: "6",
    total: "66",
  });
  await expect(
    page.getByRole("heading", { name: "Needs Review", exact: true }),
  ).toBeVisible({ timeout: 30000 });
  const original = await page.getByTestId("run-id").textContent();
  await page
    .getByRole("link", { name: "Open in Exception review", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "Correct invoice_number", exact: true })
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
  await expect(page.locator(".timeline")).toContainText(
    "Human correction loaded",
  );
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Validated", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Audit history", exact: true }).click();
  await expect(
    page.getByText("Correction Saved", { exact: true }).first(),
  ).toBeVisible();
  await page.goto("/runs/" + original);
  await expect(
    page.getByRole("heading", { name: "Needs Review", exact: true }),
  ).toBeVisible();
});
test("partial invoices enforce cumulative balance and all operational pages load", async ({
  page,
}) => {
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
  await expect(
    page.getByRole("heading", {
      name: "Authorized. Reserved. Available.",
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Every invoice, accounted for.",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("Unique invoices", { exact: true }),
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
