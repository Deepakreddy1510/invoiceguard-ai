import { afterEach, expect, it, vi } from "vitest";
import {
  apiFetch,
  request,
  setAccessToken,
  setActiveWorkspace,
} from "./client";
afterEach(() => {
  setAccessToken(null);
  setActiveWorkspace(null);
  vi.unstubAllGlobals();
});
it("pins the workspace before asynchronous token acquisition and rejects a stale upload", async () => {
  let resolve!: (value: string) => void;
  setAccessToken(
    () =>
      new Promise<string>((done) => {
        resolve = done;
      }),
  );
  setActiveWorkspace("demo");
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  const upload = apiFetch("/api/v1/documents", { method: "POST" });
  const result = expect(upload).rejects.toHaveProperty("name", "AbortError");
  setActiveWorkspace("private");
  resolve("synthetic-test-token");
  await result;
  expect(fetcher).not.toHaveBeenCalled();
});
it("aborts old requests and discards responses whose body arrives after switching", async () => {
  let resolve!: (value: unknown) => void;
  let signal!: AbortSignal;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_: string, init: RequestInit) => {
      signal = init.signal!;
      return {
        ok: true,
        json: () =>
          new Promise((done) => {
            resolve = done;
          }),
      };
    }),
  );
  setActiveWorkspace("demo");
  const old = request("/dashboard");
  const result = expect(old).rejects.toHaveProperty("name", "AbortError");
  await vi.waitFor(() => expect(resolve).toBeDefined());
  setActiveWorkspace("private");
  resolve({ total_invoices: 100 });
  await result;
  expect(signal).toBeDefined();
});
it("sends the authorized selection on every API request including PDF reads", async () => {
  const fetcher = vi.fn(async () => ({ ok: true }));
  vi.stubGlobal("fetch", fetcher);
  setActiveWorkspace("private");
  await apiFetch("/api/v1/documents/id/pdf");
  const init = fetcher.mock.calls[0] as unknown as [string, RequestInit];
  expect(new Headers(init[1].headers).get("X-Workspace-ID")).toBe("private");
});
