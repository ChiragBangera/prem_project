// Match report: the score, what the chances say it should have been, and how the game unfolded.
import { html, useEffect, useState } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { useScope } from "../lib/scope.js";
import { dateLong, formation, nf, timeOf, weekday } from "../lib/format.js";

import { Async, Badge, Card, Crest, DataNotices, Insights, PageHead, Tabs, useDocumentTitle, playerHref, teamHref } from "../ui/common.js";
import { MatchDeep } from "../ui/matchdeep.js";
import { Contributors } from "../ui/matchcontrib.js";
import { setQuery, useLocation } from "../lib/router.js";
import { DataTable } from "../ui/table.js";
import { MatchPitch } from "../charts/pitch.js";
import { XgRace } from "../charts/race.js";
import { Frame, AxisY, niceTicks, scaleBand, scaleLinear } from "../charts/core.js";
import { tooltip } from "../lib/tooltip.js";
import { scorerLines } from "../ui/matchcard.js";
import { LiveView, Tug } from "../ui/matchlive.js";

const RESULT = { Goal: "Goal", SavedShot: "Saved", BlockedShot: "Blocked", MissedShots: "Off target", ShotOnPost: "Hit the post", OwnGoal: "Own goal" };
const SITUATION = { OpenPlay: "Open play", FromCorner: "Corners", SetPiece: "Set pieces", DirectFreekick: "Free kicks", Penalty: "Penalties" };

function Buckets({ b, homeShort, awayShort }) {
  const max = Math.max(0.2, ...b.home, ...b.away);
  return html`<${Frame} height=${210} label="Expected goals by fifteen-minute period" margin=${{ top: 10, right: 8, bottom: 30, left: 40 }}>
    ${({ iw, ih }) => {
      const sx = scaleBand(b.labels, [0, iw], 0.24);
      const sy = scaleLinear([0, max * 1.1], [ih, 0]);
      const half = sx.bandwidth / 2;
      const yt = niceTicks(0, max * 1.1, 4);
      return html`<g>
        <${AxisY} scale=${sy} ticks=${yt} iw=${iw} format=${(v) => nf(v, 1)} />
        <line class="axis-line" x1="0" x2=${iw} y1=${ih} y2=${ih} />
        ${b.labels.map((l, i) => html`<g key=${l} onMouseMove=${(e) => tooltip.move(e, html`<div><div class="tt-title">${l}′</div><div class="tt-row"><span class="k"><i class="key" style=${{ background: "var(--c1)" }}></i>${homeShort}</span><span class="v">${nf(b.home[i], 2)}</span></div><div class="tt-row"><span class="k"><i class="key" style=${{ background: "var(--c2)" }}></i>${awayShort}</span><span class="v">${nf(b.away[i], 2)}</span></div></div>`)} onMouseLeave=${tooltip.hide}>
          <rect x=${sx(l)} y=${sy(b.home[i])} width=${half - 1} height=${Math.max(0, ih - sy(b.home[i]))} rx="2" style=${{ fill: "var(--c1)" }} />
          <rect x=${sx(l) + half + 1} y=${sy(b.away[i])} width=${half - 1} height=${Math.max(0, ih - sy(b.away[i]))} rx="2" style=${{ fill: "var(--c2)" }} />
          <text class="tick-label" x=${sx(l) + sx.bandwidth / 2} y=${ih + 18} text-anchor="middle">${l}</text>
        </g>`)}
      </g>`;
    }}
  </${Frame}>`;
}

function PlayersTable({ side, list, team, scope }) {
  const cols = [
    { key: "name", label: "Player", sticky: true, firstDir: "asc", render: (r) => html`<a class="cell-inline" href=${playerHref(r.id, { league: scope.league, season: scope.season })}><span class="name">${r.name}</span><span class="muted xsmall">${r.position}</span></a>` },
    { key: "minutes", label: "Min", num: true },
    { key: "goals", label: "G", num: true, className: "strong" }, { key: "assists", label: "A", num: true },
    { key: "shots", label: "Sh", num: true }, { key: "xg", label: "xG", num: true, render: (r) => nf(r.xg, 2) },
    { key: "xa", label: "xA", num: true, render: (r) => nf(r.xa, 2) }, { key: "kp", label: "KP", num: true },
    { key: "cards", label: "Cards", num: true, sortable: false, value: (r) => r.yellow + r.red * 2, render: (r) => (r.red ? "🟥" : r.yellow ? "🟨" : "") },
  ];
  return html`<${Card} flush title=${team}>
    <${DataTable} columns=${cols} rows=${list} rowKey=${(r) => r.id} initialSort=${{ key: "xg", dir: "desc" }} dense tight caption=${`${team} players`} />
  </${Card}>`;
}

/** Who scored, under the team's name on the scoreboard. */
function Scorers({ list, align }) {
  const lines = scorerLines(list);
  if (!lines.length) return null;
  return html`<div class=${"sb-scorers " + align}>${lines.map((l, i) => html`<span key=${l.id ?? i}><b>${l.full}</b> ${l.minutes.join(", ")}</span>`)}</div>`;
}

const SHAPE = (f) => formation(f) || "–";

/**
 * The scoreboard shows the same xG as the chart, the shot map and the head to head below it: every shot added up. Understat's own match figure
 * counts the shots of one attack once (a saved shot and the rebound scored a moment later are one chance, not two), so it is lower when there
 * were rebounds; say so on hover rather than show two different totals for one team on one page.
 */
function matchXgNote(f, summary) {
  const h = summary?.home?.xg, a = summary?.away?.xg;
  if (h == null || a == null || (Math.abs(h - f.hxg) < 0.01 && Math.abs(a - f.axg) < 0.01)) return "Every shot's xG added up";
  return `Every shot's xG added up. Understat's match figure, which counts the shots of one attack (a rebound) once, is ${nf(f.hxg, 2)} – ${nf(f.axg, 2)}.`;
}

/** What the event data adds to the result: possession, passing, set pieces, discipline and the shape each side used. */
function HowPlayed({ stats, f }) {
  if (!stats) return null;
  const pair = (label, v, format = (x) => String(x), inverse = false) => (v && v[0] != null && v[1] != null ? html`<${Tug} label=${label} home=${v[0]} away=${v[1]} format=${format} inverse=${inverse} />` : null);
  return html`<${Card} title="How the game was played" sub="From the event data: who had the ball, how they used it, and the shape each side played.">
    <div class="stack" style=${{ "--gap": "12px" }}>
      ${pair("Possession (share of passes)", stats.poss, (v) => `${v}%`)}
      ${pair("Passes", stats.passes)}
      ${pair("Pass accuracy", stats.pass_acc, (v) => `${v}%`)}
      ${pair("Corners", stats.corners)}
      ${pair("Fouls", stats.fouls, undefined, true)}
      ${pair("Yellow cards", stats.yellow, undefined, true)}
      ${stats.red && (stats.red[0] || stats.red[1]) ? pair("Red cards", stats.red, undefined, true) : null}
    </div>
    <div class="row between small" style=${{ marginTop: "14px", gap: "12px" }}>
      <span><b>${f.home_short}</b> <span class="muted">${SHAPE(stats.formations?.[0])}${stats.managers?.[0] ? ` · ${stats.managers[0]}` : ""}</span></span>
      <span style=${{ textAlign: "right" }}><b>${f.away_short}</b> <span class="muted">${SHAPE(stats.formations?.[1])}${stats.managers?.[1] ? ` · ${stats.managers[1]}` : ""}</span></span>
    </div>
  </${Card}>`;
}

function MatchView({ d }) {
  const scope = useScope();
  const tab = useLocation().query.tab === "deep" ? "deep" : "quick";
  const { report: r, insights, scope: dscope, meta, stats } = d;
  const f = r.fixture, s = r.summary;
  const chances = [...r.key_chances].sort((a, b) => b.xg - a.xg).slice(0, 8);
  const goalsHome = f.hg, goalsAway = f.ag;
  return html`
    <${PageHead} eyebrow=${`${dscope.league_name} · ${dscope.label} · Matchweek ${f.round}`} title=${`${f.home} v ${f.away}`} sub=${`${weekday(f.date)} ${dateLong(f.date)}, kicked off ${timeOf(f.dt)}.`} />
    <span class="wide-page" hidden></span>
    <${DataNotices} scope=${dscope} meta=${meta} />
    <div class="scoreboard card">
      <div class="sb-col"><a class="sb-team" href=${teamHref(f.home)}><${Crest} team=${f.home} short=${f.home_short} size=${56} /><span>${f.home}</span></a><${Scorers} list=${r.scorers?.h} align="start" /></div>
      <div class="sb-score"><div class="figure">${goalsHome}<i>–</i>${goalsAway}</div><div class="sb-xg num" title=${matchXgNote(f, r.summary)}>xG ${nf(r.summary?.home?.xg ?? f.hxg, 2)} – ${nf(r.summary?.away?.xg ?? f.axg, 2)}${stats?.poss ? html` · possession ${stats.poss[0]}–${stats.poss[1]}%` : ""}</div></div>
      <div class="sb-col away"><a class="sb-team away" href=${teamHref(f.away)}><${Crest} team=${f.away} short=${f.away_short} size=${56} /><span>${f.away}</span></a><${Scorers} list=${r.scorers?.a} align="end" /></div>
    </div>
    <${Insights} items=${insights} scope=${dscope} />

    <div class="mrow m-race">
      <${Card} title="How the chances built up" sub="Running total of expected goals. Rings mark goals; hover a ring for the scorer.">
        <${XgRace} home=${r.timeline.home} away=${r.timeline.away} homeName=${f.home} awayName=${f.away} homeShort=${f.home_short} awayShort=${f.away_short} />
      </${Card}>
      <${Contributors} players=${r.players} f=${f} scope=${{ league: scope.league, season: scope.season }} />
    </div>

    <div class=${"mrow " + (stats ? "m-n3" : "m-n2")}>
      <${Card} title="When the chances came" sub="Expected goals in each period of the match.">
        <${Buckets} b=${r.buckets} homeShort=${f.home_short} awayShort=${f.away_short} />
        <div class="legend" style=${{ marginTop: "6px" }}><span class="item"><span class="swatch box" style=${{ background: "var(--c1)" }}></span>${f.home}</span><span class="item"><span class="swatch box" style=${{ background: "var(--c2)" }}></span>${f.away}</span></div>
      </${Card}>
      <${Card} title="Head to head">
        <div class="stack" style=${{ "--gap": "12px" }}>
          <${Tug} label="Expected goals" home=${s.home.xg} away=${s.away.xg} format=${(v) => nf(v, 2)} />
          <${Tug} label="Shots" home=${s.home.shots} away=${s.away.shots} />
          <${Tug} label="On target" home=${s.home.on_target} away=${s.away.on_target} />
          <${Tug} label="xG per shot" home=${s.home.xg_per_shot} away=${s.away.xg_per_shot} format=${(v) => nf(v, 3)} />
          <${Tug} label="Big chances (0.30+)" home=${s.home.big_chances} away=${s.away.big_chances} />
          <${Tug} label="Goals" home=${s.home.goals} away=${s.away.goals} />
        </div>
      </${Card}>
      ${stats ? html`<${HowPlayed} stats=${stats} f=${f} />` : null}
    </div>

    <div class="mrow m-5-7">
      <${Card} title="Shot map" sub="Home attacks right, away attacks left. Circle size is chance quality; a dark rim marks a goal.">
        <${MatchPitch} home=${r.shots.home} away=${r.shots.away} />
        <div class="legend" style=${{ marginTop: "10px" }}><span class="item"><span class="swatch dot" style=${{ background: "var(--c1)" }}></span>${f.home}</span><span class="item"><span class="swatch dot" style=${{ background: "var(--c2)" }}></span>${f.away}</span><span class="item">Bigger circle = better chance (xG)</span></div>
      </${Card}>
      <${Card} flush title="The best chances" sub="The eight shots with the highest xG.">
        <div class="chancelist">${chances.map((c) => html`<div class="chance" key=${c.id}>
          <span class="cmp-dot" style=${{ background: c.side === "h" ? "var(--c1)" : "var(--c2)" }}></span>
          <span class="num muted" style=${{ width: "34px" }}>${c.minute}′</span>
          <span class="stack" style=${{ "--gap": "0", flex: 1, minWidth: 0 }}><a class="link truncate" href=${playerHref(c.player_id, { league: scope.league, season: scope.season })}>${c.player}</a><span class="xsmall muted truncate">${SITUATION[c.situation] || c.situation}${c.assisted_by ? ` · assist ${c.assisted_by}` : ""}</span></span>
          <${Badge} tone=${c.result === "Goal" ? "good" : ""}>${RESULT[c.result] || c.result}</${Badge}>
          <b class="num" style=${{ width: "44px", textAlign: "right" }}>${nf(c.xg, 2)}</b>
        </div>`)}</div>
      </${Card}>
    </div>

    <div class="row between top" style=${{ marginBottom: "10px" }}>
      <${Tabs} label="Player view" value=${tab} onChange=${(t) => setQuery({ tab: t === "quick" ? null : t })} tabs=${[{ value: "quick", label: "Quick view" }, { value: "deep", label: "Deep analytics" }]} />
      ${tab === "deep" ? html`<span class="muted small">Every player who played, with every Scout metric for this match alone.</span>` : null}
    </div>
    ${tab === "deep"
      ? html`<${MatchDeep} id=${f.id} scope=${scope} f=${f} />`
      : html`<div class="grid cols-2">
        <${PlayersTable} side="h" list=${r.players.home} team=${f.home} scope=${scope} />
        <${PlayersTable} side="a" list=${r.players.away} team=${f.away} scope=${scope} />
      </div>`}
  `;
}

export default function MatchPage({ params }) {
  const { league, season } = useScope();
  const id = Number(params.id);
  // Where the match is first: a match Understat has not listed yet (being played, or just finished) has no report, only what WhoScored's
  // page said at half time or full time. Asking with follow=1 tells the updater someone is watching it (read at half time too).
  const [unlisted, setUnlisted] = useState(false);   // asked again every minute only while Understat has not listed the match
  const live = useApi(`/api/match/${id}/live`, { league, season, follow: 1 }, { staleMs: 0, persist: false, pollMs: unlisted ? 60000 : 0 });
  const played = live.data?.fixture?.id === id ? Boolean(live.data.fixture.played) : null;   // never the previous match's answer
  useEffect(() => setUnlisted(played === false), [played]);
  const q = useApi(`/api/match/${id}`, { league, season }, { enabled: played === true });
  useDocumentTitle(played === false ? "Live match" : "Match report");
  if (played === false) return html`<${Async} q=${live}>${(d) => html`<${LiveView} d=${d} />`}</${Async}>`;
  return html`<${Async} q=${played ? q : live}>${(d) => (played ? html`<${MatchView} d=${d} />` : null)}</${Async}>`;
}
