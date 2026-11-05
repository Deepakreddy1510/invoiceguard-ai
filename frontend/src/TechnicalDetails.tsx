import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { useLocation } from "react-router-dom";
import { useWorkspace } from "./workspaces";
const TechnicalHost = createContext<HTMLElement | null | undefined>(undefined);
export function TechnicalScope({ children }: { children: ReactNode }) {
  const { active } = useWorkspace();
  const [host, setHost] = useState<HTMLDivElement | null>(null);
  const disclosure = useRef<HTMLDetailsElement>(null);
  const location = useLocation();
  useEffect(() => {
    if (disclosure.current) disclosure.current.open = false;
  }, [location.pathname]);
  return (
    <TechnicalHost.Provider value={host}>
      {children}
      {active?.role === "ADMIN" && (
        <details ref={disclosure} className="technical-details technical-hub">
          <summary>
            Technical details <span>Administrator access</span>
          </summary>
          <p className="footnote">
            Complete recorded evidence and processing information. Financial
            decisions remain unchanged.
          </p>
          <div ref={setHost} />
        </details>
      )}
    </TechnicalHost.Provider>
  );
}
export function TechnicalDetails({
  children,
  label = "Processing information",
}: {
  children: ReactNode;
  label?: string;
}) {
  const { active } = useWorkspace();
  const host = useContext(TechnicalHost);
  if (active?.role !== "ADMIN") return null;
  if (host !== undefined)
    return host
      ? createPortal(
          <section className="technical-section">
            <h3>{label}</h3>
            {children}
          </section>,
          host,
        )
      : null;
  return (
    <details className="technical-details">
      <summary>{label}</summary>
      {children}
    </details>
  );
}
