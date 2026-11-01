import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import App from "./App";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("loads API records without inventing processing results", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [
        {
          id: "1",
          number: "PO-TEST",
          currency: "USD",
          authorized_gross: "2200.000000",
          status: "OPEN",
          billing_mode: "ITEMIZED",
          valid_until: "2026-12-31",
          vendor: { legal_name: "Test vendor", status: "APPROVED" },
          items: [],
        },
      ],
    }),
  );
  window.history.replaceState({}, "", "/purchase-orders");
  render(<App />);
  expect(await screen.findByText("PO-TEST")).toBeInTheDocument();
  expect(
    screen.getByText(/Authorization is not a payment/),
  ).toBeInTheDocument();
});
it("shows backend failure rather than sample records", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));
  window.history.replaceState({}, "", "/purchase-orders");
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Procurement API is unavailable",
  );
  expect(screen.queryByText("PO-2026-001")).not.toBeInTheDocument();
});
