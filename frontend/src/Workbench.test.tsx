import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useState } from "react";
import { TablePagination, WorkbenchTabs } from "./Workbench";
import DocumentViewer from "./DocumentViewer";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("tabs expose one active panel and move keyboard focus with arrows, Home and End", () => {
  function Example() {
    const [value, setValue] = useState("overview");
    return (
      <WorkbenchTabs
        value={value}
        onChange={setValue}
        tabs={[
          { value: "overview", label: "Overview" },
          { value: "checks", label: "Financial checks" },
          { value: "activity", label: "Activity" },
        ]}
      >
        {value}
      </WorkbenchTabs>
    );
  }
  render(<Example />);
  const overview = screen.getByRole("tab", { name: "Overview" });
  overview.focus();
  fireEvent.keyDown(overview, { key: "ArrowRight" });
  expect(screen.getByRole("tab", { name: "Financial checks" })).toHaveFocus();
  expect(screen.getByRole("tabpanel")).toHaveTextContent("checks");
  fireEvent.keyDown(document.activeElement!, { key: "End" });
  expect(screen.getByRole("tab", { name: "Activity" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  fireEvent.keyDown(document.activeElement!, { key: "Home" });
  expect(overview).toHaveFocus();
});
it("pagination keeps partial last pages bounded and announces actual record positions", () => {
  const change = vi.fn();
  const { rerender } = render(
    <TablePagination page={0} total={25} onChange={change} />,
  );
  expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Next page" }));
  expect(change).toHaveBeenCalledWith(1);
  rerender(<TablePagination page={1} total={25} onChange={change} />);
  expect(screen.getByRole("status")).toHaveTextContent("21–25 of 25");
  expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
});
it("does not render a private PDF when the authorized endpoint denies access and supports retry", async () => {
  const fetcher = vi.fn(async () => ({ ok: false, status: 403 }));
  vi.stubGlobal("fetch", fetcher);
  render(<DocumentViewer documentId="private-record" />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "You do not have access",
  );
  expect(fetcher).toHaveBeenCalledWith(
    "/api/v1/documents/private-record/content",
    expect.objectContaining({ signal: expect.any(AbortSignal) }),
  );
  expect(
    screen.queryByRole("link", { name: /Open source/ }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry PDF" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "You do not have access",
  );
});
