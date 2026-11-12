// Scout: find players by what they do. A desk of three parts: every filter in a rail on the left, the table from the top of the screen, and one
// player at a glance on the right. Every player is listed until you narrow it down; nothing is pre-selected.
import { html, useEffect, useMemo, useState } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useScope, useMeta, leagueName } from "../lib/scope.js";
import { href, useLocation } from "../lib/router.js";
import { cls, plural } from "../lib/format.js";
import { useMedia } from "../lib/media.js";
import { TOP_CHOICES } from "../lib/filters.js";
import { Icon } from "../lib/icons.js";
import { Async, Button, DataNotices, EmptyState, Insights, Notice, Segmented, Select, useDocumentTitle } from "../ui/common.js";
import { useExplorer, sortSentence, openPlayer } from "../ui/explore/model.js";
import { Rail } from "../ui/explore/Rail.js";
import { ShadeKey, Sheet } from "../ui/explore/Sheet.js";
import { Peek } from "../ui/explore/Peek.js";
import { ColumnPicker } from "../ui/explore/ColumnPicker.js";
import { PlayerCell } from "../ui/cells.js";
import { CompareTray } from "../ui/explore/Tray.js";
import { CsvButton } from "../ui/table.js";
import { MetricMap } from "../ui/explore/MetricMap.js";
import { ScopePicker, scopeFromQuery } from "../ui/explore/Scope.js";

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
  const { ctx, view, filters, sorted, shown, columns, chips, setView, setFilters, isFiltered } = model;
  const picks = useMemo(() => new Set(view.cmp), [view.cmp.join()]);
  const onPick = (id, on) => setView({ cmp: on ? [...view.cmp.filter((x) => x !== id), id].slice(-4) : view.cmp.filter((x) => x !== id) });
  const narrow = useMedia("(max-width: 1000px)");
  const [peekId, setPeekId] = useState(null);
  const [railOpen, setRailOpen] = useState(false);
  const peeked = peekId != null && !narrow ? sorted.find((r) => r.id === peekId) : null;
  const cov = d.coverage, enr = d.enrichment;
  const agesPct = cov.players ? cov.ages_known / cov.players : 1;
  const config = useMemo(() => ({ level: "player", noun: "players", ageRef: d.scope.age_reference, poolMinutes: d.scope.pool_minutes, searchPlaceholder: "Search by player or club" }), [d.scope.age_reference, d.scope.pool_minutes]);
  const where = `${d.scope.leagues.map((l) => leagueName(meta, l)).join(" + ")}, ${d.scope.labels.join(", ")}`;

  // the columns: the set in view, the measure the list is sorted by when it is not among them, and minutes last (the sample behind every rate)
  const keys = useMemo(() => {
    const set = columns.keys.filter((k) => k !== "minutes");
    const pin = ctx.metrics[view.sort] && ctx.idx[view.sort] !== undefined && view.sort !== "minutes" && !set.includes(view.sort) ? [view.sort] : [];
    return [...pin, ...set, ...(ctx.idx.minutes !== undefined ? ["minutes"] : [])];
  }, [columns.keys.join(), view.sort, ctx]);
  const lead = { label: "Player", width: narrow ? 178 : peeked ? 236 : 290, sortKey: "name",
    render: (r, rank) => html`<div class="dk-who"><span class="dk-rank">${rank}</span><${PlayerCell} row=${r} ctx=${ctx} season=${scope.season} picked=${picks.has(r.id)} onPick=${onPick} /></div>` };
  const csv = [{ label: "Player", value: (r) => r.name }, { label: "Club", value: (r) => r.team }, ...keys.map((k) => ({ label: ctx.metrics[k].label, value: (r) => r.v[ctx.idx[k]] }))];
  const capped = view.top > 0 && sorted.length > view.top;
  const topOptions = [{ value: "0", label: "Everyone" }, ...[...new Set([...TOP_CHOICES, ...(view.top > 0 ? [view.top] : [])])].sort((a, b) => a - b).map((n) => ({ value: String(n), label: `Top ${n}` }))];

  const head = html`<div class="dk-railhead"><h1>Scout</h1><p>${where}. ${plural(d.rows.length, "player")} with minutes, none hidden.</p>
    <div class="row wrap" style=${{ gap: "6px" }}><${ScopePicker} meta=${meta} active=${active} resolvedLabels=${d.scope.labels} />
      <${Button} size="sm" class="dk-railtoggle" icon="filter" onClick=${() => setRailOpen(!railOpen)}>${railOpen ? "Hide filters" : `Filters${chips.length ? ` (${chips.length})` : ""}`}</${Button}></div></div>`;

  return html`
    <${DataNotices} scope=${{ note: d.scope.notes?.[0] }} meta=${d.meta} />
    ${agesPct < 0.6 || enr.rosters?.running ? html`<${Notice} icon="clock">Ages are known for ${cov.ages_known} of ${cov.players} players${enr.rosters?.running ? " (fetching club squad lists now: exact birthdates arrive in a minute or so)" : enr.ages.running ? ` (looking up ${enr.ages.done} of ${enr.ages.total} more on Wikidata now)` : ""}. A player with no known age is never matched by an age filter.</${Notice}>` : null}
    <${Coverage} d=${d} ctx=${ctx} />
    <div class=${cls("desk", "full", peeked && "peeking", railOpen && "rail-open")}>
      <${Rail} model=${model} allRows=${d.rows} config=${config} head=${head} path="/scout" query=${query} />
      <section class="dk-main" aria-label="Players">
        <div class="results-bar">
          <span class="dk-count"><b class="rb-title">${capped ? `Top ${shown.length} of ${sorted.length.toLocaleString("en-GB")}` : sorted.length.toLocaleString("en-GB")} players</b>${isFiltered ? html`<span class="muted small">of ${d.rows.length.toLocaleString("en-GB")}</span>` : html`<span class="muted small">everyone, no filters</span>`}</span>
          <div class="rb-controls">
            <${Select} compact value=${String(view.top)} label="How many to show" options=${topOptions} onChange=${(v) => setView({ top: Number(v) })} />
            <${Segmented} small label="View" options=${[{ value: "table", label: "Table" }, { value: "map", label: "Map" }]} value=${view.view} onChange=${(v) => setView({ view: v })} />
            <${CsvButton} columns=${csv} rows=${shown} filename="prem-lab-scout.csv" />
            <${Button} size="sm" icon="external" title="Copy a link to exactly this view" onClick=${() => navigator.clipboard?.writeText(window.location.href)}>Copy link</${Button}>
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
          ? html`<${EmptyState} title="No players match these filters" text=${isFiltered ? "Remove a filter above the table, or clear them all." : "Nothing is loaded for this selection."}
              action=${isFiltered ? html`<${Button} onClick=${model.clearFilters}>Clear all filters</${Button}>` : null} />`
          : view.view === "map"
            ? html`<div class="dk-scroll"><div class="card-body"><${MetricMap} model=${model} level="player" scope=${scope} noun="players" onOpen=${(r) => openPlayer(r, scope)} /></div></div>`
            : html`<div class="dk-notes"><${SmallSampleNote} model=${model} /></div>
              <${Sheet} model=${model} lead=${lead} keys=${keys} rowKey=${(r) => r.id} picked=${peeked?.id ?? null} caption="Players"
                onPick=${(r) => (narrow ? openPlayer(r, scope) : setPeekId(peekId === r.id ? null : r.id))} />
              <div class="dk-foot"><span>${sortSentence(view, ctx)} Click a row to see the player beside the list.</span><${ShadeKey} /></div>`}
      </section>
      ${peeked ? html`<${Peek} row=${peeked} ctx=${ctx} season=${scope.season} picked=${picks.has(peeked.id)} onPick=${onPick} onClose=${() => setPeekId(null)} />` : null}
    </div>
    ${!isFiltered && view.view === "table" && d.highlights?.length ? html`<section class="dk-below"><div class="section-title"><h2>Worth a look in this selection</h2></div><${Insights} items=${d.highlights} scope=${scope} limit=${3} compact expandable /></section>` : null}
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
