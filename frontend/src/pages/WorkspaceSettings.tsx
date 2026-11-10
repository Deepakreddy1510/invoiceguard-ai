import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { request } from "../client";
import { useWorkspace, workspaceLabel, type Workspace } from "../workspaces";
import { Notice, PageTitle, Status, useResource, Skeleton } from "../ui";
import { Dialog, Help } from "../Experience";
export default function WorkspaceSettings() {
  const { active, reload } = useWorkspace();
  const [params, setParams] = useSearchParams();
  const catalog = useResource<{ workspaces: Workspace[] }>(
    "/workspaces?include_archived=true",
  );
  const [chosen, setChosen] = useState<Workspace | null>(null);
  const target =
    chosen ??
    (["rename", "archive"].includes(params.get("action") ?? "")
      ? (catalog.data?.workspaces.find(
          (w) => w.id === params.get("workspace") && w.role === "ADMIN",
        ) ?? null)
      : null);
  function setTarget(w: Workspace | null) {
    setChosen(w);
    if (!w) {
      setParams({});
      setError("");
    }
  }
  const [localAction, setAction] = useState(params.get("action") ?? "rename");
  const action = chosen ? localAction : (params.get("action") ?? localAction);
  const [name, setName] = useState(active?.name ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  function open(w: Workspace, a: string) {
    setParams({});
    setTarget(w);
    setAction(a);
    setName(w.name);
    setError("");
  }
  async function save() {
    if (!target) return;
    setBusy(true);
    setError("");
    try {
      await request(
        "/workspaces/" + target.id + (action === "rename" ? "" : "/" + action),
        {
          method: action === "rename" ? "PATCH" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            version: target.version,
            name: action === "rename" ? name : undefined,
            confirm: action !== "rename",
          }),
        },
      );
      setMessage(
        action === "rename"
          ? "Workspace name updated."
          : action === "archive"
            ? "Workspace archived. Its records are retained."
            : "Workspace restored. Queued work can resume.",
      );
      setTarget(null);
      catalog.reload();
      reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const cards = (items: Workspace[]) => (
    <div className="workspace-cards">
      {items.map((w) => (
        <article className="panel workspace-card" key={w.id}>
          <div className="workspace-avatar">
            {workspaceLabel(w).slice(0, 2).toUpperCase()}
          </div>
          <div>
            <h2>{workspaceLabel(w)}</h2>
            <p>
              {w.kind === "DEMO"
                ? "Sample workspace · Fictional company data"
                : w.kind === "MY"
                  ? "Your personal company workspace"
                  : "Company workspace"}
            </p>
            <span className="tag">
              {w.archived_at ? "Archived" : "Active"}
              {w.id === active?.id ? " · Currently selected" : ""}
            </span>
          </div>
          {w.role === "ADMIN" ? (
            <div className="toolbar">
              <button onClick={() => open(w, "rename")}>Rename</button>
              <button
                onClick={() => open(w, w.archived_at ? "restore" : "archive")}
              >
                {w.archived_at ? "Restore" : "Archive"}
              </button>
            </div>
          ) : (
            <Status value={w.role} />
          )}
        </article>
      ))}
    </div>
  );
  return (
    <>
      <PageTitle
        eyebrow="SETTINGS"
        title="Your workspaces"
        description="Keep each company's invoices, suppliers and purchase orders together. Manage access to active and archived workspaces."
      />
      {message && (
        <p className="submission-message" role="status">
          {message}
        </p>
      )}
      <Notice error={catalog.error} onRetry={catalog.reload} />
      <Help title="What happens when I archive a workspace?">
        <p>
          Its financial history stays available. New uploads, changes and
          automatic email checks pause. Invoices already processing must finish
          first. Restore the workspace to resume queued work. Keep at least one
          workspace active.
        </p>
        <p>
          Workspace deletion is not offered because financial containers and
          their history are retained.
        </p>
      </Help>
      {catalog.loading ? (
        <Skeleton label="Loading workspace settings" />
      ) : (
        <div className="workspace-groups">
          <section aria-label="Active workspaces">
            <h2>Active workspaces</h2>
            {cards(
              (catalog.data?.workspaces ?? []).filter((w) => !w.archived_at),
            )}
          </section>
          <section aria-label="Archived workspaces">
            <h2>Archived workspaces</h2>
            {catalog.data?.workspaces.some((w) => w.archived_at) ? (
              cards(catalog.data.workspaces.filter((w) => !!w.archived_at))
            ) : (
              <p className="muted-text">No archived workspaces.</p>
            )}
          </section>
        </div>
      )}
      {active?.role === "ADMIN" && (
        <section className="panel settings-history">
          <h2>Records & activity</h2>
          <p>
            Find invoice decisions, reviewer changes and procurement activity.
            Complete records remain available in administrator details.
          </p>
          <Link className="button" to="/audit">
            Activity history
          </Link>
        </section>
      )}
      {active?.role === "ADMIN" && (
        <details
          className="panel settings-secondary"
          id="email-settings"
          open={window.location.hash === "#email-settings"}
        >
          <summary>Email intake configuration</summary>
          <EmailSettings />
        </details>
      )}
      {target && (
        <Dialog
          title={
            action === "rename"
              ? "Rename workspace"
              : action === "archive"
                ? "Archive workspace?"
                : "Restore workspace?"
          }
          onClose={() => {
            if (!busy) setTarget(null);
          }}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void save();
            }}
          >
            <Notice error={error} />
            {action === "rename" ? (
              <label className="comment-label">
                Workspace name
                <input
                  autoFocus
                  value={name}
                  maxLength={160}
                  required
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
            ) : (
              <p>
                {action === "archive"
                  ? "Pause new invoices, procurement changes and email checks for"
                  : "Resume invoice processing and email checks for"}{" "}
                <strong>{workspaceLabel(target)}</strong>? All existing
                documents, decisions and amounts reserved against orders are
                retained.
              </p>
            )}
            <div className="toolbar">
              <button
                type="button"
                disabled={busy}
                onClick={() => setTarget(null)}
              >
                Keep current settings
              </button>
              <button
                className={action === "archive" ? "danger" : "primary"}
                disabled={busy || !name.trim()}
              >
                {busy
                  ? "Saving…"
                  : action === "rename"
                    ? "Save name"
                    : action === "archive"
                      ? "Archive workspace"
                      : "Restore workspace"}
              </button>
            </div>
          </form>
        </Dialog>
      )}
    </>
  );
}

function EmailSettings() {
  const email = useResource<{
    available: boolean;
    configuration_message: string;
    email_classifier: string;
    connections: { id: string; email: string; status: string }[];
  }>("/email", 5000);
  return (
    <section className="panel email-settings" aria-label="Email configuration">
      <div className="panel-heading">
        <div>
          <h2>Email intake settings</h2>
          <p>
            Read-only connection and privacy configuration for this workspace.
          </p>
        </div>
        <Link className="button" to="/email-intake">
          Open invoice inbox
        </Link>
      </div>
      <Notice error={email.error} />
      {email.loading ? (
        <Skeleton label="Loading email settings" />
      ) : (
        <div className="settings-content">
          <p>
            {email.data?.available
              ? "Gmail authorization is available. Connect or manage the account from Email Intake."
              : "Gmail authorization is unavailable. An administrator must configure Google OAuth and server-side token encryption."}
          </p>
          <p>
            Only new incoming mail is checked. Access is read-only.
            Disconnecting retains invoices and financial history.
          </p>
          <p>
            {email.data?.email_classifier === "GEMINI"
              ? "Email AI is explicitly enabled by server configuration. Relevant email/document text may be sent to Gemini for classification."
              : "Standard email classification is configured. Email content is not sent to an AI service."}
          </p>
          <details>
            <summary>Administrator configuration details</summary>
            <p>{email.data?.configuration_message}</p>
            <p>
              Set provider credentials privately on the server. This interface
              never displays or collects secret keys.
            </p>
          </details>
        </div>
      )}
    </section>
  );
}
