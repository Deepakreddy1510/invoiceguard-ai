import { createContext, useContext, useEffect } from "react";
import { Auth0Provider, useAuth0 } from "@auth0/auth0-react";
import { setAccessToken } from "./client";
type PublicConfig = {
  auth_mode: string;
  issuer: string;
  client_id: string;
  audience: string;
};
const Session = createContext<{
  enabled: boolean;
  email?: string;
  logout?: () => void;
}>({ enabled: false });
function SignedIn({ children }: { children: React.ReactNode }) {
  const auth = useAuth0();
  const { isAuthenticated, getAccessTokenSilently } = auth;
  useEffect(() => {
    if (isAuthenticated)
      setAccessToken(async () => {
        const token = await getAccessTokenSilently();
        if (!token)
          throw new Error("No API access token was returned. Sign in again.");
        return token;
      });
    else setAccessToken(null);
  }, [isAuthenticated, getAccessTokenSilently]);
  if (auth.isLoading)
    return <div className="startup">Checking your secure session…</div>;
  if (auth.error)
    return (
      <div className="startup" role="alert">
        Sign-in failed: {auth.error.message}
        <button onClick={() => auth.loginWithRedirect()}>
          Try sign-in again
        </button>
      </div>
    );
  if (!auth.isAuthenticated)
    return (
      <div className="login-card">
        <div className="logo-mark">IG</div>
        <p className="eyebrow">INVOICEGUARD AI</p>
        <h1>
          A clear decision.
          <br />
          An evidence trail.
        </h1>
        <p>
          Sign in with your invited account to access your synthetic
          demonstration workspace.
        </p>
        <button className="primary" onClick={() => auth.loginWithRedirect()}>
          Sign in securely
        </button>
      </div>
    );
  // Install before children issue requests, including the initial render.
  setAccessToken(async () => {
    const token = await auth.getAccessTokenSilently();
    if (!token)
      throw new Error("No API access token was returned. Sign in again.");
    return token;
  });
  return (
    <Session.Provider
      value={{
        enabled: true,
        email: auth.user?.email,
        logout: () =>
          auth.logout({ logoutParams: { returnTo: window.location.origin } }),
      }}
    >
      {children}
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
  return (
    <Auth0Provider
      domain={new URL(config.issuer).host}
      clientId={config.client_id}
      cacheLocation="memory"
      authorizationParams={{
        audience: config.audience,
        redirect_uri: window.location.origin,
      }}
    >
      <SignedIn>{children}</SignedIn>
    </Auth0Provider>
  );
}
export function AccountControl() {
  const session = useContext(Session);
  return session.enabled ? (
    <div className="account">
      <span>{session.email ?? "Invited evaluator"}</span>
      <button onClick={session.logout}>Sign out</button>
    </div>
  ) : (
    <span className="account-label">Finance workspace</span>
  );
}
