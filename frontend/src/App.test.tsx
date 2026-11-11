import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import App from "./App";
import { setActiveWorkspace } from "./client";
afterEach(() => {
  cleanup();
  setActiveWorkspace(null);
  sessionStorage.clear();
  vi.unstubAllGlobals();
});
it("loads API records without inventing processing results", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({
      ok: true,
      json: async () =>
        url.endsWith("/workspaces/bootstrap")
          ? {
              subject: "test",
              default_workspace_id: "demo",
              workspaces: [
                {
                  id: "demo",
                  name: "Demo Workspace",
                  kind: "DEMO",
                  role: "ADMIN",
                },
              ],
            }
          : url.endsWith("/me")
            ? { can_manage_procurement: true }
            : [
                {
                  id: "1",
                  number: "PO-TEST",
                  currency: "USD",
                  authorized_gross: "2200.000000",
                  status: "OPEN",
                  billing_mode: "ITEMIZED",
                  valid_until: "2026-12-31",
                  vendor: { legal_name: "Test vendor", status: "APPROVED" },
                  items: [],
                },
              ],
    })),
  );
  window.history.replaceState({}, "", "/purchase-orders");
  render(<App />);
  expect(await screen.findByText("PO-TEST")).toBeInTheDocument();
  expect(
    screen.getByText(/Authorization is not a payment/),
  ).toBeInTheDocument();
});
it("shows backend failure rather than sample records", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ detail: "Request failed." }),
    }),
  );
  window.history.replaceState({}, "", "/purchase-orders");
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Request failed.");
  expect(screen.queryByText("PO-2026-001")).not.toBeInTheDocument();
});

it.each([false, true])(
  "gates sidebar and direct Email Intake navigation when flag is %s",
  async (enabled) => {
    const fetcher = vi.fn(async (url: string) => ({
      ok: true,
      json: async () =>
        url.endsWith("/workspaces/bootstrap")
          ? {
              subject: "feature-test",
              default_workspace_id: "private",
              workspaces: [
                {
                  id: "private",
                  name: "My Workspace",
                  kind: "MY",
                  role: "ADMIN",
                },
              ],
            }
          : url.endsWith("/me")
            ? { workspace_name: "My Workspace", role: "ADMIN" }
            : url.includes("/runs?")
              ? { runs: [] }
              : url.startsWith("/api/v1/email")
                ? {
                    available: false,
                    connections: [],
                    messages: [],
                    attachments: [],
                    metrics: {},
                  }
                : {},
    }));
    vi.stubGlobal("fetch", fetcher);
    window.history.replaceState({}, "", "/email-intake?gmail=connected");
    render(<App enableEmailIntake={enabled} />);
    await screen.findByRole("link", {
      name: "Invoice processing",
    });
    if (enabled) {
      expect(screen.getByRole("link", { name: "Email Intake" })).toBeVisible();
      expect(window.location.pathname).toBe("/email-intake");
    } else {
      expect(
        screen.queryByRole("link", { name: "Email Intake" }),
      ).not.toBeInTheDocument();
      expect(
        await screen.findByRole("button", { name: "+ New invoice" }),
      ).toBeVisible();
      expect(window.location.pathname).toBe("/process");
      expect(
        fetcher.mock.calls.some(([url]) => url.includes("/api/v1/email")),
      ).toBe(false);
    }
  },
);
