import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { relativeTime, when } from "../client";
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
  });
  const resource = useResource<{ events: AuditEvent[] }>(
    "/audit-events?" + query,
    3000,
  );
  const events = resource.data?.events ?? [];
  const shown = events.filter(
    (e) =>
      (!stage || eventStage(e.action) === stage) &&
      (!actor || e.actor === actor) &&
      (e.action + " " + e.actor + " " + eventLabel(e.action))
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const stages = [...new Set(events.map((e) => eventStage(e.action)))];
  const actors = [...new Set(events.map((e) => e.actor))];
  return (
    <>
      <PageTitle
        eyebrow="CONTROL / AUDIT HISTORY"
        title="A record you can follow."
        description="Every processing event, decision and reviewer action, preserved in order."
      />
      {params.get("run_id") && (
        <div className="scope-banner">
          <span>
            Showing run <code>{params.get("run_id")?.slice(0, 8)}</code>
          </span>
          <Link to="/audit">View all audit history</Link>
        </div>
      )}
      <Notice error={resource.error} onRetry={resource.reload} />
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Workspace event history</h2>
            <p>
              Stage and actor filters apply to the current page of stored
              events.
            </p>
          </div>
          <label className="search-field">
            <Icon name="search" />
            <span className="sr-only">Filter audit events</span>
            <input
              aria-label="Filter audit events"
              placeholder="Search event or actor"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
        </div>
        <div className="audit-filters">
          <FilterChips
            label="Filter audit stage on this page"
            value={stage}
            onChange={setStage}
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
            onChange={setActor}
            options={[
              { value: "", label: "All actors" },
              ...actors.map((value) => ({ value, label: value })),
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
                      <span className="eyebrow">
                        RUN {event.run_id.slice(0, 8)}
                      </span>
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
                    <div className="event-meta">
                      <span>{event.actor}</span>
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
    </>
  );
}
