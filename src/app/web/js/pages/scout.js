// Scout: find players by what they do. Every player is listed until you narrow it down; every control is yours and nothing is pre-selected.
import { html, useEffect, useMemo } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useScope, useMeta, leagueName } from "../lib/scope.js";
import { href, navigate, useLocation } from "../lib/router.js";
import { plural } from "../lib/format.js";
import { Icon } from "../lib/icons.js";
import { Async, Button, DataNotices, EmptyState, Insights, Notice, PageHead, useDocumentTitle } from "../ui/common.js";
import { useExplorer } from "../ui/explore/model.js";
import { FilterBar } from "../ui/explore/FilterBar.js";
import { InsightStrip, ResultsBar, ResultsTable, csvColumns, openPlayer, playerColumns } from "../ui/explore/Results.js";
import { MetricMap } from "../ui/explore/MetricMap.js";
import { ScopePicker, scopeFromQuery } from "../ui/explore/Scope.js";

function CompareTray({ ids, rows, onChange }) {
  if (!ids.length) return null;
  const chosen = ids.map((id) => rows.find((r) => r.id === id)).filter(Boolean);
  return html`<div class="tray" role="region" aria-label="Comparison selection">
    <div class="tray-list">${chosen.map((r) => html`<span class="chip on" key=${r.id}>${r.name}<button type="button" aria-label=${`Remove ${r.name}`} onClick=${() => onChange(ids.filter((x) => x !== r.id))}><${Icon} name="x" /></button></span>`)}</div>
    <div class="row" style=${{ gap: "8px" }}>
      <${Button} kind="quiet" size="sm" onClick=${() => onChange([])}>Clear</${Button}>
      <${Button} kind="primary" size="sm" icon="compare" disabled=${ids.length < 2} onClick=${() => navigate("/compare", { ids: ids.join(",") })}>${ids.length < 2 ? "Pick one more" : `Compare ${ids.length}`}</${Button}>
    </div>
  </div>`;
}

/** Sorting a rate with no minutes limit puts a few-minute cameo at the top. Say so, once, with a one-click remedy: never apply it silently. */
function SmallSampleNote({ model }) {
  const { ctx, view, sorted, filters, patchFilters } = model;
  const def = ctx.metrics[view.sort];
  if (!def || !["rate", "ratio"].includes(def.shape) || filters.minutes > 0) return null;
  const top = sorted.slice(0, 10);
  const thin = top.filter((r) => r.in_pool === false).length;
  if (thin < 3) return null;
  const pool = model.ctx.groupSizes ? null : null;
  return html`<${Notice} tone="warn" icon="alert">${thin} of the first ${top.length} have played very little, so their ${def.short} is not steady (a few minutes can swing any rate). Nothing is hidden. <button type="button" class="linklike" onClick=${() => patchFilters({ minutes: 450 })}>Only players with 450+ minutes</button></${Notice}>`;
}

function Coverage({ d, ctx }) {
  const cov = d.coverage;
  const players = d.rows.length;
  const notes = [];
  if (cov.event_players === 0) notes.push(html`No event data is stored for this selection, so the metrics that need it (tackles, passes, carries, duels …) are blank, never zero. <a class="link" href=${href("/data")}>See how it is fetched</a>.`);
  else if (cov.event_players < players * 0.9) notes.push(html`Event data is stored for ${cov.event_players} of ${players} players here; the rest are blank on event metrics. <a class="link" href=${href("/data")}>Data status</a>`);
  const shotMissing = Object.entries(cov.shots || {}).filter(([, v]) => v[0] < v[1]);
  if (shotMissing.length) notes.push(html`Match pages are still being downloaded for ${shotMissing.map(([k, v]) => `${k.replace(":", " ")} (${v[0]} of ${v[1]})`).join(", ")}; set-piece and shot-location metrics fill in as they arrive.`);
  return notes.length ? html`<${Notice} icon="clock">${notes.map((n, i) => html`<span key=${i}>${i ? " " : ""}${n}</span>`)}</${Notice}>` : null;
}

function ScoutView({ d, scope, meta, catalog, query, active }) {
  const model = useExplorer({ level: "player", payload: d, catalog, query });
  const { ctx, view, filters, shown, sorted, filtered, setView, setColumns, isFiltered } = model;
  const picks = useMemo(() => new Set(view.cmp), [view.cmp.join()]);
  const onPick = (id, on) => setView({ cmp: on ? [...view.cmp.filter((x) => x !== id), id].slice(-4) : view.cmp.filter((x) => x !== id) });
  const columns = playerColumns(model, { scope, picks, onPick });
  const cov = d.coverage, enr = d.enrichment;
  const agesPct = cov.players ? cov.ages_known / cov.players : 1;
  const config = useMemo(() => ({
    level: "player", noun: "players", ageRef: d.scope.age_reference, poolMinutes: d.scope.pool_minutes, searchPlaceholder: "Search by player or club",
    controls: ["roles", "positions", "tags", "clubs", "minutes", "age", "part", "rule"],
  }), [d.scope.age_reference, d.scope.pool_minutes]);
  const sortBy = (k) => setView({ sort: k, dir: ctx.metrics[k]?.hib === false ? "asc" : "desc" });
  const eyebrow = `${d.scope.leagues.map((l) => leagueName(meta, l)).join(" + ")} · ${d.scope.labels.join(", ")}`;

  return html`
    <${PageHead} eyebrow=${eyebrow} title="Scout"
      sub=${`${plural(d.rows.length, "player")} with minutes on the pitch, none hidden. Narrow the list with any filter, rank it by any of ${ctx.order.length} metrics, and choose the columns you want. Percentiles compare each player only with others in the same role.`}
      actions=${html`<${ScopePicker} meta=${meta} active=${active} resolvedLabels=${d.scope.labels} />
        <${Button} size="sm" icon="external" title="Copy a link to exactly this view" onClick=${() => navigator.clipboard?.writeText(window.location.href)}>Copy link</${Button}>`} />
    <${DataNotices} scope=${{ note: d.scope.notes?.[0] }} meta=${d.meta} />
    ${agesPct < 0.6 || enr.rosters?.running ? html`<${Notice} icon="clock">Ages are known for ${cov.ages_known} of ${cov.players} players${enr.rosters?.running ? " (fetching club squad lists now: exact birthdates arrive in a minute or so)" : enr.ages.running ? ` (looking up ${enr.ages.done} of ${enr.ages.total} more on Wikidata now)` : ""}. The age filter only applies to players with a known age.${cov.inferred_roles ? ` ${cov.inferred_roles} roles are inferred from minutes and sharpen as position data arrives.` : ""}</${Notice}>` : null}
    <${Coverage} d=${d} ctx=${ctx} />
    <${FilterBar} model=${model} allRows=${d.rows} config=${config} onShowColumns=${(keys) => setColumns(keys.filter((k) => ctx.idx[k] !== undefined))} onSortBy=${sortBy} />
    ${!isFiltered && view.view === "table" ? html`<${Insights} items=${d.highlights} scope=${scope} limit=${3} compact expandable />` : null}

    <div class="card results-card">
      <${ResultsBar} model=${model} level="player" noun="players" csv=${{ columns: csvColumns(columns), filename: "prem-lab-scout.csv" }} />
      ${sorted.length
        ? view.view === "map"
          ? html`<div class="card-body"><${MetricMap} model=${model} level="player" scope=${scope} noun="players" onOpen=${(r) => openPlayer(r, scope)} /></div>`
          : html`<div class="results-notes"><${SmallSampleNote} model=${model} /></div><${InsightStrip} model=${model} noun="players" /><${ResultsTable} model=${model} columns=${columns} rowKey=${(r) => r.id} onOpen=${(r) => openPlayer(r, scope)} />`
        : html`<${EmptyState} title="No players match these filters" text=${isFiltered ? "Remove a filter below the search box, or clear them all." : "Nothing is loaded for this selection."}
            action=${isFiltered ? html`<${Button} onClick=${model.clearFilters}>Clear all filters</${Button}>` : null} />`}
    </div>
    <${CompareTray} ids=${view.cmp} rows=${d.rows} onChange=${(ids) => setView({ cmp: ids })} />
  `;
}

export default function Scout() {
  const scope = useScope();
  const { meta, catalog } = useMeta();
  const { query } = useLocation();
  const active = scopeFromQuery(query, scope);
  const q = useApi("/api/players", { leagues: active.leagues, seasons: active.seasons, min_minutes: 1 });
  const enrichment = q.data?.enrichment;
  const running = enrichment && (enrichment.ages.running || enrichment.roles.running || enrichment.rosters?.running);
  useEffect(() => {
    if (!running) return undefined;
    const t = setInterval(() => q.reload(), 6000);
    return () => clearInterval(t);
  }, [running, q.reload]);
  useDocumentTitle("Scout");
  return html`<${Async} q=${q}>${(d) => html`<${ScoutView} d=${d} scope=${{ ...scope, season: active.seasons.length === 1 ? active.seasons[0] : scope.season }} meta=${meta} catalog=${catalog} query=${query} active=${active} />`}</${Async}>`;
}
