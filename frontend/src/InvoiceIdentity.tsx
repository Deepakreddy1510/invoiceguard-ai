import { Icon } from "./icons";
import { CopyButton } from "./ui";

/** Identity is neutral. Financial and processing state belong in separate badges. */
export function InvoiceIdentity({
  number,
  supplier,
  compact = true,
  copy = false,
  fallback = "Invoice details pending",
}: {
  number?: string | null;
  supplier?: string | null;
  compact?: boolean;
  copy?: boolean;
  fallback?: string;
}) {
  const label = number || fallback;
  return (
    <span
      className={
        "invoice-identity " +
        (compact ? "identity-compact" : "identity-expanded")
      }
    >
      <span className="invoice-document-mark" aria-hidden="true">
        <Icon name="file" />
      </span>
      <span className="invoice-identity-text">
        <strong className="invoice-identifier" title={label}>
          {label}
        </strong>
        {supplier !== undefined && (
          <span
            className="invoice-supplier"
            title={supplier || "Supplier not identified"}
          >
            {supplier || "Supplier not identified"}
          </span>
        )}
      </span>
      {copy && number && (
        <CopyButton text={number} label="Copy invoice number" />
      )}
    </span>
  );
}
