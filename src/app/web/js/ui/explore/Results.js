// The results area shared by Scout and Teams: the control bar (sort, top N, columns, view), a short read of the ranking, and the table.
import { html, useMemo } from "../../lib/html.js";
import { navigate } from "../../lib/router.js";
import { cls, plural } from "../../lib/format.js";
import { blank, fmtMetric, fmtPct } from "../../lib/metricfmt.js";
import { TOP_CHOICES, finiteValues, histogram, quantile, sortValue } from "../../lib/filters.js";
import { Segmented, Select } from "../common.js";
import { CsvButton, DataTable } from "../table.js";
import { Distribution } from "../../charts/distribution.js";
import { FormCell, MetricCell, PlayerCell, TagCell, TeamCell } from "../cells.js";
import { ColumnPicker } from "./ColumnPicker.js";
import { MetricSelect } from "./MetricSelect.js";
import { bandsFor } from "./model.js";

const NAME_SORTS = { player: [{ value: "name", label: "Name (A–Z)" }], team: [{ value: "rank", label: "League position" }, { value: "name", label: "Name (A–Z)" }] };

export function sortLabel(key, ctx) {
  if (key === "name") return "name";
  if (key === "rank") return "league position";
  return ctx.metrics[key]?.label || key;
}

export function directionWords(key, dir, ctx) {
  if (key === "name") return dir === "asc" ? "A to Z" : "Z to A";
  if (key === "rank") return dir === "asc" ? "best first" : "worst first";
  const hib = ctx.metrics[key]?.hib;
  if (hib === false) return dir === "asc" ? "best (lowest) first" : "worst (highest) first";
  return dir === "asc" ? "lowest first" : "highest first";
}

// ------------------------------------------------------------------ the bar

export function ResultsBar({ model, level, noun, csv, hideColumns }) {
  const { ctx, view, sorted, shown, setView } = model;
  const capped = view.top > 0 && sorted.length > view.top;
  const sortKey = view.sort;
  const choices = [...new Set([...TOP_CHOICES, ...(view.top > 0 ? [view.top] : [])])].sort((a, b) => a - b);
  const topOptions = [{ value: "0", label: `All ${sorted.length.toLocaleString("en-GB")}` }, ...choices.map((n) => ({ value: String(n), label: `Top ${n}` }))];
  return html`<div class="results-bar">
    <div class="stack" style=${{ "--gap": "2px" }}>
      <b class="rb-title">${capped ? `Top ${shown.length}` : plural(sorted.length, noun.replace(/s$/, ""), noun)}${capped ? html` <span class="muted rb-of">of ${sorted.length.toLocaleString("en-GB")}</span>` : ""}</b>
      <span class="muted small">${sortKey ? `By ${sortLabel(sortKey, ctx)}, ${directionWords(sortKey, view.dir, ctx)}. Click any column heading to re-sort.` : ""}</span>
    </div>
    <div class="rb-controls">
      <label class="rb-field"><span class="rb-label">Sort by</span>
        <${MetricSelect} ctx=${ctx} compact value=${sortKey} label="Sort by" extra=${NAME_SORTS[level]} onChange=${(k) => setView({ sort: k, dir: k === "name" || k === "rank" ? "asc" : ctx.metrics[k]?.hib === false ? "asc" : "desc" })} />
        <button type="button" class="btn sm icon-only" title=${view.dir === "asc" ? "Showing lowest first: switch to highest first" : "Showing highest first: switch to lowest first"} aria-label="Reverse the order" onClick=${() => setView({ dir: view.dir === "asc" ? "desc" : "asc" })}>${view.dir === "asc" ? "↑" : "↓"}</button>
      </label>
      <label class="rb-field"><span class="rb-label">Show</span>
        <${Select} compact value=${String(view.top)} label="How many to show" options=${topOptions} onChange=${(v) => setView({ top: Number(v) })} />
      </label>
      ${hideColumns || view.view === "map" ? null : html`<${ColumnPicker} model=${model} />`}
      <${Segmented} small label="View" options=${[{ value: "table", label: "Table" }, { value: "map", label: "Map" }]} value=${view.view} onChange=${(v) => setView({ view: v })} />
      ${csv ? html`<${CsvButton} columns=${csv.columns} rows=${shown} filename=${csv.filename} />` : null}
    </div>
  </div>`;
}

// ------------------------------------------------------------------ a read of the ranking

/** Leader, typical value and the cut for the top group, beside a histogram: what the sorted list looks like at a glance. */
export function InsightStrip({ model, noun }) {
  const { ctx, view, filtered, sorted } = model;
  const key = view.sort;
  const def = ctx.metrics[key];
  const read = useMemo(() => {
    if (!def) return null;
    const values = finiteValues(filtered, key, ctx);
    if (values.length < 5) return null;
    const hist = histogram(values, 28);
    if (!hist) return null;
    const asc = view.dir === "asc";
    const cut = view.top > 0 && sorted.length > view.top ? sortValue(sorted[view.top - 1], key, ctx) : quantile(hist.sorted, asc ? 0.1 : 0.9);
    const leader = sorted.find((r) => !blank(sortValue(r, key, ctx)));
    return { hist, cut, leader, unknown: filtered.length - values.length, asc, capped: view.top > 0 && sorted.length > view.top, n: values.length };
  }, [filtered, sorted, key, view.dir, view.top, ctx, def]);
  if (!read) return null;
  const f = (v) => fmtMetric(def, v);
  const p = read.leader ? read.leader.p[ctx.idx[key]] : null;
  return html`<div class="insight-strip">
    <div class="is-tiles">
      <div class="is-tile"><span class="label">Leader</span><b class="figure">${f(sortValue(read.leader, key, ctx))}</b><span class="xsmall muted truncate">${read.leader.name ?? read.leader.team}${p != null ? ` · ${fmtPct(p)}th percentile` : ""}</span></div>
      <div class="is-tile"><span class="label">Median of ${read.n.toLocaleString("en-GB")}</span><b class="figure">${f(read.hist.median)}</b><span class="xsmall muted">${def.label}</span></div>
      <div class="is-tile"><span class="label">${read.capped ? `Cut for the top ${view.top}` : read.asc ? "Lowest 10% end at" : "Top 10% starts at"}</span><b class="figure">${f(read.cut)}</b><span class="xsmall muted">${read.unknown ? `${read.unknown.toLocaleString("en-GB")} ${noun} have no value (shown last)` : "everyone has a value"}</span></div>
    </div>
    <div class="is-chart"><${Distribution} hist=${read.hist} format=${f} label=${`Distribution of ${def.label}`} unit=${noun}
      keep=${read.asc ? { from: null, to: read.cut } : { from: read.cut, to: null }} /></div>
  </div>`;
}

// ------------------------------------------------------------------ columns and the table

export function metricColumns(keys, ctx, bandOf) {
  return keys.map((k) => {
    const def = ctx.metrics[k];
    const i = ctx.idx[k];
    return {
      key: k, label: def.short, fullLabel: def.label, num: true, band: bandOf[def.group], title: `${def.what}${def.read ? ` ${def.read}` : ""}`,
      value: (r) => r.v[i], csvLabel: def.label, render: (r) => html`<${MetricCell} row=${r} ctx=${ctx} k=${k} />`,
    };
  });
}

/** The metric the list is sorted by, as an extra column right after the fixed ones when it is not already shown. */
export function pinnedSort(model, bandOf) {
  const { ctx, view, columns } = model;
  const key = view.sort;
  const def = ctx.metrics[key];
  if (!def || key === "minutes" || columns.keys.includes(key) || ctx.idx[key] === undefined) return [];
  return metricColumns([key], ctx, { [def.group]: "Sorted by" });
}

export function playerColumns(model, { scope, picks, onPick }) {
  const { ctx, columns, filters, patchFilters } = model;
  const { bands, keys } = bandsFor(columns.keys.filter((k) => k !== "minutes"), ctx);
  const bandOf = Object.fromEntries(bands.map((b) => [b.group, b.label]));
  const minutesIdx = ctx.idx.minutes;
  return [
    { key: "name", label: "Player", sticky: true, firstDir: "asc", width: "min(250px, 52vw)", band: "", value: (r) => r.name,
      render: (r) => html`<${PlayerCell} row=${r} ctx=${ctx} season=${scope.season} picked=${picks.has(r.id)} onPick=${onPick} />`, csvValue: (r) => r.name },
    { key: "tags", label: "Profile", sortable: false, band: "", csv: false, className: "col-profile", headClass: "col-profile", title: "Labels earned by simple rules on percentiles. Click a label to filter by it.",
      render: (r) => html`<${TagCell} row=${r} active=${filters.tags} onTag=${(t) => patchFilters({ tags: filters.tags.includes(t) ? filters.tags.filter((x) => x !== t) : [...filters.tags, t] })} />` },
    ...(minutesIdx !== undefined ? [{ key: "minutes", label: "Min", num: true, band: "", title: "League minutes played: the sample behind every rate.", value: (r) => r.v[minutesIdx],
      render: (r) => html`<span class=${cls("num", r.in_pool === false && "muted")}>${blank(r.v[minutesIdx]) ? "–" : Math.round(r.v[minutesIdx]).toLocaleString("en-GB")}</span>` }] : []),
    ...pinnedSort(model, bandOf),
    ...metricColumns(keys, ctx, bandOf),
  ];
}

export function teamColumns(model) {
  const { ctx, columns } = model;
  const { bands, keys } = bandsFor(columns.keys, ctx);
  const bandOf = Object.fromEntries(bands.map((b) => [b.group, b.label]));
  return [
    { key: "rank", label: "#", num: true, width: "48px", firstDir: "asc", band: "", title: "Position in that league and season's table.", value: (r) => r.rank, render: (r) => html`<span class="rank">${r.rank ?? "–"}</span>` },
    { key: "name", label: "Team", sticky: true, firstDir: "asc", width: "min(230px, 46vw)", band: "", value: (r) => r.team,
      render: (r) => html`<${TeamCell} row=${r} sub=${`${r.league}${r.season ? ` ${r.season}/${String(r.season + 1).slice(-2)}` : ""}`} />`, csvValue: (r) => r.team },
    { key: "form", label: "Form", sortable: false, band: "", csv: false, className: "col-form", headClass: "col-form", title: "Last five results, oldest to newest.", render: (r) => html`<${FormCell} items=${r.form} />` },
    ...pinnedSort(model, bandOf),
    ...metricColumns(keys, ctx, bandOf),
  ];
}

export function ResultsTable({ model, columns, rowKey, onOpen, maxHeight = "min(78vh, 920px)" }) {
  const { view, shown, setView } = model;
  return html`<${DataTable} columns=${columns} rows=${shown} rowKey=${rowKey} pageSize=${50} tight presorted maxHeight=${maxHeight}
    sort=${view.sort ? { key: view.sort, dir: view.dir } : null}
    onSort=${(s) => setView({ sort: s.key, dir: s.dir })}
    onRowClick=${onOpen} caption="Results" />`;
}

export function csvColumns(columns) {
  return columns.filter((c) => c.csv !== false).map((c) => ({ label: c.csvLabel || c.label, value: c.csvValue || c.value }));
}

export function openPlayer(row, scope) {
  navigate(`/player/${row.id}`, { league: row.league, season: row.seasons?.length === 1 ? row.seasons[0] : scope.season });
}

export function openTeam(row) {
  navigate(`/team/${encodeURIComponent(row.team)}`, { league: row.league, season: row.season });
}
