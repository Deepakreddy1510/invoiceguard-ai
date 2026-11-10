import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { writeFileSync } from "node:fs";

test("named company and sample workspaces preserve isolation, stage history and accessible focus", async ({
  page,
  request,
}, info) => {
  test.setTimeout(180000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Create Workspace", exact: true })
    .click();
  await page.getByLabel("Workspace name", { exact: true }).fill("Nandi Pipes");
  await page.screenshot({
    path: info.outputPath("create-empty.png"),
    fullPage: true,
  });
  const creation = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/workspaces") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Confirm creation" }).click();
  const company = (await (await creation).json()).workspace_id;
  await expect(page.getByLabel("Workspace", { exact: true })).toHaveValue(
    company,
  );
  await expect(page.locator(".demo-disclosure")).toHaveCount(0);
  for (const path of ["vendors", "purchase-orders", "runs"]) {
    const response = await request.get("/api/v1/" + path, {
      headers: { "X-Workspace-ID": company },
    });
    const data = await response.json();
    expect(
      Array.isArray(data)
        ? data.length
        : (data.items?.length ?? data.runs?.length ?? 0),
    ).toBe(0);
  }
  await page.screenshot({
    path: info.outputPath("empty-company.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Create Workspace", exact: true })
    .click();
  await page.getByLabel("Workspace name", { exact: true }).fill("Nandi sample");
  await page.getByLabel("Workspace type").selectOption("SAMPLE");
  const sampleCreation = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/workspaces") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Confirm creation" }).click();
  const sample = (await (await sampleCreation).json()).workspace_id;
  await expect(page.getByLabel("Workspace", { exact: true })).toHaveValue(
    sample,
  );
  await expect
    .poll(
      async () => {
        const state = await (
          await request.get("/api/v1/workspaces/sample-initialization", {
            headers: { "X-Workspace-ID": sample },
          })
        ).json();
        expect(state.initialization.status).not.toBe("FAILED");
        return state.initialization.status;
      },
      { timeout: 120000 },
    )
    .toBe("COMPLETE");
  await expect(
    page.getByRole("region", { name: "Sample data", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Dismiss", exact: true }).click();
  await expect(page.getByRole("progressbar")).toHaveCount(0);
  await page.screenshot({
    path: info.outputPath("sample-complete.png"),
    fullPage: true,
  });
  const headers = { "X-Workspace-ID": sample };
  const state = await (
    await request.get("/api/v1/workspaces/sample-initialization", { headers })
  ).json();
  const runs = await Promise.all(
    state.initialization.run_ids.map(async (id: string) =>
      (await request.get("/api/v1/runs/" + id, { headers })).json(),
    ),
  );
  const blocked = runs.find((r) => r.decision?.outcome === "BLOCKED");
  expect(blocked.status).toBe("SUCCEEDED");
  // Real persisted sample run for frontend stage regressions; no fabricated event history.
  writeFileSync(
    info.outputPath("completed-sample-events.json"),
    JSON.stringify(
      {
        id: blocked.id,
        document_id: blocked.document_id,
        parent_run_id: blocked.parent_run_id,
        status: blocked.status,
        attempt: blocked.attempt,
        outcome: blocked.decision.outcome,
        created_at: blocked.created_at,
        finished_at: blocked.finished_at,
        error: blocked.error,
        events: blocked.events,
        pages: null,
        extraction: null,
        decision: null,
      },
      null,
      2,
    ) + "\n",
  );
  await page.goto("/runs/" + blocked.id);
  await page.getByRole("tab", { name: "Activity", exact: true }).click();
  await expect(page.locator(".business-execution .status-running")).toHaveCount(
    0,
  );
  await expect(
    page.locator(".business-execution .status-skipped"),
  ).toBeVisible();
  await page
    .getByRole("region", { name: "Invoice activity" })
    .getByText(/^Immutable execution timeline/)
    .click();
  await expect(
    page
      .getByRole("region", { name: "Invoice activity" })
      .getByText(/Historical start/)
      .last(),
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath("blocked-stage-summary.png"),
    fullPage: true,
  });
  await page.getByLabel("Workspace", { exact: true }).selectOption(company);
  await page.goto("/purchase-orders");
  const input = page.locator(".search-field input").first();
  await input.focus();
  const assertFocus = async () => {
    expect(
      await input.evaluate((el) => getComputedStyle(el).outlineStyle),
    ).toBe("none");
    expect(
      await input.evaluate(
        (el) => getComputedStyle(el.parentElement!).outlineStyle,
      ),
    ).toBe("solid");
    expect(await input.evaluate((el) => getComputedStyle(el).boxShadow)).toBe(
      "none",
    );
  };
  await assertFocus();
  await page.screenshot({
    path: info.outputPath("focus-desktop.png"),
    fullPage: true,
  });
  await page.emulateMedia({ forcedColors: "active" });
  await assertFocus();
  await page.emulateMedia({ forcedColors: "none" });
  await page.setViewportSize({ width: 390, height: 844 });
  await input.focus();
  await assertFocus();
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze())
      .violations,
  ).toEqual([]);
  await page.screenshot({
    path: info.outputPath("focus-mobile.png"),
    fullPage: true,
  });
});

test("workspace form keeps normal, hover, invalid and disabled states accessible", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Create Workspace", exact: true })
    .click();
  const input = page.getByLabel("Workspace name", { exact: true });
  expect(await input.evaluate((el) => getComputedStyle(el).outlineStyle)).toBe(
    "none",
  );
  const normalBorder = await input.evaluate(
    (el) => getComputedStyle(el).borderTopColor,
  );
  await input.blur();
  await input.hover();
  expect(await input.evaluate((el) => getComputedStyle(el).outlineStyle)).toBe(
    "none",
  );
  await input.focus();
  expect(await input.evaluate((el) => getComputedStyle(el).outlineWidth)).toBe(
    "2px",
  );
  expect(await input.evaluate((el) => getComputedStyle(el).boxShadow)).toBe(
    "none",
  );
  await input.evaluate((el) => el.setAttribute("aria-invalid", "true"));
  expect(
    await input.evaluate((el) => getComputedStyle(el).borderTopColor),
  ).not.toBe(normalBorder);
  await input.evaluate((el) => {
    el.removeAttribute("aria-invalid");
    (el as HTMLInputElement).disabled = true;
  });
  await expect(input).toBeDisabled();
  await input.evaluate((el) => ((el as HTMLInputElement).disabled = false));
  expect(
    (
      await new AxeBuilder({ page })
        .include('form[aria-label="Create Workspace"]')
        .withTags(["wcag2a", "wcag2aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
});
