import { createContext, useContext, useEffect, useState } from "react";
import { Auth0Provider, useAuth0 } from "@auth0/auth0-react";
import { clearSession, setAccessToken, setSessionSubject } from "./client";
import { Dialog } from "./Experience";
import "./auth.css";
type PublicConfig = {
  auth_mode: string;
  issuer: string;
  client_id: string;
  audience: string;
};
const Session = createContext<{
  enabled: boolean;
  email?: string;
  name?: string;
  verified?: boolean;
  logout?: () => void;
}>({ enabled: false });

export function AuthEntry({
  busy = false,
  error = "",
  onContinue,
}: {
  busy?: boolean;
  error?: string;
  onContinue: (signup: boolean) => void;
}) {
  const [signup, setSignup] = useState(false);
  const [reset, setReset] = useState(false);
  return (
    <main className="auth-page">
      <section className="auth-story" aria-label="InvoiceGuard introduction">
        <a className="brand" href="/">
          <span className="logo-mark">IG</span> InvoiceGuard
        </a>
        <div>
          <p className="eyebrow">CONFIDENCE IN EVERY INVOICE</p>
          <h1>
            Your next decision.
            <br />
            Backed by evidence.
          </h1>
          <p>
            Bring invoices, suppliers and purchase orders into one clear view.
            Give your finance team the confidence to move forward.
          </p>
          <ul>
            <li>Trace every invoice to its source</li>
            <li>Catch duplicates and budget exceptions</li>
            <li>Keep your company’s records private</li>
          </ul>
        </div>
        <p className="auth-footnote">
          InvoiceGuard AI · Accounts payable, under control.
        </p>
      </section>
      <section className="auth-entry" aria-labelledby="auth-title">
        <div className="auth-card">
          <p className="eyebrow">YOUR FINANCE WORKSPACE</p>
          <h2 id="auth-title">
            {signup ? "Create your account" : "Welcome back"}
          </h2>
          <p>
            {signup
              ? "A private workspace for your team’s next chapter."
              : "Sign in to pick up where your team left off."}
          </p>
          <div className="auth-tabs" aria-label="Account access">
            <button
              aria-pressed={!signup}
              onClick={() => {
                setSignup(false);
                setReset(false);
              }}
            >
              Sign in
            </button>
            <button
              aria-pressed={signup}
              onClick={() => {
                setSignup(true);
                setReset(false);
              }}
            >
              Create account
            </button>
          </div>
          {error && (
            <div className="error-banner" role="alert">
              {error}
            </div>
          )}
          <button
            className="primary auth-continue"
            disabled={busy}
            onClick={() => onContinue(signup)}
          >
            {busy
              ? "Opening secure sign-in…"
              : signup
                ? "Create account securely →"
                : "Sign in securely →"}
          </button>
          {!signup && (
            <button className="text-button" onClick={() => setReset(true)}>
              Forgot password?
            </button>
          )}
          {reset && (
            <p role="status">
              Choose “Don’t remember your password?” on the secure sign-in page
              to receive a reset email.{" "}
              <button onClick={() => onContinue(false)}>
                Open password recovery
              </button>
            </p>
          )}
          <p className="auth-security">
            You’ll continue to our identity provider to enter your credentials
            {signup ? " and verify your email" : ""}. InvoiceGuard never
            receives your password.
          </p>
          {signup && (
            <p>
              Your account starts with an empty, private My Workspace. You can
              also create an isolated Asterfield sample company to explore the
              workflow.
            </p>
          )}
        </div>
        <p className="auth-footnote">
          Source evidence. Clear decisions. A complete audit trail.
        </p>
      </section>
    </main>
  );
}

function SignedIn({ children }: { children: React.ReactNode }) {
  const auth = useAuth0();
  const [expired, setExpired] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [redirecting, setRedirecting] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const expire = () => {
      clearSession();
      setExpired(true);
    };
    window.addEventListener("invoiceguard:session-expired", expire);
    return () => {
      window.removeEventListener("invoiceguard:session-expired", expire);
      clearSession();
    };
  }, []);
  async function login(signup: boolean) {
    setRedirecting(true);
    setError("");
    clearSession();
    try {
      await auth.loginWithRedirect({
        appState: {
          returnTo: window.location.pathname + window.location.search,
        },
        authorizationParams: {
          screen_hint: signup ? "signup" : "login",
          ...(expired ? { prompt: "login" } : {}),
        },
      });
    } catch {
      setError(
        "Secure sign-in could not be opened. Check your connection and try again.",
      );
      setRedirecting(false);
    }
  }
  if (auth.isLoading)
    return (
      <div className="startup" role="status">
        Restoring your secure session…
      </div>
    );
  if (!auth.isAuthenticated || auth.error || expired || leaving) {
    setAccessToken(null);
    return (
      <AuthEntry
        busy={redirecting || leaving}
        error={
          error ||
          (expired
            ? "Your session has expired. Sign in again to continue."
            : auth.error
              ? "Sign-in was not completed. Please try again or contact your account administrator."
              : "")
        }
        onContinue={(signup) => void login(signup)}
      />
    );
  }
  setSessionSubject(auth.user?.sub ?? "authenticated");
  // Install before protected children issue their initial API requests.
  setAccessToken(async () => {
    try {
      const token = await auth.getAccessTokenSilently();
      if (!token) throw new Error("Missing token");
      return token;
    } catch {
      window.dispatchEvent(new Event("invoiceguard:session-expired"));
      throw new Error("Your session has expired. Sign in again.");
    }
  });
  return (
    <Session.Provider
      value={{
        enabled: true,
        email: auth.user?.email,
        name: auth.user?.name,
        verified: auth.user?.email_verified,
        logout: () => {
          clearSession();
          setLeaving(true);
          void auth
            .logout({ logoutParams: { returnTo: window.location.origin } })
            .catch(() => {
              setLeaving(false);
              setExpired(true);
              setError(
                "Sign-out could not reach the identity provider. Your local workspace has been closed. Retry sign-in to continue.",
              );
            });
        },
      }}
    >
      <div key={auth.user?.sub}>{children}</div>
    </Session.Provider>
  );
}
export function Authentication({
  config,
  children,
}: {
  config: PublicConfig;
  children: React.ReactNode;
}) {
  if (config.auth_mode !== "oidc") return <>{children}</>;
  if (!config.issuer || !config.client_id || !config.audience)
    return (
      <div className="startup" role="alert">
        Secure sign-in is not configured. Ask your administrator to configure
        the OIDC issuer, audience and client ID.
      </div>
    );
  return (
    <Auth0Provider
      domain={new URL(config.issuer).host}
      clientId={config.client_id}
      cacheLocation="memory"
      useRefreshTokens
      useRefreshTokensFallback
      authorizationParams={{
        audience: config.audience,
        redirect_uri: window.location.origin,
        scope: "openid profile email offline_access",
      }}
      onRedirectCallback={(state) => {
        const path = state?.returnTo;
        window.history.replaceState(
          {},
          document.title,
          typeof path === "string" &&
            path.startsWith("/") &&
            !path.startsWith("//")
            ? path
            : "/",
        );
      }}
    >
      <SignedIn>{children}</SignedIn>
    </Auth0Provider>
  );
}
export function AccountControl() {
  const session = useContext(Session);
  const [confirm, setConfirm] = useState(false);
  return session.enabled ? (
    <>
      <details className="account-menu">
        <summary aria-label="Your account">
          {session.email ?? session.name ?? "Your account"}
        </summary>
        <div>
          <strong>{session.name ?? "Your account"}</strong>
          <p>{session.email}</p>
          <p>
            {session.verified
              ? "Email verified"
              : "Check your inbox to verify your email, if requested."}
          </p>
          <button onClick={() => setConfirm(true)}>Sign out</button>
        </div>
      </details>
      {confirm && (
        <Dialog
          title="Sign out of InvoiceGuard?"
          onClose={() => setConfirm(false)}
        >
          <p>
            Your saved work stays in your workspace. Unsaved edits will be lost.
          </p>
          <div className="toolbar">
            <button onClick={() => setConfirm(false)}>Stay signed in</button>
            <button className="primary" onClick={session.logout}>
              Sign out securely
            </button>
          </div>
        </Dialog>
      )}
    </>
  ) : (
    <span className="account-label">Local development</span>
  );
}
