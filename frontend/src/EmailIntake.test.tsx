import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import EmailIntake from "./pages/EmailIntake";
import { setActiveWorkspace } from "./client";
afterEach(() => {
  cleanup();
  setActiveWorkspace(null);
  vi.unstubAllGlobals();
});
const base = {
  available: false,
  configuration_message:
    "Gmail connection unavailable. Configure Google OAuth and server encryption.",
  can_manage: true,
  can_review: true,
  workspace_id: "mine",
  connections: [],
  metrics: {
    emails_checked: 0,
    invoice_candidates: 0,
    attachments_ingested: 0,
    awaiting_review: 0,
    ignored: 0,
    failed: 0,
    unique_documents: 0,
  },
  messages: [],
};
it("shows unavailable Gmail without inventing connection or email activity", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, json: async () => base })),
  );
  render(
    <MemoryRouter>
      <EmailIntake />
    </MemoryRouter>,
  );
  expect(await screen.findByText(/Gmail connection unavailable/)).toBeVisible();
  expect(screen.getByRole("button", { name: "Connect Gmail" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Manage connection" }));
  expect(
    screen.getByText("No mailbox is connected to this workspace."),
  ).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Close dialog" }));
  expect(screen.getByText("No incoming email in this view")).toBeVisible();
});
it("queues actual sync requests with the active workspace and renders distinct processing/decision states", async () => {
  setActiveWorkspace("mine");
  const fetcher = vi.fn(async (url: string) => ({
    ok: true,
    json: async () =>
      url.endsWith("/sync")
        ? { queued: true }
        : {
            ...base,
            available: true,
            connections: [
              {
                id: "c1",
                email: "provider-contract@example.invalid",
                status: "ACTIVE",
                last_sync_at: null,
                next_sync_at: "2026-11-05T00:00:00Z",
                error: null,
              },
            ],
            messages: [
              {
                id: "m1",
                subject: "Synthetic invoice",
                sender: "sender@example.invalid",
                received_at: null,
                status: "INTAKE_RECORDED",
                attachments: [
                  {
                    id: "a1",
                    filename: "synthetic.pdf",
                    status: "INGESTED",
                    classification: { category: "INVOICE" },
                    processing_status: "SUCCEEDED",
                    decision: "NEEDS_REVIEW",
                    run_id: "r1",
                  },
                ],
              },
            ],
          },
  }));
  vi.stubGlobal("fetch", fetcher);
  render(
    <MemoryRouter>
      <EmailIntake />
    </MemoryRouter>,
  );
  expect(
    await screen.findByText("provider-contract@example.invalid"),
  ).toBeVisible();
  expect(screen.getByText("Completed")).toBeVisible();
  expect(screen.getByText("Needs review")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Check now" }));
  await waitFor(() =>
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/email/connections/c1/sync",
      expect.objectContaining({ method: "POST" }),
    ),
  );
  expect(
    await screen.findByText(
      "Checking for new invoices. Results will appear as messages are processed.",
    ),
  ).toBeVisible();
  const call = fetcher.mock.calls.find(([url]) =>
    url.endsWith("/sync"),
  ) as unknown as [string, RequestInit];
  expect(new Headers(call[1].headers).get("X-Workspace-ID")).toBe("mine");
});
it("renders email bodies as text and never executes supplied markup", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({
      ok: true,
      json: async () =>
        url.includes("/messages/")
          ? {
              id: "m1",
              subject: "Untrusted message",
              sender: "sender@example.invalid",
              body: '<img src="https://evil.invalid/x" onerror="alert(1)"><script>steal()</script>',
              received_at: null,
              workspace_id: "mine",
              attachments: [],
              events: [],
            }
          : base,
    })),
  );
  render(
    <MemoryRouter initialEntries={["/email-intake?message=m1"]}>
      <EmailIntake />
    </MemoryRouter>,
  );
  expect(await screen.findByText(/<img src=/)).toBeVisible();
  expect(document.querySelector(".email-body img")).toBeNull();
  expect(document.querySelector(".email-body script")).toBeNull();
});
