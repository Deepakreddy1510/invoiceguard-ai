import { POComparison } from "./POComparison";
import { useEffect, useMemo, useState } from "react";
import {
  amount,
  fact,
  isTerminal,
  type Evidence,
  type RunDetail,
  type RunEvent,
  type Rule,
} from "./models";
import { duration, money, when } from "./client";
import { CopyButton, humanize, PdfPreview, Status } from "./ui";
import { TechnicalDetails } from "./TechnicalDetails";
import {
  checkGroup,
  checkGroups,
  checkExplanation,
  ruleLabel,
  nextAction,
  primaryIssues,
} from "./business";
import { Icon } from "./icons";
const stageNames: Record<string, string> = {
  ingestion: "Invoice received",
  text_extraction: "Document read",
  ocr: "Scanned document reading",
  field_extraction: "Details identified",
  validation: "Financial checks",
  decision: "Decision recorded",
  supplier_po: "Supplier and PO checked",
  review_disposition: "Reviewer disposition",
};
const pipeline = [
  "ingestion",
  "text_extraction",
  "field_extraction",
  "supplier_po",
  "validation",
  "decision",
];
export function stageInterval(events: RunEvent[], latest: RunEvent) {
  if (!["SUCCEEDED", "FAILED", "SKIPPED"].includes(latest.outcome)) return null;
  const start = [...events]
    .reverse()
    .find(
      (e) =>
        e.id < latest.id &&
        e.stage === latest.stage &&
        e.attempt === latest.attempt &&
        e.outcome === "RUNNING",
    );
  if (!start) return null;
  const ms = Date.parse(latest.created_at) - Date.parse(start.created_at);
  return Number.isFinite(ms) && ms >= 0 ? ms : null;
}
function Elapsed({ run }: { run: RunDetail }) {
  const [now, setNow] = useState(Date.now());
  const terminal = isTerminal(run);
  useEffect(() => {
    if (terminal) return;
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [run.id, terminal]);
  const end = run.finished_at
    ? Date.parse(run.finished_at)
    : !isTerminal(run)
      ? now
      : null;
  if (end == null) return null;
  return (
    <span title="Wall time from the persisted run creation timestamp, including queue time">
      <Icon name="clock" /> {isTerminal(run) ? "Run duration" : "Elapsed"}{" "}
      {duration(end - Date.parse(run.created_at))}
    </span>
  );
}
export function ExtractedFields({
  run,
}: {
  run: Pick<RunDetail, "extraction" | "document_id">;
}) {
  if (!run.extraction) return null;
  const fieldOrder = [
    "invoice_number",
    "invoice_date",
    "vendor_name",
    "vendor_code",
    "tax_id",
    "po_number",
    "currency",
    "pricing_mode",
    "subtotal",
    "discount",
    "charges",
    "tax",
    "total",
  ];
  const values = Object.entries(run.extraction.fields).filter(
    (entry): entry is [string, Evidence] =>
      !!entry[1] &&
      typeof entry[1] === "object" &&
      !Array.isArray(entry[1]) &&
      "value" in entry[1],
  );
  values.sort(
    ([a], [b]) =>
      (fieldOrder.includes(a) ? fieldOrder.indexOf(a) : 999) -
      (fieldOrder.includes(b) ? fieldOrder.indexOf(b) : 999),
  );
  return (
    <div className="extraction-output">
      <div className="output-heading">
        <h4>Extracted fields</h4>
      </div>
      {run.extraction.fallback_reason && (
        <details className="extraction-note">
          <summary>Extraction notes</summary>
          <p className="footnote">
            Conservative extraction was used. Check source evidence for any
            uncertain values.
          </p>
        </details>
      )}
      <div className="table-scroll">
        <table className="evidence-table">
          <thead>
            <tr>
              <th>Field & value</th>
              <th>Source evidence</th>
            </tr>
          </thead>
          <tbody>
            {values.map(([name, value]) => (
              <tr key={name}>
                <td>
                  <span className="field-name">{humanize(name)}</span>
                  <strong>
                    {value.value
                      ? humanizeValue(name, value.value)
                      : "Not found in document"}
                  </strong>
                  {!value.verified && (
                    <span className="evidence-flag">Review required</span>
                  )}
                </td>
                <td>
                  <details>
                    <summary>View source evidence</summary>
                    <span
                      className={
                        value.verified ? "evidence-verified" : "evidence-flag"
                      }
                    >
                      {value.verified
                        ? "Source verified"
                        : "Unverified or missing"}
                    </span>
                    {(value.page != null || value.method) && (
                      <span className="vendor">
                        {[
                          value.page != null ? "Page " + value.page : null,
                          value.method ? humanize(value.method) : null,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    )}
                    {value.quote && <blockquote>{value.quote}</blockquote>}
                    {value.reviewer && <small>Confirmed by a reviewer</small>}
                  </details>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {run.extraction.fields.issues?.length ? (
        <ul className="source-issues">
          {run.extraction.fields.issues.map((issue, i) => (
            <li key={i}>{issue}</li>
          ))}
        </ul>
      ) : null}
      {!!run.extraction.fields.items?.length && (
        <details className="line-items">
          <summary>
            Extracted line items ({run.extraction.fields.items.length})
          </summary>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Item / evidence</th>
                  <th className="amount">Quantity × unit price</th>
                  <th className="amount">Net / tax / gross</th>
                </tr>
              </thead>
              <tbody>
                {run.extraction.fields.items.map((item, index) => (
                  <tr key={index}>
                    <td>
                      {item.sku?.value ?? "Unresolved item"}
                      {item.sku?.page != null && (
                        <span className="vendor">Page {item.sku.page}</span>
                      )}
                      {item.sku?.quote && (
                        <blockquote>{item.sku.quote}</blockquote>
                      )}
                      <span
                        className={
                          Object.values(item).every((v) => v.verified)
                            ? "evidence-verified"
                            : "evidence-flag"
                        }
                      >
                        {Object.values(item).every((v) => v.verified)
                          ? "Source verified"
                          : "Review required"}
                      </span>
                    </td>
                    <td className="amount">
                      {item.quantity?.value ?? "—"} ×{" "}
                      {item.unit_price?.value ?? "—"}
                    </td>
                    <td className="amount">
                      {item.net?.value ?? "—"} / {item.tax?.value ?? "—"} /{" "}
                      {item.gross?.value ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
      <details className="source-panel">
        <summary>Original PDF and evidence</summary>
        <PdfPreview documentId={run.document_id} />
      </details>
    </div>
  );
}
export function RuleResults({ rules }: { rules: Rule[] }) {
  const incomplete = rules.some(
    (r) =>
      r.outcome !== "PASS" &&
      /^REQUIRED_|^VENDOR_IDENTITY$|^PO_EXISTS$/.test(r.rule_id),
  );
  return (
    <div className="rules">
      {checkGroups.map((group) => {
        const checks = rules.filter((r) => checkGroup(r.rule_id) === group);
        if (!checks.length) return null;
        const issues = checks.filter((r) => r.outcome !== "PASS");
        const dependent =
          incomplete &&
          !issues.length &&
          ["Amounts and taxes", "Purchase order"].includes(group);
        return (
          <details className="check-group" key={group} open={issues.length > 0}>
            <summary>
              <strong>{group}</strong>
              <span>
                {issues.length
                  ? `${issues.length} issue${issues.length === 1 ? "" : "s"}`
                  : dependent
                    ? "Awaiting required information"
                    : "Checks passed"}
              </span>
            </summary>
            <ul>
              {checks.map((rule) => (
                <li
                  className={
                    "rule rule-" +
                    (dependent ? "review" : rule.outcome.toLowerCase())
                  }
                  key={rule.rule_id}
                >
                  <div>
                    <strong>{ruleLabel(rule.rule_id)}</strong>
                    <p>{checkExplanation(rule)}</p>
                    {rule.actual != null && (
                      <p>
                        Recorded value: {rule.actual}
                        {rule.expected != null && (
                          <> · Expected: {rule.expected}</>
                        )}
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </details>
        );
      })}
    </div>
  );
}
function humanizeValue(name: string, value: string) {
  return name === "pricing_mode" ? humanize(value) : value;
}
function FinancialOutput({ run }: { run: RunDetail }) {
  if (!run.decision) return null;
  const labels: Record<string, string> = {
    po_number: "Purchase order",
    requested: "Invoice amount",
    currency: "Currency",
    available_before: "Available before this decision",
    available_after: "Available after this decision",
    commitment_state: "Commitment state",
  };
  return (
    <>
      <dl className="financial-summary">
        {Object.entries(labels).map(([key, label]) => {
          const value = run.decision!.summary[key];
          return typeof value === "string" || typeof value === "number" ? (
            <div key={key}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ) : null;
        })}
      </dl>
      <POComparison run={run} />
      <RuleResults rules={run.decision.rules} />
      <TechnicalDetails label="Original financial rule records">
        <pre>{JSON.stringify(run.decision, null, 2)}</pre>
      </TechnicalDetails>
    </>
  );
}
function Stage({ name, run }: { name: string; run: RunDetail }) {
  const events = run.events.filter(
    (e) =>
      (e.stage === name ||
        (name === "supplier_po" && e.stage === "validation")) &&
      (e.attempt === run.attempt || (name === "ingestion" && e.attempt === 0)),
  );
  const last = events.at(-1);
  const state =
    name === "supplier_po" && last?.outcome === "SUCCEEDED" && !run.decision
      ? "RUNNING"
      : (last?.outcome ?? "PENDING");
  const [open, setOpen] = useState(
    state === "RUNNING" || state === "FAILED" || name === "field_extraction",
  );
  useEffect(() => {
    if (state === "RUNNING" || state === "FAILED") setOpen(true);
  }, [state, last?.id]);
  const ms =
    last && name !== "supplier_po" ? stageInterval(events, last) : null;
  return (
    <li
      className={"stage stage-" + state.toLowerCase()}
      data-stage={name}
      data-state={state}
    >
      <span className="stage-marker" aria-hidden="true">
        {state === "RUNNING" ? (
          <span className="spinner" />
        ) : state === "SUCCEEDED" ? (
          <Icon name="check" />
        ) : state === "FAILED" ? (
          <Icon name="close" />
        ) : state === "SKIPPED" ? (
          <span>−</span>
        ) : null}
      </span>
      <details open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
        <summary>
          <div>
            <h3>{stageNames[name] ?? humanize(name)}</h3>
          </div>
          <div className="stage-meta">
            {ms != null && (
              <span title="Interval between matching persisted start and finish events">
                {duration(ms)}
              </span>
            )}
            <Status value={state} />
            <Icon name="chevron" />
          </div>
        </summary>
        <div className="stage-body">
          {!last ? (
            <p className="muted-text">Waiting for this step to start.</p>
          ) : (
            <>
              <p className="stage-message">
                {name === "supplier_po"
                  ? "Based on the recorded supplier and purchase order validation checks."
                  : name === "validation" && state === "SUCCEEDED"
                    ? "Financial checks recorded for this invoice."
                    : name === "field_extraction" && state === "SUCCEEDED"
                      ? "Invoice details are available below."
                      : name === "text_extraction" && state === "SUCCEEDED"
                        ? "The document was read successfully."
                        : name === "ingestion" && state === "SUCCEEDED"
                          ? "Your invoice was received and saved for processing."
                          : name === "decision" && state === "SUCCEEDED"
                            ? "The financial decision was recorded. No payment was executed."
                            : last.detail}
              </p>
              <div className="event-meta">
                <time dateTime={last.created_at}>{when(last.created_at)}</time>
              </div>
            </>
          )}
          {name === "text_extraction" && state === "SUCCEEDED" && run.pages && (
            <div className="output-tags">
              {run.pages.map((page) => (
                <span className="tag" key={page.page}>
                  Page {page.page} ·{" "}
                  {page.method === "OCR"
                    ? "Scanned document was read"
                    : "Digital document"}
                </span>
              ))}
            </div>
          )}
          {name === "field_extraction" && state === "SUCCEEDED" && (
            <ExtractedFields run={run} />
          )}
          {name === "supplier_po" && run.decision && (
            <ul>
              {run.decision.rules
                .filter((r) => /^(VENDOR|PO_)/.test(r.rule_id))
                .map((r) => (
                  <li key={r.rule_id}>{checkExplanation(r)}</li>
                ))}
            </ul>
          )}
          {name === "validation" && state === "SUCCEEDED" && (
            <FinancialOutput run={run} />
          )}
          {name === "review_disposition" && run.decision && (
            <RuleResults rules={run.decision.rules} />
          )}
        </div>
      </details>
    </li>
  );
}
export default function RunDetails({
  run,
  busy,
  onRetry,
  onSelect,
  onReview,
}: {
  run: RunDetail;
  busy: boolean;
  onRetry: () => void;
  onSelect: (id: string) => void;
  onReview: () => void;
}) {
  const stages = useMemo(
    () =>
      run.events.some((e) => e.stage === "review_disposition")
        ? ["review_disposition"]
        : pipeline
            .flatMap((stage) =>
              stage === "text_extraction" &&
              run.events.some(
                (e) => e.stage === "ocr" && e.outcome !== "SKIPPED",
              )
                ? [stage, "ocr"]
                : [stage],
            )
            .filter(
              (stage) =>
                stage !== "ingestion" ||
                !run.parent_run_id ||
                run.events.some((e) => e.stage === "ingestion"),
            ),
    [run.events, run.parent_run_id],
  );
  const exceptions = primaryIssues(run.decision?.rules ?? []);
  const reasons = exceptions.length
    ? exceptions
    : (run.decision?.rules.filter((rule) =>
        ["VENDOR_APPROVED", "VENDOR_PO", "PO_BALANCE"].includes(rule.rule_id),
      ) ?? []);
  const po = run.decision?.summary.po_number;
  const total = amount(run);
  const latest = run.events.at(-1);
  return (
    <>
      <header className="run-heading">
        <div>
          <p className="eyebrow">
            {isTerminal(run) ? "RECORDED EXECUTION" : "LIVE RUN VIEW"}
          </p>
          <h2>
            {run.invoice_number ??
              fact(run, "invoice_number")?.value ??
              "Invoice number missing"}
          </h2>
          {(run.vendor_name || fact(run, "vendor_name")?.value) && (
            <p>{run.vendor_name ?? fact(run, "vendor_name")?.value}</p>
          )}
        </div>
        <div className="run-status">
          <span className="field-name">Processing status</span>
          <Status value={run.status} />
          {run.decision && (
            <div className="header-decision">
              <span className="field-name">Financial decision</span>
              <Status value={run.decision.outcome} />
            </div>
          )}
          {total && (
            <strong className="run-total">
              {total.currency
                ? money(total.value, total.currency)
                : total.value}
            </strong>
          )}
        </div>
      </header>
      <span className="sr-only" aria-hidden="true" data-testid="run-id">
        {run.id}
      </span>
      <div className="invoice-identity-strip">
        {fact(run, "invoice_date")?.value && (
          <span>
            <small>Invoice date</small>
            <strong>{fact(run, "invoice_date")!.value}</strong>
          </span>
        )}
        {fact(run, "po_number")?.value && (
          <span>
            <small>Purchase order</small>
            <strong>{fact(run, "po_number")!.value}</strong>
          </span>
        )}
        {run.extraction?.provider && (
          <span>
            <small>Document reading</small>
            <strong>{humanize(run.extraction.provider)}</strong>
          </span>
        )}
      </div>
      {run.decision ? (
        <section
          className={
            "decision-card decision-" + run.decision.outcome.toLowerCase()
          }
          aria-label="Financial decision"
        >
          <p className="eyebrow">FINANCIAL DECISION</p>
          <div className="decision-title">
            <span className="decision-icon">
              <Icon
                name={
                  run.decision.outcome === "VALIDATED"
                    ? "check"
                    : run.decision.outcome === "BLOCKED"
                      ? "close"
                      : "review"
                }
              />
            </span>
            <h3>{humanize(run.decision.outcome)}</h3>
          </div>
          <p>
            {run.decision.summary.manual_rejection === true
              ? "A reviewer rejected this invoice."
              : run.decision.outcome === "VALIDATED"
                ? "The recorded financial checks passed."
                : run.decision.outcome === "BLOCKED"
                  ? "Financial controls blocked this invoice."
                  : "This invoice requires a source or policy review."}
          </p>
          {reasons.length > 0 && (
            <ul>
              {reasons
                .filter((rule) => rule.explanation.trim())
                .slice(0, 3)
                .map((rule) => (
                  <li key={rule.rule_id}>{checkExplanation(rule)}</li>
                ))}
            </ul>
          )}
          <div className="decision-links">
            {run.review_task_id && (
              <a
                className="button primary"
                href={"/reviews/" + run.review_task_id}
              >
                Open in Exception review <Icon name="arrow" />
              </a>
            )}
            {typeof po === "string" && (
              <a
                className="button"
                href={"/purchase-orders?po=" + encodeURIComponent(po)}
              >
                View purchase order
              </a>
            )}
            <a className="button" href={"/audit?run_id=" + run.id}>
              View activity history
            </a>
          </div>
          <p>
            <strong>Next action</strong>
            <br />
            {nextAction(run.decision.outcome)}
          </p>
        </section>
      ) : null}
      <TechnicalDetails>
        <div className="run-meta">
          <code title={run.id}>{run.id}</code>
          <CopyButton text={run.id} label="Copy run ID" />
          <Elapsed run={run} />
        </div>
        <dl className="mode-summary">
          <div>
            <dt>Requested extraction</dt>
            <dd>{run.requested_mode ?? "AUTO"}</dd>
          </div>
          {run.extraction?.provider && (
            <div>
              <dt>Actual provider</dt>
              <dd>{humanize(run.extraction.provider)}</dd>
            </div>
          )}
          {run.extraction?.model && (
            <div>
              <dt>Model used</dt>
              <dd>{String(run.extraction.model)}</dd>
            </div>
          )}
          {run.extraction?.attempted_provider && (
            <div>
              <dt>Attempted provider</dt>
              <dd>
                {String(run.extraction.attempted_provider)}
                {run.extraction.attempted_model
                  ? " · " + String(run.extraction.attempted_model)
                  : ""}
              </dd>
            </div>
          )}
        </dl>
      </TechnicalDetails>
      {run.intake_context && (
        <details className="source-panel">
          <summary>Email and invoice purchase order references</summary>
          <p>Email candidates remain separate from PDF-extracted fields.</p>
          <p>
            <strong>PO reference in PDF:</strong>{" "}
            {fact(run, "po_number")?.verified
              ? fact(run, "po_number")?.value
              : "Not found or needs verification"}
          </p>
          {run.intake_context.po_evidence.map((e, i) => (
            <blockquote key={i}>
              {e.source}: {e.quote} · Candidate {e.value}
            </blockquote>
          ))}
          {run.intake_context.selected_po_number && (
            <p>
              Reviewer-selected procurement candidate:{" "}
              {run.intake_context.selected_po_number}
            </p>
          )}
          <a href={"/email-intake?message=" + run.intake_context.message_id}>
            Open source email and intake history
          </a>
        </details>
      )}
      <p className="sr-only" aria-live="polite" aria-atomic="true">
        {latest
          ? humanize(latest.stage) + ": " + humanize(latest.outcome)
          : "Processing " + humanize(run.status)}
      </p>
      {run.parent_run_id && (
        <p className="footnote">
          Derived from{" "}
          <button
            className="text-button"
            onClick={() => onSelect(run.parent_run_id!)}
          >
            the previous processing record
          </button>{" "}
          · prior execution remains in history.
        </p>
      )}
      {run.status === "QUEUED" && (
        <div className="notice">
          Waiting to process this invoice. Stages will appear as they are
          recorded.
        </div>
      )}
      {run.error && (
        <div className="error-banner" role="alert">
          <div>
            <strong>Processing could not finish.</strong>
            <p>{run.error}</p>
          </div>
          {run.status === "FAILED" && (
            <button disabled={busy} onClick={onRetry}>
              Retry failed run
            </button>
          )}
        </div>
      )}
      <div className="section-heading">
        <h3>Processing timeline</h3>
        <span>Updates as your invoice is processed</span>
      </div>
      <ol className="timeline" aria-label="Actual execution stages">
        {stages.map((stage) => (
          <Stage key={run.id + stage} name={stage} run={run} />
        ))}
      </ol>
      <TechnicalDetails label="Persisted execution events">
        {run.events.length > 0 && (
          <details className="operational-events">
            <summary>
              All persisted execution events ({run.events.length})
            </summary>
            <ol>
              {run.events.map((event) => (
                <li key={event.id}>
                  <strong>
                    {humanize(event.stage)} · {humanize(event.outcome)}
                  </strong>
                  <p>{event.detail}</p>
                  <time dateTime={event.created_at}>
                    {when(event.created_at)}
                  </time>{" "}
                  · attempt {event.attempt}
                </li>
              ))}
            </ol>
          </details>
        )}
      </TechnicalDetails>
      {!run.decision && (
        <div className="decision-awaiting">
          <Icon name="review" />
          <p>
            No financial decision has been recorded.
            {run.status === "FAILED"
              ? " Resolve the technical failure before retrying."
              : " Processing status does not imply financial approval."}
          </p>
        </div>
      )}
      {!run.review_task_id && run.decision && (
        <button
          className="text-button correction-action"
          disabled={busy}
          onClick={onReview}
        >
          Request source correction <Icon name="arrow" />
        </button>
      )}
    </>
  );
}
