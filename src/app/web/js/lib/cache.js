// A persistent copy of what the app has already loaded, kept in this browser (IndexedDB).
//
// The server answers from the local database and tells the browser when a response is unchanged (ETag), so a repeat request is cheap.
// This layer makes the first paint cheaper still: when a page asks for something it has seen before, the last copy is shown at once while
// the fresh answer is fetched, then swapped in if it differs ("stale while revalidate"). It is only a cache: if IndexedDB is missing or
// blocked (a private window, a policy), every call quietly does nothing and the app works exactly as before.

const DB_NAME = "prem-lab";
const STORE = "api";
const VERSION = 1;
const MAX_ENTRIES = 80;                 // oldest entries are dropped beyond this
const MAX_BYTES = 12 * 1024 * 1024;     // an entry bigger than this (as JSON) is not stored
export const CACHE_FORMAT = 4;          // bump when the shape of stored entries changes: older ones are ignored

// An answer is only worth showing from a stored copy if the same version of the app wrote it: a new release can change what an endpoint
// returns, and a page built for the new shape must never be handed the old one. The version is asked of the server once; if it cannot
// be learned, nothing is read from or written to the store.
let versionPromise = null;
function appVersion() {
  if (!versionPromise) {
    versionPromise = fetch("/api/health", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => String(j?.version || ""))
      .catch(() => "")
      .then((v) => { if (v) forgetOtherVersions(v); return v; });
  }
  return versionPromise;
}

let opening = null;

function open() {
  if (!opening) {
    opening = new Promise((resolve) => {
      try {
        if (typeof indexedDB === "undefined") return resolve(null);
        const req = indexedDB.open(DB_NAME, VERSION);
        req.onupgradeneeded = () => { req.result.createObjectStore(STORE); };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => resolve(null);
        req.onblocked = () => resolve(null);
      } catch (_) { resolve(null); }
    });
  }
  return opening;
}

function run(mode, work) {
  return open().then((db) => new Promise((resolve) => {
    if (!db) return resolve(undefined);
    try {
      const tx = db.transaction(STORE, mode);
      const store = tx.objectStore(STORE);
      const result = work(store);
      tx.oncomplete = () => resolve(result && "result" in result ? result.result : undefined);
      tx.onerror = () => resolve(undefined);
      tx.onabort = () => resolve(undefined);
    } catch (_) { resolve(undefined); }
  }));
}

/** The stored entry { data, at } for a key, or undefined. */
export async function persistedGet(key) {
  const app = await appVersion();
  if (!app) return undefined;
  const entry = await run("readonly", (s) => s.get(key));
  return entry && entry.format === CACHE_FORMAT && entry.app === app ? entry : undefined;
}

export async function persistedSet(key, data) {
  let size = 0;
  try { size = JSON.stringify(data).length; } catch (_) { return; }
  if (size > MAX_BYTES) return;
  const app = await appVersion();
  if (!app) return;
  await run("readwrite", (s) => s.put({ format: CACHE_FORMAT, app, data, at: Date.now(), size }, key));
  trim();
}

/** Drop whatever another version of the app (or an older storage format) left behind. */
async function forgetOtherVersions(app) {
  await run("readwrite", (s) => {
    const req = s.openCursor();
    req.onsuccess = () => {
      const cursor = req.result;
      if (!cursor) return;
      if (cursor.value?.app !== app || cursor.value?.format !== CACHE_FORMAT) cursor.delete();
      cursor.continue();
    };
    return null;
  });
}

/** Forget every stored entry whose key starts with `prefix` (all of them without one). */
export async function persistedDelete(prefix = "") {
  await run("readwrite", (s) => {
    const req = s.openCursor();
    req.onsuccess = () => {
      const cursor = req.result;
      if (!cursor) return;
      if (!prefix || String(cursor.key).startsWith(prefix)) cursor.delete();
      cursor.continue();
    };
    return null;
  });
}

let trimming = false;
async function trim() {
  if (trimming) return;
  trimming = true;
  try {
    await run("readwrite", (s) => {
      const all = [];
      const req = s.openCursor();
      req.onsuccess = () => {
        const cursor = req.result;
        if (cursor) { all.push({ key: cursor.key, at: cursor.value.at || 0 }); cursor.continue(); return; }
        all.sort((a, b) => b.at - a.at).slice(MAX_ENTRIES).forEach((e) => s.delete(e.key));
      };
      return null;
    });
  } finally { trimming = false; }
}
