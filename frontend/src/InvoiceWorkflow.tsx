import { InvoiceIdentity } from "./InvoiceIdentity";
import { Help } from "./Experience";
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
import { Dialog } from "./Experience";
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
  const [visibility, setVisibility] = useState("active");
  const [archiveConfirm, setArchiveConfirm] = useState(false);
  const [search, setSearch] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [mobileDetail, setMobileDetail] = useState(
    !!initialRunId || !!new URLSearchParams(window.location.search).get("run"),
  );
  const [mode, setMode] = useState("AUTO");
  const capabilities = useResource<{
    can_manage_procurement: boolean;
    can_select_extraction_mode: boolean;
    gemini_configured: boolean;
    vendor_count: number;
    po_count: number;
  }>("/me");
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState("");
  const [error, setError] = useState("");
  const [operation, setOperation] = useState<
    "upload" | "retry" | "review" | "organize"
  >("upload");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [toast, setToast] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const runPanel = useRef<HTMLElement>(null);
  const focusRun = useRef<string | null>(null);
  const history = useResource<{ runs: RunSummary[] }>(
    `/runs?offset=${offset}&limit=20&visibility=${visibility}&search=${encodeURIComponent(search)}${filter ? "&outcome=" + filter : ""}`,
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
      setMobileDetail(true);
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
      body.append("extraction_mode", mode);
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
          : "Invoice received. Follow its progress and decision below.",
      );
      if (manual.current === selectionAtStart) {
        focusRun.current = result.run_id;
        selectRun(result.run_id, false);
      }
      setUploadOpen(false);
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
  async function organize() {
    if (!detail.data || busy) return;
    setOperation("organize");
    setBusy(true);
    setError("");
    try {
      await request("/documents/" + detail.data.document_id + "/visibility", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archived: !detail.data.archived_at }),
      });
      setArchiveConfirm(false);
      setMessage(
        detail.data.archived_at
          ? "Invoice restored to the active queue."
          : "Invoice archived from the queue. Its PDF, decisions and reserved capacity are retained.",
      );
      history.reload();
      detail.reload();
    } catch (cause) {
      setError((cause as Error).message);
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
    <section
      className={
        "workflow invoice-workbench " +
        (mobileDetail ? "show-detail" : "show-queue")
      }
      aria-label="Invoice processing workbench"
    >
      <PageTitle
        eyebrow="VERIFICATION / INVOICE PROCESSING"
        title="Invoice workbench"
        description="Your invoice queue, recorded decisions and source documents in one place."
        action={
          <button
            className="primary"
            disabled={busy}
            onClick={() => setUploadOpen(true)}
          >
            + New invoice
          </button>
        }
      />
      {uploadOpen && (
        <Dialog title="New invoice" onClose={() => setUploadOpen(false)}>
          <section className="upload-panel">
            <div className="upload-intro">
              <span className="section-index">01</span>
              <div>
                <h2 id="processing-title">Process an invoice</h2>
                <p>
                  PDF documents up to 10 MiB · 20 pages · Digital text or
                  English scans
                </p>
              </div>
            </div>
            {capabilities.data &&
              (capabilities.data.vendor_count === 0 ||
                capabilities.data.po_count === 0) && (
                <div className="notice">
                  Start by adding a vendor and creating a purchase order. Then
                  upload your first invoice.{" "}
                  <a href="/vendors">Manage vendors</a> ·{" "}
                  <a href="/purchase-orders">Create purchase order</a>
                </div>
              )}
            <div className="extraction-mode">
              <label htmlFor="extraction-mode">Extraction mode</label>
              <select
                id="extraction-mode"
                aria-label="Extraction mode"
                disabled={busy}
                value={mode}
                onChange={(e) => {
                  setMode(e.target.value);
                  uploadKey.current = null;
                }}
              >
                <option value="AUTO">Automatic — Recommended</option>
                {capabilities.data?.can_select_extraction_mode && (
                  <>
                    <option
                      value="GEMINI"
                      disabled={!capabilities.data.gemini_configured}
                    >
                      AI-assisted
                      {!capabilities.data.gemini_configured
                        ? " — not configured"
                        : ""}
                    </option>
                    <option value="FALLBACK">Standard extraction</option>
                  </>
                )}
              </select>
              <p className="footnote">
                {mode === "AUTO"
                  ? capabilities.data?.gemini_configured
                    ? "Uses Gemini when available, with standard extraction as a backup. The actual method is recorded on each invoice."
                    : "Uses standard extraction. Gemini is not configured. The same financial checks apply."
                  : mode === "GEMINI"
                    ? "Uses Gemini-assisted extraction. If it cannot complete, processing stops and the failure is recorded."
                    : "Uses built-in document reading, including scanned PDFs. The same supplier, order and financial checks always apply."}
                {capabilities.data?.can_select_extraction_mode &&
                  !capabilities.data.gemini_configured &&
                  " AI-assisted reading is not available in this workspace yet. Standard extraction is available."}
              </p>
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
                  <span id="upload-help">
                    Upload an invoice PDF. Scanned invoices are supported.
                  </span>
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
                    Your document is checked by the actual verification
                    pipeline.
                  </p>
                )}
                <button
                  className="primary"
                  disabled={!file || busy}
                  type="submit"
                >
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
        </Dialog>
      )}
      {busy && operation === "upload" && !uploadOpen && (
        <p role="status">
          Uploading document… You can continue browsing the queue.
        </p>
      )}
      {message && !uploadOpen && (
        <p role="status" className="submission-message">
          {message}
        </p>
      )}
      {!uploadOpen && (
        <Notice
          error={error}
          onRetry={
            operation === "upload"
              ? () => void upload()
              : operation === "retry"
                ? retry
                : operation === "organize"
                  ? organize
                  : review
          }
        />
      )}
      <div className="workflow-columns">
        <section className="panel history">
          <div className="section-heading">
            <div>
              <p className="eyebrow">YOUR WORKSPACE</p>
              <h2>Invoice queue</h2>
            </div>
            <span className="tag">{runs.length} on this page</span>
          </div>
          <p className="footnote">
            Runs include retries and duplicate assessments, counted separately
            from unique invoices.
          </p>
          <label className="queue-visibility">
            Show invoices
            <select
              aria-label="Queue visibility"
              value={visibility}
              onChange={(event) => {
                setVisibility(event.target.value);
                setOffset(0);
              }}
            >
              <option value="active">Active queue</option>
              <option value="archived">Archived invoices</option>
              <option value="all">All invoices</option>
            </select>
          </label>
          <label className="search-field">
            <span className="sr-only">Search invoice history</span>
            <input
              aria-label="Search invoice history"
              placeholder="Invoice, vendor or PO"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setOffset(0);
              }}
            />
          </label>
          <FilterChips
            label="Filter run history"
            value={filter}
            onChange={(value) => {
              setFilter(value);
              setOffset(0);
            }}
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
              title={
                runs.length
                  ? "No matching processing records"
                  : "No invoices yet"
              }
            >
              {runs.length
                ? "Choose another outcome filter."
                : "Upload your first PDF to start a recorded verification."}
            </EmptyState>
          ) : (
            <div
              className="history-list"
              role="region"
              aria-label="Scrollable invoice queue"
              tabIndex={0}
            >
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
                    <InvoiceIdentity
                      number={run.invoice_number}
                      supplier={run.vendor_name ?? null}
                      fallback={
                        isTerminal(run)
                          ? "Invoice number missing"
                          : "New invoice · awaiting details"
                      }
                    />
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
          tabIndex={0}
          className="panel run-detail"
          aria-label="Processing run"
        >
          <button className="queue-back" onClick={() => setMobileDetail(false)}>
            ← Back to invoice queue
          </button>
          <Notice error={detail.error} onRetry={detail.reload} />
          {detail.data && capabilities.data?.can_manage_procurement && (
            <div className="queue-organization">
              <button
                type="button"
                disabled={busy}
                onClick={() => setArchiveConfirm(true)}
              >
                {detail.data.archived_at
                  ? "Restore invoice to queue"
                  : "Archive invoice from queue"}
              </button>
              {detail.data.archived_at && (
                <span className="tag">Archived from queue</span>
              )}
            </div>
          )}
          {archiveConfirm && (
            <Dialog
              title="Organize invoice queue"
              onClose={() => !busy && setArchiveConfirm(false)}
            >
              <p>
                Archiving only hides this document and its processing attempts
                from the active queue. The original PDF, decisions, reviews,
                duplicate checks and reserved or settled capacity stay intact.
                Dashboard totals still include archived invoices.
              </p>
              <p>
                Use Archived invoices to find it again. To dispute an invoice,
                use source review; archiving does not reverse a financial
                decision.
              </p>
              <Notice error={error} />
              <button disabled={busy} onClick={() => void organize()}>
                {detail.data?.archived_at
                  ? "Confirm restore"
                  : "Confirm archive"}
              </button>
              <button disabled={busy} onClick={() => setArchiveConfirm(false)}>
                Cancel
              </button>
            </Dialog>
          )}
          {detail.data ? (
            <RunDetails
              key={detail.data.id}
              run={detail.data}
              busy={busy}
              onRetry={retry}
              onSelect={selectRun}
              onReview={review}
            />
          ) : selected ? (
            <>
              <p className="eyebrow">RETRIEVING PERSISTED RUN</p>
              <span>The selected invoice is loading.</span>
              {!detail.error && (
                <Skeleton label="Loading persisted run" rows={4} />
              )}
            </>
          ) : history.loading ? (
            <Skeleton label="Loading latest run" rows={4} />
          ) : (
            <EmptyState title="Ready when you are">
              Upload an invoice to follow its recorded stages, source evidence
              and financial checks.
            </EmptyState>
          )}
        </section>
        <aside
          className="panel workbench-document"
          aria-label="Source document panel"
        >
          <div className="section-heading">
            <h2>Original invoice</h2>
            <span>Source document</span>
          </div>
          {detail.data ? (
            <PdfPreview documentId={detail.data.document_id} />
          ) : (
            <p className="muted-text">
              Select an invoice to compare its original PDF.
            </p>
          )}
        </aside>
      </div>
      <Help title="How invoice history is protected">
        <p>
          Uploads and financial commitments retain their audit history. Source
          corrections are revalidated; unsettled holds can be released only
          through an explicit review action. Settled amounts cannot be removed
          by deleting an upload.
        </p>
      </Help>
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
