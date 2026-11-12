// A match being played, or just finished before Understat has listed it: where it is by the clock, what WhoScored's page said when it was
// last read (half time, full time), and when the next read happens. Provisional numbers are said to be provisional.
import { html } from "../lib/html.js";
import { PHASE_LABEL, kickoff } from "../lib/matchfmt.js";
import { Card, Crest, FavouriteButton, Form, Notice, PageHead, teamHref } from "./common.js";
import { useApi } from "../lib/api.js";
import { href } from "../lib/router.js";
import { nf, ordinal, signed } from "../lib/format.js";

/** A tug-of-war row: home value grows left, away value grows right. */
export function Tug({ label, home, away, format = (v) => String(v), inverse = false, neutral = false, values, lead }) {
  const total = (home + away) || 1;
  const homeBetter = !neutral && (inverse ? home < away : home > away);   // neutral: a matter of style, neither side is "ahead"
  const awayBetter = !neutral && (inverse ? away < home : away > home);
  if (values) return html`<div class="tug">
    <b class=${"num " + (lead === 0 ? "lead" : "")}>${values[0]}</b>
    <div class="tug-mid"><span class="tug-label">${label}</span>
      <span class="tug-bars"><i class="h" style=${{ width: (home / total) * 100 + "%" }}></i><i class="a" style=${{ width: (away / total) * 100 + "%" }}></i></span></div>
    <b class=${"num " + (lead === 1 ? "lead" : "")}>${values[1]}</b>
  </div>`;
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

/** What a live match's page is made from, in one line of facts: which read, what comes next, when xG arrives. ``d`` is /api/match/{id}/live. */
export function LiveNotice({ d }) {
  if (!d) return null;
  const read = d.read;
  const what = !read ? null : read.final ? "Full-time read" : read.elapsed === "HT" ? "Half-time read" : `Read at ${String(read.elapsed || "?").replace(/['′’]+$/, "")}′`;
  const next = nextLine(d);
  if (read?.final && d.overdue) {
    // finished days ago and still not in Understat (it is late, or down): this page is the stored WhoScored match, and says so plainly
    const day = read.at ? new Date(read.at * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : null;
    return html`<div class="livebar" role="status">
      <span class="livebar-item"><b>From WhoScored</b>${day ? `, read on ${day}` : ""}: score, shots, events and line-ups</span>
      <span class="livebar-item">Understat has not published this match, so there is no xG yet; nothing is estimated</span>
    </div>`;
  }
  return html`<div class="livebar" role="status">
    ${read ? html`<span class="livebar-item"><b>${what}</b>${read.at ? ` taken at ${clock(read.at)}` : ""}${read.final ? "" : " · provisional until full time"}</span>` : null}
    ${next ? html`<span class="livebar-item">${next}</span>` : null}
    <span class="livebar-item">Expected goals arrive from Understat after full time; nothing is estimated</span>
    ${followLine(d) ? html`<span class="livebar-item muted" title=${followLine(d)}>${d.followed ? "Followed: read at half time too" : "Read at full time only"}</span>` : null}
  </div>`;
}

const PREVIEW = [["pts_pg", "Points per game", 2], ["xg_pg", "xG per game", 2], ["xga_pg", "xG against per game", 2], ["xgd_pg", "xG difference per game", 2],
  ["gf_pg", "Goals per game", 2], ["ga_pg", "Goals against per game", 2], ["deep_pg", "Deep completions per game", 1], ["ppda", "Passes allowed per pressing action", 1]];
const LOWER = new Set(["xga_pg", "ga_pg", "ppda"]);

/** Each side's xG difference match by match, as small bars: above the line it made the better chances. */
function XgdStrip({ values, color }) {
  const list = (values || []).slice(-10);
  const top = Math.max(0.5, ...list.map((v) => Math.abs(v)));
  const w = 14;
  return html`<svg class="xgd-strip" viewBox=${`0 0 ${Math.max(1, list.length) * w} 44`} width=${Math.max(1, list.length) * w} height="44" role="img" aria-label=${`xG difference in the last ${list.length} matches: ${list.map((v) => nf(v, 1)).join(", ")}`}>
    <line x1="0" x2=${list.length * w} y1="22" y2="22" class="axis-line" />
    ${list.map((v, i) => { const h = (Math.abs(v) / top) * 20; return html`<rect key=${i} x=${i * w + 2} y=${v >= 0 ? 22 - h : 22} width=${w - 4} height=${Math.max(1, h)} rx="2" style=${{ fill: color, opacity: v >= 0 ? 1 : 0.4 }}><title>${signed(v, 2)}</title></rect>`; })}
  </svg>`;
}

/** Before a match is played: how the two sides compare on the season so far. */
function Preview({ f, scope }) {
  const q = useApi("/api/compare/teams", { a: f.home, b: f.away, league: scope.league, season: scope.season });
  const d = q.data;
  if (!d?.a?.row || !d?.b?.row || !d.a.row.played || !d.b.row.played) return null;
  const by = Object.fromEntries((d.metrics || []).map((m) => [m.key, m]));
  const side = (t, color, values) => html`<div class="pv-side">
    <div class="duo-head"><b><i class="side-dot" style=${{ background: color }}></i>${t.team}</b><span class="muted small num">${ordinal(t.row.rank)} · ${t.row.pts} pts</span></div>
    <div class="row between" style=${{ gap: "12px" }}><span class="small secondary num">${t.row.w}W ${t.row.d}D ${t.row.l}L · ${ordinal(t.row.rank_xpts)} on expected points</span><${Form} items=${(t.row.form || []).slice(-5)} /></div>
    <div class="row between" style=${{ gap: "12px", alignItems: "flex-end" }}><span class="xsmall muted">xG difference, last ${Math.min(10, (values || []).length)} matches</span><${XgdStrip} values=${values} color=${color} /></div>
  </div>`;
  const played = (d.meetings || []).filter((m) => m.played);
  return html`<${Card} title="The season so far, side by side" sub="How the two sides compare on what they have done this season. A description, not a prediction."
    actions=${html`<a class="btn sm" href=${href("/compare", { mode: "teams", a: f.home, b: f.away })}>Full comparison</a>`}>
    <div class="pv-grid">
      <div class="stack" style=${{ "--gap": "18px" }}>${side(d.a, "var(--c1)", d.xgd_by_match?.a)}${side(d.b, "var(--c2)", d.xgd_by_match?.b)}
        ${played.length ? html`<div class="small secondary">Already met this season: ${played.map((m) => `${m.home} ${m.hg}–${m.ag} ${m.away}`).join("; ")}.</div>` : null}</div>
      <div class="stack" style=${{ "--gap": "11px" }}>${PREVIEW.map(([key, label, digits]) => (by[key] && by[key].a != null && by[key].b != null
        ? html`<${Tug} key=${key} label=${label} home=${Math.max(0, by[key].a)} away=${Math.max(0, by[key].b)} format=${() => ""} inverse=${LOWER.has(key)} values=${[key === "xgd_pg" ? signed(by[key].a, digits) : nf(by[key].a, digits), key === "xgd_pg" ? signed(by[key].b, digits) : nf(by[key].b, digits)]} lead=${by[key].a === by[key].b ? null : (by[key].a > by[key].b) !== LOWER.has(key) ? 0 : 1} />` : null))}</div>
    </div>
  </${Card}>`;
}

/** A match that has not been read yet (not started, or being played before its first read): where it is by the clock, and when it will be read. */
export function LiveView({ d }) {
  const f = d.fixture;
  const k = kickoff(f);
  const live = d.phase === "first_half" || d.phase === "second_half";
  return html`
    <${PageHead} eyebrow=${`${d.scope.league_name} · ${d.scope.label} · Matchweek ${f.round}`} title=${`${f.home} v ${f.away}`}
      sub=${`${k.long}, kick-off ${k.time}. ${d.phase === "full_time" && d.overdue && !d.read ? "Finished, but neither Understat nor WhoScored has its result stored here yet. It appears with the next update." : PHASE_SUB[d.phase] || ""}`} />
    <section class=${"scoreboard" + (live ? " live" : "")} aria-label="Score">
      <div class="sb-main">
        <div class="sb-col won"><a class="sb-team" href=${teamHref(f.home)}><${Crest} team=${f.home} short=${f.home_short} size=${52} /><span>${f.home}</span></a>
          <${FavouriteButton} league=${d.scope.league} team=${f.home} compact /></div>
        <div class="sb-score">
          <div class=${"sb-status" + (live ? " live" : "")}>${live ? html`<i></i>` : null}${PHASE_LABEL[d.phase]}</div>
          <div class="figure">${d.phase === "upcoming" ? html`<span class="w sb-ko">${k.time}</span>` : html`<span>–</span><i>–</i><span>–</span>`}</div>
          ${d.phase === "upcoming" ? html`<div class="sb-ht">${k.long}</div>` : null}
        </div>
        <div class="sb-col away won"><a class="sb-team away" href=${teamHref(f.away)}><${Crest} team=${f.away} short=${f.away_short} size=${52} /><span>${f.away}</span></a>
          <${FavouriteButton} league=${d.scope.league} team=${f.away} compact /></div>
      </div>
    </section>
    <${Preview} f=${f} scope=${d.scope} />
    <${Notice} icon="info">
      <div class="stack" style=${{ "--gap": "4px" }}>
        ${d.events_on && d.phase !== "upcoming" ? html`<span><b>Not read yet.</b> The match is read from WhoScored's match centre at the moments below, not minute by minute. Once it has been read, this page becomes the full match page: momentum, shots, passing, defending and line-ups.</span>` : null}
        ${nextLine(d) ? html`<span>${nextLine(d)}</span>` : null}
        ${followLine(d) ? html`<span class="small secondary">${followLine(d)}</span>` : null}
      </div>
    </${Notice}>
  `;
}
