import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { request, jsonPost, when } from "../client";
import {
  EmptyState,
  PdfPreview,
  Notice,
  PageTitle,
  Skeleton,
  Status,
  useResource,
} from "../ui";
import { useWorkspace } from "../workspaces";
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
  const [preview, setPreview] = useState(false);
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
        <h3>{a.filename}</h3>
        <Status value={a.status} />
      </div>
      <p>
        {a.mime_type} · {a.byte_size.toLocaleString()} bytes · {a.attempts}{" "}
        intake attempts
      </p>
      {a.status !== "UNSUPPORTED" && (
        <>
          <button onClick={() => setPreview((v) => !v)}>
            {preview ? "Close original PDF" : "Preview original attachment"}
          </button>
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
        </>
      )}
      {a.sha256 && (
        <p className="footnote">
          SHA-256 <code className="hash">{a.sha256}</code>
        </p>
      )}
      <Notice error={error || a.error || run.error} />
      {a.classification ? (
        <>
          <dl className="mode-summary">
            <div>
              <dt>Intake classification</dt>
              <dd>
                <Status value={a.classification.category} />
              </dd>
            </div>
            <div>
              <dt>Actual classifier</dt>
              <dd>
                {a.classification.provider}
                {a.classification.model ? " · " + a.classification.model : ""}
              </dd>
            </div>
          </dl>
          <p>{a.classification.explanation}</p>
          {a.classification.multiple_invoices && (
            <p className="footnote">
              Possible multiple invoices in this PDF: confirm document
              boundaries during intake review.
            </p>
          )}
          {a.classification.fallback_reason && (
            <p className="footnote">{a.classification.fallback_reason}</p>
          )}
          {a.classification.classification_evidence?.quote && (
            <blockquote>
              {a.classification.classification_evidence.source}:{" "}
              {a.classification.classification_evidence.quote}
            </blockquote>
          )}
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
                    <td>{f.kind}</td>
                    <td>{f.value}</td>
                    <td>
                      {f.source}
                      <blockquote>{f.quote}</blockquote>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <p>Classification has not been recorded.</p>
      )}
      {!!a.po_candidates?.length && (
        <>
          <h4>Procurement candidates</h4>
          {a.po_candidates.map((p) => (
            <p key={p.id}>
              <Link to={"/purchase-orders?po=" + encodeURIComponent(p.number)}>
                {p.number}
              </Link>{" "}
              · {p.vendor} · {p.status} · Stored procurement record
            </p>
          ))}
        </>
      )}
      {a.email_rules?.map((r, i) => (
        <p className="footnote" key={i}>
          {r.rule_id} · {r.outcome}: {r.explanation}
        </p>
      ))}
      {a.run_id && (
        <>
          <p>
            <Link to={"/runs/" + a.run_id}>
              Open actual invoice run, PDF and source evidence
            </Link>
          </p>
          {a.handoff_run_id && a.handoff_run_id !== a.run_id && (
            <p className="footnote">
              Showing the latest persisted revision.{" "}
              <Link to={"/runs/" + a.handoff_run_id}>
                Inspect original email handoff run
              </Link>
              .
            </p>
          )}
          {a.replayed && (
            <p className="footnote">
              Exact-document replay: the linked historical run is retained. No
              additional commitment was created by replay.
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
              <h4>Persisted invoice execution</h4>
              <ol className="email-events">
                {run.data.events.map((e) => (
                  <li key={e.id}>
                    <strong>
                      {e.stage} · {e.outcome}
                    </strong>
                    <span>{e.detail}</span>
                    <time>{when(e.created_at)}</time>
                  </li>
                ))}
              </ol>
              {run.data.decision && (
                <div className="rules">
                  <h4>Financial controls</h4>
                  {run.data.decision.rules.map((r, i) => (
                    <div key={i}>
                      <strong>
                        {r.rule_id} · {r.outcome}
                      </strong>
                      <p>{r.explanation}</p>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}
      {a.review && (
        <p className="footnote">
          Intake review by {a.review.actor}: {a.review.action} —{" "}
          {a.review.reason}
        </p>
      )}
      {canReview &&
        ["REVIEW", "IGNORED", "FAILED", "UNSUPPORTED"].includes(a.status) &&
        !a.run_id && (
          <fieldset className="email-review" disabled={busy}>
            <legend>Human intake review</legend>
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
  const { active } = useWorkspace();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [disconnect, setDisconnect] = useState(false);
  const list = useResource<Overview>(
    `/email?search=${encodeURIComponent(search)}&status=${status}&offset=${offset}`,
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
          ? "Synchronization queued for the background worker."
          : "Mailbox reads disabled. Revocation is queued; historical records are retained.",
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
        title="From inbox to evidence."
        description="Gmail attachments enter the same verified invoice workflow. Intake classification is separate from financial approval."
      />
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
            "Gmail consent completed. New incoming mail will be checked by the worker."}
        </p>
      )}
      <section className="panel email-connection" aria-label="Gmail connection">
        <div className="panel-heading">
          <h2>Gmail connection</h2>
          <span className="tag">
            {active?.kind === "MY" ? "My Workspace" : active?.name}
          </span>
        </div>
        {list.loading ? (
          <Skeleton label="Loading Gmail connection" />
        ) : (
          <>
            <p>
              {list.data?.available
                ? "Google OAuth is configured on the server."
                : list.data?.configuration_message}
            </p>
            <p className="footnote">
              Configured email classifier:{" "}
              {list.data?.email_classifier ?? "FALLBACK"}. Gmail message content
              is sent to Gemini only when the server explicitly enables email
              AI.
            </p>
            {current ? (
              <>
                <dl className="financial-summary">
                  <div>
                    <dt>Account</dt>
                    <dd>{current.email}</dd>
                  </div>
                  <div>
                    <dt>Connection status</dt>
                    <dd>
                      <Status value={current.status} />
                    </dd>
                  </div>
                  <div>
                    <dt>Last completed synchronization</dt>
                    <dd>{when(current.last_sync_at)}</dd>
                  </div>
                  <div>
                    <dt>Next scheduled attempt</dt>
                    <dd>
                      {["ACTIVE", "REVOKE_PENDING"].includes(current.status)
                        ? when(current.next_sync_at)
                        : "—"}
                    </dd>
                  </div>
                </dl>
                <Notice error={current.error ?? ""} />
              </>
            ) : (
              <p>No mailbox is connected to this workspace.</p>
            )}
            {list.data?.can_manage && (
              <div className="toolbar">
                <button
                  className="primary"
                  disabled={
                    busy ||
                    !list.data.available ||
                    (!!current &&
                      !["DISCONNECTED", "AUTH_REQUIRED"].includes(
                        current.status,
                      ))
                  }
                  onClick={() => void control("connect")}
                >
                  {current?.status === "AUTH_REQUIRED"
                    ? "Reconnect Gmail"
                    : "Connect Gmail"}
                </button>
                {current?.status === "ACTIVE" && (
                  <button
                    disabled={busy || !list.data.available}
                    onClick={() => void control("sync")}
                  >
                    Check for new emails
                  </button>
                )}
                {current &&
                  !["DISCONNECTED", "REVOKE_PENDING"].includes(
                    current.status,
                  ) && (
                    <button disabled={busy} onClick={() => setDisconnect(true)}>
                      Disconnect Gmail
                    </button>
                  )}
              </div>
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
                <button disabled={busy} onClick={() => setDisconnect(false)}>
                  Keep connection
                </button>
              </div>
            )}
            <p className="footnote">
              Only new inbox mail is checked after connection. Google read-only
              permission is required. When Gemini email classification is
              enabled, bounded email and document text are sent to Gemini. Use a
              dedicated synthetic test mailbox until live verification and
              Google requirements are complete.
            </p>
          </>
        )}
      </section>
      {list.data && (
        <section
          className="metric-grid email-metrics"
          aria-label="Persisted email intake metrics"
        >
          {[
            ["emails_checked", "Emails checked"],
            ["invoice_candidates", "Invoice candidates"],
            ["attachments_ingested", "Attachments ingested"],
            ["awaiting_review", "Awaiting intake review"],
            ["ignored", "Ignored attachments"],
            ["failed_attempts", "Failed intake attempts"],
            ["linked_invoices", "Unique linked invoices"],
            ["unique_documents", "Unique Gmail documents"],
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
            Workspace-scoped source records; completed intake does not imply an
            approved invoice.
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
                <option key={v}>{v}</option>
              ))}
            </select>
          </label>
        </div>
        {list.loading ? (
          <Skeleton label="Loading email intake" />
        ) : !list.data?.messages.length ? (
          <EmptyState title="No incoming email in this view">
            Connect a dedicated Gmail account, then send it a synthetic invoice
            PDF. Actual messages and worker events will appear here.
          </EmptyState>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Sender / subject</th>
                  <th>Received</th>
                  <th>Attachment</th>
                  <th>Classification</th>
                  <th>Intake</th>
                  <th>Processing</th>
                  <th>Financial decision</th>
                </tr>
              </thead>
              <tbody>
                {list.data.messages.flatMap((m) =>
                  (m.attachments.length ? m.attachments : [null]).map(
                    (a, index) => (
                      <tr key={m.id + ":" + index}>
                        <td>
                          <button
                            className="table-link"
                            onClick={() => setParams({ message: m.id })}
                          >
                            {m.subject || "(No subject)"}
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
        <section className="email-detail" aria-label="Source email detail">
          <button onClick={() => setParams({})}>Close email detail</button>
          {detail.loading ? (
            <Skeleton label="Loading source email" />
          ) : (
            detail.data && (
              <>
                <h2>{detail.data.subject || "(No subject)"}</h2>
                <p>
                  {detail.data.sender} · {when(detail.data.received_at)} ·
                  Workspace {detail.data.workspace_id}
                </p>
                <details className="source-panel" open>
                  <summary>Safe email body preview</summary>
                  <pre className="email-body">
                    {detail.data.body ||
                      "No readable message body was retained."}
                  </pre>
                </details>
                {detail.data.attachments.map((a) => (
                  <AttachmentDetail
                    key={a.id}
                    attachment={a}
                    canReview={!!list.data?.can_review}
                    onDone={() => {
                      list.reload();
                      detail.reload();
                    }}
                  />
                ))}
                <section className="panel">
                  <h3>Recent persisted mailbox and attachment events</h3>
                  <ol className="email-events">
                    {detail.data.events.map((e) => (
                      <li key={e.id}>
                        <strong>
                          {e.stage} · {e.outcome}
                        </strong>
                        <span>{e.detail}</span>
                        {e.evidence != null && (
                          <details>
                            <summary>Recorded evidence at this event</summary>
                            <pre className="email-body">
                              {JSON.stringify(e.evidence, null, 2)}
                            </pre>
                          </details>
                        )}
                        <time>{when(e.created_at)}</time>
                      </li>
                    ))}
                  </ol>
                </section>
              </>
            )
          )}
        </section>
      )}
      <p className="footnote">
        Email PO claims are candidates under email-po-review-v1. They cannot
        override verified PDF evidence, vendor status or PO capacity.{" "}
        <Link to="/process">Manual PDF upload remains available</Link>.
      </p>
    </>
  );
}
