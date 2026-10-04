import test from "node:test";
import assert from "node:assert/strict";
import { axisRange, changes, deltaText, isFlat, isZeroBased, metricBounds, opponentLine, quickPicks, readTrend, reliability, resultText, strength, versus } from "../../src/app/web/js/lib/trend.js";

const RATE = { key: "shots90", label: "Shots per 90", short: "Shots/90", unit: "per90", decimals: 1, hib: true, shape: "rate" };
const FOULS = { ...RATE, key: "fouls90", label: "Fouls per 90", hib: false };
const SHARE = { key: "pass_acc", label: "Pass accuracy", short: "Pass %", unit: "share", decimals: 0, hib: true, shape: "ratio" };

/** A payload for one metric from a list of `[value, tier, minutes]` (null value = did not play), the way the server builds it: minute-weighted season and form. */
function payloadOf(rows, { key = "shots90", window = 5, splits = {} } = {}) {
  const matches = rows.map(([v, tier, minutes = 90], i) => ({
    i, round: i + 1, date: `2025-09-${String(i + 1).padStart(2, "0")}`, match_id: 1000 + i, opp: `Club ${i}`, opp_short: `C${String(i).padStart(2, "0")}`, home: i % 2 === 0,
    gf: 1, ga: 0, result: "w", played: v != null, page: true, minutes: v == null ? 0 : minutes, started: v != null, events: true,
    opp_ctx: tier ? { tier, rank_xpts: tier === "top" ? 2 : tier === "mid" ? 10 : 19, n_teams: 20, xg_pg: 1.4, xga_pg: 1.2 } : null,
  }));
  const played = rows.map((r) => r[0] != null);
  const weighted = (idx) => {
    const mins = idx.reduce((a, j) => a + matches[j].minutes, 0);
    return mins ? idx.reduce((a, j) => a + rows[j][0] * matches[j].minutes, 0) / mins : null;
  };
  const m = rows.map((r) => r[0]);
  const c = rows.map((_, i) => weighted(rows.slice(0, i + 1).map((__, j) => j).filter((j) => played[j])));
  const r = rows.map((_, i) => weighted(rows.slice(0, i + 1).map((__, j) => j).filter((j) => played[j]).slice(-window)));
  const n = rows.map((row, i) => (row[0] == null ? null : matches[i].minutes));
  return { matches, window, series: { [key]: { m, c, r, n } }, splits };
}

test("opponent strength runs from the weakest side (0) to the strongest (1)", () => {
  assert.equal(strength({ n_teams: 20, rank_xpts: 1 }), 1);
  assert.equal(strength({ n_teams: 20, rank_xpts: 20 }), 0);
  assert.ok(Math.abs(strength({ n_teams: 20, rank_xpts: 10 }) - 10 / 19) < 1e-9);
  assert.equal(strength(null), null);
  assert.equal(strength({ n_teams: 1, rank_xpts: 1 }), null);
  assert.equal(opponentLine({ rank_xpts: 19, n_teams: 20, tier: "bottom", xg_pg: 1.04, xga_pg: 2.0 }), "19th of 20 by expected points (bottom-third side). It scores 1.0 and concedes 2.0 xG a game.");
  assert.match(opponentLine(null), /not known/);
});

test("counts and rates are bars from zero; shares, ratings and distances are dots", () => {
  assert.ok(isZeroBased({ unit: "per90" }) && isZeroBased({ unit: "total" }) && isZeroBased({ unit: "share", signed: true }));
  assert.ok(!isZeroBased({ unit: "share" }) && !isZeroBased({ unit: "rating" }) && !isZeroBased({ unit: "metres" }) && !isZeroBased(null));
});

test("a bounded metric's axis never leaves the values it can take", () => {
  assert.deepEqual(metricBounds({ unit: "share" }), { lo: 0, hi: 1 });
  assert.deepEqual(metricBounds({ unit: "rating" }), { lo: 0, hi: 10 });
  assert.deepEqual(metricBounds({ unit: "score" }), { lo: 0, hi: 100 });
  assert.deepEqual(metricBounds({ unit: "metres" }), { lo: 0, hi: Infinity });
  assert.deepEqual(metricBounds({ unit: "per90", signed: true }), { lo: -Infinity, hi: Infinity });
});

test("a match's number is faded by how little stands behind it, and says so when it is thin", () => {
  assert.deepEqual(reliability(RATE, 90, 90), { alpha: 1, thin: false, note: null });
  assert.equal(reliability(RATE, 45, 45).alpha, 0.75);
  const cameo = reliability(RATE, 12, 12);
  assert.ok(cameo.thin && cameo.alpha === 0.3 && cameo.note === "Only 12 minutes behind this number, so it says little on its own.");
  assert.equal(reliability(SHARE, 3, 90).note, "Only 3 attempts behind this number, so it says little on its own.");
  assert.equal(reliability(SHARE, 1, 90).note, "Only 1 attempt behind this number, so it says little on its own.");
  assert.equal(reliability(SHARE, 40, 90).thin, false);
  assert.deepEqual(reliability({ unit: "total", shape: "plain" }, null, 5), { alpha: 1, thin: false, note: null });
  assert.equal(reliability({ unit: "rating", shape: "plain" }, null, 10).thin, true);
});

test("a match moves the season line only when he played and the metric has a number for it", () => {
  const moved = changes([null, 1, 1, 1.5, 1.5, 1.2], [null, 1, null, 2, null, 0.5]);
  assert.deepEqual(moved.slice(0, 5), [null, null, null, 0.5, null]);              // the first appearance has nothing to move from
  assert.ok(Math.abs(moved[5] - -0.3) < 1e-9);
});

test("changes are written to one more digit than the metric, in points for a share, and tiny ones read as zero", () => {
  assert.equal(deltaText(RATE, 0.04), "+0.04");
  assert.equal(deltaText({ ...RATE, decimals: 2 }, -0.0312), "−0.031");
  assert.equal(deltaText(SHARE, -0.003), "−0.3 pts");
  assert.equal(deltaText(SHARE, 0.0004), "0.0 pts");
  assert.equal(deltaText(RATE, null), "–");
  assert.ok(isFlat(SHARE, 0.0004) && !isFlat(SHARE, -0.003) && isFlat(RATE, 0.001) && !isFlat(RATE, 0.04));
});

test("the axis follows the bars, until a few freak matches would flatten the rest of the season", () => {
  assert.deepEqual(axisRange([1, 2, 3], { lo: 0, hi: 2 }), { lo: 0, hi: 3, clipHigh: false, clipLow: false });                    // too few matches to call anything an outlier
  const season = [0.1, 0.2, 0.15, 0.3, 0.25, 0.2, 0.1, 0.35, 0.3, 0.2, 0.4, 0.15];
  assert.equal(axisRange(season, { lo: 0, hi: 0.3 }).clipHigh, false);
  const freak = axisRange([...season, 3.2], { lo: 0, hi: 0.3 });
  assert.ok(freak.clipHigh && freak.hi < 1 && freak.hi >= 0.3 * 1.35);                                                           // stops near the ordinary tall bars, not at 3.2
  assert.ok(!axisRange([...season, 0.55], { lo: 0, hi: 0.3 }).clipHigh);                                                          // a merely tall bar is not clipped
  const signed = axisRange([0.5, 0.4, 0.3, 0.2, 0.1, -0.1, -0.2, -0.3, -0.2, -3], { lo: -0.2, hi: 0.3 });
  assert.ok(signed.clipLow && signed.lo > -3);
});

test("the form sentence follows the metric's direction, and says 'in line' when nothing moved", () => {
  const rising = payloadOf([[1, "mid"], [1, "mid"], [1, "mid"], [1, "mid"], [1, "mid"], [1, "mid"], [1, "mid"], [3, "mid"], [3, "mid"], [3, "mid"], [3, "mid"], [3, "mid"]]);
  const good = readTrend(rising, "shots90", RATE).find((r) => r.kind === "form");
  assert.match(good.text, /^Over his last 5 appearances he is at 3\.0, above his season figure of 1\.[0-9]\.$/);
  assert.equal(good.tone, "good");
  assert.equal(readTrend(rising, "fouls90", FOULS).length, 0);                                                      // a metric the payload does not hold says nothing
  assert.equal(readTrend({ ...rising, series: { fouls90: rising.series.shots90 } }, "fouls90", FOULS).find((r) => r.kind === "form").tone, "bad");
  const flat = payloadOf(Array.from({ length: 12 }, () => [2, "mid"]));
  const same = readTrend(flat, "shots90", RATE).find((r) => r.kind === "form");
  assert.equal(same.tone, null);
  assert.match(same.text, /are in line with his season figure/);
  assert.equal(readTrend(payloadOf([[2, "mid"], [2, "mid"], [2, "mid"]]), "shots90", RATE).length, 0);               // three matches: no recent form to speak of
});

test("a share is 'the same' within two points, not within eight percent of itself", () => {
  const rows = [...Array.from({ length: 8 }, () => [0.8, "mid"]), ...Array.from({ length: 5 }, () => [0.86, "mid"])];
  const near = payloadOf(rows.map(([v, t]) => [v > 0.82 ? 0.81 : v, t]), { key: "pass_acc" });
  assert.match(readTrend(near, "pass_acc", SHARE).find((r) => r.kind === "form").text, /in line/);
  const apart = payloadOf(rows, { key: "pass_acc" });
  assert.match(readTrend(apart, "pass_acc", SHARE).find((r) => r.kind === "form").text, /above his season figure/);
});

test("what he does against strong and weak sides is reported, with the lesson only where more is better, and with a warning on small samples", () => {
  const splits = { tier: { top: { matches: 3, minutes: 270, v: { shots90: 1 } }, mid: { matches: 6, minutes: 540, v: { shots90: 2 } }, bottom: { matches: 3, minutes: 270, v: { shots90: 3 } } } };
  const p = payloadOf(Array.from({ length: 12 }, (_, i) => [2, i < 3 ? "top" : i < 9 ? "mid" : "bottom"]), { splits });
  const got = readTrend(p, "shots90", RATE).find((r) => r.kind === "opponents");
  assert.match(got.text, /^Against the top third of the league \(3 matches\) he is at 1\.0; against the bottom third \(3 matches\), at 3\.0\. He produces more of it against weaker sides, so part of his season figure comes from easier opponents\. Few matches stand behind each figure, so take it as a hint\.$/);
  const neutral = readTrend({ ...p, series: { fouls90: p.series.shots90 }, splits: { tier: { top: { ...splits.tier.top, v: { fouls90: 1 } }, bottom: { ...splits.tier.bottom, v: { fouls90: 3 } } } } }, "fouls90", FOULS).find((r) => r.kind === "opponents");
  assert.match(neutral.text, /It is higher against weaker sides\./);
  assert.doesNotMatch(neutral.text, /easier opponents/);
  const stronger = { tier: { top: { matches: 5, minutes: 450, v: { shots90: 3 } }, bottom: { matches: 5, minutes: 450, v: { shots90: 1 } } } };
  assert.match(readTrend({ ...p, splits: stronger }, "shots90", RATE).find((r) => r.kind === "opponents").text, /which makes his season figure more impressive\. *$/);
  const alike = { tier: { top: { matches: 5, minutes: 450, v: { shots90: 2 } }, bottom: { matches: 5, minutes: 450, v: { shots90: 2.1 } } } };
  assert.match(readTrend({ ...p, splits: alike }, "shots90", RATE).find((r) => r.kind === "opponents").text, /hardly changes with the strength of the opponent\.$/);
  const thin = { tier: { top: { matches: 1, minutes: 90, v: { shots90: 3 } }, bottom: { matches: 5, minutes: 450, v: { shots90: 1 } } } };
  assert.equal(readTrend({ ...p, splits: thin }, "shots90", RATE).some((r) => r.kind === "opponents"), false);          // one match against the top is not a comparison
});

test("home and away are compared only with enough matches", () => {
  const venue = { home: { matches: 8, minutes: 700, v: { shots90: 3 } }, away: { matches: 7, minutes: 600, v: { shots90: 1.5 } } };
  const p = payloadOf(Array.from({ length: 12 }, () => [2, "mid"]), { splits: { venue } });
  assert.match(readTrend(p, "shots90", RATE).find((r) => r.kind === "venue").text, /^At home he is at 3\.0 \(8 matches\), away at 1\.5 \(7 matches\)\. That is clearly higher at home\.$/);
  const few = { venue: { home: { matches: 2, minutes: 180, v: { shots90: 3 } }, away: venue.away } };
  assert.equal(readTrend({ ...p, splits: few }, "shots90", RATE).some((r) => r.kind === "venue"), false);
});

test("his highest and lowest matches are named, and a run against one kind of opponent is called out", () => {
  const rows = [[0.5, "top"], [0.7, "top"], [2.5, "bottom"], [2.9, "bottom"], [1.0, "mid"], [1.2, "mid"], [3.1, "bottom"], [1.1, "mid"], [0.6, "top"], [1.4, "mid"]];
  const got = readTrend(payloadOf(rows), "shots90", RATE).find((r) => r.kind === "extremes");
  assert.equal(got.text, "His highest was 3.1 v C06, his lowest 0.5 v C00. All three of his highest came against bottom-third sides. All three of his lowest came against top-third sides.");
  const mixed = [[0.5, "top"], [0.7, "mid"], [2.5, "bottom"], [2.9, "mid"], [1.0, "mid"], [1.2, "mid"], [3.1, "top"], [1.1, "mid"], [0.6, "bottom"], [1.4, "mid"]];
  assert.doesNotMatch(readTrend(payloadOf(mixed), "shots90", RATE).find((r) => r.kind === "extremes").text, /All three/);
});

test("a ten-minute cameo is never his 'highest' match", () => {
  const rows = [[1, "mid"], [1.2, "mid"], [0.9, "mid"], [1.1, "mid"], [1, "mid"], [1.3, "mid"], [0.8, "mid"], [9, "mid", 8]];
  const text = readTrend(payloadOf(rows), "shots90", RATE).find((r) => r.kind === "extremes").text;
  assert.match(text, /^His highest was 1\.3 /);
});

test("the matches that moved the season figure most are named", () => {
  const rows = [[1, "mid"], [1, "mid"], [1, "mid"], [3, "mid"], [1, "mid"], [1, "mid"], [0, "mid"], [1, "mid"], [1, "mid"]];
  const got = readTrend(payloadOf(rows), "shots90", RATE).find((r) => r.kind === "movers");
  assert.match(got.text, /^The match that lifted his season figure most was at C03 \(\+[0-9.]+\), and the one that pulled it down most was v C06 \(−[0-9.]+\)\.$/);
});

test("matches are named by venue and opponent, and results from his side", () => {
  assert.equal(versus({ home: true, opp_short: "ARS" }), "v ARS");
  assert.equal(versus({ home: false, opp: "Arsenal" }), "at Arsenal");
  assert.equal(resultText({ result: "w", gf: 2, ga: 0 }), "W 2–0");
  assert.equal(resultText({ result: "l", gf: 0, ga: 1 }), "L 0–1");
  assert.equal(resultText({ result: null, gf: null, ga: null }), null);
});

test("the quick picks are the metrics that define his role, as far as the trend has them", () => {
  const cat = {
    profile: { full: { MID: ["xa90", "kp90", "xgchain90", "gone90", "xa90"], GK: [] }, role: { MID: ["npxg90", "kp90"] } },
    order: ["saves", "save_pct", "npxg90", "xa90"], metrics: { saves: { group: "goalkeeping" }, save_pct: { group: "goalkeeping" }, npxg90: { group: "shooting" }, xa90: { group: "shooting" } },
  };
  const have = new Set(["xa90", "kp90", "xgchain90", "npxg90", "saves", "save_pct"]);
  assert.deepEqual(quickPicks(cat, "MID", have, [...have]), ["xa90", "kp90", "xgchain90", "npxg90"]);            // listed order, no repeats, nothing the trend lacks
  assert.deepEqual(quickPicks(cat, "GK", have, [...have]), ["saves", "save_pct"]);                              // no list for goalkeepers: their own group
  assert.deepEqual(quickPicks(cat, "ATT", new Set(["a", "b"]), ["a", "b"]), ["a", "b"]);                         // nothing known: the first metrics there are
  assert.deepEqual(quickPicks(null, "MID", have, ["xa90"]), ["xa90"]);
});
