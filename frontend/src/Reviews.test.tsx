import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import Reviews from "./pages/Reviews";
vi.mock("./DocumentViewer", () => ({ default: () => <p>Document viewer</p> }));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const run = (id: string) => ({
  id: "run-" + id,
  invoice_number: "INV-" + id,
  vendor_name: "Rivermark Catering",
  status: "SUCCEEDED",
  outcome: "NEEDS_REVIEW",
  attempt: 1,
});
const task = (id: string) => ({
  id,
  run: run(id),
  status: "OPEN",
  version: 1,
  latest_run_id: "run-" + id,
  document_id: "doc-" + id,
  created_at: "2026-11-01T00:00:00Z",
  outcome: "NEEDS_REVIEW",
  extraction: {
    provider: "FALLBACK",
    fields: { invoice_number: { value: "INV-" + id, verified: true } },
  },
  decisions: [
    {
      run_id: "run-" + id,
      outcome: "NEEDS_REVIEW",
      rules: [],
      created_at: "2026-11-01T00:00:00Z",
    },
  ],
  commitments: [],
  corrections: [],
});
function mount(path = "/reviews", empty = false, denied = false) {
  const fetcher = vi.fn(async (url: string) => ({
    ok: !denied || !url.endsWith("/missing"),
    status: 404,
    json: async () =>
      url.includes("/reviews?")
        ? { tasks: empty ? [] : [task("one"), task("two")] }
        : url.includes("/runs/")
          ? { ...run("one"), decision: null, extraction: null }
          : url.endsWith("/missing")
            ? { detail: "Review not found" }
            : task(url.split("/").at(-1)!),
  }));
  vi.stubGlobal("fetch", fetcher);
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/reviews/:id?" element={<Reviews />} />
      </Routes>
    </MemoryRouter>,
  );
  return fetcher;
}
it("automatically opens the first eligible review with bounded, keyboard-accessible regions", async () => {
  mount();
  expect(
    await screen.findByRole("heading", { name: "INV-one Rivermark Catering" }),
  ).toBeVisible();
  expect(
    screen.getByRole("region", { name: "Scrollable exception queue" }),
  ).toHaveAttribute("tabindex", "0");
  expect(
    screen.getByRole("region", { name: "Scrollable review details" }),
  ).toHaveAttribute("tabindex", "0");
  const queue = screen.getByRole("region", { name: "Exception queue" });
  expect(within(queue).getByRole("link", { name: /INV-one/ })).toHaveAttribute(
    "aria-current",
    "page",
  );
});
it("preserves an explicit selection, focuses selected details and retains edits across tabs", async () => {
  mount("/reviews/two");
  expect(
    await screen.findByRole("heading", { name: "INV-two Rivermark Catering" }),
  ).toBeVisible();
  fireEvent.change(screen.getByLabelText("Correct invoice number"), {
    target: { value: "SOURCE-VERIFIED-NUMBER" },
  });
  fireEvent.click(screen.getByRole("tab", { name: "History" }));
  fireEvent.click(screen.getByRole("tab", { name: "Review & correct" }));
  expect(screen.getByLabelText("Correct invoice number")).toHaveValue(
    "SOURCE-VERIFIED-NUMBER",
  );
  fireEvent.click(
    within(screen.getByRole("region", { name: "Exception queue" })).getByRole(
      "link",
      { name: /INV-one/ },
    ),
  );
  expect(
    await screen.findByRole("heading", { name: "INV-one Rivermark Catering" }),
  ).toBeVisible();
  expect(
    screen.getByRole("region", { name: "Scrollable review details" }),
  ).toHaveFocus();
});
it("renders a deliberate empty state with no empty detail columns", async () => {
  mount("/reviews", true);
  expect(await screen.findByText("No open exceptions")).toBeVisible();
  expect(
    screen.queryByRole("region", { name: "Exception details" }),
  ).not.toBeInTheDocument();
});
it("explains missing or inaccessible selection and offers recovery", async () => {
  mount("/reviews/missing", false, true);
  expect(
    await screen.findByText("This review could not be opened"),
  ).toBeVisible();
  fireEvent.click(
    screen.getByRole("button", { name: "Open first available exception" }),
  );
  expect(
    await screen.findByRole("heading", { name: "INV-one Rivermark Catering" }),
  ).toBeVisible();
});
