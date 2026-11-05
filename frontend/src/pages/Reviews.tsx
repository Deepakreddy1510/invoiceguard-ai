import { RuleResults } from "../RunDetails";
import { Help } from "../Experience";
import { nextAction, actorLabel } from "../business";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { jsonPost, money, relativeTime, when } from "../client";
import { amount, type Extraction, type Rule, type RunSummary } from "../models";
import { useRunDetails } from "../run-data";
import {
  EmptyState,
  humanize,
  Notice,
  PageTitle,
  PdfPreview,
  Skeleton,
  Status,
  useResource,
} from "../ui";
import { Icon } from "../icons";
const fields = [
  "vendor_name",
  "vendor_code",
  "tax_id",
  "invoice_number",
  "invoice_date",
  "po_number",
  "currency",
  "pricing_mode",
  "subtotal",
  "discount",
  "charges",
  "tax",
  "total",
];
const itemKeys = [
  "sku",
  "quantity",
  "unit_price",
  "net",
  "tax_rate",
  "tax",
  "gross",
];
type Task = {
  id: string;
  document_id: string;
  latest_run_id: string;
  version: number;
  assignee: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  run: RunSummary;
  outcome: string | null;
};
type ReviewDetail = Task & {
  extraction: Extraction | null;
  decisions: {
    run_id: string;
    outcome: string;
    rules: Rule[];
    created_at: string;
  }[];
  commitments: {
    id: string;
    amount: string;
    currency: string;
    status: string;
  }[];
  corrections: {
    id: string;
    run_id: string;
    actor: string;
    comment: string;
    created_at: string;
  }[];
};
export default function Reviews() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [showAll, setShowAll] = useState(false);
  const queue = useResource<{ tasks: Task[] }>(
    "/reviews?status=" + (showAll ? "ALL" : "OPEN"),
    3000,
  );
  const detail = useResource<ReviewDetail>(id ? "/reviews/" + id : null, 2000);
  const extras = useRunDetails((queue.data?.tasks ?? []).map((t) => t.run));
  const [baseVersion, setBaseVersion] = useState(0);
  const [confirmed, setConfirmed] = useState<string[]>([]);
  const [reset, setReset] = useState(0);
  const [values, setValues] = useState<Record<string, string>>({});
  const [items, setItems] = useState<Record<string, string>[]>([]);
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [attest, setAttest] = useState(false);
  useEffect(() => {
    if (!id || !detail.data?.extraction) return;
    const sourceFields = detail.data.extraction.fields;
    setBaseVersion(detail.data.version);
    setConfirmed([]);
    setValues(
      Object.fromEntries(
        fields.map((k) => [
          k,
          (sourceFields[k] as { value?: string | null })?.value ?? "",
        ]),
      ),
    );
    setItems(
      (detail.data.extraction.fields.items ?? []).map((item) =>
        Object.fromEntries(itemKeys.map((k) => [k, item[k]?.value ?? ""])),
      ),
    );
    setComment("");
    setAttest(false);
    // Keep in-progress edits on polling. Only a new persisted revision or explicit reload resets the form.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, detail.data?.latest_run_id, reset]);
  function reloadForm() {
    setReset((v) => v + 1);
    detail.reload();
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!id || !detail.data?.extraction) return;
    setBusy(true);
    setError("");
    try {
      const before = detail.data.extraction.fields;
      const changed = Object.fromEntries(
        fields
          .filter(
            (k) =>
              ((before[k] as { value?: string })?.value ?? "") !== values[k] ||
              confirmed.includes(k),
          )
          .map((k) => [k, values[k] || null]),
      );
      const oldItems = (before.items ?? []).map((row) =>
        Object.fromEntries(itemKeys.map((k) => [k, row[k]?.value ?? ""])),
      );
      const replaced = JSON.stringify(oldItems) !== JSON.stringify(items);
      const result = await jsonPost("/reviews/" + id + "/corrections", {
        version: baseVersion,
        comment,
        values: changed,
        ...(replaced
          ? {
              items: items.map((row) =>
                Object.fromEntries(itemKeys.map((k) => [k, row[k] || null])),
              ),
            }
          : {}),
      });
      navigate("/runs/" + result.run_id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function release() {
    if (!id || !detail.data || !attest) return;
    setBusy(true);
    setError("");
    try {
      await jsonPost("/reviews/" + id + "/release", {
        version: baseVersion,
        comment,
      });
      detail.reload();
      queue.reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const task = id ? detail.data : null;
  const stale = !!task && baseVersion !== task.version;
  const latestDecision = task?.decisions.at(-1);
  const po = task?.extraction?.fields.po_number as
    { value?: string } | undefined;
  return (
    <>
      <PageTitle
        eyebrow="EXCEPTIONS / HUMAN REVIEW"
        title="Resolve uncertainty with evidence."
        description="Correct the source facts. Keep the history. Revalidate every financial control."
      />
      <Notice
        error={error || queue.error || detail.error}
        onRetry={() => {
          setError("");
          queue.reload();
          detail.reload();
        }}
      />
      <div className="toolbar">
        <label className="switch-label">
          <input
            role="switch"
            type="checkbox"
            checked={showAll}
            onChange={(e) => setShowAll(e.target.checked)}
          />
          <span className="switch-track" aria-hidden="true" />
          Include resolved reviews
        </label>
        <span>{queue.data?.tasks.length ?? "…"} tasks on this page</span>
      </div>
      <div className={id ? "review-layout" : "review-layout queue-only"}>
        <section className="panel review-queue" aria-label="Exception queue">
          <div className="section-heading">
            <h2>Exception queue</h2>
            <Icon name="review" />
          </div>
          {queue.loading ? (
            <Skeleton label="Loading exceptions" rows={3} />
          ) : queue.data && !queue.data.tasks.length ? (
            <EmptyState title="No open exceptions">
              Invoices needing source or policy review will appear here.
            </EmptyState>
          ) : (
            queue.data?.tasks.map((t) => {
              const record = extras[t.run.id];
              const total = amount(record);
              const reason = record?.decision?.rules.find(
                (rule) => rule.outcome !== "PASS",
              )?.explanation;
              return (
                <Link
                  aria-current={t.id === id ? "page" : undefined}
                  className={"review-card " + (t.id === id ? "selected" : "")}
                  key={t.id}
                  to={"/reviews/" + t.id}
                >
                  <div className="review-card-heading">
                    <strong>
                      {t.run.invoice_number ?? "Invoice number missing"}
                    </strong>
                    <Icon name="chevron" />
                  </div>
                  {t.run.vendor_name && <span>{t.run.vendor_name}</span>}
                  {reason && <p className="review-reason">{reason}</p>}
                  <div className="review-card-bottom">
                    {total && (
                      <strong>
                        {total.currency
                          ? money(total.value, total.currency)
                          : total.value}
                      </strong>
                    )}
                    <Status value={t.status} />
                  </div>
                  <time dateTime={t.created_at} title={when(t.created_at)}>
                    {relativeTime(t.created_at)}
                  </time>
                </Link>
              );
            })
          )}
        </section>
        {id && (
          <section
            className="panel review-detail"
            aria-label="Exception details"
          >
            {detail.loading ? (
              <Skeleton label="Loading review and evidence" rows={5} />
            ) : (
              task && (
                <>
                  <div className="panel-heading">
                    <div>
                      <p className="eyebrow">INVOICE REVIEW</p>
                      <h2>
                        {task.run.invoice_number ?? "Invoice number missing"}
                      </h2>
                      {task.run.vendor_name && <p>{task.run.vendor_name}</p>}
                      <small>
                        {task.assignee
                          ? "Assigned to " + actorLabel(task.assignee)
                          : "Unassigned"}
                      </small>
                    </div>
                    <Status value={task.status} />
                  </div>
                  <div className="review-links">
                    <Link to={"/runs/" + task.latest_run_id}>
                      Open latest processing decision <Icon name="arrow" />
                    </Link>
                    {po?.value && (
                      <Link
                        to={
                          "/purchase-orders?po=" + encodeURIComponent(po.value)
                        }
                      >
                        View referenced purchase order
                      </Link>
                    )}
                  </div>
                  <details className="source-panel">
                    <summary>Original document</summary>
                    <PdfPreview documentId={task.document_id} />
                  </details>
                  <Help title="How to resolve this invoice">
                    <p>
                      Compare the flagged details with the original invoice.
                      Correct only what the source supports, explain your
                      changes and confirm that you checked the document. Saving
                      runs the full financial checks again; it does not bypass a
                      block or execute payment.
                    </p>
                  </Help>
                  <h3>Why this invoice needs attention</h3>
                  {latestDecision ? (
                    <>
                      <p>
                        <strong>Next action</strong>
                        <br />
                        {nextAction(latestDecision.outcome)}
                      </p>
                      <RuleResults rules={latestDecision.rules} />
                    </>
                  ) : (
                    <p className="muted-text">
                      Revalidation is in progress. The next decision will appear
                      when recorded.
                    </p>
                  )}
                  {task.commitments.some((c) =>
                    ["HELD", "RESERVED"].includes(c.status),
                  ) && (
                    <div className="notice">
                      <strong>Capacity remains reserved during review.</strong>
                      {task.commitments
                        .filter((c) => ["HELD", "RESERVED"].includes(c.status))
                        .map((c) => (
                          <p key={c.id}>
                            {money(c.amount, c.currency)} · {humanize(c.status)}
                          </p>
                        ))}
                    </div>
                  )}
                  {task.extraction ? (
                    <form onSubmit={submit}>
                      {stale && task.status === "OPEN" && (
                        <div className="notice">
                          This review changed.{" "}
                          <button type="button" onClick={reloadForm}>
                            Reload current revision
                          </button>
                        </div>
                      )}
                      <fieldset
                        disabled={stale || task.status !== "OPEN" || busy}
                      >
                        <div className="section-heading">
                          <h3>Verify & correct invoice fields</h3>
                          <span>Source evidence below each value</span>
                        </div>
                        <div className="field-grid">
                          {fields.map((field) => {
                            const source = task.extraction!.fields[field] as {
                              verified?: boolean;
                              method?: string;
                              page?: number;
                              quote?: string;
                            };
                            return (
                              <div className="review-field" key={field}>
                                <label htmlFor={"correct-" + field}>
                                  {humanize(field)}
                                </label>
                                {field === "pricing_mode" ? (
                                  <select
                                    id={"correct-" + field}
                                    aria-label={
                                      "Correct " + humanize(field).toLowerCase()
                                    }
                                    value={values[field] ?? ""}
                                    onChange={(e) =>
                                      setValues((v) => ({
                                        ...v,
                                        [field]: e.target.value,
                                      }))
                                    }
                                  >
                                    <option value="">Needs verification</option>
                                    <option value="TAX_EXCLUSIVE">
                                      Tax added to net price
                                    </option>
                                    <option value="TAX_INCLUSIVE">
                                      Tax included in price
                                    </option>
                                  </select>
                                ) : (
                                  <input
                                    id={"correct-" + field}
                                    aria-label={
                                      "Correct " + humanize(field).toLowerCase()
                                    }
                                    value={values[field] ?? ""}
                                    onChange={(e) =>
                                      setValues((v) => ({
                                        ...v,
                                        [field]: e.target.value,
                                      }))
                                    }
                                  />
                                )}
                                <small
                                  className={
                                    source?.verified
                                      ? "evidence-verified"
                                      : "evidence-flag"
                                  }
                                >
                                  {source?.method === "HUMAN"
                                    ? "Previously reviewer supplied"
                                    : source?.verified
                                      ? "Source-backed value"
                                      : "Unverified or missing"}
                                </small>
                                {source?.quote && (
                                  <blockquote>
                                    {source.page != null && (
                                      <span>Page {source.page} · </span>
                                    )}
                                    {source.quote}
                                  </blockquote>
                                )}
                                {!source?.verified && values[field] && (
                                  <label className="confirm-field">
                                    <input
                                      type="checkbox"
                                      aria-label={
                                        "Confirm " +
                                        humanize(field).toLowerCase()
                                      }
                                      checked={confirmed.includes(field)}
                                      onChange={(e) =>
                                        setConfirmed((previous) =>
                                          e.target.checked
                                            ? [...previous, field]
                                            : previous.filter(
                                                (k) => k !== field,
                                              ),
                                        )
                                      }
                                    />{" "}
                                    Confirm against source
                                  </label>
                                )}
                              </div>
                            );
                          })}
                        </div>
                        <h3>Line items</h3>
                        <div className="table-scroll">
                          <table className="editable-items">
                            <thead>
                              <tr>
                                {itemKeys.map((k) => (
                                  <th key={k}>{humanize(k)}</th>
                                ))}
                                <th>Action</th>
                              </tr>
                            </thead>
                            <tbody>
                              {items.map((row, index) => (
                                <tr key={index}>
                                  {itemKeys.map((k) => (
                                    <td key={k}>
                                      <input
                                        aria-label={`Item ${index + 1} ${k}`}
                                        value={row[k]}
                                        onChange={(e) =>
                                          setItems((rows) =>
                                            rows.map((r, i) =>
                                              i === index
                                                ? { ...r, [k]: e.target.value }
                                                : r,
                                            ),
                                          )
                                        }
                                      />
                                    </td>
                                  ))}
                                  <td>
                                    <button
                                      type="button"
                                      aria-label={"Remove item " + (index + 1)}
                                      onClick={() =>
                                        setItems((rows) =>
                                          rows.filter((_, i) => i !== index),
                                        )
                                      }
                                    >
                                      Remove
                                    </button>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        <button
                          type="button"
                          onClick={() =>
                            setItems((rows) => [
                              ...rows,
                              Object.fromEntries(itemKeys.map((k) => [k, ""])),
                            ])
                          }
                        >
                          Add item
                        </button>
                        <label className="comment-label">
                          Reviewer comment
                          <textarea
                            aria-label="Reviewer comment"
                            minLength={10}
                            maxLength={2000}
                            value={comment}
                            onChange={(e) => setComment(e.target.value)}
                            required
                            placeholder="Describe the source evidence and the reason for your correction."
                          />
                        </label>
                        <label className="attestation">
                          <input
                            type="checkbox"
                            checked={attest}
                            onChange={(e) => setAttest(e.target.checked)}
                            required
                          />
                          I checked this revision against document or vendor
                          evidence. Financial controls will still run.
                        </label>
                        <div className="review-actions">
                          <button
                            className="primary"
                            disabled={!attest || busy}
                            type="submit"
                          >
                            {busy
                              ? "Submitting…"
                              : "Save correction and revalidate"}
                            <Icon name="arrow" />
                          </button>
                          <button
                            className="danger"
                            type="button"
                            disabled={
                              !attest || comment.trim().length < 10 || busy
                            }
                            onClick={release}
                          >
                            Reject case and release hold
                          </button>
                        </div>
                      </fieldset>
                    </form>
                  ) : (
                    <EmptyState title="No extraction available yet">
                      Wait for recorded extraction or retry the failed
                      processing run.
                    </EmptyState>
                  )}
                  <h3>Previous revisions and decisions</h3>
                  <ol className="revision-history">
                    {task.decisions.map((d) => (
                      <li key={d.run_id}>
                        <Link to={"/runs/" + d.run_id}>
                          <Status value={d.outcome} />
                          <Icon name="arrow" />
                        </Link>
                        <time dateTime={d.created_at}>
                          {when(d.created_at)}
                        </time>
                      </li>
                    ))}
                  </ol>
                  {task.corrections.map((c) => (
                    <article className="correction-record" key={c.id}>
                      <strong>{actorLabel(c.actor)}</strong>
                      <time dateTime={c.created_at}>{when(c.created_at)}</time>
                      <p>{c.comment}</p>
                      <Link to={"/runs/" + c.run_id}>
                        Inspect corrected revision <Icon name="arrow" />
                      </Link>
                    </article>
                  ))}
                </>
              )
            )}
          </section>
        )}
      </div>
    </>
  );
}
