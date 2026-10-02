import test from "node:test";
import assert from "node:assert/strict";
import {
  emptyFilters, makeIndex, applyFilters, sortRows, takeTop, lensCount, isFiltered, activeChips, describeRule,
  encodeRules, decodeRules, stateFromQuery, stateToQuery, viewFromQuery, viewToQuery, parseCols, customCols, histogram, quantile, sureAge,
} from "../../src/app/web/js/lib/filters.js";
import { fmtMetric } from "../../src/app/web/js/lib/metricfmt.js";

const keys = ["minutes", "minutes_share", "npxg90", "xa90", "tackles90", "fouls90", "age"];
const idx = makeIndex(keys);
const ctx = {
  idx,
  metrics: {
    npxg90: { key: "npxg90", short: "npxG/90", unit: "per90", decimals: 2, hib: true },
    tackles90: { key: "tackles90", short: "Tackles/90", unit: "per90", decimals: 1, hib: true },
    fouls90: { key: "fouls90", short: "Fouls/90", unit: "per90", decimals: 1, hib: false },
  },
  tags: { poacher: {}, builder: {} },
  lenses: {
    threats: { key: "threats", blurb: "Top 20% for npxG", roles: [], rules: [{ metric: "npxg90", op: ">=", value: 80, on: "pct" }, { metric: "minutes", op: ">=", value: 450, on: "value" }] },
    wingers: { key: "wingers", blurb: "Attackers only", roles: ["ATT"], rules: [{ metric: "xa90", op: ">=", value: 0.2, on: "value" }] },
  },
};

//            minutes share npxg xa  tkl  fouls age
const row = (id, name, group, v, p, extra = {}) => ({ id, name, team: "Club " + id, teams: ["Club " + id], group, pos2: null, tags: [], age: null, dob_basis: "roster", v, p, ...extra });
const rows = [
  row(1, "Ann Striker", "ATT", [1800, 0.8, 0.6, 0.1, null, 1.0, 27], [60, 70, 95, 30, null, 60, null], { pos2: "ST", tags: [{ key: "poacher", label: "Poacher" }], age: 27 }),
  row(2, "Bo Cameo", "ATT", [100, 0.05, 1.2, 0.3, null, 0.5, 19], [30, 5, 99, 80, null, 90, null], { pos2: "W", age: 19 }),
  row(3, "Cy Mid", "MID", [2000, 0.9, null, 0.25, 3.1, 2.0, 31], [70, 90, null, 85, 92, 20, null], { pos2: "DM", age: 31 }),
  row(4, "Di Keeper", "GK", [3000, 1.0, null, null, null, 0.0, 34], [90, 99, null, null, null, 99, null], { pos2: "GK", age: 34 }),
  row(5, "Ed Unknown", "DEF", [900, 0.4, 0.05, 0.02, 1.5, 1.4, null], [50, 40, 20, 10, 60, 50, null], { pos2: null, age: null, tags: [{ key: "builder", label: "Ball-playing defender" }] }),
  row(6, "Flo Guess", "DEF", [1200, 0.6, 0.08, 0.05, 2.0, 1.1, 22], [55, 50, 25, 15, 75, 55, null], { pos2: "CB", age: 22, dob_basis: "name" }),
];
const ids = (list) => list.map((r) => r.id);

test("by default nothing is selected and nobody is hidden", () => {
  const s = emptyFilters();
  assert.equal(isFiltered(s), false);
  assert.deepEqual(ids(applyFilters(rows, s, ctx)), [1, 2, 3, 4, 5, 6]);
});

test("role, position, profile and club filters are independent and additive", () => {
  const f = (patch) => ids(applyFilters(rows, { ...emptyFilters(), ...patch }, ctx));
  assert.deepEqual(f({ roles: ["ATT"] }), [1, 2]);
  assert.deepEqual(f({ roles: ["ATT", "GK"] }), [1, 2, 4]);
  assert.deepEqual(f({ positions: ["ST", "CB"] }), [1, 6]);                 // a player with no known position cannot match one
  assert.deepEqual(f({ tags: ["poacher", "builder"] }), [1, 5]);            // any of the chosen profiles
  assert.deepEqual(f({ roles: ["ATT"], tags: ["poacher"] }), [1]);           // different filters narrow together
  assert.deepEqual(f({ clubs: ["Club 3"] }), [3]);
  assert.deepEqual(f({ q: "keeper" }), [4]);
  assert.deepEqual(f({ q: "club 2" }), [2]);
});

test("minutes, role in the team and age behave as written, and unknown ages never sneak in", () => {
  const f = (patch) => ids(applyFilters(rows, { ...emptyFilters(), ...patch }, ctx));
  assert.deepEqual(f({ minutes: 1000 }), [1, 3, 4, 6]);
  assert.deepEqual(f({ part: "starter" }), [1, 3, 4, 6]);
  assert.deepEqual(f({ part: "rotation" }), [2, 5]);
  assert.deepEqual(f({ age: [18, 30] }), [1, 2]);                             // 5 has no age; 6 has a name-only age, which is not sure enough
  assert.deepEqual(f({ age: [18, 30], ageUnknown: true }), [1, 2, 5, 6]);
  assert.equal(sureAge(rows[5]), null);
});

test("a metric rule never passes a row whose value is unknown, and an unknown metric does not exclude anyone", () => {
  const f = (rules) => ids(applyFilters(rows, { ...emptyFilters(), rules }, ctx));
  assert.deepEqual(f([{ metric: "npxg90", op: ">=", value: 0.5, on: "value" }]), [1, 2]);          // row 3 and 4 have no npxG: unknown is not zero
  assert.deepEqual(f([{ metric: "npxg90", op: "<=", value: 0.5, on: "value" }]), [5, 6]);
  assert.deepEqual(f([{ metric: "npxg90", op: ">=", value: 90, on: "pct" }]), [1, 2]);
  assert.deepEqual(f([{ metric: "fouls90", op: ">=", value: 80, on: "pct" }]), [2, 4]);             // percentiles already read higher-is-better: cleanest 20%
  assert.deepEqual(f([{ metric: "nothing_like_this", op: ">=", value: 1, on: "value" }]), [1, 2, 3, 4, 5, 6]);
  assert.deepEqual(f([{ metric: "xa90", op: ">=", value: 0.2, on: "value" }, { metric: "tackles90", op: ">=", value: 3, on: "value" }]), [3]);
});

test("a lens only adds its own rules and never changes another filter", () => {
  const base = { ...emptyFilters(), roles: ["ATT", "MID"] };
  const withLens = { ...base, lenses: ["threats"] };
  assert.deepEqual(ids(applyFilters(rows, base, ctx)), [1, 2, 3]);
  assert.deepEqual(ids(applyFilters(rows, withLens, ctx)), [1]);              // 2 is in the top 20% but has under 450 minutes
  assert.deepEqual(withLens.roles, ["ATT", "MID"]);                           // the role filter is untouched
  assert.deepEqual(ids(applyFilters(rows, { ...emptyFilters(), lenses: ["wingers"] }, ctx)), [2]);   // the lens carries its own role limit: attackers only
  assert.deepEqual(ids(applyFilters(rows, { ...emptyFilters(), lenses: ["threats", "wingers"] }, ctx)), []);
  assert.equal(lensCount(rows, base, ctx, "threats"), 1);
  assert.equal(lensCount(rows, withLens, ctx, "threats"), 1);                 // already on: the same count, not a double application
});

test("sorting puts unknown values last in both directions and keeps ties in order", () => {
  const sortIds = (key, dir) => ids(sortRows(rows, { key, dir }, ctx));
  assert.deepEqual(sortIds("npxg90", "desc"), [2, 1, 6, 5, 3, 4]);
  assert.deepEqual(sortIds("npxg90", "asc"), [5, 6, 1, 2, 3, 4]);
  assert.deepEqual(sortIds("name", "asc"), [1, 2, 3, 4, 5, 6]);
  assert.deepEqual(sortIds("name", "desc"), [6, 5, 4, 3, 2, 1]);
  assert.deepEqual(sortIds("pct:fouls90", "desc"), [4, 2, 1, 6, 5, 3]);
  assert.deepEqual(sortIds("role", "asc"), [1, 2, 3, 5, 6, 4]);              // attackers, midfielders, defenders, goalkeepers
  assert.deepEqual(ids(sortRows(rows, { key: null }, ctx)), [1, 2, 3, 4, 5, 6]);
  assert.deepEqual(ids(takeTop(sortRows(rows, { key: "minutes", dir: "desc" }, ctx), 2)), [4, 3]);
  assert.equal(takeTop(rows, 0).length, 6);
});

test("the active-filter chips remove exactly one restriction each", () => {
  const state = { ...emptyFilters(), roles: ["ATT", "DEF"], tags: ["poacher"], minutes: 450, age: [20, 30], rules: [{ metric: "npxg90", op: ">=", value: 0.3, on: "value" }, { metric: "fouls90", op: ">=", value: 80, on: "pct" }], lenses: ["threats"] };
  const labels = { role: (r) => ({ ATT: "Attackers", DEF: "Defenders" })[r], position: (p) => p, tag: (t) => ({ poacher: "Poacher" })[t], lens: (k) => ({ threats: "Goal threats" })[k], fmt: fmtMetric };
  const chips = activeChips(state, ctx, labels);
  assert.deepEqual(chips.map((c) => c.text), ["Attackers", "Defenders", "Poacher", "450+ minutes", "Age 20–30", "npxG/90 ≥ 0.30", "Fouls/90: lowest 20% of role peers", "Lens: Goal threats"]);
  const dropRole = chips[0].next;
  assert.deepEqual(dropRole.roles, ["DEF"]);
  assert.equal(dropRole.minutes, 450);
  assert.deepEqual(chips[5].next.rules.map((r) => r.metric), ["fouls90"]);
  assert.deepEqual(chips[7].next.lenses, []);
  assert.deepEqual(activeChips(emptyFilters(), ctx, labels), []);
  assert.equal(describeRule({ metric: "tackles90", op: "<=", value: 20, on: "pct" }, ctx, fmtMetric), "Tackles/90: bottom 20% of role peers");
});

test("rules and whole states survive a round trip through the URL", () => {
  const rules = [{ metric: "npxg90", op: ">=", value: 80, on: "pct" }, { metric: "tackles90", op: "<=", value: 2.5, on: "value" }];
  assert.equal(encodeRules(rules), "npxg90>=p80;tackles90<=2.5");
  assert.deepEqual(decodeRules("npxg90>=p80;tackles90<=2.5", idx), rules);
  assert.deepEqual(decodeRules("npxg90>=p80;bogus;nope>=3;tackles90<=x", idx), [rules[0]]);   // junk and unknown metrics are dropped
  const state = { ...emptyFilters(), q: "ha", roles: ["ATT", "MID"], positions: ["CB"], tags: ["poacher"], clubs: ["Club 1", "Club 2"], minutes: 450, age: [18, 23], ageUnknown: true, part: "starter", rules, lenses: ["threats"] };
  const query = stateToQuery(state);
  assert.deepEqual(stateFromQuery(query, ctx), state);
  assert.deepEqual(Object.values(stateToQuery(emptyFilters())).filter((v) => v !== null), []);    // the default state leaves the URL empty
  assert.deepEqual(stateFromQuery({ r: "ATT,XX", tag: "poacher,nonsense", lens: "threats,gone", min: "-5", age: "x-y", part: "weird" }, ctx),
    { ...emptyFilters(), roles: ["ATT"], tags: ["poacher"], lenses: ["threats"] });
});

test("sorting, columns and the map axes are kept in the URL too, and only when they differ from the defaults", () => {
  const defaults = { sort: "score", dir: "desc", cols: "overview", mx: "xa90", my: "npxg90" };
  assert.deepEqual(viewFromQuery({}, defaults), { sort: "score", dir: "desc", top: 0, view: "table", cols: "overview", mx: "xa90", my: "npxg90", mc: "role", ms: "minutes", cmp: [] });
  const view = viewFromQuery({ sort: "npxg90", dir: "asc", top: "20", view: "map", cols: "x:xg,kp90", mx: "xg", cmp: "3,9,x" }, defaults);
  assert.deepEqual(view, { sort: "npxg90", dir: "asc", top: 20, view: "map", cols: "x:xg,kp90", mx: "xg", my: "npxg90", mc: "role", ms: "minutes", cmp: [3, 9] });
  assert.deepEqual(viewToQuery(viewFromQuery({}, defaults), defaults), { sort: null, dir: null, top: null, view: null, cols: null, mx: null, my: null, mc: null, ms: null, cmp: null });
  assert.equal(viewToQuery(view, defaults).cols, "x:xg,kp90");
  assert.deepEqual(parseCols("x:xg,kp90"), { preset: null, custom: ["xg", "kp90"] });
  assert.deepEqual(parseCols("attacking"), { preset: "attacking", custom: null });
  assert.equal(customCols(["a", "b"]), "x:a,b");
});

test("the histogram ignores one wild outlier and counts every value", () => {
  const values = Array.from({ length: 100 }, (_, i) => i / 10).concat([500]);
  const h = histogram(values, 10);
  assert.equal(h.counts.reduce((a, b) => a + b, 0), 101);
  assert.ok(h.hi < 20);                                     // the range stops near the bulk, not at 500
  assert.equal(histogram([1], 10), null);
  assert.equal(histogram([3, 3, 3], 10), null);
  assert.equal(quantile([1, 2, 3, 4], 0.5), 2.5);
});
