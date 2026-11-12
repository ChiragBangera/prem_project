// The explorer model: everything Scout and Teams share. It reads the dataset and the catalog, keeps filters, sorting and columns in the URL
// (so a view is a link), and hands the page the rows to draw. No drawing happens here.
import { useCallback, useMemo, useState } from "../../lib/html.js";
import { navigate, setQuery as writeAddress } from "../../lib/router.js";
import { ui } from "../../lib/store.js";
import {
  applyFilters, activeChips, emptyFilters, makeIndex, parseCols, sortRows, stateFromQuery, stateToQuery, takeTop, viewFromQuery, viewToQuery, customCols, isFiltered,
} from "../../lib/filters.js";
import { fmtMetric } from "../../lib/metricfmt.js";
import { formation } from "../../lib/format.js";

/** What the filter and sort functions need to read a dataset. Built once per payload. */
export function buildContext(level, payload, catalog) {
  const cat = catalog[level];
  const tags = {};
  (cat.tags || []).forEach((t) => { tags[t.key] = t; });
  return {
    level,
    idx: makeIndex(payload.keys),
    keys: payload.keys,
    metrics: cat.metrics,
    order: cat.order.filter((k) => payload.keys.includes(k)),
    groups: cat.groups,
    views: cat.views,
    lensList: cat.lenses,
    lenses: Object.fromEntries(cat.lenses.map((l) => [l.key, l])),
    tags,
    tagList: cat.tags || [],
    roles: catalog.roles,
    positions: catalog.positions,
    groupSizes: payload.scope?.group_sizes || {},
    coverage: payload.coverage || {},
  };
}

const DEFAULTS = {
  player: { sort: "output", dir: "desc", cols: "overview", mx: "xa90", my: "npxg90", mc: "role", ms: "minutes" },
  team: { sort: "rank", dir: "asc", cols: "overview", mx: "xg_pg", my: "xga_pg", mc: "league", ms: "none" },
};

/**
 * The sort key to use when the URL names none: the broadest score that most rows actually have. The all-data score (it includes the event
 * metrics) when nearly everyone has one, else the role score, which exists for every outfield player whatever data has been fetched.
 */
export function defaultSort(level, ctx, rows) {
  if (level === "team") return "rank";
  const have = (key) => { const i = ctx.idx[key]; return i === undefined ? 0 : rows.reduce((n, r) => n + (r.v[i] != null ? 1 : 0), 0); };
  return have("score_full") >= 0.85 * have("output") && have("score_full") > 0 ? "score_full" : "output";
}

export function labelsFor(ctx) {
  return {
    role: (r) => ctx.roles?.plural?.[r] || r,
    position: (p) => ctx.positions?.labels?.[p] || p,
    tag: (t) => ctx.tags[t]?.label || t,
    lens: (k) => ctx.lenses[k]?.label || k,
    formation: (f) => formation(f) || f,
    fmt: fmtMetric,
  };
}

/** The metric keys a `cols` value shows, with a name for it. */
export function resolveColumns(colsValue, ctx) {
  const { preset, custom } = parseCols(colsValue);
  if (custom) {
    const keys = custom.filter((k) => ctx.idx[k] !== undefined && ctx.metrics[k]);
    return { keys, name: "Custom", preset: null, custom: true };
  }
  const view = ctx.views.find((v) => v.key === (preset || "overview")) || ctx.views[0];
  return { keys: view.metrics.filter((k) => ctx.idx[k] !== undefined), name: view.label, preset: view.key, custom: false, blurb: view.blurb };
}

/**
 * The state is read from `query` and written with `write(patch)` (keys set to null are removed). Both default to the page's address, so a view
 * is a link; a table inside a page whose address already means something else (a match's tabs) passes its own pair from `useLocalQuery`.
 * `overrides` replaces some of the level's defaults (the sort a match table opens on, for one).
 */
export function useExplorer({ level, payload, catalog, query, write = writeAddress, overrides = null, extend = null }) {
  const ctx = useMemo(() => { const c = buildContext(level, payload, catalog); return extend ? { ...c, ...extend } : c; }, [level, payload, catalog, extend]);
  const defaults = useMemo(() => ({ ...DEFAULTS[level], sort: defaultSort(level, ctx, payload.rows), ...(overrides || {}) }), [level, ctx, payload.rows, overrides]);
  const setQuery = write;
  const queryKey = JSON.stringify(query);
  const filters = useMemo(() => stateFromQuery(query, ctx), [queryKey, ctx]);
  const view = useMemo(() => viewFromQuery(query, defaults), [queryKey, defaults]);
  const rows = payload.rows;
  const filtered = useMemo(() => applyFilters(rows, filters, ctx), [rows, filters, ctx]);
  const sorted = useMemo(() => sortRows(filtered, { key: view.sort, dir: view.dir }, ctx), [filtered, view.sort, view.dir, ctx]);
  const shown = useMemo(() => takeTop(sorted, view.top), [sorted, view.top]);
  const columns = useMemo(() => resolveColumns(view.cols || defaults.cols, ctx), [view.cols, defaults.cols, ctx]);
  const labels = useMemo(() => labelsFor(ctx), [ctx]);
  const chips = useMemo(() => activeChips(filters, ctx, labels), [filters, ctx, labels]);

  const setFilters = useCallback((next) => {
    const state = typeof next === "function" ? next(filters) : next;
    setQuery(stateToQuery(state));
  }, [filters, setQuery]);
  const patchFilters = useCallback((patch) => setFilters((s) => ({ ...s, ...patch })), [setFilters]);
  const clearFilters = useCallback(() => setQuery(stateToQuery(emptyFilters())), [setQuery]);
  const setView = useCallback((patch) => setQuery(viewToQuery({ ...view, ...patch }, defaults)), [view, defaults, setQuery]);

  /** Show exactly these metrics as columns (saved, so the picker opens on them next time). */
  const setColumns = useCallback((keys) => {
    const clean = keys.filter((k) => ctx.idx[k] !== undefined);
    ui.set((s) => ({ customCols: { ...(s.customCols || {}), [level]: clean } }));
    setView({ cols: customCols(clean) });
  }, [ctx, level, setView]);

  return { ctx, defaults, filters, view, filtered, sorted, shown, columns, labels, chips, isFiltered: isFiltered(filters), setFilters, patchFilters, clearFilters, setView, setColumns, query, write: setQuery };
}

/** A query kept in the component instead of the address: `[query, write]` for useExplorer, starting from `initial`. */
export function useLocalQuery(initial = {}) {
  const [query, setLocal] = useState(initial);
  const write = useCallback((patch) => setLocal((q) => {
    const next = { ...q };
    for (const [k, v] of Object.entries(patch)) { if (v == null || v === "") delete next[k]; else next[k] = String(v); }
    return next;
  }), []);
  return [query, write];
}

/** The order a list is in, in words: "highest first", "best (lowest) first", "A to Z". */
export function directionWords(key, dir, ctx) {
  if (key === "name") return dir === "asc" ? "A to Z" : "Z to A";
  if (key === "rank") return dir === "asc" ? "best first" : "worst first";
  const hib = ctx.metrics[key]?.hib;
  if (hib === false) return dir === "asc" ? "best (lowest) first" : "worst (highest) first";
  return dir === "asc" ? "lowest first" : "highest first";
}

/** A label as it reads inside a sentence: an ordinary first word is lowered ("tackles per 90"), a name or an abbreviation is kept ("xG per game", "PPDA"). */
export const inSentence = (label) => (/^[A-Z][a-z]/.test(label) ? label[0].toLowerCase() + label.slice(1) : label);

/** "Sorted by xG per game, highest first." for the foot of a table; empty when the sort is not one it can name. */
export function sortSentence(view, ctx) {
  const { sort, dir } = view;
  if (sort === "rank") return `Sorted by league position, ${directionWords("rank", dir, ctx)}.`;
  if (sort === "name") return `Sorted by name, ${directionWords("name", dir, ctx)}.`;
  const def = ctx.metrics[sort];
  return def ? `Sorted by ${inSentence(def.label)}, ${directionWords(sort, dir, ctx)}.` : "";
}

export function openPlayer(row, scope) {
  navigate(`/player/${row.id}`, { league: row.league, season: row.seasons?.length === 1 ? row.seasons[0] : scope.season });
}

export function openTeam(row) {
  navigate(`/team/${encodeURIComponent(row.team)}`, { league: row.league, season: row.season });
}
