// A match being played, or just finished before Understat has listed it: where it is by the clock, what WhoScored's page said when it was
// last read (half time, full time), and when the next read happens. Provisional numbers are said to be provisional.
import { html } from "../lib/html.js";
import { nf } from "../lib/format.js";
import { PHASE_LABEL, kickoff } from "../lib/matchfmt.js";
import { Badge, Card, Crest, FavouriteButton, Notice, PageHead, teamHref } from "./common.js";
import { DataTable } from "./table.js";
import { MatchPitch } from "../charts/pitch.js";

/** A tug-of-war row: home value grows left, away value grows right. */
export function Tug({ label, home, away, format = (v) => String(v), inverse = false }) {
  const total = (home + away) || 1;
  const homeBetter = inverse ? home < away : home > away;
  const awayBetter = inverse ? away < home : away > home;
  return html`<div class="tug">
    <b class=${"num " + (homeBetter ? "lead" : "")}>${format(home)}</b>
    <div class="tug-mid"><span class="tug-label">${label}</span>
      <span class="tug-bars"><i class="h" style=${{ width: (home / total) * 100 + "%" }}></i><i class="a" style=${{ width: (away / total) * 100 + "%" }}></i></span></div>
    <b class=${"num " + (awayBetter ? "lead" : "")}>${format(away)}</b>
  </div>`;
}

const clock = (ts) => new Date(ts * 1000).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });

const PHASE_SUB = {
  upcoming: "Not started yet.",
  first_half: "First half, by the clock.",
  half_time: "Half time, by the clock.",
  second_half: "Second half, by the clock.",
  full_time: "Finished by the clock. Understat lists the result, its shots and xG a little after the final whistle; the full report appears here then.",
};

/** What the latest read was, in words: "Read at half time (HT, 1 : 0) at 15:49. Provisional: replaced by the full-time read." */
function readLine(read) {
  if (!read) return null;
  const when = read.at ? ` at ${clock(read.at)}` : "";
  const what = read.final ? "Read at full time" : read.elapsed === "HT" ? "Read at half time" : `Read in play (${read.elapsed || "?"}')`;
  return `${what}${read.score ? ` (${read.score.replace(" : ", "–")})` : ""}${when}.${read.final ? " Final: these numbers will not change." : " Provisional: the full-time read replaces them, and they count nowhere else until then."}`;
}

function nextLine(d) {
  if (!d.events_on) return "Event data is switched off for this league, so nothing is read during matches. Switch it on in Data to read matches at full time, and at half time for the ones you follow.";
  const n = d.next_read;
  if (!n) return null;
  const moment = n.moment === "ht" ? "half time" : "full time";
  return n.at <= d.now + 30 ? `The ${moment} read is happening now.` : `Next read: ${moment}, about ${clock(n.at)}.`;
}

function followLine(d) {
  if (!d.events_on) return null;
  if (d.followed === "favourite") return "You follow this match (a favourite team plays): it is read at half time as well as full time.";
  if (d.followed === "opened") return "You opened this match while it is being played, so it is followed: read at half time as well as full time.";
  return "Every match is read at full time. Make one of these teams a favourite to have its matches read at half time too.";
}

const TIMELINE_WORD = { goal: "Goal", penalty: "Penalty", own_goal: "Own goal", yellow: "Yellow card", red: "Red card", sub: "On" };

/** Goals, cards and substitutions in order, each under its side. */
function Timeline({ items, f }) {
  if (!items?.length) return html`<p class="small muted">No goals, cards or substitutions yet.</p>`;
  return html`<div class="live-timeline">${items.map((t, i) => html`<div key=${i} class=${"live-ev " + t.side}>
    <span class="num live-min">${t.minute}'</span>
    <span class=${"live-kind " + t.kind}>${TIMELINE_WORD[t.kind] || t.kind}</span>
    <span class="live-who">${t.player || "–"}<span class="muted xsmall"> · ${t.side === "home" ? f.home : f.away}</span></span>
  </div>`)}</div>`;
}

function Lineup({ rows, team, formation }) {
  if (!rows?.length) return null;
  const starters = rows.filter((p) => p.start), bench = rows.filter((p) => !p.start);
  return html`<div class="stack" style=${{ "--gap": "6px" }}>
    <div class="row between"><b>${team}</b><span class="muted small">${formation ? formation.split("").join("-") : ""}</span></div>
    <ol class="live-xi">${starters.map((p) => html`<li key=${p.name}><span class="num muted">${p.shirt ?? ""}</span> ${p.name} <span class="muted xsmall">${p.pos || ""}</span></li>`)}</ol>
    ${bench.length ? html`<div class="xsmall muted">Bench: ${bench.map((p) => p.name).join(", ")}</div>` : null}
  </div>`;
}

const PLAYER_COLS = (f) => [
  { key: "name", label: "Player", className: "strong", render: (r) => html`<span class="row" style=${{ gap: "6px" }}><i class=${"deep-side " + r.side} style=${{ background: r.side === "home" ? "var(--c1)" : "var(--c2)" }} title=${r.side === "home" ? f.home : f.away}></i>${r.name}</span>` },
  { key: "pos", label: "Pos" },
  { key: "touches", label: "Touches", num: true },
  { key: "passes", label: "Passes", num: true },
  { key: "pass_acc", label: "Pass %", num: true, render: (r) => (r.pass_acc == null ? "–" : `${r.pass_acc}%`) },
  { key: "key_passes", label: "Key passes", num: true },
  { key: "shots", label: "Shots", num: true },
  { key: "sot", label: "On target", num: true },
  { key: "takeons_won", label: "Dribbles won", num: true },
  { key: "tackles", label: "Tackles", num: true },
  { key: "interceptions", label: "Interceptions", num: true },
  { key: "recoveries", label: "Recoveries", num: true },
  { key: "fouls", label: "Fouls", num: true },
];

export function LiveView({ d }) {
  const f = d.fixture, read = d.read, st = read?.stats;
  const k = kickoff(f);
  const [hg, ag] = read?.score ? read.score.split(":").map((x) => x.trim()) : ["", ""];
  const tone = d.phase === "upcoming" ? "" : "accent";
  return html`
    <${PageHead} eyebrow=${`${d.scope.league_name} · ${d.scope.label} · Matchweek ${f.round}`} title=${`${f.home} v ${f.away}`}
      sub=${`${k.long}, kick-off ${k.time}. ${PHASE_SUB[d.phase] || ""}`} />
    <div class="scoreboard card">
      <div class="sb-col"><a class="sb-team" href=${teamHref(f.home)}><${Crest} team=${f.home} short=${f.home_short} size=${56} /><span>${f.home}</span></a>
        <${FavouriteButton} league=${d.scope.league} team=${f.home} compact /></div>
      <div class="sb-score"><div class="figure">${hg || "–"}<i>–</i>${ag || "–"}</div>
        <div class="sb-xg"><${Badge} tone=${tone}>${read?.final ? "Full time" : PHASE_LABEL[d.phase]}</${Badge}>${st?.poss ? html` <span class="num">possession ${st.poss[0]}–${st.poss[1]}%</span>` : null}</div></div>
      <div class="sb-col away"><a class="sb-team away" href=${teamHref(f.away)}><${Crest} team=${f.away} short=${f.away_short} size=${56} /><span>${f.away}</span></a>
        <${FavouriteButton} league=${d.scope.league} team=${f.away} compact /></div>
    </div>
    <${Notice} icon="info">
      <div class="stack" style=${{ "--gap": "4px" }}>
        ${read ? html`<span><b>${readLine(read)}</b></span>` : d.events_on && d.phase !== "upcoming" ? html`<span><b>No read yet.</b> Event data comes from WhoScored's match centre, read on the moments below; nothing is read minute by minute.</span>` : null}
        ${nextLine(d) ? html`<span>${nextLine(d)}</span>` : null}
        ${followLine(d) ? html`<span class="small secondary">${followLine(d)}</span>` : null}
      </div>
    </${Notice}>
    ${st ? html`<div class="mrow m-5-7">
      <${Card} title="So far" sub=${read.final ? "The whole match, from the event data." : `Up to the read at ${clock(read.at)}.`}>
        <div class="stack" style=${{ "--gap": "10px" }}>
          ${st.poss ? html`<${Tug} label="Possession (share of passes)" home=${st.poss[0]} away=${st.poss[1]} format=${(v) => `${v}%`} />` : null}
          ${st.pass_acc[0] != null && st.pass_acc[1] != null ? html`<${Tug} label="Pass accuracy" home=${st.pass_acc[0]} away=${st.pass_acc[1]} format=${(v) => `${v}%`} />` : null}
          ${st.rows.map((r) => html`<${Tug} key=${r.key} label=${r.label} home=${r.home} away=${r.away} format=${(v) => nf(v, 0)} inverse=${r.key === "fouls" || r.key === "yellow"} />`)}
        </div>
      </${Card}>
      <${Card} title="Shots" sub=${`From WhoScored's page: where each shot was taken (filled: scored). Not sized by xG: Understat's xG arrives after the match.`}>
        <${MatchPitch} home=${read.shots?.home || []} away=${read.shots?.away || []} />
        <div class="row between xsmall muted"><span>${f.home} attack →</span><span>← ${f.away} attack</span></div>
      </${Card}>
    </div>
    <div class="mrow m-n2">
      <${Card} title="Goals, cards and substitutions"><${Timeline} items=${read.timeline} f=${f} /></${Card}>
      <${Card} title="Line-ups"><div class="mrow m-n2"><${Lineup} rows=${read.lineups?.home} team=${f.home} formation=${st.formations[0]} /><${Lineup} rows=${read.lineups?.away} team=${f.away} formation=${st.formations[1]} /></div></${Card}>
    </div>
    <${Card} flush title="Every player so far" sub="Both teams, from the event data. Click a column to sort.">
      <${DataTable} columns=${PLAYER_COLS(f)} rows=${read.players || []} rowKey=${(r) => r.side + r.name} dense caption="Every player so far" />
    </${Card}>` : null}
  `;
}
