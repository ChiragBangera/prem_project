// Fetch layer. Errors are normalised, requests are cancelled when they stop mattering, and useApi keeps the previous render on screen
// while new data loads (no skeleton flash). Answers are remembered twice: in memory for the session, and in IndexedDB (lib/cache.js) so
// a page opened again later paints at once from the last copy and swaps in the fresh answer when it differs.
import { useCallback, useEffect, useRef, useState } from "./html.js";
import { pending } from "./store.js";
import { persistedDelete, persistedGet, persistedSet } from "./cache.js";

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

const cache = new Map();                 // key -> { data, at }; at = 0 marks a copy restored from IndexedDB (shown, but always revalidated)
const inflight = new Map();              // key -> promise, so two components asking for the same thing share one request
const keyOf = (path, params) => path + query(params);

// Endpoints whose answer must always be live: never shown from a stored copy.
const LIVE = ["/api/data", "/api/health", "/api/search", "/api/shortlist", "/api/meta"];
const storable = (path) => !LIVE.some((p) => path.startsWith(p));

export function invalidate(prefix) {
  for (const k of [...cache.keys()]) if (!prefix || k.startsWith(prefix)) cache.delete(k);
  persistedDelete(prefix || "");
}

function load(key, path, params, signal) {
  const shared = inflight.get(key);
  if (shared) return shared;
  const p = api.get(path, params, { signal }).then((data) => {
    cache.set(key, { data, at: Date.now() });
    if (storable(path)) persistedSet(key, data);
    return data;
  }).finally(() => { inflight.delete(key); });
  // a request that someone aborted must not be handed to the next caller
  if (!signal) inflight.set(key, p);
  return p;
}

/** Start loading something the user is likely to ask for next. Failures are ignored. */
export function prefetch(path, params) {
  const key = keyOf(path, params);
  const hit = cache.get(key);
  if (hit && hit.at && Date.now() - hit.at < 60000) return;
  load(key, path, params).catch(() => {});
}

/**
 * useApi(path, params, { enabled, keepPrevious, staleMs, pollMs, persist })
 * -> { data, error, loading (first load), refetching, reload, restored }
 *
 * `restored` is true while the data on screen is the stored copy from an earlier visit and the fresh answer is still on its way.
 */
export function useApi(path, params, { enabled = true, keepPrevious = true, staleMs = 20000, pollMs = 0, persist = true } = {}) {
  const key = enabled && path ? keyOf(path, params) : null;
  const [state, setState] = useState(() => {
    const hit = key && cache.get(key);
    return { data: hit ? hit.data : null, error: null, loading: !!key && !hit, refetching: false, restored: false, key };
  });
  const seq = useRef(0);
  const last = useRef(null);

  const run = useCallback((force = false) => {
    if (!key) return () => {};
    const hit = cache.get(key);
    if (hit && hit.at && !force && Date.now() - hit.at < staleMs) {
      setState({ data: hit.data, error: null, loading: false, refetching: false, restored: false, key });
      return () => {};
    }
    const ctl = new AbortController();
    const mine = ++seq.current;
    let networked = false;
    setState((s) => ({
      data: hit ? hit.data : keepPrevious ? (s.data ?? last.current) : null,
      error: null,
      loading: !hit && !(keepPrevious && (s.data ?? last.current)),
      refetching: !!hit || (keepPrevious && !!(s.data ?? last.current)),
      restored: false,
      key,
    }));
    if (!hit && persist && storable(path)) {
      persistedGet(key).then((entry) => {
        if (!entry || networked || mine !== seq.current) return;
        if (!cache.has(key)) cache.set(key, { data: entry.data, at: 0 });
        last.current = entry.data;
        setState({ data: entry.data, error: null, loading: false, refetching: true, restored: true, key });
      });
    }
    load(key, path, params, ctl.signal)
      .then((data) => {
        networked = true;
        if (mine !== seq.current) return;
        last.current = data;
        setState({ data, error: null, loading: false, refetching: false, restored: false, key });
      })
      .catch((error) => {
        networked = true;
        if (error.name === "AbortError" || mine !== seq.current) return;
        // a restored copy is better than an error page: keep showing it, and say the refresh failed
        setState((s) => ({ data: keepPrevious ? s.data : null, error, loading: false, refetching: false, restored: false, key }));
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
  return { data: state.data, error: state.error, loading: state.loading, refetching: state.refetching, restored: state.restored, reload };
}
