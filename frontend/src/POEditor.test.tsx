import { expect, it } from "vitest";
import { calculatePO, type POItem } from "./POEditor";
const item = (price: string, rate = "0.10", quantity = "3"): POItem => ({
  sku: "TEST",
  description: "Synthetic",
  quantity,
  unit_price: price,
  tax_rate: rate,
});
it.each(["USD", "INR", "EUR", "GBP"])(
  "uses decimal half-up per line for %s",
  (currency) => {
    expect(
      calculatePO([item("0.335"), item("0.005", "0", "1")], currency),
    ).toEqual({ subtotal: "1.02", tax: "0.10", gross: "1.12" });
  },
);
it("uses yen integer rounding and dinar three-place rounding", () => {
  expect(calculatePO([item("0.5", "0.5", "1")], "JPY")).toEqual({
    subtotal: "1",
    tax: "1",
    gross: "2",
  });
  expect(calculatePO([item("0.0005", "0.5", "1")], "KWD")).toEqual({
    subtotal: "0.001",
    tax: "0.001",
    gross: "0.002",
  });
});
it("preserves precision beyond JavaScript safe integers", () => {
  expect(calculatePO([item("99999999999999.99", "0", "1")], "USD")?.gross).toBe(
    "99999999999999.99",
  );
});
it.each([item("1e3"), item("-1"), item("1", "1.1"), item("1", "0", "0")])(
  "does not fabricate totals for invalid input",
  (row) => {
    expect(calculatePO([row], "USD")).toBeNull();
  },
);
it("accepts persisted eight-place tax rates while retaining six-place price precision", () => {
  expect(
    calculatePO([item("20.000000", "0.10000000", "10.000000")], "USD"),
  ).toEqual({ subtotal: "200.00", tax: "20.00", gross: "220.00" });
});
