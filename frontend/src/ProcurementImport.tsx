import { TechnicalDetails } from "./TechnicalDetails";
import { humanize } from "./ui";
import { Help } from "./Experience";
import { useState } from "react";
import { apiFetch } from "./client";
import { Notice } from "./ui";
type Preview = {
  valid: boolean;
  row_count: number;
  record_count: number;
  file_sha256: string;
  errors: { row: number; message: string }[];
  records: {
    row: number;
    data: Record<string, unknown>;
    totals?: Record<string, string>;
  }[];
};
export default function ProcurementImport({
  kind,
  onDone,
}: {
  kind: "vendors" | "purchase-orders";
  onDone: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [key, setKey] = useState(crypto.randomUUID());
  async function template() {
    setError("");
    try {
      const response = await apiFetch(
        "/api/v1/procurement/imports/templates/" + kind + ".csv",
      );
      if (!response.ok) throw new Error("Template download failed.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = kind + "-template.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function submit(commit = false) {
    if (!file) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await apiFetch(
        "/api/v1/procurement/imports/" +
          (commit ? "commit" : "preview") +
          "?kind=" +
          kind,
        {
          method: "POST",
          body,
          headers: commit ? { "Idempotency-Key": key } : undefined,
        },
      );
      const data = await response.json();
      if (!response.ok) {
        if (data.detail?.errors)
          setPreview((p) =>
            p ? { ...p, valid: false, errors: data.detail.errors } : p,
          );
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : (data.detail?.message ?? "CSV validation failed."),
        );
      }
      if (commit) {
        setMessage(
          `${data.record_count} records imported${data.replayed ? " (already saved)" : ""}.`,
        );
        setPreview(null);
        setFile(null);
        onDone();
      } else setPreview(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="source-panel import-panel">
      <summary>
        Import {kind === "vendors" ? "vendors" : "purchase orders"} from CSV
      </summary>
      <p>
        Upload up to 500 rows in a UTF-8 CSV file (256 KiB maximum). Preview
        your rows before importing. No records are added until every row passes
        its checks.
      </p>
      <Help title="How should I prepare my file?">
        <p>
          Start with the template. Keep the header row unchanged and use one
          supplier per row, or the template’s line-item rows for each order.
          Enter tax rates as fractions: 0.18 means 18%. Errors identify the row
          to correct; no partial import is saved.
        </p>
      </Help>
      <button type="button" onClick={template}>
        Download CSV template
      </button>
      <label className="comment-label">
        Procurement CSV
        <input
          type="file"
          disabled={busy}
          accept=".csv,text/csv"
          aria-label={"Import " + kind + " CSV"}
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null);
            setPreview(null);
            setMessage("");
            setError("");
            setKey(crypto.randomUUID());
          }}
        />
      </label>
      <button
        type="button"
        disabled={!file || busy}
        onClick={() => void submit(false)}
      >
        Preview import
      </button>
      <Notice error={error} />
      {message && (
        <p role="status" className="submission-message">
          {message}
        </p>
      )}
      {preview && (
        <div>
          <p>
            {preview.row_count} rows · {preview.record_count} records ·{" "}
            {preview.valid ? "Ready to import" : "Validation errors"}
          </p>
          {preview.errors.map((row, index) => (
            <p className="inline-error" key={index}>
              Row {row.row}: {row.message}
            </p>
          ))}
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>CSV row</th>
                  <th>Record details</th>
                </tr>
              </thead>
              <tbody>
                {preview.records.map((record) => (
                  <tr key={record.row}>
                    <td>{record.row}</td>
                    <td>
                      <dl className="import-preview-fields">
                        {Object.entries(record.data).map(([key, value]) => (
                          <div key={key}>
                            <dt>{humanize(key)}</dt>
                            <dd>
                              {value === null
                                ? "—"
                                : typeof value === "object"
                                  ? Array.isArray(value)
                                    ? `${value.length} line items`
                                    : "Additional details"
                                  : typeof value === "string" &&
                                      /^[A-Z_]+$/.test(value)
                                    ? humanize(value)
                                    : String(value)}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <TechnicalDetails label="Import source and calculations">
            <pre>{JSON.stringify(preview.records, null, 2)}</pre>
          </TechnicalDetails>
          <button
            className="primary"
            type="button"
            disabled={!preview.valid || busy}
            onClick={() => void submit(true)}
          >
            Import records
          </button>
        </div>
      )}
    </details>
  );
}
