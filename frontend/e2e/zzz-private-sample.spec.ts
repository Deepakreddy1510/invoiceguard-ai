import { test, expect } from "@playwright/test";

test("isolated Asterfield initialization shows real progress, outcomes, evidence and desktop navigation", async ({
  page,
  request,
}, info) => {
  test.setTimeout(180000);
  const response = await request.post("/api/v1/workspaces/sample");
  expect(response.status()).toBe(201);
  const { workspace_id } = await response.json();
  await page.setViewportSize({ width: 1700, height: 900 });
  await page.goto("/");
  await page
    .getByLabel("Workspace", { exact: true })
    .selectOption(workspace_id);
  const section = page.getByRole("region", {
    name: "Sample invoice initialization",
  });
  await expect(section).toBeVisible();
  await expect
    .poll(
      async () => {
        const result = await request.get(
          "/api/v1/workspaces/sample-initialization",
          { headers: { "X-Workspace-ID": workspace_id } },
        );
        const data = await result.json();
        expect(data.initialization.status).not.toBe("FAILED");
        return data.initialization.status;
      },
      { timeout: 120000 },
    )
    .toBe("COMPLETE");
  await expect(
    page.getByRole("region", { name: "Sample data", exact: true }),
  ).toContainText("21 of 21");
  const metrics = await (
    await request.get("/api/v1/dashboard", {
      headers: { "X-Workspace-ID": workspace_id },
    })
  ).json();
  expect(metrics.outcomes).toMatchObject({
    VALIDATED: 14,
    NEEDS_REVIEW: 1,
    BLOCKED: 5,
  });
  expect(metrics.total_invoices).toBe(20);
  expect(metrics.duplicate_assessments).toBe(1);
  expect(metrics.processing_runs).toBe(21);
  await expect(
    page.getByRole("button", { name: /^Unique invoices/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /^Unique invoices/ }),
  ).toContainText("20");
  await page.screenshot({
    path: info.outputPath("asterfield-dashboard.png"),
    fullPage: true,
  });
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  for (const name of [
    "Overview",
    "Invoice processing",
    "Exception review",
    "Email Intake",
    "Vendors",
    "Purchase orders",
    "Settings",
  ])
    await expect(nav.getByRole("link", { name, exact: true })).toBeInViewport();
  expect(
    await page
      .locator(".sidebar-scroll")
      .evaluate((node) => node.scrollHeight - node.clientHeight),
  ).toBeLessThanOrEqual(1);
  expect(
    await nav.evaluate((node) => node.scrollHeight - node.clientHeight),
  ).toBeLessThanOrEqual(1);
  await page.screenshot({
    path: info.outputPath("sidebar-desktop-100.png"),
    fullPage: true,
  });
  const state = await (
    await request.get("/api/v1/workspaces/sample-initialization", {
      headers: { "X-Workspace-ID": workspace_id },
    })
  ).json();
  const original = state.initialization.run_ids;
  await request.post("/api/v1/workspaces/sample");
  const repeated = await (
    await request.get("/api/v1/workspaces/sample-initialization", {
      headers: { "X-Workspace-ID": workspace_id },
    })
  ).json();
  expect(repeated.initialization.run_ids).toEqual(original);
  await page.goto("/runs/" + original[0]);
  await expect(page.getByTestId("run-id")).toHaveText(original[0]);
  await expect(
    page.getByRole("heading", { name: "Validated", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", {
      name: "Original invoice PDF, page 1 of 1",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Scrollable PDF page", exact: true }),
  ).toHaveAttribute("aria-busy", "false");
  await page.getByRole("tab", { name: "Activity", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Recorded processing activity",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.locator(".business-execution li").first()).toBeVisible();
  await page.screenshot({
    path: info.outputPath("asterfield-recorded-stages.png"),
    fullPage: true,
  });
  await page.goto("/reviews");
  await expect(
    page
      .getByRole("heading", { name: "Resolve uncertainty with evidence." })
      .first(),
  ).toBeVisible();
  await expect(page.locator(".review-queue-row").first()).toBeVisible();
  await expect(
    page.getByRole("img", {
      name: "Original invoice PDF, page 1 of 1",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Scrollable PDF page", exact: true }),
  ).toHaveAttribute("aria-busy", "false");
  await page.screenshot({
    path: info.outputPath("exception-review-100.png"),
    fullPage: true,
  });
});
