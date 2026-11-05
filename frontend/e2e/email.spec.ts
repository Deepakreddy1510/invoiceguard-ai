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
}) => {
  test.setTimeout(45000);
  const valid = intake("initial");
  await page.goto("/email-intake");
  await expect(page.getByText(/Gmail connection unavailable/)).toBeVisible();
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
  for (const disclosure of await attachment
    .locator("details.technical-details > summary")
    .all())
    await disclosure.click();
  await expect(attachment.getByText("FALLBACK", { exact: true })).toBeVisible();
  await expect(attachment.locator(".rules")).toContainText(
    "Available purchase order balance",
  );
  await expect(attachment.locator(".email-events")).toContainText("Decision");
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
  await page
    .getByRole("link", { name: "Purchase orders", exact: true })
    .click();
  const row = page.getByRole("row").filter({ hasText: "GMAIL-BROWSER-PO" });
  await expect(row.getByRole("cell").nth(2)).toHaveText("USD 66.00");
  await expect(row.getByRole("cell").nth(3)).toHaveText("USD 154.00");
  await page.goto("/email-intake?message=" + blocked.message_id);
  await expect(
    page.getByRole("heading", { name: "Invoices from your inbox" }),
  ).toBeVisible();
  await expect(page.getByRole("status", { name: /Loading/ })).toHaveCount(0);
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
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
