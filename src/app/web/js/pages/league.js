// League: standings read three ways (results, expected, style) plus two charts that explain them.
import { html, useMemo } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useScope } from "../lib/scope.js";
import { href, navigate, setQuery, useLocation } from "../lib/router.js";
import { nf, ordinal, plural, signed } from "../lib/format.js";
import { Tip } from "../lib/tooltip.js";
import { Async, Card, DataNotices, Form, Insights, PageHead, Segmented, Select, TeamName, useDocumentTitle } from "../ui/common.js";
import { CsvButton, DataTable } from "../ui/table.js";
import { GapCell } from "../ui/blocks.js";
import { Sparkline, RankChart, SERIES_COLORS } from "../charts/lines.js";
import { Icon } from "../lib/icons.js";
import { useStableSlots } from "../lib/slots.js";
import { Scatter } from "../charts/scatter.js";

const VIEWS = [
  { value: "standings", label: "Standings" },
  { value: "expected", label: "Expected" },
  { value: "style", label: "Style" },
];

function columnsFor(view) {
  const team = { key: "team", label: "Team", sticky: true, firstDir: "asc", render: (r) => html`<${TeamName} team=${r.team} short=${r.short} />` };
  const rank = { key: "rank", label: "#", num: true, width: "46px", firstDir: "asc", render: (r) => html`<span class="rank">${r.rank}</span>` };
  if (view === "expected") {
    return [
      rank, team,
      { key: "pts", label: "Pts", num: true, className: "strong", title: "Points won." },
      { key: "xpts", label: "xPts", num: true, value: (r) => r.xpts, render: (r) => nf(r.xpts, 1), title: "Points the chances deserved: every match replayed thousands of times from its shots." },
      { key: "xpts_gap", label: "Pts − xPts", num: true, render: (r) => html`<${GapCell} value=${r.xpts_gap} max=${14} />`, title: "Blue: more points than the chances earned (fortunate). Orange: fewer (unfortunate)." },
      { key: "rank_xpts", label: "Rank on xPts", num: true, firstDir: "asc", title: "Where the table would look on expected points, and how far that is from the real one.",
        render: (r) => html`<span class="num">${r.rank_xpts}</span> ${r.rank_gap === 0 ? html`<span class="muted xsmall">same</span>` : html`<span class=${"delta-val xsmall " + (r.rank_gap > 0 ? "pos" : "neg")}>${r.rank_gap > 0 ? "▲" : "▼"}${Math.abs(r.rank_gap)}</span>`}` },
      { key: "xgd", label: "xGD", num: true, render: (r) => signed(r.xgd, 1), title: "xG minus xGA over the games shown." },
      { key: "g_xg", label: "Goals − xG", num: true, render: (r) => html`<${GapCell} value=${r.g_xg} max=${16} />`, title: "Attack luck: goals scored above the chances created." },
      { key: "xga_ga", label: "xGA − GA", num: true, render: (r) => html`<${GapCell} value=${r.xga_ga} max=${16} />`, title: "Defence luck: fewer goals conceded than the chances allowed (positive is fortunate)." },
    ];
  }
  if (view === "style") {
    return [
      { ...rank, key: "rank_style", label: "#", value: (r) => r.rank, render: (r) => html`<span class="rank">${r.rank}</span>` }, team,
      { key: "xg_pg", label: "xG/g", num: true, render: (r) => nf(r.xg_pg, 2), heat: { domain: [0.8, 2.4] }, title: "Expected goals created per game." },
      { key: "xga_pg", label: "xGA/g", num: true, render: (r) => nf(r.xga_pg, 2), heat: { domain: [0.8, 2.2], invert: true }, title: "Expected goals conceded per game. Lower is better." },
      { key: "xgd_pg", label: "xGD/g", num: true, render: (r) => signed(r.xgd_pg, 2), heat: { domain: [-1.2, 1.2], mode: "div" }, title: "Net chance quality per game." },
      { key: "ppda", label: "PPDA", num: true, render: (r) => nf(r.ppda, 1), heat: { domain: [6, 16], invert: true }, title: "Opponent passes allowed per defensive action. Lower means a more intense press." },
      { key: "oppda", label: "Opp. PPDA", num: true, render: (r) => nf(r.oppda, 1), heat: { domain: [6, 16] }, title: "The same measure for the pressing this team faces. Higher means opponents let them play." },
      { key: "deep_pg", label: "Deep comp./g", num: true, render: (r) => nf(r.deep_pg, 1), heat: { domain: [6, 18] }, title: "Passes completed within about 20 yards of the opponent's goal." },
      { key: "deep_allowed_pg", label: "Deep allowed/g", num: true, render: (r) => nf(r.deep_allowed_pg, 1), heat: { domain: [6, 16], invert: true }, title: "Deep completions the opposition manage against them. Lower is better." },
    ];
  }
  return [
    rank, team,
    { key: "played", label: "P", num: true },
    { key: "w", label: "W", num: true, className: "subtle-cell" },
    { key: "d", label: "D", num: true, className: "subtle-cell" },
    { key: "l", label: "L", num: true, className: "subtle-cell" },
    { key: "gf", label: "GF", num: true },
    { key: "ga", label: "GA", num: true },
    { key: "gd", label: "GD", num: true, render: (r) => signed(r.gd, 0) },
    { key: "pts", label: "Pts", num: true, className: "strong" },
    { key: "form", label: "Form", sortable: false, render: (r) => html`<${Form} items=${r.form} />`, title: "Last five results, oldest to newest." },
    { key: "xpts", label: "xPts", num: true, render: (r) => nf(r.xpts, 1), title: "Points the chances deserved." },
    { key: "xpts_gap", label: "Pts − xPts", num: true, render: (r) => html`<${GapCell} value=${r.xpts_gap} max=${14} />`, title: "Blue: more points than the chances earned. Orange: fewer." },
    { key: "trend_xgd", label: "xGD trend", sortable: false, render: (r) => html`<${Sparkline} values=${r.trend_xgd} baseline=${0} color="var(--c1)" label=${`${r.team} rolling xG difference`} />`, title: "Rolling chance difference through the season. Above the dotted line is a winning trend." },
  ];
}

function headline(table) {
  if (!table.length) return "";
  const gap = [...table].sort((a, b) => a.xpts_gap - b.xpts_gap);
  const worst = gap[0], best = gap[gap.length - 1];
  const bits = [];
  if (worst.xpts_gap < -3) bits.push(`${worst.team} are ${ordinal(worst.rank)} but the chances say ${ordinal(worst.rank_xpts)} (${signed(worst.xpts_gap, 1)} points against expectation)`);
  if (best.xpts_gap > 3) bits.push(`${best.team} have ${nf(best.xpts_gap, 1)} more points than their chances earned`);
  return bits.length ? bits.join("; ") + "." : "Results and chances broadly agree across the table.";
}

function TeamMap({ table, follow, colorOf, scope }) {
  const avgX = table.reduce((s, t) => s + t.xg_pg, 0) / table.length;
  const avgY = table.reduce((s, t) => s + t.xga_pg, 0) / table.length;
  const points = table.map((t) => ({ id: t.team, x: t.xg_pg, y: t.xga_pg, label: t.short, highlight: follow.includes(t.team), color: follow.includes(t.team) ? colorOf(t.team) : undefined, data: t }));
  return html`<${Scatter} points=${points} mark="pill" invertY=${true} refX=${avgX} refY=${avgY} height=${400}
    xLabel="Chances created per game (xG) →" yLabel="← Chances allowed per game (xGA)"
    corners=${{ tr: "Dominant", tl: "Defence-led", br: "Attack-led", bl: "Struggling" }} hoverPad=${22}
    label="Attack versus defence, one marker per team"
    onSelect=${(p) => navigate(`/team/${encodeURIComponent(p.id)}`, { league: scope.league, season: scope.season })}
    renderTip=${(p) => html`<${Tip} title=${p.data.team} sub=${`${ordinal(p.data.rank)} · ${p.data.pts} pts`} rows=${[
      { label: "xG per game", value: nf(p.data.xg_pg, 2) }, { label: "xGA per game", value: nf(p.data.xga_pg, 2) }, { label: "xG difference / game", value: signed(p.data.xgd_pg, 2) },
    ]} />`} />`;
}

function LeagueView({ d, query }) {
  const { scope, meta, table, trajectories, insights } = d;
  const view = VIEWS.some((v) => v.value === query.view) ? query.view : "standings";
  const teamNames = table.map((t) => t.team);
  // default: follow the top three so the chart opens on the title race; "none" clears it
  const follow = query.follow === "none" ? [] : query.follow ? query.follow.split("|").filter((t) => teamNames.includes(t)).slice(0, 4) : table.slice(0, 3).map((t) => t.team);
  const setFollow = (list) => setQuery({ follow: list.length ? list.join("|") : "none" });
  const toggleFollow = (t) => setFollow(follow.includes(t) ? follow.filter((x) => x !== t) : [...follow, t].slice(-4));
  const slotOf = useStableSlots(follow);
  const colorOf = (t) => SERIES_COLORS[slotOf(t)];
  const columns = useMemo(() => columnsFor(view), [view]);
  const initialSort = view === "style" ? { key: "xgd_pg", dir: "desc" } : { key: view === "expected" ? "xpts_gap" : "rank", dir: view === "expected" ? "desc" : "asc" };
  const ucl = scope.ucl_places, rel = scope.relegation_places, n = table.length;
  const filtered = d.filter.venue !== "all" || d.filter.last;
  const scopeLine = [d.filter.venue !== "all" ? `${d.filter.venue === "h" ? "home" : "away"} matches only` : "", d.filter.last ? `last ${d.filter.last} games` : ""].filter(Boolean).join(", ");

  return html`
    <${PageHead} eyebrow=${`${scope.league_name} · ${scope.label} · after ${plural(scope.rounds_played, "matchweek")}`} title="League table" sub=${headline(table)}
      actions=${html`<a class="btn" href=${href("/teams", { lg: scope.league, ss: String(scope.season) })} title="Filter, rank and map every team measure: possession, pressing, set pieces ..."><span>All team measures</span></a><${CsvButton} columns=${columns} rows=${table} filename=${`${scope.league}-${scope.season}-table.csv`} />`} />
    <${DataNotices} scope=${scope} meta=${meta} />
    <${Insights} items=${insights} scope=${scope} limit=${3} />

    <${Card} flush title=${VIEWS.find((v) => v.value === view).label}
      sub=${scopeLine ? `Filtered: ${scopeLine}. Positions and points reflect only those games.` : view === "standings" ? "Sorted by position. Click any header to re-sort." : view === "expected" ? "Where results and chances part ways." : "How each team plays: press, territory, chance quality."}
      actions=${html`<div class="row wrap" style=${{ gap: "8px" }}>
        <${Segmented} label="Table view" options=${VIEWS} value=${view} onChange=${(v) => setQuery({ view: v === "standings" ? null : v })} small />
        <${Segmented} label="Venue" options=${[{ value: "all", label: "All" }, { value: "h", label: "Home" }, { value: "a", label: "Away" }]} value=${d.filter.venue} onChange=${(v) => setQuery({ venue: v === "all" ? null : v })} small />
        <${Select} compact label="Window" value=${String(d.filter.last || "")} options=${[{ value: "", label: "Whole season" }, { value: "5", label: "Last 5" }, { value: "10", label: "Last 10" }]} onChange=${(v) => setQuery({ last: v || null })} />
      </div>`}>
      <${DataTable} columns=${columns} rows=${table} rowKey=${(r) => r.team} initialSort=${initialSort} dense
        onRowClick=${(r) => navigate(`/team/${encodeURIComponent(r.team)}`, { league: scope.league, season: scope.season })} caption="League table"
        zone=${(r) => (view === "style" ? null : r.rank <= ucl ? "ucl" : r.rank > n - rel ? "rel" : "none")} />
      <div class="card-foot row wrap" style=${{ gap: "18px" }}>
        <span class="legend"><span class="item"><span class="swatch box" style=${{ background: "var(--c1)" }}></span>Champions League places</span><span class="item"><span class="swatch box" style=${{ background: "var(--crit)" }}></span>Relegation places</span></span>
        <span>Click a team for its full profile.</span>
      </div>
    </${Card}>

    <div class="grid cols-2">
      <${Card} title="Attack against defence" sub="Where each team sits on chances created and allowed. Dotted lines are league averages. Click a team to open it.">
        <${TeamMap} table=${table} follow=${follow} colorOf=${colorOf} scope=${scope} />
        <p class="xsmall muted" style=${{ marginTop: "8px" }}>Teams you follow in the race chart are outlined in the same colour. Up and to the right is better.</p>
      </${Card}>
      <${Card} title="The race, matchweek by matchweek" sub="Table position after each round. Click a line to follow it (up to four)."
        actions=${html`<${Select} compact label="Follow a team" value="" options=${[{ value: "", label: "Follow a team…" }, ...[...table].sort((a, b) => a.team.localeCompare(b.team)).map((t) => ({ value: t.team, label: t.team }))]} onChange=${(v) => v && toggleFollow(v)} />`}>
        <${RankChart} series=${trajectories.rank} rounds=${trajectories.rounds} highlight=${follow} nTeams=${n} height=${400}
          zones=${{ ucl, rel }} onPick=${toggleFollow} colorOf=${colorOf}
          shortOf=${(t) => table.find((x) => x.team === t)?.short || t.slice(0, 3).toUpperCase()} />
        <div class="follow-chips">
          ${follow.map((t, i) => html`<button type="button" class="chip" key=${t} onClick=${() => toggleFollow(t)} title="Stop following"><i class="dot" style=${{ background: colorOf(t) }}></i>${t}<${Icon} name="x" /></button>`)}
          ${follow.length ? html`<button type="button" class="chip" onClick=${() => setFollow([])}>Clear</button>` : html`<span class="xsmall muted">Nobody followed. Hover the lines, or pick a team above.</span>`}
          <span class="xsmall muted" style=${{ marginLeft: "auto" }}>Blue band: Champions League places · red band: relegation places</span>
        </div>
      </${Card}>
    </div>
  `;
}

export default function League() {
  const { league, season } = useScope();
  const { query } = useLocation();
  const venue = ["h", "a"].includes(query.venue) ? query.venue : "all";
  const last = query.last ? Number(query.last) : undefined;
  const q = useApi("/api/league", { league, season, venue, last });
  useDocumentTitle("League table");
  return html`<${Async} q=${q}>${(d) => html`<${LeagueView} d=${d} query=${query} />`}</${Async}>`;
}
