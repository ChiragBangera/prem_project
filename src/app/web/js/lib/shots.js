// Shots, the same at every level (a match, a player, a team): one shape, one set of words, one way to filter, order and add them up.
//
// A shot here is { id, x, y, xg, result, minute, player, player_id, situation, type, assisted_by, last_action, side } with x and y from 0 to 1
// toward the goal attacked, and, where the list spans several matches, { match_id, date, opponent, home }. xg is null when the source has no
// figure for the shot (a match read before Understat has published it): it is then never counted as zero.

export const RESULT_WORD = { Goal: "Goal", SavedShot: "Saved", BlockedShot: "Blocked", MissedShots: "Off target", ShotOnPost: "Hit the post", OwnGoal: "Own goal" };
export const SITUATION_WORD = { OpenPlay: "Open play", FromCorner: "From a corner", SetPiece: "Set piece", DirectFreekick: "Direct free kick", Penalty: "Penalty" };
const BODY_WORD = { RightFoot: "Right foot", LeftFoot: "Left foot", Head: "Header", OtherBodyPart: "Other body part" };
const spaced = (t) => String(t || "").replace(/([a-z])([A-Z])/g, "$1 $2");

export const resultWord = (r) => RESULT_WORD[r] || spaced(r);
export const situationWord = (s) => SITUATION_WORD[s] || spaced(s);
export const bodyWord = (t) => BODY_WORD[t] || spaced(t);
/** What the taker did, or was given, just before the shot. Understat writes "None" and "Standard" where it has nothing to say. */
export const lastActionWord = (a) => (!a || a === "None" || a === "Standard" ? null : spaced(a).replace(/^./, (c) => c.toUpperCase()));

const ON_TARGET = new Set(["Goal", "SavedShot"]);
export const isGoal = (s) => s.result === "Goal";
export const onTarget = (s) => ON_TARGET.has(s.result);

/** Circle radius in metres on the pitch: area grows with xG. One size for a shot with no xG. */
export const shotRadius = (xg) => (xg == null ? 1.5 : 0.7 + Math.sqrt(Math.max(0, xg)) * 2.1);

/** How a shot is drawn: "goal" (solid, dark rim), "on" (saved: half filled), "off" (faint); "noxg" is added when there is no xG for it. */
export const shotLook = (s) => (isGoal(s) ? "goal" : s.result === "SavedShot" ? "on" : "off") + (s.xg == null ? " noxg" : "");

export const SHOT_SITUATIONS = [
  { value: "all", label: "All shots", test: () => true },
  { value: "open", label: "Open play", test: (s) => s.situation === "OpenPlay" },
  { value: "corner", label: "Corners", test: (s) => s.situation === "FromCorner" },
  { value: "set", label: "Free kicks", test: (s) => s.situation === "SetPiece" || s.situation === "DirectFreekick" },
  { value: "pen", label: "Penalties", test: (s) => s.situation === "Penalty" },
];

export const SHOT_RESULTS = [
  { value: "all", label: "Every result", test: () => true },
  { value: "target", label: "On target", test: onTarget },
  { value: "goals", label: "Goals", test: isGoal },
];

/** The taker of a shot as one key: the same man on the other side of the list is someone else. */
export const takerKey = (s) => `${s.side ?? 0}:${s.player_id > 0 ? s.player_id : s.player}`;

/** The shots that pass every filter given. `side` is 0, 1 or null for both; `taker` a takerKey or null. */
export function filterShots(list, { side = null, taker = null, situation = "all", result = "all" } = {}) {
  const sit = (SHOT_SITUATIONS.find((x) => x.value === situation) || SHOT_SITUATIONS[0]).test;
  const res = (SHOT_RESULTS.find((x) => x.value === result) || SHOT_RESULTS[0]).test;
  return (list || []).filter((s) => (side == null || (s.side ?? 0) === side) && (taker == null || takerKey(s) === taker) && sit(s) && res(s));
}

/**
 * Shots, goals, on target and xG of a list. xG is the sum over the shots that have one, with `known` saying how many that is: null when
 * none has, and `per` (xG per shot) only when every shot has.
 */
export function shotTotals(list) {
  const known = list.filter((s) => s.xg != null);
  const xg = known.length ? known.reduce((a, s) => a + s.xg, 0) : null;
  return { n: list.length, goals: list.filter(isGoal).length, on_target: list.filter(onTarget).length, xg, known: known.length,
    per: list.length && known.length === list.length ? xg / list.length : null };
}

/** Everyone who took a shot, most shots first (then most xG, then name). */
export function shotTakers(list) {
  const out = new Map();
  for (const s of list || []) {
    if (!s.player) continue;
    const key = takerKey(s);
    const t = out.get(key) || { key, name: s.player, side: s.side ?? 0, player_id: s.player_id, n: 0, goals: 0, xg: null };
    t.n += 1; t.goals += isGoal(s) ? 1 : 0;
    if (s.xg != null) t.xg = (t.xg || 0) + s.xg;
    out.set(key, t);
  }
  return [...out.values()].sort((a, b) => b.n - a.n || (b.xg || 0) - (a.xg || 0) || a.name.localeCompare(b.name));
}

/** "time": as they came (by match date, then minute). "xg": the best chance first, shots with no xG last in the order they came. */
export function orderShots(list, by = "time") {
  const time = (a, b) => String(a.date || "").localeCompare(String(b.date || "")) || (a.match_id || 0) - (b.match_id || 0) || a.minute - b.minute || String(a.id).localeCompare(String(b.id), undefined, { numeric: true });
  const out = [...(list || [])];
  if (by === "xg") return out.sort((a, b) => (a.xg == null) - (b.xg == null) || (b.xg ?? 0) - (a.xg ?? 0) || time(a, b));
  return out.sort(time);
}

/** One row of /api/team/shots ([x, y, xg, result, minute, player, situation, body part, match, player id, assist, last action]) as a shot. */
export function teamShot(row, index, side, games = {}) {
  const g = games[row[8]] || {};
  return { id: `${side}-${index}`, x: row[0], y: row[1], xg: row[2], result: row[3], minute: row[4], player: row[5], situation: row[6], type: row[7],
    match_id: row[8], player_id: row[9] ?? null, assisted_by: row[10] ?? null, last_action: row[11] ?? null, side,
    date: g.date ?? null, opponent: g.opponent ?? null, home: g.home ?? null };
}
