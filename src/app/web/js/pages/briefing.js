// Briefing: the page you open first. Findings lead; evidence follows.
import { html, useMemo } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useMeta, useScope } from "../lib/scope.js";
import { href, navigate } from "../lib/router.js";
import { nf, plural, signed } from "../lib/format.js";
import { Icon } from "../lib/icons.js";
import { Async, Card, Crest, DataNotices, Insights, PageHead, Section, useDocumentTitle } from "../ui/common.js";
import { shortlistStore, useStore } from "../lib/store.js";
import { DataTable } from "../ui/table.js";
import { MetricCell, PlayerCell, ScoreCell, TagCell } from "../ui/cells.js";
import { FixtureRow, MoverRow } from "../ui/blocks.js";
import { MatchCard, kickoff } from "../ui/matchcard.js";
import { buildContext } from "../ui/explore/model.js";
import { DivergingBars } from "../charts/bars.js";
import { Tip } from "../lib/tooltip.js";

function headline(d) {
  const { table, scope, context } = d;
  const [a, b] = table;
  if (!a) return "";
  if (scope.complete) return `${a.team} won the ${scope.label} title by ${plural(a.pts - b.pts, "point")}.`;
  const left = scope.rounds_total - scope.rounds_played;
  const gap = a.pts - b.pts;
  const lead = gap === 0 ? `${a.team} and ${b.team} are level on ${a.pts} points` : `${a.team} lead ${b.team} by ${plural(gap, "point")}`;
  let next = "";
  if (context.next_kickoff) {
    const k = kickoff({ utc: `${context.next_kickoff.slice(0, 10)}T${context.next_kickoff.slice(11, 19)}Z`, date: context.next_kickoff.slice(0, 10), dt: context.next_kickoff });
    next = ` Next kickoff: ${k.day}, ${k.time}.`;
  }
  return `${lead} with ${plural(left, "matchweek")} left.${next}`;
}

function gapRows(table) {
  return [...table].sort((a, b) => b.xpts_gap - a.xpts_gap).map((t) => ({
    key: t.team, value: t.xpts_gap, team: t,
    label: html`<a class="cell-team" href=${href(`/team/${encodeURIComponent(t.team)}`)}><${Crest} team=${t.team} short=${t.short} size=${20} /><span class="truncate">${t.team}</span></a>`,
  }));
}

/** The players you track, with this season's numbers: the briefing is for you, not for the league in general. */
function Watchlist({ scope }) {
  const items = useStore(shortlistStore, (s) => s.items);
  const { catalog } = useMeta();
  const leagues = [...new Set(items.map((i) => i.league || "EPL"))];
  const q = useApi("/api/players", { leagues, seasons: [scope.season === "auto" || !scope.season ? "auto" : scope.season], min_minutes: 1 }, { enabled: items.length > 0 });
  const ctx = useMemo(() => (q.data && catalog ? buildContext("player", q.data, catalog) : null), [q.data, catalog]);
  if (!items.length || !q.data || !ctx) return null;
  const byId = new Map(q.data.rows.map((r) => [r.id, r]));
  const rows = items.map((it) => byId.get(it.id)).filter(Boolean).slice(0, 6);
  if (!rows.length) return null;
  const keys = ["npxg90", "xa90", "g_xg"];
  const cols = [
    { key: "name", label: "Player", sticky: true, render: (r) => html`<${PlayerCell} row=${r} ctx=${ctx} season=${scope.season} />` },
    { key: "output", label: "Role score", num: true, render: (r) => html`<${ScoreCell} row=${r} />` },
    ...keys.map((k) => ({ key: k, label: ctx.metrics[k].short, num: true, title: ctx.metrics[k].what, render: (r) => html`<${MetricCell} row=${r} ctx=${ctx} k=${k} />` })),
    { key: "tags", label: "Profile", sortable: false, render: (r) => html`<${TagCell} row=${r} />` },
  ];
  return html`<${Section} title="Your shortlist" sub=${`${items.length} tracked`} actions=${html`<a class="link small" href=${href("/shortlist")}>Open shortlist</a>`}>
    <${Card} flush><${DataTable} columns=${cols} rows=${rows} rowKey=${(r) => r.id} tight caption="Shortlisted players" onRowClick=${(r) => navigate(`/player/${r.id}`, { league: r.league, season: scope.season })} /></${Card}>
  </${Section}>`;
}

function BriefingView({ d }) {
  const { scope, meta, table, upcoming, recent, movers, insights, highlights } = d;
  const flagged = recent.filter((m) => m.flag);
  return html`
    <${PageHead} eyebrow=${`${scope.league_name} · ${scope.label} · Matchweek ${scope.rounds_played} of ${scope.rounds_total}${scope.complete ? " · final" : ""}`}
      title="Briefing" sub=${headline(d)} />
    <${DataNotices} scope=${scope} meta=${meta} />

    <${Section} title="What stands out" sub=${`${insights.length} findings, ranked by how far they sit from expectation`}>
      <${Insights} items=${insights} scope=${scope} limit=${6} />
    </${Section}>

    <${Watchlist} scope=${{ league: scope.league, season: scope.season }} />

    <div class="grid cols-main-side top">
      <${Section} title="Latest results" sub=${flagged.length ? `${flagged.length} of ${recent.length} did not follow the chances` : "All followed the chances"} actions=${html`<a class="link small" href=${href("/matches")}>All matchweeks</a>`}>
        <div class="mgrid brief-grid">${recent.slice(0, 6).map((m) => html`<${MatchCard} key=${m.id} m=${m} />`)}</div>
      </${Section}>
      <div class="stack">
        ${upcoming.length ? html`<${Card} flush title="Next fixtures" sub="Kickoff in your time zone, with each side's league position, form and chance difference" actions=${html`<a class="link small" href=${href("/matches")}>Schedule</a>`}>
          <div class="fixtures">${upcoming.slice(0, 6).map((f) => html`<${FixtureRow} key=${f.id} f=${f} />`)}</div>
        </${Card}>` : null}
        ${movers.risers.length || movers.fallers.length ? html`<${Card} title="Movers" sub=${`Table position over the last ${movers.span} matchweeks`}>
          <div class="movers">
            ${movers.risers.map((m) => html`<${MoverRow} key=${m.team} m=${m} up=${true} />`)}
            ${movers.fallers.map((m) => html`<${MoverRow} key=${m.team} m=${m} up=${false} />`)}
          </div>
        </${Card}>` : null}
      </div>
    </div>

    <div class="grid cols-wide-narrow top">
      <${Card} title="Points against expected points"
        sub="Expected points replay every shot of every match. Blue: more points than the chances earned. Orange: fewer.">
        <${DivergingBars} rows=${gapRows(table)} format=${(v) => signed(v, 1)}
          tip=${(r) => html`<${Tip} title=${r.team.team} rows=${[
            { label: "Points", value: r.team.pts }, { label: "Expected points", value: nf(r.team.xpts, 1) },
            { label: "Table rank", value: r.team.rank }, { label: "Rank on expected points", value: r.team.rank_xpts },
          ]} />`} />
      </${Card}>
      <${Section} title="From the scouting board" sub="Players whose numbers say something">
        <div class="stack" style=${{ "--gap": "10px" }}><${Insights} items=${highlights} scope=${scope} limit=${4} compact /></div>
        <a class="link" href=${href("/scout")}>Open the scouting board <${Icon} name="arrowRight" size="sm" /></a>
      </${Section}>
    </div>
  `;
}

export default function Briefing() {
  const { league, season } = useScope();
  const q = useApi("/api/briefing", { league, season });
  useDocumentTitle("Briefing");
  return html`<${Async} q=${q}>${(d) => html`<${BriefingView} d=${d} />`}</${Async}>`;
}
