// Team: how a side is really doing (results vs chances), who drives it, what is next.
import { html, useMemo } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useScope, useMeta } from "../lib/scope.js";
import { navigate, setQuery, useLocation, href } from "../lib/router.js";
import { dateShort, nf, ordinal, pct, plural, signed, timeOf, weekday } from "../lib/format.js";
import { Tip } from "../lib/tooltip.js";
import { Async, Badge, Card, Crest, DataNotices, EmptyState, Form, Insights, Notice, PageHead, Section, Select, Stat, Tabs, useDocumentTitle, playerHref, matchHref, teamHref, Star } from "../ui/common.js";
import { DataTable } from "../ui/table.js";
import { GapCell, labHref } from "../ui/blocks.js";
import { PercentileBars, ProbBar, StackedBar } from "../charts/bars.js";
import { LineChart } from "../charts/lines.js";
import { MatchStrip, StripLegend } from "../charts/matchstrip.js";
import { rememberVisit } from "../ui/palette.js";
import { useEffect } from "../lib/html.js";

const SPLIT_LABEL = {
  home: "Home", away: "Away", first_half: "First half of season", second_half: "Second half of season",
  last6: "Last 6 matches", vs_stronger: "Against stronger teams", vs_weaker: "Against weaker teams",
};

const GROUP_LABEL = { situation: "Situation", shotZone: "Shot zone", timing: "Timing", gameState: "Game state", attackSpeed: "Attack speed", formation: "Formation", result: "Shot result" };
const NAME_MAP = {
  OpenPlay: "Open play", FromCorner: "From corners", SetPiece: "Set pieces", DirectFreekick: "Direct free kicks", Penalty: "Penalties",
  shotPenaltyArea: "Penalty area", shotSixYardBox: "Six-yard box", shotOboxTotal: "Outside the box",
  SavedShot: "Saved", BlockedShot: "Blocked", MissedShots: "Off target", ShotOnPost: "Hit the post", Goal: "Goals", OwnGoal: "Own goals",
};
const prettyName = (n) => NAME_MAP[n] || n;

function difficulty(strength) {
  if (strength >= 0.5) return { label: "Tough", tone: "warn" };
  if (strength <= -0.5) return { label: "Kind", tone: "good" };
  return { label: "Even", tone: "" };
}

function Squad({ squad, scope, concentration }) {
  const cols = [
    { key: "name", label: "Player", sticky: true, firstDir: "asc", render: (r) => html`<a class="cell-inline" href=${playerHref(r.id, { league: scope.league, season: scope.season })}><span class="name">${r.name}</span><span class="muted xsmall">${r.pos}</span></a>` },
    { key: "minutes", label: "Min", num: true },
    { key: "goals", label: "G", num: true },
    { key: "xg", label: "xG", num: true, render: (r) => nf(r.xg, 1) },
    { key: "g_xg", label: "G − xG", num: true, render: (r) => html`<${GapCell} value=${r.g_xg} max=${8} />`, title: "Goals minus expected goals. Blue: finishing above the chances." },
    { key: "assists", label: "A", num: true },
    { key: "xa", label: "xA", num: true, render: (r) => nf(r.xa, 1) },
    { key: "shots", label: "Shots", num: true },
    { key: "kp", label: "Key passes", num: true },
    { key: "share_npxg", label: "npxG share", num: true, title: "The part of the team's non-penalty xG that comes from this player's shots.", render: (r) => html`<span class="gap-bar"><span class="bar-inline" style=${{ width: "64px" }}><i style=${{ width: Math.min(100, (r.share_npxg || 0) * 250) + "%" }}></i></span><span class="val">${pct(r.share_npxg)}</span></span>` },
    { key: "chain_share", label: "xGChain share", num: true, title: "How much of the team's attacking play passes through him.", render: (r) => pct(r.chain_share) },
    { key: "star", label: "", sortable: false, csv: false, render: (r) => html`<${Star} player=${{ id: r.id, name: r.name, team: scope.team, league: scope.league }} />` },
  ];
  return html`<${Card} flush title="Squad contributions" sub=${concentration?.top3?.length ? `${concentration.top3.join(", ")} account for ${pct(concentration.top3_share)} of the team's non-penalty xG.` : "Minutes and output for everyone who has played."}>
    <${DataTable} columns=${cols} rows=${squad} rowKey=${(r) => r.id} initialSort=${{ key: "minutes", dir: "desc" }} dense pageSize=${16} caption="Squad"
      onRowClick=${(r) => navigate(`/player/${r.id}`, { league: scope.league, season: scope.season })} />
  </${Card}>`;
}

function Fixtures({ upcoming, schedule, team }) {
  if (!upcoming.length) return html`<${Card} title="Fixtures"><${EmptyState} compact icon="calendar" title="No fixtures left" text="The season is complete for this team." /></${Card}>`;
  const harder = schedule.remaining_avg_opp - schedule.played_avg_opp;
  return html`<${Card} flush title="What is next" sub=${`${plural(schedule.remaining, "game")} left. ${Math.abs(harder) < 0.15 ? "The run-in is no harder or easier than what they have faced." : harder > 0 ? "The run-in is tougher than the games already played." : "The run-in is kinder than the games already played."}`}>
    <div class="fixtures">
      ${upcoming.map((f) => {
        const d = difficulty(f.opp_strength);
        return html`<a class="fixture team-fixture" key=${f.match_id} href=${f.venue === "h" ? labHref(team, f.opponent) : labHref(f.opponent, team)}>
          <div class="when num"><b>${weekday(f.date)} ${dateShort(f.date)}</b><span class="muted">${timeOf(f.dt)}</span></div>
          <div class="teams"><span class="t"><${Crest} team=${f.opponent} short=${f.opponent_short} size=${22} /><span class="truncate">${f.venue === "h" ? "vs" : "at"} ${f.opponent}</span></span></div>
          <div class="prob">${f.forecast ? html`<${ProbBar} home=${f.forecast.win} draw=${f.forecast.draw} away=${f.forecast.loss} homeLabel="Win" awayLabel="Loss" compact />` : html`<span class="muted small">No forecast yet</span>`}</div>
          <div class="exp"><${Badge} tone=${d.tone} title="Strength of the opponent on the ratings model">${d.label}</${Badge}></div>
        </a>`;
      })}
    </div>
  </${Card}>`;
}

function Splits({ splits }) {
  const rows = Object.entries(SPLIT_LABEL).filter(([k]) => splits[k] && splits[k].played).map(([k, label]) => ({ key: k, label, ...splits[k] }));
  const cols = [
    { key: "label", label: "Split", sortable: false, className: "strong", render: (r) => r.label },
    { key: "played", label: "P", num: true, sortable: false },
    { key: "pts_pg", label: "Pts/g", num: true, sortable: false, render: (r) => nf(r.pts_pg, 2) },
    { key: "xpts_pg", label: "xPts/g", num: true, sortable: false, render: (r) => nf(r.xpts_pg, 2) },
    { key: "xg_pg", label: "xG/g", num: true, sortable: false, render: (r) => nf(r.xg_pg, 2) },
    { key: "xga_pg", label: "xGA/g", num: true, sortable: false, render: (r) => nf(r.xga_pg, 2) },
    { key: "xgd_pg", label: "xGD/g", num: true, sortable: false, render: (r) => html`<span class=${"delta-val " + (r.xgd_pg > 0.05 ? "pos" : r.xgd_pg < -0.05 ? "neg" : "")}>${signed(r.xgd_pg, 2)}</span>` },
  ];
  return html`<${Card} flush title="Splits" sub="The same team in different circumstances. Small samples wobble: read the pattern, not one number.">
    <${DataTable} columns=${cols} rows=${rows} rowKey=${(r) => r.key} dense caption="Team splits" />
  </${Card}>`;
}

function Managers({ eras }) {
  const cols = [
    { key: "manager", label: "Manager", sortable: false, className: "strong" },
    { key: "period", label: "In charge", sortable: false, render: (r) => `${dateShort(r.start)} – ${r.end ? dateShort(r.end) : "now"}` },
    { key: "played", label: "P", num: true, sortable: false },
    { key: "pts_pg", label: "Pts/g", num: true, sortable: false, render: (r) => nf(r.pts_pg, 2) },
    { key: "xpts_pg", label: "xPts/g", num: true, sortable: false, render: (r) => nf(r.xpts_pg, 2) },
    { key: "xg_pg", label: "xG/g", num: true, sortable: false, render: (r) => nf(r.xg_pg, 2) },
    { key: "xga_pg", label: "xGA/g", num: true, sortable: false, render: (r) => nf(r.xga_pg, 2) },
    { key: "xgd_pg", label: "xGD/g", num: true, sortable: false, render: (r) => html`<span class=${"delta-val " + (r.xgd_pg > 0.05 ? "pos" : r.xgd_pg < -0.05 ? "neg" : "")}>${signed(r.xgd_pg, 2)}</span>` },
  ];
  return html`<${Card} flush title="Managers" sub="Only this season's matches, split by the stints in managers.json. Short spells are noisy.">
    <${DataTable} columns=${cols} rows=${eras} rowKey=${(r) => r.manager + r.start} dense caption="Manager stints" />
  </${Card}>`;
}

function BarCell({ value, max, color }) {
  return html`<span class="gap-bar"><span class="bar-inline" style=${{ width: "88px" }}><i style=${{ width: Math.min(100, (value / (max || 1)) * 100) + "%", background: color }}></i></span><span class="val">${nf(value, 1)}</span></span>`;
}

function Chances({ team, scope }) {
  const q = useApi("/api/team/chances", { team, league: scope.league, season: scope.season });
  const { query } = useLocation();
  const group = GROUP_LABEL[query.group] ? query.group : "situation";
  return html`<${Async} q=${q}>${(d) => {
    const rows = (d.groups[group] || []).filter((r) => r.shots || r.xg).map((r) => ({ ...r, label: prettyName(r.name), a_xg: r.against?.xg ?? 0, a_shots: r.against?.shots ?? 0, a_goals: r.against?.goals ?? 0 }));
    const maxXg = Math.max(1, ...rows.map((r) => Math.max(r.xg, r.a_xg)));
    const totalFor = rows.reduce((s, r) => s + r.xg, 0);
    const cols = [
      { key: "label", label: GROUP_LABEL[group], firstDir: "asc", className: "strong", value: (r) => r.label },
      { key: "shots", label: "Shots for", num: true }, { key: "goals", label: "Goals for", num: true },
      { key: "xg", label: "xG for", num: true, render: (r) => html`<${BarCell} value=${r.xg} max=${maxXg} color="var(--c1)" />` },
      { key: "xg_shot", label: "xG/shot", num: true, value: (r) => (r.shots ? r.xg / r.shots : null), render: (r) => (r.shots ? nf(r.xg / r.shots, 3) : "–") },
      { key: "a_shots", label: "Shots against", num: true }, { key: "a_goals", label: "Goals against", num: true },
      { key: "a_xg", label: "xG against", num: true, render: (r) => html`<${BarCell} value=${r.a_xg} max=${maxXg} color="var(--c2)" />` },
    ];
    return html`<div class="stack" style=${{ "--gap": "16px" }}>
      <${Insights} items=${d.insights} scope=${scope} />
      <${Card} flush title="Where the chances come from and go" sub="Blue: chances this team creates. Orange: chances it allows. All values are xG unless stated."
        actions=${html`<${Select} compact label="Breakdown" value=${group} options=${Object.entries(GROUP_LABEL).filter(([k]) => d.groups[k]?.length).map(([value, label]) => ({ value, label }))} onChange=${(v) => setQuery({ group: v === "situation" ? null : v })} />`}>
        <div class="card-body" style=${{ paddingBottom: 0 }}>
          <${StackedBar} segments=${rows.filter((r) => r.xg > 0).map((r) => ({ key: r.name, label: r.label, value: r.xg }))} unit=" xG" />
          <p class="xsmall muted" style=${{ marginTop: "8px" }}>Share of the ${nf(totalFor, 1)} xG this team has created, by ${GROUP_LABEL[group].toLowerCase()}.</p>
        </div>
        <${DataTable} columns=${cols} rows=${rows} rowKey=${(r) => r.name} dense caption="Chance breakdown" />
      </${Card}>
    </div>`;
  }}</${Async}>`;
}

function TeamView({ d, team, tab }) {
  const meta = useMeta();
  const { scope, meta: dm, profile: p, insights, forecasts, teams } = d;
  const t = p.team;
  const idx = p.matches.map((m) => m.n);
  const rolling = p.rolling;
  // A line needs two points; the five-match average only starts at match five.
  const rollingReady = rolling.xg.filter((v) => v != null).length >= 2;
  const others = teams.filter((x) => x.name !== team).map((x) => ({ value: x.name, label: x.name }));
  useEffect(() => { rememberVisit({ kind: "team", href: teamHref(team), label: team, sub: `${scope.league_name} ${scope.label}` }); }, [team, scope.season]);

  const shift = t.rank_gap;
  const sub = `${ordinal(t.rank)} in the ${scope.league_name} on ${t.pts} points after ${plural(t.played, "game")}.${Math.abs(shift) >= 2 ? ` On expected points they would be ${ordinal(t.rank_xpts)}.` : ""}`;
  const tabs = [{ value: "overview", label: "Overview" }, { value: "squad", label: "Squad", count: p.squad.length }, { value: "chances", label: "Chances" }];

  return html`
    <${PageHead} lead=${html`<${Crest} team=${t.team} short=${t.short} size=${46} />`} eyebrow=${`${scope.league_name} · ${scope.label}`} title=${t.team} sub=${sub}
      actions=${html`<${Select} compact label="Compare with another team" value="" options=${[{ value: "", label: "Compare with…" }, ...others]} onChange=${(v) => v && navigate("/compare", { mode: "teams", a: team, b: v })} />`} />
    <${DataNotices} scope=${scope} meta=${dm} />
    <div class="tiles">
      <${Stat} label="Position" value=${ordinal(t.rank)} sub=${`${ordinal(t.rank_xpts)} on expected points`} />
      <${Stat} label="Points" value=${t.pts} sub=${`${nf(t.xpts, 1)} expected (${signed(t.xpts_gap, 1)})`} tone=${t.xpts_gap > 1 ? "up" : t.xpts_gap < -1 ? "down" : ""} />
      <${Stat} label="Goals for–against" value=${`${t.gf}–${t.ga}`} sub=${`xG ${nf(t.xg, 1)}–${nf(t.xga, 1)}`} />
      <${Stat} label="Chance difference" value=${`${signed(t.xgd_pg, 2)}`} sub=${`per game · ${ordinal(t.rank_xgd)} in the league`} />
      <div class="tile"><span class="label">Last five</span><span style=${{ paddingTop: "4px" }}><${Form} items=${t.form} /></span><span class="delta">${t.w}W ${t.d}D ${t.l}L overall</span></div>
    </div>
    <${Tabs} tabs=${tabs} value=${tab} onChange=${(v) => setQuery({ tab: v === "overview" ? null : v })} label="Team sections" />

    ${tab === "overview" ? html`
      <${Insights} items=${insights} scope=${scope} limit=${3} expandable />
      <div class="grid cols-wide-narrow top">
        <${Card} title="Every match: chances against results" sub="Bars show whether they created more (blue) or allowed more (orange). The marker is what happened. Click a match to open it.">
          <${MatchStrip} matches=${p.matches} onOpen=${(m) => m.match_id && navigate(`/match/${m.match_id}`)} />
          <${StripLegend} />
        </${Card}>
        <${Card} title="Against the rest of the league" sub="Percentile among all teams. The tick marks the league median.">
          <${PercentileBars} items=${p.percentiles.map((x) => ({ key: x.key, label: x.label, pct: x.percentile, raw: nf(x.value, x.key === "ppda" || x.key === "deep_pg" || x.key === "deep_allowed_pg" ? 1 : 2),
            tip: html`<${Tip} title=${x.label} rows=${[{ label: "This team", value: nf(x.value, 2) }, { label: "League average", value: nf(x.league_average, 2) }, { label: "Percentile", value: Math.round(x.percentile) }]} />` }))} />
          <p class="xsmall muted" style=${{ marginTop: "12px" }}>Percentiles always read "higher is better": a strong press or few chances allowed scores high.</p>
        </${Card}>
      </div>
      <div class="grid cols-2">
        <${Card} title="Chances created and allowed" sub=${rollingReady ? "Rolling five-match average of xG for and against." : "xG for and against in each match. The rolling five-match average appears once six matches are played."}>
          <${LineChart} x=${idx} series=${[{ key: "xg", label: "xG for", values: rollingReady ? rolling.xg : p.matches.map((m) => m.xg), color: "var(--c1)", endLabel: "for" }, { key: "xga", label: "xG against", values: rollingReady ? rolling.xga : p.matches.map((m) => m.xga), color: "var(--c2)", endLabel: "against" }]}
            height=${260} yFormat=${(v) => nf(v, 1)} xFormat=${(v) => String(v)} xLabel="Matchweek" tooltipTitle=${(i) => `Matchweek ${idx[i]} · vs ${p.matches[i].opponent}`} tooltipFormat=${(v) => nf(v, 2)} />
        </${Card}>
        <${Card} title="Points and expected points" sub="Running totals. The gap between the lines is the luck, good or bad, banked so far.">
          <${LineChart} x=${idx} series=${[{ key: "pts", label: "Points", values: p.cumulative.map((c) => c.pts), color: "var(--c1)", endLabel: "pts" }, { key: "xpts", label: "Expected points", values: p.cumulative.map((c) => c.xpts), color: "var(--c2)", dashed: true, endLabel: "xPts" }]}
            height=${260} yFormat=${(v) => String(Math.round(v))} xLabel="Matchweek" tooltipTitle=${(i) => `After matchweek ${idx[i]}`} tooltipFormat=${(v) => nf(v, 1)} />
        </${Card}>
      </div>
      <div class="grid cols-2 top">
        <${Fixtures} upcoming=${p.upcoming} schedule=${p.schedule} team=${team} />
        <${Splits} splits=${p.splits} />
      </div>
      ${p.eras?.length ? html`<${Managers} eras=${p.eras} />` : null}
    ` : null}

    ${tab === "squad" ? html`<${Squad} squad=${p.squad} scope=${{ ...scope, team }} concentration=${p.concentration} />` : null}
    ${tab === "chances" ? html`<${Chances} team=${team} scope=${scope} />` : null}
  `;
}

export default function Team({ params }) {
  const { league, season } = useScope();
  const { query } = useLocation();
  const team = params.team;
  const q = useApi("/api/team", { team, league, season });
  const tab = ["squad", "chances"].includes(query.tab) ? query.tab : "overview";
  useDocumentTitle(team);
  return html`<${Async} q=${q}>${(d) => html`<${TeamView} d=${d} team=${team} tab=${tab} />`}</${Async}>`;
}
