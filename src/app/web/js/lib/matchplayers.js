// The pure part of a match's Deep analytics table: which players pass the filters, and who is best and worst at each metric among them.
import { blank } from "./metricfmt.js";

export const MINUTE_CHOICES = [
  { value: "0", label: "Everyone" },
  { value: "15", label: "15+ min" },
  { value: "30", label: "30+ min" },
  { value: "45", label: "45+ min" },
  { value: "60", label: "60+ min" },
  { value: "90", label: "Full match" },
];

/** `side` is "both", "h" or "a"; `role` is "all" or a role group; `minutes` is the least a player must have played; `started` keeps starters only. */
export function filterPlayers(rows, { side = "both", role = "all", minutes = 0, started = false, search = "" } = {}) {
  const needle = search.trim().toLowerCase();
  return rows.filter((r) => (side === "both" || r.side === side) && (role === "all" || r.group === role) && r.minutes >= minutes && (!started || r.started)
    && (!needle || r.name.toLowerCase().includes(needle)));
}

/**
 * Who leads and who trails on each metric among `rows`: `{ key: { best: id, worst: id } }`. Nothing is marked for a metric that describes style rather
 * than quality (`hib` null), when fewer than `minRows` players have a value, or when they all share one, since then nobody stands out.
 * A tie is marked only when at most `maxTie` players share it: a dozen players on zero goals are not "the weakest", they are the norm.
 */
export function extremes(rows, keys, ctx, minRows = 4, maxTie = 3) {
  const out = {};
  for (const k of keys) {
    const def = ctx.metrics[k], i = ctx.idx[k];
    if (!def || i === undefined || def.hib === null || def.hib === undefined) continue;
    const have = rows.filter((r) => !blank(r.v[i]));
    if (have.length < minRows) continue;
    const vals = have.map((r) => r.v[i]);
    const hi = Math.max(...vals), lo = Math.min(...vals);
    if (hi === lo) continue;
    const [best, worst] = def.hib ? [hi, lo] : [lo, hi];
    const pick = (x) => { const ids = have.filter((r) => r.v[i] === x).map((r) => r.id); return new Set(ids.length <= maxTie ? ids : []); };
    out[k] = { best: pick(best), worst: pick(worst) };
  }
  return out;
}
