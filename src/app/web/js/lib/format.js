// Number, date and text formatting. Negative numbers use a true minus sign (U+2212).

const MINUS = "−";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export const isNum = (v) => typeof v === "number" && Number.isFinite(v);

export function nf(v, digits = 2) {
  if (!isNum(v)) return "–";
  const text = Math.abs(v).toFixed(digits);
  return v < 0 && Number(text) !== 0 ? MINUS + text : text;
}

export function signed(v, digits = 1) {
  if (!isNum(v)) return "–";
  const text = Math.abs(v).toFixed(digits);
  if (Number(text) === 0) return text;
  return (v > 0 ? "+" : MINUS) + text;
}

export function pct(v, digits = 0) {
  return isNum(v) ? `${(v * 100).toFixed(digits)}%` : "–";
}

/** Probability for people: never claims certainty (">99%") or impossibility ("<1%") it cannot back. */
export function probText(p, digits = 0) {
  if (!isNum(p)) return "–";
  if (p >= 0.995) return ">99%";
  if (p < 0.005) return "<1%";
  return `${(p * 100).toFixed(p < 0.1 ? Math.max(1, digits) : digits)}%`;
}

export function int(v) {
  return isNum(v) ? Math.round(v).toLocaleString("en-GB") : "–";
}

export function compact(v) {
  if (!isNum(v)) return "–";
  const a = Math.abs(v);
  if (a >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${(v / 1e3).toFixed(a >= 1e4 ? 0 : 1)}k`;
  return String(Math.round(v));
}

export function ordinal(n) {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

export function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many || one + "s"}`;
}

/** A player's age unless it came from a name match alone (shown with a "?", it may belong to a namesake), so it never decides a filter. */
export const sureAge = (row) => (row.dob_basis === "name" ? null : row.age ?? null);

/** "4231" -> "4-2-3-1" (a formation as people write it). */
export const formation = (f) => (f ? String(f).split("").join("-") : null);

export function seasonLabel(s) {
  const n = Number(s);
  return Number.isFinite(n) ? `${n}/${String(n + 1).slice(-2)}` : String(s);
}

export function dateShort(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return `${d} ${MONTHS[m - 1]}`;
}

export function dateLong(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

export function weekday(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
}

export function timeOf(dt) {
  return dt && dt.length >= 16 ? dt.slice(11, 16) : "";
}

export function relTime(seconds) {
  if (seconds == null) return "never";
  if (seconds < 90) return "just now";
  const m = seconds / 60;
  if (m < 90) return `${Math.round(m)} min ago`;
  const h = m / 60;
  if (h < 36) return `${Math.round(h)} h ago`;
  return `${Math.round(h / 24)} days ago`;
}

export function bytes(n) {
  if (!isNum(n)) return "–";
  if (n < 1024) return `${n} B`;
  if (n < 1e6) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}

export function initials(name) {
  const parts = String(name || "").split(/[\s\-]+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function hueOf(text) {
  let h = 0;
  for (let i = 0; i < String(text).length; i++) h = (h * 31 + String(text).charCodeAt(i)) >>> 0;
  return h % 360;
}

export function cls(...parts) {
  return parts.filter(Boolean).join(" ");
}

export function debounce(fn, ms = 200) {
  let t;
  const wrapped = (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
  wrapped.cancel = () => clearTimeout(t);
  return wrapped;
}

export function fold(text) {
  return String(text || "")
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/ø/gi, "o")
    .replace(/ß/g, "ss")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}
