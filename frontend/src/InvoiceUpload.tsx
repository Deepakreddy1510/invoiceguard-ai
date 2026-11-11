import { useEffect, useRef, useState } from "react";
import { request, RequestError } from "./client";
import { Dialog } from "./Experience";
import { Icon } from "./icons";
import { PdfPreview } from "./ui";
import type { RunDetail } from "./models";

type Entry = {
  id: string;
  file: File;
  key: string;
  mode?: string;
  status: "Waiting" | "Uploading" | "Processing" | "Completed" | "Failed";
  runId?: string;
  retryRun?: boolean;
  outcome?: string | null;
  error?: string;
};
const limit = 5;
const maxBytes = 10 * 1024 * 1024;
export default function InvoiceUpload({
  open,
  onClose,
  onAccepted,
  onUpdated,
  capabilities,
}: {
  open: boolean;
  onClose: () => void;
  onAccepted: (id: string, replayed: boolean, autoSelect: boolean) => void;
  onUpdated: () => void;
  capabilities?: {
    can_select_extraction_mode: boolean;
    gemini_configured: boolean;
    vendor_count: number;
    po_count: number;
  };
}) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const current = useRef<Entry[]>([]);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [paused, setPaused] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState("AUTO");
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const lifetime = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    return () => controller.abort();
  }, []);
  function update(next: Entry[]) {
    current.current = next;
    setEntries(next);
  }
  function patch(id: string, changes: Partial<Entry>) {
    update(
      current.current.map((e) => (e.id === id ? { ...e, ...changes } : e)),
    );
  }
  function choose(files: File[]) {
    if (lock.current) return;
    setError("");
    if (input.current) input.current.value = "";
    if (current.current.length + files.length > limit) {
      setError("Choose up to five PDFs per batch.");
      return;
    }
    const next = [...current.current];
    for (const file of files) {
      if (
        !/\.pdf$/i.test(file.name) ||
        (file.type &&
          !["application/pdf", "application/x-pdf"].includes(file.type))
      ) {
        setError(
          "Choose a PDF document (.pdf). Other file types are not supported.",
        );
        continue;
      }
      if (file.size > maxBytes) {
        setError("This PDF exceeds the 10 MiB limit.");
        continue;
      }
      if (!file.size) {
        setError("This PDF is empty. Choose a readable invoice.");
        continue;
      }
      if (
        next.some(
          (e) =>
            e.file.name === file.name &&
            e.file.size === file.size &&
            e.file.lastModified === file.lastModified,
        )
      )
        continue;
      next.push({
        id: crypto.randomUUID(),
        key: crypto.randomUUID(),
        file,
        status: "Waiting",
      });
    }
    update(next);
  }
  async function start(ids: string[]) {
    // Synchronous guard prevents repeated clicks before React renders disabled controls.
    if (lock.current || !ids.length) return;
    const signal = lifetime.current!.signal;
    lock.current = true;
    setBusy(true);
    setError("");
    setPaused(false);
    const single = current.current.length === 1;
    try {
      for (const id of ids) {
        if (signal.aborted) break;
        const entry = current.current.find((e) => e.id === id)!;
        if (entry.status === "Completed") continue;
        try {
          let runId = entry.runId;
          if (!runId || entry.retryRun) {
            patch(id, {
              status: "Uploading",
              error: undefined,
              mode: entry.mode ?? mode,
            });
            let replayed = false;
            if (runId) {
              const result = await request<{ run_id: string }>(
                `/runs/${runId}/retry`,
                { method: "POST", signal },
              );
              runId = result.run_id;
            } else {
              const body = new FormData();
              body.append("file", entry.file);
              body.append("extraction_mode", entry.mode ?? mode);
              const result = await request<{
                run_id: string;
                replayed: boolean;
              }>("/documents", {
                method: "POST",
                body,
                signal,
                headers: { "Idempotency-Key": entry.key },
              });
              runId = result.run_id;
              replayed = result.replayed;
            }
            if (signal.aborted) break;
            patch(id, { runId, retryRun: false, status: "Processing" });
            onAccepted(runId, replayed, single);
            if (single) onClose();
          } else patch(id, { status: "Processing", error: undefined });
          // Wait for the actual terminal run before the next upload/inspection.
          const deadline = Date.now() + 5 * 60 * 1000;
          while (!signal.aborted) {
            const run = await request<RunDetail>(`/runs/${runId}`, { signal });
            if (signal.aborted) break;
            if (run.status === "SUCCEEDED" || run.status === "FAILED") {
              patch(id, {
                status: run.status === "SUCCEEDED" ? "Completed" : "Failed",
                outcome: run.outcome,
                retryRun: run.status === "FAILED",
                error:
                  run.status === "FAILED"
                    ? "Processing could not finish. Open the timeline for details, then retry."
                    : undefined,
              });
              onUpdated();
              break;
            }
            if (Date.now() >= deadline)
              throw new RequestError(
                "Processing is taking longer than expected. Check this run before continuing the queue.",
                503,
              );
            await new Promise<void>((resolve) => {
              const done = () => {
                clearTimeout(timer);
                signal.removeEventListener("abort", done);
                resolve();
              };
              const timer = setTimeout(done, 2000);
              signal.addEventListener("abort", done, { once: true });
              if (signal.aborted) done();
            });
          }
        } catch (cause) {
          if (signal.aborted || (cause as Error).name === "AbortError") break;
          const unavailable =
            !(cause instanceof RequestError) ||
            cause.status >= 500 ||
            [401, 403].includes(cause.status);
          patch(id, {
            status: "Failed",
            error:
              cause instanceof RequestError
                ? cause.message
                : "Could not reach the service. Check your connection, then retry this file.",
          });
          if (unavailable) {
            setPaused(true);
            break;
          }
        }
      }
    } finally {
      lock.current = false;
      if (!signal.aborted) setBusy(false);
    }
  }
  const queue = entries.length > 0 && (
    <section aria-label="PDF upload queue" className="pdf-upload-queue">
      <ul>
        {entries.map((entry) => (
          <li key={entry.id}>
            <div>
              <strong>{entry.file.name}</strong> ·{" "}
              {(entry.file.size / 1024 / 1024).toFixed(2)} MiB
            </div>
            <p role="status">
              {entry.status}
              {entry.outcome ? ` · ${entry.outcome}` : ""}
            </p>
            {entry.error && <p role="alert">{entry.error}</p>}
            {entry.runId && (
              <a
                href={`/runs/${entry.runId}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                Processing timeline and financial checks
              </a>
            )}
            {entry.status === "Waiting" && (
              <button
                type="button"
                disabled={busy}
                aria-label={
                  entries.length === 1
                    ? "Remove selected PDF"
                    : `Remove ${entry.file.name}`
                }
                onClick={() =>
                  update(current.current.filter((e) => e.id !== entry.id))
                }
              >
                Remove
              </button>
            )}
            {entry.status === "Failed" && (
              <button
                type="button"
                disabled={busy}
                onClick={() => void start([entry.id])}
              >
                Retry {entry.file.name}
              </button>
            )}
          </li>
        ))}
      </ul>
      {paused && (
        <p role="alert">
          Queue paused. Retry the failed file before continuing.
        </p>
      )}
      <p className="footnote">
        After refresh, accepted invoices remain in invoice history. Select
        unsubmitted files again; they are never automatically resubmitted.
      </p>
    </section>
  );
  if (!open) return queue;
  return (
    <Dialog title="New invoice" onClose={onClose}>
      <section className="upload-panel">
        <h2>Process invoices</h2>
        <p>
          Up to five PDFs · 10 MiB each · 20 pages · Digital text or English
          scans. Files upload and process one at a time.
        </p>
        {capabilities &&
          (!capabilities.vendor_count || !capabilities.po_count) && (
            <p className="notice">
              Start by adding a vendor and creating a purchase order.{" "}
              <a href="/vendors">Manage vendors</a> ·{" "}
              <a href="/purchase-orders">Create purchase order</a>
            </p>
          )}
        <label>
          Extraction mode
          <select
            aria-label="Extraction mode"
            value={mode}
            disabled={busy || entries.some((e) => !!e.mode)}
            onChange={(e) => setMode(e.target.value)}
          >
            <option value="AUTO">Automatic — Recommended</option>
            {capabilities?.can_select_extraction_mode && (
              <>
                <option
                  value="GEMINI"
                  disabled={!capabilities.gemini_configured}
                >
                  AI-assisted
                </option>
                <option value="FALLBACK">Standard extraction</option>
              </>
            )}
          </select>
        </label>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!paused)
              void start(
                current.current
                  .filter((e) => e.status === "Waiting")
                  .map((e) => e.id),
              );
          }}
        >
          <input
            ref={input}
            className="sr-only"
            aria-label="Invoice PDF"
            type="file"
            accept="application/pdf,.pdf"
            multiple
            disabled={busy}
            onChange={(e) => choose(Array.from(e.target.files ?? []))}
          />
          <button
            type="button"
            className={"dropzone " + (drag ? "is-dragging" : "")}
            disabled={busy}
            onClick={() => input.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              choose(Array.from(e.dataTransfer.files));
            }}
          >
            <Icon name="upload" /> Drop your invoice PDFs here or choose files
          </button>
          {queue}
          {entries.length === 1 && entries[0].status === "Waiting" && (
            <details className="source-panel upload-preview">
              <summary>Preview selected PDF</summary>
              <PdfPreview file={entries[0].file} />
            </details>
          )}
          {error && (
            <p role="alert" className="inline-error">
              {error}
            </p>
          )}
          <button
            className="primary"
            type="submit"
            disabled={
              busy || paused || !entries.some((e) => e.status === "Waiting")
            }
          >
            {busy
              ? "Processing queue…"
              : entries.length > 1
                ? "Upload and process all"
                : "Upload and process"}
          </button>
          {!busy &&
            entries.length > 0 &&
            !entries.some((e) =>
              ["Waiting", "Uploading", "Processing"].includes(e.status),
            ) && (
              <button
                type="button"
                onClick={() => {
                  update([]);
                  setPaused(false);
                  setError("");
                }}
              >
                Start a new batch
              </button>
            )}
        </form>
      </section>
    </Dialog>
  );
}
