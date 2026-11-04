import { apiFetch } from "./client";
export type PurchaseOrder = {
  id: string;
  version: number;
  has_history: boolean;
  number: string;
  currency: string;
  authorized_gross: string;
  reserved_gross?: string;
  available_gross?: string;
  settled_gross?: string;
  status: string;
  billing_mode: string;
  valid_until: string;
  issued_on: string;
  vendor: { legal_name: string; status: string };
  items: {
    sku: string;
    tax_rate: string;
    line_number: number;
    description: string;
    quantity: string;
    unit_price: string;
  }[];
};
export async function loadProcurement(
  signal: AbortSignal,
): Promise<PurchaseOrder[]> {
  const response = await apiFetch("/api/v1/purchase-orders", { signal });
  if (!response.ok)
    throw new Error(
      "Procurement API is unavailable. Check backend and database readiness.",
    );
  return response.json();
}
