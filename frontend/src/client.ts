let accessToken: (() => Promise<string>) | null = null;
export function setAccessToken(getter: (() => Promise<string>) | null) {
  accessToken = getter;
}
let activeWorkspace: string | null = null;
let workspaceEpoch = 0;
const pending = new Set<AbortController>();
export function setActiveWorkspace(id: string | null) {
  if (activeWorkspace === id) return;
  activeWorkspace = id;
  workspaceEpoch += 1;
  for (const controller of pending) controller.abort();
  pending.clear();
}
export async function apiFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const id = activeWorkspace,
    epoch = workspaceEpoch;
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (init?.signal?.aborted) controller.abort();
  init?.signal?.addEventListener("abort", abort, { once: true });
  pending.add(controller);
  try {
    const headers = new Headers(init?.headers);
    if (id) headers.set("X-Workspace-ID", id);
    if (accessToken)
      headers.set("Authorization", "Bearer " + (await accessToken()));
    if (epoch !== workspaceEpoch || controller.signal.aborted)
      throw new DOMException("Workspace changed.", "AbortError");
    const response = await fetch(path, {
      ...init,
      headers,
      signal: controller.signal,
    });
    if (epoch !== workspaceEpoch)
      throw new DOMException("Workspace changed.", "AbortError");
    return response;
  } finally {
    pending.delete(controller);
    init?.signal?.removeEventListener("abort", abort);
  }
}
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const epoch = workspaceEpoch;
  const response = await apiFetch("/api/v1" + path, init);
  if (!response.ok) {
    const body = await response
      .json()
      .catch(() => ({ detail: "Request failed." }));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : (body.detail?.message ??
            (Array.isArray(body.detail)
              ? body.detail
                  .map(
                    (item: { loc: unknown[]; msg: string }) =>
                      item.loc.slice(1).join(".") + ": " + item.msg,
                  )
                  .join("; ")
              : "Request rejected. Check your fields and access.")),
    );
  }
  const data = await response.json();
  if (epoch !== workspaceEpoch)
    throw new DOMException("Workspace changed.", "AbortError");
  return data;
}
export function jsonPost(path: string, body: unknown) {
  return request<any>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
export function money(
  value: string | number | null | undefined,
  currency: string = "USD",
) {
  if (value == null) return "—";
  const raw = String(value);
  if (!/^-?\d+(\.\d+)?$/.test(raw)) return raw;
  const [whole, fraction = ""] = raw.split(".");
  const places = currency === "JPY" ? 0 : currency === "KWD" ? 3 : 2;
  const decimals = fraction.replace(/0+$/, "").padEnd(places, "0");
  return (
    currency +
    " " +
    whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",") +
    (decimals ? "." + decimals : "")
  );
}
export function when(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : "—";
}

export function duration(ms: number | null | undefined) {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return "—";
  if (ms < 1000) return Math.round(ms) + " ms";
  if (ms < 60000) return (ms / 1000).toFixed(1) + " s";
  return Math.floor(ms / 60000) + "m " + Math.floor((ms % 60000) / 1000) + "s";
}
export function relativeTime(
  value: string | null | undefined,
  now = Date.now(),
) {
  if (!value || !Number.isFinite(Date.parse(value))) return "Time unavailable";
  const seconds = Math.max(0, Math.floor((now - Date.parse(value)) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return seconds + "s ago";
  if (seconds < 3600) return Math.floor(seconds / 60) + "m ago";
  if (seconds < 86400) return Math.floor(seconds / 3600) + "h ago";
  return Math.floor(seconds / 86400) + "d ago";
}
export function utilization(part: string | undefined, total: string) {
  if (
    part == null ||
    !/^\d+(\.\d+)?$/.test(part) ||
    !/^\d+(\.\d+)?$/.test(total)
  )
    return null;
  const integer = (v: string) => {
    const [whole, fraction = ""] = v.split(".");
    return BigInt(whole + fraction.padEnd(6, "0").slice(0, 6));
  };
  const a = integer(part),
    b = integer(total);
  if (b <= 0n) return null;
  return Math.min(100, Number((a * 10000n) / b) / 100);
}
