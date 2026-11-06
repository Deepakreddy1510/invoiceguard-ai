import { TablePagination } from "../Workbench";
import { Dialog, Help } from "../Experience";
import { useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../client";
import {
  EmptyState,
  FilterChips,
  Notice,
  PageTitle,
  Skeleton,
  Status,
  useResource,
} from "../ui";
import ProcurementImport from "../ProcurementImport";
type Vendor = {
  id: string;
  legal_name: string;
  code: string;
  tax_id: string | null;
  status: string;
  version: number;
  po_count: number;
  identity_locked: boolean;
};
const blank = { legal_name: "", code: "", tax_id: "", status: "APPROVED" };
export default function Vendors() {
  const resource = useResource<Vendor[]>("/vendors", 5000);
  const me = useResource<{ can_manage_procurement: boolean }>("/me");
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [editing, setEditing] = useState<Vendor | null | false>(false);
  const [values, setValues] = useState(blank);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<Vendor | null>(null);
  const manager = !!me.data?.can_manage_procurement;
  function edit(vendor: Vendor | null) {
    setEditing(vendor);
    setValues(
      vendor
        ? {
            legal_name: vendor.legal_name,
            code: vendor.code,
            tax_id: vendor.tax_id ?? "",
            status: vendor.status,
          }
        : blank,
    );
    setError("");
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await request("/vendors" + (editing ? "/" + editing.id : ""), {
        method: editing ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...values,
          tax_id: values.tax_id || null,
          ...(editing ? { version: editing.version } : {}),
        }),
      });
      setMessage(
        editing
          ? "Vendor updated. Prior financial history is retained."
          : "Vendor created. You can now create its purchase order.",
      );
      setEditing(false);
      resource.reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!confirmDelete) return;
    setBusy(true);
    setError("");
    try {
      await request(
        "/vendors/" + confirmDelete.id + "?version=" + confirmDelete.version,
        { method: "DELETE" },
      );
      setMessage("Unused vendor deleted; its audit record is retained.");
      setConfirmDelete(null);
      resource.reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const shown = (resource.data ?? []).filter(
    (v) =>
      (!status || v.status === status) &&
      (v.code + " " + v.legal_name + " " + (v.tax_id ?? ""))
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const currentPage = Math.min(
    page,
    Math.max(0, Math.ceil(shown.length / 10) - 1),
  );
  return (
    <>
      <PageTitle
        eyebrow="PROCUREMENT / VENDORS"
        title="Your suppliers, together."
        description="Keep supplier details accurate, control who can bill you and find their purchase orders in one place."
        action={
          manager && (
            <button
              className="primary"
              disabled={busy}
              onClick={() => edit(null)}
            >
              Create Vendor
            </button>
          )
        }
      />
      <Notice
        error={error || resource.error}
        onRetry={() => {
          setError("");
          resource.reload();
        }}
      />
      {message && (
        <p className="submission-message" role="status">
          {message}
        </p>
      )}
      <Help title="What do supplier statuses mean?">
        <p>
          Approved suppliers can submit invoices for validation. Suspending a
          supplier temporarily blocks new validation; marking one inactive
          prevents new invoices while keeping its existing orders and history.
          Status changes do not release amounts already reserved.
        </p>
      </Help>
      {editing !== false && (
        <Dialog
          title={editing ? "Edit vendor" : "Create vendor"}
          onClose={() => !busy && setEditing(false)}
        >
          <section className="detail-panel">
            <div className="section-heading">
              <h2>{editing ? "Edit vendor" : "Create vendor"}</h2>
              <button onClick={() => setEditing(false)}>Close form</button>
            </div>
            {editing && editing.identity_locked && (
              <div className="notice">
                This supplier already has orders or invoices. Its identifying
                details are protected to preserve history. You can still update
                its status. Add a separate supplier when its legal identity
                changes.
              </div>
            )}
            <Notice error={error} />
            <form onSubmit={save}>
              <fieldset disabled={busy}>
                <div className="field-grid">
                  <label>
                    Legal vendor name
                    <input
                      aria-label="Legal vendor name"
                      required
                      minLength={2}
                      maxLength={200}
                      disabled={!!(editing && editing.identity_locked)}
                      value={values.legal_name}
                      onChange={(e) =>
                        setValues((v) => ({ ...v, legal_name: e.target.value }))
                      }
                    />
                  </label>
                  <label>
                    Vendor code
                    <input
                      aria-label="Vendor code"
                      required
                      maxLength={40}
                      disabled={!!(editing && editing.identity_locked)}
                      value={values.code}
                      onChange={(e) =>
                        setValues((v) => ({ ...v, code: e.target.value }))
                      }
                    />
                  </label>
                  <label>
                    Tax identifier
                    <input
                      aria-label="Tax identifier"
                      maxLength={80}
                      disabled={!!(editing && editing.identity_locked)}
                      value={values.tax_id}
                      onChange={(e) =>
                        setValues((v) => ({ ...v, tax_id: e.target.value }))
                      }
                    />
                  </label>
                  <label>
                    Status
                    <select
                      aria-label="Vendor status"
                      value={values.status}
                      onChange={(e) =>
                        setValues((v) => ({ ...v, status: e.target.value }))
                      }
                    >
                      {["APPROVED", "SUSPENDED", "INACTIVE"].map((value) => (
                        <option key={value} value={value}>
                          {value[0] + value.slice(1).toLowerCase()}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <div className="toolbar">
                  <button className="primary" type="submit">
                    Save vendor
                  </button>
                </div>
              </fieldset>
            </form>
          </section>
        </Dialog>
      )}
      {manager && <ProcurementImport kind="vendors" onDone={resource.reload} />}
      <section className="panel">
        <div className="table-toolbar">
          <FilterChips
            label="Filter vendor status"
            value={status}
            onChange={(value) => {
              setStatus(value);
              setPage(0);
            }}
            options={[
              { value: "", label: "All" },
              ...["APPROVED", "SUSPENDED", "INACTIVE"].map((value) => ({
                value,
                label: value[0] + value.slice(1).toLowerCase(),
              })),
            ]}
          />
          <input
            aria-label="Search vendors"
            placeholder="Name, code or tax identifier"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
          />
        </div>
        {resource.loading ? (
          <Skeleton label="Loading vendors" />
        ) : !shown.length ? (
          <EmptyState
            title="No vendors in this view"
            action={
              manager && (
                <button onClick={() => edit(null)}>
                  Add your first vendor
                </button>
              )
            }
          >
            Start by adding a vendor and creating a purchase order. Then upload
            your first invoice.
          </EmptyState>
        ) : (
          <div
            className="table-scroll catalogue-table"
            role="region"
            aria-label="Scrollable supplier table"
            tabIndex={0}
          >
            <table>
              <thead>
                <tr>
                  <th>Legal name / code</th>
                  <th>Tax identifier</th>
                  <th>Status</th>
                  <th className="amount">Linked POs</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {shown
                  .slice(currentPage * 10, currentPage * 10 + 10)
                  .map((vendor) => (
                    <tr key={vendor.id}>
                      <td>
                        <strong>{vendor.legal_name}</strong>
                        <span className="vendor">{vendor.code}</span>
                      </td>
                      <td>{vendor.tax_id ?? "—"}</td>
                      <td>
                        <Status value={vendor.status} />
                      </td>
                      <td className="amount">{vendor.po_count}</td>
                      <td>
                        {manager && (
                          <div className="action-buttons">
                            <button
                              disabled={busy}
                              onClick={() => edit(vendor)}
                            >
                              Edit / deactivate
                            </button>
                            <button
                              disabled={vendor.identity_locked}
                              title={
                                vendor.identity_locked
                                  ? "Dependent history prevents deletion. Deactivate instead."
                                  : undefined
                              }
                              onClick={() => setConfirmDelete(vendor)}
                            >
                              Delete
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
        <TablePagination
          size={10}
          page={currentPage}
          total={shown.length}
          onChange={setPage}
        />
      </section>
      {confirmDelete && (
        <section className="notice" role="alert">
          <p>
            Delete unused vendor {confirmDelete.code}? An audit record will
            remain.
          </p>
          <button className="danger" disabled={busy} onClick={remove}>
            Confirm vendor deletion
          </button>
          <button onClick={() => setConfirmDelete(null)}>Keep vendor</button>
        </section>
      )}
      <p className="footnote">
        Inactive and suspended vendors cannot validate new invoices under the
        existing financial controls.{" "}
        <Link to="/purchase-orders">Manage purchase orders</Link>
      </p>
    </>
  );
}
