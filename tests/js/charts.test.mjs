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
  // a label never covers another dot: with a neighbour to the right the name goes to the other side, and with dots all round it is left out
  const dots = [{ id: 1, x: 50, y: 50, r: 4 }, { id: 2, x: 70, y: 50, r: 4 }];
  const [beside] = placeLabels([{ id: 1, x: 50, y: 50, r: 4, text: "Alpha" }], { w: 300, h: 200 }, 12, dots);
  assert.equal(beside.anchor, "end");
  const ring = Array.from({ length: 24 }, (_, i) => ({ id: 10 + i, x: 50 + 22 * Math.cos(i * Math.PI / 12), y: 50 + 14 * Math.sin(i * Math.PI / 12), r: 5 }));
  assert.equal(placeLabels([{ id: 1, x: 50, y: 50, r: 4, text: "Alpha" }], { w: 300, h: 200 }, 12, ring).length, 0);
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

test("pass network names: each sits nearest its own dot, or is moved out on a leader line; none covers a dot or another name", async () => {
  const { placeNames } = await import("../../src/app/web/js/charts/pitchmaps.js");
  const radius = () => 3;
  // two players who stood in almost the same place, a third just under them, and one alone
  const nodes = [{ id: 1, name: "Schlager", x: 500, y: 500, touches: 60 }, { id: 2, name: "McAtee", x: 505, y: 510, touches: 40 },
    { id: 3, name: "Milenkovic", x: 440, y: 505, touches: 50 }, { id: 4, name: "Sels", x: 100, y: 500, touches: 30 }];
  const at = placeNames(nodes, radius, (n) => n.name);
  assert.equal(at.size, 4);
  assert.equal(at.get(4).leader, undefined);                              // room beside the dot: no line needed
  assert.ok(at.get(2).leader || at.get(1).leader);                        // the pile is told apart with a line
  const boxes = [...at.values()].map((p) => p.box);
  const hit = (a, b) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) assert.equal(hit(boxes[i], boxes[j]), false);
});
