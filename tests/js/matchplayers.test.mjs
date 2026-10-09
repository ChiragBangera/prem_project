import test from "node:test";
import assert from "node:assert/strict";
import { extremes, filterPlayers } from "../../src/app/web/js/lib/matchplayers.js";

const ctx = { idx: { tackles90: 0, fouls90: 1, touches90: 2 }, metrics: { tackles90: { hib: true }, fouls90: { hib: false }, touches90: { hib: null } } };
const row = (id, side, group, minutes, started, v) => ({ id, name: `Player ${id}`, side, group, minutes, started, v });
const rows = [
  row(1, "h", "DEF", 90, true, [4, 3, 50]), row(2, "h", "MID", 90, true, [2, 1, 70]), row(3, "a", "DEF", 60, true, [1, 0, 40]),
  row(4, "a", "ATT", 20, false, [0, 2, 30]), row(5, "a", "MID", 90, true, [null, 1, 60]),
];

test("the match table filters by team, role, minutes, starters and name, all together", () => {
  assert.equal(filterPlayers(rows, {}).length, 5);
  assert.deepEqual(filterPlayers(rows, { side: "a" }).map((r) => r.id), [3, 4, 5]);
  assert.deepEqual(filterPlayers(rows, { minutes: 60 }).map((r) => r.id), [1, 2, 3, 5]);
  assert.deepEqual(filterPlayers(rows, { minutes: 90, role: "MID" }).map((r) => r.id), [2, 5]);
  assert.deepEqual(filterPlayers(rows, { started: true, side: "a" }).map((r) => r.id), [3, 5]);
  assert.deepEqual(filterPlayers(rows, { search: " player 4 " }).map((r) => r.id), [4]);
});

test("the best and the weakest follow the direction of the metric, and style metrics have neither", () => {
  const e = extremes(rows, ["tackles90", "fouls90", "touches90"], ctx);
  assert.deepEqual([...e.tackles90.best], [1]);
  assert.deepEqual([...e.tackles90.worst], [4]);                 // blank (player 5) is nobody's worst
  assert.deepEqual([...e.fouls90.best], [3]);                    // fewer fouls is better
  assert.deepEqual([...e.fouls90.worst], [1]);
  assert.equal(e.touches90, undefined);
});

test("nobody is marked when too few have a value or they all share one", () => {
  assert.deepEqual(extremes(rows.slice(0, 3), ["tackles90"], ctx), {});
  const same = rows.map((r) => ({ ...r, v: [1, 1, 1] }));
  assert.deepEqual(extremes(same, ["tackles90", "fouls90"], ctx), {});
});

test("a crowd tied on the lowest value is the norm, not the weakest", () => {
  const goals = [1, 0, 0, 0, 0, 0].map((g, n) => row(n + 1, "h", "MID", 90, true, [g, 0, 0]));
  const e = extremes(goals, ["tackles90"], ctx);
  assert.deepEqual([...e.tackles90.best], [1]);
  assert.equal(e.tackles90.worst.size, 0);
});
