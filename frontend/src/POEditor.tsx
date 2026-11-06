import { Dialog } from "./Experience";
import { useState } from "react";
import { request, money } from "./client";
import { Notice, useResource } from "./ui";
export type POItem = {
  sku: string;
  description: string;
  quantity: string;
  unit_price: string;
  tax_rate: string;
};
export type EditablePO = {
  id: string;
  version: number;
  number: string;
  vendor_id: string;
  currency: string;
  status: string;
  issued_on: string;
  valid_until: string;
  billing_mode: string;
  authorized_gross: string;
  items: POItem[];
};
const blankItem = (): POItem => ({
  sku: "",
  description: "",
  quantity: "1",
  unit_price: "",
  tax_rate: "0",
});
function scaled(value: string, places = 6) {
  if (!new RegExp("^\\d{1,14}(\\.\\d{1," + places + "})?$").test(value))
    throw new Error("Invalid decimal");
  const [whole, fraction = ""] = value.split(".");
  return BigInt(whole + fraction.padEnd(places, "0"));
}
export function calculatePO(items: POItem[], currency: string) {
  try {
    const places = currency === "JPY" ? 0 : currency === "KWD" ? 3 : 2;
    const power = 10n ** BigInt(places);
    const halfUp = (value: bigint, divisor: bigint) =>
      (value + divisor / 2n) / divisor;
    let subtotal = 0n,
      tax = 0n;
    for (const item of items) {
      const q = scaled(item.quantity),
        price = scaled(item.unit_price),
        rate = scaled(item.tax_rate, 8);
      if (q <= 0n || rate > 100000000n) return null;
      const net = halfUp(q * price * power, 1000000000000n);
      subtotal += net;
      tax += halfUp(net * rate, 100000000n);
    }
    const decimal = (value: bigint) => {
      if (!places) return value.toString();
      const digits = value.toString().padStart(places + 1, "0");
      return digits.slice(0, -places) + "." + digits.slice(-places);
    };
    return {
      subtotal: decimal(subtotal),
      tax: decimal(tax),
      gross: decimal(subtotal + tax),
    };
  } catch {
    return null;
  }
}
export default function POEditor({
  initial,
  onClose,
  onSaved,
}: {
  initial: EditablePO | null;
  onClose: () => void;
  onSaved: (number: string) => void;
}) {
  const vendors =
    useResource<
      { id: string; code: string; legal_name: string; status: string }[]
    >("/vendors");
  const year = new Date().getFullYear();
  const [form, setForm] = useState(
    initial ?? {
      number: "",
      vendor_id: "",
      currency: "USD",
      status: "OPEN",
      issued_on: year + "-01-01",
      valid_until: year + "-12-31",
      billing_mode: "ITEMIZED",
      authorized_gross: "",
      items: [blankItem()],
    },
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const totals = form.items.length
    ? calculatePO(form.items, form.currency)
    : null;
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload = {
        number: form.number,
        vendor_id: form.vendor_id,
        currency: form.currency,
        status: form.status,
        issued_on: form.issued_on,
        valid_until: form.valid_until,
        billing_mode: form.billing_mode,
        authorized_gross: form.authorized_gross,
        items: form.items.map(
          ({ sku, description, quantity, unit_price, tax_rate }) => ({
            sku,
            description,
            quantity,
            unit_price,
            tax_rate,
          }),
        ),
        ...(initial ? { version: initial.version } : {}),
      };
      const result = await request<{ number: string }>(
        "/purchase-orders" + (initial ? "/" + initial.id : ""),
        {
          method: initial ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      onSaved(result.number);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const update = (key: string, value: string) =>
    setForm((f) => ({ ...f, [key]: value }));
  return (
    <Dialog
      title={initial ? "Edit purchase order" : "Create purchase order"}
      wide
      onClose={() => !busy && onClose()}
    >
      <section className="detail-panel" aria-label="Purchase order editor">
        <div className="section-heading">
          <h2>{initial ? "Edit purchase order" : "Create purchase order"}</h2>
          <button type="button" disabled={busy} onClick={onClose}>
            Close form
          </button>
        </div>
        <Notice error={error || vendors.error} onRetry={vendors.reload} />
        <form onSubmit={save}>
          <fieldset disabled={busy}>
            <div className="field-grid">
              <label>
                PO number
                <input
                  aria-label="PO number"
                  required
                  maxLength={60}
                  value={form.number}
                  onChange={(e) => update("number", e.target.value)}
                />
              </label>
              <label>
                Vendor
                <select
                  aria-label="PO vendor"
                  required
                  value={form.vendor_id}
                  onChange={(e) => update("vendor_id", e.target.value)}
                >
                  <option value="">Select vendor in this workspace</option>
                  {vendors.data?.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.code} · {v.legal_name} · {v.status}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Currency
                <select
                  aria-label="PO currency"
                  value={form.currency}
                  onChange={(e) => update("currency", e.target.value)}
                >
                  {["USD", "INR", "EUR", "GBP", "JPY", "KWD"].map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </label>
              <label>
                Status
                <select
                  aria-label="PO status"
                  value={form.status}
                  onChange={(e) => update("status", e.target.value)}
                >
                  {[
                    "OPEN",
                    "CLOSED",
                    "CANCELLED",
                    ...(initial?.status === "PARTIALLY_BILLED"
                      ? ["PARTIALLY_BILLED"]
                      : []),
                  ].map((status) => (
                    <option
                      key={status}
                      disabled={status === "PARTIALLY_BILLED"}
                    >
                      {status}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Issue date
                <input
                  type="date"
                  aria-label="PO issue date"
                  required
                  value={form.issued_on}
                  onChange={(e) => update("issued_on", e.target.value)}
                />
              </label>
              <label>
                Valid until
                <input
                  type="date"
                  aria-label="PO valid until"
                  min={form.issued_on}
                  required
                  value={form.valid_until}
                  onChange={(e) => update("valid_until", e.target.value)}
                />
              </label>
              <label>
                Billing mode
                <select
                  aria-label="PO billing mode"
                  value={form.billing_mode}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      billing_mode: e.target.value,
                      items:
                        e.target.value === "AMOUNT_BASED"
                          ? []
                          : f.items.length
                            ? f.items
                            : [blankItem()],
                    }))
                  }
                >
                  <option value="ITEMIZED">Itemized</option>
                  <option value="AMOUNT_BASED">Amount-based</option>
                </select>
              </label>
              <label>
                Authorized gross
                <input
                  inputMode="decimal"
                  aria-label="Authorized gross"
                  required
                  value={form.authorized_gross}
                  onChange={(e) => update("authorized_gross", e.target.value)}
                />
              </label>
            </div>
            <h3>Line items</h3>
            {form.billing_mode === "AMOUNT_BASED" && !form.items.length && (
              <p className="footnote">
                Amount-based authorization is set directly. No opening billed
                balance or tax allocation is invented; real invoice controls
                still run.
              </p>
            )}
            <div className="table-scroll">
              <table className="editable-items">
                <thead>
                  <tr>
                    {[
                      "SKU",
                      "Description",
                      "Quantity",
                      "Unit price",
                      "Tax rate",
                    ].map((label) => (
                      <th key={label}>{label}</th>
                    ))}
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {form.items.map((item, index) => (
                    <tr key={index}>
                      {(
                        [
                          "sku",
                          "description",
                          "quantity",
                          "unit_price",
                          "tax_rate",
                        ] as const
                      ).map((key) => (
                        <td key={key}>
                          <input
                            aria-label={"PO item " + (index + 1) + " " + key}
                            required
                            maxLength={
                              key === "description"
                                ? 300
                                : key === "sku"
                                  ? 60
                                  : 22
                            }
                            inputMode={
                              ["quantity", "unit_price", "tax_rate"].includes(
                                key,
                              )
                                ? "decimal"
                                : "text"
                            }
                            value={item[key]}
                            onChange={(e) =>
                              setForm((f) => ({
                                ...f,
                                items: f.items.map((row, i) =>
                                  i === index
                                    ? { ...row, [key]: e.target.value }
                                    : row,
                                ),
                              }))
                            }
                          />
                        </td>
                      ))}
                      <td>
                        <button
                          type="button"
                          aria-label={"Remove PO item " + (index + 1)}
                          disabled={
                            form.billing_mode === "ITEMIZED" &&
                            form.items.length === 1
                          }
                          onClick={() =>
                            setForm((f) => ({
                              ...f,
                              items: f.items.filter((_, i) => i !== index),
                            }))
                          }
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <button
              type="button"
              onClick={() =>
                setForm((f) => ({ ...f, items: [...f.items, blankItem()] }))
              }
            >
              Add PO item
            </button>
            {totals && (
              <>
                <dl className="financial-summary">
                  <div>
                    <dt>Calculated subtotal</dt>
                    <dd>{money(totals.subtotal, form.currency)}</dd>
                  </div>
                  <div>
                    <dt>Calculated tax</dt>
                    <dd>{money(totals.tax, form.currency)}</dd>
                  </div>
                  <div>
                    <dt>Calculated gross</dt>
                    <dd>{money(totals.gross, form.currency)}</dd>
                  </div>
                  <div>
                    <dt>Authorized gross</dt>
                    <dd>{money(form.authorized_gross, form.currency)}</dd>
                  </div>
                </dl>
                <button
                  type="button"
                  onClick={() => update("authorized_gross", totals.gross)}
                >
                  Use calculated gross
                </button>
              </>
            )}
            <p className="footnote">
              Tax rates use fractional decimals (0.10 = 10%). Calculations round
              each line net and tax using currency-specific half-up rules. The
              every value is checked again before saving.
            </p>
            <div className="toolbar">
              <button
                className="primary"
                type="submit"
                disabled={busy || (form.billing_mode === "ITEMIZED" && !totals)}
              >
                Save purchase order
              </button>
            </div>
          </fieldset>
        </form>
      </section>
    </Dialog>
  );
}
