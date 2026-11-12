// Deep analytics for one match: every player who played, side by side, on the same desk as Scout: filters in a rail (the side, role,
// minutes, started or came on, rules on any measure), the table with every Scout measure worked out for this match alone, the best and the
// weakest of each measure ringed, and one player beside the list. Its state lives in the page, not the address (the match's tabs use that).
import { html, useMemo, useState } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useMeta } from "../lib/scope.js";
import { cls, plural } from "../lib/format.js";
import { useMedia } from "../lib/media.js";
import { Icon } from "../lib/icons.js";
import { extremes } from "../lib/matchplayers.js";
import { Async, Notice, Segmented, EmptyState, Button, playerHref } from "./common.js";
import { CsvButton } from "./table.js";
import { useExplorer, useLocalQuery, sortSentence, openPlayer } from "./explore/model.js";
import { Rail } from "./explore/Rail.js";
import { MarkKey, ShadeKey, Sheet } from "./explore/Sheet.js";
import { Peek } from "./explore/Peek.js";
import { ColumnPicker } from "./explore/ColumnPicker.js";
import { MetricMap } from "./explore/MetricMap.js";

// Open on the players who are ranked (30+ minutes): a rate from a few minutes tops any list sorted by it. "Any" is one click away and the
// count says how many are out.
const RANKED_FROM = "30";
const SIDE = { h: "var(--c1)", a: "var(--c2)" };

function Desk({ d, f, catalog, scope }) {
  const payload = useMemo(() => ({ keys: d.keys, rows: d.rows.map((r) => ({ ...r, league: scope.league, seasons: [scope.season] })),
    scope: { group_sizes: d.group_sizes }, coverage: { event_players: d.coverage.events } }), [d, scope]);
  const extend = useMemo(() => ({ pctWhat: (r) => `Better than, among this season's ${(catalog.roles?.plural?.[r.group] || "players").toLowerCase()}` }), [catalog]);
  const overrides = useMemo(() => ({ sort: d.keys.includes("xg_xa90") ? "xg_xa90" : "minutes", dir: "desc" }), [d.keys]);
  const [query, write] = useLocalQuery({ min: RANKED_FROM });
  const model = useExplorer({ level: "player", payload, catalog, query, write, overrides, extend });
  const { ctx, view, filtered, sorted, shown, columns, chips, setView, setFilters, isFiltered } = model;
  const narrow = useMedia("(max-width: 1000px)");
  const [peekId, setPeekId] = useState(null);
  const [railOpen, setRailOpen] = useState(false);
  const peeked = peekId != null && !narrow ? sorted.find((r) => r.id === peekId) : null;
  const config = useMemo(() => ({ level: "player", kind: "match", noun: "players", searchPlaceholder: "Find a player",
    sides: [{ value: f.home, label: f.home_short || f.home, dot: SIDE.h }, { value: f.away, label: f.away_short || f.away, dot: SIDE.a }] }), [f]);
  const keys = useMemo(() => {
    const set = columns.keys.filter((k) => k !== "minutes");
    const pin = ctx.metrics[view.sort] && ctx.idx[view.sort] !== undefined && view.sort !== "minutes" && !set.includes(view.sort) ? [view.sort] : [];
    return [...pin, ...set, ...(ctx.idx.minutes !== undefined ? ["minutes"] : [])];
  }, [columns.keys.join(), view.sort, ctx]);
  const marks = useMemo(() => extremes(filtered, keys.filter((k) => k !== "minutes"), ctx), [filtered, keys, ctx]);
  const short = (team) => (team === f.home ? f.home_short : team === f.away ? f.away_short : team);
  const lead = { label: "Player", width: narrow ? 178 : peeked ? 220 : 250, sortKey: "name",
    render: (r, rank) => {
      const link = playerHref(r.id, { league: scope.league, season: scope.season });
      const inner = html`<span class="name">${r.name}</span><span class="sub">${[short(r.team), ctx.positions?.labels?.[r.pos2] || r.pos2, r.started ? null : "came on"].filter(Boolean).join(" · ")}</span>`;
      return html`<div class="dk-who"><span class="dk-rank">${rank}</span><div class="pcell"><i class="dk-dot" style=${{ background: SIDE[r.side] }} title=${r.team}></i>
        ${link ? html`<a class="cell-player" href=${link} onClick=${(e) => e.stopPropagation()}>${inner}</a>` : html`<span class="cell-player">${inner}</span>`}</div></div>`;
    } };
  const csv = [{ label: "Player", value: (r) => r.name }, { label: "Team", value: (r) => r.team }, { label: "Started", value: (r) => (r.started ? "yes" : "no") },
    ...keys.map((k) => ({ label: ctx.metrics[k].label, value: (r) => r.v[ctx.idx[k]] }))];
  const thin = filtered.filter((r) => !r.in_pool).length;
  const head = html`<div class="dk-railhead"><h2>Every player</h2><p>${plural(d.rows.length, "player")} played in ${f.home} v ${f.away}. Each number is for this match alone; a shade ranks it against the season's players in the same role.</p>
    <${Button} size="sm" class="dk-railtoggle" icon="filter" onClick=${() => setRailOpen(!railOpen)}>${railOpen ? "Hide filters" : `Filters${chips.length ? ` (${chips.length})` : ""}`}</${Button}></div>`;

  return html`<div class="stack" style=${{ "--gap": "12px" }}>
    <div class=${cls("desk", "inset", peeked && "peeking", railOpen && "rail-open")}>
      <${Rail} model=${model} allRows=${payload.rows} config=${config} head=${head} />
      <section class="dk-main" aria-label="Players in this match">
        <div class="results-bar">
          <span class="dk-count"><b class="rb-title">${plural(sorted.length, "player")}</b><span class="muted small">${isFiltered ? `of ${d.rows.length}` : "everyone who played"}</span></span>
          <div class="rb-controls">
            <${Segmented} small label="View" options=${[{ value: "table", label: "Table" }, { value: "map", label: "Map" }]} value=${view.view} onChange=${(v) => setView({ view: v })} />
            <${CsvButton} columns=${csv} rows=${shown} filename=${`prem-lab-match-${f.home_short}-${f.away_short}.csv`} />
          </div>
        </div>
        ${chips.length ? html`<div class="dk-pills" aria-label="Active filters">
          ${chips.map((c) => html`<span key=${c.id} class=${cls("fchip", c.kind)} title=${c.title}><span>${c.text}</span>
            <button type="button" class="x" aria-label=${`Remove filter ${c.text}`} onClick=${() => setFilters(c.next)}><${Icon} name="x" /></button></span>`)}
          <${Button} kind="quiet" size="sm" onClick=${model.clearFilters}>Clear all</${Button}>
        </div>` : null}
        ${view.view === "map" ? null : html`<div class="dk-setrow"><div class="dk-sets" role="tablist" aria-label="Which measures to show">
          ${columns.custom ? html`<button type="button" role="tab" aria-selected="true" title="The measures you chose yourself">Your columns</button>` : null}
          ${ctx.views.map((v) => html`<button type="button" role="tab" key=${v.key} aria-selected=${String(columns.preset === v.key)} title=${v.blurb} onClick=${() => setView({ cols: v.key === "overview" ? null : v.key })}>${v.label}</button>`)}
          </div><${ColumnPicker} model=${model} />
        </div>`}
        ${!sorted.length
          ? html`<${EmptyState} title="No players match these filters" text="Widen the minutes, or clear the filters." action=${html`<${Button} onClick=${model.clearFilters}>Clear all filters</${Button}>`} />`
          : view.view === "map"
            ? html`<div class="dk-scroll"><div class="card-body"><${MetricMap} model=${model} level="player" scope=${scope} noun="players" labelCount=${30} onOpen=${(r) => openPlayer(r, scope)} /></div></div>`
            : html`<${Sheet} model=${model} lead=${lead} keys=${keys} rowKey=${(r) => r.id} picked=${peeked?.id ?? null} caption="Players in this match" marks=${marks}
                peers="his role, this season" onPick=${(r) => (narrow ? r.id > 0 && openPlayer(r, scope) : setPeekId(peekId === r.id ? null : r.id))} />
              <div class="dk-foot"><span>${sortSentence(view, ctx)} Click a row to see the player beside the list.</span>
                <span class="row wrap" style=${{ gap: "4px 14px" }}><${MarkKey} /><${ShadeKey} peers="his role, this season" /></span></div>`}
      </section>
      ${peeked ? html`<${Peek} row=${peeked} ctx=${ctx} season=${scope.season} onClose=${() => setPeekId(null)}
        facts=${[{ value: peeked.started ? "Started" : "Came on", label: short(peeked.team) }]}
        note=${`Each bar ranks his number in this match against this season's ${(ctx.roles?.plural?.[peeked.group] || "players").toLowerCase()}; the tick is the middle of the role.${peeked.in_pool ? "" : " Under 30 minutes, so not ranked."}`} />` : null}
    </div>
    <${Notice} icon="info">Every number is for this match alone, from its shots, the line-ups${d.coverage.events ? " and the event data" : ""}. Players under 30 minutes are not ranked${thin ? ` (${thin} in the list now)` : ""}, and one match is a small sample: read a single rate with care.${d.coverage.events ? "" : " No event data is stored for this match, so tackles, passes, carries and duels are blank."}</${Notice}>
  </div>`;
}

export function MatchDeep({ id, scope, f, live = false }) {
  const { catalog } = useMeta();
  // a match drawn from a WhoScored read: its own cache key, asked again every minute, never kept in the browser's store (see MatchPage)
  const q = useApi(`/api/match/${id}/players`, live ? { league: scope.league, season: scope.season, live: 1 } : { league: scope.league, season: scope.season },
    live ? { staleMs: 0, persist: false, pollMs: 60000 } : undefined);
  return html`<${Async} q=${q}>${(d) => (catalog ? html`<${Desk} d=${d} f=${f} catalog=${catalog} scope=${scope} />` : null)}</${Async}>`;
}
