// Teams: find clubs by how they play and how they are doing. The same desk as Scout, one level up: every filter in a rail on the left, the
// table from the top of the screen, and one team at a glance on the right. Every team is listed until you narrow it down.
import { html, useMemo, useState } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useScope, useMeta, leagueName } from "../lib/scope.js";
import { href, useLocation } from "../lib/router.js";
import { cls, plural } from "../lib/format.js";
import { useMedia } from "../lib/media.js";
import { TOP_CHOICES } from "../lib/filters.js";
import { Icon } from "../lib/icons.js";
import { Async, Button, DataNotices, EmptyState, Notice, Segmented, Select, useDocumentTitle } from "../ui/common.js";
import { FormCell, TeamCell } from "../ui/cells.js";
import { CsvButton } from "../ui/table.js";
import { useExplorer, sortSentence, openTeam } from "../ui/explore/model.js";
import { Rail } from "../ui/explore/Rail.js";
import { ShadeKey, Sheet } from "../ui/explore/Sheet.js";
import { TeamPeek } from "../ui/explore/Peek.js";
import { ColumnPicker } from "../ui/explore/ColumnPicker.js";
import { MetricMap } from "../ui/explore/MetricMap.js";
import { ScopePicker, scopeFromQuery } from "../ui/explore/Scope.js";

function Coverage({ d }) {
  const c = d.coverage;
  const notes = [];
  if (c.event_teams === 0) notes.push(html`No event data is stored for this selection, so style measures (possession, passing, pressing, carries) are blank, never zero. <a class="link" href=${href("/data")}>See how it is fetched</a>.`);
  else if (c.event_teams < c.teams) notes.push(html`Event data is stored for ${c.event_teams} of ${c.teams} teams here; the rest are blank on event measures.`);
  if (c.shot_teams < c.teams) notes.push(html`Shot measures need every match page of a season, which ${c.teams - c.shot_teams} teams do not have yet: they fill in as the pages download.`);
  return notes.length ? html`<${Notice} icon="clock">${notes.map((n, i) => html`<span key=${i}>${i ? " " : ""}${n}</span>`)}</${Notice}>` : null;
}

const FORM = { key: "form", label: "Form", width: 118, align: "left", className: "left", title: "The last five results, oldest first.", render: (r) => html`<${FormCell} items=${r.form} />` };

function TeamsView({ d, scope, meta, catalog, query, active }) {
  const model = useExplorer({ level: "team", payload: d, catalog, query });
  const { ctx, view, sorted, shown, columns, chips, setView, setFilters, isFiltered } = model;
  const narrow = useMedia("(max-width: 1000px)");
  const phone = useMedia("(max-width: 720px)");   // a phone's first screen shows the team and the measures; the form guide is on the team's page
  const [peekKey, setPeekKey] = useState(null);
  const [railOpen, setRailOpen] = useState(false);
  const peeked = peekKey != null && !narrow ? sorted.find((r) => r.key === peekKey) : null;
  const config = useMemo(() => ({ level: "team", kind: "team", noun: "teams", searchPlaceholder: "Search by team" }), []);
  const leagues = d.scope.leagues.map((l) => leagueName(meta, l));
  const where = `${leagues.join(" + ")}, ${d.scope.labels.join(", ")}`;
  const mixed = new Set(d.rows.map((r) => `${r.league}:${r.season}`)).size > 1;

  // the columns: the set in view, with the measure the list is sorted by first when it is not among them
  const keys = useMemo(() => {
    const set = columns.keys;
    const pin = ctx.metrics[view.sort] && ctx.idx[view.sort] !== undefined && !set.includes(view.sort) ? [view.sort] : [];
    return [...(phone ? [] : [FORM]), ...pin, ...set];
  }, [columns.keys.join(), view.sort, ctx, phone]);
  const lead = { label: "Team", width: narrow ? 190 : 250, sortKey: "rank", firstDir: "asc",
    render: (r) => html`<div class="dk-who"><span class="dk-rank" title="Position in its league">${r.rank ?? "–"}</span><${TeamCell} row=${r} sub=${mixed ? `${leagueName(meta, r.league)}${r.season ? ` ${r.season}/${String(r.season + 1).slice(-2)}` : ""}` : null} /></div>` };
  const csv = [{ label: "Position", value: (r) => r.rank }, { label: "Team", value: (r) => r.team }, { label: "League", value: (r) => r.league }, { label: "Season", value: (r) => r.season },
    ...keys.filter((c) => typeof c === "string").map((k) => ({ label: ctx.metrics[k].label, value: (r) => r.v[ctx.idx[k]] }))];
  const capped = view.top > 0 && sorted.length > view.top;
  const topOptions = [{ value: "0", label: "Every team" }, ...[...new Set([...TOP_CHOICES.filter((n) => n < d.rows.length), ...(view.top > 0 ? [view.top] : [])])].sort((a, b) => a - b).map((n) => ({ value: String(n), label: `Top ${n}` }))];

  const head = html`<div class="dk-railhead"><h1>Teams</h1><p>${where}. ${plural(d.rows.length, "team")}, ranked on ${ctx.order.length} measures. A rank compares a team only with the others in its own league and season.</p>
    <div class="row wrap" style=${{ gap: "6px" }}><${ScopePicker} meta=${meta} active=${active} resolvedLabels=${d.scope.labels} />
      <${Button} size="sm" class="dk-railtoggle" icon="filter" onClick=${() => setRailOpen(!railOpen)}>${railOpen ? "Hide filters" : `Filters${chips.length ? ` (${chips.length})` : ""}`}</${Button}></div></div>`;

  return html`
    <${DataNotices} scope=${{ note: d.scope.notes?.[0] }} meta=${d.meta} />
    <${Coverage} d=${d} />
    <div class=${cls("desk", "full", peeked && "peeking", railOpen && "rail-open")}>
      <${Rail} model=${model} allRows=${d.rows} config=${config} head=${head} path="/teams" query=${query} />
      <section class="dk-main" aria-label="Teams">
        <div class="results-bar">
          <span class="dk-count"><b class="rb-title">${capped ? `Top ${shown.length} of ${sorted.length}` : sorted.length} teams</b>${isFiltered ? html`<span class="muted small">of ${d.rows.length}</span>` : html`<span class="muted small">every team, no filters</span>`}</span>
          <div class="rb-controls">
            <${Select} compact value=${String(view.top)} label="How many to show" options=${topOptions} onChange=${(v) => setView({ top: Number(v) })} />
            <${Segmented} small label="View" options=${[{ value: "table", label: "Table" }, { value: "map", label: "Map" }]} value=${view.view} onChange=${(v) => setView({ view: v })} />
            <${CsvButton} columns=${csv} rows=${shown} filename="prem-lab-teams.csv" />
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
          ? html`<${EmptyState} title="No teams match these filters" text="Remove a filter above the table, or clear them all."
              action=${isFiltered ? html`<${Button} onClick=${model.clearFilters}>Clear all filters</${Button}>` : null} />`
          : view.view === "map"
            ? html`<div class="dk-scroll"><div class="card-body"><${MetricMap} model=${model} level="team" scope=${scope} noun="teams" labelCount=${40} onOpen=${openTeam} /></div></div>`
            : html`<${Sheet} model=${model} lead=${lead} keys=${keys} rowKey=${(r) => r.key} picked=${peeked?.key ?? null} caption="Teams" peers="the league"
                onPick=${(r) => (narrow ? openTeam(r) : setPeekKey(peekKey === r.key ? null : r.key))} />
              <div class="dk-foot"><span>${sortSentence(view, ctx)} Click a row to see the team beside the list.</span><${ShadeKey} peers="the league" /></div>`}
      </section>
      ${peeked ? html`<${TeamPeek} row=${peeked} ctx=${ctx} leagueName=${leagueName(meta, peeked.league)} pool=${d.scope.pools?.[`${peeked.league}:${peeked.season}`]} onClose=${() => setPeekKey(null)} />` : null}
    </div>
  `;
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
