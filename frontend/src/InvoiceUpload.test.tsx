import { MemoryRouter } from "react-router-dom";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import InvoiceUpload from "./InvoiceUpload";
import { setActiveWorkspace } from "./client";
vi.mock("./ui", () => ({ PdfPreview: () => null }));
afterEach(() => {
  cleanup();
  setActiveWorkspace(null);
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
function pdf(name: string) {
  return new File(["%PDF-synthetic"], name, { type: "application/pdf" });
}
function response(data: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => data };
}
function mount() {
  const accepted = vi.fn(),
    updated = vi.fn();
  const view = render(
    <MemoryRouter>
      <InvoiceUpload
        open
        onClose={() => {}}
        onAccepted={accepted}
        onUpdated={updated}
      />
    </MemoryRouter>,
  );
  return { ...view, accepted, updated };
}
function select(files: File[]) {
  fireEvent.change(screen.getByLabelText("Invoice PDF"), { target: { files } });
}
function row(name: string) {
  return screen.getByText(name).closest("li")!;
}
it("selects one or five PDFs, removes files, accepts drops and bounds batches", () => {
  mount();
  const files = [1, 2, 3, 4, 5].map((n) => pdf(`${n}.pdf`));
  select([files[0]]);
  expect(
    screen.getByRole("button", { name: "Upload and process" }),
  ).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "Remove selected PDF" }));
  fireEvent.drop(
    screen.getByRole("button", { name: /Drop your invoice PDFs/ }),
    { dataTransfer: { files } },
  );
  expect(
    within(
      screen.getByRole("region", { name: "PDF upload queue" }),
    ).getAllByRole("listitem"),
  ).toHaveLength(5);
  expect(screen.getAllByText(/0.00 MiB/)).toHaveLength(5);
  select([pdf("six.pdf")]);
  expect(screen.getByRole("alert")).toHaveTextContent("five PDFs");
  expect(screen.queryByText("six.pdf")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Remove 3.pdf" }));
  expect(screen.queryByText("3.pdf")).not.toBeInTheDocument();
});
it("waits for the real terminal decision before the next upload and prevents repeated submits", async () => {
  let finish!: (value: unknown) => void;
  const posts: string[] = [];
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/documents")) {
      posts.push(((init!.body as FormData).get("file") as File).name);
      return response({ run_id: `run-${posts.length}`, replayed: false });
    }
    if (url.endsWith("/run-1"))
      return new Promise((resolve) => {
        finish = resolve;
      });
    return response({ status: "SUCCEEDED", outcome: "BLOCKED" });
  });
  vi.stubGlobal("fetch", fetcher);
  const { updated } = mount();
  select([pdf("one.pdf"), pdf("two.pdf")]);
  const button = screen.getByRole("button", { name: "Upload and process all" });
  fireEvent.click(button);
  fireEvent.click(button);
  await waitFor(() => expect(posts).toEqual(["one.pdf"]));
  await waitFor(() =>
    expect(within(row("one.pdf")).getByRole("status")).toHaveTextContent(
      "Processing",
    ),
  );
  expect(within(row("two.pdf")).getByRole("status")).toHaveTextContent(
    "Waiting",
  );
  await act(async () =>
    finish(response({ status: "SUCCEEDED", outcome: "VALIDATED" })),
  );
  await waitFor(() => expect(posts).toEqual(["one.pdf", "two.pdf"]));
  await waitFor(() =>
    expect(within(row("two.pdf")).getByRole("status")).toHaveTextContent(
      "Completed · BLOCKED",
    ),
  );
  expect(within(row("one.pdf")).getByRole("link")).toHaveAttribute(
    "href",
    "/runs/run-1",
  );
  expect(updated).toHaveBeenCalledTimes(2);
});
it("continues after 422, retries only that upload and keeps its idempotency key", async () => {
  const attempts: { name: string; key: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/documents")) {
        const file = (init!.body as FormData).get("file") as File;
        attempts.push({
          name: file.name,
          key: new Headers(init!.headers).get("Idempotency-Key")!,
        });
        if (attempts.length === 1)
          return response(
            { detail: "PDF checking could not finish. Try again." },
            422,
          );
        return response({ run_id: file.name, replayed: false });
      }
      return response({ status: "SUCCEEDED", outcome: "NEEDS_REVIEW" });
    }),
  );
  mount();
  select([pdf("failed.pdf"), pdf("good.pdf")]);
  fireEvent.click(
    screen.getByRole("button", { name: "Upload and process all" }),
  );
  await waitFor(() =>
    expect(within(row("good.pdf")).getByRole("status")).toHaveTextContent(
      "Completed",
    ),
  );
  expect(within(row("failed.pdf")).getByRole("alert")).toHaveTextContent(
    "PDF checking could not finish",
  );
  fireEvent.click(screen.getByRole("button", { name: "Retry failed.pdf" }));
  await waitFor(() =>
    expect(within(row("failed.pdf")).getByRole("status")).toHaveTextContent(
      "Completed",
    ),
  );
  expect(attempts.map((a) => a.name)).toEqual([
    "failed.pdf",
    "good.pdf",
    "failed.pdf",
  ]);
  expect(attempts[0].key).toBe(attempts[2].key);
});
it("pauses on unavailable server, sanitizes its response and resumes by explicit retry", async () => {
  let posts = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/documents"))
        return ++posts === 1
          ? response({ detail: "private server traceback" }, 502)
          : response({ run_id: "recovered" });
      return response({ status: "SUCCEEDED", outcome: "VALIDATED" });
    }),
  );
  mount();
  select([pdf("one.pdf"), pdf("two.pdf")]);
  fireEvent.click(
    screen.getByRole("button", { name: "Upload and process all" }),
  );
  await screen.findByText(/Queue paused/);
  expect(posts).toBe(1);
  expect(
    screen.queryByText(/private server traceback/),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Upload and process all" }),
  ).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Retry one.pdf" }));
  await waitFor(() =>
    expect(within(row("one.pdf")).getByRole("status")).toHaveTextContent(
      "Completed",
    ),
  );
  expect(
    screen.getByRole("button", { name: "Upload and process all" }),
  ).toBeEnabled();
});
it("retries a technically failed worker run without reuploading the accepted PDF", async () => {
  let retried = false;
  const fetcher = vi.fn(async (url: string) => {
    if (url.endsWith("/documents")) return response({ run_id: "original" });
    if (url.endsWith("/retry")) {
      retried = true;
      return response({ run_id: "retry-run" });
    }
    return response({
      status: retried ? "SUCCEEDED" : "FAILED",
      outcome: retried ? "VALIDATED" : null,
    });
  });
  vi.stubGlobal("fetch", fetcher);
  mount();
  select([pdf("worker.pdf")]);
  fireEvent.click(screen.getByRole("button", { name: "Upload and process" }));
  await screen.findByRole("button", { name: "Retry worker.pdf" });
  fireEvent.click(screen.getByRole("button", { name: "Retry worker.pdf" }));
  await waitFor(() =>
    expect(within(row("worker.pdf")).getByRole("status")).toHaveTextContent(
      "Completed",
    ),
  );
  expect(
    fetcher.mock.calls.filter(([url]) => url.endsWith("/documents")),
  ).toHaveLength(1);
  expect(within(row("worker.pdf")).getByRole("link")).toHaveAttribute(
    "href",
    "/runs/retry-run",
  );
});
it("deduplicates repeated selection and shows an existing backend run without creating a retry", async () => {
  const fetcher = vi.fn(async (url: string) =>
    url.endsWith("/documents")
      ? response({ run_id: "existing", replayed: true })
      : response({ status: "SUCCEEDED", outcome: "BLOCKED" }),
  );
  vi.stubGlobal("fetch", fetcher);
  const { accepted } = mount();
  const file = pdf("same.pdf");
  select([file]);
  select([file]);
  expect(screen.getAllByText("same.pdf")).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "Upload and process" }));
  await waitFor(() =>
    expect(accepted).toHaveBeenCalledWith("existing", true, true),
  );
  await waitFor(() =>
    expect(within(row("same.pdf")).getByRole("status")).toHaveTextContent(
      "Completed · BLOCKED",
    ),
  );
  expect(fetcher.mock.calls.some(([url]) => url.endsWith("/retry"))).toBe(
    false,
  );
});
it("cancels the queue on workspace change and never uploads waiting files in the new workspace", async () => {
  setActiveWorkspace("first");
  let finish!: (value: unknown) => void;
  const fetcher = vi.fn(async (url: string) =>
    url.endsWith("/documents")
      ? new Promise((resolve) => {
          finish = resolve;
        })
      : response({}),
  );
  vi.stubGlobal("fetch", fetcher);
  const view = mount();
  select([pdf("one.pdf"), pdf("two.pdf")]);
  fireEvent.click(
    screen.getByRole("button", { name: "Upload and process all" }),
  );
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  setActiveWorkspace("second");
  view.unmount();
  await act(async () => finish(response({ run_id: "old" })));
  expect(fetcher).toHaveBeenCalledTimes(1);
});
it("refresh never automatically resubmits file data", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  const view = mount();
  select([pdf("unsubmitted.pdf")]);
  view.unmount();
  mount();
  expect(screen.queryByText("unsubmitted.pdf")).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Upload and process" }),
  ).toBeDisabled();
  expect(fetcher).not.toHaveBeenCalled();
});
