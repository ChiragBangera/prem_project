// How a metric value is written. One place, so a table cell, a tooltip, a filter chip and the dictionary all agree.
import { nf, signed } from "./format.js";

/** Unknown: missing, NaN or infinite. Never confused with zero. */
export const blank = (v) => v === null || v === undefined || (typeof v === "number" && !Number.isFinite(v));

/**
 * A value as people read it. A share is a percentage, a difference carries its sign, a count has no decimals.
 * `def` is a catalog metric ({ unit, decimals, signed }); without one the number is shown with two decimals.
 */
export function fmtMetric(def, v) {
  if (blank(v)) return "–";
  if (!def) return nf(v, 2);
  const d = def.decimals ?? 2;
  switch (def.unit) {
    case "share": return `${(v * 100).toFixed(d)}%`;
    case "score": return String(Math.round(v));
    case "metres": return `${nf(v, d)} m`;
    default: break;
  }
  if (def.signed) return signed(v, d);
  return nf(v, d);
}

/** A percentile as a whole number: "87". */
export const fmtPct = (p) => (blank(p) ? "–" : String(Math.round(p)));

/** What the number is "per": used in column and axis labels. */
export function unitWord(def) {
  switch (def?.unit) {
    case "per90": return "per 90 minutes";
    case "pergame": return "per game";
    case "share": return "share";
    case "metres": return "metres";
    case "age": return "years";
    case "pitch": return "position on the pitch (0 own goal, 100 theirs)";
    case "rating": return "rating";
    case "score": return "score out of 100";
    default: return "";
  }
}

/** True when higher is better, false when lower is better, null for style metrics where neither is "better". */
export const direction = (def) => (def ? def.hib : null);
