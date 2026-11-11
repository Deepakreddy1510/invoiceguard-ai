import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { Link, useNavigate } from "react-router-dom";
import { request, setActiveWorkspace } from "./client";
import { Dialog } from "./Experience";
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
  const name =
    workspace.kind === "DEMO"
      ? workspace.name.replace(/ · Sample company$/, "")
      : workspace.name;
  return workspace.kind === "DEMO" && /synthetic|demonstration/i.test(name)
    ? "Demo Workspace"
    : name;
}
export function normalWorkspaces(workspaces: Workspace[]) {
  return workspaces;
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
  created: (catalog: Catalog, id: string) => void;
  openCreation: (type?: "EMPTY" | "SAMPLE") => void;
};
const Workspaces = createContext<Context>({
  active: null,
  workspaces: [],
  choose: () => {},
  reload: () => {},
  created: () => {},
  openCreation: () => {},
});
export const useWorkspace = () => useContext(Workspaces);
export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [creationType, setCreationType] = useState<"EMPTY" | "SAMPLE" | null>(
    null,
  );
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
        openCreation: (type = "EMPTY") => setCreationType(type),
        reload: () => setRetry((v) => v + 1),
        created: (result, id) => {
          setCatalog(result);
          setActiveWorkspace(id);
          setSelected(id);
          navigate("/", { replace: true });
        },
      }}
    >
      <div className="workspace-frame" key={active.id}>
        {children}
      </div>
      {creationType && (
        <WorkspaceCreation
          initialType={creationType}
          onClose={() => setCreationType(null)}
        />
      )}
    </Workspaces.Provider>
  );
}
export function WorkspaceSelector() {
  const { active, workspaces, choose, openCreation } = useWorkspace();
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
            {workspace.kind === "DEMO" ? " · Fictional sample" : ""}
            {workspace.kind === "DEMO" &&
            !workspace.name.startsWith("Asterfield") &&
            workspaces.slice(0, index).some((w) => w.kind === "DEMO")
              ? " · previous"
              : ""}
          </option>
        ))}
      </select>
      <button type="button" onClick={() => openCreation()}>
        Create Workspace
      </button>
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
    </div>
  );
}

function WorkspaceCreation({
  initialType,
  onClose,
}: {
  initialType: "EMPTY" | "SAMPLE";
  onClose: () => void;
}) {
  const { created } = useWorkspace();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [nonce, setNonce] = useState(crypto.randomUUID());
  const [name, setName] = useState("");
  const [workspaceType, setWorkspaceType] = useState<string>(initialType);
  async function create() {
    setBusy(true);
    setError("");
    try {
      const result = await request<Catalog & { workspace_id: string }>(
        "/workspaces",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            request_id: nonce,
            name: name.trim(),
            workspace_type: workspaceType,
          }),
        },
      );
      try {
        sessionStorage.setItem(
          "invoiceguard.workspace." + result.subject,
          result.workspace_id,
        );
      } catch {
        /* Storage is optional. */
      }
      onClose();
      setNonce(crypto.randomUUID());
      created(result, result.workspace_id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title="Create Workspace" onClose={() => !busy && onClose()}>
      <p>
        Name your workspace and choose whether to start empty or explore
        fictional sample invoices.
      </p>
      <Notice error={error} />
      <form
        className="workspace-create-form"
        aria-label="Create Workspace"
        onSubmit={(event) => {
          event.preventDefault();
          void create();
        }}
      >
        <label htmlFor="new-workspace-name">Workspace name</label>
        <input
          id="new-workspace-name"
          required
          maxLength={160}
          value={name}
          disabled={busy}
          onChange={(event) => setName(event.target.value)}
        />
        <label htmlFor="new-workspace-type">Workspace type</label>
        <select
          id="new-workspace-type"
          value={workspaceType}
          disabled={busy}
          onChange={(event) => setWorkspaceType(event.target.value)}
        >
          <option value="EMPTY">Empty workspace</option>
          <option value="SAMPLE">Sample workspace</option>
        </select>
        <p>
          {workspaceType === "EMPTY"
            ? "Private company workspace with no vendors, purchase orders, invoices or commitments. Add your own records when ready."
            : "Fictional suppliers and purchase orders, with 21 original sample PDFs queued for the worker. Includes Validated, Needs Review and Blocked examples."}
        </p>
        <p>
          Existing history is preserved. Duplicate names are allowed; each
          workspace has its own identity.
        </p>
        <button type="submit" disabled={busy || !name.trim()}>
          {busy ? "Creating…" : "Confirm creation"}
        </button>
        <button type="button" disabled={busy} onClick={onClose}>
          Cancel
        </button>
      </form>
    </Dialog>
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
  const { active, openCreation } = useWorkspace();
  const [data, setData] = useState<{
    eligible: boolean;
    initialization: Initialization | null;
  } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const acknowledgementKey = "invoiceguard.sample-ack." + active?.id;
  const [acknowledged, setAcknowledged] = useState(() => {
    try {
      return localStorage.getItem(acknowledgementKey) === "true";
    } catch {
      return false;
    }
  });
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
          : "/workspaces/sample-initialization/start",
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
  const complete =
    installation?.status === "COMPLETE" &&
    installation.completed === installation.total &&
    !installation.error;
  if (complete) {
    return (
      <section className="sample-complete" aria-label="Sample data">
        <span>Sample data · Fictional company</span>{" "}
        {!acknowledged && (
          <>
            <span role="status">
              Sample invoices ready — {installation.completed} of{" "}
              {installation.total} processed.
            </span>{" "}
            <button
              type="button"
              onClick={() => {
                setAcknowledged(true);
                try {
                  localStorage.setItem(acknowledgementKey, "true");
                } catch {
                  /* Optional storage. */
                }
              }}
            >
              Dismiss
            </button>{" "}
          </>
        )}
        {installation.run_ids?.[0] && (
          <Link to={"/runs/" + installation.run_ids[0]}>
            View recorded invoice stages
          </Link>
        )}
      </section>
    );
  }
  return (
    <section
      className="sample-initialization"
      aria-label="Sample invoice initialization"
    >
      <strong>
        {complete ? "Sample invoices ready" : "Sample invoice initialization"}
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
            {complete
              ? " Real decisions and source evidence are ready."
              : installation.status === "COMPLETE"
                ? " Completion records are inconsistent; inspect initialization before continuing."
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
          {complete && installation.run_ids?.[0] && (
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
          {active?.role === "ADMIN" &&
            /history|procurement.*changed|Gmail|mailbox/i.test(error) && (
              <div className="notice">
                <p>
                  Existing workspace history must stay in this workspace. Start
                  the fixed 21-invoice scenario in a separate, clean sample
                  instead.
                </p>
                <button onClick={() => openCreation("SAMPLE")}>
                  Create Fresh Sample Workspace
                </button>
              </div>
            )}
          <button onClick={() => setRevision((value) => value + 1)}>
            Retry status
          </button>
        </>
      )}
    </section>
  );
}
