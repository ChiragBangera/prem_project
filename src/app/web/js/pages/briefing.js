// Briefing: the page you open first. Findings lead; evidence follows.
import { useMedia } from "../lib/media.js";
import { html, useMemo } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useMeta, useScope } from "../lib/scope.js";
import { href, navigate } from "../lib/router.js";
import { plural } from "../lib/format.js";
import { Icon } from "../lib/icons.js";
import { Async, Card, DataNotices, Form, Insights, PageHead, Section, TeamName, useDocumentTitle } from "../ui/common.js";
import { shortlistStore, useStore } from "../lib/store.js";
import { DataTable } from "../ui/table.js";
import { MetricCell, PlayerCell, ScoreCell, TagCell } from "../ui/cells.js";
import { FixtureRow, GapCell, MoverRow } from "../ui/blocks.js";
import { MatchCard, kickoff } from "../ui/matchcard.js";
import { buildContext } from "../ui/explore/model.js";

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

/** The table at a glance: where each side stands and how far its points sit from the chances it has made. */
function TableSnapshot({ table, scope }) {
  const n = table.length;
  const cols = [
    { key: "rank", label: "#", num: true, width: "38px", firstDir: "asc", render: (r) => html`<span class="rank">${r.rank}</span>` },
    { key: "team", label: "Team", firstDir: "asc", render: (r) => html`<${TeamName} team=${r.team} short=${r.short} size=${20} />` },
    { key: "played", label: "P", num: true },
    { key: "pts", label: "Pts", num: true, className: "strong" },
    { key: "xpts_gap", label: "Pts − xPts", num: true, render: (r) => html`<${GapCell} value=${r.xpts_gap} max=${Math.max(8, ...table.map((t) => Math.abs(t.xpts_gap)))} />`,
      title: "Points won minus the points the chances earned (every match replayed from its shots). Blue: more than earned. Orange: fewer." },
    { key: "form", label: "Form", sortable: false, render: (r) => html`<${Form} items=${r.form} />`, title: "Last five results, oldest to newest." },
  ];
  return html`<${Card} flush title="The table" sub="Points, and how far they sit from what the chances earned"
    actions=${html`<a class="link small" href=${href("/league")}>Full table</a>`}>
    <${DataTable} columns=${cols} rows=${table} rowKey=${(r) => r.team} initialSort=${{ key: "rank", dir: "asc" }} tight caption="League table at a glance"
      onRowClick=${(r) => navigate(`/team/${encodeURIComponent(r.team)}`, { league: scope.league, season: scope.season })}
      zone=${(r) => (r.rank <= scope.ucl_places ? "ucl" : r.rank > n - scope.relegation_places ? "rel" : "none")} />
  </${Card}>`;
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
  // on a phone the findings and the table are one column: six findings put the table five screens down, three leave it within reach
  const shown = useMedia("(max-width: 860px)") ? 3 : 6;
  return html`
    <${PageHead} eyebrow=${`${scope.league_name} · ${scope.label} · Matchweek ${scope.rounds_played} of ${scope.rounds_total}${scope.complete ? " · final" : ""}`}
      title="Briefing" sub=${headline(d)} />
    <span class="wide-page" hidden></span>
    <${DataNotices} scope=${scope} meta=${meta} />

    <div class="mrow brief-lead">
      <${Section} title="What stands out" sub=${`${Math.min(shown, insights.length)} of ${plural(insights.length, "finding")}, ranked by how far they sit from expectation`}>
        <${Insights} items=${insights} scope=${scope} limit=${shown} expandable />
      </${Section}>
      <${TableSnapshot} table=${table} scope=${scope} />
    </div>

    <${Watchlist} scope=${{ league: scope.league, season: scope.season }} />

    <${Card} title="Latest results" sub=${flagged.length ? `${flagged.length} of ${recent.length} did not follow the chances` : "All followed the chances"} actions=${html`<a class="link small" href=${href("/matches")}>All matchweeks</a>`}>
      <div class="mgrid brief-grid">${recent.slice(0, 10).map((m) => html`<${MatchCard} key=${m.id} m=${m} />`)}</div>
    </${Card}>

    <div class="mrow m-5-7">
      ${upcoming.length ? html`<${Card} flush title="Next fixtures" sub="Kickoff in your time zone, with each side's league position, form and chance difference" actions=${html`<a class="link small" href=${href("/matches")}>Schedule</a>`}>
        <div class="fixtures">${upcoming.slice(0, 6).map((f) => html`<${FixtureRow} key=${f.id} f=${f} />`)}</div>
      </${Card}>` : html`<span></span>`}
      <div class="stack" style=${{ "--gap": "20px" }}>
        ${movers.risers.length || movers.fallers.length ? html`<${Card} title="Movers" sub=${`Table position over the last ${movers.span} matchweeks`}>
          <div class="movers two">
            <div class="movers">${movers.risers.map((m) => html`<${MoverRow} key=${m.team} m=${m} up=${true} />`)}</div>
            <div class="movers">${movers.fallers.map((m) => html`<${MoverRow} key=${m.team} m=${m} up=${false} />`)}</div>
          </div>
        </${Card}>` : null}
        <${Section} title="From the scouting board" sub="Players whose numbers say something">
          <${Insights} items=${highlights} scope=${scope} limit=${4} compact />
          <a class="link" href=${href("/scout")}>Open the scouting board <${Icon} name="arrowRight" size="sm" /></a>
        </${Section}>
      </div>
    </div>
  `;
}

export default function Briefing() {
  const { league, season } = useScope();
  const q = useApi("/api/briefing", { league, season });
  useDocumentTitle("Briefing");
  return html`<${Async} q=${q}>${(d) => html`<${BriefingView} d=${d} />`}</${Async}>`;
}
