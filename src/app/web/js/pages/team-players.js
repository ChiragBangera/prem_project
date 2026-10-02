// Team players: the squad in the same explorer Scout uses (filters, lenses, any columns, sorting, map), limited to this club.
import { html, useMemo, useState } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useMeta } from "../lib/scope.js";
import { useLocation } from "../lib/router.js";
import { pct, plural } from "../lib/format.js";
import { Async, Button, Card, EmptyState, Segmented, playerHref } from "../ui/common.js";
import { BarList } from "../charts/bars.js";
import { useExplorer } from "../ui/explore/model.js";
import { FilterBar } from "../ui/explore/FilterBar.js";
import { ResultsBar, ResultsTable, csvColumns, openPlayer, playerColumns } from "../ui/explore/Results.js";
import { MetricMap } from "../ui/explore/MetricMap.js";

const SHARES = [
  { value: "share_npxg", label: "Share of non-penalty xG", note: "The part of the team's non-penalty xG that comes from his shots." },
  { value: "share_xa", label: "Share of xA", note: "The part of the team's expected assists that comes from his passes." },
  { value: "chain_share", label: "Share of xGChain", note: "How much of the team's attacking play passes through him (every possession that ended in a shot)." },
];

/** Who the attack runs through: the squad's biggest contributors on one measure. */
function Contributions({ squad, concentration }) {
  const [measure, setMeasure] = useState("share_npxg");
  const info = SHARES.find((s) => s.value === measure);
  const rows = [...squad].filter((r) => (r[measure] || 0) > 0).sort((a, b) => b[measure] - a[measure]).slice(0, 8);
  if (!rows.length) return null;
  return html`<${Card} title="Where the output comes from" sub=${concentration?.top3?.length ? `${concentration.top3.join(", ")} account for ${pct(concentration.top3_share)} of the team's non-penalty xG.` : info.note}
    actions=${html`<${Segmented} small label="Measure" value=${measure} onChange=${setMeasure} options=${SHARES.map((s) => ({ value: s.value, label: s.label.replace("Share of ", "") }))} />`}>
    <${BarList} rows=${rows.map((r) => ({ key: r.id, label: html`<a class="link truncate" href=${playerHref(r.id)}>${r.name}</a>`, value: r[measure], right: pct(r[measure]) }))} max=${rows[0][measure]} />
    <p class="xsmall muted" style=${{ marginTop: "10px" }}>${info.note} A team that leans on one or two players for most of its chances is easier to stop, and fragile when they are missing.</p>
  </${Card}>`;
}

const NO_PICKS = new Set();

function Squad({ payload, team, scope, catalog, query, squadShares, concentration }) {
  const rows = useMemo(() => payload.rows.filter((r) => (r.teams || [r.team]).includes(team)), [payload, team]);
  const derived = useMemo(() => ({ ...payload, rows }), [payload, rows]);
  const model = useExplorer({ level: "player", payload: derived, catalog, query });
  const { ctx, view, sorted, isFiltered, setView, setColumns } = model;
  const columns = playerColumns(model, { scope, picks: NO_PICKS, onPick: null });
  const config = useMemo(() => ({
    level: "player", noun: "players", ageRef: payload.scope.age_reference, poolMinutes: payload.scope.pool_minutes, searchPlaceholder: "Search this squad",
    controls: ["roles", "positions", "tags", "minutes", "part", "rule"],
  }), [payload.scope]);
  if (!rows.length) return html`<${Card}><${EmptyState} icon="users" title="No players found" text="Understat lists no minutes for this team in the selected season." /></${Card}>`;
  const sortBy = (k) => setView({ sort: k, dir: ctx.metrics[k]?.hib === false ? "asc" : "desc" });
  return html`<div class="stack" style=${{ "--gap": "16px" }}>
    <p class="small muted">${plural(rows.length, "player")} with minutes for ${team}. Percentiles compare each player with everyone in the league who plays the same role, not just this squad.</p>
    <${FilterBar} model=${model} allRows=${rows} config=${config} onShowColumns=${(keys) => setColumns(keys.filter((k) => ctx.idx[k] !== undefined))} onSortBy=${sortBy} />
    <div class="card results-card">
      <${ResultsBar} model=${model} level="player" noun="players" csv=${{ columns: csvColumns(columns), filename: `prem-lab-${team}-squad.csv` }} />
      ${sorted.length
        ? view.view === "map"
          ? html`<div class="card-body"><${MetricMap} model=${model} level="player" scope=${scope} noun="players" labelCount=${25} onOpen=${(r) => openPlayer(r, scope)} /></div>`
          : html`<${ResultsTable} model=${model} columns=${columns} rowKey=${(r) => r.id} onOpen=${(r) => openPlayer(r, scope)} maxHeight="min(72vh, 820px)" />`
        : html`<${EmptyState} title="No players match these filters" action=${isFiltered ? html`<${Button} onClick=${model.clearFilters}>Clear all filters</${Button}>` : null} />`}
    </div>
    <${Contributions} squad=${squadShares} concentration=${concentration} />
  </div>`;
}

export default function TeamPlayers({ team, scope, squad, concentration }) {
  const { catalog } = useMeta();
  const { query } = useLocation();
  const q = useApi("/api/players", { leagues: [scope.league], seasons: [scope.season], min_minutes: 1 });
  return html`<${Async} q=${q}>${(payload) => html`<${Squad} payload=${payload} team=${team} scope=${scope} catalog=${catalog} query=${query} squadShares=${squad} concentration=${concentration} />`}</${Async}>`;
}
