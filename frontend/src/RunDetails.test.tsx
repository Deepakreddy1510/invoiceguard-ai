import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import RunDetails, { stageInterval } from "./RunDetails";
import type { RunDetail, RunEvent } from "./models";
const event = (
  id: number,
  outcome: string,
  at: string,
  attempt = 1,
): RunEvent => ({
  id,
  stage: "validation",
  outcome,
  created_at: at,
  attempt,
  detail: "Persisted " + outcome,
});
afterEach(cleanup);
it("requires matching start/finish events in the same attempt before showing a stage interval", () => {
  const start = event(1, "RUNNING", "2026-06-15T00:00:00Z"),
    end = event(2, "SUCCEEDED", "2026-06-15T00:00:02Z");
  expect(stageInterval([start, end], end)).toBe(2000);
  expect(stageInterval([end], end)).toBeNull();
  expect(
    stageInterval([start, { ...end, attempt: 2 }], { ...end, attempt: 2 }),
  ).toBeNull();
  expect(stageInterval([start], start)).toBeNull();
});
it("keeps succeeded processing distinct from a blocked financial outcome with backend reasons", () => {
  const run: RunDetail = {
    id: "id",
    document_id: "doc",
    parent_run_id: null,
    status: "SUCCEEDED",
    attempt: 1,
    outcome: "BLOCKED",
    invoice_number: "INV-1",
    created_at: "2026-06-15T00:00:00Z",
    finished_at: "2026-06-15T00:00:02Z",
    error: null,
    events: [
      event(1, "RUNNING", "2026-06-15T00:00:00Z"),
      event(2, "SUCCEEDED", "2026-06-15T00:00:02Z"),
    ],
    pages: null,
    extraction: null,
    decision: {
      outcome: "BLOCKED",
      summary: { po_number: "PO-1", requested: "120.00", currency: "USD" },
      rules: [
        {
          rule_id: "PO_BALANCE",
          outcome: "BLOCK",
          explanation: "Actual backend balance explanation.",
          actual: "120",
          expected: "100",
        },
      ],
    },
  };
  render(
    <RunDetails
      run={run}
      busy={false}
      onRetry={() => {}}
      onSelect={() => {}}
      onReview={() => {}}
    />,
  );
  expect(document.querySelector(".run-status .status")).toHaveTextContent(
    "Succeeded",
  );
  expect(screen.getByRole("heading", { name: "Blocked" })).toBeVisible();
  expect(
    screen.getAllByText("Actual backend balance explanation.").length,
  ).toBeGreaterThan(0);
  expect(
    screen.getByRole("link", { name: "View purchase order" }),
  ).toHaveAttribute("href", "/purchase-orders?po=PO-1");
  expect(screen.queryByText(/confidence/i)).not.toBeInTheDocument();
});
