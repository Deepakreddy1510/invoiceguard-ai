import { Link, useNavigate } from "react-router-dom";
import { useState } from "react";
import { duration, money, relativeTime, when } from "../client";
import { amount, outcomes, type RunSummary } from "../models";
import { useRunDetails } from "../run-data";
import {
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
type Metrics = {
  total_invoices: number;
  outcomes: Record<string, number>;
  processing_runs: number;
  failed_runs: number;
  duplicate_assessments: number;
  average_run_seconds: number | null;
  duration_sample_count: number;
  recent_runs: RunSummary[];
  worker: { available: boolean; last_seen: string | null };
};
const empty: RunSummary[] = [];
export default function Dashboard() {
  const [outcome, setOutcome] = useState("");
  const [search, setSearch] = useState("");
  const navigate = useNavigate();
  const me = useResource<{
    workspace_kind: string;
    vendor_count: number;
    po_count: number;
    can_manage_procurement: boolean;
  }>("/me");
  const base = useResource<Metrics>("/dashboard", 3000);
  const query = new URLSearchParams({
    ...(outcome ? { outcome } : {}),
    ...(search ? { search } : {}),
  });
  const filtered = useResource<Metrics>(
    query.size ? "/dashboard?" + query : null,
    3000,
  );
  const view = query.size ? filtered : base;
  const data = base.data;
  const runs = view.data?.recent_runs ?? empty;
  const details = useRunDetails(runs);
  const cards = [
    {
      value: "",
      label: "Unique invoices",
      count: data?.total_invoices,
      note: "Each invoice counted once, including unresolved ones",
      tone: "all",
    },
    ...outcomes.map((value) => ({
      value,
      label: humanize(value),
      count: data?.outcomes[value],
      note:
        value === "VALIDATED"
          ? "Recorded financial checks passed"
          : value === "NEEDS_REVIEW"
            ? "Source or policy needs attention"
            : "A financial control prevented approval",
      tone: value.toLowerCase(),
    })),
  ];
  return (
    <>
      <PageTitle
        eyebrow="ACCOUNTS PAYABLE / OVERVIEW"
        title="Every invoice, accounted for."
        description="A clear view of your decisions, exceptions and the evidence behind them."
        action={
          <Link className="button primary" to="/process">
            <Icon name="upload" />
            Process invoice
          </Link>
        }
      />
      <Notice
        error={base.error || filtered.error}
        onRetry={() => {
          base.reload();
          filtered.reload();
        }}
      />
      {me.data?.workspace_kind === "MY" &&
        (me.data.vendor_count === 0 || me.data.po_count === 0) && (
          <div className="notice">
            <strong>Make this workspace your own.</strong>
            <p>
              Start by adding a vendor and creating a purchase order. Then
              upload your first invoice.
            </p>
            <div className="toolbar">
              <Link className="button primary" to="/vendors">
                Add vendor
              </Link>
              <Link className="button" to="/purchase-orders">
                Create purchase order
              </Link>
            </div>
          </div>
        )}
      <div className="metric-grid">
        {cards.map((card) => (
          <button
            key={card.value}
            className={"metric metric-" + card.tone}
            aria-pressed={outcome === card.value}
            onClick={() => setOutcome(card.value)}
          >
            <span>
              {card.label}
              <Icon name="arrow" />
            </span>
            <strong>{card.count ?? "—"}</strong>
            <p>{card.note}</p>
          </button>
        ))}
      </div>
      {data && (
        <section
          className="distribution"
          aria-label="Unique invoice outcome distribution"
        >
          <div className="distribution-bar">
            {outcomes.map((value) => (
              <span
                key={value}
                className={"distribution-" + value.toLowerCase()}
                style={{
                  width:
                    (data.total_invoices
                      ? (data.outcomes[value] / data.total_invoices) * 100
                      : 0) + "%",
                }}
                title={`${humanize(value)}: ${data.outcomes[value]}`}
              />
            ))}
          </div>
          <p>
            {data.total_invoices
              ? `${data.total_invoices} unique invoices · current recorded outcomes`
              : "No recorded financial outcomes yet"}
          </p>
        </section>
      )}
      {data && (
        <div
          className="operational-strip"
          aria-label="Persisted operational metrics"
        >
          <span className="operation-chip">
            <i className={data.worker.available ? "live-dot" : "idle-dot"} />
            Worker {data.worker.available ? "active" : "not recently observed"}
            {data.worker.last_seen && (
              <time
                dateTime={data.worker.last_seen}
                title={when(data.worker.last_seen)}
              >
                {" "}
                · {relativeTime(data.worker.last_seen)}
              </time>
            )}
          </span>
          <span className="operation-chip">
            <b>{data.processing_runs}</b> total runs
          </span>
          <span className="operation-chip">
            <b>{data.failed_runs}</b> technical failures
          </span>
          <span className="operation-chip">
            <b>{data.duplicate_assessments}</b> duplicate assessments
          </span>
          {data.average_run_seconds != null && (
            <span
              className="operation-chip"
              title={`${data.duration_sample_count} completed runs; includes queue time`}
            >
              Mean duration <b>{duration(data.average_run_seconds * 1000)}</b>
            </span>
          )}
        </div>
      )}
      <section className="panel activity-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">THE WORK, AS IT HAPPENS</p>
            <h2>Recent processing activity</h2>
            <p>Run history includes retries and duplicate assessments.</p>
          </div>
          <Link to="/process">
            View processing history <Icon name="arrow" />
          </Link>
        </div>
        <div className="table-toolbar">
          <FilterChips
            label="Filter dashboard outcomes"
            value={outcome}
            onChange={setOutcome}
            options={[
              { value: "", label: "All", count: data?.total_invoices },
              ...outcomes.map((value) => ({
                value,
                label: humanize(value),
                count: data?.outcomes[value],
              })),
            ]}
          />
          <label className="search-field">
            <Icon name="search" />
            <span className="sr-only">Search invoices</span>
            <input
              aria-label="Search invoices"
              placeholder="Search invoice or vendor"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
        </div>
        {view.loading ? (
          <Skeleton label="Loading persisted activity" rows={4} />
        ) : !runs.length ? (
          <EmptyState
            title={
              query.size
                ? "No matching activity"
                : "Your invoice history starts here"
            }
          >
            {query.size
              ? "Try a different search or outcome."
              : "Process a PDF to see its real stages and decision."}
          </EmptyState>
        ) : (
          <div className="table-scroll">
            <table className="activity-table">
              <thead>
                <tr>
                  <th>Invoice</th>
                  <th>Vendor</th>
                  <th className="amount">Amount</th>
                  <th>Outcome / processing</th>
                  <th className="amount">Duration</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => {
                  const total = amount(details[run.id]);
                  return (
                    <tr
                      key={run.id}
                      className="clickable-row"
                      tabIndex={0}
                      aria-label={"Open run " + (run.invoice_number ?? run.id)}
                      onClick={(e) => {
                        if (!(e.target as HTMLElement).closest("a"))
                          navigate("/runs/" + run.id);
                      }}
                      onKeyDown={(e) => {
                        if (
                          e.target === e.currentTarget &&
                          ["Enter", " "].includes(e.key)
                        ) {
                          e.preventDefault();
                          navigate("/runs/" + run.id);
                        }
                      }}
                    >
                      <td>
                        <Link to={"/runs/" + run.id}>
                          {run.invoice_number ?? "Invoice number missing"}
                        </Link>
                        {run.parent_run_id && (
                          <span className="vendor">Retry / revision</span>
                        )}
                      </td>
                      <td>{run.vendor_name ?? "Unresolved"}</td>
                      <td className="amount">
                        {total
                          ? total.currency
                            ? money(total.value, total.currency)
                            : total.value
                          : "—"}
                      </td>
                      <td>
                        {run.outcome ? (
                          <Status value={run.outcome} />
                        ) : (
                          <span className="muted-text">Awaiting decision</span>
                        )}
                        <span className="vendor">
                          Processing: {humanize(run.status)}
                        </span>
                      </td>
                      <td
                        className="amount"
                        title="From persisted run timestamps, including queue time"
                      >
                        {run.finished_at
                          ? duration(
                              Date.parse(run.finished_at) -
                                Date.parse(run.created_at),
                            )
                          : "—"}
                      </td>
                      <td>
                        <time
                          dateTime={run.created_at}
                          title={when(run.created_at)}
                        >
                          {relativeTime(run.created_at)}
                        </time>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
