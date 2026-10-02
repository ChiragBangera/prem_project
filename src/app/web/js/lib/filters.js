// The filter engine behind Scout and Teams. Pure functions: state in, rows out, so every rule is testable without a browser.
//
// Principles (they come straight from how people use the page):
//  * Nothing is pre-selected. The default state is "everyone", and every restriction is something the user chose.
//  * Filters are independent and additive: each one narrows the list, none changes another.
//  * A lens is just a bundle of metric rules. Switching one on adds those rules; it never touches roles, columns or the sort.
//  * Unknown is not zero. A row with no value for a metric cannot pass a rule on that metric.
//
// Rows are compact: { id, name, team, teams, group, pos2, tags, age, dob_basis, v: [...], p: [...] } with v (values) and p (percentiles)
// aligned to the dataset's `keys`. `ctx.idx` maps a metric key to its position.
import { blank } from "./metricfmt.js";
import { fold } from "./format.js";

export const ROLE_ORDER = ["ATT", "MID", "DEF", "GK"];
export const OPS = [">=", "<="];

export function emptyFilters() {
  return { q: "", roles: [], positions: [], tags: [], clubs: [], formations: [], minutes: 0, age: null, ageUnknown: false, part: "", rules: [], lenses: [] };
}

export function makeIndex(keys) {
  const idx = Object.create(null);
  keys.forEach((k, i) => { idx[k] = i; });
  return idx;
}

/** The value of a metric on a row, or undefined when the dataset has no such metric. null when it is unknown for this row. */
export function valueOf(row, ctx, key) {
  const i = ctx.idx[key];
  return i === undefined ? undefined : row.v[i];
}

export function pctOf(row, ctx, key) {
  const i = ctx.idx[key];
  return i === undefined ? undefined : row.p[i];
}

/** A player's age, unless it came from a name match alone (it may belong to a namesake, so it never decides a filter). */
export const sureAge = (row) => (row.dob_basis === "name" ? null : row.age ?? null);

// ------------------------------------------------------------------ rules

/** Does a row satisfy `{ metric, op, value, on }`? `on` is "value" (the number itself) or "pct" (percentile among role peers). */
export function testRule(row, rule, ctx) {
  const i = ctx.idx[rule.metric];
  if (i === undefined) return true; // a metric this dataset does not have: the rule cannot apply, so it does not exclude
  const x = rule.on === "pct" ? row.p[i] : row.v[i];
  if (blank(x)) return false;
  return rule.op === ">=" ? x >= rule.value : x <= rule.value;
}

const rulesPass = (row, rules, ctx) => rules.every((r) => testRule(row, r, ctx));

/** The lens objects a state selects, in the order selected, ignoring keys the catalog does not know. */
export function activeLenses(state, ctx) {
  return state.lenses.map((k) => ctx.lenses?.[k]).filter(Boolean);
}

// ------------------------------------------------------------------ the predicate

/** Compile a state to one function (row) => boolean. */
export function predicateFor(state, ctx) {
  const needle = fold(state.q);
  const roles = state.roles.length ? new Set(state.roles) : null;
  const positions = state.positions.length ? new Set(state.positions) : null;
  const tags = state.tags.length ? new Set(state.tags) : null;
  const clubs = state.clubs.length ? new Set(state.clubs) : null;
  const formations = state.formations?.length ? new Set(state.formations) : null;
  const lenses = activeLenses(state, ctx);
  const minutesIdx = ctx.idx.minutes;
  const shareIdx = ctx.idx.minutes_share;
  return (row) => {
    if (needle && !fold(`${row.name ?? row.team} ${row.team ?? ""} ${row.teams ? row.teams.join(" ") : ""}`).includes(needle)) return false;
    if (roles && !roles.has(row.group)) return false;
    if (positions && !positions.has(row.pos2)) return false; // a player whose detailed position is unknown cannot match a position
    if (tags && !(row.tags || []).some((t) => tags.has(t.key))) return false;
    if (clubs && !(row.teams ? row.teams.some((t) => clubs.has(t)) : clubs.has(row.team))) return false;
    if (formations && !formations.has(row.formation)) return false;
    if (state.minutes > 0 && minutesIdx !== undefined) {
      const m = row.v[minutesIdx];
      if (blank(m) || m < state.minutes) return false;
    }
    if (state.age) {
      const age = sureAge(row);
      if (age == null) { if (!state.ageUnknown) return false; } else if (age < state.age[0] || age > state.age[1]) return false;
    }
    if (state.part && shareIdx !== undefined) {
      const share = row.v[shareIdx];
      if (blank(share)) return false;
      if (state.part === "starter" && share < 0.6) return false;
      if (state.part === "rotation" && share >= 0.6) return false;
    }
    if (state.rules.length && !rulesPass(row, state.rules, ctx)) return false;
    for (const lens of lenses) {
      if (lens.roles?.length && !lens.roles.includes(row.group)) return false;
      if (!rulesPass(row, lens.rules, ctx)) return false;
    }
    return true;
  };
}

export function applyFilters(rows, state, ctx) {
  const pass = predicateFor(state, ctx);
  return rows.filter(pass);
}

/** How many rows a lens would leave if it were switched on now (everything else as it is), for the number on the lens chip. */
export function lensCount(rows, state, ctx, lensKey) {
  const on = state.lenses.includes(lensKey) ? state.lenses : [...state.lenses, lensKey];
  return applyFilters(rows, { ...state, lenses: on }, ctx).length;
}

/** Does anything restrict the list? (Drives "Clear all" and the active-filter strip.) */
export function isFiltered(state) {
  return Boolean(state.q || state.roles.length || state.positions.length || state.tags.length || state.clubs.length || state.formations?.length
    || state.minutes > 0 || state.age || state.part || state.rules.length || state.lenses.length);
}

// ------------------------------------------------------------------ sorting and limiting

/** The thing a column sorts by. "pct:xg" sorts by percentile. */
export function sortValue(row, key, ctx) {
  if (key.startsWith("pct:")) return pctOf(row, ctx, key.slice(4));
  switch (key) {
    case "name": return row.name ?? row.team;
    case "team": return row.team;
    case "league": return row.league;
    case "role": return ROLE_ORDER.indexOf(row.group);
    case "pos": return row.pos2 ?? null;
    case "rank": return row.rank ?? null;
    case "tags": return (row.tags || []).length;
    default: return valueOf(row, ctx, key);
  }
}

const textKeys = new Set(["name", "team", "league", "pos"]);

/** A new array sorted by `key`. Unknown values always sit last, whichever way the sort runs. Ties keep their order. */
export function sortRows(rows, sort, ctx) {
  if (!sort?.key) return rows;
  const dir = sort.dir === "asc" ? 1 : -1;
  const decorated = rows.map((r, i) => [sortValue(r, sort.key, ctx), i, r]);
  decorated.sort((a, b) => {
    const x = a[0], y = b[0];
    const bx = blank(x), by = blank(y);
    if (bx || by) return bx && by ? a[1] - b[1] : bx ? 1 : -1;
    const c = textKeys.has(sort.key) ? String(x).localeCompare(String(y), "en", { sensitivity: "base", numeric: true }) : x - y;
    return c ? c * dir : a[1] - b[1];
  });
  return decorated.map((d) => d[2]);
}

/** The first n rows (n of 0 or less means all). */
export function takeTop(rows, n) {
  return n > 0 ? rows.slice(0, n) : rows;
}

// ------------------------------------------------------------------ describing filters in words

/** "npxG/90 ≥ 0.40" or "npxG/90: top 20% of role peers". `long` uses the full metric name and, for teams, says "teams" for "role peers". */
export function describeRule(rule, ctx, fmt, long = false) {
  const def = ctx.metrics?.[rule.metric];
  const name = (long ? def?.label : def?.short) || rule.metric;
  if (rule.on === "pct") {
    const words = pctWords(def, rule);
    return `${name}: ${ctx.level === "team" ? words.replace("role peers", "teams in the league") : words}`;
  }
  return `${name} ${rule.op === ">=" ? "≥" : "≤"} ${fmt ? fmt(def, rule.value) : rule.value}`;
}

function pctWords(def, rule) {
  const hib = def ? def.hib : true;
  if (rule.op === ">=") {
    const share = 100 - rule.value;
    return hib === false ? `lowest ${share}% of role peers` : hib === null ? `highest ${share}% of role peers` : `top ${share}% of role peers`;
  }
  return hib === false ? `highest ${rule.value}% of role peers` : hib === null ? `lowest ${rule.value}% of role peers` : `bottom ${rule.value}% of role peers`;
}

/**
 * The chips shown under the filter bar: one per restriction, each with the state that removes just that restriction.
 * `labels` supplies display text: { role(key), position(key), tag(key), lens(key), fmt(def, value) }.
 */
export function activeChips(state, ctx, labels) {
  const chips = [];
  const without = (patch) => ({ ...state, ...patch });
  if (state.q) chips.push({ id: "q", kind: "search", text: `“${state.q}”`, title: "Name or club contains", next: without({ q: "" }) });
  for (const r of state.roles) chips.push({ id: `role:${r}`, kind: "role", text: labels.role(r), title: "Role", next: without({ roles: state.roles.filter((x) => x !== r) }) });
  for (const p of state.positions) chips.push({ id: `pos:${p}`, kind: "position", text: labels.position(p), title: "Detailed position", next: without({ positions: state.positions.filter((x) => x !== p) }) });
  for (const t of state.tags) chips.push({ id: `tag:${t}`, kind: "tag", text: labels.tag(t), title: "Profile", next: without({ tags: state.tags.filter((x) => x !== t) }) });
  for (const c of state.clubs) chips.push({ id: `club:${c}`, kind: "club", text: c, title: "Club", next: without({ clubs: state.clubs.filter((x) => x !== c) }) });
  for (const f of state.formations || []) chips.push({ id: `form:${f}`, kind: "formation", text: labels.formation ? labels.formation(f) : f, title: "Formation", next: without({ formations: state.formations.filter((x) => x !== f) }) });
  if (state.minutes > 0) chips.push({ id: "min", kind: "minutes", text: `${state.minutes}+ minutes`, title: "Minutes played", next: without({ minutes: 0 }) });
  if (state.age) chips.push({ id: "age", kind: "age", text: `Age ${state.age[0]}–${state.age[1]}${state.ageUnknown ? " (+ unknown)" : ""}`, title: "Age", next: without({ age: null, ageUnknown: false }) });
  if (state.part) chips.push({ id: "part", kind: "part", text: state.part === "starter" ? "Regular starters" : "Rotation and bench", title: "Role in the team", next: without({ part: "" }) });
  state.rules.forEach((r, i) => chips.push({ id: `rule:${i}`, kind: "rule", index: i, text: describeRule(r, ctx, labels.fmt), title: "Metric filter (click to edit)", rule: r, next: without({ rules: state.rules.filter((_, j) => j !== i) }) }));
  for (const key of state.lenses) {
    const lens = ctx.lenses?.[key];
    if (lens) chips.push({ id: `lens:${key}`, kind: "lens", text: `Lens: ${labels.lens(key)}`, title: lens.blurb, next: without({ lenses: state.lenses.filter((x) => x !== key) }) });
  }
  return chips;
}

// ------------------------------------------------------------------ the URL

const csv = (v) => (v ? String(v).split(",").map((s) => s.trim()).filter(Boolean) : []);
const RULE = /^([a-z0-9_]+)(>=|<=)(p?)(-?\d+(?:\.\d+)?)$/;

export function encodeRules(rules) {
  return rules.map((r) => `${r.metric}${r.op}${r.on === "pct" ? "p" : ""}${r.value}`).join(";");
}

/** Parse "npxg90>=p80;xa90>=0.2". Pieces that do not parse, or name an unknown metric, are dropped. */
export function decodeRules(text, idx) {
  const out = [];
  for (const piece of String(text || "").split(";")) {
    const m = RULE.exec(piece.trim());
    if (!m || (idx && idx[m[1]] === undefined)) continue;
    out.push({ metric: m[1], op: m[2], on: m[3] ? "pct" : "value", value: Number(m[4]) });
  }
  return out;
}

/** Filter state from a URL query. Unknown lens and tag keys are dropped. */
export function stateFromQuery(query, ctx) {
  const s = emptyFilters();
  s.q = query.q || "";
  s.roles = csv(query.r).filter((r) => ROLE_ORDER.includes(r));
  s.positions = csv(query.pos);
  s.tags = csv(query.tag).filter((t) => !ctx.tags || ctx.tags[t]);
  s.clubs = (query.club || "").split("|").filter(Boolean);
  s.formations = (query.form || "").split("|").filter(Boolean);
  s.minutes = Math.max(0, Number(query.min) || 0);
  const [lo, hi] = (query.age || "").split("-").map(Number);
  s.age = query.age && Number.isFinite(lo) && Number.isFinite(hi) ? [Math.min(lo, hi), Math.max(lo, hi)] : null;
  s.ageUnknown = query.unk === "1";
  s.part = query.part === "starter" || query.part === "rotation" ? query.part : "";
  s.rules = decodeRules(query.f, ctx.idx);
  s.lenses = csv(query.lens).filter((k) => !ctx.lenses || ctx.lenses[k]);
  return s;
}

/** The query patch that stores a state: every filter key, null where the state is the default (so the URL stays short). */
export function stateToQuery(state) {
  return {
    q: state.q || null,
    r: state.roles.join(",") || null,
    pos: state.positions.join(",") || null,
    tag: state.tags.join(",") || null,
    club: state.clubs.join("|") || null,
    form: (state.formations || []).join("|") || null,
    min: state.minutes > 0 ? state.minutes : null,
    age: state.age ? `${state.age[0]}-${state.age[1]}` : null,
    unk: state.age && state.ageUnknown ? "1" : null,
    part: state.part || null,
    f: encodeRules(state.rules) || null,
    lens: state.lenses.join(",") || null,
  };
}

// ------------------------------------------------------------------ view state (sort, columns, map axes), stored beside the filters

export const TOP_CHOICES = [10, 20, 50, 100];

export function viewFromQuery(query, defaults = {}) {
  const top = Number(query.top);
  return {
    sort: query.sort || defaults.sort || null,
    dir: query.dir === "asc" || query.dir === "desc" ? query.dir : defaults.dir || "desc",
    top: Number.isFinite(top) && top > 0 ? top : 0,
    view: query.view === "map" ? "map" : "table",
    cols: query.cols || defaults.cols || "",
    mx: query.mx || defaults.mx || null,
    my: query.my || defaults.my || null,
    mc: query.mc || defaults.mc || "role",
    ms: query.ms || defaults.ms || "minutes",
    cmp: csv(query.cmp).map(Number).filter(Number.isFinite),
  };
}

export function viewToQuery(view, defaults = {}) {
  return {
    sort: view.sort && view.sort !== defaults.sort ? view.sort : null,
    dir: view.dir && view.dir !== (defaults.dir || "desc") ? view.dir : null,
    top: view.top > 0 ? view.top : null,
    view: view.view === "map" ? "map" : null,
    cols: view.cols && view.cols !== defaults.cols ? view.cols : null,
    mx: view.mx && view.mx !== defaults.mx ? view.mx : null,
    my: view.my && view.my !== defaults.my ? view.my : null,
    mc: view.mc && view.mc !== (defaults.mc || "role") ? view.mc : null,
    ms: view.ms && view.ms !== (defaults.ms || "minutes") ? view.ms : null,
    cmp: view.cmp?.length ? view.cmp.join(",") : null,
  };
}

/** Columns from the `cols` query value: a preset key ("attacking") or "x:xg,kp90" for a custom list. */
export function parseCols(value) {
  if (!value) return { preset: null, custom: null };
  if (value.startsWith("x:")) return { preset: null, custom: csv(value.slice(2)) };
  return { preset: value, custom: null };
}

export const customCols = (keys) => `x:${keys.join(",")}`;

// ------------------------------------------------------------------ distributions (for the little histogram and the filter sliders)

export function finiteValues(rows, key, ctx) {
  const out = [];
  for (const r of rows) {
    const v = sortValue(r, key, ctx);
    if (!blank(v) && typeof v === "number") out.push(v);
  }
  return out;
}

export function quantile(sorted, q) {
  if (!sorted.length) return NaN;
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos), hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

/** Equal-width bins between the 1st and 99th percentile, so one outlier does not flatten the picture. Values beyond are clamped into the end bins. */
export function histogram(values, bins = 24) {
  if (values.length < 2) return null;
  const sorted = [...values].sort((a, b) => a - b);
  let lo = quantile(sorted, 0.01), hi = quantile(sorted, 0.99);
  if (!(hi > lo)) { lo = sorted[0]; hi = sorted[sorted.length - 1]; }
  if (!(hi > lo)) return null;
  const width = (hi - lo) / bins;
  const counts = new Array(bins).fill(0);
  for (const v of values) counts[Math.max(0, Math.min(bins - 1, Math.floor((v - lo) / width)))] += 1;
  return { lo, hi, width, counts, n: values.length, median: quantile(sorted, 0.5), sorted };
}
