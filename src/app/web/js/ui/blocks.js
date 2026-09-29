// Domain blocks shared by several pages: a result, an upcoming fixture, a probability list.
import { html } from "../lib/html.js";
import { cls, dateShort, nf, pct, probText, timeOf, weekday } from "../lib/format.js";
import { Icon } from "../lib/icons.js";
import { Crest, matchHref, teamHref, Badge, Delta } from "./common.js";
import { href } from "../lib/router.js";

export const labHref = (home, away) => href("/forecast", { tab: "lab", home, away });
import { ProbBar, BarList } from "../charts/bars.js";

export const FLAG_LABEL = {
  against_run_of_play: "Against the run of play",
  favourite_held: "Favourite held",
};

/** One sentence that says what the chances thought of a played match. */
export function verdict(m) {
  const home = m.hg > m.ag, away = m.ag > m.hg;
  if (m.flag === "against_run_of_play") {
    const winner = home ? m.home : m.away;
    const p = home ? m.p_home : m.p_away;
    return `${winner} won although the chances gave them just ${pct(p)}.`;
  }
  if (m.flag === "favourite_held") {
    const fav = m.p_home > m.p_away ? m.home : m.away;
    return `${fav} were ${pct(Math.max(m.p_home, m.p_away))} favourites on chances and only drew.`;
  }
  return null;
}

export function ResultItem({ m, showDate = true }) {
  const v = verdict(m);
  const homeWon = m.hg > m.ag, awayWon = m.ag > m.hg;
  return html`<a class=${cls("result", v && "flagged")} href=${matchHref(m.id)}>
    <div class="result-teams">
      <div class=${cls("line", homeWon && "won")}><${Crest} team=${m.home} short=${m.home_short} size=${22} /><span class="name">${m.home}</span><span class="goals figure num">${m.hg}</span></div>
      <div class=${cls("line", awayWon && "won")}><${Crest} team=${m.away} short=${m.away_short} size=${22} /><span class="name">${m.away}</span><span class="goals figure num">${m.ag}</span></div>
    </div>
    <div class="result-sub">
      <span class="num">xG ${nf(m.hxg, 1)} – ${nf(m.axg, 1)}</span>
      ${showDate ? html`<span>${weekday(m.date)} ${dateShort(m.date)}</span>` : null}
      ${m.flag ? html`<${Badge} tone="warn">${FLAG_LABEL[m.flag]}</${Badge}>` : null}
    </div>
    ${v ? html`<div class="result-verdict">${v}</div>` : null}
  </a>`;
}

export function FixtureRow({ f, onOpen, showRound }) {
  return html`<a class="fixture" href=${labHref(f.home, f.away)}>
    <div class="when num"><b>${weekday(f.date)} ${dateShort(f.date)}</b><span class="muted">${timeOf(f.dt)}${showRound && f.round ? ` · MW${f.round}` : ""}</span></div>
    <div class="teams">
      <span class="t"><${Crest} team=${f.home} short=${f.home_short} size=${22} /><span class="truncate">${f.home}</span></span>
      <span class="t"><${Crest} team=${f.away} short=${f.away_short} size=${22} /><span class="truncate">${f.away}</span></span>
    </div>
    <div class="prob"><${ProbBar} home=${f.p_home} draw=${f.p_draw} away=${f.p_away} homeLabel=${f.home_short} awayLabel=${f.away_short} compact /></div>
    <div class="exp num"><b>${nf(f.exp_home, 1)} – ${nf(f.exp_away, 1)}</b><span class="muted">${f.most_likely ? `likely ${f.most_likely[0]}–${f.most_likely[1]}` : ""}</span></div>
  </a>`;
}

/** A ranked list of probabilities for one race (title, top four, survival). */
export function RaceList({ title, sub, rows, empty, foot }) {
  return html`<div class="racelist">
    <div class="racelist-head"><h3>${title}</h3>${sub ? html`<span class="muted small">${sub}</span>` : null}</div>
    ${rows.length
      ? html`<${BarList} max=${1} rows=${rows.map((r) => ({ key: r.team, label: html`<a class="cell-team" href=${teamHref(r.team)}><${Crest} team=${r.team} short=${r.short} size=${20} /><span class="truncate">${r.team}</span></a>`, value: r.p, right: probText(r.p) }))} />`
      : html`<div class="muted small">${empty}</div>`}
    ${foot ? html`<div class="racelist-foot">${foot}</div>` : null}
  </div>`;
}

export function MoverRow({ m, up }) {
  return html`<div class="mover"><${Icon} name=${up ? "trendUp" : "trendDown"} size="sm" class=${up ? "up" : "down"} />
    <a class="cell-team" href=${teamHref(m.team)}><${Crest} team=${m.team} short=${m.short} size=${20} />${m.team}</a>
    <span class="muted num">${m.from}<i>→</i>${m.to}</span></div>`;
}

/** A signed gap with a small bar: blue above expectation, orange below. */
export function GapCell({ value, max = 12, digits = 1 }) {
  if (value == null || !Number.isFinite(value)) return html`<span class="muted">–</span>`;
  const w = Math.min(50, (Math.abs(value) / max) * 50);
  return html`<span class="gap-bar">
    <span class="gap-track" aria-hidden="true"><i class="axis"></i><i class=${"fill " + (value >= 0 ? "pos" : "neg")} style=${value >= 0 ? { left: "50%", width: w + "%" } : { right: "50%", width: w + "%" }}></i></span>
    <span class="val"><${Delta} value=${value} digits=${digits} /></span>
  </span>`;
}
