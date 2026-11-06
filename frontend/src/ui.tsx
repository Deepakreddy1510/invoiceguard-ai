import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import { request } from "./client";
import { businessLabels } from "./business";
import { Icon } from "./icons";
export function useResource<T>(
  path: string | null,
  interval = 0,
  stopWhen?: (value: T) => boolean,
) {
  const [state, setState] = useState<{
    path: string | null;
    data: T | null;
    error: string;
  }>({ path: null, data: null, error: "" });
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    let timer: number | undefined;
    const load = async () => {
      let stop = false;
      try {
        const value = await request<T>(path, { signal: controller.signal });
        if (!controller.signal.aborted) {
          setState({ path, data: value, error: "" });
          stop = !!stopWhen?.(value);
        }
      } catch (e) {
        if (!controller.signal.aborted)
          setState((previous) => ({
            path,
            data: previous.path === path ? previous.data : null,
            error: (e as Error).message,
          }));
      }
      if (!controller.signal.aborted && interval && !stop)
        timer = window.setTimeout(load, interval);
    };
    void load();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [path, interval, refresh, stopWhen]);
  const current = state.path === path;
  return {
    data: current ? state.data : null,
    error: current ? state.error : "",
    loading: !!path && (!current || !state.data) && !(current && state.error),
    reload: () => setRefresh((v) => v + 1),
  };
}
export function humanize(value: string) {
  return (
    businessLabels[value] ??
    value
      .toLowerCase()
      .replaceAll("_", " ")
      .replace(/(^|\s)\S/g, (c) => c.toUpperCase())
  );
}
export function Notice({
  error,
  onRetry,
}: {
  error: string;
  onRetry?: () => void;
}) {
  return error ? (
    <div className="error-banner" role="alert">
      <Icon name="review" />
      <div>
        <strong>We couldn’t complete that request.</strong>
        <p>{error}</p>
      </div>
      {onRetry && (
        <button onClick={onRetry}>
          <Icon name="refresh" />
          Retry
        </button>
      )}
    </div>
  ) : null;
}
export function Status({ value }: { value: string }) {
  return (
    <span className={"status status-" + value.toLowerCase()}>
      <span className="status-dot" />
      {humanize(value)}
    </span>
  );
}
export function PageTitle({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-title">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}
export function Skeleton({
  label = "Loading records",
  rows = 3,
}: {
  label?: string;
  rows?: number;
}) {
  return (
    <div className="skeleton-list" role="status" aria-label={label}>
      <span className="sr-only">{label}…</span>
      {Array.from({ length: rows }, (_, i) => (
        <div className="skeleton" key={i} />
      ))}
    </div>
  );
}
export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">
        <Icon name="file" />
      </span>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}
export function FilterChips({
  value,
  onChange,
  options,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string; count?: number }[];
  label: string;
}) {
  return (
    <div className="filter-chips" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
          {option.count != null && <span>{option.count}</span>}
        </button>
      ))}
    </div>
  );
}
export function CopyButton({
  text,
  label = "Copy",
}: {
  text: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(false);
  return (
    <span className="copy-control">
      <button
        type="button"
        className="quiet-button"
        aria-label={label}
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(text);
            setCopied(true);
            setError(false);
          } catch {
            setError(true);
          }
        }}
      >
        <Icon name={copied ? "check" : "copy"} />
        {copied ? "Copied" : label}
      </button>
      <span role="status" className={error ? "copy-error" : "sr-only"}>
        {error
          ? "Copy unavailable. Select the text to copy it manually."
          : copied
            ? "Copied to clipboard."
            : ""}
      </span>
    </span>
  );
}
const LazyDocumentViewer = lazy(() => import("./DocumentViewer"));
export function PdfPreview(props: {
  documentId?: string;
  file?: File | null;
  sourcePath?: string;
}) {
  return (
    <Suspense fallback={<p role="status">Loading document viewer…</p>}>
      <LazyDocumentViewer {...props} />
    </Suspense>
  );
}
