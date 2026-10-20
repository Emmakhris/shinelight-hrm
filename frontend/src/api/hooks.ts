import { useMutation, useQuery, useQueryClient, type UseQueryOptions } from "@tanstack/react-query";
import { api, asList, type Paginated } from "./client";

export type Params = Record<string, string | number | boolean | undefined | null>;

function clean(params?: Params) {
  const out: Record<string, string | number | boolean> = {};
  if (!params) return out;
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") out[k] = v;
  return out;
}

export function useApi<T = unknown>(url: string | null, params?: Params,
  options?: Omit<UseQueryOptions<T>, "queryKey" | "queryFn">) {
  return useQuery<T>({
    queryKey: [url, clean(params)],
    queryFn: async () => (await api.get<T>(url as string, { params: clean(params) })).data,
    enabled: !!url && (options?.enabled ?? true),
    ...options,
  });
}

/** Fetch a (possibly paginated) list endpoint and always return an array. */
export function useList<T = Record<string, unknown>>(url: string | null, params?: Params) {
  const q = useApi<Paginated<T> | T[]>(url, { page_size: 500, ...params });
  return { ...q, items: asList<T>(q.data), count: Array.isArray(q.data) ? q.data.length : q.data?.count ?? 0 };
}

export function useInvalidate() {
  const qc = useQueryClient();
  return (...prefixes: string[]) =>
    qc.invalidateQueries({
      predicate: (q) => prefixes.some((p) => typeof q.queryKey[0] === "string" && (q.queryKey[0] as string).startsWith(p)),
    });
}

export function useAction<TVars = unknown, TRes = unknown>(fn: (vars: TVars) => Promise<TRes>, invalidate: string[] = []) {
  const inv = useInvalidate();
  return useMutation<TRes, unknown, TVars>({
    mutationFn: fn,
    onSuccess: () => {
      if (invalidate.length) inv(...invalidate);
    },
  });
}

export const post = <T = unknown>(url: string, data?: unknown) => api.post<T>(url, data).then((r) => r.data);
export const patch = <T = unknown>(url: string, data?: unknown) => api.patch<T>(url, data).then((r) => r.data);
export const put = <T = unknown>(url: string, data?: unknown) => api.put<T>(url, data).then((r) => r.data);
export const del = (url: string) => api.delete(url).then((r) => r.data);
