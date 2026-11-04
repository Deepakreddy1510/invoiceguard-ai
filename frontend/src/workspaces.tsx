import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";
import { request, setActiveWorkspace } from "./client";
import { Notice, Skeleton } from "./ui";
export type Workspace = {
  id: string;
  name: string;
  kind: "DEMO" | "MY" | "CUSTOM";
  role: string;
  created_at: string;
};
type Catalog = {
  workspaces: Workspace[];
  default_workspace_id: string;
  subject: string;
};
type Context = {
  active: Workspace | null;
  workspaces: Workspace[];
  choose: (id: string) => void;
  reload: () => void;
};
const Workspaces = createContext<Context>({
  active: null,
  workspaces: [],
  choose: () => {},
  reload: () => {},
});
export const useWorkspace = () => useContext(Workspaces);
export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    if (!catalog) setActiveWorkspace(null);
    void request<Catalog>("/workspaces/bootstrap", {
      method: "POST",
      signal: controller.signal,
    })
      .then((result) => {
        if (controller.signal.aborted) return;
        if (!Array.isArray(result.workspaces) || !result.workspaces.length)
          throw new Error(
            "No authorized workspace is available. Ask the administrator for an invitation.",
          );
        let stored: string | null = null;
        try {
          stored = sessionStorage.getItem(
            "invoiceguard.workspace." + result.subject,
          );
        } catch {
          /* Storage is optional. */
        }
        const id = result.workspaces.some((w) => w.id === stored)
          ? stored!
          : result.default_workspace_id;
        if (selected && id !== selected) navigate("/", { replace: true });
        setActiveWorkspace(id);
        setSelected(id);
        setCatalog(result);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError((e as Error).message);
      });
    return () => controller.abort();
    // Catalog is intentionally retained during a controlled refresh, not a dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [retry]);
  function choose(id: string) {
    if (!catalog?.workspaces.some((w) => w.id === id)) return;
    setActiveWorkspace(id);
    setSelected(id);
    try {
      sessionStorage.setItem("invoiceguard.workspace." + catalog.subject, id);
    } catch {
      /* Keep switching usable without browser storage. */
    }
    navigate("/", { replace: true });
  }
  const active = catalog?.workspaces.find((w) => w.id === selected) ?? null;
  if (!active)
    return (
      <div className="startup">
        <h1>Opening your workspace</h1>
        <Notice error={error} onRetry={() => setRetry((v) => v + 1)} />
        {!error && <Skeleton label="Loading authorized workspaces" />}
      </div>
    );
  return (
    <Workspaces.Provider
      value={{
        active,
        workspaces: catalog!.workspaces,
        choose,
        reload: () => setRetry((v) => v + 1),
      }}
    >
      <div className="workspace-frame" key={active.id}>
        {children}
      </div>
    </Workspaces.Provider>
  );
}
export function WorkspaceSelector() {
  const { active, workspaces, choose, reload } = useWorkspace();
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [nonce, setNonce] = useState(crypto.randomUUID());
  async function fresh() {
    setBusy(true);
    setError("");
    try {
      const result = await request<Catalog & { workspace_id: string }>(
        "/workspaces/fresh-demo",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ request_id: nonce, confirm_create: true }),
        },
      );
      try {
        sessionStorage.setItem(
          "invoiceguard.workspace." + result.subject,
          result.workspace_id,
        );
      } catch {
        /* selection still defaults to the newest demo */
      }
      setConfirm(false);
      setNonce(crypto.randomUUID());
      reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="workspace-selector">
      <label htmlFor="workspace-picker">WORKSPACE</label>
      <select
        id="workspace-picker"
        aria-label="Workspace"
        value={active?.id ?? ""}
        onChange={(e) => choose(e.target.value)}
      >
        {workspaces.map((workspace, index) => (
          <option key={workspace.id} value={workspace.id}>
            {workspace.kind === "MY"
              ? "My Workspace"
              : workspace.kind === "DEMO"
                ? `Demo Workspace${workspaces.slice(0, index).some((w) => w.kind === "DEMO") ? " · previous" : ""}`
                : workspace.name}
          </option>
        ))}
      </select>
      {active?.role === "ADMIN" && (
        <button
          type="button"
          className="text-button"
          onClick={() => setConfirm((v) => !v)}
        >
          Create fresh demo
        </button>
      )}
      {confirm && (
        <div className="fresh-demo-confirm">
          <p>
            Create a new isolated demo with 18 vendors and 36 POs? Existing
            workspaces, decisions and commitments stay intact. Real example runs
            will be queued for the worker.
          </p>
          <button type="button" disabled={busy} onClick={fresh}>
            {busy ? "Creating…" : "Confirm new demo"}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => setConfirm(false)}
          >
            Keep current workspace
          </button>
        </div>
      )}
      <Notice error={error} />
    </div>
  );
}
