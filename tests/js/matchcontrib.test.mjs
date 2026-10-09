import test from "node:test";
import assert from "node:assert/strict";
import { contributors, shortName } from "../../src/app/web/js/ui/matchcontrib.js";

const team = [["A", 0.9], ["B", 0.5], ["C", 0.3], ["D", 0.2], ["E", 0.05], ["F", 0.03], ["G", 0.02], ["H", 0.0]].map(([name, xg], i) => ({ id: i + 1, name, xg, xa: 0 }));

test("contributors are ordered, share one total, and carry a running share that ends at 100%", () => {
  const c = contributors(team, (p) => p.xg, 4);
  assert.deepEqual(c.rows.map((r) => r.name), ["A", "B", "C", "D", "3 others"]);   // E, F, G pooled; H did nothing and is left out
  assert.ok(Math.abs(c.total - 2.0) < 1e-9);
  assert.ok(Math.abs(c.rows.reduce((s, r) => s + r.share, 0) - 1) < 1e-9);
  assert.ok(Math.abs(c.rows.at(-1).cum - 1) < 1e-9);
  assert.equal(c.rows[0].share, 0.45);
  assert.equal(c.rows.at(-1).id, null);
});

test("nothing to split is an empty list, never a division by zero", () => {
  assert.deepEqual(contributors(team.map((p) => ({ ...p, xg: 0 })), (p) => p.xg), { total: 0, rows: [] });
  assert.deepEqual(contributors([], (p) => p.xg), { total: 0, rows: [] });
});

test("names shorten to an initial and the surname, whatever the surname is", () => {
  assert.equal(shortName("Enzo Fonetta"), "E. Fonetta");
  assert.equal(shortName("Kevin De Bruyne"), "K. De Bruyne");
  assert.equal(shortName("Rodri"), "Rodri");
});
