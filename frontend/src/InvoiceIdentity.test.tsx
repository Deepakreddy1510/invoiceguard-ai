import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { InvoiceIdentity } from "./InvoiceIdentity";
import { Status } from "./ui";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it.each([
  ["VALIDATED", "Validated"],
  ["NEEDS_REVIEW", "Needs review"],
  ["BLOCKED", "Blocked"],
  ["RUNNING", "Processing"],
  ["QUEUED", "Waiting to process"],
  ["FAILED", "Processing failed"],
])("keeps %s status separate from neutral invoice identity", (value, label) => {
  const { container } = render(
    <>
      <InvoiceIdentity number="INV-123" supplier="Cedarline" />
      <Status value={value} />
    </>,
  );
  expect(screen.getByText(label)).toHaveClass("status");
  const icon = container.querySelector(`[data-status-icon="${value}"] svg`);
  expect(icon).toBeInTheDocument();
  expect(icon).toHaveAttribute("aria-hidden", "true");
  expect(
    container.querySelector(".invoice-document-mark"),
  ).not.toContainElement(icon as HTMLElement);
});
it("never describes technical completion as financial validation", () => {
  const { container } = render(<Status value="SUCCEEDED" />);
  expect(screen.getByText("Completed")).toHaveClass("status-succeeded");
  expect(screen.queryByText("Validated")).not.toBeInTheDocument();
  expect(container.querySelector('[data-status-icon="VALIDATED"]')).toBeNull();
});
it("preserves complete long identifiers, supplier names, copy value and keyboard focus", async () => {
  const number = "INV-MAIL-EMAIL-ONLY-002",
    supplier =
      "Rivermark Catering and International Hospitality Procurement Services";
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
  render(<InvoiceIdentity number={number} supplier={supplier} copy />);
  expect(screen.getByText(number)).toHaveAttribute("title", number);
  expect(screen.getByText(supplier)).toHaveAttribute("title", supplier);
  const copy = screen.getByRole("button", { name: "Copy invoice number" });
  copy.focus();
  expect(copy).toHaveFocus();
  fireEvent.click(copy);
  expect(writeText).toHaveBeenCalledWith(number);
  expect(await screen.findByText("Copied to clipboard.")).toBeInTheDocument();
});
it("shows honest unknown fields without generating a short invoice ID", () => {
  render(
    <InvoiceIdentity number={null} supplier={null} compact={false} copy />,
  );
  expect(screen.getByText("Supplier not identified")).toBeInTheDocument();
  expect(screen.getByText("Invoice details pending")).toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

it("uses distinct financial, processing and technical-error symbols rather than a universal warning icon", () => {
  const values = ["VALIDATED", "NEEDS_REVIEW", "BLOCKED", "RUNNING", "FAILED"];
  const { container } = render(
    <>
      {values.map((value) => (
        <Status key={value} value={value} />
      ))}
      <InvoiceIdentity number="INV-IDENTITY" />
    </>,
  );
  const paths = Array.from(
    container.querySelectorAll(".status-symbol path"),
    (el) => el.getAttribute("d"),
  );
  expect(new Set(paths).size).toBe(values.length);
  expect(paths).not.toContain(
    container.querySelector(".invoice-document-mark path")?.getAttribute("d"),
  );
});
