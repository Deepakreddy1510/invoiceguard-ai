import { InvoiceIdentity } from "./InvoiceIdentity";
import { amount, type RunSummary } from "./models";
import { useRunDetails } from "./run-data";
import { money } from "./client";
import { Link } from "react-router-dom";
import {
  useResource,
  humanize,
  EmptyState,
  Notice,
  Status,
  Skeleton,
} from "./ui";
import { when, relativeTime } from "./client";

type Task = {
  id: string;
  run: RunSummary;
  outcome: string | null;
};
export function OverviewInsights({
  outcomes,
  total,
}: {
  outcomes?: Record<string, number>;
  total?: number;
}) {
  const reviews = useResource<{ tasks: Task[] }>("/reviews?status=OPEN", 3000);
  const reviewDetails = useRunDetails(
    (reviews.data?.tasks ?? []).slice(0, 3).map((task) => task.run),
  );
  const email = useResource<{
    messages: {
      id: string;
      sender: string;
      subject: string;
      attachments: {
        filename: string;
        decision: string | null;
        status: string;
      }[];
    }[];
  }>("/email?view=actionable", 5000);
  const categories = [
    { key: "VALIDATED", label: "Validated", color: "#25845f" },
    { key: "NEEDS_REVIEW", label: "Needs review", color: "#ad721b" },
    { key: "BLOCKED", label: "Blocked", color: "#b54e50" },
  ];
  const known = categories.reduce((n, c) => n + (outcomes?.[c.key] ?? 0), 0);
  const pending = Math.max(0, (total ?? 0) - known);
  const segments = [
    ...categories.map((c) => ({ ...c, count: outcomes?.[c.key] ?? 0 })),
    {
      key: "PENDING",
      label: "Awaiting decision",
      color: "#c8d0dc",
      count: pending,
    },
  ];
  let cumulative = 0;
  const gradient = segments
    .map((s) => {
      const start = cumulative;
      cumulative += total ? (s.count / total) * 100 : 0;
      return `${s.color} ${start}% ${cumulative}%`;
    })
    .join(",");
  return (
    <div className="insight-grid">
      <section className="panel outcome-insight">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">THE BIG PICTURE</p>
            <h2>Invoice outcomes</h2>
          </div>
          <span className="tag">Unique invoices</span>
        </div>
        {total ? (
          <div className="outcome-content">
            <div
              className="outcome-donut"
              role="img"
              aria-label={segments
                .map((s) => `${s.label}: ${s.count}`)
                .join(", ")}
              style={{ background: `conic-gradient(${gradient})` }}
            >
              <div>
                <strong>{total}</strong>
                <span>invoices</span>
              </div>
            </div>
            <div className="outcome-legend">
              {segments
                .filter((s) => s.count > 0 || s.key !== "PENDING")
                .map((s) => (
                  <div key={s.key}>
                    <span
                      className="legend-dot"
                      style={{ background: s.color }}
                    />
                    <span>{s.label}</span>
                    <strong>{s.count}</strong>
                  </div>
                ))}
            </div>
          </div>
        ) : (
          <EmptyState title="Your first invoice starts the picture">
            Process an invoice to see real outcomes here.
          </EmptyState>
        )}
        <p className="footnote">
          Retries and repeated uploads do not increase unique invoice counts.
        </p>
      </section>
      <section className="panel priority-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">YOUR NEXT MOVE</p>
            <h2>Needs your attention</h2>
          </div>
          <span className="count-badge">
            {reviews.data?.tasks.length ?? "—"}
          </span>
        </div>
        <Notice error={reviews.error} />
        {reviews.loading ? (
          <Skeleton label="Loading review queue" rows={2} />
        ) : reviews.data?.tasks.length ? (
          <ul className="priority-list">
            {reviews.data.tasks.slice(0, 3).map((t) => {
              const total = amount(reviewDetails[t.run.id]);
              return (
                <li key={t.id} className="attention-invoice-row">
                  <Link
                    className="attention-invoice-link"
                    to={"/reviews/" + t.id}
                  >
                    <InvoiceIdentity
                      number={t.run.invoice_number}
                      supplier={t.run.vendor_name ?? null}
                      fallback="Invoice details need checking"
                    />
                  </Link>
                  <div className="attention-invoice-meta">
                    {total && (
                      <strong>
                        {total.currency
                          ? money(total.value, total.currency)
                          : total.value}
                      </strong>
                    )}
                    <Status value={t.outcome ?? t.run.status} />
                  </div>
                  <Link
                    className="attention-open"
                    to={"/reviews/" + t.id}
                    aria-label={
                      "Open invoice " +
                      (t.run.invoice_number ?? "requiring review")
                    }
                  >
                    Open →
                  </Link>
                </li>
              );
            })}
          </ul>
        ) : (
          <div className="all-clear">
            <span>✓</span>
            <h3>You're all caught up</h3>
            <p>No open review tasks are waiting in this workspace.</p>
          </div>
        )}
        <div className="panel-footer">
          <Link to="/reviews">Review exceptions →</Link>
          <Link to="/purchase-orders">Check order balances →</Link>
        </div>
      </section>
      <section className="panel inbox-insight">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">CONNECTED WORKFLOW</p>
            <h2>From your inbox</h2>
          </div>
          <Link to="/email-intake">Open inbox →</Link>
        </div>
        <Notice error={email.error} />
        {email.loading ? (
          <Skeleton label="Loading incoming invoices" rows={2} />
        ) : email.data?.messages.length ? (
          <ul className="priority-list">
            {email.data.messages.slice(0, 3).map((m) => (
              <li key={m.id}>
                <div>
                  <Link to={"/email-intake?message=" + m.id}>
                    {m.subject || "Invoice email"}
                  </Link>
                  <p>{m.sender}</p>
                </div>
                {m.attachments[0] && (
                  <Status
                    value={m.attachments[0].decision ?? m.attachments[0].status}
                  />
                )}
              </li>
            ))}
          </ul>
        ) : (
          <div className="email-empty">
            <h3>Let invoices come to you</h3>
            <p>
              Connect Gmail to collect supplier PDFs automatically, or upload
              one yourself.
            </p>
            <Link className="button" to="/email-intake">
              Set up email intake
            </Link>
          </div>
        )}
      </section>
    </div>
  );
}
type Activity = {
  id: string;
  action: string;
  actor: string;
  created_at: string;
  run_id: string | null;
  href?: string;
  entity?: {
    invoice_number: string | null;
    vendor: string | null;
    outcome: string | null;
    amount?: string | null;
    currency?: string | null;
  };
  detail: Record<string, unknown>;
};
export function BusinessActivity() {
  const data = useResource<{ events: Activity[] }>(
    "/audit-events?view=recent&limit=5",
    5000,
  );
  return (
    <section className="panel business-feed">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">A CLEAR RECORD</p>
          <h2>Recent Invoice Activity</h2>
        </div>
        <Link to="/audit">View full history →</Link>
      </div>
      <Notice error={data.error} />
      {data.loading ? (
        <Skeleton label="Loading recent activity" rows={3} />
      ) : !data.data?.events.length ? (
        <EmptyState title="Your activity will appear here">
          Invoice decisions, supplier changes and order updates stay connected.
        </EmptyState>
      ) : (
        <ol>
          {data.data.events.map((e) => (
            <li key={e.id}>
              <span className="feed-dot" />
              <div>
                <strong>
                  {e.entity?.outcome && e.action.includes("DECISION")
                    ? "Invoice " + humanize(e.entity.outcome).toLowerCase()
                    : e.action === "CORRECTION_SAVED"
                      ? "Invoice corrected · revalidation queued"
                      : e.action === "EMAIL_HANDOFF"
                        ? "Invoice imported from Gmail"
                        : humanize(e.action)}
                </strong>
                <div className="activity-invoice-identity">
                  {e.entity ? (
                    <InvoiceIdentity
                      number={e.entity?.invoice_number}
                      supplier={e.entity?.vendor ?? undefined}
                    />
                  ) : typeof e.detail.number === "string" ? (
                    e.detail.number
                  ) : (
                    "Business record"
                  )}
                </div>
              </div>
              {e.entity?.amount && (
                <span>
                  {e.entity.currency
                    ? money(e.entity.amount, e.entity.currency)
                    : e.entity.amount}
                </span>
              )}
              <time dateTime={e.created_at} title={when(e.created_at)}>
                {relativeTime(e.created_at)}
              </time>
              <Link to={e.href ?? (e.run_id ? "/runs/" + e.run_id : "/audit")}>
                {e.run_id ? "View invoice" : "View record"}
              </Link>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
