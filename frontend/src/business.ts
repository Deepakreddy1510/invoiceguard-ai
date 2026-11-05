import type { Rule } from "./models";
export const businessLabels: Record<string, string> = {
  DOCUMENT_ACCEPTED: "Invoice received",
  DOCUMENT_REPLAYED: "Previously uploaded invoice opened",
  DECISION_RECORDED: "Invoice decision recorded",
  CORRECTION_SAVED: "Invoice details corrected",
  PURCHASE_ORDER_CREATED: "Purchase order created",
  PURCHASE_ORDER_UPDATED: "Purchase order updated",
  PURCHASE_ORDER_CANCELLED: "Purchase order cancelled",
  VENDOR_UPDATED: "Supplier details updated",
  VENDOR_CREATED: "Supplier added",
  WORKSPACE_RENAMED: "Workspace renamed",
  WORKSPACE_ARCHIVED: "Workspace archived",
  WORKSPACE_RESTORED: "Workspace restored",
  RESERVATION_CREATED: "Order amount reserved",
  RESERVATION_REPLACED: "Reserved amount updated",
  RESERVATION_RELEASED: "Reserved amount released",

  EMAIL_SYNC_REQUESTED: "Email check requested",
  EMAIL_HANDOFF: "Invoice received from email",
  EMAIL_DISCONNECT: "Gmail disconnected",
  invoice_number: "Invoice number",
  invoice_date: "Invoice date",
  vendor_name: "Supplier",
  vendor_code: "Supplier code",
  tax_id: "Supplier tax identifier",
  po_number: "Purchase order",
  pricing_mode: "Tax basis",
  TAX_EXCLUSIVE: "Tax added to net price",
  TAX_INCLUSIVE: "Tax included in price",
  PDF_TEXT: "Digital document",
  OCR: "Scanned document was read",

  VALIDATED: "Validated",
  NEEDS_REVIEW: "Needs review",
  BLOCKED: "Blocked",
  QUEUED: "Waiting to process",
  RUNNING: "Processing",
  SUCCEEDED: "Completed",
  FAILED: "Processing failed",
  REVIEW: "Needs intake review",
  INGESTED: "Sent for validation",
  IGNORED: "Ignored",
  UNSUPPORTED: "Unsupported attachment",
  NOT_INVOICE: "Not an invoice",
  UNCERTAIN: "Invoice type unclear",
  SCREENING: "Checking attachment",
  FALLBACK: "Standard extraction",
  AUTO: "Automatic extraction",
  GEMINI: "AI-assisted extraction",
  VENDOR_APPROVED: "Supplier approval",
  VENDOR_IDENTITY: "Supplier identity",
  VENDOR_CONSISTENCY: "Supplier details agree",
  VENDOR_PO: "Supplier matches purchase order",
  PO_EXISTS: "Purchase order found",
  PO_STATUS: "Purchase order open for billing",
  PO_BALANCE: "Available purchase order balance",
  PO_DATES: "Purchase order dates",
  BUSINESS_DUPLICATE: "Invoice already recorded",
  NEAR_DUPLICATE: "Possible duplicate invoice",
  EMAIL_PO_CONTEXT: "Email and invoice references agree",
  GRAND_TOTAL: "Invoice total",
  HEADER_TAX: "Tax total",
  REQUIRED_PO_NUMBER: "Purchase order reference required",
};
export function checkGroup(id: string) {
  if (/DUPLICATE|COLLISION|EMAIL/.test(id))
    return "Duplicate and authorization checks";
  if (
    /^REQUIRED_|EVIDENCE|EXTRACTION|DOCUMENT_TYPE|INVOICE_NUMBER|FIELDS/.test(
      id,
    )
  )
    return "Invoice details";
  if (/^VENDOR_(?!PO)/.test(id)) return "Supplier";
  if (/^PO_|VENDOR_PO|MATCH|PRICE|QUANTITY|CURRENCY/.test(id))
    return "Purchase order";
  return "Amounts and taxes";
}
export const checkGroups = [
  "Supplier",
  "Invoice details",
  "Purchase order",
  "Amounts and taxes",
  "Duplicate and authorization checks",
];
export function primaryIssues(rules: Rule[]) {
  return [...rules]
    .filter((r) => r.outcome !== "PASS")
    .sort(
      (a, b) =>
        (a.outcome === "BLOCK" ? 0 : 1) - (b.outcome === "BLOCK" ? 0 : 1) ||
        checkGroups.indexOf(checkGroup(a.rule_id)) -
          checkGroups.indexOf(checkGroup(b.rule_id)),
    );
}
export function nextAction(outcome: string) {
  return outcome === "VALIDATED"
    ? "No correction is needed. Continue your organisation’s payment approval process; InvoiceGuard does not execute payments."
    : outcome === "BLOCKED"
      ? "Check the highlighted financial controls and request a corrected invoice or procurement authorisation. A review cannot bypass a financial block."
      : "Compare the highlighted details with the source invoice, then resolve them in Exception review.";
}
export function actorLabel(actor: string) {
  return actor === "local-demo-reviewer"
    ? "Demo Administrator"
    : /^(worker|gmail-worker|system)$/.test(actor)
      ? "Automated Processing"
      : actor.startsWith("auth0|")
        ? "Workspace member"
        : actor;
}

export function checkExplanation(rule: Rule) {
  const copy: Record<string, [string, string]> = {
    VENDOR_APPROVED: [
      "This supplier is approved for invoicing.",
      "This supplier is not approved for new invoices. Check its saved approval status.",
    ],
    VENDOR_IDENTITY: [
      "The supplier was identified from the invoice.",
      "The supplier could not be identified unambiguously. Check its name, supplier code and tax identifier.",
    ],
    VENDOR_CONSISTENCY: [
      "Supplier identifiers agree with the saved record.",
      "The supplied identifiers do not all agree with the saved supplier record.",
    ],
    PO_EXISTS: [
      "The referenced purchase order exists in this workspace.",
      "The referenced purchase order could not be found. Confirm the reference with the supplier.",
    ],
  };
  if (copy[rule.rule_id])
    return copy[rule.rule_id][rule.outcome === "PASS" ? 0 : 1];
  if (rule.rule_id.startsWith("DECIMAL_"))
    return rule.outcome === "PASS"
      ? "This amount uses a supported numeric format."
      : "Confirm a valid nonnegative amount in the source invoice.";

  if (rule.rule_id.startsWith("REQUIRED_"))
    return rule.outcome === "PASS"
      ? "The required value was verified against the source document."
      : "This required invoice detail was not found or could not be verified. Check the source document before correcting it.";
  if (rule.rule_id === "EXTRACTION_ISSUES" && rule.outcome === "PASS")
    return "No extraction ambiguities were reported.";
  return rule.explanation
    .replace(/original document [0-9a-f-]{36}/gi, "original recorded invoice")
    .replace(
      /\b[A-Z][A-Z_]{3,}\b/g,
      (value) =>
        businessLabels[value] ?? value.toLowerCase().replaceAll("_", " "),
    );
}

export function ruleLabel(id: string) {
  if (id.startsWith("REQUIRED_")) {
    const field = id.slice(9).toLowerCase();
    return (businessLabels[field] ?? field.replaceAll("_", " ")) + " required";
  }
  if (id.startsWith("DECIMAL_"))
    return id.slice(8).toLowerCase().replaceAll("_", " ") + " format";
  const line = id.match(/^LINE_(\d+)_(.+)$/);
  if (line)
    return (
      `Line ${line[1]} · ` +
      ({
        FIELDS: "Source details",
        SIGNS: "Supported amounts",
        PRICE: "Authorised price",
        TAX: "Tax rate",
        MATCH: "Order item",
        ARITHMETIC: "Arithmetic",
      }[line[2]] ?? line[2].toLowerCase())
    );
  if (id.startsWith("QUANTITY_"))
    return "Cumulative quantity · line " + id.slice(9);
  return (
    businessLabels[id] ??
    businessLabels[id.toUpperCase()] ??
    id
      .toLowerCase()
      .replaceAll("_", " ")
      .replace(/^./, (c) => c.toUpperCase())
  );
}
