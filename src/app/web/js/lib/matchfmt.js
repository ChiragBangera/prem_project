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
