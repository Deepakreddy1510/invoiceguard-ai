import {
  render,
  screen,
  fireEvent,
  cleanup,
  waitFor,
  act,
} from "@testing-library/react";
import { expect, it, vi, beforeEach, afterEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { AuthEntry, Authentication, AccountControl } from "./auth";
const provider = vi.hoisted(() => ({
  session: null as null | {
    access_token: string;
    user: { id: string; email: string; email_confirmed_at: string };
  },
  listener: vi.fn<(event: string, session: unknown) => void>(),
  signUp: vi.fn(async () => ({ error: null })),
  signInWithPassword: vi.fn(async () => ({ error: null })),
  resetPasswordForEmail: vi.fn(async () => ({ error: null })),
  updateUser: vi.fn(async () => ({ error: null })),
  resend: vi.fn(async () => ({ error: null })),
  signOut: vi.fn(async () => ({ error: null })),
}));
vi.mock("@supabase/supabase-js", () => ({
  createClient: () => ({
    auth: {
      ...provider,
      getSession: async () => ({
        data: { session: provider.session },
        error: null,
      }),
      onAuthStateChange: (listener: typeof provider.listener) => {
        provider.listener = listener;
        return { data: { subscription: { unsubscribe: vi.fn() } } };
      },
    },
  }),
}));
const config = {
  auth_mode: "supabase",
  supabase_url: "https://project.supabase.co",
  supabase_publishable_key: "sb_publishable_test",
};
beforeEach(() => {
  provider.session = null;
  vi.clearAllMocks();
  window.history.replaceState({}, "", "/");
});
afterEach(cleanup);
function app() {
  return render(
    <Authentication config={config}>
      <MemoryRouter>
        <AccountControl />
        <p>Private invoice</p>
      </MemoryRouter>
    </Authentication>,
  );
}
async function credentials() {
  fireEvent.change(await screen.findByLabelText("Email address"), {
    target: { value: "a@example.invalid" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "correct-password" },
  });
}
it("collects signup credentials and shows email confirmation guidance", async () => {
  app();
  fireEvent.click(
    await screen.findByRole("button", { name: /^Create account$/ }),
  );
  await credentials();
  fireEvent.click(
    screen.getByRole("button", { name: "Create account securely →" }),
  );
  await waitFor(() =>
    expect(provider.signUp).toHaveBeenCalledWith({
      email: "a@example.invalid",
      password: "correct-password",
      options: { emailRedirectTo: window.location.origin + "/" },
    }),
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    "confirm your email",
  );
  expect(screen.queryByText("Private invoice")).toBeNull();
});
it("logs in with email/password and can resend verification", async () => {
  app();
  await credentials();
  fireEvent.click(screen.getByRole("button", { name: "Sign in securely →" }));
  await waitFor(() =>
    expect(provider.signInWithPassword).toHaveBeenCalledWith({
      email: "a@example.invalid",
      password: "correct-password",
    }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Resend verification email" }),
  );
  await waitFor(() => expect(provider.resend).toHaveBeenCalled());
});
it("sends recovery mail to the configured recovery route", async () => {
  app();
  await screen.findByLabelText("Email address");
  fireEvent.click(screen.getByRole("button", { name: "Forgot password?" }));
  fireEvent.change(screen.getByLabelText("Email address"), {
    target: { value: "a@example.invalid" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send reset email" }));
  await waitFor(() =>
    expect(provider.resetPasswordForEmail).toHaveBeenCalledWith(
      "a@example.invalid",
      { redirectTo: window.location.origin + "/?auth=recovery" },
    ),
  );
});
it("restores sessions, closes content on expiry and account changes", async () => {
  provider.session = {
    access_token: "token",
    user: {
      id: "account-a",
      email: "a@example.invalid",
      email_confirmed_at: "now",
    },
  };
  app();
  expect(await screen.findByText("Private invoice")).toBeVisible();
  act(() => window.dispatchEvent(new Event("invoiceguard:session-expired")));
  expect(screen.queryByText("Private invoice")).toBeNull();
  expect(screen.getByRole("alert")).toHaveTextContent("expired");
});
it("requires recovery password update before rendering private data", async () => {
  window.history.replaceState({}, "", "/?auth=recovery");
  provider.session = {
    access_token: "token",
    user: {
      id: "account-a",
      email: "a@example.invalid",
      email_confirmed_at: "now",
    },
  };
  app();
  fireEvent.change(await screen.findByLabelText("Password"), {
    target: { value: "new-password" },
  });
  expect(screen.queryByText("Private invoice")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Save new password" }));
  await waitFor(() =>
    expect(provider.updateUser).toHaveBeenCalledWith({
      password: "new-password",
    }),
  );
  expect(provider.signOut).toHaveBeenCalled();
});
it("confirms logout and closes sensitive content immediately", async () => {
  provider.session = {
    access_token: "token",
    user: {
      id: "account-a",
      email: "a@example.invalid",
      email_confirmed_at: "now",
    },
  };
  app();
  await screen.findByText("Private invoice");
  fireEvent.click(screen.getByLabelText("Your account"));
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  fireEvent.click(screen.getByRole("button", { name: "Sign out securely" }));
  expect(screen.queryByText("Private invoice")).toBeNull();
  expect(provider.signOut).toHaveBeenCalled();
});
it("shows authentication errors and disables busy submissions", () => {
  render(<AuthEntry busy error="Invalid credentials" onContinue={vi.fn()} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Invalid credentials");
  expect(screen.getByRole("button", { name: "Please wait…" })).toBeDisabled();
});

it("remounts private content across accounts and accepts refreshed sessions", async () => {
  provider.session = {
    access_token: "first",
    user: {
      id: "account-a",
      email: "a@example.invalid",
      email_confirmed_at: "now",
    },
  };
  app();
  await screen.findByText("Private invoice");
  act(() =>
    provider.listener("TOKEN_REFRESHED", {
      ...provider.session,
      access_token: "refreshed",
    }),
  );
  expect(screen.getByText("Private invoice")).toBeVisible();
  act(() =>
    provider.listener("SIGNED_IN", {
      access_token: "second",
      user: {
        id: "account-b",
        email: "b@example.invalid",
        email_confirmed_at: "now",
      },
    }),
  );
  expect(
    screen.getByText("b@example.invalid", { selector: "summary" }),
  ).toBeVisible();
  act(() => provider.listener("SIGNED_OUT", null));
  expect(screen.queryByText("Private invoice")).toBeNull();
});
