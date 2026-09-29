// Hash router. The URL is the source of truth for page state, so views are linkable.
import { useEffect, useState } from "./html.js";

function parse() {
  const raw = decodeURI(window.location.hash.slice(1) || "/");
  const [pathPart, qs = ""] = raw.split("?");
  const path = pathPart.startsWith("/") ? pathPart : "/" + pathPart;
  const query = {};
  new URLSearchParams(qs).forEach((v, k) => { query[k] = v; });
  return { path, query };
}

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
      r.keys.forEach((k, i) => { params[k] = decodeURIComponent(m[i + 1]); });
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
