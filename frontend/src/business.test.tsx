import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { humanize } from "./ui";
import { RuleResults } from "./RunDetails";
import { TechnicalDetails } from "./TechnicalDetails";
import { primaryIssues, actorLabel } from "./business";
afterEach(cleanup);
it("keeps processing, intake and financial statuses distinct", () => {
  expect(humanize("SUCCEEDED")).toBe("Completed");
  expect(humanize("VALIDATED")).toBe("Validated");
  expect(humanize("REVIEW")).toBe("Needs intake review");
  expect(actorLabel("worker")).toBe("Automated Processing");
});
it("orders blocks before review issues without changing source rules", () => {
  const rules = [
    {
      rule_id: "REQUIRED_PO_NUMBER",
      outcome: "REVIEW",
      explanation: "Reference missing",
      actual: null,
      expected: null,
    },
    {
      rule_id: "VENDOR_APPROVED",
      outcome: "BLOCK",
      explanation: "Supplier suspended",
      actual: null,
      expected: null,
    },
  ];
  expect(primaryIssues(rules).map((r) => r.rule_id)).toEqual([
    "VENDOR_APPROVED",
    "REQUIRED_PO_NUMBER",
  ]);
  expect(rules[0].rule_id).toBe("REQUIRED_PO_NUMBER");
});
it("does not present dependent amounts as passed when required information is missing", () => {
  render(
    <RuleResults
      rules={[
        {
          rule_id: "REQUIRED_PO_NUMBER",
          outcome: "REVIEW",
          explanation: "PO missing",
          actual: null,
          expected: null,
        },
        {
          rule_id: "GRAND_TOTAL",
          outcome: "PASS",
          explanation: "Arithmetic agrees",
          actual: null,
          expected: null,
        },
      ]}
    />,
  );
  expect(screen.getByText("Awaiting required information")).toBeVisible();
  expect(screen.queryByText("Checks passed")).not.toBeInTheDocument();
});
it("does not disclose technical records without an administrator workspace", () => {
  render(
    <TechnicalDetails>
      <pre>private-technical-record</pre>
    </TechnicalDetails>,
  );
  expect(
    screen.queryByText("private-technical-record"),
  ).not.toBeInTheDocument();
});
