// A match as a compact card: big team names and score, who scored under each side, and the numbers that explain the game (xG, possession, shots).
import { html } from "../lib/html.js";
import { cls, nf } from "../lib/format.js";
import { FLAG_LABEL, PHASE_LABEL, kickoff, phaseOf, scorerLines, shortName, verdict } from "../lib/matchfmt.js";
import { Icon } from "../lib/icons.js";
import { Crest, Badge, matchHref, useFavourite } from "./common.js";

export { FLAG_LABEL, kickoff, scorerLines, shortName, verdict };

const Scorers = ({ list, red }) => {
  const lines = scorerLines(list);
  if (!lines.length && !(red || []).length) return null;
  return html`<div class="mc-scorers">
    ${lines.map((s, i) => html`<span class="mc-scorer" key=${s.id ?? i}><b>${s.name}</b> ${s.minutes.join(", ")}</span>`)}
    ${(red || []).map((r, i) => html`<span class="mc-red" key=${"r" + i} title="Sent off"><i></i>${shortName(r.player)}</span>`)}
  </div>`;
};

/** A pair of numbers where the larger side is bold. `fmt` formats each; `inverse` makes the smaller one the leader (fouls, say). */
function Pair({ label, a, b, fmt = (v) => v, inverse = false }) {
  if (a == null || b == null) return null;
  const lead = a === b ? 0 : (a > b) !== inverse ? 1 : 2;
  return html`<div class="mc-stat"><span class="mc-stat-label">${label}</span>
    <span class="mc-stat-val num"><b class=${lead === 1 ? "lead" : ""}>${fmt(a)}</b><i>–</i><b class=${lead === 2 ? "lead" : ""}>${fmt(b)}</b></span></div>`;
}

/** A small filled star after a favourite team's name. */
function FavMark({ team }) {
  return useFavourite(team) ? html`<span class="mc-fav" title="A favourite team"><${Icon} name="star" size="sm" /></span>` : null;
}

export function MatchCard({ m, showDate = true, link = true }) {
  const k = kickoff(m);
  const played = m.played;
  const clock = phaseOf(m), phase = clock === "full_time" && m.still_playing ? "second_half" : clock;   // the last read found it still in play
  const live = !played && phase !== "upcoming";
  const homeWon = played && m.hg > m.ag, awayWon = played && m.ag > m.hg;
  const stats = m.stats || {};
  const poss = stats.poss;
  const note = played ? verdict(m) : null;
  const body = html`
    <div class="mc-top">
      <span class="mc-when num">${showDate ? `${k.day} · ` : ""}${k.time}</span>
      <span class="mc-status">${live ? html`<${Badge} tone="accent">${PHASE_LABEL[phase]}</${Badge}>` : played ? "FT" : "Upcoming"}${m.flag ? html` <${Badge} tone="warn" title=${note || ""}>${FLAG_LABEL[m.flag]}</${Badge}>` : ""}</span>
    </div>
    <div class="mc-board">
      <div class=${cls("mc-side", homeWon && "won")}>
        <${Crest} team=${m.home} short=${m.home_short} size=${30} />
        <div class="mc-who"><span class="mc-name">${m.home}<${FavMark} team=${m.home} /></span>${played ? html`<${Scorers} list=${m.scorers?.h} red=${m.red?.h} />` : null}</div>
        <span class="mc-goals figure num">${played ? m.hg : ""}</span>
      </div>
      <div class=${cls("mc-side", awayWon && "won")}>
        <${Crest} team=${m.away} short=${m.away_short} size=${30} />
        <div class="mc-who"><span class="mc-name">${m.away}<${FavMark} team=${m.away} /></span>${played ? html`<${Scorers} list=${m.scorers?.a} red=${m.red?.a} />` : null}</div>
        <span class="mc-goals figure num">${played ? m.ag : ""}</span>
      </div>
    </div>
    ${played ? html`<div class="mc-stats">
      <${Pair} label="xG" a=${m.hxg} b=${m.axg} fmt=${(v) => nf(v, 2)} />
      ${poss ? html`<${Pair} label="Possession" a=${poss[0]} b=${poss[1]} fmt=${(v) => `${v}%`} />` : null}
      ${m.shots ? html`<${Pair} label="Shots" a=${m.shots.h} b=${m.shots.a} />` : null}
    </div>` : html`<div class="mc-upnext muted small">${live ? (phase === "full_time" ? "Finished: Understat's shots and xG arrive shortly. Open it for the event data read at full time." : "Being played now. Open it to follow it.") : `Kicks off ${k.long} at ${k.time}`}</div>`}`;
  return link
    ? html`<a class=${cls("mc", m.flag && "flagged", !played && "upcoming")} href=${matchHref(m.id)} aria-label=${`${m.home} ${played ? `${m.hg} ${m.away} ${m.ag}` : `v ${m.away}`}`}>${body}</a>`
    : html`<div class=${cls("mc", m.flag && "flagged", !played && "upcoming")}>${body}</div>`;
}
