import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import RunDetails, { stageInterval, stageState } from "./RunDetails";
import type { RunDetail, RunEvent } from "./models";
import completedSample from "./fixtures/completed-sample-events.json";
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
      summary: {
        po_number: "PO-1",
        requested: "120.00",
        currency: "USD",
        email_context: {
          policy_version: "email-po-review-v1",
          po_evidence: [{ value: "MAIL-PO-001" }],
        },
      },
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
    "Completed",
  );
  expect(screen.getByRole("heading", { name: "Blocked" })).toBeVisible();
  expect(
    screen.getAllByText("Actual backend balance explanation.").length,
  ).toBeGreaterThan(0);
  expect(
    screen.getByRole("link", { name: "View purchase order" }),
  ).toHaveAttribute("href", "/purchase-orders?po=PO-1");
  expect(screen.queryByText(/confidence/i)).not.toBeInTheDocument();
  expect(document.body).not.toHaveTextContent("[object Object]");
  expect(screen.queryByText("Copy run ID")).not.toBeInTheDocument();
});

it("keeps failed, skipped, retry and unfinished outcomes literal", () => {
  const run = {
    status: "FAILED",
    attempt: 2,
    events: [
      { ...event(1, "RUNNING", "2026-06-15T00:00:00Z"), attempt: 1 },
      { ...event(2, "FAILED", "2026-06-15T00:00:01Z"), attempt: 1 },
      { ...event(3, "RUNNING", "2026-06-15T00:00:02Z"), attempt: 2 },
      { ...event(4, "FAILED", "2026-06-15T00:00:03Z"), attempt: 2 },
      {
        ...event(5, "SKIPPED", "2026-06-15T00:00:03Z"),
        attempt: 2,
        stage: "ocr",
      },
      {
        ...event(6, "RUNNING", "2026-06-15T00:00:03Z"),
        attempt: 2,
        stage: "field_extraction",
      },
    ],
  } as RunDetail;
  const original = JSON.stringify(run.events);
  expect(stageState(run, "validation").state).toBe("FAILED");
  expect(stageState(run, "ocr").state).toBe("SKIPPED");
  expect(stageState(run, "field_extraction").state).toBe("INCOMPLETE");
  expect(
    stageState({ ...run, status: "RUNNING" }, "field_extraction").state,
  ).toBe("RUNNING");
  expect(
    stageState({ ...run, status: "RETRY_WAIT" }, "field_extraction").state,
  ).toBe("INCOMPLETE");
  expect(stageState({ ...run, attempt: 3 }, "validation").state).toBe(
    "PENDING",
  );
  expect(JSON.stringify(run.events)).toBe(original);
});

it("summarizes a real completed blocked sample without animating immutable starts", () => {
  const run = completedSample as RunDetail;
  expect(run.status).toBe("SUCCEEDED");
  expect(run.outcome).toBe("BLOCKED");
  expect(run.events.some((event) => event.outcome === "RUNNING")).toBe(true);
  expect(stageState(run, "validation").state).toBe("SUCCEEDED");
  expect(stageState(run, "ocr").state).toBe("SKIPPED");
  render(
    <RunDetails
      run={run}
      busy={false}
      onRetry={() => {}}
      onSelect={() => {}}
      onReview={() => {}}
    />,
  );
  fireEvent.click(screen.getByRole("tab", { name: "Activity" }));
  expect(
    document.querySelector(".business-execution .status-running"),
  ).toBeNull();
  expect(
    document.querySelector(".business-execution .status-skipped"),
  ).toHaveTextContent("Skipped");
  expect(document.querySelector(".business-execution")).not.toHaveTextContent(
    "Historical start",
  );
  expect(screen.getAllByText(/Historical start/).length).toBeGreaterThan(0);
});
