import test from "node:test";
import assert from "node:assert/strict";
import { PF, DK, blocks, channels, grid, leaders, minuteLabel, momentum, network, pick, playerRows, teamStats } from "../../src/app/web/js/lib/matchcentre.js";

// Home (0): players 1 and 2. Away (1): player 9. First half ends at minute 47; the second starts at 48.
const c = {
  clock: { end: 96, ht: 47, second_from: 48 },
  names: { 1: "Ann One", 2: "Bea Two", 9: "Cy Nine" },
  teams: [{ players: [{ id: 1, start: true }, { id: 2, start: true }] }, { players: [{ id: 9, start: true }] }],
  timeline: [{ em: 70, kind: "sub", tm: 0, p: 3, other: 2 }],
  touches: [[0, 1, 5, 700, 300, 1], [0, 1, 5, 900, 500, 2], [0, 1, 30, 200, 500, 1], [0, 2, 60, 800, 900, 2], [1, 1, 10, 700, 500, 9], [1, 2, 80, 300, 500, 9]],
  passes: [
    [0, 1, 5, 300, 300, 700, 300, 1, PF.PROG | PF.F3, 1, 2], [0, 1, 6, 700, 300, 900, 500, 1, PF.BOX | PF.KEY, 1, 2], [0, 1, 7, 500, 500, 600, 500, 0, 0, 2, 0],
    [0, 2, 75, 500, 500, 600, 500, 1, 0, 1, 2], [0, 1, 8, 0, 0, 100, 100, 1, PF.RESTART, 1, 2],
    [1, 1, 10, 300, 500, 400, 500, 1, 0, 9, 0], [1, 2, 80, 300, 500, 400, 500, 1, PF.LONG, 9, 0],
  ],
  def: [[0, 1, 12, 650, 500, DK.TACKLE, 1, 1], [0, 1, 13, 700, 500, DK.RECOVER, 1, 2], [0, 2, 70, 200, 500, DK.AERIAL, 0, 1], [1, 1, 20, 100, 500, DK.CLEAR, 1, 9]],
  takeons: [[0, 1, 15, 800, 500, 1, 2]],
  carries: [[0, 1, 16, 600, 500, 850, 500, 1, 2]],
  fouls: [[1, 1, 25, 500, 500, 9]],
  shots: [{ tm: 0, pe: 1, em: 5, mi: 5, x: 900, y: 500, result: "Goal", p: 2, big: true, xg: 0.4 }, { tm: 1, pe: 2, em: 80, mi: 77, x: 700, y: 500, result: "MissedShots", p: 9, big: false, xg: null }],
};

test("a period keeps only its own rows, and restarts are not open-play passes", () => {
  assert.equal(pick(c.passes, { period: 1, tm: 0 }).length, 4);
  const [home, away] = teamStats(c, "all");
  assert.equal(home.passes, 4);                          // the throw-in is left out
  assert.equal(home.pass_ok, 3);
  assert.equal(Math.round(home.possession), 67);        // 4 of 6 open-play passes
  assert.equal(home.f3_touches, 3);
  assert.equal(home.tilt, 75);                           // 3 of the 4 final-third touches
  assert.equal(home.box_touches, 1);
  assert.equal(home.f3_entries, 2);                      // a pass and a carry
  assert.equal(home.box_entries, 2);
  assert.equal(home.xg, 0.4);
  assert.equal(away.xg, null);                           // one shot without xG: no total is made up
  assert.equal(home.high_regains, 1);
  assert.equal(away.long_share, 50);
  const second = teamStats(c, 2);
  assert.equal(second[0].passes, 1);
  assert.equal(second[1].shots, 1);
});

test("PPDA divides the other side's build-up passes by this side's pressing actions", () => {
  const [home, away] = teamStats(c, "all");
  assert.equal(home.press, 1);                           // the tackle at 65% of the pitch; a recovery is not a pressing action
  assert.equal(home.ppda, 2);                            // the away side's two passes in its own 60%
  assert.equal(away.ppda, 3 / 1);                        // the away foul high up, against three home build-up passes
});

test("momentum counts final-third touches, weights the box and shots, and never smooths across half time", () => {
  const mo = momentum(c, { window: 5 });
  assert.equal(mo.raw[0][5], 1 + 3 + 6);                 // a final-third touch, a box touch and a shot in minute 5
  assert.equal(mo.raw[1][80], 6);                        // the shot only: the away touch that minute is in its own half
  assert.ok(mo.home[5] > 0 && mo.home[7] > 0 && mo.home[8] === 0);
  assert.equal(mo.home.length, 97);
  const edge = momentum({ ...c, touches: [[0, 1, 47, 900, 500, 1]], shots: [] });
  assert.ok(edge.home[47] > 0 && edge.home[48] === 0);   // the last minute of the first half does not leak into the second
});

test("blocks cut each half into quarter-hours, stoppage time joining the last", () => {
  const b = blocks(c);
  assert.deepEqual(b.map((x) => x.label), ["1–15", "16–30", "31–45+", "46–60", "61–75", "76–90+"]);
  assert.deepEqual([b[2].from, b[2].to, b[3].from, b[5].to], [30, 47, 48, 96]);
  assert.equal(b[0].possession, 75);
  assert.equal(b[5].shots[1], 1);
});

test("the starting network stops at the first substitution and pairs passes either way", () => {
  const net = network(c, 0, { starters: true, minEdge: 1, minTouches: 1 });
  assert.equal(net.until, 70);
  assert.deepEqual(net.edges, [{ a: 1, b: 2, n: 2 }]);    // the pass after the change, and the throw-in, are not counted
  assert.equal(network(c, 0, { minEdge: 1, minTouches: 1 }).edges[0].n, 3);
});

test("channels, grids, player lines and leaders", () => {
  assert.deepEqual(channels(c, 0).counts, [1, 1, 1]);
  assert.equal(grid(pick(c.touches, { tm: 0 })).reduce((a, v) => a + v, 0), 4);
  const rows = playerRows(c);
  const two = rows.find((r) => r.id === 2);
  assert.deepEqual([two.touches, two.goals, two.prog_carries, two.takeons_won, two.recoveries, two.xg], [2, 1, 1, 1, 1, 0.4]);
  assert.equal(rows.find((r) => r.id === 1).pass_acc, 100);
  const board = leaders(c).find((b) => b.key === "prog_passes");
  assert.deepEqual(board.top.map((p) => p.name), ["Ann One"]);
  assert.equal(minuteLabel(1, 46), "45+2′");
  assert.equal(minuteLabel(2, 92), "90+3′");
  assert.equal(minuteLabel(2, 59), "60′");
});

// ------------------------------------------------------------------ moves
import { SK, SF, moveBreaks, moveEnding, moveLeaders, moveLines, moveStats, pickMoves } from "../../src/app/web/js/lib/matchcentre.js";

const st = (kind, p, x, y, ex = -1, ey = -1, ok = 1, flags = 0) => [kind, p, x, y, ex, ey, ok, 5, flags];
const mv = (over) => ({ tm: 0, pe: 1, em: 5, c0: 300, c1: 320, st: "open", sp: 0, sat: null, steps: [], n: 0, end: "lost", lost: 0, by: 0, how: "", at: null, si: null, f3: false, box: false, keep: null, re: "", ...over });
const cm = {
  ...c,
  possessions: [
    mv({ steps: [st(SK.PASS, 1, 300, 500, 500, 500), st(SK.CARRY, 2, 500, 500, 700, 500), st(SK.PASS, 2, 700, 500, 900, 500, 1, SF.CROSS), st(SK.SHOT, 1, 900, 500)], n: 2, end: "goal", si: 0, f3: true, box: true }),
    mv({ steps: [st(SK.PASS, 1, 300, 500, 400, 500), st(SK.TAKEON, 2, 400, 500, -1, -1, 0)], n: 1, end: "lost", lost: 2, by: 9, how: "tackle", at: [420, 500] }),
    mv({ steps: [st(SK.PASS, 2, 300, 500, 400, 0, 0)], end: "out", lost: 2, keep: false, re: "throw_in" }),
    mv({ tm: 1, pe: 2, steps: [st(SK.PASS, 9, 300, 500, 600, 500, 0, SF.LONG)], end: "lost", lost: 9, by: 1, how: "interception", at: [550, 500] }),
  ],
};

test("moves are picked by side, half, ending, length and whether they reached the box", () => {
  assert.equal(pickMoves(cm, { tm: 0 }).length, 3);
  assert.equal(pickMoves(cm, { period: 2 }).length, 1);
  assert.deepEqual(pickMoves(cm, { ended: "shot" }).map((m) => m.end), ["goal"]);
  assert.equal(pickMoves(cm, { ended: "lost" }).length, 2);
  assert.equal(pickMoves(cm, { minPasses: 2 }).length, 1);
  assert.equal(pickMoves(cm, { box: true }).length, 1);
  assert.equal(pickMoves(cm, { player: 9 }).length, 1);
});

test("a side's moves in numbers; xG only when every shot has one", () => {
  const [home, away] = moveStats(cm);
  assert.deepEqual([home.moves, home.shots, home.goals, home.box, home.lost, home.out, home.longest], [3, 1, 1, 1, 1, 1, 2]);
  assert.equal(home.passes_per, 1.5);
  assert.equal(home.xg, 0.4);
  assert.equal(away.xg, null);
});

test("who lost it and who broke it up", () => {
  const { lost, broke } = moveLeaders(cm);
  assert.deepEqual(lost.map((r) => [r.id, r.value]), [[2, 2], [9, 1]]);
  assert.deepEqual(broke.map((r) => [r.id, r.tm, r.value]).sort(), [[1, 0, 1], [9, 1, 1]]);
  assert.deepEqual(moveBreaks(cm, 0), [[420, 500, "tackle", 2, 9, 1, 5]]);
});

test("a move reads as numbered lines, a carry between them, and one sentence on how it ended", () => {
  const lines = moveLines(cm, cm.possessions[0]);
  assert.deepEqual(lines.map((l) => [l.n, l.text]), [[1, "One → Two"], [null, "Two carried it 21 m"], [2, "Two → One, cross"], [3, "One shot"]]);
  assert.equal(moveEnding(cm, cm.possessions[0]), "Goal: Two, 0.40 xG.");
  assert.equal(moveEnding(cm, cm.possessions[1]), "Lost by Two, tackled by Nine.");
  assert.equal(moveEnding(cm, cm.possessions[2]), "Two played it out of play.");
});

import { playerOutcomes } from "../../src/app/web/js/lib/matchcentre.js";
import { fitLine, offTheLine } from "../../src/app/web/js/lib/stats.js";
import { clipLine } from "../../src/app/web/js/charts/scatter.js";

test("each player's forward actions, split by whether the move came to a shot", () => {
  const co = { ...c, possessions: [
    mv({ ls: true, steps: [st(SK.PASS, 1, 300, 500, 500, 500, 1, SF.PROG), st(SK.CARRY, 2, 500, 500, 700, 500, 1, SF.PROG), st(SK.PASS, 2, 700, 500, 900, 500, 1, SF.CROSS), st(SK.SHOT, 1, 900, 500)], end: "goal" }),
    mv({ ls: false, steps: [st(SK.PASS, 1, 300, 500, 500, 500, 1, SF.PROG), st(SK.PASS, 1, 500, 500, 520, 500), st(SK.TAKEON, 2, 400, 500, -1, -1, 0), st(SK.TAKEON, 2, 400, 500)] }),
    mv({ pe: 2, ls: false, steps: [st(SK.PASS, 1, 300, 500, 500, 500, 1, SF.PROG)] }),
  ] };
  const [second, first] = playerOutcomes(co);                                         // equally busy: the one with more to show comes first
  assert.deepEqual([first.id, first.n, first.shot], [1, 3, 1]);                       // the shot and the plain pass are not counted
  assert.deepEqual(second.kinds, { prog_carries: { n: 1, shot: 1 }, crosses: { n: 1, shot: 1 }, takeons_won: { n: 1, shot: 0 } });
  assert.deepEqual(playerOutcomes(co, 1).map((r) => [r.id, r.n]), [[2, 3], [1, 2]]);
  assert.equal(playerOutcomes(co, 2)[0].n, 1);
});

test("the trend line, who stands off it, and the part of it inside the plot", () => {
  const pts = Array.from({ length: 10 }, (_, i) => ({ id: i, x: i, y: 2 * i + 1 + (i % 2 ? 0.1 : -0.1) }));
  const line = fitLine(pts);
  assert.ok(Math.abs(line.b - 2) < 0.05 && Math.abs(line.a - 1) < 0.2);
  assert.equal(fitLine(pts.slice(0, 5)), null);
  assert.equal(fitLine(pts.map((p) => ({ ...p, x: 3 }))), null);
  const off = offTheLine([...pts, { id: "low", x: 8, y: 5 }, { id: "ignored", x: 1, y: -9 }], line, { fromX: 5 });
  assert.equal(off.below[0].id, "low");
  assert.ok(!off.below.some((p) => p.id === "ignored"));                              // left of the cut: a gap at low volume is noise
  assert.deepEqual(clipLine({ a: 0, b: 1 }, [0, 10], [2, 6]), [2, 2, 6, 6]);
  assert.equal(clipLine({ a: 20, b: 0 }, [0, 10], [2, 6]), null);
});
