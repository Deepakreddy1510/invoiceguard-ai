import { EmailIntakeFeature } from "./features";
import WorkspaceSettings from "./pages/WorkspaceSettings";
import { TechnicalScope } from "./TechnicalDetails";
import {
  BrowserRouter,
  Navigate,
  NavLink,
  Routes,
  Route,
  useNavigate,
  useParams,
  useLocation,
} from "react-router-dom";
import { useCallback, useEffect, useState } from "react";
import InvoiceWorkflow from "./InvoiceWorkflow";
import EmailIntake from "./pages/EmailIntake";
import Vendors from "./pages/Vendors";
import {
  SampleInitialization,
  WorkspaceProvider,
  WorkspaceSelector,
  useWorkspace,
  workspaceLabel,
} from "./workspaces";
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
function Shell({ enableEmailIntake }: { enableEmailIntake: boolean }) {
  const { active } = useWorkspace();
  const { data } = useResource<{ workspace_name: string; role: string }>("/me");
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [compact, setCompact] = useState(
    () => window.matchMedia?.("(max-width:768px)").matches ?? false,
  );
  useEffect(() => {
    const query = window.matchMedia?.("(max-width:768px)");
    if (!query) return;
    const update = () => setCompact(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  const nav = [
    { to: "/", label: "Overview", icon: "grid" },
    { to: "/process", label: "Invoice processing", icon: "upload" },
    { to: "/reviews", label: "Exception review", icon: "review" },
    { to: "/email-intake", label: "Email Intake", icon: "audit" },
    { to: "/vendors", label: "Vendors", icon: "orders" },
    { to: "/purchase-orders", label: "Purchase orders", icon: "orders" },
    { to: "/settings", label: "Settings", icon: "grid" },
  ] as const;
  const visibleNav = nav.filter(
    (item) => enableEmailIntake || item.to !== "/email-intake",
  );
  return (
    <div className={"app-shell " + (collapsed ? "sidebar-collapsed" : "")}>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <aside
        onKeyDown={(e) => {
          if (e.key === "Escape" && open) {
            setOpen(false);
            document.querySelector<HTMLButtonElement>(".nav-toggle")?.focus();
          }
        }}
        className={"sidebar " + (open ? "is-open" : "")}
      >
        <div className="sidebar-brandline">
          <NavLink to="/" className="brand" onClick={() => setOpen(false)}>
            <span className="logo-mark">IG</span>
            <span>
              InvoiceGuard
              <span className="brand-sub">AI · ACCOUNTS PAYABLE</span>
            </span>
          </NavLink>
          <button
            className="icon-button sidebar-collapse"
            aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
            aria-expanded={!collapsed}
            onClick={() => setCollapsed(!collapsed)}
          >
            <Icon name="menu" />
          </button>
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
        <div className="sidebar-scroll">
          {(!collapsed || compact) && <WorkspaceSelector />}
          <nav
            id="workspace-navigation"
            aria-label="Main navigation"
            tabIndex={0}
          >
            {visibleNav.map(({ to, label, icon }) => (
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
                <span className="nav-label">{label}</span>
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="sidebar-note">
          <span className="sidebar-note-mark">
            <Icon name="check" />
          </span>
          <strong>Smarter invoice processing.</strong>
          <p>From incoming invoices to clear, reliable decisions.</p>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <strong>
              {active
                ? workspaceLabel(active)
                : (data?.workspace_name ?? "InvoiceGuard")}
            </strong>
            {active?.kind === "DEMO" && (
              <span className="demo-disclosure">
                Sample workspace · Fictional company data
              </span>
            )}
          </div>
          {collapsed && !compact && (
            <div className="header-workspace">
              <WorkspaceSelector />
            </div>
          )}
          <AccountControl />
        </header>
        <main id="main-content" className="content" tabIndex={-1}>
          <SampleInitialization />
          <TechnicalScope>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/process" element={<WorkflowRoute />} />
              <Route path="/runs/:id" element={<WorkflowRoute />} />
              <Route path="/reviews" element={<Reviews />} />
              <Route path="/reviews/:id" element={<Reviews />} />
              <Route path="/purchase-orders" element={<PurchaseOrders />} />
              <Route
                path="/email-intake"
                element={
                  enableEmailIntake ? (
                    <EmailIntake />
                  ) : (
                    <Navigate to="/" replace />
                  )
                }
              />
              <Route path="/vendors" element={<Vendors />} />
              <Route path="/audit" element={<Audit />} />
              <Route path="/settings" element={<WorkspaceSettings />} />
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
          </TechnicalScope>
          <footer>
            <span>InvoiceGuard AI · Accounts Payable</span>
            <span>Support your team’s next decision.</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
export default function App({
  enableEmailIntake = false,
}: {
  enableEmailIntake?: boolean;
}) {
  return (
    <EmailIntakeFeature.Provider value={enableEmailIntake}>
      <BrowserRouter>
        <WorkspaceProvider>
          <Shell enableEmailIntake={enableEmailIntake} />
        </WorkspaceProvider>
      </BrowserRouter>
    </EmailIntakeFeature.Provider>
  );
}
