let accessToken: (() => Promise<string>) | null = null;
export function setAccessToken(getter: (() => Promise<string>) | null) {
  accessToken = getter;
}
export async function apiFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  if (!accessToken) return fetch(path, init);
  const token = await accessToken();
  const headers = new Headers(init?.headers);
  headers.set("Authorization", "Bearer " + token);
  return fetch(path, { ...init, headers });
}
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch("/api/v1" + path, init);
  if (!response.ok) {
    const body = await response
      .json()
      .catch(() => ({ detail: "Request failed." }));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : "Request rejected. Check your fields and access.",
    );
  }
  return response.json();
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
