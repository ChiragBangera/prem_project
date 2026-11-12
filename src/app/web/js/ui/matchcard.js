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

/** Kicked off more than two days ago: a result that has still not arrived is not "arriving shortly". */
const overdue = (m, now = Date.now()) => !!m.utc && now - Date.parse(m.utc) > 2 * 86400e3;

export function MatchCard({ m, showDate = true, link = true }) {
  const k = kickoff(m);
  // `result`: finished and stored from WhoScored, but Understat has not published it. The score, scorers and counts are real; xG is not there yet.
  const unpublished = !m.played && m.result ? m.result : null;
  const played = m.played || !!unpublished;
  if (unpublished) m = { ...m, hg: unpublished.hg, ag: unpublished.ag };
  const clock = phaseOf(m), phase = clock === "full_time" && m.still_playing ? "second_half" : clock;   // the last read found it still in play
  const live = !played && phase !== "upcoming";
  const homeWon = played && m.hg > m.ag, awayWon = played && m.ag > m.hg;
  const stats = m.stats || {};
  const poss = stats.poss;
  const note = m.played ? verdict(m) : null;
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
      ${m.hxg != null && m.axg != null ? html`<div class="mc-xg" title="Expected goals: the chances each side made">
        <b class=${"num" + (m.hxg > m.axg ? " lead" : "")}>${nf(m.hxg, 2)}</b>
        <span class="mc-xg-mid"><span class="tug-bars"><i class="h" style=${{ width: (m.hxg / ((m.hxg + m.axg) || 1)) * 100 + "%" }}></i><i class="a" style=${{ width: (m.axg / ((m.hxg + m.axg) || 1)) * 100 + "%" }}></i></span><span class="mc-stat-label">xG</span></span>
        <b class=${"num" + (m.axg > m.hxg ? " lead" : "")}>${nf(m.axg, 2)}</b>
      </div>` : unpublished ? html`<div class="mc-noxg muted small" title="The score, scorers and counts are from WhoScored. Expected goals come from Understat, which has not published this match.">No xG yet: Understat has not published this match</div>` : null}
      ${poss ? html`<${Pair} label="Possession" a=${poss[0]} b=${poss[1]} fmt=${(v) => `${v}%`} />` : null}
      ${m.shots ? html`<${Pair} label="Shots" a=${m.shots.h} b=${m.shots.a} />` : null}
    </div>` : html`<div class="mc-upnext muted small">${live ? (phase === "full_time" ? (overdue(m) ? "Finished, but neither source has it here yet: the score appears with the next update." : "Finished: Understat's shots and xG arrive shortly. Open it for the event data read at full time.") : "Being played now. Open it to follow it.") : `Kicks off ${k.long} at ${k.time}`}</div>`}`;
  return link
    ? html`<a class=${cls("mc", m.flag && "flagged", !played && "upcoming")} href=${matchHref(m.id)} aria-label=${`${m.home} ${played ? `${m.hg} ${m.away} ${m.ag}` : `v ${m.away}`}`}>${body}</a>`
    : html`<div class=${cls("mc", m.flag && "flagged", !played && "upcoming")}>${body}</div>`;
}
