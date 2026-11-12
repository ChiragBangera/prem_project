// What the Match page works out from a match's event rows (/api/match/:id/centre): the numbers of the whole match or of one half, who had
// the upper hand minute by minute, where each side played, who passed to whom. Pure functions: no drawing, no network, so they are tested.
//
// Row layouts (see app/analytics/match_centre.py). Positions are tenths of the pitch (0-1000), each team attacking left to right.
//   touch   [tm, period, minute, x, y, player]
//   pass    [tm, period, minute, x, y, endX, endY, ok, flags, player, receiver]
//   def     [tm, period, minute, x, y, kind, ok, player]
//   takeon  [tm, period, minute, x, y, ok, player]
//   carry   [tm, period, minute, x0, y0, x1, y1, progressive, player]
//   foul    [tm, period, minute, x, y, player]

export const PF = { PROG: 1, KEY: 2, BOX: 4, F3: 8, LONG: 16, CROSS: 32, THROUGH: 64, ASSIST: 128, RESTART: 256, CORNER: 512, FREEKICK: 1024 };
export const DK = { TACKLE: 1, INTERCEPT: 2, CLEAR: 3, BLOCK_PASS: 4, BLOCK_SHOT: 5, RECOVER: 6, BEATEN: 7, AERIAL: 8 };
export const NX = 24, NY = 16;
export const FINAL_THIRD = 667, BOX_X = 833, BOX_Y0 = 211, BOX_Y1 = 789, HIGH = 600;

const inPeriod = (period) => (period === "all" || period == null ? () => true : (row) => row[1] === Number(period));
export const inBox = (x, y) => x >= BOX_X && y >= BOX_Y0 && y <= BOX_Y1;
const ON_TARGET = new Set(["Goal", "SavedShot"]);
const share = (a, b) => (a + b ? (100 * a) / (a + b) : null);

/** The rows of one period ("all", 1 or 2), and optionally of one team and one player. */
export function pick(rows, { period = "all", tm = null, player = null, playerIndex } = {}) {
  const keep = inPeriod(period);
  const at = playerIndex ?? (rows[0] ? rows[0].length - 1 : 0);
  return (rows || []).filter((r) => keep(r) && (tm == null || r[0] === tm) && (player == null || r[at] === player));
}

export const pickShots = (shots, { period = "all", tm = null, player = null } = {}) =>
  (shots || []).filter((s) => (period === "all" || s.pe === Number(period)) && (tm == null || s.tm === tm) && (player == null || s.p === player));

/** Both sides' numbers for a period, home first. Every entry is a count unless its name says otherwise; null where it cannot be worked out. */
export function teamStats(c, period = "all") {
  const touches = pick(c.touches, { period }), passes = pick(c.passes, { period }), defs = pick(c.def, { period });
  const carries = pick(c.carries, { period }), takeons = pick(c.takeons, { period }), fouls = pick(c.fouls, { period });
  const shots = pickShots(c.shots, { period });
  const out = [0, 1].map((tm) => {
    const p = passes.filter((r) => r[0] === tm && !(r[8] & PF.RESTART));
    const ok = p.filter((r) => r[7]);
    const t = touches.filter((r) => r[0] === tm);
    const d = defs.filter((r) => r[0] === tm);
    const s = shots.filter((x) => x.tm === tm);
    const kind = (k, won) => d.filter((r) => r[5] === k && (won == null || Boolean(r[6]) === won)).length;
    const aerials = d.filter((r) => r[5] === DK.AERIAL);
    const xgKnown = s.length > 0 && s.every((x) => x.xg != null);
    return {
      touches: t.length, passes: p.length, pass_ok: ok.length, pass_acc: p.length ? (100 * ok.length) / p.length : null,
      f3_touches: t.filter((r) => r[3] >= FINAL_THIRD).length, box_touches: t.filter((r) => inBox(r[3], r[4])).length,
      f3_entries: ok.filter((r) => r[8] & PF.F3).length + carries.filter((r) => r[0] === tm && r[3] < FINAL_THIRD && r[5] >= FINAL_THIRD).length,
      box_entries: ok.filter((r) => r[8] & PF.BOX).length + carries.filter((r) => r[0] === tm && !inBox(r[3], r[4]) && inBox(r[5], r[6])).length,
      prog_passes: ok.filter((r) => r[8] & PF.PROG).length, prog_carries: carries.filter((r) => r[0] === tm && r[7]).length,
      key_passes: p.filter((r) => r[8] & PF.KEY).length, crosses: p.filter((r) => r[8] & PF.CROSS).length,
      long_balls: p.filter((r) => r[8] & PF.LONG).length, long_share: p.length ? (100 * p.filter((r) => r[8] & PF.LONG).length) / p.length : null,
      takeons: takeons.filter((r) => r[0] === tm).length, takeons_won: takeons.filter((r) => r[0] === tm && r[5]).length,
      shots: s.length, on_target: s.filter((x) => ON_TARGET.has(x.result)).length, goals: s.filter((x) => x.result === "Goal").length,
      big_chances: s.filter((x) => x.big).length, box_shots: s.filter((x) => inBox(x.x, x.y)).length,
      xg: xgKnown ? s.reduce((a, x) => a + x.xg, 0) : null,
      tackles: kind(DK.TACKLE), tackles_won: kind(DK.TACKLE, true), interceptions: kind(DK.INTERCEPT), clearances: kind(DK.CLEAR),
      recoveries: kind(DK.RECOVER), high_regains: d.filter((r) => r[5] === DK.RECOVER && r[3] >= HIGH).length, blocks: kind(DK.BLOCK_SHOT) + kind(DK.BLOCK_PASS),
      aerials: aerials.length, aerials_won: aerials.filter((r) => r[6]).length,
      fouls: fouls.filter((r) => r[0] === tm).length,
      // pressing actions in the attacking 60% of the pitch: what PPDA divides by
      press: d.filter((r) => (r[5] === DK.TACKLE || r[5] === DK.INTERCEPT || r[5] === DK.BEATEN) && r[3] >= 400).length + fouls.filter((r) => r[0] === tm && r[3] >= 400).length,
      own_build: p.filter((r) => r[3] < HIGH).length,   // this side's passes in its own 60%: what the other side's PPDA counts
      def_height: (() => { const h = d.filter((r) => r[5] === DK.TACKLE || r[5] === DK.INTERCEPT || r[5] === DK.BEATEN || r[5] === DK.BLOCK_PASS); return h.length >= 5 ? h.reduce((a, r) => a + r[3], 0) / h.length / 10 * 1.05 : null; })(),
    };
  });
  out.forEach((s, tm) => {
    const o = out[1 - tm];
    s.possession = share(s.passes, o.passes);
    s.tilt = share(s.f3_touches, o.f3_touches);
    s.ppda = s.press ? o.own_build / s.press : null;
    s.aerial_pct = s.aerials ? (100 * s.aerials_won) / s.aerials : null;
  });
  return out;
}

/**
 * Who was on top, minute by minute. A side's pressure in a minute is its touches in the final third, a touch in the box counting three and
 * a shot six: plain counting, no model. Returned smoothed over `window` minutes (centred), one entry per clock minute from 0 to the end.
 */
export function momentum(c, { window = 5 } = {}) {
  const end = Math.max(1, c.clock?.end || 0);
  const raw = [new Array(end + 1).fill(0), new Array(end + 1).fill(0)];
  for (const r of c.touches || []) {
    if (r[3] < FINAL_THIRD) continue;
    raw[r[0]][Math.min(end, r[2])] += inBox(r[3], r[4]) ? 3 : 1;
  }
  for (const s of c.shots || []) raw[s.tm][Math.min(end, s.em)] += 6;
  const half = Math.floor(window / 2);
  const ht = c.clock?.ht ?? end;
  const smooth = (arr) => arr.map((_, i) => {
    // a window never reaches across half time: the second half starts from nothing, as the match does
    const lo = Math.max(i <= ht ? 0 : ht + 1, i - half), hi = Math.min(i <= ht ? ht : end, i + half);
    let sum = 0;
    for (let k = lo; k <= hi; k++) sum += arr[k];
    return sum / (hi - lo + 1);
  });
  const home = smooth(raw[0]), away = smooth(raw[1]);
  return { minutes: home.map((_, i) => i), home, away, net: home.map((v, i) => v - away[i]), max: Math.max(1, ...home, ...away), raw };
}

/** The match cut into blocks of `size` minutes (each half on its own, stoppage time joining the last block of its half): possession and field tilt in each. */
export function blocks(c, size = 15) {
  const ht = c.clock?.ht ?? 45, end = c.clock?.end ?? 90, from2 = c.clock?.second_from ?? ht + 1;
  const spans = [];
  const cut = (period, start, stop, base) => {
    for (let k = 0; k < 3; k++) {
      const a = start + k * size, b = k === 2 ? stop : Math.min(stop, start + (k + 1) * size - 1);
      if (a > stop) break;
      spans.push({ period, from: a, to: b, label: `${base + k * size + 1}–${base + (k + 1) * size}${k === 2 && b - a + 1 > size ? "+" : ""}` });
    }
  };
  cut(1, 0, ht, 0);
  if (end > ht) cut(2, from2, end, 45);
  return spans.map((sp) => {
    const within = (r) => r[1] === sp.period && r[2] >= sp.from && r[2] <= sp.to;
    const passes = [0, 1].map((tm) => (c.passes || []).filter((r) => r[0] === tm && within(r) && !(r[8] & PF.RESTART)).length);
    const f3 = [0, 1].map((tm) => (c.touches || []).filter((r) => r[0] === tm && within(r) && r[3] >= FINAL_THIRD).length);
    const shots = [0, 1].map((tm) => (c.shots || []).filter((s) => s.tm === tm && s.pe === sp.period && s.em >= sp.from && s.em <= sp.to).length);
    return { ...sp, possession: share(passes[0], passes[1]), tilt: share(f3[0], f3[1]), shots, passes };
  });
}

/** Counts per cell (NX by NY, row-major) of rows' start positions. */
export function grid(rows, xi = 3, yi = 4) {
  const g = new Array(NX * NY).fill(0);
  for (const r of rows) {
    const cx = Math.min(NX - 1, Math.max(0, Math.floor((r[xi] * NX) / 1001)));
    const cy = Math.min(NY - 1, Math.max(0, Math.floor((r[yi] * NY) / 1001)));
    g[cy * NX + cx] += 1;
  }
  return g;
}

/**
 * A side's pass network: each player at the average position of his touches, and the passes between each pair (either way).
 * `starters` keeps the eleven who started and stops at the first substitution, the usual way to show the shape a side set out in.
 */
export function network(c, tm, { period = "all", starters = false, minEdge = 2, minTouches = 3 } = {}) {
  const team = c.teams?.[tm];
  let until = Infinity, allowed = null;
  if (starters && team) {
    allowed = new Set(team.players.filter((p) => p.start).map((p) => p.id));
    const subs = (c.timeline || []).filter((t) => t.tm === tm && t.kind === "sub").map((t) => t.em);
    const reds = (c.timeline || []).filter((t) => t.tm === tm && t.kind === "red").map((t) => t.em);
    until = Math.min(Infinity, ...subs, ...reds);
  }
  const keep = (r, pid) => r[2] < until && (!allowed || allowed.has(pid));
  const nodes = new Map();
  for (const r of pick(c.touches, { period, tm })) {
    if (!r[5] || !keep(r, r[5])) continue;
    const n = nodes.get(r[5]) || { id: r[5], name: c.names?.[r[5]] || "", x: 0, y: 0, touches: 0 };
    n.x += r[3]; n.y += r[4]; n.touches += 1;
    nodes.set(r[5], n);
  }
  const pairs = new Map();
  let total = 0;
  for (const r of pick(c.passes, { period, tm })) {
    if (!r[7] || !r[10] || r[8] & PF.RESTART || !keep(r, r[9]) || (allowed && !allowed.has(r[10]))) continue;
    const a = Math.min(r[9], r[10]), b = Math.max(r[9], r[10]);
    const key = a + ":" + b;
    pairs.set(key, (pairs.get(key) || 0) + 1);
    total += 1;
  }
  const outNodes = [...nodes.values()].filter((n) => n.touches >= minTouches).map((n) => ({ ...n, x: Math.round(n.x / n.touches), y: Math.round(n.y / n.touches) }));
  const ids = new Set(outNodes.map((n) => n.id));
  const edges = [...pairs.entries()].map(([k, n]) => { const [a, b] = k.split(":").map(Number); return { a, b, n }; })
    .filter((e) => e.n >= minEdge && ids.has(e.a) && ids.has(e.b)).sort((x, y) => y.n - x.n);
  return { nodes: outNodes.sort((a, b) => b.touches - a.touches), edges, matches: 1, passes: total, until: Number.isFinite(until) ? until : null };
}

/** Where a side attacked: its final-third touches split across the left, centre and right of the pitch (its own left at index 0), as shares. */
export function channels(c, tm, period = "all") {
  const parts = [0, 0, 0];
  for (const r of pick(c.touches, { period, tm })) {
    if (r[3] >= FINAL_THIRD) parts[r[4] < 333 ? 0 : r[4] < 667 ? 1 : 2] += 1;
  }
  const total = parts[0] + parts[1] + parts[2];
  return { counts: parts, shares: parts.map((v) => (total ? (100 * v) / total : 0)), total };
}

/** One line per player who touched the ball: the counts a person reads during a match. */
export function playerRows(c, period = "all") {
  const rows = new Map();
  const of = (pid, tm) => {
    if (!pid) return null;
    if (!rows.has(pid)) rows.set(pid, { id: pid, tm, name: c.names?.[pid] || "", touches: 0, passes: 0, pass_ok: 0, prog_passes: 0, key_passes: 0, f3_passes: 0, box_touches: 0,
      prog_carries: 0, takeons: 0, takeons_won: 0, tackles_won: 0, interceptions: 0, recoveries: 0, clearances: 0, aerials: 0, aerials_won: 0, shots: 0, on_target: 0, goals: 0, xg: null, fouls: 0 });
    return rows.get(pid);
  };
  for (const r of pick(c.touches, { period })) { const p = of(r[5], r[0]); if (p) { p.touches += 1; if (inBox(r[3], r[4])) p.box_touches += 1; } }
  for (const r of pick(c.passes, { period })) {
    const p = of(r[9], r[0]);
    if (!p || r[8] & PF.RESTART) continue;
    p.passes += 1; p.pass_ok += r[7] ? 1 : 0;
    if (r[7] && r[8] & PF.PROG) p.prog_passes += 1;
    if (r[8] & PF.KEY) p.key_passes += 1;
    if (r[7] && r[8] & PF.F3) p.f3_passes += 1;
  }
  for (const r of pick(c.carries, { period })) { const p = of(r[8], r[0]); if (p && r[7]) p.prog_carries += 1; }
  for (const r of pick(c.takeons, { period })) { const p = of(r[6], r[0]); if (p) { p.takeons += 1; p.takeons_won += r[5] ? 1 : 0; } }
  for (const r of pick(c.def, { period })) {
    const p = of(r[7], r[0]);
    if (!p) continue;
    if (r[5] === DK.TACKLE && r[6]) p.tackles_won += 1;
    else if (r[5] === DK.INTERCEPT) p.interceptions += 1;
    else if (r[5] === DK.RECOVER) p.recoveries += 1;
    else if (r[5] === DK.CLEAR) p.clearances += 1;
    else if (r[5] === DK.AERIAL) { p.aerials += 1; p.aerials_won += r[6] ? 1 : 0; }
  }
  for (const r of pick(c.fouls, { period })) { const p = of(r[5], r[0]); if (p) p.fouls += 1; }
  for (const s of pickShots(c.shots, { period })) {
    const p = of(s.p, s.tm);
    if (!p) continue;
    p.shots += 1; p.on_target += ON_TARGET.has(s.result) ? 1 : 0; p.goals += s.result === "Goal" ? 1 : 0;
    if (s.xg != null) p.xg = (p.xg || 0) + s.xg;
  }
  return [...rows.values()].map((p) => ({ ...p, pass_acc: p.passes ? (100 * p.pass_ok) / p.passes : null, def_actions: p.tackles_won + p.interceptions + p.recoveries + p.clearances }));
}

const LEADER_BOARDS = [
  { key: "touches", label: "Touches" }, { key: "prog_passes", label: "Progressive passes" }, { key: "key_passes", label: "Chances created" },
  { key: "prog_carries", label: "Progressive carries" }, { key: "takeons_won", label: "Take-ons won" }, { key: "box_touches", label: "Touches in the box" },
  { key: "recoveries", label: "Ball recoveries" }, { key: "def_actions", label: "Defensive actions" }, { key: "aerials_won", label: "Aerial duels won" },
];

/** Who led the match at what: for each board, the top `n` players of both sides together (ties broken by touches). Boards nobody scored on are left out. */
export function leaders(c, period = "all", n = 3) {
  const rows = playerRows(c, period);
  return LEADER_BOARDS.map((b) => ({ ...b, top: rows.filter((r) => r[b.key] > 0).sort((x, y) => y[b.key] - x[b.key] || y.touches - x.touches).slice(0, n).map((r) => ({ id: r.id, tm: r.tm, name: r.name, value: r[b.key] })) }))
    .filter((b) => b.top.length);
}

/** The minute a row happened as a person says it: "45+2′" in first-half stoppage time, "90+4′" at the end. `mi` is the 0-based match minute. */
export function minuteLabel(pe, mi) {
  const m = mi + 1;
  if (pe === 1 && m > 45) return `45+${m - 45}′`;
  if (pe === 2 && m > 90) return `90+${m - 90}′`;
  return `${m}′`;
}

/** The clock minute (continuous, stoppage included) as the match minute it is drawn at: second-half minutes start again at 45. */
export function axisMinute(c, em, pe) {
  const ht = c.clock?.ht ?? 45, from2 = c.clock?.second_from ?? ht + 1;
  return pe === 2 || em >= from2 ? 45 + (em - from2) : em;
}

// ------------------------------------------------------------------ moves (possessions)
//
// A move is one side's run of actions: c.possessions, see app/events/possessions.py.
//   move  { tm, pe, em, c0, c1, st, sp, sat, steps, n, end, lost, by, how, at, si, f3, box, keep, re }
//   step  [kind, player, x, y, endX, endY, ok, minute, flags]     (endX / endY only on a pass or a carry; -1 otherwise)

export const SK = { PASS: 0, CARRY: 1, TAKEON: 2, TOUCH: 3, SHOT: 4, WIN: 5, CLEAR: 6 };
export const SF = { CROSS: 1, LONG: 2, THROUGH: 4, KEY: 8, HEAD: 16, PROG: 32 };

/** How a move ended, in words, and which family the ending belongs to (the "Ended in" filter). */
export const MOVE_END = {
  goal: { label: "Goal", group: "goal", tone: "good" }, own_goal: { label: "Own goal", group: "goal", tone: "good" },
  shot_on: { label: "Shot on target", group: "shot" }, shot_off: { label: "Shot off target", group: "shot" }, shot_blocked: { label: "Shot blocked", group: "shot" },
  lost: { label: "Lost the ball", group: "lost" }, out: { label: "Out of play", group: "out" }, stopped: { label: "Play stopped", group: "out" },
  foul_won: { label: "Fouled", group: "stop" }, foul: { label: "Gave away a foul", group: "lost" }, offside: { label: "Offside", group: "lost" },
  whistle: { label: "Half ended", group: "stop" },
};
export const MOVE_START = {
  kickoff: "Kick-off", throw_in: "Throw-in", goal_kick: "Goal kick", corner: "Corner", free_kick: "Free kick", penalty: "Penalty", keeper: "From the keeper",
  tackle: "Tackle won", interception: "Interception", recovery: "Loose ball picked up", clearance: "Clearance", blocked_pass: "Blocked pass", loose: "Loose ball", open: "Open play",
};
/** What the opponent did to end a move, as it reads after the loser's name: "tackled by", "intercepted by" ... */
export const MOVE_BROKEN = {
  tackle: "tackled by", interception: "intercepted by", recovery: "picked up by", clearance: "cleared by", blocked_pass: "blocked by", keeper: "gathered by",
  touch: "taken by", took: "taken by", foul: "fouled by", own_goal: "put in by",
};
const SHOT_ENDS = new Set(["goal", "shot_on", "shot_off", "shot_blocked", "own_goal"]);

/** The moves of a period, optionally one side's, one kind of ending ("goal", "shot" = any shot, "lost", "out"), a minimum of completed passes, or only those that reached the box. */
export function pickMoves(c, { period = "all", tm = null, ended = "any", minPasses = 0, box = false, player = null } = {}) {
  return (c.possessions || []).filter((m) => (period === "all" || m.pe === Number(period)) && (tm == null || m.tm === tm) && m.n >= minPasses && (!box || m.box)
    && (ended === "any" || (ended === "shot" ? SHOT_ENDS.has(m.end) : MOVE_END[m.end]?.group === ended))
    && (player == null || m.steps.some((s) => s[1] === player)));
}

/** The shot a move ended in (from c.shots), or null. */
export const moveShot = (c, m) => (m.si == null ? null : c.shots?.[m.si] || null);

/** The players of a move in the order they first appear. */
export const movePlayers = (m) => [...new Set(m.steps.map((s) => s[1]).filter(Boolean))];

/** Both sides' moves in numbers for a period, home first. `xg` is null unless every shot that ended a move has one. */
export function moveStats(c, period = "all") {
  return [0, 1].map((tm) => {
    const rows = pickMoves(c, { period, tm });
    const shots = rows.filter((m) => SHOT_ENDS.has(m.end) && m.end !== "own_goal");
    const withPass = rows.filter((m) => m.n > 0);
    const xgs = shots.map((m) => moveShot(c, m)?.xg);
    return {
      moves: rows.length, passes_per: withPass.length ? withPass.reduce((a, m) => a + m.n, 0) / withPass.length : null,
      long: rows.filter((m) => m.n >= 10).length, longest: rows.reduce((a, m) => Math.max(a, m.n), 0),
      f3: rows.filter((m) => m.f3).length, box: rows.filter((m) => m.box).length, shots: shots.length, goals: rows.filter((m) => m.end === "goal").length,
      lost: rows.filter((m) => m.end === "lost").length, out: rows.filter((m) => m.end === "out" && !m.keep).length,
      shot_share: rows.length ? (100 * shots.length) / rows.length : null,
      xg: shots.length && xgs.every((v) => v != null) ? xgs.reduce((a, v) => a + v, 0) : null,
    };
  });
}

/** Who lost the ball most (the last player of a move the other side took, or that went out) and who broke up most moves, both sides together. */
export function moveLeaders(c, period = "all", n = 5) {
  const lost = new Map(), broke = new Map();
  const bump = (map, id, tm) => { if (id) map.set(id, { id, tm, name: c.names?.[id] || "", value: (map.get(id)?.value || 0) + 1 }); };
  for (const m of pickMoves(c, { period })) {
    if (m.lost && (m.end === "lost" || (m.end === "out" && !m.keep))) bump(lost, m.lost, m.tm);
    if (m.by && m.end === "lost") bump(broke, m.by, 1 - m.tm);
  }
  const top = (map) => [...map.values()].sort((a, b) => b.value - a.value || a.name.localeCompare(b.name)).slice(0, n);
  return { lost: top(lost), broke: top(broke) };
}

/** Where a side's moves were taken off it: [[x, y, how, loser, breaker, period, minute]] in that side's direction of attack. */
export function moveBreaks(c, tm, period = "all") {
  return pickMoves(c, { period, tm, ended: "lost" }).filter((m) => m.at && m.end === "lost").map((m) => [m.at[0], m.at[1], m.how, m.lost, m.by, m.pe, Math.floor(m.c1 / 60)]);
}

const lastName = (c, id) => { const parts = String(c.names?.[id] || "").trim().split(/\s+/); return parts[parts.length - 1] || "–"; };
const metres = (s) => Math.round(Math.hypot(((s[4] - s[2]) / 1000) * 105, ((s[5] - s[3]) / 1000) * 68));

/**
 * A move as numbered lines, one per action: `{ n, who, to, text, ok, kind }`. A carry has no number of its own (it is how the ball got from one
 * action to the next). `to` is the next player of the move after a completed pass: the data names no receiver.
 */
export function moveLines(c, m) {
  const lines = [];
  let n = 0;
  m.steps.forEach((s, i) => {
    const [kind, p, , , , , ok, , flags] = s;
    const who = lastName(c, p);
    if (kind === SK.CARRY) { lines.push({ n: null, kind, who, ok: true, text: `${who} carried it ${metres(s)} m` }); return; }
    n += 1;
    let text, to = null;
    if (kind === SK.PASS) {
      const next = m.steps.slice(i + 1).find((x) => x[1] && x[1] !== p);
      const sort = flags & SF.CROSS ? "cross" : flags & SF.THROUGH ? "through ball" : flags & SF.LONG ? "long ball" : flags & SF.HEAD ? "header" : "pass";
      if (ok && next) { to = lastName(c, next[1]); text = `${who} → ${to}${sort === "pass" ? "" : `, ${sort}`}`; }
      else if (ok) text = `${who}, ${sort} completed`;
      else text = `${who}, ${sort} not completed`;
    } else if (kind === SK.TAKEON) text = `${who} ${ok ? "beat his man" : "tried to beat his man"}`;
    else if (kind === SK.SHOT) text = `${who} shot`;
    else if (kind === SK.WIN) text = `${who} picked it up`;
    else if (kind === SK.CLEAR) text = `${who} cleared`;
    else text = `${who} ${ok ? "touch" : "lost control"}`;
    lines.push({ n, kind, who, to, ok: Boolean(ok), text, flags, step: i });
  });
  return lines;
}

/** One sentence on how the move ended: who lost it and who took it, where the data says. */
export function moveEnding(c, m) {
  const end = MOVE_END[m.end]?.label || m.end;
  const shot = moveShot(c, m);
  if (shot) return `${end}: ${lastName(c, shot.p)}${shot.xg != null ? `, ${shot.xg.toFixed(2)} xG` : ""}.`;
  if (m.end === "own_goal") return `Own goal${m.by ? ` by ${lastName(c, m.by)}` : ""}.`;
  if (m.end === "lost") return `${m.lost ? `Lost by ${lastName(c, m.lost)}` : "Lost"}${m.by ? `, ${MOVE_BROKEN[m.how] || "taken by"} ${lastName(c, m.by)}` : ""}.`;
  if (m.end === "out") return m.keep ? `Out of play${m.by ? ` off ${lastName(c, m.by)}` : ""}: they kept the ball.` : `${m.lost ? `${lastName(c, m.lost)} played it` : "Played"} out of play.`;
  if (m.end === "foul_won") return `Fouled${m.by ? ` by ${lastName(c, m.by)}` : ""}: free kick won.`;
  if (m.end === "foul") return `${m.lost ? `${lastName(c, m.lost)} gave away` : "Gave away"} a foul.`;
  return `${end}.`;
}

/** The clock a move began at, as "12:05". */
export const moveClock = (m) => `${Math.floor(m.c0 / 60)}:${String(m.c0 % 60).padStart(2, "0")}`;

/**
 * Volume against what came of it, per player: his progressive passes, progressive carries, take-ons won and crosses, and how many of each
 * were in a move that came to a shot (`m.ls`: the move's own shot, or one from the corner, free kick or penalty it won). The shot itself is
 * not counted. `n` and `shot` add the four kinds up. Players with nothing are left out; busiest first.
 */
export function playerOutcomes(c, period = "all") {
  const rows = new Map();
  const kindOf = (s) => (s[0] === SK.PASS && s[8] & SF.CROSS ? "crosses" : s[0] === SK.PASS && s[8] & SF.PROG ? "prog_passes"
    : s[0] === SK.CARRY && s[8] & SF.PROG ? "prog_carries" : s[0] === SK.TAKEON && s[6] ? "takeons_won" : null);
  for (const m of pickMoves(c, { period })) {
    for (const s of m.steps) {
      const kind = kindOf(s);
      if (!kind || !s[1]) continue;
      if (!rows.has(s[1])) rows.set(s[1], { id: s[1], tm: m.tm, name: c.names?.[s[1]] || "", n: 0, shot: 0, kinds: {} });
      const row = rows.get(s[1]);
      const k = (row.kinds[kind] ||= { n: 0, shot: 0 });
      row.n += 1; k.n += 1;
      if (m.ls) { row.shot += 1; k.shot += 1; }
    }
  }
  return [...rows.values()].sort((a, b) => b.n - a.n || b.shot - a.shot || a.name.localeCompare(b.name));
}
