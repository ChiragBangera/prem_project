// Match report: the score, what the chances say it should have been, and how the game unfolded.
import { html, useEffect, useMemo, useState } from "../lib/html.js";
import { useApi } from "../lib/api.js";
import { setLeague, setSeason, useScope } from "../lib/scope.js";
import { dateLong, formation, nf, timeOf, weekday } from "../lib/format.js";

import { Async, Card, Crest, DataNotices, Insights, PageHead, Segmented, Tabs, useDocumentTitle, playerHref, teamHref } from "../ui/common.js";
import { DefendingSection, EventPlayers, GoalMouthCard, LeadersCard, LineupsSection, MomentumCard, NoEvents, NumbersCard, PassingSection, PeriodPicker, linker } from "../ui/matchcentre.js";
import { MatchDeep } from "../ui/matchdeep.js";
import { Contributors } from "../ui/matchcontrib.js";
import { setQuery, useLocation } from "../lib/router.js";
import { DataTable } from "../ui/table.js";
import { MovesSection } from "../ui/matchmoves.js";
import { ShotBoard } from "../ui/shotboard.js";
import { XgRace } from "../charts/race.js";
import { Frame, AxisY, niceTicks, scaleBand, scaleLinear } from "../charts/core.js";
import { tooltip } from "../lib/tooltip.js";
import { scorerLines } from "../ui/matchcard.js";
import { LiveNotice, LiveView, Tug } from "../ui/matchlive.js";


function Buckets({ b, homeShort, awayShort }) {
  const shots = b.unit === "shots";
  const max = Math.max(shots ? 2 : 0.2, ...b.home, ...b.away);
  const fmt = (v) => nf(v, shots ? 0 : 2);
  return html`<${Frame} height=${210} label=${shots ? "Shots by fifteen-minute period" : "Expected goals by fifteen-minute period"} margin=${{ top: 10, right: 8, bottom: 30, left: 40 }}>
    ${({ iw, ih }) => {
      const sx = scaleBand(b.labels, [0, iw], 0.24);
      const sy = scaleLinear([0, max * 1.1], [ih, 0]);
      const half = sx.bandwidth / 2;
      const yt = niceTicks(0, max * 1.1, 4);
      return html`<g>
        <${AxisY} scale=${sy} ticks=${shots ? yt.filter(Number.isInteger) : yt} iw=${iw} format=${(v) => nf(v, shots ? 0 : 1)} />
        <line class="axis-line" x1="0" x2=${iw} y1=${ih} y2=${ih} />
        ${b.labels.map((l, i) => html`<g key=${l} onMouseMove=${(e) => tooltip.move(e, html`<div><div class="tt-title">${l}′</div><div class="tt-row"><span class="k"><i class="key" style=${{ background: "var(--c1)" }}></i>${homeShort}</span><span class="v">${fmt(b.home[i])}</span></div><div class="tt-row"><span class="k"><i class="key" style=${{ background: "var(--c2)" }}></i>${awayShort}</span><span class="v">${fmt(b.away[i])}</span></div></div>`)} onMouseLeave=${tooltip.hide}>
          <rect x=${sx(l)} y=${sy(b.home[i])} width=${half - 1} height=${Math.max(0, ih - sy(b.home[i]))} rx="2" style=${{ fill: "var(--c1)" }} />
          <rect x=${sx(l) + half + 1} y=${sy(b.away[i])} width=${half - 1} height=${Math.max(0, ih - sy(b.away[i]))} rx="2" style=${{ fill: "var(--c2)" }} />
          <text class="tick-label" x=${sx(l) + sx.bandwidth / 2} y=${ih + 18} text-anchor="middle">${l}</text>
        </g>`)}
      </g>`;
    }}
  </${Frame}>`;
}

function PlayersTable({ side, list, team, scope, hasXg = true }) {
  const cols = [
    { key: "name", label: "Player", sticky: true, firstDir: "asc", render: (r) => html`<a class="cell-inline" href=${playerHref(r.id, { league: scope.league, season: scope.season })}><span class="name">${r.name}</span><span class="muted xsmall">${r.position}</span></a>` },
    { key: "minutes", label: "Min", num: true },
    { key: "goals", label: "G", num: true, className: "strong" }, { key: "assists", label: "A", num: true },
    { key: "shots", label: "Sh", num: true }, { key: "xg", label: "xG", num: true, render: (r) => nf(r.xg, 2) },
    { key: "xa", label: "xA", num: true, render: (r) => nf(r.xa, 2) }, { key: "kp", label: "KP", num: true },
    { key: "cards", label: "Cards", num: true, sortable: false, value: (r) => r.yellow + r.red * 2, render: (r) => (r.red ? "🟥" : r.yellow ? "🟨" : "") },
  ];
  return html`<${Card} flush title=${team}>
    <${DataTable} columns=${cols} rows=${list} rowKey=${(r) => r.id} initialSort=${{ key: hasXg ? "xg" : "minutes", dir: "desc" }} dense tight caption=${`${team} players`} />
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

/** A section that needs xG, on a match Understat has not published yet: the card stays, and says when it fills. */
function XgLater({ title }) {
  return html`<${Card} title=${title}><p class="small muted">Expected goals come from Understat after full time (it is looked for from the 90th minute, every three minutes). This fills in then.</p></${Card}>`;
}

const VIEWS = [
  { value: "overview", label: "Overview" }, { value: "shots", label: "Shots" }, { value: "passing", label: "Passing" },
  { value: "moves", label: "Moves" }, { value: "defending", label: "Defending" }, { value: "lineups", label: "Line-ups" }, { value: "players", label: "Players" },
];

/** The state of the match in a word or a minute: "Full time", "Half time", "67′". */
function statusOf(d, f) {
  if (!d.live) return { text: "Full time", live: false };
  if (d.live.final) return { text: "Full time", live: false };
  const e = String(d.live.elapsed || "").replace(/['′’]+$/, "");
  return { text: e === "HT" ? "Half time" : e ? `${e}′` : "Live", live: e !== "HT" };
}

function Scoreboard({ d, c, hasXg }) {
  const { report: r, stats } = d;
  const f = r.fixture;
  const status = statusOf(d, f);
  const xh = r.summary?.home?.xg ?? f.hxg, xa = r.summary?.away?.xg ?? f.axg;
  const ht = c?.info?.ht;
  const won = f.hg > f.ag ? "h" : f.ag > f.hg ? "a" : "";
  const facts = [c?.info?.venue, c?.info?.attendance ? `${Number(c.info.attendance).toLocaleString("en-GB")} there` : null, c?.info?.referee ? `Referee ${c.info.referee}` : null].filter(Boolean);
  return html`<section class=${"scoreboard" + (status.live ? " live" : "")} aria-label="Score">
    <div class="sb-main">
      <div class=${"sb-col" + (won === "h" ? " won" : "")}><a class="sb-team" href=${teamHref(f.home)}><${Crest} team=${f.home} short=${f.home_short} size=${52} /><span>${f.home}</span></a><${Scorers} list=${r.scorers?.h} align="start" /></div>
      <div class="sb-score">
        <div class=${"sb-status" + (status.live ? " live" : "")}>${status.live ? html`<i></i>` : null}${status.text}</div>
        <div class="figure"><span class=${won === "h" ? "w" : ""}>${f.hg}</span><i>–</i><span class=${won === "a" ? "w" : ""}>${f.ag}</span></div>
        ${ht && (d.live ? d.live.elapsed !== "HT" : true) ? html`<div class="sb-ht num">Half time ${ht[0]}–${ht[1]}</div>` : null}
      </div>
      <div class=${"sb-col away" + (won === "a" ? " won" : "")}><a class="sb-team away" href=${teamHref(f.away)}><${Crest} team=${f.away} short=${f.away_short} size=${52} /><span>${f.away}</span></a><${Scorers} list=${r.scorers?.a} align="end" /></div>
    </div>
    <div class="sb-strip">
      ${hasXg ? html`<div class="sb-meter" title=${matchXgNote(f, r.summary)}><b class="num">${nf(xh, 2)}</b><span class="sb-meter-mid"><span class="sb-meter-label">Expected goals</span><span class="tug-bars"><i class="h" style=${{ width: (xh / ((xh + xa) || 1)) * 100 + "%" }}></i><i class="a" style=${{ width: (xa / ((xh + xa) || 1)) * 100 + "%" }}></i></span></span><b class="num">${nf(xa, 2)}</b></div>`
        : html`<div class="sb-meter wait"><span class="sb-meter-label">${d.live?.overdue ? "No expected goals yet: Understat has not published this match" : "Expected goals arrive from Understat after full time"}</span></div>`}
      ${stats?.poss ? html`<div class="sb-meter"><b class="num">${stats.poss[0]}%</b><span class="sb-meter-mid"><span class="sb-meter-label">Possession</span><span class="tug-bars"><i class="h" style=${{ width: stats.poss[0] + "%" }}></i><i class="a" style=${{ width: stats.poss[1] + "%" }}></i></span></span><b class="num">${stats.poss[1]}%</b></div>` : null}
      <div class="sb-meter"><b class="num">${r.summary.home.shots}</b><span class="sb-meter-mid"><span class="sb-meter-label">Shots</span><span class="tug-bars"><i class="h" style=${{ width: (r.summary.home.shots / ((r.summary.home.shots + r.summary.away.shots) || 1)) * 100 + "%" }}></i><i class="a" style=${{ width: (r.summary.away.shots / ((r.summary.home.shots + r.summary.away.shots) || 1)) * 100 + "%" }}></i></span></span><b class="num">${r.summary.away.shots}</b></div>
    </div>
    ${facts.length ? html`<div class="sb-facts">${facts.map((x, i) => html`<span key=${i}>${x}</span>`)}</div>` : null}
  </section>`;
}

function MatchView({ d, live }) {
  const scope = useScope();
  const query = useLocation().query;
  const view = VIEWS.some((v) => v.value === query.view) ? query.view : query.tab === "deep" ? "players" : "overview";
  const tab = query.tab === "deep" ? "deep" : query.tab === "events" ? "events" : "quick";
  const [period, setPeriod] = useState("all");
  const { report: r, insights, scope: dscope, meta, stats } = d;
  const f = r.fixture, s = r.summary;
  const hasXg = r.has_xg !== false;   // false: a match Understat has not published, drawn from WhoScored's latest read
  const cq = useApi(`/api/match/${f.id}/centre`, { league: scope.league, season: scope.season }, d.live ? { staleMs: 0, persist: false, pollMs: 60000 } : {});
  const c = cq.data?.centre?.available ? cq.data.centre : null;
  const noEvents = cq.data?.centre && !cq.data.centre.available ? cq.data.centre.reason : null;
  const hrefOf = c ? linker(c, scope) : () => undefined;
  const boardSides = [{ label: f.home, short: f.home_short, color: "var(--c1)", goal: "right-hand goal" }, { label: f.away, short: f.away_short, color: "var(--c2)", mirror: true, goal: "left-hand goal" }];
  const boardShots = useMemo(() => [...r.shots.home.map((sh) => ({ ...sh, side: 0 })), ...r.shots.away.map((sh) => ({ ...sh, side: 1 }))].filter((sh) => sh.result !== "OwnGoal"), [r.shots]);
  const needsEvents = (node) => (c ? node : cq.loading && !cq.data ? html`<div class="card"><div class="card-body muted">Loading the event data…</div></div>` : html`<${NoEvents} reason=${noEvents} />`);

  const headToHead = html`<${Card} title="Head to head">
    <div class="stack" style=${{ "--gap": "12px" }}>
      ${hasXg ? html`<${Tug} label="Expected goals" home=${s.home.xg} away=${s.away.xg} format=${(v) => nf(v, 2)} />` : null}
      <${Tug} label="Shots" home=${s.home.shots} away=${s.away.shots} />
      <${Tug} label="On target" home=${s.home.on_target} away=${s.away.on_target} />
      ${hasXg ? html`<${Tug} label="xG per shot" home=${s.home.xg_per_shot} away=${s.away.xg_per_shot} format=${(v) => nf(v, 3)} />` : null}
      <${Tug} label=${hasXg ? "Big chances (0.30+)" : "Big chances (Opta)"} home=${s.home.big_chances} away=${s.away.big_chances} />
      <${Tug} label="Goals" home=${s.home.goals} away=${s.away.goals} />
    </div>
  </${Card}>`;

  const overview = html`
    ${d.live ? null : html`<${Insights} items=${insights} scope=${dscope} />`}
    ${c ? html`<${MomentumCard} c=${c} f=${f} />` : null}
    ${hasXg ? html`<div class="mrow m-race">
      <${Card} title="How the chances built up" sub="Running total of expected goals. Rings mark goals; hover a ring for the scorer.">
        <${XgRace} home=${r.timeline.home} away=${r.timeline.away} homeName=${f.home} awayName=${f.away} homeShort=${f.home_short} awayShort=${f.away_short} />
      </${Card}>
      <${Contributors} players=${r.players} f=${f} scope=${{ league: scope.league, season: scope.season }} />
    </div>` : null}
    ${c ? html`<${NumbersCard} c=${c} period=${period} onPeriod=${setPeriod} hasXg=${hasXg} /><${LeadersCard} c=${c} period=${period} hrefOf=${hrefOf} />`
      : html`<div class=${"mrow " + (stats ? "m-n2" : "")}>${headToHead}${stats ? html`<${HowPlayed} stats=${stats} f=${f} />` : null}</div>${noEvents ? html`<${NoEvents} reason=${noEvents} />` : null}`}
  `;

  const shots = html`
    <${Card} title="Every shot, and who took it" sub=${`${f.home} attack the right-hand goal, ${f.away} the left. Pick a player to see only his shots; pick a shot, on the pitch or in the list, for what it was worth and how it came about.`}>
      <${ShotBoard} shots=${boardShots} sides=${boardSides} takers hasXg=${hasXg} sort="time"
        playerHref=${(sh) => playerHref(sh.player_id, { league: scope.league, season: scope.season })} />
    </${Card}>
    <div class="mrow m-n2">
      ${c ? html`<${GoalMouthCard} c=${c} f=${f} period="all" hasXg=${hasXg} />` : headToHead}
      <${Card} title="When the chances came" sub=${hasXg ? "Expected goals in each period of the match." : "Shots in each period of the match (expected goals come from Understat after full time)."}>
        <${Buckets} b=${r.buckets} homeShort=${f.home_short} awayShort=${f.away_short} />
        <div class="legend" style=${{ marginTop: "6px" }}><span class="item"><span class="swatch box" style=${{ background: "var(--c1)" }}></span>${f.home}</span><span class="item"><span class="swatch box" style=${{ background: "var(--c2)" }}></span>${f.away}</span></div>
      </${Card}>
    </div>
  `;

  const players = html`
    <div class="row between top wrap" style=${{ gap: "10px" }}>
      <${Segmented} label="Player view" value=${tab} onChange=${(t) => setQuery({ tab: t === "quick" ? null : t })} options=${[{ value: "quick", label: "Quick view" }, { value: "deep", label: "Deep analytics" }, ...(c ? [{ value: "events", label: "By half" }] : [])]} />
      ${tab === "deep" ? html`<span class="muted small">Every player who played, with every Scout metric for this match alone.</span>` : null}
      ${tab === "events" && c ? html`<${PeriodPicker} c=${c} value=${period} onChange=${setPeriod} />` : null}
    </div>
    ${tab === "deep"
      ? html`<${MatchDeep} id=${f.id} scope=${scope} f=${f} live=${Boolean(d.live)} />`
      : tab === "events" && c ? html`<${EventPlayers} c=${c} f=${f} period=${period} hrefOf=${hrefOf} />`
      : html`<div class="grid cols-2">
        <${PlayersTable} side="h" list=${r.players.home} team=${f.home} scope=${scope} hasXg=${hasXg} />
        <${PlayersTable} side="a" list=${r.players.away} team=${f.away} scope=${scope} hasXg=${hasXg} />
      </div>`}
  `;

  return html`
    <${PageHead} eyebrow=${`${dscope.league_name} · ${dscope.label} · Matchweek ${f.round}`} title=${`${f.home} v ${f.away}`} sub=${`${weekday(f.date)} ${dateLong(f.date)}, kicked off ${timeOf(f.dt)}.`} />
    <span class="wide-page" hidden></span>
    ${d.live ? html`<${LiveNotice} d=${live} />` : html`<${DataNotices} scope=${dscope} meta=${meta} />`}
    <${Scoreboard} d=${d} c=${c} hasXg=${hasXg} />
    <div class="viewbar"><${Tabs} label="Match sections" value=${view} onChange=${(v) => setQuery({ view: v === "overview" ? null : v, tab: null })} tabs=${VIEWS} /></div>
    ${view === "shots" ? shots
      : view === "passing" ? needsEvents(c ? html`<${PassingSection} c=${c} f=${f} period=${period} onPeriod=${setPeriod} />` : null)
      : view === "moves" ? needsEvents(c ? html`<${MovesSection} c=${c} f=${f} period=${period} onPeriod=${setPeriod} hrefOf=${hrefOf} />` : null)
      : view === "defending" ? needsEvents(c ? html`<${DefendingSection} c=${c} f=${f} period=${period} onPeriod=${setPeriod} />` : null)
      : view === "lineups" ? needsEvents(c ? html`<${LineupsSection} c=${c} f=${f} hrefOf=${hrefOf} />` : null)
      : view === "players" ? players : overview}
  `;
}

export default function MatchPage({ params }) {
  const { league, season } = useScope();
  const id = Number(params.id);
  // A match belongs to one league and season. Its address says which, so a link opened later, or sent to someone, finds the match whatever
  // league the app was left on; an address without them (an old link) gets them from the league in view.
  const { query } = useLocation();
  useEffect(() => {
    if (query.league && query.league !== league) setLeague(query.league);
    if (query.season && query.season !== String(season)) setSeason(query.season);
    if (!query.league) setQuery({ league, season: season === "auto" ? null : season });
  }, [query.league, query.season, id]);
  // Where the match is first. One Understat has not published yet (being played, or just finished) is drawn from WhoScored's latest read:
  // the same page, with the parts that need xG waiting for Understat. Asking with follow=1 tells the updater someone is watching it.
  const [unlisted, setUnlisted] = useState(false);   // asked again every minute only while Understat has not published the match
  const live = useApi(`/api/match/${id}/live`, { league, season, follow: 1 }, { staleMs: 0, persist: false, pollMs: unlisted ? 60000 : 0 });
  const played = live.data?.fixture?.id === id ? Boolean(live.data.fixture.played) : null;   // never the previous match's answer
  const fromRead = played === false && Boolean(live.data?.read);
  useEffect(() => setUnlisted(played === false), [played]);
  // a report made from a read has its own cache key, is asked again every minute and is never kept in the browser's store: once Understat
  // has the match, the finished report is fetched afresh and no half-time copy can come back in its place
  const q = useApi(`/api/match/${id}`, fromRead ? { league, season, live: 1 } : { league, season },
    { enabled: played === true || fromRead, staleMs: fromRead ? 0 : 20000, persist: !fromRead, pollMs: fromRead ? 60000 : 0 });
  useDocumentTitle(played === false ? "Live match" : "Match report");
  if (played === false && !fromRead) return html`<${Async} q=${live}>${(dd) => html`<${LiveView} d=${dd} />`}</${Async}>`;
  return html`<${Async} q=${played || fromRead ? q : live}>${(dd) => (played || fromRead ? html`<${MatchView} d=${dd} live=${fromRead ? live.data : null} />` : null)}</${Async}>`;
}
