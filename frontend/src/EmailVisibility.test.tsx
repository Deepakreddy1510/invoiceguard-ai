import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import App from "./App";
import { setActiveWorkspace } from "./client";

const workspace = {
  id: "private",
  name: "My Workspace",
  kind: "MY",
  role: "ADMIN",
  version: 1,
};
const run = {
  id: "run-1",
  document_id: "doc-1",
  status: "SUCCEEDED",
  outcome: "VALIDATED",
  invoice_number: "INV-ACCEPTED",
  vendor_name: "Approved Supplier",
  created_at: "2026-11-11T12:00:00Z",
  finished_at: "2026-11-11T12:00:02Z",
  parent_run_id: null,
  events: [],
  pages: [],
  extraction: null,
  decision: null,
};
afterEach(() => {
  cleanup();
  setActiveWorkspace(null);
  sessionStorage.clear();
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});
function setup(path = "/") {
  const fetcher = vi.fn(async (url: string) => {
    if (url.startsWith("/api/v1/email"))
      throw new Error("Disabled email endpoint was requested");
    const data = url.includes("/workspaces")
      ? {
          subject: "verified-user",
          default_workspace_id: "private",
          workspaces: [workspace],
        }
      : url.endsWith("/me")
        ? {
            workspace_name: "My Workspace",
            workspace_kind: "MY",
            role: "ADMIN",
            vendor_count: 2,
            po_count: 3,
          }
        : url.includes("/dashboard")
          ? {
              total_invoices: 6,
              outcomes: { VALIDATED: 3, NEEDS_REVIEW: 2, BLOCKED: 1 },
              recent_runs: [run],
              worker: { available: true, last_seen: null },
              processing_runs: 7,
              failed_runs: 0,
              duplicate_assessments: 1,
            }
          : url.includes("/reviews")
            ? { tasks: [] }
            : url.includes("/audit-events")
              ? {
                  events: [
                    {
                      id: "historical",
                      action: "EMAIL_HANDOFF",
                      actor: "gmail-worker",
                      created_at: run.created_at,
                      run_id: run.id,
                      href: "/email-intake?message=old",
                      detail: {},
                    },
                  ],
                }
              : url.includes("/runs/")
                ? run
                : url.includes("/runs?")
                  ? { runs: [run] }
                  : {};
    return { ok: true, json: async () => structuredClone(data) };
  });
  vi.stubGlobal("fetch", fetcher);
  window.history.replaceState({}, "", path);
  render(<App enableEmailIntake={false} />);
  return fetcher;
}
function expectNoIntake(fetcher: ReturnType<typeof setup>) {
  expect(document.body).not.toHaveTextContent(
    /Email Intake|Gmail|From your inbox|Connected workflow|Open inbox|Let invoices come to you|Set up email intake|email checks/i,
  );
  expect(document.querySelector('a[href^="/email-intake"]')).toBeNull();
  expect(
    fetcher.mock.calls.some(([url]) => url.startsWith("/api/v1/email")),
  ).toBe(false);
  expect(document.body).not.toHaveTextContent(
    "Email Intake is disabled in this deployment",
  );
}
it("renders real dashboard summaries and recent processing without intake UI, calls or a vacant column", async () => {
  const fetcher = setup();
  expect(
    await screen.findByRole("link", { name: "INV-ACCEPTED" }),
  ).toBeVisible();
  expect(
    screen.getByRole("img", {
      name: "Validated: 3, Needs review: 2, Blocked: 1, Awaiting decision: 0",
    }),
  ).toBeVisible();
  expect(
    screen.getByRole("button", { name: /Unique invoices/ }),
  ).toHaveTextContent("6");
  expect(
    screen.getByRole("heading", { name: "Recent processing activity" }),
  ).toBeVisible();
  expect(document.querySelectorAll(".manual-insights > section")).toHaveLength(
    2,
  );
  expect(document.querySelector(".inbox-insight")).toBeNull();
  expectNoIntake(fetcher);
  fireEvent.click(screen.getByText("How InvoiceGuard works"));
  expectNoIntake(fetcher);
});
it("old intake URLs redirect silently to Overview without a disabled API request", async () => {
  const fetcher = setup("/email-intake?message=old&gmail=connected");
  await screen.findByRole("heading", { name: "Your invoices. Under control." });
  expect(window.location.pathname).toBe("/");
  expect(window.location.search).toBe("");
  expectNoIntake(fetcher);
});
it("settings and workspace onboarding omit email configuration and requests", async () => {
  const fetcher = setup("/settings#email-settings");
  await screen.findByRole("heading", { name: "Active workspaces" });
  expect(document.querySelector(".email-settings")).toBeNull();
  expectNoIntake(fetcher);
  fireEvent.click(screen.getByRole("button", { name: "Create Workspace" }));
  const dialog = screen.getByRole("dialog");
  expect(within(dialog).getByLabelText("Workspace type")).toBeVisible();
  expectNoIntake(fetcher);
});
it("manual invoice processing and multiple PDF selection remain available", async () => {
  const fetcher = setup("/process");
  fireEvent.click(await screen.findByRole("button", { name: "+ New invoice" }));
  const input = screen.getByLabelText("Invoice PDF") as HTMLInputElement;
  expect(input.multiple).toBe(true);
  fireEvent.change(input, {
    target: {
      files: ["one.pdf", "two.pdf"].map(
        (name) => new File(["%PDF-test"], name, { type: "application/pdf" }),
      ),
    },
  });
  expect(
    screen.getByRole("button", { name: "Upload and process all" }),
  ).toBeEnabled();
  expectNoIntake(fetcher);
});
