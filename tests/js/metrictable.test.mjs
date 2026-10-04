import test from "node:test";
import assert from "node:assert/strict";
import { SORTS, describeSort, nextSort, orderMetrics } from "../../src/app/web/js/lib/metrictable.js";

const m = (label, value, pct, rank, hib = true) => ({ key: label.toLowerCase(), label, value, pct, rank, hib });

/** Two kinds of metric, as the profile sends them: a style metric (hib null), a metric with no value, and one that is not ranked. */
const blocks = () => [
  { category: "Shooting", blurb: "shots", items: [m("Shots", 22, 74, 20), m("Goals", 3, 78, 16), m("Shot distance", 18.6, 74, 23, null), m("Penalties", null, null, null)] },
  { category: "Passing", blurb: "passes", items: [m("Passes", 40, 20, 70), m("Assists", 4, 90, 5), m("Fouls", 1.2, 95, 3, false), m("Age", 32, 99, 1, null), m("Crosses", 3, null, null)] },
];
const labels = (rows) => rows.map((r) => r.label);
const flat = (key, dir, grouped = false) => labels(orderMetrics(blocks(), { key, dir }, grouped).flatMap((b) => b.items));

test("a column starts in the direction that suits it, and the same column turns round", () => {
  assert.deepEqual(nextSort(null, "pct"), { key: "pct", dir: "desc" });                  // best first
  assert.deepEqual(nextSort(null, "rank"), { key: "rank", dir: "asc" });                 // rank 1 first
  assert.deepEqual(nextSort(null, "metric"), { key: "metric", dir: "asc" });             // A to Z
  assert.deepEqual(nextSort({ key: "pct", dir: "desc" }, "pct"), { key: "pct", dir: "asc" });
  assert.deepEqual(nextSort({ key: "pct", dir: "asc" }, "pct"), { key: "pct", dir: "desc" });
  assert.deepEqual(nextSort({ key: "pct", dir: "asc" }, "value"), { key: "value", dir: "desc" });   // another column: its own first direction
  assert.deepEqual(Object.keys(SORTS), ["metric", "value", "pct", "rank"]);
});

test("the sort is described in words", () => {
  assert.equal(describeSort({ key: "pct", dir: "desc" }), "percentile, highest first");
  assert.equal(describeSort({ key: "rank", dir: "asc" }), "rank, best first");
  assert.equal(describeSort({ key: "rank", dir: "desc" }), "rank, worst first");
  assert.equal(describeSort({ key: "metric", dir: "desc" }), "metric, Z to A");
});

test("with no sort the table is as it came, grouped or flattened", () => {
  const grouped = orderMetrics(blocks(), null, true);
  assert.deepEqual(grouped.map((b) => b.category), ["Shooting", "Passing"]);
  assert.deepEqual(labels(grouped[0].items), ["Shots", "Goals", "Shot distance", "Penalties"]);
  const all = orderMetrics(blocks(), null, false);
  assert.equal(all.length, 1);
  assert.equal(all[0].category, null);
  assert.deepEqual(labels(all[0].items), ["Shots", "Goals", "Shot distance", "Penalties", "Passes", "Assists", "Fouls", "Age", "Crosses"]);
  assert.deepEqual(all[0].items.map((r) => r.kind).slice(2, 6), ["Shooting", "Shooting", "Passing", "Passing"]);      // a flat list still says what each metric is about
});

test("by percentile the best come first, then the style metrics, then those with none", () => {
  assert.deepEqual(flat("pct", "desc"), ["Fouls", "Assists", "Goals", "Shots", "Passes", "Age", "Shot distance", "Penalties", "Crosses"]);
  // turned round, the style metrics and the blanks still stay at the end: neither is "worst"
  assert.deepEqual(flat("pct", "asc"), ["Passes", "Shots", "Goals", "Assists", "Fouls", "Shot distance", "Age", "Penalties", "Crosses"]);
});

test("by rank the best come first, a style metric (which shows no rank) after them, blanks last", () => {
  assert.deepEqual(flat("rank", "asc"), ["Fouls", "Assists", "Goals", "Shots", "Passes", "Shot distance", "Age", "Penalties", "Crosses"]);
  assert.deepEqual(flat("rank", "desc"), ["Passes", "Shots", "Goals", "Assists", "Fouls", "Shot distance", "Age", "Penalties", "Crosses"]);
});

test("by value the numbers are in order and a blank is never a zero", () => {
  assert.deepEqual(flat("value", "desc"), ["Passes", "Age", "Shots", "Shot distance", "Assists", "Goals", "Crosses", "Fouls", "Penalties"]);
  assert.deepEqual(flat("value", "asc"), ["Fouls", "Goals", "Crosses", "Assists", "Shot distance", "Shots", "Age", "Passes", "Penalties"]);     // Goals and Crosses tie on 3
});

test("by name the order is alphabetical, either way round", () => {
  assert.deepEqual(flat("metric", "asc"), ["Age", "Assists", "Crosses", "Fouls", "Goals", "Passes", "Penalties", "Shot distance", "Shots"]);
  assert.deepEqual(flat("metric", "desc"), ["Shots", "Shot distance", "Penalties", "Passes", "Goals", "Fouls", "Crosses", "Assists", "Age"]);
});

test("grouped, each kind is sorted inside itself and the kinds stay where they were", () => {
  const out = orderMetrics(blocks(), { key: "pct", dir: "desc" }, true);
  assert.deepEqual(out.map((b) => b.category), ["Shooting", "Passing"]);
  assert.deepEqual(labels(out[0].items), ["Goals", "Shots", "Shot distance", "Penalties"]);
  assert.deepEqual(labels(out[1].items), ["Fouls", "Assists", "Passes", "Age", "Crosses"]);
  assert.equal(out[0].blurb, "shots");                                                   // the heading keeps its text
});

test("equal rows keep the order the table started in, whichever way round", () => {
  const same = [{ category: "A", items: [m("One", 1, 50, 5), m("Two", 1, 50, 5), m("Three", 1, 50, 5)] }];
  assert.deepEqual(labels(orderMetrics(same, { key: "pct", dir: "desc" }, false)[0].items), ["One", "Two", "Three"]);
  assert.deepEqual(labels(orderMetrics(same, { key: "pct", dir: "asc" }, false)[0].items), ["One", "Two", "Three"]);
});

test("ordering never changes what it was given", () => {
  const input = blocks();
  const before = JSON.stringify(input);
  orderMetrics(input, { key: "pct", dir: "desc" }, false);
  orderMetrics(input, { key: "metric", dir: "asc" }, true);
  assert.equal(JSON.stringify(input), before);
});
