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

// ------------------------------------------------------------------ history entries
//
// Every history entry carries a small state: an id, the scroll position and the league and season in effect when it was left. Back and Forward
// then return the user to the same place: the same tab (tabs add entries), the same league and season, and the same point down the page.

const KNOWN = "prem.history.ids";
const newId = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
let known;
let fresh = null;   // the entry this app has just pushed: the next location change is a new place, not a return to an old one
function knownIds() {
  if (!known) {
    try { known = new Set(JSON.parse(window.sessionStorage.getItem(KNOWN) || "[]")); } catch (_) { known = new Set(); }
  }
  return known;
}
function remember(id) {
  const ids = knownIds();
  ids.add(id);
  try { window.sessionStorage.setItem(KNOWN, JSON.stringify([...ids].slice(-400))); } catch (_) { /* private mode: only this tab's memory */ }
}

/** The state of the current history entry ({} for one the browser made from a plain link). */
export const entryState = () => window.history.state || {};

/** Merge fields into the current entry's state without making a new entry. */
export function stampEntry(fields) {
  window.history.replaceState({ ...entryState(), ...fields }, "");
}

/** Remember how far down the current page is, so coming Back to it lands there. */
export const rememberScroll = () => stampEntry({ y: Math.round(window.scrollY) });

/** A new entry for the address shown now (before the league or season changes, so Back restores them). */
export function pushEntry() {
  rememberScroll();
  const id = newId();
  remember(id);
  fresh = id;
  window.history.pushState({ id }, "", window.location.hash || "#/");
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}

/**
 * Go somewhere. A new history entry by default (Back returns here); `replace` changes the current entry instead, for changes that are not a
 * place of their own (a filter, a sort). The current entry keeps its scroll position either way.
 */
export function navigate(path, query, { replace = false } = {}) {
  const target = href(path, query);
  if (replace) window.history.replaceState(entryState(), "", target);
  else {
    rememberScroll();
    const id = newId();
    remember(id);
    fresh = id;
    window.history.pushState({ id }, "", target);
  }
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

/**
 * Which kind of move led to the address shown: "new" (a link, or navigate), "same" (the current entry changed in place) or "back" (Back or
 * Forward to an entry seen before, whose state says where the user was).
 */
function classify(lastId) {
  const state = entryState();
  if (!state.id) {
    const id = newId();
    remember(id);
    stampEntry({ id });
    return { kind: "new", id };
  }
  if (state.id === lastId) return { kind: "same", id: state.id };
  if (state.id === fresh) { fresh = null; return { kind: "new", id: state.id }; }
  const seen = knownIds().has(state.id);
  remember(state.id);
  return { kind: seen ? "back" : "new", id: state.id };
}

export function useLocation() {
  const [loc, setLoc] = useState(() => {
    if ("scrollRestoration" in window.history) window.history.scrollRestoration = "manual";   // the app restores it, once the page is drawn
    const { id } = classify(null);
    return { ...parse(), kind: "new", id };
  });
  useEffect(() => {
    let lastId = loc.id, lastHash = window.location.hash;
    // Back between two entries with the same address (a league switch made one) fires popstate but no hashchange; a different address fires
    // both, and the second must not undo what the first set up
    const on = () => {
      if (entryState().id === lastId && window.location.hash === lastHash) return;
      const { kind, id } = classify(lastId);
      lastId = id;
      lastHash = window.location.hash;
      setLoc({ ...parse(), kind, id });
    };
    window.addEventListener("hashchange", on);
    window.addEventListener("popstate", on);
    return () => { window.removeEventListener("hashchange", on); window.removeEventListener("popstate", on); };
  }, []);
  return loc;
}
