import { createContext, useContext, useEffect, useState, useRef } from "react";
import {
  createClient,
  type SupabaseClient,
  type Session as SupabaseSession,
} from "@supabase/supabase-js";
import { clearSession, setAccessToken, setSessionSubject } from "./client";
import { Icon } from "./icons";
import { Dialog } from "./Experience";
import "./auth.css";
type PublicConfig = {
  auth_mode: string;
  supabase_url: string;
  supabase_publishable_key: string;
};
const Session = createContext<{
  enabled: boolean;
  email?: string;
  name?: string;
  verified?: boolean;
  logout?: () => void;
}>({ enabled: false });

type Action = "login" | "signup" | "forgot" | "reset" | "resend";
export function AuthEntry({
  busy = false,
  error = "",
  message = "",
  recovery = false,
  onContinue,
  onModeChange,
  onCancelRecovery,
}: {
  busy?: boolean;
  error?: string;
  message?: string;
  recovery?: boolean;
  onContinue: (action: Action, email: string, password: string) => void;
  onModeChange?: () => void;
  onCancelRecovery?: () => void;
}) {
  const [signup, setSignup] = useState(false);
  const [reset, setReset] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const passwordInput = useRef<HTMLInputElement>(null);
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
            {recovery
              ? "Set a new password"
              : reset
                ? "Reset your password"
                : signup
                  ? "Create your account"
                  : "Welcome back"}
          </h2>
          <p>
            {signup
              ? "A private workspace for your team’s next chapter."
              : "Sign in to pick up where your team left off."}
          </p>
          {!recovery && (
            <div className="auth-tabs" aria-label="Account access">
              <button
                aria-pressed={!signup}
                onClick={() => {
                  setVisible(false);
                  onModeChange?.();
                  setSignup(false);
                  setReset(false);
                }}
              >
                Sign in
              </button>
              <button
                aria-pressed={signup}
                onClick={() => {
                  setVisible(false);
                  onModeChange?.();
                  setSignup(true);
                  setReset(false);
                }}
              >
                Create account
              </button>
            </div>
          )}
          {error && (
            <div className="error-banner" role="alert">
              {error}
            </div>
          )}
          {message && <p role="status">{message}</p>}
          <form
            onSubmit={(event) => {
              event.preventDefault();
              if (busy) return;
              onContinue(
                recovery
                  ? "reset"
                  : reset
                    ? "forgot"
                    : signup
                      ? "signup"
                      : "login",
                email,
                password,
              );
            }}
          >
            {!recovery && (
              <label>
                Email address
                <input
                  type="email"
                  name="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </label>
            )}
            {(!reset || recovery) && (
              <div className="password-field">
                <label htmlFor="auth-password">Password</label>
                <div className="password-input">
                  <input
                    id="auth-password"
                    name="password"
                    ref={passwordInput}
                    type={visible ? "text" : "password"}
                    required
                    minLength={signup || recovery ? 8 : undefined}
                    autoComplete={
                      signup || recovery ? "new-password" : "current-password"
                    }
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                  />
                  <button
                    type="button"
                    className="password-toggle"
                    aria-label={visible ? "Hide password" : "Show password"}
                    aria-pressed={visible}
                    onClick={() => {
                      setVisible((value) => !value);
                      passwordInput.current?.focus();
                    }}
                  >
                    <Icon name={visible ? "eye-off" : "eye"} />
                  </button>
                </div>
              </div>
            )}
            <button className="primary auth-continue" disabled={busy}>
              {busy
                ? "Please wait…"
                : recovery
                  ? "Save new password"
                  : reset
                    ? "Send reset email"
                    : signup
                      ? "Create account securely →"
                      : "Sign in securely →"}
            </button>
          </form>
          {recovery && (
            <button
              className="text-button"
              onClick={() => {
                setVisible(false);
                onCancelRecovery?.();
              }}
            >
              Back to sign in
            </button>
          )}
          {!signup && !recovery && (
            <button
              className="text-button"
              onClick={() => {
                setVisible(false);
                onModeChange?.();
                setReset(!reset);
              }}
            >
              {reset ? "Back to sign in" : "Forgot password?"}
            </button>
          )}
          {!recovery && (
            <button
              className="text-button"
              disabled={busy || !email}
              onClick={() => onContinue("resend", email, "")}
            >
              Resend verification email
            </button>
          )}
          <p className="auth-security">
            Your credentials are sent securely to Supabase Auth. Confirm your
            email before signing in.
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

function SignedIn({
  client,
  children,
}: {
  client: SupabaseClient;
  children: React.ReactNode;
}) {
  const [session, setSession] = useState<SupabaseSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const submitting = useRef(false);
  const modeRevision = useRef(0);
  const [recovery, setRecovery] = useState(
    new URLSearchParams(window.location.search).get("auth") === "recovery",
  );
  useEffect(() => {
    let live = true;
    let authRevision = 0;
    const { data } = client.auth.onAuthStateChange((event, next) => {
      if (!live) return;
      authRevision += 1;
      if (event === "PASSWORD_RECOVERY") setRecovery(true);
      if (next) setSessionSubject(next.user.id);
      else clearSession();
      setSession(next);
      setLoading(false);
    });
    const initialRevision = authRevision;
    void client.auth
      .getSession()
      .then(({ data, error }) => {
        if (!live || authRevision !== initialRevision) return;
        if (error)
          setError("Could not restore your session. Please sign in again.");
        setSession(data.session);
        setLoading(false);
      })
      .catch(() => {
        if (live) {
          setError("Could not reach sign-in. Check your connection.");
          setLoading(false);
        }
      });
    const expire = () => {
      clearSession();
      setSession(null);
      setError("Your session has expired. Sign in again to continue.");
      void client.auth.signOut({ scope: "local" });
    };
    window.addEventListener("invoiceguard:session-expired", expire);
    return () => {
      live = false;
      data.subscription.unsubscribe();
      window.removeEventListener("invoiceguard:session-expired", expire);
      clearSession();
    };
  }, [client]);
  async function perform(action: Action, email: string, password: string) {
    if (submitting.current) return;
    submitting.current = true;
    const revision = modeRevision.current;
    setBusy(true);
    setError("");
    setMessage("");
    const redirect = window.location.origin + "/";
    try {
      let result;
      if (action === "signup")
        result = await client.auth.signUp({
          email,
          password,
          options: { emailRedirectTo: redirect },
        });
      else if (action === "forgot")
        result = await client.auth.resetPasswordForEmail(email, {
          redirectTo: redirect + "?auth=recovery",
        });
      else if (action === "reset") {
        result = await client.auth.updateUser({ password });
        if (!result.error) {
          const signedOut = await client.auth.signOut({ scope: "local" });
          if (signedOut.error) throw signedOut.error;
          clearSession();
          setSession(null);
          setRecovery(false);
          window.history.replaceState({}, "", "/");
        }
      } else if (action === "resend")
        result = await client.auth.resend({
          type: "signup",
          email,
          options: { emailRedirectTo: redirect },
        });
      else result = await client.auth.signInWithPassword({ email, password });
      if (revision !== modeRevision.current) return;
      if (result.error) throw result.error;
      if (action === "login") {
        const authenticated =
          "data" in result
            ? (result.data as { session?: SupabaseSession | null })
            : null;
        if (!authenticated?.session) throw new Error("missing_session");
        window.history.replaceState({}, "", "/");
        setSessionSubject(authenticated.session.user.id);
        setSession(authenticated.session);
      }
      if (action === "signup" || action === "resend")
        setMessage(
          "Check your inbox to confirm your email. If the account already exists, sign in or reset your password.",
        );
      if (action === "forgot")
        setMessage(
          "If an account exists, a password reset email is on its way.",
        );
      if (action === "reset")
        setMessage("Password updated. Sign in with your new password.");
    } catch (cause) {
      if (revision !== modeRevision.current) return;
      const code =
        typeof cause === "object" && cause !== null && "code" in cause
          ? String(cause.code)
          : "";
      const legacyProvider =
        typeof cause === "object" &&
        cause !== null &&
        "name" in cause &&
        cause.name === "AuthApiError" &&
        "status" in cause &&
        cause.status === 400;
      const legacyMessage =
        legacyProvider && "message" in cause ? String(cause.message) : "";
      if (
        action === "login" &&
        (code === "invalid_credentials" ||
          legacyMessage === "Invalid login credentials")
      )
        setError("Invalid email or password. Please try again.");
      else if (
        action === "login" &&
        (code === "email_not_confirmed" ||
          legacyMessage === "Email not confirmed")
      )
        setError(
          "Confirm your email before signing in. Check your inbox or resend the verification email.",
        );
      else if (
        action === "signup" &&
        ["user_already_exists", "email_exists"].includes(code)
      )
        setMessage(
          "Check your inbox to confirm your email. If the account already exists, sign in or reset your password.",
        );
      else if (code === "weak_password" || code === "validation_failed")
        setError(
          "Use a valid email address and a password of at least 8 characters, then try again.",
        );
      else if (
        ["over_request_rate_limit", "over_email_send_rate_limit"].includes(code)
      )
        setError("Too many attempts. Wait a moment, then try again.");
      else
        setError(
          "Unable to complete this request. Check your connection and try again. If it continues, contact your administrator.",
        );
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  if (loading)
    return (
      <div className="startup" role="status">
        Restoring your secure session…
      </div>
    );
  if (!session || recovery)
    return (
      <AuthEntry
        busy={busy}
        error={error}
        message={message}
        recovery={recovery}
        onContinue={(...args) => void perform(...args)}
        onModeChange={() => {
          modeRevision.current += 1;
          setError("");
          setMessage("");
        }}
        onCancelRecovery={() => {
          modeRevision.current += 1;
          clearSession();
          setSession(null);
          setRecovery(false);
          setError("");
          setMessage("");
          window.history.replaceState({}, "", "/");
          void client.auth.signOut({ scope: "local" });
        }}
      />
    );
  setSessionSubject(session.user.id);
  setAccessToken(async () => {
    const { data, error } = await client.auth.getSession();
    if (error || !data.session) {
      window.dispatchEvent(new Event("invoiceguard:session-expired"));
      throw new Error("Your session has expired.");
    }
    return data.session.access_token;
  });
  return (
    <Session.Provider
      value={{
        enabled: true,
        email: session.user.email,
        verified: !!session.user.email_confirmed_at,
        logout: () => {
          clearSession();
          setSession(null);
          void client.auth.signOut().then(({ error }) => {
            if (error) {
              void client.auth.signOut({ scope: "local" });
              setError(
                "Signed out on this device. The server could not revoke other sessions.",
              );
            }
          });
        },
      }}
    >
      <div key={session.user.id}>{children}</div>
    </Session.Provider>
  );
}
function SupabaseAuthentication({
  config,
  children,
}: {
  config: PublicConfig;
  children: React.ReactNode;
}) {
  const [client] = useState(() =>
    createClient(config.supabase_url, config.supabase_publishable_key, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
        flowType: "pkce",
      },
    }),
  );
  return <SignedIn client={client}>{children}</SignedIn>;
}
export function Authentication({
  config,
  children,
}: {
  config: PublicConfig;
  children: React.ReactNode;
}) {
  if (config.auth_mode === "local") return <>{children}</>;
  if (
    config.auth_mode !== "supabase" ||
    !config.supabase_url ||
    !config.supabase_publishable_key
  )
    return (
      <div className="startup" role="alert">
        Secure sign-in is not configured. Ask your administrator to configure
        Supabase.
      </div>
    );
  return (
    <SupabaseAuthentication config={config}>{children}</SupabaseAuthentication>
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
