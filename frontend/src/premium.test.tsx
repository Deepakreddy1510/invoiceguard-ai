import {
  cleanup,
  render,
  screen,
  fireEvent,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, it, expect, vi } from "vitest";
import WorkspaceSettings from "./pages/WorkspaceSettings";
import { OverviewInsights } from "./OverviewInsights";
import { setActiveWorkspace } from "./client";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  setActiveWorkspace(null);
});
const workspace = {
  id: "own",
  name: "Cedarline Operations",
  kind: "CUSTOM",
  role: "ADMIN",
  version: 3,
  archived_at: null,
  created_at: "2026-11-01T00:00:00Z",
};
it("renames through the actual API contract with optimistic version and keeps the workspace ID", async () => {
  const fetcher = vi.fn(async (url: string, options?: RequestInit) => ({
    ok: true,
    json: async () =>
      url.startsWith("/api/v1/workspaces?")
        ? { workspaces: [workspace] }
        : {
            ...workspace,
            name: JSON.parse(String(options?.body)).name,
            version: 4,
          },
  }));
  vi.stubGlobal("fetch", fetcher);
  render(
    <MemoryRouter>
      <WorkspaceSettings />
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Rename" }));
  fireEvent.change(screen.getByLabelText("Workspace name"), {
    target: { value: "Cedarline Finance" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save name" }));
  await waitFor(() =>
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/workspaces/own",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          version: 3,
          name: "Cedarline Finance",
          confirm: false,
        }),
      }),
    ),
  );
  expect(await screen.findByText("Workspace name updated.")).toBeVisible();
});
it("asks for archive confirmation and never offers destructive workspace deletion", async () => {
  const fetcher = vi.fn(async () => ({
    ok: true,
    json: async () => ({ workspaces: [workspace] }),
  }));
  vi.stubGlobal("fetch", fetcher);
  render(
    <MemoryRouter>
      <WorkspaceSettings />
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Archive" }));
  expect(
    screen.getByRole("dialog", { name: "Archive workspace?" }),
  ).toBeVisible();
  expect(screen.getByText(/All existing documents/)).toBeVisible();
  expect(
    screen.queryByRole("button", { name: /Delete/ }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Archive workspace" }));
  await waitFor(() =>
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/workspaces/own/archive",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ version: 3, confirm: true }),
      }),
    ),
  );
});
it("does not offer management actions for a viewer and shows retained archived state", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => ({
        workspaces: [
          { ...workspace, role: "VIEWER", archived_at: "2026-11-02T00:00:00Z" },
        ],
      }),
    })),
  );
  render(
    <MemoryRouter>
      <WorkspaceSettings />
    </MemoryRouter>,
  );
  expect(await screen.findByText("Archived")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Rename" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Restore" }),
  ).not.toBeInTheDocument();
});
it("charts only actual counts, separates awaiting decisions and gives useful empty states", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({
      ok: true,
      json: async () =>
        url.includes("reviews") ? { tasks: [] } : { messages: [] },
    })),
  );
  const view = render(
    <MemoryRouter>
      <OverviewInsights
        outcomes={{ VALIDATED: 3, NEEDS_REVIEW: 1, BLOCKED: 1 }}
        total={6}
      />
    </MemoryRouter>,
  );
  expect(screen.getByRole("img")).toHaveAttribute(
    "aria-label",
    "Validated: 3, Needs review: 1, Blocked: 1, Awaiting decision: 1",
  );
  expect(await screen.findByText("You're all caught up")).toBeVisible();
  view.unmount();
  render(
    <MemoryRouter>
      <OverviewInsights outcomes={{}} total={0} />
    </MemoryRouter>,
  );
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(
    screen.getByText("Your first invoice starts the picture"),
  ).toBeVisible();
});
