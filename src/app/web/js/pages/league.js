// League: the table read three ways (results, expected, style) on the same sheet as Scout and Teams, plus two charts that explain it.
import { html, useMemo, useState } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useMeta, useScope } from "../lib/scope.js";
import { href, navigate, setQuery, useLocation } from "../lib/router.js";
import { nf, ordinal, plural, signed } from "../lib/format.js";
import { Tip } from "../lib/tooltip.js";
import { makeIndex, sortRows } from "../lib/filters.js";
import { rankShares } from "../lib/stats.js";
import { Async, Card, DataNotices, Insights, PageHead, Segmented, Select, useDocumentTitle } from "../ui/common.js";
import { FormCell, TeamCell } from "../ui/cells.js";
import { CsvButton } from "../ui/table.js";
import { GapCell } from "../ui/blocks.js";
import { Sheet, ShadeKey } from "../ui/explore/Sheet.js";
import { sortSentence } from "../ui/explore/model.js";
import { Sparkline, RankChart, SERIES_COLORS } from "../charts/lines.js";
import { Icon } from "../lib/icons.js";
import { useStableSlots } from "../lib/slots.js";
import { Scatter } from "../charts/scatter.js";

// The table's numbers, named as the team catalog names them where it has the same measure, so a heading means the same here as on Teams.
const FROM_CATALOG = { played: "played", w: "wins", d: "draws", l: "losses", gf: "gf", ga: "ga", gd: "gd", pts: "pts", xpts: "xpts", xpts_gap: "pts_xpts",
  xg_pg: "xg_pg", xga_pg: "xga_pg", xgd_pg: "xgd_pg", ppda: "ppda", oppda: "oppda", deep_pg: "deep_pg", deep_allowed_pg: "deepa_pg" };
const OWN = {
  xgd: { label: "xG difference", short: "xGD", unit: "total", decimals: 1, hib: true, signed: true, what: "Expected goals created minus expected goals conceded, over the games shown." },
  g_xg: { label: "Goals minus xG", short: "G − xG", unit: "total", decimals: 1, hib: null, signed: true, what: "Attack luck: goals scored above (positive) or below the chances created.", read: "Big gaps rarely last a season." },
  xga_ga: { label: "xGA minus goals against", short: "xGA − GA", unit: "total", decimals: 1, hib: null, signed: true, what: "Defence luck: fewer goals conceded than the chances allowed is positive (fortunate).", read: "Big gaps rarely last a season." },
  rank_xpts: { label: "Rank on expected points", short: "xPts rank", unit: "total", decimals: 0, hib: false, what: "Where the team would sit if the table were ordered by expected points, and how far that is from its real place." },
};
const KEYS = [...Object.keys(FROM_CATALOG), ...Object.keys(OWN)];
// counts that describe how much was played, not how well: no shade
const PLAIN = new Set(["played", "d"]);

const FORM = { key: "form", label: "Form", width: 118, align: "left", className: "left", title: "The last five results, oldest first.", render: (r) => html`<${FormCell} items=${r.form} />` };
const TREND = { key: "trend", label: "xGD trend", width: 112, title: "The rolling difference in chances through the season. Above the dotted line is a winning trend.",
  render: (r) => html`<${Sparkline} values=${r.trend_xgd} baseline=${0} color="var(--c1)" label=${`${r.team} rolling xG difference`} />` };
// a gap is drawn against the largest one in the table, so the bars read early in a season as well as late
const gap = (key) => ({ key, width: 124, gap: true, render: (r, most) => html`<${GapCell} value=${r[key]} max=${most} />` });
const RANK_XPTS = { key: "rank_xpts", render: (r) => html`<span class="num">${r.rank_xpts}</span> ${r.rank_gap === 0 ? html`<span class="muted xsmall">same</span>`
  : html`<span class=${"delta-val xsmall " + (r.rank_gap > 0 ? "pos" : "neg")} title=${r.rank_gap > 0 ? `${r.rank_gap} places higher on expected points` : `${-r.rank_gap} places lower on expected points`}>${r.rank_gap > 0 ? "▲" : "▼"}${Math.abs(r.rank_gap)}</span>`}` };

const SETS = [
  { value: "standings", label: "Table", blurb: "Results, goals and points, as the league table shows them.", sort: { sort: "rank", dir: "asc" },
    cols: ["played", "w", "d", "l", "gf", "ga", "gd", "pts", FORM, "xpts", gap("xpts_gap"), TREND] },
  { value: "expected", label: "Expected", blurb: "Where results and chances part ways: points against expected points, and the luck at each end.", sort: { sort: "xpts_gap", dir: "desc" },
    cols: ["pts", "xpts", gap("xpts_gap"), RANK_XPTS, "xgd", gap("g_xg"), gap("xga_ga")] },
  { value: "style", label: "Style", blurb: "How each team plays: chances made and allowed, the press and territory.", sort: { sort: "xgd_pg", dir: "desc" },
    cols: ["xg_pg", "xga_pg", "xgd_pg", "ppda", "oppda", "deep_pg", "deep_allowed_pg"] },
];

/** The table as explorer rows: each number in `v`, its rank in the league in `p`, and the measures they are, borrowed from the catalog. */
function useLeagueTable(table, catalog) {
  return useMemo(() => {
    const cat = catalog?.team?.metrics || {};
    const metrics = Object.fromEntries(KEYS.map((k) => [k, OWN[k] ? { key: k, ...OWN[k] } : { ...cat[FROM_CATALOG[k]], key: k }]).filter(([, m]) => m.label));
    const keys = KEYS.filter((k) => metrics[k]);
    const shares = Object.fromEntries(keys.map((k) => [k, rankShares(table.map((t) => t[k]), metrics[k].hib)]));
    const rows = table.map((t, i) => ({ ...t, key: t.team, v: keys.map((k) => t[k] ?? null), p: keys.map((k) => shares[k][i]) }));
    return { rows, ctx: { level: "team", idx: makeIndex(keys), keys, metrics, plain: PLAIN, roles: catalog?.roles, positions: catalog?.positions } };
  }, [table, catalog]);
}

function headline(table) {
  if (!table.length) return "";
  const byGap = [...table].sort((a, b) => a.xpts_gap - b.xpts_gap);
  const worst = byGap[0], best = byGap[byGap.length - 1];
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

function TableDesk({ d, set, catalog }) {
  const { scope, table } = d;
  const { rows, ctx } = useLeagueTable(table, catalog);
  const [sorts, setSorts] = useState({});
  const sort = sorts[set.value] || set.sort;
  const sorted = useMemo(() => sortRows(rows, { key: sort.sort, dir: sort.dir }, ctx), [rows, sort.sort, sort.dir, ctx]);
  const model = { ctx, view: sort, filtered: rows, shown: sorted, setView: (patch) => setSorts((s) => ({ ...s, [set.value]: { ...sort, ...patch } })) };
  const cols = useMemo(() => set.cols.map((c) => {
    if (!c.gap) return c;
    const most = Math.max(1, ...table.map((t) => Math.abs(t[c.key] ?? 0)));
    return { ...c, render: (r) => c.render(r, most) };
  }), [set, table]);
  const ucl = scope.ucl_places, rel = scope.relegation_places, n = table.length;
  const zone = (r) => (set.value === "style" ? null : r.rank <= ucl ? "zone-ucl" : r.rank > n - rel ? "zone-rel" : null);
  const lead = { label: "Team", width: 236, sortKey: "rank", firstDir: "asc", rowClass: zone,
    render: (r) => html`<div class="dk-who"><span class="dk-rank" title="League position">${r.rank}</span><${TeamCell} row=${r} /></div>` };
  const filtered = d.filter.venue !== "all" || d.filter.last;
  const scopeLine = [d.filter.venue !== "all" ? `${d.filter.venue === "h" ? "home" : "away"} matches only` : "", d.filter.last ? `the last ${d.filter.last} games` : ""].filter(Boolean).join(", ");
  const csv = [{ label: "Position", value: (r) => r.rank }, { label: "Team", value: (r) => r.team },
    ...set.cols.map((c) => (typeof c === "string" ? c : c.key)).filter((k) => ctx.metrics[k]).map((k) => ({ label: ctx.metrics[k].label, value: (r) => r[k] }))];
  return html`<div class="desk norail fit whole">
    <section class="dk-main" aria-label="League table">
      <div class="results-bar">
        <span class="dk-count"><b class="rb-title">${plural(n, "team")}</b><span class="muted small">${filtered ? `${scopeLine}: places and points count only those games` : "every match so far, home and away"}</span></span>
        <div class="rb-controls">
          <${Segmented} label="Venue" options=${[{ value: "all", label: "All" }, { value: "h", label: "Home" }, { value: "a", label: "Away" }]} value=${d.filter.venue} onChange=${(v) => setQuery({ venue: v === "all" ? null : v })} small />
          <${Select} compact label="Window" value=${String(d.filter.last || "")} options=${[{ value: "", label: "Whole season" }, { value: "5", label: "Last 5" }, { value: "10", label: "Last 10" }]} onChange=${(v) => setQuery({ last: v || null })} />
          <${CsvButton} columns=${csv} rows=${sorted} filename=${`${scope.league}-${scope.season}-${set.value}.csv`} />
        </div>
      </div>
      <div class="dk-setrow"><div class="dk-sets" role="tablist" aria-label="Which table to show">
        ${SETS.map((s) => html`<button type="button" role="tab" key=${s.value} aria-selected=${String(s.value === set.value)} title=${s.blurb} onClick=${() => setQuery({ view: s.value === "standings" ? null : s.value })}>${s.label}</button>`)}
      </div><span class="dk-setsay">${set.blurb}</span></div>
      <${Sheet} model=${model} lead=${lead} keys=${cols} rowKey=${(r) => r.team} caption="League table" peers="the league" colWidth=${set.value === "standings" ? 64 : 92}
        onPick=${(r) => navigate(`/team/${encodeURIComponent(r.team)}`, { league: scope.league, season: scope.season })} />
      <div class="dk-foot"><span>${sortSentence(sort, ctx)} Point at a heading for what it means; click it for its spread and to sort. Click a team for its page.</span>
        <span class="row wrap" style=${{ gap: "4px 14px" }}>${set.value === "style" ? null : html`<span class="legend"><span class="item"><span class="swatch box" style=${{ background: "var(--c1)" }}></span>Champions League places</span><span class="item"><span class="swatch box" style=${{ background: "var(--crit)" }}></span>Relegation places</span></span>`}<${ShadeKey} peers="the league" /></span></div>
    </section>
  </div>`;
}

function LeagueView({ d, query, catalog }) {
  const { scope, meta, table, trajectories, insights } = d;
  const set = SETS.find((s) => s.value === query.view) || SETS[0];
  const teamNames = table.map((t) => t.team);
  // default: follow the top three so the chart opens on the title race; "none" clears it
  const follow = query.follow === "none" ? [] : query.follow ? query.follow.split("|").filter((t) => teamNames.includes(t)).slice(0, 4) : table.slice(0, 3).map((t) => t.team);
  const setFollow = (list) => setQuery({ follow: list.length ? list.join("|") : "none" });
  const toggleFollow = (t) => setFollow(follow.includes(t) ? follow.filter((x) => x !== t) : [...follow, t].slice(-4));
  const slotOf = useStableSlots(follow);
  const colorOf = (t) => SERIES_COLORS[slotOf(t)];
  const ucl = scope.ucl_places, rel = scope.relegation_places, n = table.length;

  return html`
    <${PageHead} eyebrow=${`${scope.league_name} · ${scope.label} · after ${plural(scope.rounds_played, "matchweek")}`} title="League table" sub=${headline(table)}
      actions=${html`<a class="btn" href=${href("/teams", { lg: scope.league, ss: String(scope.season) })} title="Filter, rank and map every team measure: possession, pressing, set pieces ..."><span>All team measures</span></a>`} />
    <${DataNotices} scope=${scope} meta=${meta} />
    <${Insights} items=${insights} scope=${scope} limit=${3} />
    ${catalog ? html`<${TableDesk} d=${d} set=${set} catalog=${catalog} />` : null}

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
          ${follow.map((t) => html`<button type="button" class="chip" key=${t} onClick=${() => toggleFollow(t)} title="Stop following"><i class="dot" style=${{ background: colorOf(t) }}></i>${t}<${Icon} name="x" /></button>`)}
          ${follow.length ? html`<button type="button" class="chip" onClick=${() => setFollow([])}>Clear</button>` : html`<span class="xsmall muted">Nobody followed. Hover the lines, or pick a team above.</span>`}
          <span class="xsmall muted" style=${{ marginLeft: "auto" }}>Blue band: Champions League places · red band: relegation places</span>
        </div>
      </${Card}>
    </div>
  `;
}

export default function League() {
  const { league, season } = useScope();
  const { catalog } = useMeta();
  const { query } = useLocation();
  const venue = ["h", "a"].includes(query.venue) ? query.venue : "all";
  const last = query.last ? Number(query.last) : undefined;
  const q = useApi("/api/league", { league, season, venue, last });
  useDocumentTitle("League table");
  return html`<${Async} q=${q}>${(d) => html`<${LeagueView} d=${d} query=${query} catalog=${catalog} />`}</${Async}>`;
}
