import {
  BrowserRouter,
  NavLink,
  Routes,
  Route,
  useNavigate,
  useParams,
  useLocation,
} from "react-router-dom";
import { useCallback, useState } from "react";
import InvoiceWorkflow from "./InvoiceWorkflow";
import Dashboard from "./pages/Dashboard";
import PurchaseOrders from "./pages/PurchaseOrders";
import Reviews from "./pages/Reviews";
import Audit from "./pages/Audit";
import { AccountControl } from "./auth";
import { EmptyState, useResource } from "./ui";
import { Icon } from "./icons";
function WorkflowRoute() {
  const { id } = useParams();
  const navigate = useNavigate();
  const select = useCallback(
    (run: string) => navigate("/runs/" + run),
    [navigate],
  );
  return <InvoiceWorkflow initialRunId={id} onSelectRun={select} />;
}
function Shell() {
  const { data } = useResource<{ workspace_name: string; role: string }>("/me");
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const nav = [
    { to: "/", label: "Overview", icon: "grid" },
    { to: "/process", label: "Invoice processing", icon: "upload" },
    { to: "/reviews", label: "Exception review", icon: "review" },
    { to: "/purchase-orders", label: "Purchase orders", icon: "orders" },
    { to: "/audit", label: "Audit history", icon: "audit" },
  ] as const;
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <aside className={"sidebar " + (open ? "is-open" : "")}>
        <div className="sidebar-brandline">
          <NavLink to="/" className="brand" onClick={() => setOpen(false)}>
            <span className="logo-mark">IG</span>
            <span>
              InvoiceGuard
              <span className="brand-sub">AI · ACCOUNTS PAYABLE</span>
            </span>
          </NavLink>
          <button
            className="icon-button nav-toggle"
            aria-label={open ? "Close navigation" : "Open navigation"}
            aria-expanded={open}
            aria-controls="workspace-navigation"
            onClick={() => setOpen((v) => !v)}
          >
            <Icon name={open ? "close" : "menu"} />
          </button>
        </div>
        <p className="nav-caption">WORKSPACE</p>
        <nav id="workspace-navigation" aria-label="Main navigation">
          {nav.map(({ to, label, icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                isActive ||
                (to === "/process" && location.pathname.startsWith("/runs/"))
                  ? "active"
                  : ""
              }
            >
              <Icon name={icon} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-note">
          <span className="sidebar-note-mark">
            <Icon name="check" />
          </span>
          <strong>Evidence before approval.</strong>
          <p>
            Deterministic controls.
            <br />
            Human judgment where it matters.
          </p>
          <span>Synthetic data · No payments</span>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <span className="topbar-label">YOUR WORKSPACE</span>
            <strong>{data?.workspace_name ?? "InvoiceGuard workspace"}</strong>
          </div>
          <AccountControl />
        </header>
        <main id="main-content" className="content" tabIndex={-1}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/process" element={<WorkflowRoute />} />
            <Route path="/runs/:id" element={<WorkflowRoute />} />
            <Route path="/reviews" element={<Reviews />} />
            <Route path="/reviews/:id" element={<Reviews />} />
            <Route path="/purchase-orders" element={<PurchaseOrders />} />
            <Route path="/audit" element={<Audit />} />
            <Route
              path="*"
              element={
                <EmptyState
                  title="This page couldn’t be found"
                  action={
                    <NavLink className="button" to="/">
                      Return to overview
                    </NavLink>
                  }
                >
                  Your invoice records are still available in the workspace.
                </EmptyState>
              }
            />
          </Routes>
          <footer>
            <span>InvoiceGuard AI</span>
            <p>Verification, with a clear record. No payments are executed.</p>
          </footer>
        </main>
      </div>
    </div>
  );
}
export default function App() {
  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  );
}
