// Briefing: the page you open first. Findings lead; evidence follows.
import { html } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useMeta, useScope } from "../lib/scope.js";
import { href, navigate } from "../lib/router.js";
import { dateShort, nf, plural, probText, signed, timeOf, weekday } from "../lib/format.js";
import { Icon } from "../lib/icons.js";
import { Async, Card, Crest, DataNotices, Insights, PageHead, Section, Segmented, TeamName, useDocumentTitle } from "../ui/common.js";
import { shortlistStore, useStore } from "../lib/store.js";
import { DataTable } from "../ui/table.js";
import { PctCell, PlayerCell, ScoreCell, TagCell } from "../ui/cells.js";
import { FixtureRow, MoverRow, RaceList, ResultItem } from "../ui/blocks.js";
import { DivergingBars } from "../charts/bars.js";
import { Tip } from "../lib/tooltip.js";

function headline(d) {
  const { table, race, scope, context } = d;
  const [a, b] = table;
  if (!a) return "";
  if (scope.complete) return `${a.team} won the ${scope.label} title by ${plural(a.pts - b.pts, "point")}.`;
  const left = scope.rounds_total - scope.rounds_played;
  const gap = a.pts - b.pts;
  const lead = gap === 0 ? `${a.team} and ${b.team} are level on ${a.pts} points` : `${a.team} lead ${b.team} by ${plural(gap, "point")}`;
  const odds = race?.find((r) => r.team === a.team);
  const oddsText = odds && odds.p_title >= 0.01 ? ` The simulation gives them ${probText(odds.p_title)} to win the title.` : "";
  const next = context.next_kickoff ? ` Next kickoff: ${weekday(context.next_kickoff)} ${dateShort(context.next_kickoff)}, ${timeOf(context.next_kickoff)}.` : "";
  return `${lead} with ${plural(left, "matchweek")} left.${oddsText}${next}`;
}

function liveRaces(race, scope) {
  if (!race) return null;
  const by = (key, lo, hi) => race.filter((r) => r[key] >= lo && r[key] <= hi).sort((x, y) => y[key] - x[key]).map((r) => ({ team: r.team, short: r.short, p: r[key] }));
  const count = (test) => race.filter(test).length;
  const title = by("p_title", 0.005, 1);
  const top4 = by("p_top4", 0.03, 0.97);
  const rel = by("p_relegation", 0.03, 0.97);
  const in4 = count((r) => r.p_top4 > 0.97), out4 = count((r) => r.p_top4 < 0.03);
  const down = count((r) => r.p_relegation > 0.97), safe = count((r) => r.p_relegation < 0.03);
  return {
    ucl: scope.ucl_places, relN: scope.relegation_places,
    title: title.slice(0, 6), titleFoot: `${race.length - title.length} other teams are below 0.5%.`,
    top4: top4.slice(0, 7), top4Foot: [in4 ? `${in4} all but in` : "", out4 ? `${out4} out of reach` : ""].filter(Boolean).join(" · "),
    rel: rel.slice(0, 7), relFoot: [down ? `${down} all but down` : "", safe ? `${safe} safe` : ""].filter(Boolean).join(" · "),
  };
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
  const q = useApi("/api/players", { leagues, seasons: [scope.season === "auto" || !scope.season ? "auto" : scope.season], min_minutes: 90 }, { enabled: items.length > 0 });
  if (!items.length || !q.data) return null;
  const byId = new Map(q.data.rows.map((r) => [r.id, r]));
  const rows = items.map((it) => byId.get(it.id)).filter(Boolean).slice(0, 6);
  if (!rows.length) return null;
  const cols = [
    { key: "name", label: "Player", sticky: true, render: (r) => html`<${PlayerCell} row=${r} season=${scope.season} />` },
    { key: "output", label: "Role score", num: true, render: (r) => html`<${ScoreCell} row=${r} />` },
    { key: "contrib90", label: catalog.metrics.contrib90.short, num: true, render: (r) => html`<${PctCell} row=${r} metric="contrib90" def=${catalog.metrics.contrib90} />` },
    { key: "g_xg", label: "G − xG", num: true, render: (r) => html`<span class=${"luckcell"}><span class=${"delta-val " + (r.g_xg > 0.5 ? "pos" : r.g_xg < -0.5 ? "neg" : "")}>${signed(r.g_xg, 1)}</span><span class="muted xsmall">z ${signed(r.g_xg_z, 1)}</span></span>` },
    { key: "tags", label: "Profile", sortable: false, render: (r) => html`<${TagCell} row=${r} />` },
  ];
  return html`<${Section} title="Your shortlist" sub=${`${items.length} tracked`} actions=${html`<a class="link small" href=${href("/shortlist")}>Open shortlist</a>`}>
    <${Card} flush><${DataTable} columns=${cols} rows=${rows} rowKey=${(r) => r.id} tight caption="Shortlisted players" onRowClick=${(r) => navigate(`/player/${r.id}`, { league: r.league, season: scope.season })} /></${Card}>
  </${Section}>`;
}

function BriefingView({ d }) {
  const { scope, meta, context, table, race, upcoming, recent, movers, insights, highlights } = d;
  const races = liveRaces(race, scope);
  const flagged = recent.filter((m) => m.flag);
  return html`
    <${PageHead} eyebrow=${`${scope.league_name} · ${scope.label} · Matchweek ${scope.rounds_played} of ${scope.rounds_total}${scope.complete ? " · final" : ""}`}
      title="Briefing" sub=${headline(d)} />
    <${DataNotices} scope=${scope} meta=${meta} />

    <${Section} title="What stands out" sub=${`${insights.length} findings, ranked by how far they sit from expectation`}>
      <${Insights} items=${insights} scope=${scope} limit=${6} />
    </${Section}>

    <${Watchlist} scope=${{ league: scope.league, season: scope.season }} />

    ${races ? html`<${Section} title="The run-in" sub=${`The season replayed thousands of times from the ${plural(context.matches_total - context.matches_played, "match", "matches")} still to play`}>
      <div class="card runin">
        <${RaceList} title="Title" sub="Chance to finish first" rows=${races.title} foot=${races.titleFoot} empty="Nobody has a realistic title chance." />
        <${RaceList} title=${`Top ${races.ucl}`} sub="Champions League places" rows=${races.top4} foot=${races.top4Foot} empty="The top four looks settled." />
        <${RaceList} title="Relegation" sub=${`Bottom ${races.relN}`} rows=${races.rel} foot=${races.relFoot} empty="Relegation looks settled." />
      </div>
    </${Section}>` : null}

    <div class="grid cols-main-side top">
      <${Card} title=${upcoming.length ? "Next fixtures" : "Results"} sub=${upcoming.length ? "Probabilities from the ratings model, not from the bookmakers" : "The season is over"}
        actions=${html`<a class="link small" href=${href("/forecast")}>All forecasts</a>`} flush>
        ${upcoming.length
          ? html`<div class="fixtures">${upcoming.map((f) => html`<${FixtureRow} key=${f.id} f=${f} />`)}</div>`
          : html`<div class="results">${recent.map((m) => html`<${ResultItem} key=${m.id} m=${m} />`)}</div>`}
      </${Card}>
      <div class="stack">
        ${upcoming.length ? html`<${Card} title="Latest results" sub=${flagged.length ? `${flagged.length} of ${recent.length} did not follow the chances` : "All followed the chances"} flush>
          <div class="results">${recent.slice(0, 5).map((m) => html`<${ResultItem} key=${m.id} m=${m} />`)}</div>
          <div class="card-foot"><a class="link" href=${href("/matches")}>All matchweeks</a></div>
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
