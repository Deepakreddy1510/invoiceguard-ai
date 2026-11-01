import { useCallback, useEffect, useRef, useState } from "react";
import { request, money, relativeTime } from "./client";
import {
  amount,
  isTerminal,
  outcomes,
  type RunDetail,
  type RunSummary,
} from "./models";
import {
  EmptyState,
  FilterChips,
  humanize,
  Notice,
  PageTitle,
  PdfPreview,
  Skeleton,
  Status,
  useResource,
} from "./ui";
import { Icon } from "./icons";
import RunDetails from "./RunDetails";
import { useRunDetails } from "./run-data";
const stopRun = (run: RunDetail) => isTerminal(run);
const emptyRuns: RunSummary[] = [];
const maxBytes = 10 * 1024 * 1024;
export default function InvoiceWorkflow({
  initialRunId,
  onSelectRun,
}: { initialRunId?: string; onSelectRun?: (id: string) => void } = {}) {
  const [selected, setSelected] = useState<string | null>(
    () =>
      initialRunId ?? new URLSearchParams(window.location.search).get("run"),
  );
  const selectedRef = useRef(selected);
  const manual = useRef(0);
  const uploadKey = useRef<string | null>(null);
  const watched = useRef(new Set<string>());
  const [offset, setOffset] = useState(0);
  const [filter, setFilter] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState("");
  const [error, setError] = useState("");
  const [operation, setOperation] = useState<"upload" | "retry" | "review">(
    "upload",
  );
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [toast, setToast] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const runPanel = useRef<HTMLElement>(null);
  const focusRun = useRef<string | null>(null);
  const history = useResource<{ runs: RunSummary[] }>(
    `/runs?offset=${offset}&limit=20`,
    1500,
  );
  const detail = useResource<RunDetail>(
    selected ? "/runs/" + selected : null,
    1000,
    stopRun,
  );
  const runs = history.data?.runs ?? emptyRuns;
  const extras = useRunDetails(runs);
  const selectRun = useCallback(
    (id: string, manualChoice = true) => {
      if (manualChoice) {
        manual.current += 1;
        focusRun.current = null;
      }
      selectedRef.current = id;
      setSelected(id);
      if (onSelectRun) onSelectRun(id);
      else {
        const url = new URL(window.location.href);
        url.searchParams.set("run", id);
        window.history.replaceState({}, "", url);
      }
    },
    [onSelectRun],
  );
  useEffect(() => {
    if (initialRunId && initialRunId !== selectedRef.current) {
      manual.current += 1;
      selectedRef.current = initialRunId;
      setSelected(initialRunId);
    }
  }, [initialRunId]);
  useEffect(() => {
    if (!selectedRef.current && runs.length) selectRun(runs[0].id, false);
  }, [runs, selectRun]);
  useEffect(() => {
    for (const run of [...runs, ...(detail.data ? [detail.data] : [])]) {
      if (!isTerminal(run)) watched.current.add(run.id);
      if (watched.current.has(run.id) && isTerminal(run)) {
        watched.current.delete(run.id);
        setToast(
          run.status === "FAILED"
            ? "Invoice processing failed. Open the run to inspect the technical error."
            : `Invoice ${run.invoice_number ?? run.id.slice(0, 8)}: ${humanize(run.outcome ?? "SUCCEEDED")}`,
        );
      }
    }
  }, [runs, detail.data]);
  useEffect(() => {
    if (detail.data && focusRun.current === detail.data.id) {
      focusRun.current = null;
      runPanel.current?.scrollIntoView?.({ block: "start" });
      runPanel.current?.focus({ preventScroll: true });
    }
  }, [detail.data, message]);
  function chooseFile(next: File | null) {
    setFile(null);
    uploadKey.current = null;
    setFileError("");
    setMessage("");
    if (input.current) input.current.value = "";
    if (!next) return;
    if (
      !/\.pdf$/i.test(next.name) ||
      (next.type &&
        !["application/pdf", "application/x-pdf"].includes(next.type))
    ) {
      setFileError(
        "Choose a PDF document (.pdf). Other file types are not supported.",
      );
      return;
    }
    if (next.size > maxBytes) {
      setFileError(
        "This PDF exceeds the 10 MiB limit. Choose a smaller document.",
      );
      return;
    }
    if (next.size === 0) {
      setFileError("This PDF is empty. Choose a readable invoice.");
      return;
    }
    setFile(next);
  }
  async function upload(e?: React.FormEvent) {
    setOperation("upload");
    e?.preventDefault();
    if (!file || busy) return;
    const selectionAtStart = manual.current;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const body = new FormData();
      body.append("file", file);
      const result = await request<{ run_id: string; replayed: boolean }>(
        "/documents",
        {
          method: "POST",
          body,
          headers: {
            "Idempotency-Key": (uploadKey.current ??= crypto.randomUUID()),
          },
        },
      );
      if (!result.replayed) watched.current.add(result.run_id);
      setMessage(
        result.replayed
          ? "Already uploaded — showing the existing processing record."
          : "PDF accepted. Following the persisted processing run.",
      );
      if (manual.current === selectionAtStart) {
        focusRun.current = result.run_id;
        selectRun(result.run_id, false);
      }
      setOffset(0);
      history.reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function retry() {
    setOperation("retry");
    if (!selected || busy) return;
    const atStart = manual.current;
    setBusy(true);
    setError("");
    try {
      const result = await request<{ run_id: string }>(
        "/runs/" + selected + "/retry",
        { method: "POST" },
      );
      watched.current.add(result.run_id);
      if (manual.current === atStart) selectRun(result.run_id, false);
      history.reload();
      setMessage("Retry queued. The original failed run remains in history.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function review() {
    setOperation("review");
    if (!selected || busy) return;
    setBusy(true);
    try {
      const task = await request<{ id: string }>(
        "/runs/" + selected + "/review",
        { method: "POST" },
      );
      window.location.assign("/reviews/" + task.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const shown = runs.filter((r) => !filter || r.outcome === filter);
  return (
    <section className="workflow" aria-labelledby="processing-title">
      <PageTitle
        eyebrow="VERIFICATION / INVOICE PROCESSING"
        title="From invoice to informed decision."
        description="Upload a document. Follow the evidence. Understand every financial decision."
      />
      <section className="panel upload-panel">
        <div className="upload-intro">
          <span className="section-index">01</span>
          <div>
            <h2 id="processing-title">Process an invoice</h2>
            <p>
              PDF documents up to 10 MiB · 20 pages · Digital text or English
              scans
            </p>
          </div>
        </div>
        <form onSubmit={upload} className="upload-form">
          <input
            className="sr-only"
            id="invoice-pdf"
            ref={input}
            tabIndex={-1}
            type="file"
            accept="application/pdf,.pdf"
            aria-label="Invoice PDF"
            aria-describedby="upload-help"
            onChange={(e) => chooseFile(e.target.files?.[0] ?? null)}
          />
          <button
            type="button"
            className={"dropzone " + (drag ? "is-dragging" : "")}
            onClick={() => input.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              if (e.dataTransfer.files.length !== 1) {
                setFileError("Choose one PDF at a time.");
                return;
              }
              chooseFile(e.dataTransfer.files[0]);
            }}
          >
            <span className="dropzone-icon">
              <Icon name="upload" />
            </span>
            <span>
              <strong>
                {file ? "Choose a different PDF" : "Drop your invoice here"}
              </strong>
              <span id="upload-help">or click to browse your files</span>
            </span>
            <span className="file-format">PDF</span>
          </button>
          <div className="upload-action">
            {file ? (
              <div className="selected-file">
                <Icon name="file" />
                <div>
                  <strong>{file.name}</strong>
                  <span>{(file.size / 1024 / 1024).toFixed(2)} MiB</span>
                </div>
                <button
                  type="button"
                  className="icon-button"
                  aria-label="Remove selected PDF"
                  onClick={() => chooseFile(null)}
                >
                  <Icon name="close" />
                </button>
              </div>
            ) : (
              <p className="muted-text">
                Your document is checked by the actual verification pipeline.
              </p>
            )}
            <button className="primary" disabled={!file || busy} type="submit">
              <Icon name="arrow" />
              {busy ? "Submitting…" : "Upload and process"}
            </button>
          </div>
        </form>
        {fileError && (
          <p className="inline-error" role="alert">
            {fileError}
          </p>
        )}
        {file && (
          <details className="source-panel upload-preview">
            <summary>Preview selected PDF</summary>
            <PdfPreview file={file} />
          </details>
        )}
        {message && (
          <p role="status" className="submission-message">
            <Icon name="check" />
            {message}
          </p>
        )}
        <Notice
          error={error}
          onRetry={() => {
            if (operation === "upload") void upload();
            else if (operation === "retry") void retry();
            else void review();
          }}
        />
      </section>
      <div className="workflow-columns">
        <section className="panel history">
          <div className="section-heading">
            <div>
              <p className="eyebrow">YOUR WORKSPACE</p>
              <h2>Processing history</h2>
            </div>
            <span className="tag">{runs.length} on this page</span>
          </div>
          <p className="footnote">
            Runs include retries and duplicate assessments, counted separately
            from unique invoices.
          </p>
          <FilterChips
            label="Filter run history"
            value={filter}
            onChange={setFilter}
            options={[
              { value: "", label: "All" },
              ...outcomes.map((v) => ({ value: v, label: humanize(v) })),
            ]}
          />
          <Notice error={history.error} onRetry={history.reload} />
          {history.loading ? (
            <Skeleton label="Loading processing history" rows={4} />
          ) : !shown.length && !history.error ? (
            <EmptyState
              title={runs.length ? "No matching runs" : "No invoices yet"}
            >
              {runs.length
                ? "Choose another outcome filter."
                : "Upload your first PDF to start a recorded verification."}
            </EmptyState>
          ) : (
            <div className="history-list">
              {shown.map((run) => {
                const total = amount(extras[run.id]);
                const rules = extras[run.id]?.decision?.rules;
                return (
                  <button
                    type="button"
                    className={
                      "history-run " + (selected === run.id ? "selected" : "")
                    }
                    key={run.id}
                    aria-pressed={selected === run.id}
                    onClick={() => selectRun(run.id)}
                  >
                    <div className="history-row-top">
                      <strong>
                        {run.invoice_number ?? "Invoice number missing"}
                      </strong>
                      <Icon name="chevron" />
                    </div>
                    {run.vendor_name && (
                      <span className="history-vendor">{run.vendor_name}</span>
                    )}
                    {total && (
                      <strong className="history-amount">
                        {total.currency
                          ? money(total.value, total.currency)
                          : total.value}
                      </strong>
                    )}
                    <div className="history-outcome">
                      {run.outcome ? (
                        <Status value={run.outcome} />
                      ) : (
                        <span className="muted-text">Awaiting decision</span>
                      )}
                      {run.parent_run_id && (
                        <span className="tag">
                          {extras[run.id]?.events.some(
                            (e) => e.stage === "retry",
                          )
                            ? "Retry"
                            : extras[run.id]?.events.some(
                                  (e) => e.stage === "review",
                                )
                              ? "Review revision"
                              : "Related run"}
                        </span>
                      )}
                      {rules?.some(
                        (r) => r.rule_id === "BUSINESS_DUPLICATE",
                      ) && <span className="tag">Duplicate</span>}
                    </div>
                    <div className="history-row-bottom">
                      <span>{humanize(run.status)}</span>
                      <time
                        dateTime={run.created_at}
                        title={whenDate(run.created_at)}
                      >
                        {relativeTime(run.created_at)}
                      </time>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
          <div className="pagination">
            <button
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 20))}
            >
              Newer
            </button>
            <button
              disabled={runs.length < 20}
              onClick={() => setOffset(offset + 20)}
            >
              Older
            </button>
          </div>
        </section>
        <section
          ref={runPanel}
          tabIndex={-1}
          className="panel run-detail"
          aria-label="Processing run"
        >
          <Notice error={detail.error} onRetry={detail.reload} />
          {detail.data ? (
            <RunDetails
              run={detail.data}
              busy={busy}
              onRetry={retry}
              onSelect={selectRun}
              onReview={review}
            />
          ) : selected ? (
            <>
              <p className="eyebrow">RETRIEVING PERSISTED RUN</p>
              <code>{selected}</code>
              {!detail.error && (
                <Skeleton label="Loading persisted run" rows={4} />
              )}
            </>
          ) : history.loading ? (
            <Skeleton label="Loading latest run" rows={4} />
          ) : (
            <EmptyState title="Your next decision starts here">
              Upload an invoice to follow its recorded stages, source evidence
              and financial checks.
            </EmptyState>
          )}
        </section>
      </div>
      {toast && (
        <div className="toast" role="status">
          <Icon name="check" />
          <span>{toast}</span>
          <button
            className="icon-button"
            aria-label="Dismiss completion notification"
            onClick={() => setToast("")}
          >
            <Icon name="close" />
          </button>
        </div>
      )}
    </section>
  );
}
function whenDate(value: string) {
  return new Date(value).toLocaleString();
}
