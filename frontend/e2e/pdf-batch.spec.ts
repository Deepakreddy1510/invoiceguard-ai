import { test, expect } from "@playwright/test";

// UI protocol test with controlled HTTP responses; not a live-provider acceptance claim.
test("multi-PDF queue waits for actual results, survives partial rejection and restores accepted history after refresh", async ({
  page,
}) => {
  let accepted = 0;
  let holdProcessing = false;
  const records: Record<string, unknown>[] = [];
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = {};
    let status = 200;
    if (path.endsWith("/config"))
      data = { auth_mode: "local", app_environment: "local" };
    else if (path.includes("/workspaces"))
      data = {
        subject: "browser-test",
        default_workspace_id: "test-workspace",
        workspaces: [
          {
            id: "test-workspace",
            name: "Isolated browser fixture",
            kind: "MY",
            role: "ADMIN",
            version: 1,
          },
        ],
      };
    else if (path.endsWith("/me"))
      data = {
        workspace_name: "Isolated browser fixture",
        role: "ADMIN",
        vendor_count: 1,
        po_count: 1,
        can_select_extraction_mode: false,
      };
    else if (path.endsWith("/documents")) {
      // The first file is rejected; subsequent PDFs are accepted through the same API.
      accepted++;
      if (accepted === 1) {
        status = 422;
        data = { detail: "PDF checking could not finish. Try again." };
      } else {
        const id = `batch-${accepted}`;
        records.push({
          id,
          document_id: id,
          status: holdProcessing ? "RUNNING" : "SUCCEEDED",
          outcome: holdProcessing
            ? null
            : accepted === 2
              ? "VALIDATED"
              : "BLOCKED",
          created_at: new Date().toISOString(),
          finished_at: new Date().toISOString(),
          invoice_number: id,
          vendor_name: "Synthetic supplier",
          events: [],
          pages: null,
          extraction: null,
          decision: null,
        });
        data = { run_id: id, replayed: false };
      }
    } else if (path.endsWith("/runs")) data = { runs: records };
    else if (path.includes("/runs/"))
      data = records.find((r) => r.id === path.split("/").pop()) ?? {};
    else if (path.endsWith("/content")) {
      await route.fulfill({ status: 404, body: "" });
      return;
    }
    await route.fulfill({ status, json: data });
  });
  await page.goto("/process");
  await page.getByRole("button", { name: "+ New invoice" }).click();
  await page.getByLabel("Invoice PDF", { exact: true }).setInputFiles(
    [1, 2, 3].map((n) => ({
      name: `${n}.pdf`,
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-synthetic"),
    })),
  );
  const queue = page.getByRole("region", { name: "PDF upload queue" });
  await expect(queue.getByRole("listitem")).toHaveCount(3);
  await page.getByRole("button", { name: "Remove 3.pdf" }).click();
  await page.getByRole("button", { name: "Upload and process all" }).click();
  await expect(queue).toContainText("Completed · VALIDATED");
  await expect(queue).toContainText("PDF checking could not finish");
  expect(accepted).toBe(2);
  await page.getByRole("button", { name: "Retry 1.pdf" }).click();
  await expect(queue).toContainText("Completed · BLOCKED");
  expect(accepted).toBe(3);
  await page.getByRole("button", { name: "Start a new batch" }).click();
  holdProcessing = true;
  await page.getByLabel("Invoice PDF", { exact: true }).setInputFiles(
    [4, 5].map((n) => ({
      name: `${n}.pdf`,
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-synthetic"),
    })),
  );
  await page.getByRole("button", { name: "Upload and process all" }).click();
  await expect(queue.getByRole("listitem").first()).toContainText("Processing");
  expect(accepted).toBe(4);
  await page.reload();
  await expect(
    page.getByRole("button", { name: /^batch-4 Synthetic supplier/ }),
  ).toBeVisible();
  expect(accepted).toBe(4);
});
