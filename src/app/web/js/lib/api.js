// Fetch layer. Errors are normalised, requests are cancelled when they stop mattering,
// and useApi keeps the previous render on screen while new data loads (no skeleton flash).
import { useCallback, useEffect, useRef, useState } from "./html.js";
import { pending } from "./store.js";

export class ApiError extends Error {
  constructor(status, code, message, hint, extra) {
    super(message);
    this.status = status;
    this.code = code;
    this.hint = hint || null;
    this.extra = extra || {};
  }
}

function query(params) {
  const usp = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    usp.set(k, Array.isArray(v) ? v.join(",") : String(v));
  });
  const s = usp.toString();
  return s ? "?" + s : "";
}

async function request(method, path, { params, body, signal } = {}) {
  pending.set((s) => ({ n: s.n + 1 }));
  try {
    const res = await fetch(path + query(params), {
      method,
      signal,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    let payload = null;
    try { payload = await res.json(); } catch (_) { /* non-JSON error page */ }
    if (!res.ok) {
      throw new ApiError(res.status, payload?.error || "http_error", payload?.message || `Request failed (${res.status})`, payload?.hint, payload);
    }
    return payload;
  } catch (err) {
    if (err instanceof ApiError || err.name === "AbortError") throw err;
    throw new ApiError(0, "network", "Cannot reach the Prem Lab server.", "Is it still running? Start it again with `prem serve`.");
  } finally {
    pending.set((s) => ({ n: Math.max(0, s.n - 1) }));
  }
}

export const api = {
  get: (path, params, opts) => request("GET", path, { params, ...opts }),
  put: (path, body) => request("PUT", path, { body }),
  post: (path, body) => request("POST", path, { body }),
  del: (path) => request("DELETE", path),
};

const cache = new Map();
const keyOf = (path, params) => path + query(params);

export function invalidate(prefix) {
  for (const k of cache.keys()) if (!prefix || k.startsWith(prefix)) cache.delete(k);
}

/**
 * useApi(path, params, { enabled, keepPrevious, staleMs, pollMs })
 * -> { data, error, loading (first load), refetching, reload }
 */
export function useApi(path, params, { enabled = true, keepPrevious = true, staleMs = 20000, pollMs = 0 } = {}) {
  const key = enabled && path ? keyOf(path, params) : null;
  const [state, setState] = useState(() => {
    const hit = key && cache.get(key);
    return { data: hit ? hit.data : null, error: null, loading: !!key && !hit, refetching: false, key };
  });
  const seq = useRef(0);
  const last = useRef(null);

  const run = useCallback((force = false) => {
    if (!key) return () => {};
    const hit = cache.get(key);
    if (hit && !force && Date.now() - hit.at < staleMs) {
      setState({ data: hit.data, error: null, loading: false, refetching: false, key });
      return () => {};
    }
    const ctl = new AbortController();
    const mine = ++seq.current;
    setState((s) => ({
      data: hit ? hit.data : keepPrevious ? (s.data ?? last.current) : null,
      error: null,
      loading: !hit && !(keepPrevious && (s.data ?? last.current)),
      refetching: !!hit || (keepPrevious && !!(s.data ?? last.current)),
      key,
    }));
    api.get(path, params, { signal: ctl.signal })
      .then((data) => {
        if (mine !== seq.current) return;
        cache.set(key, { data, at: Date.now() });
        last.current = data;
        setState({ data, error: null, loading: false, refetching: false, key });
      })
      .catch((error) => {
        if (error.name === "AbortError" || mine !== seq.current) return;
        setState((s) => ({ data: keepPrevious ? s.data : null, error, loading: false, refetching: false, key }));
      });
    return () => ctl.abort();
  }, [key]);

  useEffect(() => run(false), [run]);
  useEffect(() => {
    if (!pollMs || !key) return undefined;
    const t = setInterval(() => run(true), pollMs);
    return () => clearInterval(t);
  }, [pollMs, key, run]);

  const reload = useCallback(() => run(true), [run]);
  return { data: state.data, error: state.error, loading: state.loading, refetching: state.refetching, reload };
}
