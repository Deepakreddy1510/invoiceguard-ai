import { Icon } from "../icons";
import { InvoiceIdentity } from "../InvoiceIdentity";
import { TechnicalDetails } from "../TechnicalDetails";
import { humanize } from "../ui";
import { Dialog, Help } from "../Experience";
import { fact } from "../models";
import {
  nextAction,
  actorLabel,
  primaryIssues,
  checkExplanation,
} from "../business";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { request, jsonPost, when, money } from "../client";
import {
  EmptyState,
  PdfPreview,
  Notice,
  PageTitle,
  Skeleton,
  Status,
  useResource,
} from "../ui";
import type { RunDetail } from "../models";
type Fact = {
  kind: string;
  value: string;
  source: string;
  quote: string;
  verified: boolean;
};
type Classification = {
  category: string;
  multiple_invoices?: boolean;
  provider: string;
  model: string | null;
  explanation: string;
  fallback_reason: string | null;
  evidence: Fact[];
  classification_evidence?: { source: string; quote: string | null };
};
type Attachment = {
  id: string;
  filename: string;
  mime_type: string;
  byte_size: number;
  sha256: string | null;
  classification: Classification | null;
  status: string;
  attempts: number;
  next_attempt_at: string;
  error: string | null;
  run_id: string | null;
  handoff_run_id?: string | null;
  document_id: string | null;
  decision: string | null;
  processing_status: string | null;
  replayed: boolean;
  review: { actor: string; reason: string; action: string } | null;
  po_candidates?: {
    id: string;
    number: string;
    vendor: string;
    status: string;
    source: string;
  }[];
  email_rules?: { rule_id: string; outcome: string; explanation: string }[];
};
type Message = {
  id: string;
  subject: string;
  sender: string;
  received_at: string | null;
  status: string;
  attachments: Attachment[];
};
type Detail = Message & {
  body: string;
  workspace_id: string;
  gmail_id: string;
  attachment_events?: Detail["events"];
  events: {
    id: string;
    stage: string;
    outcome: string;
    detail: string;
    evidence?: unknown;
    created_at: string;
  }[];
};
type Connection = {
  id: string;
  email: string;
  status: string;
  last_sync_at: string | null;
  next_sync_at: string;
  error: string | null;
  failure_count: number;
};
type Overview = {
  available: boolean;
  email_classifier?: string;
  configuration_message: string | null;
  can_manage: boolean;
  can_review: boolean;
  workspace_id: string;
  connections: Connection[];
  metrics: Record<string, number>;
  messages: Message[];
};
function EmailDocumentPreview({ attachment: a }: { attachment: Attachment }) {
  const [preview, setPreview] = useState(false);
  return (
    <section className="email-document-preview">
      <button onClick={() => setPreview((v) => !v)}>
        {preview ? "Close original PDF" : "Preview original attachment"}
      </button>
      <p>{a.filename}</p>
      {preview && (
        <PdfPreview
          documentId={a.document_id ?? undefined}
          sourcePath={
            a.document_id
              ? undefined
              : "/api/v1/email/attachments/" + a.id + "/content"
          }
        />
      )}
    </section>
  );
}
function AttachmentDetail({
  attachment: a,
  canReview,
  onDone,
}: {
  attachment: Attachment;
  canReview: boolean;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const [po, setPo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = useResource<RunDetail>(
    a.run_id ? "/runs/" + a.run_id : null,
    1500,
  );
  async function action(value: string) {
    setBusy(true);
    setError("");
    try {
      await jsonPost("/email/attachments/" + a.id + "/review", {
        action: value,
        reason,
        selected_po_id: po || null,
      });
      onDone();
      setReason("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="panel email-attachment"
      aria-label={"Attachment " + a.filename}
    >
      <div className="panel-heading">
        <h3>
          <InvoiceIdentity
            number={
              run.data?.invoice_number ??
              fact(run.data, "invoice_number")?.value
            }
            supplier={run.data?.vendor_name ?? undefined}
            compact={false}
            fallback={a.filename}
          />
        </h3>
        <span className="email-intake-tag">
          <small>Email intake</small>
          <Status value={a.status} />
        </span>
      </div>
      <TechnicalDetails>
        {" "}
        <p>
          {a.mime_type} · {a.byte_size.toLocaleString()} bytes · {a.attempts}{" "}
          intake attempts
        </p>
      </TechnicalDetails>
      <TechnicalDetails label="Document fingerprint">
        {a.sha256 && (
          <p className="footnote">
            SHA-256 <code className="hash">{a.sha256}</code>
          </p>
        )}
      </TechnicalDetails>
      <Notice error={error || a.error || run.error} />
      {run.data?.decision && (
        <section
          className={
            "decision-card decision-" + run.data.decision.outcome.toLowerCase()
          }
          aria-label="Invoice financial decision"
        >
          <div className="email-decision-heading">
            <div>
              <p className="eyebrow">Financial decision</p>
              <h3>{humanize(run.data.decision.outcome)}</h3>
            </div>
            <div>
              <small>Processing</small>
              <Status value={run.data.status} />
            </div>
          </div>
          <p>
            {primaryIssues(run.data.decision.rules)[0]
              ? checkExplanation(primaryIssues(run.data.decision.rules)[0])
              : "The recorded supplier, order and amount checks passed."}
          </p>
          <Link to={"/runs/" + a.run_id}>View full invoice decision</Link>
          <p>
            <strong>Next action</strong>
            <br />
            {nextAction(run.data.decision.outcome)}
          </p>
        </section>
      )}
      {a.run_id && !run.data?.decision && (
        <p>
          <Link to={"/runs/" + a.run_id}>View live invoice processing →</Link>
        </p>
      )}
      {run.data?.extraction && (
        <>
          <p className="eyebrow">
            {run.data.extraction.provider === "GEMINI"
              ? "AI-ASSISTED DOCUMENT READING"
              : "DOCUMENT SUMMARY"}
          </p>
          <dl className="financial-summary">
            {[
              "invoice_number",
              "vendor_name",
              "invoice_date",
              "po_number",
              "currency",
              "total",
            ].map((key) => {
              const value = fact(run.data, key)?.value;
              return value ? (
                <div key={key}>
                  <dt>{humanize(key)}</dt>
                  <dd>
                    {key === "total" && fact(run.data, "currency")?.value
                      ? money(value, fact(run.data, "currency")!.value!)
                      : value}
                  </dd>
                </div>
              ) : null;
            })}
          </dl>
        </>
      )}

      {a.classification ? (
        <>
          <dl className="mode-summary">
            <div>
              <dt>Attachment type</dt>
              <dd>
                <Status value={a.classification.category} />
              </dd>
            </div>
          </dl>
          <TechnicalDetails>
            <dl className="mode-summary">
              <div>
                <dt>Actual classifier</dt>
                <dd>
                  {a.classification.provider}
                  {a.classification.model ? " · " + a.classification.model : ""}
                </dd>
              </div>
            </dl>
          </TechnicalDetails>
          <p>
            {a.classification.category === "INVOICE"
              ? run.data?.decision
                ? "This attachment was identified as an invoice. Its financial result is shown above."
                : "This attachment was identified as an invoice. Intake and financial verification remain separate."
              : a.classification.category === "NOT_INVOICE"
                ? "This attachment does not appear to be an invoice."
                : "Confirm whether this attachment is an invoice before forwarding."}
          </p>
          {a.classification.multiple_invoices && (
            <p className="footnote">
              Possible multiple invoices in this PDF: confirm document
              boundaries during intake review.
            </p>
          )}
          {a.classification.fallback_reason && (
            <TechnicalDetails>
              <p className="footnote">{a.classification.fallback_reason}</p>
            </TechnicalDetails>
          )}
          <details className="source-panel">
            <summary>Why this attachment was identified</summary>
            {a.classification.classification_evidence?.quote && (
              <blockquote>
                {humanize(a.classification.classification_evidence.source)}:{" "}
                {a.classification.classification_evidence.quote}
              </blockquote>
            )}
          </details>
          <details className="source-panel">
            <summary>Supporting email references</summary>
            <div className="table-scroll">
              <table className="evidence-table">
                <thead>
                  <tr>
                    <th>Candidate field</th>
                    <th>Value</th>
                    <th>Source and exact quote</th>
                  </tr>
                </thead>
                <tbody>
                  {a.classification.evidence.map((f, i) => (
                    <tr key={i}>
                      <td>{humanize(f.kind)}</td>
                      <td>{f.value}</td>
                      <td>
                        <details>
                          <summary>
                            View source evidence · {humanize(f.source)}
                          </summary>
                          <blockquote>{f.quote}</blockquote>
                        </details>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      ) : (
        <p>This attachment has not been checked yet.</p>
      )}
      {!!a.po_candidates?.length && (
        <>
          <h4>Possible purchase orders</h4>
          {a.po_candidates.map((p) => (
            <p key={p.id}>
              <Link to={"/purchase-orders?po=" + encodeURIComponent(p.number)}>
                {p.number}
              </Link>{" "}
              · {p.vendor} · {humanize(p.status)} · Saved purchase order
            </p>
          ))}
        </>
      )}
      {a.email_rules?.map((r, i) => (
        <p className="footnote" key={i}>
          {r.explanation}
        </p>
      ))}
      {a.run_id && (
        <>
          {a.handoff_run_id && a.handoff_run_id !== a.run_id && (
            <p className="footnote">
              Showing the latest reviewed details.{" "}
              <Link to={"/runs/" + a.handoff_run_id}>
                View the original processing record
              </Link>
              .
            </p>
          )}
          {a.replayed && (
            <p className="footnote">
              This PDF was already uploaded. Its existing decision is retained,
              with no extra amount reserved against the order.
            </p>
          )}
          <dl className="mode-summary">
            <div>
              <dt>Invoice processing status</dt>
              <dd>
                <Status
                  value={run.data?.status ?? a.processing_status ?? "QUEUED"}
                />
              </dd>
            </div>
            {(run.data?.outcome ?? a.decision) && (
              <div>
                <dt>Financial decision</dt>
                <dd>
                  <Status value={(run.data?.outcome ?? a.decision)!} />
                </dd>
              </div>
            )}
          </dl>
          {run.data && (
            <>
              <TechnicalDetails label="Persisted invoice execution">
                <h4>Persisted invoice execution</h4>
                <ol className="email-events">
                  {run.data.events.map((e) => (
                    <li key={e.id}>
                      <strong>
                        {humanize(e.stage)} · {humanize(e.outcome)}
                      </strong>
                      <span>{e.detail}</span>
                      <time>{when(e.created_at)}</time>
                    </li>
                  ))}
                </ol>
              </TechnicalDetails>
            </>
          )}
        </>
      )}
      {a.review && (
        <p className="footnote">
          Intake review by {actorLabel(a.review.actor)}: {a.review.action} —{" "}
          {a.review.reason}
        </p>
      )}
      {canReview &&
        ["REVIEW", "IGNORED", "FAILED", "UNSUPPORTED"].includes(a.status) &&
        !a.run_id && (
          <fieldset className="email-review" disabled={busy}>
            <legend>Check this attachment</legend>
            <p>
              Forwarding confirms document intake only. All financial controls
              still run. Email-only PO claims remain subject to financial
              review.
            </p>
            <label>
              Review reason
              <textarea
                aria-label={"Intake review reason for " + a.filename}
                minLength={10}
                maxLength={2000}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </label>
            {!!a.po_candidates?.length && (
              <label>
                Evidence-supported PO candidate
                <select
                  aria-label={"PO candidate for " + a.filename}
                  value={po}
                  onChange={(e) => setPo(e.target.value)}
                >
                  <option value="">No selection</option>
                  {a.po_candidates.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.number} · {p.vendor}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <div className="toolbar">
              {a.status !== "UNSUPPORTED" && (
                <>
                  <button
                    disabled={reason.trim().length < 10 || !a.classification}
                    onClick={() => void action("FORWARD")}
                  >
                    Forward to invoice processing
                  </button>
                  <button
                    disabled={reason.trim().length < 10}
                    onClick={() => void action("RETRY")}
                  >
                    Retry intake
                  </button>
                </>
              )}
              <button
                disabled={reason.trim().length < 10}
                onClick={() => void action("IGNORE")}
              >
                Ignore attachment
              </button>
            </div>
          </fieldset>
        )}
    </section>
  );
}
export default function EmailIntake() {
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [manage, setManage] = useState(false);
  const [disconnect, setDisconnect] = useState(false);
  const [view, setView] = useState("actionable");
  const list = useResource<Overview>(
    `/email?view=${view}&search=${encodeURIComponent(search)}&status=${status}&offset=${offset}`,
    3000,
  );
  const selected = params.get("message");
  const detail = useResource<Detail>(
    selected ? "/email/messages/" + selected : null,
    2000,
  );
  const current =
    list.data?.connections.find((c) => c.status !== "DISCONNECTED") ??
    list.data?.connections[0];
  async function control(action: string) {
    setBusy(true);
    setError("");
    try {
      if (action === "connect") {
        const r = await request<{ authorization_url: string }>(
          "/email/oauth/start",
          { method: "POST" },
        );
        window.location.assign(r.authorization_url);
        return;
      }
      await request(`/email/connections/${current!.id}/${action}`, {
        method: "POST",
      });
      setMessage(
        action === "sync"
          ? "Checking for new invoices. Results will appear as messages are processed."
          : "Email checks have stopped. Existing invoices and email records are retained.",
      );
      setDisconnect(false);
      list.reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageTitle
        eyebrow="AUTOMATION / EMAIL INTAKE"
        title="Invoices from your inbox"
        description="Automatically collect and review supplier invoices from your connected email."
      />
      <div
        className="filter-chips"
        role="group"
        aria-label="Email activity view"
      >
        <button
          aria-pressed={view === "actionable"}
          onClick={() => {
            setView("actionable");
            setOffset(0);
          }}
        >
          Actionable invoices
        </button>
        <button
          aria-pressed={view === "all"}
          onClick={() => {
            setView("all");
            setOffset(0);
          }}
        >
          All email activity
        </button>
      </div>
      <Notice
        error={error || list.error || detail.error}
        onRetry={() => {
          list.reload();
          detail.reload();
        }}
      />
      {params.get("gmail") === "failed" && (
        <Notice error="Google authorization could not be completed. Check consent and server configuration, then connect again." />
      )}
      {(message || params.get("gmail") === "connected") && (
        <p role="status" className="submission-message">
          {message ||
            "Gmail connected. New incoming invoice attachments will be checked automatically."}
        </p>
      )}
      <section className="panel email-connection" aria-label="Gmail connection">
        <div className="connection-summary">
          <strong>Gmail</strong>
          {list.loading ? (
            <span role="status">Loading connection…</span>
          ) : (
            <>
              {current ? (
                <>
                  <span>{current.email}</span>
                  <Status value={current.status} />
                  <span>Last checked {when(current.last_sync_at)}</span>
                </>
              ) : (
                <p>
                  {list.data?.available
                    ? "Connect Gmail to collect incoming supplier invoices."
                    : "Gmail connection unavailable. Ask your administrator to finish email setup, or upload a PDF manually."}
                </p>
              )}
            </>
          )}
        </div>
        <div className="toolbar">
          {list.data?.can_manage && current?.status === "ACTIVE" && (
            <button
              disabled={busy || !list.data.available}
              onClick={() => void control("sync")}
            >
              Check now
            </button>
          )}
          {list.data?.can_manage &&
            (!current ||
              ["DISCONNECTED", "AUTH_REQUIRED"].includes(current.status)) && (
              <button
                className="primary"
                disabled={busy || !list.data.available}
                onClick={() => void control("connect")}
              >
                {current?.status === "AUTH_REQUIRED"
                  ? "Reconnect Gmail"
                  : "Connect Gmail"}
              </button>
            )}
          <button onClick={() => setManage(true)}>Manage connection</button>
        </div>
      </section>
      {manage && (
        <Dialog
          title="Gmail connection"
          onClose={() => {
            setManage(false);
            setDisconnect(false);
          }}
        >
          <p>
            {current
              ? `Connected account: ${current.email}`
              : "No mailbox is connected to this workspace."}
          </p>
          {current && (
            <>
              <Status value={current.status} />
              <p>Last successful check: {when(current.last_sync_at)}</p>
              <p>
                Next check:{" "}
                {["ACTIVE", "REVOKE_PENDING"].includes(current.status)
                  ? when(current.next_sync_at)
                  : "Not scheduled"}
              </p>
              <Notice error={current.error ?? ""} />
            </>
          )}
          <Help title="How do I connect Gmail?">
            <p>
              Select Connect Gmail, grant read-only access and keep this
              workspace selected. Only new inbox mail is collected; existing
              financial history is retained when you disconnect.
            </p>
          </Help>
          <p>
            {list.data?.email_classifier === "GEMINI"
              ? "AI-assisted email reading is enabled by your administrator. Relevant text may be sent to Gemini; financial checks remain separate."
              : "Standard email reading is enabled. Email content is not sent to an AI service."}
          </p>
          <p>
            <a href="/settings#email-settings">
              Email configuration and privacy settings
            </a>
          </p>
          {list.data?.can_manage &&
            current &&
            !["DISCONNECTED", "REVOKE_PENDING"].includes(current.status) && (
              <button disabled={busy} onClick={() => setDisconnect(true)}>
                Disconnect Gmail
              </button>
            )}
          {disconnect && (
            <div className="notice">
              <p>
                Stop reading this mailbox and revoke Google access? Existing
                messages, invoices and financial history will remain.
              </p>
              <button
                disabled={busy}
                onClick={() => void control("disconnect")}
              >
                Confirm Gmail disconnect
              </button>
              <button onClick={() => setDisconnect(false)}>
                Keep connection
              </button>
            </div>
          )}
        </Dialog>
      )}
      {list.data && (
        <section
          className="metric-grid email-metrics"
          aria-label="Persisted email intake metrics"
        >
          {[
            ["invoice_candidates", "Invoice attachments found"],
            ["completed_decisions", "Invoices processed"],
            ["awaiting_review", "Needs attention"],
            ["failed", "Intake issues"],
          ].map(([key, label]) => (
            <article className="panel metric-card" key={key}>
              <span>{label}</span>
              <strong>{list.data!.metrics[key] ?? 0}</strong>
            </article>
          ))}
        </section>
      )}
      <section className="panel">
        <div className="panel-heading">
          <h2>Incoming email</h2>
          <p>
            Invoice candidates and attachments needing attention. Processing
            completion is separate from financial approval.
          </p>
        </div>
        <div className="table-toolbar">
          <input
            aria-label="Search incoming emails"
            placeholder="Sender, subject or attachment"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setOffset(0);
            }}
          />
          <label>
            Intake filter
            <select
              aria-label="Filter email intake"
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">All</option>
              {[
                "QUEUED",
                "SCREENING",
                "REVIEW",
                "INGESTED",
                "IGNORED",
                "FAILED",
                "UNSUPPORTED",
              ].map((v) => (
                <option key={v} value={v}>
                  {humanize(v)}
                </option>
              ))}
            </select>
          </label>
        </div>
        {list.loading ? (
          <Skeleton label="Loading email intake" />
        ) : !list.data?.messages.length ? (
          <EmptyState title="No incoming email in this view">
            Connect Gmail and send an invoice PDF to the connected address. New
            invoice attachments and their results will appear here.
          </EmptyState>
        ) : (
          <div
            className="table-scroll inbox-table"
            role="region"
            aria-label="Scrollable email inbox"
            tabIndex={0}
          >
            <table>
              <thead>
                <tr>
                  <th>Sender / subject</th>
                  <th>Received</th>
                  <th>Attachment</th>
                  <th>Document type</th>
                  <th>Email intake</th>
                  <th>Processing</th>
                  <th>Financial decision</th>
                  <th>Next action</th>
                </tr>
              </thead>
              <tbody>
                {list.data.messages.flatMap((m) =>
                  (m.attachments.length ? m.attachments : [null]).map(
                    (a, index) => (
                      <tr
                        key={m.id + ":" + index}
                        className={
                          selected === m.id ? "selected-row" : undefined
                        }
                      >
                        <td>
                          <button
                            className="table-link"
                            onClick={() => setParams({ message: m.id })}
                          >
                            <span className="email-subject-identity">
                              <span
                                className="invoice-document-mark"
                                aria-hidden="true"
                              >
                                <Icon name="file" />
                              </span>
                              <span title={m.subject || "No subject"}>
                                {m.subject || "(No subject)"}
                              </span>
                            </span>
                          </button>
                          <span className="vendor">
                            {m.sender || "Sender unavailable"}
                          </span>
                        </td>
                        <td>{when(m.received_at)}</td>
                        <td>{a?.filename ?? "No attachments"}</td>
                        <td>
                          {a?.classification ? (
                            <Status value={a.classification.category} />
                          ) : (
                            "—"
                          )}
                        </td>
                        <td>
                          <Status value={a?.status ?? m.status} />
                        </td>
                        <td>
                          {a?.processing_status ? (
                            <Status value={a.processing_status} />
                          ) : (
                            "—"
                          )}
                        </td>
                        <td>
                          {a?.decision ? (
                            <Link to={"/runs/" + a.run_id}>
                              <Status value={a.decision} />
                            </Link>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td>
                          <button
                            className="text-button"
                            onClick={() => setParams({ message: m.id })}
                          >
                            {a?.decision
                              ? "View decision"
                              : ["REVIEW", "UNSUPPORTED", "FAILED"].includes(
                                    a?.status ?? "",
                                  )
                                ? "Check attachment"
                                : "View details"}
                          </button>
                        </td>
                      </tr>
                    ),
                  ),
                )}
              </tbody>
            </table>
          </div>
        )}
        <div className="pagination">
          <button
            disabled={!offset}
            onClick={() => setOffset((v) => Math.max(0, v - 30))}
          >
            Previous emails
          </button>
          <button
            disabled={(list.data?.messages.length ?? 0) < 30}
            onClick={() => setOffset((v) => v + 30)}
          >
            Next emails
          </button>
        </div>
      </section>
      {selected && (
        <Dialog title="Email details" wide onClose={() => setParams({})}>
          {detail.loading ? (
            <Skeleton label="Loading source email" />
          ) : (
            detail.data && (
              <div
                className="email-source-layout"
                aria-label="Source email detail"
              >
                <div className="email-source">
                  <p className="eyebrow">SUPPLIER EMAIL</p>
                  <h3>{detail.data.subject || "(No subject)"}</h3>
                  <p>
                    <strong>From</strong> {detail.data.sender}
                  </p>
                  <p>
                    <strong>Received</strong> {when(detail.data.received_at)}
                  </p>
                  <details className="source-panel" open>
                    <summary>Email content</summary>
                    <pre className="email-body">
                      {detail.data.body ||
                        "No readable message body was retained."}
                    </pre>
                  </details>
                  <Help title="How email references are checked">
                    <p>
                      A purchase order mentioned in an email is a candidate. It
                      cannot replace missing invoice details or override
                      supplier and budget checks.
                    </p>
                  </Help>
                  {detail.data.attachments
                    .filter((a) => a.status !== "UNSUPPORTED")
                    .map((a) => (
                      <EmailDocumentPreview key={a.id} attachment={a} />
                    ))}
                  <TechnicalDetails label="Mailbox and attachment events">
                    <pre className="email-body">
                      {JSON.stringify(detail.data.events, null, 2)}
                    </pre>
                  </TechnicalDetails>
                </div>
                <div>
                  {detail.data.attachments.length ? (
                    detail.data.attachments.map((a) => (
                      <AttachmentDetail
                        key={a.id}
                        attachment={a}
                        canReview={!!list.data?.can_review}
                        onDone={() => {
                          list.reload();
                          detail.reload();
                        }}
                      />
                    ))
                  ) : (
                    <EmptyState title="No invoice attachment">
                      This email has no attachment to process.
                    </EmptyState>
                  )}
                </div>
              </div>
            )
          )}
        </Dialog>
      )}
      <p className="footnote">
        Purchase order references from email require verification. They cannot
        override verified PDF evidence, vendor status or PO capacity.{" "}
        <Link to="/process">Manual PDF upload remains available</Link>.
      </p>
    </>
  );
}
