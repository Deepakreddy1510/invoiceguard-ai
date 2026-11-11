import { test, expect } from "@playwright/test";

// Controlled HTTP fixtures exercise the actual public-config boot and layout.
test("manual-processing overview has no disabled intake UI or traffic at desktop and mobile sizes", async ({
  page,
}, info) => {
  const emailRequests: string[] = [];
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.startsWith("/api/v1/email")) emailRequests.push(path);
    const run = {
      id: "run-test",
      document_id: "doc-test",
      invoice_number: "INV-REAL-RESULT",
      vendor_name: "Approved Supplier",
      status: "SUCCEEDED",
      outcome: "VALIDATED",
      created_at: "2026-11-11T12:00:00Z",
      finished_at: "2026-11-11T12:00:02Z",
      pages: [],
      events: [],
      extraction: null,
      decision: null,
    };
    const data = path.endsWith("/config")
      ? { auth_mode: "local", enable_email_intake: false }
      : path.includes("/workspaces")
        ? {
            subject: "fixture",
            default_workspace_id: "private",
            workspaces: [
              {
                id: "private",
                name: "My Workspace",
                kind: "MY",
                role: "ADMIN",
                version: 1,
              },
            ],
          }
        : path.endsWith("/me")
          ? {
              workspace_name: "My Workspace",
              workspace_kind: "MY",
              role: "ADMIN",
              vendor_count: 2,
              po_count: 3,
            }
          : path.endsWith("/dashboard")
            ? {
                total_invoices: 6,
                outcomes: { VALIDATED: 3, NEEDS_REVIEW: 2, BLOCKED: 1 },
                recent_runs: [run],
                worker: { available: true, last_seen: null },
                processing_runs: 7,
                failed_runs: 0,
                duplicate_assessments: 1,
              }
            : path.includes("/reviews")
              ? { tasks: [] }
              : path.includes("/audit-events")
                ? { events: [] }
                : path.includes("/runs/")
                  ? run
                  : path.endsWith("/runs")
                    ? { runs: [run] }
                    : {};
    await route.fulfill({ json: data });
  });
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/email-intake?gmail=connected");
    await expect(page).toHaveURL(/\/$/);
    await expect(
      page.getByRole("link", { name: "INV-REAL-RESULT" }),
    ).toBeVisible();
    await expect(page.locator("body")).not.toContainText(
      /Email Intake|Gmail|From your inbox|CONNECTED WORKFLOW|Open inbox|Set up email intake/i,
    );
    await expect(page.locator('a[href^="/email-intake"]')).toHaveCount(0);
    await expect(page.locator(".manual-insights > section")).toHaveCount(2);
    const insight = await page.locator(".manual-insights").boundingBox();
    const activity = await page.locator(".activity-panel").boundingBox();
    expect(activity!.y).toBeGreaterThanOrEqual(insight!.y + insight!.height);
    expect(activity!.y - insight!.y - insight!.height).toBeLessThan(100);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: info.outputPath(`overview-${width}.png`),
      fullPage: true,
    });
  }
  await page.goto("/settings#email-settings");
  await expect(
    page.getByRole("heading", { name: "Active workspaces" }),
  ).toBeVisible();
  await expect(page.locator(".email-settings")).toHaveCount(0);
  expect(emailRequests).toEqual([]);
});
