import test from "node:test";
import assert from "node:assert/strict";
import { poissonBinomial, tails, mean, quantile, poissonOutcome } from "../../src/app/web/js/lib/stats.js";

test("poisson-binomial pmf sums to one and matches the binomial case", () => {
  const pmf = poissonBinomial([0.5, 0.5, 0.5]);
  assert.deepEqual(pmf.map((p) => Math.round(p * 1000) / 1000), [0.125, 0.375, 0.375, 0.125]);
  const messy = poissonBinomial([0.02, 0.4, 0.13, 0.76, 0.08, 0.31]);
  assert.ok(Math.abs(messy.reduce((a, b) => a + b, 0) - 1) < 1e-12);
});

test("mean of the pmf equals the sum of probabilities", () => {
  const ps = [0.1, 0.2, 0.3, 0.4];
  const pmf = poissonBinomial(ps);
  const m = pmf.reduce((acc, p, k) => acc + p * k, 0);
  assert.ok(Math.abs(m - 1.0) < 1e-12);
});

test("tails are inclusive and complementary", () => {
  const pmf = poissonBinomial([0.5, 0.5]);
  const t = tails(pmf, 1);
  assert.ok(Math.abs(t.atLeast - 0.75) < 1e-12);
  assert.ok(Math.abs(t.atMost - 0.75) < 1e-12);
});

test("quantile interpolates", () => {
  assert.equal(quantile([1, 2, 3, 4], 0.5), 2.5);
  assert.ok(Number.isNaN(mean([])));
});

test("outcome probabilities sum to one and favour the bigger xG", () => {
  const o = poissonOutcome(2.0, 0.6);
  assert.ok(Math.abs(o.home + o.draw + o.away - 1) < 1e-9);
  assert.ok(Math.abs(o.home - 0.705) < 0.005 && Math.abs(o.away - 0.101) < 0.005);
  const even = poissonOutcome(1.2, 1.2);
  assert.ok(Math.abs(even.home - even.away) < 1e-9);
});
