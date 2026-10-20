import axios, { AxiosError } from "axios";

export const api = axios.create({
  baseURL: "/api",
  withCredentials: true,
  xsrfCookieName: "csrftoken",
  xsrfHeaderName: "X-CSRFToken",
});

let refreshing: Promise<unknown> | null = null;
let onSessionExpired: (() => void) | null = null;

export function setSessionExpiredHandler(fn: () => void) {
  onSessionExpired = fn;
}

api.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const original = error.config as (typeof error.config & { _retry?: boolean }) | undefined;
    const url = original?.url || "";
    if (error.response?.status === 401 && original && !original._retry && !url.startsWith("/auth/")) {
      original._retry = true;
      try {
        refreshing = refreshing || api.post("/auth/refresh/");
        await refreshing;
        refreshing = null;
        return api(original);
      } catch {
        refreshing = null;
        onSessionExpired?.();
      }
    }
    return Promise.reject(error);
  },
);

/** Human-readable message from a DRF error response. */
export function errorMessage(err: unknown): string {
  const e = err as AxiosError<Record<string, unknown>>;
  const data = e?.response?.data;
  if (!data) return e?.message || "Something went wrong. Check your connection and try again.";
  if (typeof (data as unknown) === "string") return (data as unknown as string).slice(0, 300);
  if (typeof data.detail === "string") return data.detail;
  const parts: string[] = [];
  for (const [k, v] of Object.entries(data)) {
    const msg = Array.isArray(v) ? v.join(" ") : typeof v === "object" ? JSON.stringify(v) : String(v);
    parts.push(k === "non_field_errors" || k === "detail" ? msg : `${k.replace(/_/g, " ")}: ${msg}`);
  }
  return parts.join(" • ") || "Request failed.";
}

export function fieldErrors(err: unknown): Record<string, string> {
  const data = (err as AxiosError<Record<string, unknown>>)?.response?.data;
  const out: Record<string, string> = {};
  if (data && typeof data === "object") {
    for (const [k, v] of Object.entries(data)) out[k] = Array.isArray(v) ? v.join(" ") : String(v);
  }
  return out;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export function asList<T>(data: Paginated<T> | T[] | undefined): T[] {
  if (!data) return [];
  return Array.isArray(data) ? data : data.results;
}

/** Download a file endpoint (keeps cookies/auth) and trigger a browser save. */
export async function download(url: string, params?: Record<string, unknown>, fallbackName = "download") {
  const res = await api.get(url, { params, responseType: "blob" });
  const cd = (res.headers["content-disposition"] as string) || "";
  const match = /filename="?([^";]+)"?/.exec(cd);
  const name = match ? match[1] : fallbackName;
  const href = URL.createObjectURL(res.data as Blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 5000);
}

export async function openBlob(url: string, params?: Record<string, unknown>) {
  const res = await api.get(url, { params, responseType: "blob" });
  const href = URL.createObjectURL(res.data as Blob);
  window.open(href, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(href), 60000);
}
