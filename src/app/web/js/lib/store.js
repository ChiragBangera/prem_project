// A tiny observable store with optional localStorage persistence.
import { useEffect, useState } from "./html.js";

export function createStore(initial, persistKey) {
  let state = { ...initial };
  if (persistKey) {
    try {
      const saved = JSON.parse(localStorage.getItem(persistKey) || "null");
      if (saved && typeof saved === "object") state = { ...state, ...saved };
    } catch (_) { /* storage may be blocked; the app works without it */ }
  }
  const listeners = new Set();
  const store = {
    get: () => state,
    set(patch) {
      const next = { ...state, ...(typeof patch === "function" ? patch(state) : patch) };
      if (Object.keys(next).every((k) => Object.is(next[k], state[k]))) return;
      state = next;
      if (persistKey) {
        try { localStorage.setItem(persistKey, JSON.stringify(state)); } catch (_) { /* ignore */ }
      }
      listeners.forEach((l) => l(state));
    },
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
  };
  return store;
}

const shallow = (a, b) => {
  if (Object.is(a, b)) return true;
  if (typeof a !== "object" || typeof b !== "object" || !a || !b) return false;
  const ka = Object.keys(a);
  return ka.length === Object.keys(b).length && ka.every((k) => Object.is(a[k], b[k]));
};

export function useStore(store, selector = (s) => s) {
  const [value, setValue] = useState(() => selector(store.get()));
  useEffect(() => {
    const update = (s) => setValue((prev) => {
      const next = selector(s);
      return shallow(prev, next) ? prev : next;
    });
    update(store.get());
    return store.subscribe(update);
  }, [store]);
  return value;
}

// ---- app-wide stores ----
export const ui = createStore({ league: "EPL", season: "auto", theme: "system", recent: [] }, "prem.ui.v1");
export const metaStore = createStore({ meta: null, catalog: null, error: null });
export const pending = createStore({ n: 0 });
export const shortlistStore = createStore({ items: [], loaded: false });
export const favouritesStore = createStore({ teams: [], loaded: false });   // favourite teams: their matches are read at half time too
