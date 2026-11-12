// Team players: the squad on the same desk as Scout (filters in a rail, the table, one player beside it, or the map), limited to this club.
import { html, useMemo, useState } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useMeta } from "../lib/scope.js";
import { useLocation } from "../lib/router.js";
import { cls, pct, plural } from "../lib/format.js";
import { useMedia } from "../lib/media.js";
import { Icon } from "../lib/icons.js";
import { Async, Button, Card, EmptyState, Segmented, playerHref } from "../ui/common.js";
import { PlayerCell } from "../ui/cells.js";
import { CsvButton } from "../ui/table.js";
import { BarList } from "../charts/bars.js";
import { useExplorer, sortSentence, openPlayer } from "../ui/explore/model.js";
import { Rail } from "../ui/explore/Rail.js";
import { ShadeKey, Sheet } from "../ui/explore/Sheet.js";
import { Peek } from "../ui/explore/Peek.js";
import { ColumnPicker } from "../ui/explore/ColumnPicker.js";
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

function Squad({ payload, team, scope, catalog, query, squadShares, concentration }) {
  const rows = useMemo(() => payload.rows.filter((r) => (r.teams || [r.team]).includes(team)), [payload, team]);
  const derived = useMemo(() => ({ ...payload, rows }), [payload, rows]);
  const model = useExplorer({ level: "player", payload: derived, catalog, query });
  const { ctx, view, sorted, shown, columns, chips, setView, setFilters, isFiltered } = model;
  const narrow = useMedia("(max-width: 1000px)");
  const [peekId, setPeekId] = useState(null);
  const [railOpen, setRailOpen] = useState(false);
  const peeked = peekId != null && !narrow ? sorted.find((r) => r.id === peekId) : null;
  const config = useMemo(() => ({ level: "player", kind: "squad", noun: "players", searchPlaceholder: "Search this squad" }), []);
  const keys = useMemo(() => {
    const set = columns.keys.filter((k) => k !== "minutes");
    const pin = ctx.metrics[view.sort] && ctx.idx[view.sort] !== undefined && view.sort !== "minutes" && !set.includes(view.sort) ? [view.sort] : [];
    return [...pin, ...set, ...(ctx.idx.minutes !== undefined ? ["minutes"] : [])];
  }, [columns.keys.join(), view.sort, ctx]);
  if (!rows.length) return html`<${Card}><${EmptyState} icon="users" title="No players found" text="Understat lists no minutes for this team in the selected season." /></${Card}>`;
  const lead = { label: "Player", width: narrow ? 178 : peeked ? 230 : 270, sortKey: "name",
    render: (r, rank) => html`<div class="dk-who"><span class="dk-rank">${rank}</span><${PlayerCell} row=${r} ctx=${ctx} season=${scope.season} /></div>` };
  const csv = [{ label: "Player", value: (r) => r.name }, ...keys.map((k) => ({ label: ctx.metrics[k].label, value: (r) => r.v[ctx.idx[k]] }))];
  const head = html`<div class="dk-railhead"><h2>The squad</h2><p>${plural(rows.length, "player")} with minutes for ${team}. A rank compares each player with everyone in the league in the same role, not just this squad.</p>
    <${Button} size="sm" class="dk-railtoggle" icon="filter" onClick=${() => setRailOpen(!railOpen)}>${railOpen ? "Hide filters" : `Filters${chips.length ? ` (${chips.length})` : ""}`}</${Button}></div>`;

  return html`<div class="stack" style=${{ "--gap": "16px" }}>
    <div class=${cls("desk", "inset", peeked && "peeking", railOpen && "rail-open")}>
      <${Rail} model=${model} allRows=${rows} config=${config} head=${head} />
      <section class="dk-main" aria-label="Squad">
        <div class="results-bar">
          <span class="dk-count"><b class="rb-title">${sorted.length} players</b>${isFiltered ? html`<span class="muted small">of ${rows.length}</span>` : html`<span class="muted small">the whole squad</span>`}</span>
          <div class="rb-controls">
            <${Segmented} small label="View" options=${[{ value: "table", label: "Table" }, { value: "map", label: "Map" }]} value=${view.view} onChange=${(v) => setView({ view: v })} />
            <${CsvButton} columns=${csv} rows=${shown} filename=${`prem-lab-${team}-squad.csv`} />
          </div>
        </div>
        ${chips.length ? html`<div class="dk-pills" aria-label="Active filters">
          ${chips.map((c) => html`<span key=${c.id} class=${cls("fchip", c.kind)} title=${c.title}><span>${c.text}</span>
            <button type="button" class="x" aria-label=${`Remove filter ${c.text}`} onClick=${() => setFilters(c.next)}><${Icon} name="x" /></button></span>`)}
          <${Button} kind="quiet" size="sm" onClick=${model.clearFilters}>Clear all</${Button}>
        </div>` : null}
        ${view.view === "map" ? null : html`<div class="dk-setrow"><div class="dk-sets" role="tablist" aria-label="Which measures to show">
          ${columns.custom ? html`<button type="button" role="tab" aria-selected="true" title="The measures you chose yourself, or the ones a ready-made search looks at">Your columns</button>` : null}
          ${ctx.views.map((v) => html`<button type="button" role="tab" key=${v.key} aria-selected=${String(columns.preset === v.key)} title=${v.blurb} onClick=${() => setView({ cols: v.key === "overview" ? null : v.key })}>${v.label}</button>`)}
          </div><${ColumnPicker} model=${model} />
        </div>`}
        ${!sorted.length
          ? html`<${EmptyState} title="No players match these filters" text="Remove a filter above the table, or clear them all." action=${isFiltered ? html`<${Button} onClick=${model.clearFilters}>Clear all filters</${Button}>` : null} />`
          : view.view === "map"
            ? html`<div class="dk-scroll"><div class="card-body"><${MetricMap} model=${model} level="player" scope=${scope} noun="players" labelCount=${25} onOpen=${(r) => openPlayer(r, scope)} /></div></div>`
            : html`<${Sheet} model=${model} lead=${lead} keys=${keys} rowKey=${(r) => r.id} picked=${peeked?.id ?? null} caption=${`${team} players`}
                onPick=${(r) => (narrow ? openPlayer(r, scope) : setPeekId(peekId === r.id ? null : r.id))} />
              <div class="dk-foot"><span>${sortSentence(view, ctx)} Click a row to see the player beside the list.</span><${ShadeKey} /></div>`}
      </section>
      ${peeked ? html`<${Peek} row=${peeked} ctx=${ctx} season=${scope.season} onClose=${() => setPeekId(null)} />` : null}
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
