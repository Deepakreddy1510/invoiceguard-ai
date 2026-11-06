import { TechnicalDetails } from "../TechnicalDetails";
import { actorLabel } from "../business";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { money, relativeTime, when } from "../client";
import {
  CopyButton,
  EmptyState,
  FilterChips,
  humanize,
  Notice,
  PageTitle,
  Skeleton,
  Status,
  useResource,
} from "../ui";
import { Icon } from "../icons";
type AuditEvent = {
  id: string;
  action: string;
  actor: string;
  created_at: string;
  run_id: string | null;
  document_id?: string | null;
  detail: Record<string, unknown>;
  entity?: {
    invoice_number: string | null;
    vendor: string | null;
    amount: string | null;
    currency: string | null;
    outcome: string | null;
    reason: string | null;
  } | null;
};
export function eventLabel(action: string) {
  const [stage, outcome] = action.split(":");
  if (!outcome) return humanize(action);
  const suffix =
    outcome === "RUNNING"
      ? "started"
      : outcome === "SUCCEEDED"
        ? "succeeded"
        : outcome === "QUEUED"
          ? "queued"
          : humanize(outcome).toLowerCase();
  return humanize(stage) + " " + suffix;
}
export default function Audit() {
  const [params] = useSearchParams();
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [stage, setStage] = useState("");
  const [actor, setActor] = useState("");
  const query = new URLSearchParams({
    ...Object.fromEntries(params),
    offset: String(offset),
    limit: "20",
    view: "business",
    search,
    actor,
    stage,
  });
  const resource = useResource<{ events: AuditEvent[] }>(
    "/audit-events?" + query,
    3000,
  );
  const events = resource.data?.events ?? [];
  const shown = events;
  const actors = [
    ...new Set([
      actor,
      "worker",
      "local-demo-reviewer",
      ...events.map((e) => e.actor),
    ]),
  ].filter(Boolean);
  return (
    <>
      <PageTitle
        eyebrow="WORKSPACE / ACTIVITY HISTORY"
        title="Activity history"
        description="Invoice decisions, processing failures and workspace actions. Original records remain available to administrators."
      />
      {params.get("run_id") && (
        <div className="scope-banner">
          <span>Showing the selected invoice’s activity</span>
          <Link to="/audit">View all activity history</Link>
        </div>
      )}
      <Notice error={resource.error} onRetry={resource.reload} />
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Workspace event history</h2>
            <p>Search and filters apply to stored events before pagination.</p>
          </div>
          <label className="search-field">
            <Icon name="search" />
            <span className="sr-only">Filter audit events</span>
            <input
              aria-label="Filter audit events"
              placeholder="Search event or actor"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setOffset(0);
              }}
            />
          </label>
        </div>
        <div className="audit-filters">
          <FilterChips
            label="Filter activity type"
            value={stage}
            onChange={(v) => {
              setStage(v);
              setOffset(0);
            }}
            options={[
              { value: "", label: "All activity" },
              { value: "INVOICE", label: "Invoices" },
              { value: "DECISION", label: "Decisions" },
              { value: "REVIEW", label: "Reviews" },
              { value: "PROCUREMENT", label: "Procurement" },
              { value: "WORKSPACE", label: "Workspace changes" },
              { value: "FAILURE", label: "Processing issues" },
            ]}
          />
          <FilterChips
            label="Filter activity author"
            value={actor}
            onChange={(v) => {
              setActor(v);
              setOffset(0);
            }}
            options={[
              { value: "", label: "All actors" },
              ...actors.map((value) => ({ value, label: actorLabel(value) })),
            ]}
          />
        </div>
        <div className="table-scroll audit-table">
          {resource.loading ? (
            <Skeleton label="Loading audit history" rows={5} />
          ) : !shown.length ? (
            <EmptyState title="No matching audit events">
              Change the filters or browse another page. Events appear when
              documents are processed or reviewed.
            </EmptyState>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Event / author</th>
                  <th>Invoice / supplier</th>
                  <th className="amount">Amount</th>
                  <th>Financial outcome</th>
                  <th>Recorded</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((event) => (
                  <tr key={event.id}>
                    <td>
                      <strong>{eventLabel(event.action)}</strong>
                      <span className="vendor">{actorLabel(event.actor)}</span>
                    </td>
                    <td>
                      {event.entity ? (
                        <>
                          <strong>
                            {event.entity.invoice_number ??
                              "Invoice details awaiting verification"}
                          </strong>
                          {event.entity.vendor && (
                            <span className="vendor">
                              {event.entity.vendor}
                            </span>
                          )}
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="amount">
                      {event.entity?.amount && event.entity.currency
                        ? money(event.entity.amount, event.entity.currency)
                        : "—"}
                    </td>
                    <td>
                      {event.entity?.outcome ? (
                        <Status value={event.entity.outcome} />
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      <time
                        dateTime={event.created_at}
                        title={when(event.created_at)}
                      >
                        {relativeTime(event.created_at)}
                      </time>
                    </td>
                    <td>
                      {event.run_id && (
                        <Link
                          className="text-button"
                          to={"/runs/" + event.run_id}
                        >
                          Open run
                        </Link>
                      )}
                      {(event.entity?.reason ||
                        typeof event.detail.message === "string") && (
                        <details className="event-context">
                          <summary>View context</summary>
                          {event.entity?.reason && (
                            <p>
                              {event.entity.reason.replace(
                                /original document [0-9a-f-]{36}/gi,
                                "original recorded invoice",
                              )}
                            </p>
                          )}
                          {typeof event.detail.message === "string" && (
                            <p>{event.detail.message}</p>
                          )}
                          <time dateTime={event.created_at}>
                            {when(event.created_at)}
                          </time>
                        </details>
                      )}
                      <TechnicalDetails label="Original audit record">
                        <details className="json-details">
                          <summary>
                            {eventLabel(event.action)} ·{" "}
                            {when(event.created_at)}
                          </summary>
                          <CopyButton
                            label="Copy event JSON"
                            text={JSON.stringify(event.detail, null, 2)}
                          />
                          <pre>{JSON.stringify(event.detail, null, 2)}</pre>
                        </details>
                      </TechnicalDetails>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="pagination">
          <button
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - 20))}
          >
            Newer
          </button>
          <span>Page {Math.floor(offset / 20) + 1}</span>
          <button
            disabled={events.length < 20}
            onClick={() => setOffset(offset + 20)}
          >
            Older
          </button>
        </div>
      </section>
      <TechnicalDetails label="Complete original audit history">
        <RawHistory query={params.toString()} />
      </TechnicalDetails>
    </>
  );
}

function RawHistory({ query }: { query: string }) {
  const [offset, setOffset] = useState(0);
  const raw = useResource<{ events: AuditEvent[] }>(
    "/audit-events?" + query + "&offset=" + offset + "&limit=50",
  );
  return (
    <>
      <Notice error={raw.error} />
      <pre className="email-body">
        {JSON.stringify(raw.data?.events ?? [], null, 2)}
      </pre>
      <button
        disabled={!offset}
        onClick={() => setOffset(Math.max(0, offset - 50))}
      >
        Newer raw records
      </button>
      <button
        disabled={(raw.data?.events.length ?? 0) < 50}
        onClick={() => setOffset(offset + 50)}
      >
        Older raw records
      </button>
    </>
  );
}
