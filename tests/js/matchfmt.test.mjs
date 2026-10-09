import test from "node:test";
import assert from "node:assert/strict";
import { kickoff, phaseOf, scorerLines, shortName, verdict } from "../../src/app/web/js/lib/matchfmt.js";
import { blank, direction, fmtMetric, fmtPct } from "../../src/app/web/js/lib/metricfmt.js";
import { formation } from "../../src/app/web/js/lib/format.js";

test("a scorer is shown by a surname people recognise, without guessing at particles", () => {
  assert.equal(shortName("Bruno Fernandes"), "Fernandes");
  assert.equal(shortName("Alexis Mac Allister"), "Mac Allister");
  assert.equal(shortName("Kevin De Bruyne"), "De Bruyne");
  assert.equal(shortName("Trent Alexander-Arnold"), "Alexander-Arnold");
  assert.equal(shortName("Salah"), "Salah");
  assert.equal(shortName(""), "");
});

test("scorer lines combine a player's goals in minute order and mark penalties and own goals", () => {
  const lines = scorerLines([
    { player: "Erling Haaland", id: 1, minute: 77, kind: "goal" },
    { player: "Bruno Fernandes", id: 2, minute: 60, kind: "pen" },
    { player: "Erling Haaland", id: 1, minute: 12, kind: "goal" },
    { player: "Jacob Greaves", id: 3, minute: 93, kind: "og" },
  ]);
  assert.deepEqual(lines.map((l) => [l.name, l.minutes]), [["Haaland", ["12′", "77′"]], ["Fernandes", ["60′ (pen)"]], ["Greaves", ["90+3′ (og)"]]]);
  assert.deepEqual(scorerLines(undefined), []);
});

test("kickoff falls back to the Understat date and time when there is no UTC stamp", () => {
  const k = kickoff({ date: "2026-08-22", dt: "2026-08-22 14:00:00" });
  assert.equal(k.time, "14:00");
  assert.equal(k.key, "2026-08-22");
  const utc = kickoff({ utc: "2026-08-22T14:00:00Z", date: "2026-08-22", dt: "2026-08-22 14:00:00" });
  assert.match(utc.time, /^\d\d:\d\d$/);
  assert.match(utc.key, /^2026-08-2[23]$/);                              // the viewer's own calendar day
});

test("a result that went against the chances gets one sentence, and only then", () => {
  const lied = verdict({ flag: "against_run_of_play", home: "A", away: "B", hg: 1, ag: 0, hxg: 0.4, axg: 2.2 });
  assert.match(lied, /^A won although the chances gave them just \d+%\.$/);
  assert.match(verdict({ flag: "favourite_held", home: "A", away: "B", hg: 1, ag: 1, hxg: 2.5, axg: 0.5 }), /^A were \d+% favourites on chances and only drew\.$/);
  assert.equal(verdict({ flag: null, hxg: 1, axg: 1 }), null);
  assert.equal(verdict({ flag: "against_run_of_play", hxg: null }), null);
});

test("values are written the way people read them", () => {
  const share = { unit: "share", decimals: 0 }, per90 = { unit: "per90", decimals: 2 }, diff = { unit: "total", decimals: 1, signed: true }, metres = { unit: "metres", decimals: 1 };
  assert.equal(fmtMetric(share, 0.806), "81%");
  assert.equal(fmtMetric(per90, 0.5), "0.50");
  assert.equal(fmtMetric(diff, 2.34), "+2.3");
  assert.equal(fmtMetric(diff, -1.8), "−1.8");
  assert.equal(fmtMetric({ unit: "score", decimals: 0 }, 74.7), "75");
  assert.equal(fmtMetric(metres, 21.234), "21.2 m");
  assert.equal(fmtMetric(per90, null), "–");
  assert.equal(fmtMetric(per90, NaN), "–");
  assert.equal(fmtMetric(undefined, 1.234), "1.23");
  assert.equal(blank(0), false);                                          // zero is a value; unknown is not zero
  assert.equal(blank(undefined), true);
  assert.equal(fmtPct(86.6), "87");
  assert.equal(fmtPct(null), "–");
});

test("a metric says which way is better", () => {
  assert.equal(direction({ hib: false }), false);
  assert.equal(direction({ hib: true }), true);
  assert.equal(direction({ hib: null }), null);                           // style metrics: neither end is "better"
  assert.equal(direction(undefined), null);
});

test("a formation is written with dashes", () => {
  assert.equal(formation("4231"), "4-2-3-1");
  assert.equal(formation("433"), "4-3-3");
  assert.equal(formation(null), null);
});

test("an unplayed fixture's phase follows the clock from its kickoff, as the server's match clock does", () => {
  const m = { played: false, utc: "2026-10-10T14:00:00Z" };
  const at = (minutes) => Date.parse("2026-10-10T14:00:00Z") + minutes * 60000;
  assert.deepEqual([-5, 10, 50, 70, 115].map((x) => phaseOf(m, at(x))), ["upcoming", "first_half", "half_time", "second_half", "full_time"]);
  assert.equal(phaseOf({ ...m, played: true }, at(10)), "played");
  assert.equal(phaseOf({ played: false }, at(10)), "upcoming");    // no kickoff time: nothing to say
});
