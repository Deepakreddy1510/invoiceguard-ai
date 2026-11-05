import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";
import path from "node:path";
const backend = path.resolve(process.cwd(), "../backend");
const python =
  process.platform === "win32"
    ? path.join(backend, ".venv/Scripts/python.exe")
    : path.join(backend, ".venv/bin/python");
test("fresh scanned PDF auto-selects, follows persisted events and updates already-open overview and audit", async ({
  page,
  context,
}, testInfo) => {
  // Six real OCR pages need headroom on slower CI hosts; no artificial backend delay.
  test.setTimeout(60000);
  const overview = await context.newPage();
  const audit = await context.newPage();
  await overview.goto("/");
  await audit.goto("/audit");
  await expect(
    overview.getByRole("heading", { name: "Recent processing activity" }),
  ).toBeVisible();
  // The suite owns a fresh database; keep the exact OCR assertion deterministic.
  // Random mixed letter/digit IDs introduce OCR errors unrelated to UI behavior.
  const number = "UI-EDITORIAL-FRESH";
  const pdf = execFileSync(
    python,
    [
      "-c",
      `import sys,json,pymupdf
from scripts.generate_samples import invoice_pdf
pdf=pymupdf.open(stream=invoice_pdf(**json.loads(sys.argv[1])),filetype="pdf")
for index in range(5):
    supporting=pymupdf.open()
    page=supporting.new_page()
    page.insert_text((45,70), "SYNTHETIC SUPPORTING RECORD / DEMONSTRATION ONLY",fontsize=12)
    page.insert_textbox(pymupdf.Rect(45,100,540,700), ("Paper cartons were delivered with the packing references held by the synthetic supplier. This supporting page adds no line items or monetary values. Packaging and delivery records are retained for source review. " * 14),fontsize=11)
    image=page.get_pixmap(matrix=pymupdf.Matrix(2,2)).tobytes("png")
    extra=pdf.new_page()
    extra.insert_image(extra.rect,stream=image)
    supporting.close()
sys.stdout.buffer.write(pdf.tobytes(garbage=4,deflate=True))`,
      JSON.stringify({
        number,
        scanned: true,
        quantity: "7",
        subtotal: "140",
        tax: "14",
        total: "154",
      }),
    ],
    { cwd: backend, maxBuffer: 12 * 1024 * 1024 },
  );
  const snapshots: { id: string; status: string; events: number }[] = [];
  page.on("response", async (response) => {
    if (/\/api\/v1\/runs\/[^/?]+$/.test(response.url()) && response.ok()) {
      const data = await response.json();
      snapshots.push({
        id: data.id,
        status: data.status,
        events: data.events.length,
      });
    }
  });
  await page.goto("/process");
  await page.getByLabel("Invoice PDF", { exact: true }).setInputFiles({
    name: "new-independent-document.pdf",
    mimeType: "application/pdf",
    buffer: pdf,
  });
  const accepted = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/documents") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Upload and process", exact: true })
    .click();
  const receipt = await (await accepted).json();
  await expect(page.getByTestId("run-id")).toHaveText(receipt.run_id, {
    timeout: 15000,
  });
  await expect(
    page.getByRole("heading", { name: "Validated", exact: true }),
  ).toBeVisible({ timeout: 45000 });
  await expect(page.locator('[data-stage="ocr"]')).toHaveAttribute(
    "data-state",
    "SUCCEEDED",
  );
  await page.locator('[data-stage="ocr"] summary').click();
  await expect(page.locator('[data-stage="ocr"]')).toContainText(
    "OCR executed on pages 1",
  );
  expect(
    snapshots.some(
      (s) =>
        s.id === receipt.run_id && ["QUEUED", "RUNNING"].includes(s.status),
    ),
  ).toBeTruthy();
  expect(
    snapshots.some(
      (s) =>
        s.id === receipt.run_id && s.status === "SUCCEEDED" && s.events > 0,
    ),
  ).toBeTruthy();
  await expect(page.locator('.history-run[aria-pressed="true"]')).toContainText(
    number,
  );
  await expect(
    page.getByRole("region", { name: "Financial decision" }),
  ).toContainText("The recorded financial checks passed.");
  await expect(page.locator('[data-stage="validation"] .rules')).toContainText(
    "Available purchase order balance",
  );
  await expect(
    overview.getByRole("link", { name: number, exact: true }),
  ).toBeVisible({ timeout: 12000 });
  await expect(
    audit.locator(`a[href="/runs/${receipt.run_id}"]`).first(),
  ).toBeVisible({ timeout: 12000 });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("process-desktop.png") });
  await overview.screenshot({
    path: testInfo.outputPath("overview-desktop.png"),
  });
  const other = page
    .locator(".history-run")
    .filter({ hasNotText: number })
    .first();
  await other.click();
  await expect(page.getByTestId("run-id")).not.toHaveText(receipt.run_id);
  const selected = await page.getByTestId("run-id").textContent();
  await page.waitForResponse((r) => r.url().includes("/api/v1/runs?"));
  await expect(page.getByTestId("run-id")).toHaveText(selected!);
  await overview.close();
  await audit.close();
});
test("warm screens expose keyboard controls and have no detected WCAG A/AA violations", async ({
  page,
}, testInfo) => {
  for (const route of [
    "/",
    "/purchase-orders",
    "/vendors",
    "/reviews",
    "/audit",
    "/process",
  ]) {
    await page.goto(route);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("status", { name: /Loading/ })).toHaveCount(0, {
      timeout: 10000,
    });
    const scan = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(
      scan.violations.map((v) => ({
        id: v.id,
        description: v.description,
        nodes: v.nodes.map((n) => n.target),
      })),
    ).toEqual([]);
  }
  await page.goto("/purchase-orders");
  await page.getByRole("button", { name: "PO-2026-001", exact: false }).click();
  await expect(
    page.getByRole("heading", { name: "Commitment history" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 1024, height: 900 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(1024);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open navigation" }).focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("link", { name: "Overview", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Open navigation" }),
  ).toHaveAttribute("aria-expanded", "false");
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.screenshot({ path: testInfo.outputPath("overview-mobile.png") });
  await page.setViewportSize({ width: 1440, height: 1000 });
  const cards = page.locator(".metric-grid");
  await cards.getByRole("button", { name: /Blocked/ }).click();
  await expect(
    page
      .getByRole("group", { name: "Filter dashboard outcomes" })
      .getByRole("button", { name: /Blocked/ }),
  ).toHaveAttribute("aria-pressed", "true");
});
