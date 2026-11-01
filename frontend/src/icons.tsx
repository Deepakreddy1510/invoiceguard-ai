import type { CSSProperties } from "react";
type Name =
  | "grid"
  | "upload"
  | "review"
  | "orders"
  | "audit"
  | "arrow"
  | "check"
  | "close"
  | "file"
  | "search"
  | "copy"
  | "chevron"
  | "clock"
  | "menu"
  | "refresh";
const paths: Record<Name, string> = {
  grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  upload: "M12 16V3 M7 8l5-5 5 5 M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5",
  review: "M9 3h6l6 6v6l-6 6H9l-6-6V9z M12 7v6 M12 17h.01",
  orders: "M6 3h12v18H6z M9 7h6 M9 11h6 M9 15h4",
  audit: "M4 6h16 M4 12h16 M4 18h10 M2 6h.01 M2 12h.01 M2 18h.01",
  arrow: "M4 12h15 M13 6l6 6-6 6",
  check: "M5 12l4 4L19 6",
  close: "M6 6l12 12 M18 6L6 18",
  file: "M14 2H5v20h14V7z M14 2v5h5 M8 12h8 M8 16h6",
  search: "M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14 M15 15l6 6",
  copy: "M8 8h12v13H8z M16 8V3H3v13h5",
  chevron: "M9 5l7 7-7 7",
  clock: "M12 8v5l3 2 M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20",
  menu: "M3 6h18 M3 12h18 M3 18h18",
  refresh:
    "M20 7v5h-5 M4 17v-5h5 M5 8a8 8 0 0 1 13-3l2 3 M4 16l2 3a8 8 0 0 0 13-3",
};
export function Icon({
  name,
  className = "",
  style,
}: {
  name: Name;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <svg
      className={"icon " + className}
      style={style}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}
