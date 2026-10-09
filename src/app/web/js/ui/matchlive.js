// A match being played, or just finished before Understat has listed it: where it is by the clock, what WhoScored's page said when it was
// last read (half time, full time), and when the next read happens. Provisional numbers are said to be provisional.
import { html } from "../lib/html.js";
import { nf } from "../lib/format.js";
import { PHASE_LABEL, kickoff } from "../lib/matchfmt.js";
import { Badge, Card, Crest, FavouriteButton, Notice, PageHead, teamHref } from "./common.js";
import { DataTable } from "./table.js";

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

function Players({ rows, team }) {
  if (!rows?.length) return null;
  const cols = [
    { key: "name", label: team, sortable: false, className: "strong" },
    { key: "touches", label: "Touches", num: true, sortable: false },
    { key: "shots", label: "Shots", num: true, sortable: false },
    { key: "key_passes", label: "Key passes", num: true, sortable: false },
    { key: "tackles", label: "Tackles", num: true, sortable: false },
  ];
  return html`<${DataTable} columns=${cols} rows=${rows} rowKey=${(r) => r.name} dense caption=${`${team}: most involved so far`} />`;
}

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
      <${Card} flush title="Most involved" sub="Each side's five players with the most touches so far.">
        <${Players} rows=${read.players.home} team=${f.home} />
        <${Players} rows=${read.players.away} team=${f.away} />
      </${Card}>
    </div>` : null}
  `;
}
