// Deep analytics for one match: every player who played, side by side in one table, with every metric of the Scout table worked out for this match alone.
import { html, useMemo, useState } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useMeta } from "../lib/scope.js";
import { cls, plural } from "../lib/format.js";
import { blank, fmtMetric } from "../lib/metricfmt.js";
import { sortRows, quantile } from "../lib/filters.js";
import { MINUTE_CHOICES, extremes, filterPlayers } from "../lib/matchplayers.js";
import { Async, Notice, Segmented, Select, EmptyState, SearchBox, Button, playerHref } from "./common.js";
import { CsvButton, DataTable } from "./table.js";
import { MetricCell } from "./cells.js";
import { ColumnPicker } from "./explore/ColumnPicker.js";
import { MetricSelect } from "./explore/MetricSelect.js";
import { buildContext, bandsFor, resolveColumns } from "./explore/model.js";
import { metricColumns, pinnedSort, csvColumns, sortLabel, directionWords } from "./explore/Results.js";

// Open on the players who are ranked (30+ minutes): a rate from a few minutes tops any list sorted by it. "Everyone" is one choice away and the count says how many are out.
const RANKED_FROM = 30;
const OPEN = { side: "both", role: "all", minutes: 0, started: false, search: "" };
const ROLES = [{ value: "all", label: "All roles" }, { value: "ATT", label: "Attackers" }, { value: "MID", label: "Midfielders" }, { value: "DEF", label: "Defenders" }, { value: "GK", label: "Goalkeepers" }];

/** Leader, middle and last on the metric the table is sorted by, among the players shown. */
function Standouts({ rows, ctx, sort }) {
  const def = ctx.metrics[sort.key];
  if (!def || ctx.idx[sort.key] === undefined) return null;
  const i = ctx.idx[sort.key];
  const have = rows.filter((r) => !blank(r.v[i])).sort((a, b) => a.v[i] - b.v[i]);
  if (have.length < 2) return null;
  const good = def.hib === false ? have[0] : have[have.length - 1], bad = def.hib === false ? have[have.length - 1] : have[0];
  const f = (v) => fmtMetric(def, v);
  const tile = (label, r) => html`<div class="is-tile"><span class="label">${label}</span><b class="figure">${f(r.v[i])}</b><span class="xsmall muted truncate">${r.name} · ${r.team}</span></div>`;
  return html`<div class="insight-strip"><div class="is-tiles">
    ${tile(def.hib === null ? "Highest" : "Best", good)}
    <div class="is-tile"><span class="label">Median of ${have.length}</span><b class="figure">${f(quantile(have.map((r) => r.v[i]), 0.5))}</b><span class="xsmall muted">${def.label}</span></div>
    ${tile(def.hib === null ? "Lowest" : "Weakest", bad)}
  </div></div>`;
}

function Table({ d, f, catalog, scope }) {
  const ctx = useMemo(() => ({ ...buildContext("player", { keys: d.keys, scope: { group_sizes: d.group_sizes }, coverage: { event_players: d.coverage.events } }, catalog),
    pctWhat: (r) => `Percentile vs this season's ${(catalog.roles?.plural?.[r.group] || "peers").toLowerCase()}` }), [d, catalog]);
  const [flt, setFlt] = useState({ ...OPEN, minutes: RANKED_FROM });
  const [colsValue, setCols] = useState(null);
  const [sort, setSort] = useState({ key: ctx.idx.xg_xa90 !== undefined ? "xg_xa90" : "minutes", dir: "desc" });
  const columns = useMemo(() => resolveColumns(colsValue || "overview", ctx), [colsValue, ctx]);
  const rows = useMemo(() => d.rows.map((r) => ({ ...r, league: scope.league, seasons: [scope.season] })), [d.rows, scope]);
  const filtered = useMemo(() => filterPlayers(rows, flt), [rows, flt]);
  const sorted = useMemo(() => sortRows(filtered, sort, ctx), [filtered, sort, ctx]);
  const lead = useMemo(() => extremes(filtered, columns.keys, ctx), [filtered, columns.keys, ctx]);
  const model = { ctx, columns, setView: (p) => setCols("cols" in p ? p.cols : colsValue), setColumns: (keys) => setCols(`x:${keys.filter((k) => ctx.idx[k] !== undefined).join(",")}`) };

  const tableColumns = useMemo(() => {
    const { bands, keys } = bandsFor(columns.keys.filter((k) => k !== "minutes"), ctx);
    const bandOf = Object.fromEntries(bands.map((b) => [b.group, b.label]));
    const metric = metricColumns(keys, ctx, bandOf).map((c) => ({
      ...c, render: (r) => {
        const mark = lead[c.key]?.best.has(r.id) ? "mx-best" : lead[c.key]?.worst.has(r.id) ? "mx-worst" : null;
        return mark ? html`<span class=${mark} title=${mark === "mx-best" ? "Best in this match among the players shown" : "Weakest in this match among the players shown"}><${MetricCell} row=${r} ctx=${ctx} k=${c.key} /></span>` : html`<${MetricCell} row=${r} ctx=${ctx} k=${c.key} />`;
      },
    }));
    return [
      { key: "name", label: "Player", sticky: true, firstDir: "asc", width: "min(230px, 52vw)", band: "", value: (r) => r.name, csvValue: (r) => r.name,
        render: (r) => html`<div class="pcell"><i class="deep-side" style=${{ background: r.side === "h" ? "var(--c1)" : "var(--c2)" }} title=${r.team}></i>
          <a class="cell-player" href=${playerHref(r.id, { league: scope.league, season: scope.season })}><span class="name">${r.name}</span><span class="sub">${[r.team === f.home ? f.home_short : f.away_short, ctx.positions?.labels?.[r.pos2] || r.pos2, r.started ? null : "Sub"].filter(Boolean).join(" · ")}</span></a></div>` },
      { key: "minutes", label: "Min", num: true, band: "", title: "Minutes played in this match.", value: (r) => r.minutes, render: (r) => html`<span class=${cls("num", !r.in_pool && "muted")}>${r.minutes}</span>` },
      ...pinnedSort({ ctx, view: { sort: sort.key }, columns }, bandOf),
      ...metric,
    ];
  }, [columns, sort.key, ctx, lead, scope, f]);

  const set = (patch) => setFlt((s) => ({ ...s, ...patch }));
  const clear = JSON.stringify(flt) !== JSON.stringify(OPEN);
  const sortKeyChoices = [{ value: "name", label: "Name (A–Z)" }];
  const onSort = (s) => setSort(s);
  const sortBy = (k) => setSort({ key: k, dir: k === "name" ? "asc" : ctx.metrics[k]?.hib === false ? "asc" : "desc" });
  const thin = filtered.filter((r) => !r.in_pool).length;

  return html`<div class="card results-card">
    <div class="deep-controls">
      <${Segmented} small label="Team" value=${flt.side} onChange=${(v) => set({ side: v })} options=${[{ value: "both", label: "Both teams" }, { value: "h", label: f.home_short }, { value: "a", label: f.away_short }]} />
      <label class="rb-field"><span class="rb-label">Played</span><${Select} compact value=${String(flt.minutes)} label="Minutes played" options=${MINUTE_CHOICES} onChange=${(v) => set({ minutes: Number(v) })} /></label>
      <label class="rb-field"><span class="rb-label">Role</span><${Select} compact value=${flt.role} label="Role" options=${ROLES} onChange=${(v) => set({ role: v })} /></label>
      <label class="rb-field"><input type="checkbox" checked=${flt.started} onChange=${(e) => set({ started: e.target.checked })} /><span class="small">Starters only</span></label>
      <div class="grow"><${SearchBox} value=${flt.search} onInput=${(v) => set({ search: v })} placeholder="Find a player" /></div>
      ${clear ? html`<${Button} kind="quiet" size="sm" onClick=${() => setFlt(OPEN)}>Clear filters</${Button}>` : null}
    </div>
    <div class="results-bar">
      <div class="stack" style=${{ "--gap": "2px" }}>
        <b class="rb-title">${plural(sorted.length, "player")}${sorted.length !== d.rows.length ? html` <span class="muted rb-of">of ${d.rows.length}</span>` : ""}</b>
        <span class="muted small">By ${sortLabel(sort.key, ctx)}, ${directionWords(sort.key, sort.dir, ctx)}. Click any column heading to re-sort.</span>
      </div>
      <div class="rb-controls">
        <label class="rb-field"><span class="rb-label">Sort by</span>
          <${MetricSelect} ctx=${ctx} compact value=${sort.key} label="Sort by" extra=${sortKeyChoices} onChange=${sortBy} />
          <button type="button" class="btn sm icon-only" aria-label="Reverse the order" title="Reverse the order" onClick=${() => setSort({ ...sort, dir: sort.dir === "asc" ? "desc" : "asc" })}>${sort.dir === "asc" ? "↑" : "↓"}</button>
        </label>
        <${ColumnPicker} model=${model} />
        <${CsvButton} columns=${csvColumns(tableColumns)} rows=${sorted} filename=${`prem-lab-match-${f.home_short}-${f.away_short}.csv`} />
      </div>
    </div>
    <div class="results-notes" style=${{ display: "flex", flexWrap: "wrap", gap: "6px 18px", padding: "8px 18px", alignItems: "center" }}>
      <span class="deep-key xsmall muted"><span><i class="b"></i>Best in this match</span><span><i class="w"></i>Weakest</span><span>among the players shown; marks follow the filters</span></span>
    </div>
    ${sorted.length
      ? html`<${Standouts} rows=${sorted} ctx=${ctx} sort=${sort} />
        <${DataTable} columns=${tableColumns} rows=${sorted} rowKey=${(r) => r.id} tight presorted maxHeight="min(78vh, 920px)" sort=${sort} onSort=${onSort} caption="Players in this match" />`
      : html`<${EmptyState} title="No players match these filters" text="Widen the playing time, or clear the filters." action=${html`<${Button} onClick=${() => setFlt(OPEN)}>Clear filters</${Button}>`} />`}
    <div class="results-notes" style=${{ padding: "10px 18px 14px" }}>
      <${Notice} icon="info">Every number is for this match alone, from its shots, the line-ups${d.coverage.events ? " and the event data" : ""}. The bar under a rate shows where it would sit among this season's players in the same role who have played enough; counts have no bar, and players under 30 minutes are not ranked${thin ? ` (${thin} here)` : ""}. One match is a small sample: read a single rate with care.${d.coverage.events ? "" : " No event data is stored for this match, so tackles, passes, carries and duels are not shown."}</${Notice}>
    </div>
  </div>`;
}

export function MatchDeep({ id, scope, f, live = false }) {
  const { catalog } = useMeta();
  // a match drawn from a WhoScored read: its own cache key, asked again every minute, never kept in the browser's store (see MatchPage)
  const q = useApi(`/api/match/${id}/players`, live ? { league: scope.league, season: scope.season, live: 1 } : { league: scope.league, season: scope.season },
    live ? { staleMs: 0, persist: false, pollMs: 60000 } : undefined);
  return html`<${Async} q=${q}>${(d) => (catalog ? html`<${Table} d=${d} f=${f} catalog=${catalog} scope=${scope} />` : null)}</${Async}>`;
}
