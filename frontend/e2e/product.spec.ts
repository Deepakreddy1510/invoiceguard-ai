import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";
const backend = path.resolve(process.cwd(), "../backend");
const python = path.join(
  backend,
  process.platform === "win32"
    ? ".venv/Scripts/python.exe"
    : ".venv/bin/python",
);
function pdf(
  number: string,
  quantity: string,
  net: string,
  tax: string,
  total: string,
) {
  return execFileSync(
    python,
    [
      "-c",
      "import sys,json; from scripts.generate_samples import invoice_pdf; sys.stdout.buffer.write(invoice_pdf(**json.loads(sys.argv[1])))",
      JSON.stringify({
        number,
        quantity,
        subtotal: net,
        tax,
        total,
        vendor_name: "Browser Supplier (Synthetic)",
        vendor_code: "BROWSER-OWN",
        vendor_tax_id: "SYNTHETIC-BROWSER-OWN",
        po: "BROWSER-PO",
      }),
    ],
    { cwd: backend },
  );
}
async function upload(
  page: Page,
  number: string,
  quantity: string,
  net: string,
  tax: string,
  total: string,
  outcome: string,
) {
  await page
    .getByRole("link", { name: "Invoice processing", exact: true })
    .click();
  await page
    .getByLabel("Extraction mode", { exact: true })
    .selectOption("FALLBACK");
  await page.getByLabel("Invoice PDF", { exact: true }).setInputFiles({
    name: number + ".pdf",
    mimeType: "application/pdf",
    buffer: pdf(number, quantity, net, tax, total),
  });
  const accepted = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/documents") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Upload and process", exact: true })
    .click();
  const receipt = await (await accepted).json();
  await expect(page.getByTestId("run-id")).toHaveText(receipt.run_id);
  await expect(
    page.getByRole("heading", { name: outcome, exact: true }),
  ).toBeVisible({ timeout: 20000 });
  await expect(page.locator(".timeline")).toContainText("Record decision");
  return receipt.run_id as string;
}
test("private workspace procurement, actual PDFs, commitments and retained history", async ({
  page,
}) => {
  test.setTimeout(60000);
  await page.goto("/");
  await page
    .getByLabel("Workspace", { exact: true })
    .selectOption({ label: "My Workspace" });
  await expect(
    page.getByText(
      "Start by adding a vendor and creating a purchase order. Then upload your first invoice.",
    ),
  ).toBeVisible();
  await page.getByRole("link", { name: "Vendors", exact: true }).click();
  await expect(page.getByText("No vendors in this view")).toBeVisible();
  await page
    .getByRole("button", { name: "Create Vendor", exact: true })
    .click();
  await page
    .getByLabel("Legal vendor name", { exact: true })
    .fill("Browser Supplier (Synthetic)");
  await page.getByLabel("Vendor code", { exact: true }).fill("BROWSER-OWN");
  await page
    .getByLabel("Tax identifier", { exact: true })
    .fill("SYNTHETIC-BROWSER-OWN");
  await page.getByRole("button", { name: "Save vendor", exact: true }).click();
  await expect(
    page.getByText("Vendor created. You can now create its purchase order."),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Purchase orders", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Create Purchase Order", exact: true })
    .click();
  await page.getByLabel("PO number", { exact: true }).fill("BROWSER-PO");
  await page.getByLabel("PO vendor", { exact: true }).selectOption({
    label: "BROWSER-OWN · Browser Supplier (Synthetic) · APPROVED",
  });
  await page.getByLabel("PO issue date", { exact: true }).fill("2026-01-01");
  await page.getByLabel("PO valid until", { exact: true }).fill("2026-12-31");
  await page.getByLabel("PO item 1 sku", { exact: true }).fill("PAPER-A4");
  await page
    .getByLabel("PO item 1 description", { exact: true })
    .fill("Synthetic paper");
  await page.getByLabel("PO item 1 quantity", { exact: true }).fill("10");
  await page.getByLabel("PO item 1 unit_price", { exact: true }).fill("20");
  await page.getByLabel("PO item 1 tax_rate", { exact: true }).fill("0.10");
  await page
    .getByRole("button", { name: "Use calculated gross", exact: true })
    .click();
  await expect(
    page.getByLabel("Authorized gross", { exact: true }),
  ).toHaveValue("220.00");
  await page
    .getByRole("button", { name: "Save purchase order", exact: true })
    .click();
  await expect(page.getByText("Purchase order saved.")).toBeVisible();
  // Editing a persisted PO uses database decimal strings and excludes read-only line metadata.
  await page
    .getByRole("button", { name: "Edit Purchase Order", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Save purchase order", exact: true })
    .click();
  await expect(page.getByText("Purchase order saved.")).toBeVisible();
  const valid = await upload(
    page,
    "BROWSER-VALID",
    "3",
    "60",
    "6",
    "66",
    "Validated",
  );
  await expect(page.locator(".rules")).toContainText("PO_BALANCE");
  await expect(page.locator(".evidence-table")).toContainText("Page 1");
  await page
    .getByRole("link", { name: "Purchase orders", exact: true })
    .click();
  const row = page.getByRole("row").filter({ hasText: "BROWSER-PO" }).first();
  await expect(row.getByRole("cell").nth(2)).toHaveText("USD 66.00");
  await expect(row.getByRole("cell").nth(3)).toHaveText("USD 154.00");
  const blocked = await upload(
    page,
    "BROWSER-OVER",
    "8",
    "160",
    "16",
    "176",
    "Blocked",
  );
  await expect(page.locator(".rules")).toContainText("PO_BALANCE");
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "BROWSER-VALID", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "BROWSER-OVER", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Audit history", exact: true }).click();
  await expect(
    page.locator(`a[href="/runs/${blocked}"]`).first(),
  ).toBeVisible();
  await page
    .getByLabel("Workspace", { exact: true })
    .selectOption({ label: "Demo Workspace" });
  await page.getByRole("link", { name: "Vendors", exact: true }).click();
  await expect(page.getByText("SYN-001", { exact: true })).toBeVisible();
  await expect(page.getByText("BROWSER-OWN", { exact: true })).toHaveCount(0);
  await page
    .getByLabel("Workspace", { exact: true })
    .selectOption({ label: "My Workspace" });
  await page.reload();
  await expect(
    page.getByLabel("Workspace", { exact: true }).locator("option:checked"),
  ).toHaveText("My Workspace");
  await expect(
    page.getByRole("link", { name: "BROWSER-VALID", exact: true }),
  ).toBeVisible();
  await page.goto("/runs/" + valid);
  await expect(
    page.getByRole("heading", { name: "Validated", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Vendors", exact: true }).click();
  await page.getByText("Import vendors from CSV", { exact: true }).click();
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download CSV template", exact: true })
    .click();
  expect((await download).suggestedFilename()).toBe("vendors-template.csv");
  await page.getByLabel("Import vendors CSV", { exact: true }).setInputFiles({
    name: "synthetic.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "legal_name,code,tax_id,status\nCSV Browser Supplier (Synthetic),BROWSER-CSV,SYNTHETIC-BROWSER-CSV,APPROVED\n",
    ),
  });
  await page
    .getByRole("button", { name: "Validate preview", exact: true })
    .click();
  await expect(
    page.getByText("1 rows · 1 records · Ready to import", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Commit import", exact: true })
    .click();
  await expect(
    page.getByText("1 records imported transactionally.", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("BROWSER-CSV", { exact: true })).toBeVisible();
});
