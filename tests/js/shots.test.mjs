// The shot helpers every shot board shares: filters, totals that never count a missing xG as zero, takers, order.
import test from "node:test";
import assert from "node:assert/strict";
import { filterShots, lastActionWord, orderShots, shotLook, shotRadius, shotTakers, shotTotals, takerKey, teamShot } from "../../src/app/web/js/lib/shots.js";

const shot = (o) => ({ id: 1, x: 0.9, y: 0.5, xg: 0.1, result: "MissedShots", minute: 10, player: "A", player_id: 7, situation: "OpenPlay", side: 0, ...o });
const LIST = [
  shot({ id: 1, minute: 80, xg: 0.05 }),
  shot({ id: 2, minute: 12, xg: 0.76, result: "Goal", situation: "Penalty" }),
  shot({ id: 3, minute: 30, xg: 0.3, result: "SavedShot", player: "B", player_id: 8 }),
  shot({ id: 4, minute: 44, xg: null, result: "Goal", player: "C", player_id: 9, side: 1, situation: "FromCorner" }),
  shot({ id: 5, minute: 50, xg: 0.2, result: "BlockedShot", player: "A", player_id: 7, side: 1 }),
];

test("filters combine: side, taker, situation and result", () => {
  assert.deepEqual(filterShots(LIST, { side: 0 }).map((s) => s.id), [1, 2, 3]);
  assert.deepEqual(filterShots(LIST, { taker: "0:7" }).map((s) => s.id), [1, 2]);
  assert.deepEqual(filterShots(LIST, { situation: "pen" }).map((s) => s.id), [2]);
  assert.deepEqual(filterShots(LIST, { result: "target" }).map((s) => s.id), [2, 3, 4]);
  assert.deepEqual(filterShots(LIST, { side: 1, result: "goals" }).map((s) => s.id), [4]);
  assert.deepEqual(filterShots(LIST, { situation: "nonsense" }).length, 5);
});

test("the same player id on the other side is another taker", () => {
  assert.notEqual(takerKey(LIST[0]), takerKey(LIST[4]));
  const t = shotTakers(LIST);
  assert.deepEqual(t.map((x) => [x.key, x.n, x.goals]), [["0:7", 2, 1], ["0:8", 1, 0], ["1:7", 1, 0], ["1:9", 1, 1]]);
  assert.equal(t.find((x) => x.key === "1:9").xg, null);
});

test("totals add only the xG that exists and say how many shots had one", () => {
  const all = shotTotals(LIST);
  assert.equal(all.n, 5); assert.equal(all.goals, 2); assert.equal(all.on_target, 3); assert.equal(all.known, 4);
  assert.ok(Math.abs(all.xg - 1.31) < 1e-9);
  assert.equal(all.per, null);                       // one shot has no xG: no average is given
  const home = shotTotals(LIST.filter((s) => s.side === 0));
  assert.ok(Math.abs(home.per - 1.11 / 3) < 1e-9);
  const none = shotTotals([LIST[3]]);
  assert.equal(none.xg, null); assert.equal(none.per, null);
  assert.deepEqual(shotTotals([]), { n: 0, goals: 0, on_target: 0, xg: null, known: 0, per: null });
});

test("order: as they came, or the best chance first with no-xG shots last", () => {
  assert.deepEqual(orderShots(LIST, "time").map((s) => s.id), [2, 3, 4, 5, 1]);
  assert.deepEqual(orderShots(LIST, "xg").map((s) => s.id), [2, 3, 5, 1, 4]);
  const two = [shot({ id: 1, date: "2025-09-02", minute: 5 }), shot({ id: 2, date: "2025-08-20", minute: 88 })];
  assert.deepEqual(orderShots(two, "time").map((s) => s.id), [2, 1]);
});

test("a shot with no xG is drawn at one size and marked", () => {
  assert.equal(shotLook(LIST[3]), "goal noxg");
  assert.equal(shotLook(LIST[2]), "on");
  assert.equal(shotLook(LIST[0]), "off");
  assert.equal(shotRadius(null), 1.5);
  assert.ok(shotRadius(0.8) > shotRadius(0.1));
});

test("a team row becomes a shot with its match", () => {
  const s = teamShot([0.9, 0.4, 0.31, "Goal", 55, "Saka", "OpenPlay", "LeftFoot", 31230, 7322, "Odegaard", "Throughball"], 3, 0, { 31230: { date: "2025-10-04", opponent: "Leeds", home: true } });
  assert.deepEqual([s.id, s.player_id, s.assisted_by, s.opponent, s.date, s.home, s.side], ["0-3", 7322, "Odegaard", "Leeds", "2025-10-04", true, 0]);
  const old = teamShot([0.9, 0.4, 0.31, "Goal", 55, "Saka", "OpenPlay", "LeftFoot", 1], 0, 1);   // a stored answer from before the extra fields
  assert.deepEqual([old.player_id, old.assisted_by, old.opponent], [null, null, null]);
  assert.equal(lastActionWord("None"), null); assert.equal(lastActionWord("TakeOn"), "Take On"); assert.equal(lastActionWord("Throughball"), "Throughball");
});
