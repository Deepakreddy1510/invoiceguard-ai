import InvoiceUpload from "./InvoiceUpload";
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
  const uploadSelection = useRef(0);
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
  const capabilities = useResource<{
    can_manage_procurement: boolean;
    can_select_extraction_mode: boolean;
    gemini_configured: boolean;
    vendor_count: number;
    po_count: number;
  }>("/me");
  const [error, setError] = useState("");
  const [operation, setOperation] = useState<
    "upload" | "retry" | "review" | "organize"
  >("upload");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");
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
            onClick={() => {
              uploadSelection.current = manual.current;
              setUploadOpen(true);
            }}
          >
            + New invoice
          </button>
        }
      />
      <InvoiceUpload
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        capabilities={capabilities.data ?? undefined}
        onAccepted={(id, replayed, autoSelect) => {
          if (!replayed) watched.current.add(id);
          setMessage(
            replayed
              ? "Already uploaded — showing the existing processing record."
              : "Invoice received. Follow its recorded progress and decision.",
          );
          if (autoSelect && manual.current === uploadSelection.current) {
            focusRun.current = id;
            selectRun(id, false);
          }
          setOffset(0);
          history.reload();
        }}
        onUpdated={history.reload}
      />
      {message && !uploadOpen && (
        <p role="status" className="submission-message">
          {message}
        </p>
      )}
      <Notice
        error={error}
        onRetry={
          operation === "retry"
            ? retry
            : operation === "organize"
              ? organize
              : review
        }
      />
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
