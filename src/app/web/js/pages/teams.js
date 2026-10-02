// Teams: the scouting board for clubs. The same filters, lenses, columns, Top-N and map as Scout, over every team metric.
import { html, useMemo } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useScope, useMeta, leagueName } from "../lib/scope.js";
import { href, useLocation } from "../lib/router.js";
import { plural } from "../lib/format.js";
import { Async, Button, DataNotices, EmptyState, Notice, PageHead, useDocumentTitle } from "../ui/common.js";
import { useExplorer } from "../ui/explore/model.js";
import { FilterBar } from "../ui/explore/FilterBar.js";
import { InsightStrip, ResultsBar, ResultsTable, csvColumns, openTeam, teamColumns } from "../ui/explore/Results.js";
import { MetricMap } from "../ui/explore/MetricMap.js";
import { ScopePicker, scopeFromQuery } from "../ui/explore/Scope.js";

function Coverage({ d }) {
  const c = d.coverage;
  const notes = [];
  if (c.event_teams === 0) notes.push(html`No event data is stored for this selection, so style metrics (possession, passing, pressing, carries) are blank, never zero. <a class="link" href=${href("/data")}>See how it is fetched</a>.`);
  else if (c.event_teams < c.teams) notes.push(html`Event data is stored for ${c.event_teams} of ${c.teams} teams here; the rest are blank on event metrics.`);
  if (c.shot_teams < c.teams) notes.push(html`Shot metrics need every match page of a season, which ${c.teams - c.shot_teams} teams do not have yet: they fill in as the pages download.`);
  return notes.length ? html`<${Notice} icon="clock">${notes.map((n, i) => html`<span key=${i}>${i ? " " : ""}${n}</span>`)}</${Notice}>` : null;
}

function TeamsView({ d, scope, meta, catalog, query, active }) {
  const model = useExplorer({ level: "team", payload: d, catalog, query });
  const { ctx, view, sorted, isFiltered, setView, setColumns } = model;
  const columns = teamColumns(model);
  const config = useMemo(() => ({ level: "team", noun: "teams", searchPlaceholder: "Search by team", controls: ["formations", "rule"] }), []);
  const sortBy = (k) => setView({ sort: k, dir: ctx.metrics[k]?.hib === false ? "asc" : "desc" });
  const eyebrow = `${d.scope.leagues.map((l) => leagueName(meta, l)).join(" + ")} · ${d.scope.labels.join(", ")}`;
  return html`
    <${PageHead} eyebrow=${eyebrow} title="Teams"
      sub=${`${plural(d.rows.length, "team")}, ranked on ${ctx.order.length} measures of results, chances, style, pressing, set pieces and discipline. Percentiles compare a team only with the others in its own league and season.`}
      actions=${html`<${ScopePicker} meta=${meta} active=${active} resolvedLabels=${d.scope.labels} />`} />
    <${DataNotices} scope=${{ note: d.scope.notes?.[0] }} meta=${d.meta} />
    <${Coverage} d=${d} />
    <${FilterBar} model=${model} allRows=${d.rows} config=${config} onShowColumns=${(keys) => setColumns(keys.filter((k) => ctx.idx[k] !== undefined))} onSortBy=${sortBy} />
    <div class="card results-card">
      <${ResultsBar} model=${model} level="team" noun="teams" csv=${{ columns: csvColumns(columns), filename: "prem-lab-teams.csv" }} />
      ${sorted.length
        ? view.view === "map"
          ? html`<div class="card-body"><${MetricMap} model=${model} level="team" scope=${scope} noun="teams" labelCount=${40} onOpen=${openTeam} /></div>`
          : html`<${InsightStrip} model=${model} noun="teams" /><${ResultsTable} model=${model} columns=${columns} rowKey=${(r) => r.key} onOpen=${openTeam} />`
        : html`<${EmptyState} title="No teams match these filters" text="Remove a filter, or clear them all." action=${isFiltered ? html`<${Button} onClick=${model.clearFilters}>Clear all filters</${Button}>` : null} />`}
    </div>`;
}

export default function Teams() {
  const scope = useScope();
  const { meta, catalog } = useMeta();
  const { query } = useLocation();
  const active = scopeFromQuery(query, scope);
  const q = useApi("/api/teams", { leagues: active.leagues, seasons: active.seasons });
  useDocumentTitle("Teams");
  return html`<${Async} q=${q}>${(d) => html`<${TeamsView} d=${d} scope=${scope} meta=${meta} catalog=${catalog} query=${query} active=${active} />`}</${Async}>`;
}
