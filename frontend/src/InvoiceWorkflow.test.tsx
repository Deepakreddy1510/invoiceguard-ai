import { MemoryRouter } from "react-router-dom";
import {
  act,
  cleanup,
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import InvoiceWorkflow from "./InvoiceWorkflow";
import type { RunDetail } from "./models";
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});
function run(id: string, status = "QUEUED"): RunDetail {
  return {
    id,
    document_id: "doc-" + id,
    parent_run_id: null,
    status,
    attempt: 1,
    outcome: null,
    invoice_number: id,
    vendor_name: "Synthetic vendor",
    created_at: "2026-06-15T00:00:00Z",
    finished_at: null,
    error: null,
    events: [],
    extraction: null,
    decision: null,
    pages: null,
  };
}
function response(value: unknown) {
  return {
    ok: true,
    json: async () => structuredClone(value),
    blob: async () => new Blob(["%PDF-test"], { type: "application/pdf" }),
  };
}
it("renders technical failure separately from a financial decision and queues a real retry request", async () => {
  const failed = {
    ...run("failed-run", "FAILED"),
    error: "OCR processing failed.",
    events: [
      {
        id: 1,
        stage: "text_extraction",
        outcome: "FAILED",
        attempt: 1,
        detail: "Real OCR failure.",
        created_at: "2026-06-15T00:00:00Z",
      },
    ],
  };
  const fetcher = vi.fn(async (url: string) =>
    response(
      url.endsWith("/retry")
        ? { run_id: "retry-run" }
        : url.includes("/runs?")
          ? { runs: [failed] }
          : url.endsWith("/retry-run")
            ? run("retry-run")
            : failed,
    ),
  );
  vi.stubGlobal("fetch", fetcher);
  render(
    <MemoryRouter>
      <InvoiceWorkflow initialRunId="failed-run" />
    </MemoryRouter>,
  );
  const region = screen.getByRole("region", { name: "Processing run" });
  expect(
    await within(region).findByText("Processing failed", {
      selector: ".run-status .status",
    }),
  ).toBeInTheDocument();
  expect(
    within(region).queryByRole("region", { name: "Financial decision" }),
  ).not.toBeInTheDocument();
  expect(
    await within(
      screen.getByRole("list", { name: "Actual execution stages" }),
    ).findByText("Real OCR failure."),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry failed run" }));
  await waitFor(() =>
    expect(screen.getByTestId("run-id")).toHaveTextContent("retry-run"),
  );
  expect(fetcher).toHaveBeenCalledWith(
    "/api/v1/runs/failed-run/retry",
    expect.objectContaining({
      method: "POST",
    }),
  );
  expect(
    screen.queryByText("The recorded financial checks passed."),
  ).not.toBeInTheDocument();
});
it("keeps unobserved stages pending for a queued run and never invents outputs or approval", async () => {
  const queued = run("queued-run");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      response(url.includes("/runs?") ? { runs: [queued] } : queued),
    ),
  );
  render(
    <MemoryRouter>
      <InvoiceWorkflow initialRunId="queued-run" />
    </MemoryRouter>,
  );
  expect(await screen.findByTestId("run-id")).toHaveTextContent("queued-run");
  expect(
    screen.getByText(/Waiting to process this invoice/),
  ).toBeInTheDocument();
  expect(
    document.querySelectorAll('.stage[data-state="PENDING"]'),
  ).toHaveLength(6);
  expect(
    document.querySelectorAll('.stage[data-state="SUCCEEDED"]'),
  ).toHaveLength(0);
  expect(
    screen.queryByRole("region", { name: "Financial decision" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByText("Extracted fields")).not.toBeInTheDocument();
});
it("selects the latest run on load, then preserves an explicit selection", async () => {
  const latest = run("newest"),
    older = run("older");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      response(
        url.includes("/runs?")
          ? { runs: [latest, older] }
          : url.endsWith("/older")
            ? older
            : latest,
      ),
    ),
  );
  render(
    <MemoryRouter>
      <InvoiceWorkflow />
    </MemoryRouter>,
  );
  expect(await screen.findByTestId("run-id")).toHaveTextContent("newest");
  fireEvent.click(screen.getByRole("button", { name: /older/ }));
  await waitFor(() =>
    expect(screen.getByTestId("run-id")).toHaveTextContent("older"),
  );
  fireEvent.click(screen.getByRole("button", { name: "Validated" }));
  expect(screen.getByTestId("run-id")).toHaveTextContent("older");
});
it("validates file type, size and removal before allowing upload", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => response({ runs: [] })),
  );
  render(
    <MemoryRouter>
      <InvoiceWorkflow />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "+ New invoice" }));
  const input = screen.getByLabelText("Invoice PDF", { exact: true });
  const submit = screen.getByRole("button", { name: "Upload and process" });
  expect(submit).toBeDisabled();
  fireEvent.change(input, {
    target: { files: [new File(["bad"], "notes.txt", { type: "text/plain" })] },
  });
  expect(await screen.findByRole("alert")).toHaveTextContent("Choose a PDF");
  expect(submit).toBeDisabled();
  const big = new File(["pdf"], "big.pdf", { type: "application/pdf" });
  Object.defineProperty(big, "size", { value: 10 * 1024 * 1024 + 1 });
  fireEvent.change(input, { target: { files: [big] } });
  expect(screen.getByRole("alert")).toHaveTextContent("10 MiB");
  fireEvent.change(input, {
    target: {
      files: [
        new File(["%PDF-test"], "invoice.pdf", { type: "application/pdf" }),
      ],
    },
  });
  expect(submit).toBeEnabled();
  expect(screen.getByText("invoice.pdf")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Remove selected PDF" }));
  expect(submit).toBeDisabled();
});
it("selects the new persisted run on upload without simulating completed stages", async () => {
  const old = run("old"),
    fresh = {
      ...run("fresh", "RUNNING"),
      events: [
        {
          id: 1,
          stage: "field_extraction",
          outcome: "RUNNING",
          attempt: 1,
          detail: "Actual extraction is running.",
          created_at: "2026-06-15T00:00:00Z",
        },
      ],
    };
  let uploaded = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url === "/api/v1/documents") {
        uploaded = true;
        return response({ run_id: "fresh", replayed: false });
      }
      return response(
        url.includes("/runs?")
          ? { runs: uploaded ? [fresh, old] : [old] }
          : url.endsWith("/fresh")
            ? fresh
            : old,
      );
    }),
  );
  render(
    <MemoryRouter>
      <InvoiceWorkflow />
    </MemoryRouter>,
  );
  expect(await screen.findByTestId("run-id")).toHaveTextContent("old");
  fireEvent.click(screen.getByRole("button", { name: "+ New invoice" }));
  fireEvent.change(screen.getByLabelText("Invoice PDF", { exact: true }), {
    target: {
      files: [
        new File(["%PDF-test"], "fresh.pdf", { type: "application/pdf" }),
      ],
    },
  });
  fireEvent.click(screen.getByRole("button", { name: "Upload and process" }));
  await waitFor(() =>
    expect(screen.getByTestId("run-id")).toHaveTextContent("fresh"),
  );
  expect(
    within(
      screen.getByRole("list", { name: "Actual execution stages" }),
    ).getByText("Actual extraction is running."),
  ).toBeVisible();
  expect(
    document.querySelector('[data-stage="field_extraction"]'),
  ).toHaveAttribute("data-state", "RUNNING");
  expect(
    screen.queryByRole("region", { name: "Financial decision" }),
  ).not.toBeInTheDocument();
});
it("preserves manual selection while upload is in flight", async () => {
  const a = run("a"),
    b = run("b");
  let finish!: (v: unknown) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      url === "/api/v1/documents"
        ? new Promise((resolve) => {
            finish = resolve;
          })
        : Promise.resolve(
            response(
              url.includes("/runs?")
                ? { runs: [a, b] }
                : url.endsWith("/b")
                  ? b
                  : a,
            ),
          ),
    ),
  );
  render(
    <MemoryRouter>
      <InvoiceWorkflow />
    </MemoryRouter>,
  );
  expect(await screen.findByTestId("run-id")).toHaveTextContent("a");
  fireEvent.click(screen.getByRole("button", { name: "+ New invoice" }));
  fireEvent.change(screen.getByLabelText("Invoice PDF", { exact: true }), {
    target: {
      files: [
        new File(["%PDF-test"], "fresh.pdf", { type: "application/pdf" }),
      ],
    },
  });
  fireEvent.click(screen.getByRole("button", { name: "Upload and process" }));
  fireEvent.click(screen.getByRole("button", { name: "Close dialog" }));
  fireEvent.click(screen.getByRole("button", { name: /^b Synthetic vendor/ }));
  await waitFor(() =>
    expect(screen.getByTestId("run-id")).toHaveTextContent("b"),
  );
  await act(async () => finish(response({ run_id: "fresh", replayed: false })));
  expect(screen.getByTestId("run-id")).toHaveTextContent("b");
});
it("polls recorded changes, announces completion and stops polling completed details", async () => {
  vi.useFakeTimers();
  let current = run("live", "RUNNING");
  const fetcher = vi.fn(async (url: string) =>
    response(url.includes("/runs?") ? { runs: [current] } : current),
  );
  vi.stubGlobal("fetch", fetcher);
  await act(async () => {
    render(
      <MemoryRouter>
        <InvoiceWorkflow initialRunId="live" />
      </MemoryRouter>,
    );
  });
  current = {
    ...current,
    events: [
      {
        id: 1,
        stage: "validation",
        outcome: "RUNNING",
        attempt: 1,
        detail: "Actual checks started.",
        created_at: "2026-06-15T00:00:01Z",
      },
    ],
  };
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1100);
  });
  expect(
    within(
      screen.getByRole("list", { name: "Actual execution stages" }),
    ).getByText("Actual checks started."),
  ).toBeVisible();
  current = {
    ...current,
    status: "SUCCEEDED",
    outcome: "BLOCKED",
    finished_at: "2026-06-15T00:00:02Z",
    events: [
      ...current.events,
      {
        id: 2,
        stage: "validation",
        outcome: "SUCCEEDED",
        attempt: 1,
        detail: "Actual checks finished.",
        created_at: "2026-06-15T00:00:02Z",
      },
    ],
    decision: {
      outcome: "BLOCKED",
      summary: {},
      rules: [
        {
          rule_id: "PO_BALANCE",
          outcome: "BLOCK",
          explanation: "Requested amount exceeds remaining authorization.",
          actual: "20",
          expected: "10",
        },
      ],
    },
  };
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1100);
  });
  expect(screen.getByRole("heading", { name: "Blocked" })).toBeVisible();
  expect(screen.getByText("Invoice live: Blocked")).toBeInTheDocument();
  const before = fetcher.mock.calls.filter(
    ([url]) => url === "/api/v1/runs/live",
  ).length;
  await act(async () => {
    await vi.advanceTimersByTimeAsync(5000);
  });
  expect(
    fetcher.mock.calls.filter(([url]) => url === "/api/v1/runs/live"),
  ).toHaveLength(before);
  expect(screen.getByRole("heading", { name: "Blocked" })).toBeVisible();
});
