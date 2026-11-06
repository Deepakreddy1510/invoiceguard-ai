import {
  render,
  screen,
  fireEvent,
  cleanup,
  waitFor,
} from "@testing-library/react";
import { expect, it, vi, beforeEach, afterEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { AuthEntry, Authentication, AccountControl } from "./auth";

it("offers real provider redirects for sign-in and registration without collecting passwords", () => {
  const continueToProvider = vi.fn();
  render(<AuthEntry onContinue={continueToProvider} />);
  expect(screen.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Sign in securely →" }));
  expect(continueToProvider).toHaveBeenLastCalledWith(false);
  fireEvent.click(screen.getByRole("button", { name: "Create account" }));
  expect(
    screen.getByRole("heading", { name: "Create your account" }),
  ).toBeVisible();
  fireEvent.click(
    screen.getByRole("button", { name: "Create account securely →" }),
  );
  expect(continueToProvider).toHaveBeenLastCalledWith(true);
  expect(document.querySelector('input[type="password"]')).toBeNull();
});
it("shows recoverable authentication errors, loading and provider password recovery", () => {
  const onContinue = vi.fn();
  render(<AuthEntry error="Session expired" busy onContinue={onContinue} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Session expired");
  expect(
    screen.getByRole("button", { name: "Opening secure sign-in…" }),
  ).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Forgot password?" }));
  expect(screen.getByRole("status")).toHaveTextContent("reset email");
});

const provider = vi.hoisted(() => ({
  isAuthenticated: true,
  isLoading: false,
  error: undefined,
  user: {
    sub: "account-a",
    email: "a@example.invalid",
    name: "Account A",
    email_verified: true,
  },
  getAccessTokenSilently: vi.fn(async () => "signed-test-token"),
  loginWithRedirect: vi.fn(async () => {}),
  logout: vi.fn(async () => {}),
}));
vi.mock("@auth0/auth0-react", () => ({
  Auth0Provider: ({ children }: { children: React.ReactNode }) => children,
  useAuth0: () => provider,
}));
const config = {
  auth_mode: "oidc",
  issuer: "https://tenant.auth0.com/",
  client_id: "public-client",
  audience: "api",
};
beforeEach(() => {
  provider.isAuthenticated = true;
  provider.isLoading = false;
  provider.logout.mockClear();
});
afterEach(() => cleanup());
it("restores provider sessions before exposing application data", () => {
  provider.isLoading = true;
  const view = render(
    <Authentication config={config}>
      <p>Private invoice</p>
    </Authentication>,
  );
  expect(screen.queryByText("Private invoice")).toBeNull();
  expect(screen.getByRole("status")).toHaveTextContent("Restoring");
  provider.isLoading = false;
  view.rerender(
    <Authentication config={config}>
      <p>Private invoice</p>
    </Authentication>,
  );
  expect(screen.getByText("Private invoice")).toBeVisible();
});
it("closes sensitive application content on session expiry", async () => {
  render(
    <Authentication config={config}>
      <p>Private invoice</p>
    </Authentication>,
  );
  window.dispatchEvent(new Event("invoiceguard:session-expired"));
  await waitFor(() => expect(screen.queryByText("Private invoice")).toBeNull());
  expect(screen.getByRole("alert")).toHaveTextContent("expired");
});
it("confirms logout, closes private content and invokes provider logout", async () => {
  render(
    <Authentication config={config}>
      <MemoryRouter>
        <AccountControl />
        <p>Private invoice</p>
      </MemoryRouter>
    </Authentication>,
  );
  fireEvent.click(screen.getByLabelText("Your account"));
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  expect(screen.getByRole("dialog")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Sign out securely" }));
  await waitFor(() => expect(screen.queryByText("Private invoice")).toBeNull());
  expect(provider.logout).toHaveBeenCalledWith({
    logoutParams: { returnTo: window.location.origin },
  });
});
