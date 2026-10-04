// The match-by-match trend, in numbers and in words. Pure functions over the /api/player/:id/trend payload, so they are tested without a browser.
import { fmtMetric } from "./metricfmt.js";
import { isNum, nf, ordinal, plural, signed } from "./format.js";

export const TIERS = ["top", "mid", "bottom"];
export const TIER_LABEL = { top: "Top third", mid: "Middle third", bottom: "Bottom third" };
const TIER_LOWER = { top: "top-third", mid: "middle-third", bottom: "bottom-third" };

const last = (xs) => (xs.length ? xs[xs.length - 1] : null);

/** "v BOU" or "at BOU": home or away, with the opponent's short name. */
export const versus = (m) => `${m.home ? "v" : "at"} ${m.opp_short || m.opp}`;

/** "W 2–0", from his club's side; null when the match has no score. */
export function resultText(m) {
  if (!m.result || m.gf == null || m.ga == null) return null;
  return `${{ w: "W", d: "D", l: "L" }[m.result]} ${m.gf}–${m.ga}`;
}

/** The metrics shown as one-click choices: the ones that define his role, as the profile lists them, limited to what the trend has. */
export function quickPicks(cat, group, have, keys) {
  const listed = [...(cat?.profile?.full?.[group] || []), ...(cat?.profile?.role?.[group] || [])];
  const picks = [...new Set(listed)].filter((k) => have.has(k)).slice(0, 7);
  if (picks.length) return picks;
  const own = (cat?.order || []).filter((k) => have.has(k) && cat.metrics[k]?.group === (group === "GK" ? "goalkeeping" : "shooting"));
  return (own.length ? own : keys).slice(0, 7);
}

/** How strong an opponent is, from 0 (weakest) to 1 (strongest): its place in this season's table by expected points. Null when unknown. */
export function strength(ctx) {
  if (!ctx || !(ctx.n_teams > 1) || !isNum(ctx.rank_xpts)) return null;
  return 1 - (ctx.rank_xpts - 1) / (ctx.n_teams - 1);
}

/** The opponent in a sentence: where it stands, and how its attack and defence do. */
export function opponentLine(ctx) {
  if (!ctx) return "Opponent strength is not known for this season.";
  const tier = TIER_LOWER[ctx.tier];
  return `${ordinal(ctx.rank_xpts)} of ${ctx.n_teams} by expected points (${tier} side). It scores ${nf(ctx.xg_pg, 1)} and concedes ${nf(ctx.xga_pg, 1)} xG a game.`;
}

/** Bars rise from zero for counts and rates, where zero means "none". Shares, ratings and distances have no such floor: they are drawn as dots on a zoomed axis. */
export const isZeroBased = (def) => !!def && (!!def.signed || ["per90", "pergame", "total", "count"].includes(def.unit));

/** The range a bounded metric cannot leave: a share is 0 to 1, a rating 0 to 10, a score or a pitch position 0 to 100. Anything else has no upper bound, and only a signed difference can go below 0. */
export function metricBounds(def) {
  const hi = { share: 1, rating: 10, score: 100, pitch: 100 }[def?.unit];
  return { lo: def?.signed ? -Infinity : 0, hi: hi ?? Infinity };
}

/**
 * The ends of the axis for bars: the tallest and lowest mark, unless a few outliers would squash every other match into a sliver. Then the axis stops a
 * little beyond the tall end of the ordinary matches and the outliers are clipped (and labelled), so the shape of the season stays readable.
 * `floor` is what must stay inside the plot whatever the bars do (the lines and the typical band): { lo, hi }.
 */
export function axisRange(bars, floor = { lo: 0, hi: 0 }) {
  const xs = bars.filter(isNum).sort((a, b) => a - b);
  const out = { lo: Math.min(floor.lo, xs[0] ?? 0), hi: Math.max(floor.hi, xs[xs.length - 1] ?? 0), clipHigh: false, clipLow: false };
  if (xs.length < 8) return out;
  const at = (q) => xs[Math.min(xs.length - 1, Math.max(0, Math.round(q * (xs.length - 1))))];
  const typicalHigh = Math.max(at(0.9), floor.hi, 0), typicalLow = Math.min(at(0.1), floor.lo, 0);
  if (xs[xs.length - 1] > typicalHigh * 1.6 && xs[xs.length - 1] > floor.hi) { out.hi = typicalHigh * 1.35; out.clipHigh = true; }
  if (xs[0] < typicalLow * 1.6 && xs[0] < floor.lo && typicalLow < 0) { out.lo = typicalLow * 1.35; out.clipLow = true; }
  return out;
}

/**
 * How much weight one match's number can bear. `n` is what stands behind it (minutes for a rate, attempts for a ratio), `minutes` what he played.
 * `alpha` fades the mark smoothly with the sample; `thin` is the point under which the tooltip says so.
 */
export function reliability(def, n, minutes) {
  let size, full, floor, unit;
  if (def?.shape === "ratio") { size = n; full = 10; floor = 5; unit = "attempts"; }
  else if (def?.shape === "rate") { size = n ?? minutes; full = 60; floor = 30; unit = "minutes"; }
  else if (def?.unit === "rating") { size = minutes; full = 45; floor = 20; unit = "minutes"; }
  else return { alpha: 1, thin: false, note: null };
  if (!isNum(size)) return { alpha: 1, thin: false, note: null };
  const thin = size < floor;
  const rounded = Math.round(size);
  const note = thin ? `Only ${rounded} ${rounded === 1 ? unit.replace(/s$/, "") : unit} behind this number, so it says little on its own.` : null;
  return { alpha: Math.max(0.3, Math.min(1, size / full)), thin, note };
}

/** How much each match moved the season-to-date line (null where it did not: no appearance, no data, or the first one). */
export function changes(c, m) {
  let prev = null;
  return c.map((v, i) => {
    const moved = isNum(v) && isNum(prev) && isNum(m[i]) ? v - prev : null;
    if (isNum(v)) prev = v;
    return moved;
  });
}

/** A change in words: percentage points for a share, signed digits otherwise, one more digit than the metric shows (a match moves a season figure a little). */
export function deltaText(def, d) {
  if (!isNum(d)) return "–";
  const share = def?.unit === "share";
  const digits = (def?.decimals ?? (share ? 0 : 2)) + 1;
  return share ? `${signed(d * 100, digits)} pts` : signed(d, digits);
}

/** True when a change is too small to show at the precision `deltaText` writes it in, so it should not be coloured as good or bad. */
export function isFlat(def, d) {
  const share = def?.unit === "share";
  const digits = (def?.decimals ?? (share ? 0 : 2)) + 1;
  return Number(Math.abs(share ? d * 100 : d).toFixed(digits)) === 0;
}

/** The smallest difference the metric shows on screen, in the units of its value. */
const quantum = (def) => (def?.unit === "share" ? 10 ** -((def.decimals ?? 0) + 2) : 10 ** -(def?.decimals ?? 2));

/** Two figures count as the same when they differ by less than `points` (a share) or by a fraction `rel` of the larger one (anything else). */
const within = (def, a, b, rel, points) => Math.abs(a - b) <= (def?.unit === "share" ? points : Math.max(rel * Math.max(Math.abs(a), Math.abs(b)), 2 * quantum(def)));

/** True when two figures are close enough that the difference should not be coloured as good or bad (5% of the figure, or a point for a share). */
export const alike = (def, a, b) => within(def, a, b, 0.05, 0.01);

const wording = (def, goodWhenUp) => (def.hib === null || def.hib === undefined ? null : goodWhenUp === (def.hib !== false) ? "good" : "bad");

/**
 * What stands out for one metric, as a few plain sentences: `[{ kind, text, tone }]`, tone "good" or "bad" only where the metric has a direction.
 * Each sentence appears only when there is enough behind it (matches and minutes), and says when the sample is small.
 */
export function readTrend(payload, key, def) {
  const s = payload.series?.[key];
  if (!s || !def) return [];
  const fmt = (v) => fmtMetric(def, v);
  const out = [];
  const window = payload.window || 5;
  const have = payload.matches.map((m, i) => ({ m, i, v: s.m[i], n: s.n ? s.n[i] : null })).filter((x) => x.m.played && isNum(x.v));

  // recent form against the season
  const season = last(s.c), form = last(s.r);
  if (have.length > window + 1 && isNum(season) && isNum(form)) {
    const diff = form - season;
    if (within(def, form, season, 0.08, 0.02)) out.push({ kind: "form", tone: null, text: `His last ${window} appearances (${fmt(form)}) are in line with his season figure (${fmt(season)}).` });
    else out.push({ kind: "form", tone: wording(def, diff > 0), text: `Over his last ${window} appearances he is at ${fmt(form)}, ${diff > 0 ? "above" : "below"} his season figure of ${fmt(season)}.` });
  }

  // against strong and weak sides
  const tier = payload.splits?.tier;
  const top = tier?.top, bottom = tier?.bottom;
  const enough = (p) => p && p.matches >= 2 && p.minutes >= 120 && isNum(p.v?.[key]);
  if (enough(top) && enough(bottom)) {
    const hi = top.v[key], lo = bottom.v[key];
    const gap = lo - hi;
    const big = !within(def, hi, lo, 0.15, 0.04);
    let verdict;
    if (!big) verdict = "It hardly changes with the strength of the opponent.";
    else if (gap > 0) verdict = def.hib === true ? "He produces more of it against weaker sides, so part of his season figure comes from easier opponents." : "It is higher against weaker sides.";
    else verdict = def.hib === true ? "He produces more of it against the strongest sides, which makes his season figure more impressive." : "It is higher against stronger sides.";
    const hint = top.matches < 4 || bottom.matches < 4 ? " Few matches stand behind each figure, so take it as a hint." : "";
    out.push({ kind: "opponents", tone: null, text: `Against the top third of the league (${plural(top.matches, "match", "matches")}) he is at ${fmt(hi)}; against the bottom third (${plural(bottom.matches, "match", "matches")}), at ${fmt(lo)}. ${verdict}${hint}` });
  }

  // home and away
  const venue = payload.splits?.venue;
  const home = venue?.home, away = venue?.away;
  const venueOk = (p) => p && p.matches >= 3 && p.minutes >= 180 && isNum(p.v?.[key]);
  if (venueOk(home) && venueOk(away)) {
    const h = home.v[key], a = away.v[key];
    const marked = !within(def, h, a, 0.25, 0.05);
    out.push({ kind: "venue", tone: null, text: `At home he is at ${fmt(h)} (${plural(home.matches, "match", "matches")}), away at ${fmt(a)} (${plural(away.matches, "match", "matches")}).${marked ? ` That is clearly higher ${h > a ? "at home" : "away"}.` : ""}` });
  }

  // his highest and lowest matches, and who they came against
  const solid = have.filter((x) => !reliability(def, x.n, x.m.minutes).thin);
  if (solid.length >= 6) {
    const sorted = [...solid].sort((a, b) => b.v - a.v);
    const high = sorted[0], low = last(sorted);
    const same = (rows, name) => rows.every((x) => x.m.opp_ctx?.tier === name);
    const notes = [];
    if (same(sorted.slice(0, 3), "bottom")) notes.push("All three of his highest came against bottom-third sides.");
    else if (same(sorted.slice(0, 3), "top")) notes.push("All three of his highest came against top-third sides.");
    if (same(sorted.slice(-3), "top")) notes.push("All three of his lowest came against top-third sides.");
    else if (same(sorted.slice(-3), "bottom")) notes.push("All three of his lowest came against bottom-third sides.");
    out.push({ kind: "extremes", tone: null, text: `His highest was ${fmt(high.v)} ${versus(high.m)}, his lowest ${fmt(low.v)} ${versus(low.m)}. ${notes.join(" ")}`.trim() });
  }

  // the matches that moved the season figure most
  const moved = changes(s.c, s.m).map((d, i) => ({ d, m: payload.matches[i] })).filter((x) => isNum(x.d) && x.d !== 0);
  if (moved.length >= 6) {
    const up = moved.reduce((a, b) => (b.d > a.d ? b : a)), down = moved.reduce((a, b) => (b.d < a.d ? b : a));
    const bits = [];
    if (up.d > 0) bits.push(`The match that lifted his season figure most was ${versus(up.m)} (${deltaText(def, up.d)})`);
    if (down.d < 0) bits.push(`${bits.length ? "the one that pulled it down most was" : "The match that pulled his season figure down most was"} ${versus(down.m)} (${deltaText(def, down.d)})`);
    if (bits.length) out.push({ kind: "movers", tone: null, text: `${bits.join(", and ")}.` });
  }
  return out;
}
