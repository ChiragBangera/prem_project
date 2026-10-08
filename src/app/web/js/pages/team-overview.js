// Team overview: how the season has gone (results against chances), how the team plays (style profile), what is next, and the splits.
import { html } from "../lib/html.js";
import { navigate } from "../lib/router.js";
import { dateShort, nf, plural, signed } from "../lib/format.js";
import { Badge, Card, Crest, EmptyState, Insights, Notice } from "../ui/common.js";
import { DataTable } from "../ui/table.js";
import { LineChart } from "../charts/lines.js";
import { MatchStrip, StripLegend } from "../charts/matchstrip.js";
import { StyleProfile } from "../ui/styleprofile.js";
import { kickoff } from "../ui/matchcard.js";

const SPLIT_LABEL = {
  home: "Home", away: "Away", first_half: "First half of season", second_half: "Second half of season",
  last6: "Last 6 matches", vs_stronger: "Against stronger teams", vs_weaker: "Against weaker teams",
};

function difficulty(strength) {
  if (strength >= 0.5) return { label: "Tough", tone: "warn" };
  if (strength <= -0.5) return { label: "Kind", tone: "good" };
  return { label: "Even", tone: "" };
}

function Fixtures({ upcoming, schedule }) {
  if (!upcoming.length) return html`<${Card} title="What is next"><${EmptyState} compact icon="calendar" title="No fixtures left" text="The season is complete for this team." /></${Card}>`;
  const harder = schedule.remaining_avg_opp - schedule.played_avg_opp;
  const sub = `${plural(schedule.remaining, "game")} left. ${Math.abs(harder) < 0.15 ? "The run-in is no harder or easier than what they have faced." : harder > 0 ? "The run-in is tougher than the games already played." : "The run-in is kinder than the games already played."}`;
  return html`<${Card} flush title="What is next" sub=${sub}>
    <div class="fixtures">${upcoming.slice(0, 8).map((f) => {
      const d = difficulty(f.opp_strength);
      const k = kickoff({ utc: f.dt ? `${f.dt.slice(0, 10)}T${f.dt.slice(11, 19)}Z` : null, date: f.date, dt: f.dt });
      return html`<a class="fixture-row" key=${f.match_id} href=${`#/match/${f.match_id}`}>
        <div class="fx-when"><b class="num">${k.time}</b><span class="muted xsmall">${k.day}</span></div>
        <div class="fx-teams"><div class="fx-side"><${Crest} team=${f.opponent} short=${f.opponent_short} size=${26} />
          <div class="stack" style=${{ "--gap": "2px", minWidth: 0 }}><span class="fx-name">${f.venue === "h" ? "vs" : "at"} ${f.opponent}</span></div>
          <${Badge} tone=${d.tone} title="How strong the opponent is on chance difference">${d.label}</${Badge}></div></div>
      </a>`;
    })}</div>
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
    { key: "xgd_pg", label: "xGD/g", num: true, sortable: false, render: (r) => html`<span class=${"delta-val " + (r.xgd_pg > 0.05 ? "pos" : r.xgd_pg < -0.05 ? "neg" : "")}>${signed(r.xgd_pg, 2)}</span>` },
  ];
  return html`<${Card} flush title="Managers" sub="This season's matches, split by the stints in managers.json. Short spells are noisy.">
    <${DataTable} columns=${cols} rows=${eras} rowKey=${(r) => r.manager + r.start} dense caption="Manager stints" />
  </${Card}>`;
}

export default function Overview({ d, team, profile }) {
  const { scope, insights } = d;
  const p = d.profile;
  const idx = p.matches.map((m) => m.n);
  const rolling = p.rolling;
  // A line needs two points; the five-match average only starts at match five.
  const rollingReady = rolling.xg.filter((v) => v != null).length >= 2;
  const evNote = profile?.row && profile.row.ev_matches < profile.row.matches
    ? `Possession, passing and pressing measures use the ${profile.row.ev_matches} of ${profile.row.matches} matches that have event data; they fill in as more are stored.` : null;
  return html`<div class="stack" style=${{ "--gap": "24px" }}>
    <${Insights} items=${insights} scope=${scope} limit=${3} expandable />

    <div class="grid cols-wide-narrow top">
      <${Card} title="Every match: chances against results" sub="Bars show whether they created more (blue) or allowed more (orange). The marker is what happened. Click a match to open it.">
        <${MatchStrip} matches=${p.matches} onOpen=${(m) => m.match_id && navigate(`/match/${m.match_id}`)} />
        <${StripLegend} />
      </${Card}>
      <${Fixtures} upcoming=${p.upcoming} schedule=${p.schedule} />
    </div>

    <${Card} title="How they play" sub="Where the team stands among the other teams of its league and season. Bars are percentiles (longer is better, whichever way the measure reads); a dot on a track is a style measure, where more is not better or worse. The thin tick is the league median.">
      ${profile?.row
        ? html`<${StyleProfile} row=${profile.row} rows=${profile.rows} ctx=${profile.ctx} />${evNote ? html`<p class="xsmall muted" style=${{ marginTop: "12px" }}>${evNote}</p>` : null}`
        : html`<${Notice} icon="info">${profile?.loading ? "Loading the league's team measures…" : "The league's team measures do not include this team and season yet."}</${Notice}>`}
    </${Card}>

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
      <${Splits} splits=${p.splits} />
      ${p.eras?.length ? html`<${Managers} eras=${p.eras} />` : null}
    </div>
  </div>`;
}
