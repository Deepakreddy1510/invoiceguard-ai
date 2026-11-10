import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { SampleInitialization, WorkspaceProvider } from "./workspaces";
const api = vi.hoisted(() => ({
  request: vi.fn(),
  status: "PROCESSING" as string | null,
}));
vi.mock("./client", () => ({
  request: api.request,
  setActiveWorkspace: vi.fn(),
}));
beforeEach(() => {
  api.status = "PROCESSING";
  api.request.mockReset();
  sessionStorage.clear();
  api.request.mockImplementation(async (path: string) => {
    if (path === "/workspaces/bootstrap")
      return {
        subject: "account-a",
        default_workspace_id: "private-sample",
        workspaces: [
          {
            id: "private-sample",
            name: "Asterfield",
            kind: "DEMO",
            role: "ADMIN",
            version: 1,
          },
        ],
      };
    if (path === "/workspaces/sample-initialization/resume") {
      api.status = "COMPLETE";
      return {};
    }
    if (path === "/workspaces/sample") {
      api.status = "PROCESSING";
      return {};
    }
    return {
      eligible: true,
      initialization: api.status
        ? {
            status: api.status,
            completed: api.status === "COMPLETE" ? 21 : 4,
            total: 21,
            current_run_id: "recorded-run",
            error:
              api.status === "FAILED" ? "A recorded technical failure" : null,
          }
        : null,
    };
  });
});
afterEach(cleanup);
function app() {
  render(
    <MemoryRouter>
      <WorkspaceProvider>
        <SampleInitialization />
      </WorkspaceProvider>
    </MemoryRouter>,
  );
}
it("discloses real incomplete progress and links persisted stages", async () => {
  app();
  expect(await screen.findByText(/4 of 21/)).toHaveTextContent(
    "this demo is not complete",
  );
  expect(screen.getByRole("progressbar")).toHaveAttribute("value", "4");
  expect(
    screen.getByRole("link", { name: "View current invoice stages" }),
  ).toHaveAttribute("href", "/runs/recorded-run");
  expect(screen.queryByText("Sample invoices ready")).toBeNull();
});
it("shows technical failure and explicitly resumes before announcing completion", async () => {
  api.status = "FAILED";
  app();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "recorded technical failure",
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Resume sample initialization" }),
  );
  expect(await screen.findByText("Sample invoices ready")).toBeVisible();
  expect(screen.getByText(/21 of 21/)).toHaveTextContent(
    "Real decisions and source evidence are ready",
  );
  expect(api.request).toHaveBeenCalledWith(
    "/workspaces/sample-initialization/resume",
    { method: "POST" },
  );
});
it("offers explicit backfill for an old sample without an installation", async () => {
  api.status = null;
  app();
  fireEvent.click(
    await screen.findByRole("button", { name: "Initialize sample invoices" }),
  );
  await waitFor(() =>
    expect(api.request).toHaveBeenCalledWith("/workspaces/sample", {
      method: "POST",
    }),
  );
  expect(await screen.findByText(/4 of 21/)).toHaveTextContent("not complete");
});
