import { useId, type ReactNode } from "react";

/** Roving-focus tabs: Arrow keys, Home and End retain native button activation. */
export function WorkbenchTabs({
  value,
  onChange,
  tabs,
  label = "Invoice detail sections",
  children,
}: {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  tabs: { value: string; label: string }[];
  children: ReactNode;
}) {
  const id = useId();
  return (
    <>
      <div className="workbench-tabs" role="tablist" aria-label={label}>
        {tabs.map((tab, index) => (
          <button
            key={tab.value}
            type="button"
            role="tab"
            id={`${id}-${tab.value}`}
            aria-selected={value === tab.value}
            aria-controls={`${id}-panel`}
            tabIndex={value === tab.value ? 0 : -1}
            onClick={() => onChange(tab.value)}
            onKeyDown={(event) => {
              const next =
                event.key === "ArrowRight"
                  ? (index + 1) % tabs.length
                  : event.key === "ArrowLeft"
                    ? (index + tabs.length - 1) % tabs.length
                    : event.key === "Home"
                      ? 0
                      : event.key === "End"
                        ? tabs.length - 1
                        : null;
              if (next === null) return;
              event.preventDefault();
              onChange(tabs[next].value);
              document.getElementById(`${id}-${tabs[next].value}`)?.focus();
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div
        className="workbench-tab-body"
        id={`${id}-panel`}
        role="tabpanel"
        aria-labelledby={`${id}-${value}`}
        tabIndex={0}
      >
        {children}
      </div>
    </>
  );
}

export function TablePagination({
  page,
  total,
  size = 20,
  onChange,
}: {
  page: number;
  total: number;
  size?: number;
  onChange: (value: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / size));
  const current = Math.min(page, pages - 1);
  return (
    <nav className="pagination" aria-label="Table pages">
      <span role="status">
        {total
          ? `${current * size + 1}–${Math.min((current + 1) * size, total)} of ${total}`
          : "0 records"}
      </span>
      <button disabled={current === 0} onClick={() => onChange(current - 1)}>
        Previous page
      </button>
      <button
        disabled={current >= pages - 1}
        onClick={() => onChange(current + 1)}
      >
        Next page
      </button>
    </nav>
  );
}
