import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { request, setActiveWorkspace } from "./client";
import { Notice, Skeleton } from "./ui";
export type Workspace = {
  id: string;
  name: string;
  kind: "DEMO" | "MY" | "CUSTOM";
  role: string;
  created_at: string;
  archived_at?: string | null;
  version: number;
};
export function workspaceLabel(workspace: Pick<Workspace, "name" | "kind">) {
  const name = workspace.name.replace(/ · Sample company$/, "");
  return workspace.kind === "DEMO" && /synthetic|demonstration/i.test(name)
    ? "Demo Workspace"
    : name;
}
export function normalWorkspaces(workspaces: Workspace[]) {
  const hasAsterfield = workspaces.some((w) => w.name.startsWith("Asterfield"));
  return workspaces.filter(
    (w) =>
      !hasAsterfield ||
      !["00000000-0000-0000-0000-000000000001"].includes(w.id),
  );
}
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
        result.workspaces = normalWorkspaces(result.workspaces);
        if (
          !result.workspaces.some((w) => w.id === result.default_workspace_id)
        )
          result.default_workspace_id = result.workspaces[0].id;
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
        try {
          sessionStorage.setItem(
            "invoiceguard.workspace." + result.subject,
            id,
          );
        } catch {
          /* Browser storage is optional. */
        }
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
  async function sample() {
    setBusy(true);
    setError("");
    try {
      const result = await request<Catalog & { workspace_id: string }>(
        "/workspaces/sample",
        { method: "POST" },
      );
      try {
        sessionStorage.setItem(
          "invoiceguard.workspace." + result.subject,
          result.workspace_id,
        );
      } catch {
        /* Storage is optional. */
      }
      reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
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
            {workspaceLabel(workspace)}
            {workspace.name.startsWith("Asterfield") ? " · Sample company" : ""}
            {workspace.kind === "DEMO" &&
            !workspace.name.startsWith("Asterfield") &&
            workspaces.slice(0, index).some((w) => w.kind === "DEMO")
              ? " · previous"
              : ""}
          </option>
        ))}
      </select>
      {!workspaces.some((w) => w.name.startsWith("Asterfield")) && (
        <div className="sample-offer">
          <p>
            Explore with your own Asterfield sample. Includes fictional
            suppliers, POs and 21 invoices processed by the worker. Gmail starts
            disconnected.
          </p>
          <button disabled={busy} onClick={() => void sample()}>
            {busy ? "Creating…" : "Create sample company"}
          </button>
        </div>
      )}
      <details className="workspace-actions">
        <summary>Workspace settings</summary>
        <div
          onClick={(e) => {
            if ((e.target as HTMLElement).closest("a"))
              e.currentTarget.closest("details")?.removeAttribute("open");
          }}
        >
          <Link to="/settings">All workspaces</Link>
          {active?.role === "ADMIN" && (
            <>
              <Link to={"/settings?workspace=" + active.id + "&action=rename"}>
                Rename this workspace
              </Link>
              <Link to={"/settings?workspace=" + active.id + "&action=archive"}>
                Archive this workspace
              </Link>
              <Link to="/settings">Restore an archived workspace</Link>
            </>
          )}
        </div>
      </details>
      {active?.role === "ADMIN" && (
        <details>
          <summary>More demo options</summary>
          <button
            type="button"
            className="text-button"
            onClick={() => setConfirm((v) => !v)}
          >
            Create fresh demo
          </button>
        </details>
      )}
      {confirm && (
        <div className="fresh-demo-confirm">
          <p>
            Create a new isolated demo with 18 vendors and 36 POs? Existing
            workspaces, decisions and commitments stay intact. Sample invoices
            will be queued for processing.
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

type Initialization = {
  status: string;
  completed: number;
  total: number;
  error: string | null;
  current_run_id: string | null;
  run_ids?: string[];
};
export function SampleInitialization() {
  const location = useLocation();
  const { active } = useWorkspace();
  const [data, setData] = useState<{
    eligible: boolean;
    initialization: Initialization | null;
  } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (active?.kind !== "DEMO") return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await request<{
          eligible: boolean;
          initialization: Initialization | null;
        }>("/workspaces/sample-initialization", { signal: controller.signal });
        if (controller.signal.aborted) return;
        setData(next);
        setError("");
        if (
          next.initialization &&
          ["QUEUED", "PROCESSING"].includes(next.initialization.status)
        )
          timer = setTimeout(() => void poll(), 1500);
      } catch (cause) {
        if (!controller.signal.aborted) setError((cause as Error).message);
      }
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [active?.id, active?.kind, revision]);
  async function initialize(resume: boolean) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await request(
        resume
          ? "/workspaces/sample-initialization/resume"
          : "/workspaces/sample",
        { method: "POST" },
      );
      setRevision((value) => value + 1);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (active?.kind !== "DEMO" || (!data?.eligible && !error)) return null;
  const installation = data?.initialization;
  if (
    installation?.status === "COMPLETE" &&
    location.pathname.startsWith("/reviews")
  )
    return null;
  return (
    <section
      className="sample-initialization"
      aria-label="Sample invoice initialization"
    >
      <strong>
        {installation?.status === "COMPLETE"
          ? "Sample invoices ready"
          : "Sample invoice initialization"}
      </strong>
      {!installation && (
        <>
          <p>
            Initialize the 21 sample invoices in their original order. Existing
            invoice history will never be overwritten.
          </p>
          <button
            disabled={busy || active?.role !== "ADMIN"}
            onClick={() => void initialize(false)}
          >
            Initialize sample invoices
          </button>
        </>
      )}
      {installation && (
        <>
          <p role="status">
            {installation.completed} of {installation.total} sample invoices
            processed.
            {installation.status === "COMPLETE"
              ? " Real decisions and source evidence are ready."
              : installation.status === "FAILED"
                ? " Initialization stopped; this demo is not complete."
                : installation.status === "QUEUED"
                  ? " Waiting for the background worker; this demo is not complete."
                  : " The worker is processing the sample; this demo is not complete. Editing is paused until initialization finishes."}
          </p>
          <progress
            aria-label="Sample invoices processed"
            value={installation.completed}
            max={installation.total}
          />
          {installation.status === "COMPLETE" && installation.run_ids?.[0] && (
            <Link to={"/runs/" + installation.run_ids[0]}>
              View recorded invoice stages
            </Link>
          )}
          {installation.current_run_id && (
            <Link to={"/runs/" + installation.current_run_id}>
              View current invoice stages
            </Link>
          )}
          {installation.error && <p role="alert">{installation.error}</p>}
          {installation.status === "FAILED" && (
            <button
              disabled={busy || active?.role !== "ADMIN"}
              onClick={() => void initialize(true)}
            >
              Resume sample initialization
            </button>
          )}
        </>
      )}
      {error && (
        <>
          <p role="alert">{error}</p>
          <button onClick={() => setRevision((value) => value + 1)}>
            Retry status
          </button>
        </>
      )}
    </section>
  );
}
