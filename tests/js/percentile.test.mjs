import test from "node:test";
import assert from "node:assert/strict";
import { beats, direction, peerGroup, readBar } from "../../src/app/web/js/lib/percentile.js";

test("a bar is read as 'better than N of every 100', flipped for fewer-is-better and silent about quality for style metrics", () => {
  assert.equal(readBar({ pct: 77.8, rank: 16, pool_n: 88, hib: true }, "midfielders"), "Better than 78 of every 100 midfielders. Rank 16 of 88.");
  assert.match(readBar({ pct: 91, rank: 8, pool_n: 88, hib: false }, "defenders"), /^Better than 91 of every 100 defenders\. Less is better here, so the bar is flipped: a long bar means he does this less than most\. Rank 8 of 88\.$/);
  assert.match(readBar({ pct: 93.2, rank: 5, pool_n: 88, hib: null }, "midfielders"), /^A matter of style, not quality: he is higher than 93 of every 100 midfielders on this, and neither high nor low is better\.$/);
  assert.equal(readBar({ pct: null, hib: true }, "midfielders"), null);
  assert.equal(readBar({ pct: 72.2, higher_is_better: true }, "midfielders"), "Better than 72 of every 100 midfielders.");      // a profile item has no rank or pool size
  assert.equal(direction({ higher_is_better: false }), false);
  assert.equal(direction({}), true);
});

test("a percentile never claims to beat 0 or 100 of every 100", () => {
  assert.equal(beats(99.8), 99);
  assert.equal(beats(0.2), 1);
  assert.equal(beats(49.5), 50);
  assert.equal(peerGroup({ n: 88, who: "midfielders", league: "Premier League", minutes: 660 }), "the 88 midfielders in the Premier League who have played at least 660 minutes");
});
