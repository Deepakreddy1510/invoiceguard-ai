import type { ReactNode } from "react";
import { useWorkspace } from "./workspaces";
export function TechnicalDetails({
  children,
  label = "Technical details",
}: {
  children: ReactNode;
  label?: string;
}) {
  const { active } = useWorkspace();
  if (active?.role !== "ADMIN") return null;
  return (
    <details className="technical-details">
      <summary>{label} · Administrator</summary>
      {children}
    </details>
  );
}
