export type Evidence = {
  value: string | null;
  verified: boolean;
  page: number | null;
  quote: string | null;
  method: string | null;
  document_id?: string;
  reviewer?: string;
};
export type LineItem = Record<string, Evidence>;
export type RunEvent = {
  id: number;
  stage: string;
  outcome: string;
  attempt: number;
  detail: string;
  created_at: string;
};
export type Rule = {
  rule_id: string;
  outcome: string;
  explanation: string;
  actual: string | null;
  expected: string | null;
};
export type RunSummary = {
  intake_context?: {
    policy_version: string;
    message_id: string;
    attachment_id: string;
    po_evidence: { value: string; source: string; quote: string }[];
    selected_po_number?: string | null;
  } | null;
  requested_mode?: string;
  actual_provider?: string | null;
  model?: string | null;
  fallback_reason?: string | null;
  id: string;
  document_id: string;
  archived_at?: string | null;
  parent_run_id: string | null;
  status: string;
  attempt: number;
  outcome: string | null;
  invoice_number?: string | null;
  vendor_name?: string | null;
  created_at: string;
  finished_at?: string | null;
  error: string | null;
};
export type Extraction = {
  model?: string | null;
  attempted_provider?: string | null;
  attempted_model?: string | null;
  requested_mode?: string;
  provider: string;
  fallback_reason: string | null;
  fields: Record<string, unknown> & { items?: LineItem[]; issues?: string[] };
};
export type Decision = {
  outcome: string;
  rules: Rule[];
  summary: Record<string, unknown>;
  policy_version?: string;
};
export type RunDetail = RunSummary & {
  review_task_id?: string | null;
  events: RunEvent[];
  pages: { page: number; text: string; method: string }[] | null;
  extraction: Extraction | null;
  decision: Decision | null;
};
export const outcomes = ["VALIDATED", "NEEDS_REVIEW", "BLOCKED"] as const;
export const isTerminal = (run: RunSummary) =>
  ["SUCCEEDED", "FAILED"].includes(run.status);
export function fact(
  run: RunDetail | undefined | null,
  name: string,
): Evidence | undefined {
  const value = run?.extraction?.fields[name];
  return value && typeof value === "object" && "value" in value
    ? (value as Evidence)
    : undefined;
}
export function amount(run: RunDetail | undefined | null) {
  const total = run?.decision?.summary.requested ?? fact(run, "total")?.value;
  const currency =
    run?.decision?.summary.currency ?? fact(run, "currency")?.value;
  return typeof total === "string"
    ? {
        value: total,
        currency: typeof currency === "string" ? currency : undefined,
      }
    : null;
}
