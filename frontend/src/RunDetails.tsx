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
import { Icon } from "./icons";
const stageNames: Record<string, string> = {
  ingestion: "Document accepted",
  text_extraction: "Read document",
  ocr: "Optical character recognition",
  field_extraction: "Extract invoice fields",
  validation: "Financial validation",
  decision: "Record decision",
  review_disposition: "Reviewer disposition",
};
const pipeline = [
  "ingestion",
  "text_extraction",
  "ocr",
  "field_extraction",
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
        <span className="tag">{humanize(run.extraction.provider)}</span>
      </div>
      {run.extraction.fallback_reason && (
        <details className="extraction-note">
          <summary>Extraction notes</summary>
          <p className="footnote">{run.extraction.fallback_reason}</p>
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
                  <strong>{value.value ?? "Missing / ambiguous"}</strong>
                  {!value.verified && (
                    <span className="evidence-flag">Review required</span>
                  )}
                </td>
                <td>
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
                        value.method,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  )}
                  {value.quote && <blockquote>{value.quote}</blockquote>}
                  {value.reviewer && (
                    <small>Confirmed by {value.reviewer}</small>
                  )}
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
  return (
    <ul className="rules">
      {rules.map((rule) => (
        <li
          className={"rule rule-" + rule.outcome.toLowerCase()}
          key={rule.rule_id}
        >
          <span className="rule-icon">
            <Icon
              name={
                rule.outcome === "PASS"
                  ? "check"
                  : rule.outcome === "BLOCK"
                    ? "close"
                    : "review"
              }
            />
          </span>
          <div>
            <div className="rule-heading">
              <strong>{humanize(rule.rule_id)}</strong>
              <Status
                value={
                  rule.outcome === "PASS"
                    ? "PASSED"
                    : rule.outcome === "BLOCK"
                      ? "BLOCKED"
                      : "NEEDS_REVIEW"
                }
              />
            </div>
            <p>{rule.explanation}</p>
            <code>{rule.rule_id}</code>
            {rule.actual != null && (
              <div className="rule-values">
                <span>
                  Actual <b>{rule.actual}</b>
                </span>
                {rule.expected != null && (
                  <span>
                    Expected <b>{rule.expected}</b>
                  </span>
                )}
              </div>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
function FinancialOutput({ run }: { run: RunDetail }) {
  if (!run.decision) return null;
  return (
    <>
      <dl className="financial-summary">
        {Object.entries(run.decision.summary)
          .filter(([key, value]) => key !== "payment_executed" && value != null)
          .map(([key, value]) => (
            <div key={key}>
              <dt>{humanize(key)}</dt>
              <dd>{Array.isArray(value) ? value.join(", ") : String(value)}</dd>
            </div>
          ))}
      </dl>
      <details
        className="rule-details"
        open={run.decision.rules.some((rule) => rule.outcome !== "PASS")}
      >
        <summary>
          Rule results · {run.decision.rules.length} recorded checks
        </summary>
        <RuleResults rules={run.decision.rules} />
      </details>
    </>
  );
}
function Stage({ name, run }: { name: string; run: RunDetail }) {
  const events = run.events.filter(
    (e) =>
      e.stage === name &&
      (e.attempt === run.attempt || (name === "ingestion" && e.attempt === 0)),
  );
  const last = events.at(-1);
  const state = last?.outcome ?? "PENDING";
  const [open, setOpen] = useState(
    state === "RUNNING" ||
      state === "FAILED" ||
      name === "field_extraction" ||
      name === "validation",
  );
  useEffect(() => {
    if (state === "RUNNING" || state === "FAILED") setOpen(true);
  }, [state, last?.id]);
  const ms = last ? stageInterval(events, last) : null;
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
            <span className="stage-kicker">{humanize(name)}</span>
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
            <p className="muted-text">Awaiting a recorded event.</p>
          ) : (
            <>
              <p className="stage-message">{last.detail}</p>
              <div className="event-meta">
                <time dateTime={last.created_at}>{when(last.created_at)}</time>
                <span>Attempt {last.attempt}</span>
              </div>
            </>
          )}
          {name === "text_extraction" && state === "SUCCEEDED" && run.pages && (
            <div className="output-tags">
              {run.pages.map((page) => (
                <span className="tag" key={page.page}>
                  Page {page.page} · {page.method}
                </span>
              ))}
            </div>
          )}
          {name === "field_extraction" && state === "SUCCEEDED" && (
            <ExtractedFields run={run} />
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
        : pipeline.filter(
            (stage) =>
              stage !== "ingestion" ||
              !run.parent_run_id ||
              run.events.some((e) => e.stage === "ingestion"),
          ),
    [run.events, run.parent_run_id],
  );
  const exceptions =
    run.decision?.rules.filter((r) => r.outcome !== "PASS") ?? [];
  const reasons = exceptions.length
    ? exceptions
    : (run.decision?.rules.filter(
        (rule) =>
          rule.outcome === "PASS" &&
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
      <div className="run-meta">
        <code data-testid="run-id" title={run.id}>
          {run.id}
        </code>
        <CopyButton text={run.id} label="Copy run ID" />
        <Elapsed run={run} />
      </div>
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
            {run.parent_run_id.slice(0, 8)}
          </button>{" "}
          · prior execution remains in history.
        </p>
      )}
      {run.status === "QUEUED" && (
        <div className="notice">
          Waiting for the Python worker. Execution stages will appear as they
          are recorded.
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
        <h3>Execution timeline</h3>
        <span>Persisted events only</span>
      </div>
      <ol className="timeline" aria-label="Actual execution stages">
        {stages.map((stage) => (
          <Stage key={run.id + stage} name={stage} run={run} />
        ))}
      </ol>
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
              {reasons.map((rule) => (
                <li key={rule.rule_id}>{rule.explanation}</li>
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
              View audit trail
            </a>
          </div>
          <p className="footnote">
            {run.decision.policy_version && (
              <>Policy: {run.decision.policy_version}. </>
            )}
            Payment has not been executed.
          </p>
        </section>
      ) : (
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
