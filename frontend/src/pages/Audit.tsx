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
function eventStage(action: string) {
  return action.includes(":") ? action.split(":")[0] : "REVIEWER_ACTION";
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
    limit: "50",
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
  const stages = [
    ...new Set([
      stage,
      "DECISION",
      "REVIEWER_ACTION",
      ...events.map((e) => eventStage(e.action)),
    ]),
  ].filter(Boolean);
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
            label="Filter audit stage on this page"
            value={stage}
            onChange={(v) => {
              setStage(v);
              setOffset(0);
            }}
            options={[
              { value: "", label: "All stages" },
              ...stages.map((value) => ({
                value,
                label:
                  value === "REVIEWER_ACTION"
                    ? "Audit actions"
                    : humanize(value),
              })),
            ]}
          />
          <FilterChips
            label="Filter audit actor on this page"
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
        <div className="audit-list">
          {resource.loading ? (
            <Skeleton label="Loading audit history" rows={5} />
          ) : !shown.length ? (
            <EmptyState title="No matching audit events">
              {events.length
                ? "Change the filters or browse another page."
                : "Events will appear when documents are processed or reviewed."}
            </EmptyState>
          ) : (
            shown.map((event, index) => {
              const tone = event.action.endsWith(":FAILED")
                ? "failed"
                : event.action.endsWith(":RUNNING")
                  ? "running"
                  : event.action.endsWith(":SUCCEEDED")
                    ? "succeeded"
                    : "neutral";
              const newRun =
                index === 0 || shown[index - 1].run_id !== event.run_id;
              return (
                <article
                  className={
                    "audit-event event-" +
                    tone +
                    (newRun ? " thread-start" : "")
                  }
                  key={event.id}
                >
                  {newRun && event.run_id && (
                    <div className="thread-label">
                      <span className="eyebrow">INVOICE PROCESSING RECORD</span>
                      <Link to={"/runs/" + event.run_id}>
                        Open run <Icon name="arrow" />
                      </Link>
                    </div>
                  )}
                  <span className="audit-marker">
                    <Icon
                      name={
                        tone === "failed"
                          ? "close"
                          : tone === "succeeded"
                            ? "check"
                            : tone === "running"
                              ? "clock"
                              : "audit"
                      }
                    />
                  </span>
                  <div className="audit-event-content">
                    <div className="audit-event-heading">
                      <strong>{eventLabel(event.action)}</strong>
                      <time
                        dateTime={event.created_at}
                        title={when(event.created_at)}
                      >
                        {relativeTime(event.created_at)}
                      </time>
                    </div>
                    {event.entity && (
                      <div className="activity-entity">
                        <p>
                          <strong>
                            {event.entity.invoice_number ??
                              "Invoice details awaiting verification"}
                          </strong>
                          {event.entity.vendor && <> · {event.entity.vendor}</>}
                          {event.entity.amount && event.entity.currency && (
                            <>
                              {" "}
                              ·{" "}
                              {money(
                                event.entity.amount,
                                event.entity.currency,
                              )}
                            </>
                          )}
                          {event.entity.outcome && (
                            <> · {humanize(event.entity.outcome)}</>
                          )}
                        </p>
                        {event.entity.reason && (
                          <p>
                            {event.entity.reason.replace(
                              /original document [0-9a-f-]{36}/gi,
                              "original recorded invoice",
                            )}
                          </p>
                        )}
                      </div>
                    )}
                    <div className="event-meta">
                      <span>{actorLabel(event.actor)}</span>
                      <time dateTime={event.created_at}>
                        {when(event.created_at)}
                      </time>
                      {event.run_id && !newRun && (
                        <Link to={"/runs/" + event.run_id}>Open run</Link>
                      )}
                    </div>
                    {typeof event.detail.message === "string" && (
                      <p className="audit-message">{event.detail.message}</p>
                    )}
                    <TechnicalDetails label="Original audit record">
                      <details className="json-details">
                        <summary>
                          Event details <Icon name="chevron" />
                        </summary>
                        <div className="json-heading">
                          <code>{event.action}</code>
                          <CopyButton
                            label="Copy event JSON"
                            text={JSON.stringify(event.detail, null, 2)}
                          />
                        </div>
                        <pre>{JSON.stringify(event.detail, null, 2)}</pre>
                      </details>
                    </TechnicalDetails>
                  </div>
                </article>
              );
            })
          )}
        </div>
        <div className="pagination">
          <button
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - 50))}
          >
            Newer
          </button>
          <span>Page {Math.floor(offset / 50) + 1}</span>
          <button
            disabled={events.length < 50}
            onClick={() => setOffset(offset + 50)}
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
