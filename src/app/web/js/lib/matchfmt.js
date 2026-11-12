// Pure helpers for showing a match: names, scorer lines, kickoff in the viewer's time zone, and the one-line verdict on a result that defied the chances.
import { dateShort, pct, weekday } from "./format.js";
import { poissonOutcome } from "./stats.js";

export const FLAG_LABEL = {
  against_run_of_play: "Against the run of play",
  favourite_held: "Favourite held",
};

/** "Alexis Mac Allister" -> "Mac Allister", "Bruno Fernandes" -> "Fernandes": a surname people recognise, without guessing at particles. */
export function shortName(name) {
  const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length <= 2) return parts[parts.length - 1] || "";
  return parts.slice(-2).join(" ");
}

const stoppage = (minute) => (minute > 90 ? `90+${minute - 90}` : String(minute));

/** One entry per scorer, with all his minutes: [{ name, minutes: ["12′", "45′ (pen)"] }], in order of first goal. */
export function scorerLines(list = []) {
  const out = [];
  const byKey = new Map();
  for (const s of [...list].sort((a, b) => a.minute - b.minute)) {
    const key = s.id ?? s.player;
    let entry = byKey.get(key);
    if (!entry) { entry = { name: shortName(s.player), full: s.player, id: s.id, minutes: [] }; byKey.set(key, entry); out.push(entry); }
    entry.minutes.push(`${stoppage(s.minute)}′${s.kind === "pen" ? " (pen)" : s.kind === "og" ? " (og)" : ""}`);
  }
  return out;
}

/** "10 Oct · 20:00" in the viewer's own time zone (Understat's times are UTC). */
export function kickoff(m) {
  if (m.utc) {
    const d = new Date(m.utc);
    if (!Number.isNaN(d.getTime())) {
      return {
        day: d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" }),
        time: d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }),
        key: d.toLocaleDateString("en-CA"),
        long: d.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" }),
      };
    }
  }
  return { day: `${weekday(m.date)} ${dateShort(m.date)}`, time: m.dt ? m.dt.slice(11, 16) : "", key: m.date, long: `${weekday(m.date)} ${dateShort(m.date)}` };
}

// The match clock, as app/data/matchclock.py has it: minutes from kickoff to the half-time whistle, the end of the break, and full time.
export const HALF_TIME = 47, HALF_TIME_END = 62, FULL_TIME = 112;

/** Where an unplayed fixture is by the clock: "upcoming", "first_half", "half_time", "second_half" or "full_time" (finished, waiting for
 * Understat to list it); "played" once it has. `now` is in milliseconds. */
export function phaseOf(m, now = Date.now()) {
  if (m.played) return "played";
  const k = m.utc ? new Date(m.utc).getTime() : NaN;
  if (Number.isNaN(k) || now < k) return "upcoming";
  const min = (now - k) / 60000;
  return min < HALF_TIME ? "first_half" : min < HALF_TIME_END ? "half_time" : min < FULL_TIME ? "second_half" : "full_time";
}

export const PHASE_LABEL = { upcoming: "Upcoming", first_half: "Live", half_time: "Half time", second_half: "Live", full_time: "Full time", played: "FT" };

/** One sentence on a result that went against the chances. */
export function verdict(m) {
  if (!m.flag || m.hxg == null) return null;
  const o = poissonOutcome(m.hxg, m.axg);
  if (m.flag === "against_run_of_play") {
    const home = m.hg > m.ag;
    return `${home ? m.home : m.away} won although the chances gave them just ${pct(home ? o.home : o.away)}.`;
  }
  if (m.flag === "favourite_held") {
    const homeFav = o.home > o.away;
    return `${homeFav ? m.home : m.away} were ${pct(Math.max(o.home, o.away))} favourites on chances and only drew.`;
  }
  return null;
}

/** One team's season so far, from its own side of each result. */
/** A fixture with its final score in `hg`/`ag` whichever source has it. Understat publishes a match some hours after it ends (and can be
 *  down for weeks); a match stored from WhoScored before that carries its score in `result`, and has no xG yet. */
export const withResult = (m) => (!m.played && m.result ? { ...m, hg: m.result.hg, ag: m.result.ag } : m);
export const finished = (m) => !!(m.played || m.result);

export function teamRecord(matches, team) {
  const out = { played: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, xg: 0, xga: 0, xgKnown: 0, flagged: 0 };
  for (const raw of matches) {
    const m = withResult(raw);
    if (!finished(m) || (m.home !== team && m.away !== team)) continue;
    const home = m.home === team;
    const gf = home ? m.hg : m.ag, ga = home ? m.ag : m.hg;
    out.played += 1; out.gf += gf; out.ga += ga;
    if (gf > ga) out.w += 1; else if (gf === ga) out.d += 1; else out.l += 1;
    const xf = home ? m.hxg : m.axg, xa = home ? m.axg : m.hxg;
    if (xf != null && xa != null) { out.xg += xf; out.xga += xa; out.xgKnown += 1; }
    if (m.flag) out.flagged += 1;
  }
  return out;
}
