import test from "node:test";
import assert from "node:assert/strict";
import { niceTicks, niceExtent, scaleLinear, scaleBand, nearest, linePath, stepPath, tickFormat } from "../../src/app/web/js/charts/core.js";
import { placeLabels, dodge } from "../../src/app/web/js/charts/scatter.js";
import { toCsv } from "../../src/app/web/js/lib/csv.js";

test("ticks land on round numbers and cover the range", () => {
  assert.deepEqual(niceTicks(0, 1, 5), [0, 0.2, 0.4, 0.6, 0.8, 1]);
  assert.deepEqual(niceTicks(-2, 6, 4), [-2, 0, 2, 4, 6]);
  const [lo, hi] = niceExtent(0.13, 0.87, 5);
  assert.ok(lo <= 0.13 && hi >= 0.87);
  assert.equal(tickFormat(0.5)(0.5), "0.5");
  assert.equal(tickFormat(1)(-2), "−2");
});

test("scales map both ways and bands do not overlap", () => {
  const s = scaleLinear([0, 10], [100, 0]);
  assert.equal(s(0), 100);
  assert.equal(s(10), 0);
  assert.equal(s.invert(50), 5);
  const b = scaleBand(["a", "b", "c"], [0, 300], 0.2);
  assert.ok(b("b") > b("a") + b.bandwidth);
  assert.equal(Math.round(b.center("a")), 50);
});

test("nearest picks the closest index in a sorted array", () => {
  assert.equal(nearest([0, 10, 20, 30], 12), 1);
  assert.equal(nearest([0, 10, 20, 30], 26), 3);
  assert.equal(nearest([5], 100), 0);
});

test("line paths break at missing values; step paths hold then jump", () => {
  const x = (v) => v * 10, y = (v) => 100 - v;
  assert.equal(linePath([0, 1, 2, 3], [1, 2, null, 4], x, y), "M0.0,99.0L10.0,98.0M30.0,96.0");
  assert.equal(stepPath([0, 5, 9], [0, 1, 2], x, y), "M0.0,100.0H50.0V99.0H90.0V98.0");
});

test("label placement drops labels that would collide; pills are nudged apart", () => {
  const placed = placeLabels([
    { id: 1, x: 50, y: 50, r: 4, text: "Alpha" },
    { id: 2, x: 52, y: 51, r: 4, text: "Alphb" },
  ], { w: 300, h: 200 });
  assert.equal(placed.length >= 1, true);
  const pills = dodge([
    { id: "a", px: 100, py: 100, bw: 30, bh: 20 },
    { id: "b", px: 102, py: 101, bw: 30, bh: 20 },
  ], { w: 300, h: 200 });
  const overlap = Math.abs(pills[0].x - pills[1].x) < 30 && Math.abs(pills[0].y - pills[1].y) < 20;
  assert.equal(overlap, false);
});

test("csv escapes commas, quotes and newlines", () => {
  const csv = toCsv([{ label: "Name", export: (r) => r.n }, { label: "Note", export: (r) => r.t }], [{ n: "A, B", t: 'say "hi"\nbye' }, { n: "C", t: null }]);
  assert.equal(csv, 'Name,Note\n"A, B","say ""hi""\nbye"\nC,');
});
