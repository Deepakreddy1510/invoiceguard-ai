import { test, expect, chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { captureNativeWindow } from "./native-zoom";

const backend = path.resolve(process.cwd(), "../backend");

test("customer creates procurement, reads a real PDF, archives and restores without releasing capacity", async ({
  page,
  request,
}, info) => {
  test.setTimeout(120000);
  const response = await request.post("/api/v1/workspaces", {
    data: {
      request_id: crypto.randomUUID(),
      name: "PS1 Customer",
      workspace_type: "EMPTY",
    },
  });
  expect(response.status()).toBe(201);
  const wid = (await response.json()).workspace_id,
    headers = { "X-Workspace-ID": wid };
  await page.goto("/");
  await page.getByLabel("Workspace", { exact: true }).selectOption(wid);
  await page.getByRole("link", { name: "Vendors", exact: true }).click();
  await page
    .getByRole("button", { name: "Create Vendor", exact: true })
    .click();
  await page
    .getByLabel("Legal vendor name", { exact: true })
    .fill("Northstar Office Supplies (Synthetic)");
  await page.getByLabel("Vendor code", { exact: true }).fill("SYN-001");
  await page
    .getByLabel("Tax identifier", { exact: true })
    .fill("SYNTHETIC-TAX-1");
  await page.screenshot({
    path: info.outputPath("supplier-onboarding.png"),
    fullPage: true,
  });
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
  await page.getByLabel("PO number", { exact: true }).fill("PS1-PO");
  await page.getByLabel("PO vendor", { exact: true }).selectOption({
    label: "SYN-001 · Northstar Office Supplies (Synthetic) · APPROVED",
  });
  await page.getByLabel("PO item 1 sku", { exact: true }).fill("PAPER-A4");
  await page
    .getByLabel("PO item 1 description", { exact: true })
    .fill("Paper cartons");
  await page.getByLabel("PO item 1 quantity", { exact: true }).fill("10");
  await page.getByLabel("PO item 1 unit_price", { exact: true }).fill("20");
  await page.getByLabel("PO item 1 tax_rate", { exact: true }).fill("0.10");
  await page
    .getByRole("button", { name: "Use calculated gross", exact: true })
    .click();
  await page
    .getByRole("dialog", { name: "Create purchase order", exact: true })
    .evaluate((el) => (el.scrollTop = 0));
  await page.screenshot({
    path: info.outputPath("purchase-order-guidance.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Save purchase order", exact: true })
    .click();
  await expect(page.getByText("Purchase order saved.")).toBeVisible();
  await page.goto("/process");
  await page
    .getByRole("button", { name: "+ New invoice", exact: true })
    .click();
  await expect(
    page.getByText("Upload an invoice PDF. Scanned invoices are supported."),
  ).toBeVisible();
  const payload = execFileSync(
    path.join(
      backend,
      process.platform === "win32"
        ? ".venv/Scripts/python.exe"
        : ".venv/bin/python",
    ),
    [
      "-c",
      "from scripts.generate_samples import invoice_pdf;import sys;sys.stdout.buffer.write(invoice_pdf(number='PS1-ARCHIVE',po='PS1-PO',quantity='3',subtotal='60',tax='6',total='66'))",
    ],
    { cwd: backend },
  );
  await page.getByLabel("Invoice PDF", { exact: true }).setInputFiles({
    name: "source.pdf",
    mimeType: "application/pdf",
    buffer: payload,
  });
  const accepted = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/documents") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Upload and process", exact: true })
    .click();
  const receipt = await (await accepted).json();
  await expect(
    page.getByRole("heading", { name: "Validated", exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await expect(page.locator(".invoice-identity-strip")).toContainText(
    "Digital PDF text",
  );
  await expect(page.locator(".invoice-identity-strip")).toContainText(
    "Standard",
  );
  await expect(
    page.getByText(/Why standard extraction was used/),
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath("reading-and-financial-decision.png"),
    fullPage: true,
  });
  const before = await (
    await request.get("/api/v1/purchase-orders", { headers })
  ).json();
  await page
    .getByRole("button", { name: "Archive invoice from queue", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Organize invoice queue" }),
  ).toContainText("does not reverse a financial decision");
  await page
    .getByRole("button", { name: "Confirm archive", exact: true })
    .click();
  await expect(
    page.getByText("Archived from queue", { exact: true }),
  ).toBeVisible();
  expect(
    (await (await request.get("/api/v1/runs", { headers })).json()).runs,
  ).toEqual([]);
  await page
    .getByLabel("Queue visibility", { exact: true })
    .selectOption("archived");
  await expect(page.locator(".history-list")).toContainText("PS1-ARCHIVE");
  expect(
    (
      await request.get(
        "/api/v1/documents/" + receipt.document_id + "/content",
        { headers },
      )
    ).status(),
  ).toBe(200);
  const after = await (
    await request.get("/api/v1/purchase-orders", { headers })
  ).json();
  expect(after[0].reserved_gross).toBe(before[0].reserved_gross);
  await page.screenshot({
    path: info.outputPath("archived-invoice.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Restore invoice to queue", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Confirm restore", exact: true })
    .click();
  await expect(
    page.getByText("Archived from queue", { exact: true }),
  ).toHaveCount(0);
  await page
    .getByLabel("Queue visibility", { exact: true })
    .selectOption("active");
  await expect(page.locator(".history-list")).toContainText("PS1-ARCHIVE");
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze())
      .violations,
  ).toEqual([]);
});

test("collapsed workspace controls remain in one desktop header row at native zoom", async ({
  baseURL,
}, info) => {
  test.setTimeout(180000);
  const context = await chromium.launchPersistentContext("", {
    headless: true,
    executablePath:
      process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ||
      chromium.executablePath(),
    viewport: null,
    args: ["--window-size=1920,1080"],
  });
  try {
    const page = context.pages()[0],
      settings = await context.newPage();
    await settings.goto("chrome://settings/appearance");
    for (const zoom of [1, 1.25, 1.5, 2]) {
      await settings.evaluate(`chrome.settingsPrivate.setDefaultZoom(${zoom})`);
      await page.goto(baseURL! + "/");
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await expect
        .poll(() => page.evaluate(() => devicePixelRatio))
        .toBeCloseTo(zoom);
      await page
        .getByRole("button", { name: "Collapse navigation", exact: true })
        .click();
      const top = page.locator(".topbar");
      expect((await top.boundingBox())!.height).toBeLessThanOrEqual(90);
      const picker = top.getByLabel("Workspace", { exact: true }),
        create = top.getByRole("button", {
          name: "Create Workspace",
          exact: true,
        }),
        manage = top
          .locator("summary")
          .filter({ hasText: "Workspace settings" });
      for (const control of [picker, create, manage])
        await expect(control).toBeInViewport();
      const boxes = await Promise.all(
        [picker, create, manage].map((control) => control.boundingBox()),
      );
      expect(
        Math.max(...boxes.map((box) => box!.y)) -
          Math.min(...boxes.map((box) => box!.y)),
      ).toBeLessThan(25);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      expect(
        (
          await new AxeBuilder({ page })
            .include(".topbar")
            .withTags(["wcag2a", "wcag2aa"])
            .analyze()
        ).violations,
      ).toEqual([]);
      await captureNativeWindow(
        page,
        info.outputPath(`collapsed-${zoom * 100}.png`),
      );
      await create.click();
      await expect(
        page.getByRole("dialog", { name: "Create Workspace", exact: true }),
      ).toBeVisible();
      await page.getByRole("button", { name: "Cancel", exact: true }).click();
      await expect(create).toBeFocused();
    }
  } finally {
    await context.close();
  }
});

test("history conflict leads to a named fresh sample and preserves the original email and PDF", async ({
  page,
  request,
}, info) => {
  test.setTimeout(150000);
  const fixture = JSON.parse(
    execFileSync(
      path.join(
        backend,
        process.platform === "win32"
          ? ".venv/Scripts/python.exe"
          : ".venv/bin/python",
      ),
      ["-m", "tests.browser_sample_recovery_fixture"],
      { cwd: backend, encoding: "utf8" },
    ),
  );
  const headers = { "X-Workspace-ID": fixture.workspace_id };
  const original = await (
    await request.get("/api/v1/runs/" + fixture.run_id, { headers })
  ).json();
  await page.goto("/");
  await page
    .getByLabel("Workspace", { exact: true })
    .selectOption(fixture.workspace_id);
  await page
    .getByRole("button", { name: "Initialize sample invoices", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("history");
  await page.screenshot({
    path: info.outputPath("safe-sample-recovery.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Create Fresh Sample Workspace", exact: true })
    .click();
  await expect(page.getByLabel("Workspace type")).toHaveValue("SAMPLE");
  await page
    .getByLabel("Workspace name", { exact: true })
    .fill("Fresh after emailed sample");
  const created = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/workspaces") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Confirm creation", exact: true })
    .click();
  const fresh = (await (await created).json()).workspace_id;
  expect(fresh).not.toBe(fixture.workspace_id);
  await expect(page.getByLabel("Workspace", { exact: true })).toHaveValue(
    fresh,
  );
  await expect
    .poll(
      async () => {
        const state = await (
          await request.get("/api/v1/workspaces/sample-initialization", {
            headers: { "X-Workspace-ID": fresh },
          })
        ).json();
        expect(state.initialization.status).not.toBe("FAILED");
        return state.initialization.status === "COMPLETE"
          ? state.initialization.completed
          : 0;
      },
      { timeout: 100000 },
    )
    .toBe(21);
  const retained = await (
    await request.get("/api/v1/runs/" + fixture.run_id, { headers })
  ).json();
  expect(retained.events).toEqual(original.events);
  expect(retained.decision).toEqual(original.decision);
  expect(
    (
      await request.get(
        "/api/v1/documents/" + fixture.document_id + "/content",
        { headers },
      )
    ).status(),
  ).toBe(200);
  const email = await (await request.get("/api/v1/email", { headers })).json();
  expect(email.connections[0].email).toBe("retained@example.invalid");
  await page.screenshot({
    path: info.outputPath("fresh-sample-ready.png"),
    fullPage: true,
  });
});
