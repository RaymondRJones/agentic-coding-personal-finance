import { useEffect, useRef, useState } from "react";
import type { Filters } from "./types";

export function filterParams(filters: Filters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.start) params.set("start", filters.start);
  if (filters.end) params.set("end", filters.end);
  for (const account of filters.accounts) params.append("account", account);
  if (filters.category) params.append("category", filters.category);
  if (filters.merchant.trim()) params.set("merchant", filters.merchant.trim());
  params.set("drop_duplicates", String(filters.dropDuplicates));
  return params;
}

export function apiUrl(path: string, params?: URLSearchParams): string {
  const query = params?.toString();
  return query ? `/api/${path}?${query}` : `/api/${path}`;
}

interface ApiState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

/**
 * Fetch JSON and keep the previous result while a new one loads, so charts hold
 * their frame (rendered at reduced opacity) instead of flashing a skeleton.
 */
export function useApi<T>(url: string | null): ApiState<T> {
  const [state, setState] = useState<ApiState<T>>({ data: null, error: null, loading: url !== null });
  const latest = useRef(url);

  useEffect(() => {
    latest.current = url;
    if (url === null) return;
    const controller = new AbortController();
    setState((s) => ({ ...s, loading: true }));
    fetch(url, { signal: controller.signal })
      .then(async (res) => {
        const body = await res.json();
        if (!res.ok) throw new Error(body.error ?? `Request failed (${res.status})`);
        return body as T;
      })
      .then((data) => {
        if (latest.current === url) setState({ data, error: null, loading: false });
      })
      .catch((err: Error) => {
        if (err.name !== "AbortError") setState((s) => ({ ...s, error: err.message, loading: false }));
      });
    return () => controller.abort();
  }, [url]);

  return state;
}
