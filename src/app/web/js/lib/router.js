// Hash router. The URL is the source of truth for page state, so views are linkable.
import { useEffect, useState } from "./html.js";

const attempt = (decode, text) => { try { return decode(text); } catch (_) { return text; } };

/**
 * The path and the query of a hash such as "#/scout?r=ATT". A malformed percent-escape (a link cut short in a chat, say) is left as
 * it is instead of throwing, which would otherwise leave the whole app unable to start; the query is decoded once, by URLSearchParams.
 */
export function parseHash(hash) {
  const raw = String(hash || "").replace(/^#/, "") || "/";
  const cut = raw.indexOf("?");
  const pathPart = attempt(decodeURI, cut < 0 ? raw : raw.slice(0, cut));
  const query = {};
  new URLSearchParams(cut < 0 ? "" : raw.slice(cut + 1)).forEach((v, k) => { query[k] = v; });
  return { path: pathPart.startsWith("/") ? pathPart : "/" + pathPart, query };
}

const parse = () => parseHash(window.location.hash);

export function href(path, query) {
  const entries = Object.entries(query || {}).filter(([, v]) => v !== undefined && v !== null && v !== "");
  const qs = entries.length ? "?" + entries.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&") : "";
  return "#" + path + qs;
}

export function navigate(path, query, { replace = false } = {}) {
  const target = href(path, query);
  if (replace) window.history.replaceState(null, "", target);
  else window.location.hash = target.slice(1);
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}

export function setQuery(patch, { replace = true } = {}) {
  const { path, query } = parse();
  const next = { ...query, ...patch };
  for (const k of Object.keys(next)) if (next[k] === null || next[k] === undefined || next[k] === "") delete next[k];
  navigate(path, next, { replace });
}

export function compile(routes) {
  return routes.map((r) => {
    const keys = [];
    const pattern = new RegExp("^" + r.path.replace(/:([a-zA-Z_]+)/g, (_, k) => { keys.push(k); return "([^/]+)"; }) + "/?$");
    return { ...r, pattern, keys };
  });
}

export function match(compiled, path) {
  for (const r of compiled) {
    const m = r.pattern.exec(path);
    if (m) {
      const params = {};
      r.keys.forEach((k, i) => { params[k] = attempt(decodeURIComponent, m[i + 1]); });
      return { route: r, params };
    }
  }
  return null;
}

export function useLocation() {
  const [loc, setLoc] = useState(parse);
  useEffect(() => {
    const on = () => setLoc(parse());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return loc;
}
