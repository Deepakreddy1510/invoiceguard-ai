import type { RunDetail } from "./models";
import { fact } from "./models";
import type { PurchaseOrder } from "./api";
import { useResource, Notice, humanize, EmptyState, Skeleton } from "./ui";
import { money } from "./client";
export function POComparison({ run }: { run: RunDetail }) {
  const number = run.decision?.summary.po_number;
  const orders = useResource<PurchaseOrder[]>(
    typeof number === "string"
      ? "/purchase-orders?search=" + encodeURIComponent(number)
      : null,
  );
  if (typeof number !== "string")
    return (
      <EmptyState title="Purchase order comparison unavailable">
        A verified purchase order has not been identified. Confirm the invoice
        reference and supplier before comparing capacity.
      </EmptyState>
    );
  const matches = orders.data?.filter((p) => p.number === number) ?? [];
  const po = matches.length === 1 ? matches[0] : undefined;
  const summary = run.decision?.summary;
  const rows: [string, string | undefined, string | undefined][] = po
    ? [
        [
          "Supplier",
          fact(run, "vendor_name")?.value ?? undefined,
          po.vendor.legal_name,
        ],
        ["Currency", fact(run, "currency")?.value ?? undefined, po.currency],
        [
          "Invoice / authorised amount",
          typeof summary?.requested === "string"
            ? money(summary.requested, po.currency)
            : undefined,
          money(po.authorized_gross, po.currency),
        ],
      ]
    : [];
  return (
    <section className="po-comparison">
      <h4>Invoice vs purchase order</h4>
      <Notice error={orders.error} />
      {orders.loading && (
        <Skeleton label="Loading purchase order comparison" rows={2} />
      )}
      {po ? (
        <>
          <p>
            <a href={"/purchase-orders?po=" + encodeURIComponent(number)}>
              {number}
            </a>{" "}
            · Current order status: {humanize(po.status)}
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Detail</th>
                  <th>Invoice</th>
                  <th>Purchase order</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(([label, actual, expected]) => (
                  <tr key={label}>
                    <th>{label}</th>
                    <td>{actual ?? "Not found in document"}</td>
                    <td>{expected}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <dl className="financial-summary">
            {typeof summary?.available_before === "string" && (
              <div>
                <dt>Available at this decision</dt>
                <dd>{money(summary.available_before, po.currency)}</dd>
              </div>
            )}
            {typeof summary?.available_after === "string" && (
              <div>
                <dt>Available after this decision</dt>
                <dd>{money(summary.available_after, po.currency)}</dd>
              </div>
            )}
            {po.reserved_gross != null && (
              <div>
                <dt>Currently reserved across invoices</dt>
                <dd>{money(po.reserved_gross, po.currency)}</dd>
              </div>
            )}
            {po.available_gross != null && (
              <div>
                <dt>Current available capacity</dt>
                <dd>{money(po.available_gross, po.currency)}</dd>
              </div>
            )}
          </dl>
          <p className="footnote">
            Order details are current. Decision balances are the historical
            values recorded when this invoice was checked.
          </p>
          <details>
            <summary>Compare quantities, prices and tax</summary>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Invoice quantity / price / tax rate</th>
                    <th>Ordered quantity / price / tax rate</th>
                  </tr>
                </thead>
                <tbody>
                  {po.items.map((item) => {
                    const source = run.extraction?.fields.items?.find(
                      (i) => i.sku?.verified && i.sku.value === item.sku,
                    );
                    return (
                      <tr key={item.sku}>
                        <td>{item.description}</td>
                        <td>
                          {source
                            ? `${source.quantity?.value ?? "Missing"} / ${source.unit_price?.value ?? "Missing"} / ${source.tax_rate?.value ?? "Missing"}`
                            : "No verified item match"}
                        </td>
                        <td>
                          {item.quantity} / {item.unit_price} / {item.tax_rate}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="footnote">
              Invoice prices retain their stated tax basis. Recorded financial
              checks determine whether they comply with the order.
            </p>
          </details>
        </>
      ) : !orders.loading && !orders.error ? (
        <p>No unique purchase order record is available for comparison.</p>
      ) : null}
    </section>
  );
}
