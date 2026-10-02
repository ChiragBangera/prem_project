// The explorer model: everything Scout and Teams share. It reads the dataset and the catalog, keeps filters, sorting and columns in the URL
// (so a view is a link), and hands the page the rows to draw. No drawing happens here.
import { useCallback, useMemo } from "../../lib/html.js";
import { setQuery } from "../../lib/router.js";
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

export function useExplorer({ level, payload, catalog, query }) {
  const ctx = useMemo(() => buildContext(level, payload, catalog), [level, payload, catalog]);
  const defaults = useMemo(() => ({ ...DEFAULTS[level], sort: defaultSort(level, ctx, payload.rows) }), [level, ctx, payload.rows]);
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
  }, [filters]);
  const patchFilters = useCallback((patch) => setFilters((s) => ({ ...s, ...patch })), [setFilters]);
  const clearFilters = useCallback(() => setQuery(stateToQuery(emptyFilters())), []);
  const setView = useCallback((patch) => setQuery(viewToQuery({ ...view, ...patch }, defaults)), [view, defaults]);

  /** Show exactly these metrics as columns (saved, so the picker opens on them next time). */
  const setColumns = useCallback((keys) => {
    const clean = keys.filter((k) => ctx.idx[k] !== undefined);
    ui.set((s) => ({ customCols: { ...(s.customCols || {}), [level]: clean } }));
    setView({ cols: customCols(clean) });
  }, [ctx, level, setView]);

  return { ctx, defaults, filters, view, filtered, sorted, shown, columns, labels, chips, isFiltered: isFiltered(filters), setFilters, patchFilters, clearFilters, setView, setColumns };
}

/** Group a list of metric keys by catalog group, in the catalog's order: the bands over the table's columns. */
export function bandsFor(keys, ctx) {
  const groupOrder = ctx.groups.map((g) => g.key);
  const label = Object.fromEntries(ctx.groups.map((g) => [g.key, g.label]));
  const withGroup = keys.map((k) => ({ key: k, group: ctx.metrics[k]?.group }));
  // keep the user's order within a band, and order the bands as the catalog does
  const order = [...new Set(withGroup.map((m) => m.group))].sort((a, b) => groupOrder.indexOf(a) - groupOrder.indexOf(b));
  const bands = order.map((g) => ({ group: g, label: label[g] || g, keys: withGroup.filter((m) => m.group === g).map((m) => m.key) }));
  return { bands, keys: bands.flatMap((b) => b.keys) };
}
