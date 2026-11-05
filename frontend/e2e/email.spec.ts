import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";
import path from "node:path";
const backend = path.resolve(process.cwd(), "../backend");
const python = path.join(
  backend,
  process.platform === "win32"
    ? ".venv/Scripts/python.exe"
    : ".venv/bin/python",
);
function intake(stage: string) {
  return JSON.parse(
    execFileSync(python, ["-m", "tests.browser_email_fixture", stage], {
      cwd: backend,
      encoding: "utf8",
    }),
  );
}
test("provider-mocked Gmail handoff uses real PostgreSQL, PDF worker, decisions and scoped browser history", async ({
  page,
}, info) => {
  test.setTimeout(60000);
  const valid = intake("initial");
  await page.goto("/email-intake");
  await expect(
    page.getByText(
      "Gmail connection unavailable. Ask your administrator to finish email setup, or upload a PDF manually.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Connect Gmail" }),
  ).toBeDisabled();
  await page
    .getByLabel("Workspace", { exact: true })
    .selectOption({ label: "Email contract workspace" });
  await page.getByRole("link", { name: "Email Intake", exact: true }).click();
  await expect(
    page.getByText("provider-contract@example.invalid", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Provider-mocked Gmail initial", exact: true })
    .click();
  const attachment = page.getByRole("region", {
    name: "Attachment contract-initial.pdf",
  });
  await expect(
    attachment.getByRole("heading", { name: "Validated", exact: true }),
  ).toBeVisible({
    timeout: 20000,
  });
  const dialog = page.getByRole("dialog", { name: "Email details" });
  await expect(
    dialog.getByRole("link", { name: "View full invoice decision" }),
  ).toHaveAttribute("href", "/runs/" + valid.run_id);
  await dialog.locator(".technical-hub > summary").click();
  await expect(dialog.getByText("FALLBACK", { exact: true })).toBeVisible();
  const recorded = await page.request.get("/api/v1/runs/" + valid.run_id, {
    headers: { "X-Workspace-ID": valid.workspace_id },
  });
  const detail = await recorded.json();
  expect(
    detail.decision.rules.find(
      (r: { rule_id: string }) => r.rule_id === "PO_BALANCE",
    ).outcome,
  ).toBe("PASS");
  expect(
    detail.events.some((e: { stage: string }) => e.stage === "decision"),
  ).toBeTruthy();
  await expect(
    page.getByText(/PROVIDER MOCK CONTRACT: no live Gmail message received/),
  ).toBeVisible();
  await page.reload();
  await expect(
    attachment.getByRole("heading", { name: "Validated", exact: true }),
  ).toBeVisible();
  const blocked = intake("overbill");
  await page.getByRole("button", { name: "Close email detail" }).click();
  await expect(
    page.getByRole("button", {
      name: "Provider-mocked Gmail overbill",
      exact: true,
    }),
  ).toBeVisible({ timeout: 10000 });
  await page
    .getByRole("button", {
      name: "Provider-mocked Gmail overbill",
      exact: true,
    })
    .click();
  await expect(
    page
      .getByRole("region", { name: "Attachment contract-overbill.pdf" })
      .getByRole("heading", { name: "Blocked", exact: true }),
  ).toBeVisible({ timeout: 20000 });
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press("Tab");
    expect(
      await page
        .getByRole("dialog", { name: "Email details" })
        .evaluate((node) => node.contains(document.activeElement)),
    ).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Email details" })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("button", {
      name: "Provider-mocked Gmail overbill",
      exact: true,
    }),
  ).toBeFocused();
  await page
    .getByRole("link", { name: "Purchase orders", exact: true })
    .click();
  const row = page.getByRole("row").filter({ hasText: "GMAIL-BROWSER-PO" });
  await expect(row.getByRole("cell").nth(2)).toHaveText("USD 66.00");
  await expect(row.getByRole("cell").nth(3)).toHaveText("USD 154.00");
  await page.goto("/email-intake?message=" + blocked.message_id);
  await expect(
    page.getByRole("dialog", { name: "Email details" }),
  ).toBeVisible();
  await expect(page.getByRole("status", { name: /Loading/ })).toHaveCount(0);
  for (const width of [1920, 1440, 1280, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    const focused = page.getByRole("dialog", { name: "Email details" });
    expect(
      await focused.evaluate((node) => node.scrollWidth <= node.clientWidth),
    ).toBe(true);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    await focused.screenshot({
      path: info.outputPath(`email-detail-${width}.png`),
    });
  }
  await page.setViewportSize({ width: 1280, height: 1000 });
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.getByRole("button", { name: "Close email detail" }).click();
  await page
    .getByLabel("Workspace", { exact: true })
    .selectOption({ label: "Demo Workspace" });
  await page.getByRole("link", { name: "Email Intake", exact: true }).click();
  await expect(
    page.getByText("provider-contract@example.invalid", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", {
      name: "Provider-mocked Gmail initial",
      exact: true,
    }),
  ).toHaveCount(0);
  expect(valid.run_id).not.toBe(blocked.run_id);
});
