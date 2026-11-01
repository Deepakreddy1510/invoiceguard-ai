import { test, expect, type Page } from "@playwright/test";
import path from "node:path";

const fixtures = path.resolve(process.cwd(), "../samples/invoices");
async function upload(page: Page, file: string) {
  await page.goto("/");
  await page
    .getByRole("link", { name: "Invoice processing", exact: true })
    .click();
  await page
    .getByLabel("Invoice PDF", { exact: true })
    .setInputFiles(path.join(fixtures, file));
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
async function outcome(page: Page, name: string) {
  await expect(
    page.getByRole("heading", {
      name: name
        .split("_")
        .map((word) => word[0] + word.slice(1).toLowerCase())
        .join(" "),
      exact: true,
    }),
  ).toBeVisible({
    timeout: 30000,
  });
}
test.describe
  .serial("real upload, worker, financial result and history", () => {
  test("valid PDF, persisted events, reload and exact replay", async ({
    page,
  }) => {
    await upload(page, "valid.pdf");
    await outcome(page, "VALIDATED");
    const run = await page.getByTestId("run-id").textContent();
    await expect(page.locator(".timeline")).toContainText(
      "Extract invoice fields",
    );
    await expect(page.locator(".timeline")).toContainText("Record decision");
    await expect(
      page.getByText("Payment has not been executed.", { exact: false }),
    ).toBeVisible();
    await page.reload();
    await outcome(page, "VALIDATED");
    await expect(page.getByTestId("run-id")).toHaveText(run!);
    await page
      .getByLabel("Invoice PDF", { exact: true })
      .setInputFiles(path.join(fixtures, "valid.pdf"));
    await page
      .getByRole("button", { name: "Upload and process", exact: true })
      .click();
    await expect(
      page.getByText(
        "Already uploaded — showing the existing processing record.",
      ),
    ).toBeVisible();
    await expect(page.getByTestId("run-id")).toHaveText(run!);
  });
  test("re-exported business duplicate has a blocked assessment", async ({
    page,
  }) => {
    await upload(page, "duplicate-reexported.pdf");
    await outcome(page, "BLOCKED");
    await expect(page.locator(".rules")).toContainText(
      "Confirmed duplicate business invoice.",
    );
  });
  test("missing invoice number routes to review", async ({ page }) => {
    await upload(page, "missing.pdf");
    await outcome(page, "NEEDS_REVIEW");
    await expect(page.locator(".rules")).toContainText(
      "REQUIRED_invoice_number",
    );
  });
  test("scanned PDF executes real OCR", async ({ page }) => {
    await upload(page, "valid-scanned.pdf");
    await outcome(page, "VALIDATED");
    await expect(page.locator(".timeline")).toContainText(
      "OCR executed on pages 1",
    );
    await expect(
      page.locator(".evidence-table").getByText("Page 1 · OCR").first(),
    ).toBeVisible();
  });
  test("corrupt file shows a real upload failure", async ({ page }) => {
    await page.goto("/");
    await page
      .getByRole("link", { name: "Invoice processing", exact: true })
      .click();
    await page.getByLabel("Invoice PDF", { exact: true }).setInputFiles({
      name: "corrupt.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-corrupt"),
    });
    await page
      .getByRole("button", { name: "Upload and process", exact: true })
      .click();
    await expect(page.getByRole("alert")).toContainText("PDF unreadable");
  });
});
