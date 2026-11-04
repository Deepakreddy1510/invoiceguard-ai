import { Link, useSearchParams } from "react-router-dom";
import { type PurchaseOrder } from "../api";
import POEditor, { type EditablePO } from "../POEditor";
import ProcurementImport from "../ProcurementImport";
import { request, money, when, utilization } from "../client";
import {
  EmptyState,
  Notice,
  PageTitle,
  Skeleton,
  Status,
  useResource,
} from "../ui";
import { Icon } from "../icons";
import { useState } from "react";
type PODetail = {
  id: string;
  version: number;
  has_history: boolean;
  vendor_id: string;
  billing_mode: string;
  issued_on: string;
  valid_until: string;
  number: string;
  vendor: string;
  currency: string;
  status: string;
  authorized: string;
  reserved: string;
  settled: string;
  available: string;
  items: {
    sku: string;
    description: string;
    quantity: string;
    unit_price: string;
    tax_rate: string;
  }[];
  commitments: {
    id: string;
    run_id: string;
    amount: string;
    status: string;
    created_at: string;
  }[];
};
export default function PurchaseOrders() {
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const me = useResource<{ can_manage_procurement: boolean }>("/me");
  const [editing, setEditing] = useState<EditablePO | null | false>(false);
  const [mutationError, setMutationError] = useState("");
  const [notice, setNotice] = useState("");
  const [action, setAction] = useState<"cancel" | "delete" | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const list = useResource<PurchaseOrder[]>("/purchase-orders", 5000);
  const orders = list.data ?? [];
  const selected = orders.find((po) => po.number === params.get("po"));
  const detail = useResource<PODetail>(
    selected ? "/purchase-orders/" + selected.id : null,
    5000,
  );
  const shown = orders.filter((po) =>
    (po.number + " " + po.vendor.legal_name)
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  async function mutate() {
    if (!selected || !action) return;
    setBusy(true);
    setMutationError("");
    try {
      await request(
        "/purchase-orders/" +
          selected.id +
          (action === "cancel" ? "/cancel" : "?version=" + selected.version),
        {
          method: action === "cancel" ? "POST" : "DELETE",
          ...(action === "cancel"
            ? {
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ version: selected.version, reason }),
              }
            : {}),
        },
      );
      setNotice(
        action === "cancel"
          ? "PO cancelled. Existing commitments and history were not released."
          : "Unused PO deleted; its audit record remains.",
      );
      setAction(null);
      setParams({});
      list.reload();
      detail.reload();
    } catch (e) {
      setMutationError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageTitle
        eyebrow="PROCUREMENT / FINANCIAL CAPACITY"
        title="Authorized. Reserved. Available."
        description="The purchase-order capacity behind each invoice, in its original currency."
        action={
          me.data?.can_manage_procurement && (
            <button className="primary" onClick={() => setEditing(null)}>
              Create Purchase Order
            </button>
          )
        }
      />
      <Notice
        error={
          list.error ? "Procurement API is unavailable. " + list.error : ""
        }
        onRetry={list.reload}
      />
      <Notice
        error={mutationError}
        onRetry={() => {
          setMutationError("");
          list.reload();
          detail.reload();
        }}
      />
      {notice && (
        <p role="status" className="submission-message">
          {notice}
        </p>
      )}
      {editing !== false && (
        <POEditor
          key={(editing && editing.id) || "new"}
          initial={editing || null}
          onClose={() => setEditing(false)}
          onSaved={(number) => {
            setEditing(false);
            setNotice("Purchase order saved.");
            setParams({ po: number });
            list.reload();
            detail.reload();
          }}
        />
      )}
      {me.data?.can_manage_procurement && (
        <ProcurementImport kind="purchase-orders" onDone={list.reload} />
      )}
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Purchase orders</h2>
            <p>
              Reserved and held commitments consume capacity. Released
              commitments do not.
            </p>
          </div>
          <span className="tag" role="status">
            {list.data
              ? `${orders.length} records · API connected`
              : "Connecting to API…"}
          </span>
        </div>
        <div className="table-toolbar">
          <label className="search-field">
            <Icon name="search" />
            <span className="sr-only">Search purchase orders</span>
            <input
              aria-label="Search purchase orders"
              placeholder="Search purchase order or vendor"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
        </div>
        {list.loading ? (
          <Skeleton label="Loading purchase orders" rows={5} />
        ) : !shown.length && !list.error ? (
          <EmptyState title="No purchase orders found">
            {search
              ? "Try another PO number or vendor."
              : "Authorized procurement records will appear here."}
          </EmptyState>
        ) : (
          <div className="table-scroll po-scroll">
            <table>
              <thead>
                <tr>
                  <th>Purchase order / vendor</th>
                  <th className="amount">Authorized</th>
                  <th className="amount">Reserved / held</th>
                  <th className="amount">Available</th>
                  <th className="amount">Settled</th>
                  <th>Reserved utilization</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((po) => {
                  const percent = utilization(
                    po.reserved_gross,
                    po.authorized_gross,
                  );
                  return (
                    <tr
                      className={selected?.id === po.id ? "selected-row" : ""}
                      key={po.id}
                    >
                      <td>
                        <button
                          className="text-button"
                          aria-expanded={selected?.id === po.id}
                          onClick={() =>
                            setParams(
                              selected?.id === po.id ? {} : { po: po.number },
                            )
                          }
                        >
                          {po.number}
                          <Icon name="chevron" />
                        </button>
                        <span className="vendor">{po.vendor.legal_name}</span>
                        {po.vendor.status !== "APPROVED" && (
                          <span className="evidence-flag">
                            Vendor {po.vendor.status.toLowerCase()}
                          </span>
                        )}
                      </td>
                      <td className="amount">
                        {money(po.authorized_gross, po.currency)}
                      </td>
                      <td className="amount">
                        {po.reserved_gross != null
                          ? money(po.reserved_gross, po.currency)
                          : "—"}
                      </td>
                      <td className="amount">
                        {po.available_gross != null
                          ? money(po.available_gross, po.currency)
                          : "—"}
                      </td>
                      <td className="amount">
                        {po.settled_gross != null
                          ? money(po.settled_gross, po.currency)
                          : "—"}
                      </td>
                      <td>
                        {percent != null ? (
                          <div className="utilization">
                            <div
                              role="meter"
                              aria-label={"Reserved capacity for " + po.number}
                              aria-valuenow={percent}
                              aria-valuemin={0}
                              aria-valuemax={100}
                            >
                              <span style={{ width: percent + "%" }} />
                            </div>
                            <span>{percent.toFixed(1)}% reserved</span>
                          </div>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td>
                        <Status value={po.status} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <p className="footnote">
        Authorization is not a payment. Figures are persisted procurement and
        commitment balances.
      </p>
      {params.get("po") && !selected && list.data && (
        <Notice
          error="The requested purchase order was not found in this workspace."
          onRetry={list.reload}
        />
      )}
      {selected && (
        <section
          className="panel detail-panel"
          aria-label="Purchase order details"
        >
          <Notice error={detail.error} onRetry={detail.reload} />
          {detail.loading ? (
            <Skeleton label="Loading PO commitments" />
          ) : (
            detail.data && (
              <>
                <div className="panel-heading">
                  <div>
                    <p className="eyebrow">PURCHASE ORDER DETAIL</p>
                    <h2>{detail.data.number}</h2>
                    <p>{detail.data.vendor}</p>
                  </div>
                  <Status value={detail.data.status} />
                  <button
                    className="icon-button"
                    aria-label="Close purchase order details"
                    onClick={() => setParams({})}
                  >
                    <Icon name="close" />
                  </button>
                </div>
                <dl className="financial-summary">
                  {[
                    ["Authorized", detail.data.authorized],
                    ["Reserved / held", detail.data.reserved],
                    ["Settled", detail.data.settled],
                    ["Available", detail.data.available],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <dt>{label}</dt>
                      <dd>{money(value, detail.data!.currency)}</dd>
                    </div>
                  ))}
                </dl>
                {me.data?.can_manage_procurement && (
                  <div className="toolbar">
                    <button
                      disabled={detail.data.has_history}
                      title={
                        detail.data.has_history
                          ? "Financial history locks PO identity, authorization and items."
                          : undefined
                      }
                      onClick={() =>
                        setEditing({
                          id: detail.data!.id,
                          version: detail.data!.version,
                          number: detail.data!.number,
                          vendor_id: detail.data!.vendor_id,
                          currency: detail.data!.currency,
                          status: detail.data!.status,
                          issued_on: detail.data!.issued_on,
                          valid_until: detail.data!.valid_until,
                          billing_mode: detail.data!.billing_mode,
                          authorized_gross: detail.data!.authorized,
                          items: detail.data!.items,
                        })
                      }
                    >
                      Edit Purchase Order
                    </button>
                    <button
                      disabled={detail.data.status === "CANCELLED"}
                      onClick={() => {
                        setAction("cancel");
                        setReason("");
                      }}
                    >
                      Cancel Purchase Order
                    </button>
                    <button
                      disabled={detail.data.has_history}
                      onClick={() => setAction("delete")}
                    >
                      Delete unused PO
                    </button>
                  </div>
                )}
                {detail.data.has_history && (
                  <p className="notice">
                    Financial history locks this PO's authorization and
                    identity. Cancellation prevents new validation but does not
                    release historical or settled commitments.
                  </p>
                )}
                {action && (
                  <div className="notice">
                    <p>
                      {action === "cancel"
                        ? "Cancel this PO while retaining all commitments and decisions?"
                        : "Delete this unused PO? An audit record will remain."}
                    </p>
                    {action === "cancel" && (
                      <label>
                        Cancellation reason
                        <textarea
                          aria-label="Cancellation reason"
                          minLength={10}
                          maxLength={2000}
                          value={reason}
                          onChange={(e) => setReason(e.target.value)}
                        />
                      </label>
                    )}
                    <button
                      className="danger"
                      disabled={
                        busy ||
                        (action === "cancel" && reason.trim().length < 10)
                      }
                      onClick={mutate}
                    >
                      {action === "cancel"
                        ? "Confirm PO cancellation"
                        : "Confirm PO deletion"}
                    </button>
                    <button onClick={() => setAction(null)}>Keep PO</button>
                  </div>
                )}
                <h3>Ordered items</h3>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Item</th>
                        <th className="amount">Quantity</th>
                        <th className="amount">Unit price</th>
                        <th className="amount">Tax rate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.data.items.map((item) => (
                        <tr key={item.sku}>
                          <td>
                            {item.sku}
                            <span className="vendor">{item.description}</span>
                          </td>
                          <td className="amount">{item.quantity}</td>
                          <td className="amount">
                            {money(item.unit_price, detail.data!.currency)}
                          </td>
                          <td className="amount">{item.tax_rate}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <h3>Commitment history</h3>
                {!detail.data.commitments.length ? (
                  <EmptyState title="No financial commitments">
                    There are no recorded commitments for this purchase order.
                  </EmptyState>
                ) : (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Invoice decision</th>
                          <th className="amount">Amount</th>
                          <th>State</th>
                          <th>Created</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.data.commitments.map((c) => (
                          <tr key={c.id}>
                            <td>
                              <Link to={"/runs/" + c.run_id}>
                                Open invoice <Icon name="arrow" />
                              </Link>
                            </td>
                            <td className="amount">
                              {money(c.amount, detail.data!.currency)}
                            </td>
                            <td>
                              <Status value={c.status} />
                            </td>
                            <td>{when(c.created_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )
          )}
        </section>
      )}
    </>
  );
}
