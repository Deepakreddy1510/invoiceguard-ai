import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import {
  SampleInitialization,
  WorkspaceProvider,
  WorkspaceSelector,
  workspaceLabel,
  normalWorkspaces,
} from "./workspaces";
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
  localStorage.clear();
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
    if (path === "/workspaces")
      return {
        ...(await api.request("/workspaces/bootstrap")),
        workspace_id: "private-sample",
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
  expect(await screen.findByText(/Sample invoices ready/)).toBeVisible();
  expect(screen.getByText(/21 of 21/)).toHaveTextContent("21 of 21 processed");
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

it("dismisses completed progress while retaining an unobtrusive sample label", async () => {
  api.status = "COMPLETE";
  app();
  fireEvent.click(await screen.findByRole("button", { name: "Dismiss" }));
  expect(screen.queryByRole("progressbar")).toBeNull();
  expect(screen.queryByText(/Sample invoices ready/)).toBeNull();
  expect(screen.getByText("Sample data · Fictional company")).toBeVisible();
  expect(api.request).not.toHaveBeenCalledWith(
    "/workspaces/sample",
    expect.anything(),
  );
});

it("preserves company names and sample provenance after rename", () => {
  expect(workspaceLabel({ name: "Nandi Pipes", kind: "CUSTOM" })).toBe(
    "Nandi Pipes",
  );
  expect(
    workspaceLabel({ name: "Company · Sample company", kind: "CUSTOM" }),
  ).toBe("Company · Sample company");
  const records = [
    {
      id: "00000000-0000-0000-0000-000000000001",
      name: "Legacy",
      kind: "DEMO",
    },
    { id: "new", name: "Asterfield", kind: "DEMO" },
  ];
  expect(
    normalWorkspaces(records as Parameters<typeof normalWorkspaces>[0]),
  ).toHaveLength(2);
});
it("asks for the company name and workspace type before creating", async () => {
  render(
    <MemoryRouter>
      <WorkspaceProvider>
        <WorkspaceSelector />
      </WorkspaceProvider>
    </MemoryRouter>,
  );
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Create Workspace",
    }),
  );
  expect(screen.getByLabelText("Workspace type")).toHaveValue("EMPTY");
  expect(
    screen.getByRole("button", { name: "Confirm creation" }),
  ).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Workspace name"), {
    target: { value: "Nandi Pipes" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Confirm creation" }));
  await waitFor(() =>
    expect(api.request).toHaveBeenCalledWith(
      "/workspaces",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining(
          '"name":"Nandi Pipes","workspace_type":"EMPTY"',
        ),
      }),
    ),
  );
});
