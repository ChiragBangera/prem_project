"""What a team's or a player's moves add up to over a set of matches: how they end, where the ball is lost, who loses it, who wins it.

A *move* is a spell of possession as :mod:`app.events.possessions` builds it for the Match page's Moves tab. This module only counts
those moves, so the Team and Player pages say the same thing as the match they came from. Nothing is stored: a match's moves take a
few milliseconds to build, and the pages remember the answer until a match is added.

Positions are in the move's own direction (the side on the ball attacks left to right), 0-1000 along the pitch and across it, as the
moves themselves keep them.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from .possessions import K_PASS, build_possessions, led_to_shot
from .silver import Match

SHOT_ENDS = frozenset({"goal", "shot_on", "shot_off", "shot_blocked"})
ZONES = (("own", "Own third"), ("mid", "Middle third"), ("final", "Final third"))
#: how a move started, grouped as a person would say it
START_GROUPS = (
    ("won", "In open play (ball won or picked up)", frozenset({"open", "tackle", "interception", "recovery", "blocked_pass", "clearance", "keeper", "loose"})),
    ("goal_kick", "Goal kick", frozenset({"goal_kick"})),
    ("throw_in", "Throw-in", frozenset({"throw_in"})),
    ("free_kick", "Free kick", frozenset({"free_kick", "penalty"})),
    ("corner", "Corner", frozenset({"corner"})),
    ("kickoff", "Kick-off", frozenset({"kickoff"})),
)
HOW_LABEL = {"tackle": "Tackled", "interception": "Pass cut out", "recovery": "Loose ball picked up by them", "blocked_pass": "Pass blocked", "touch": "An opponent got a touch",
             "keeper": "Gathered by the keeper", "clearance": "Cleared away", "took": "Taken off him", "pass": "His pass found no team-mate"}
NX, NY = 24, 16          # the same grid as every other heat map (app.events.maps)
MAX_POINTS = 500


def zone_of(x: int) -> str:
    """Which third of the pitch (in the direction of play) a position is in."""
    return "own" if x < 333 else "mid" if x < 667 else "final"


def end_group(move: dict) -> str:
    """How a move ended, in five plain groups: a shot; lost in play; out of play or a free kick to the other side; a restart won
    (throw-in, corner, free kick: the side keeps the ball); the whistle."""
    end = move["end"]
    if end in SHOT_ENDS:
        return "shot"
    if end == "lost" or end == "own_goal":
        return "lost"
    if end in ("foul", "offside"):
        return "gave"
    if end == "foul_won":
        return "kept"
    if end in ("out", "stopped"):
        return "kept" if move["keep"] else "gave"
    return "other"


def _start(move: dict) -> tuple[int, int] | None:
    """Where a move began: where the ball was won, else its first step."""
    if move.get("sat"):
        return move["sat"][0], move["sat"][1]
    for step in move["steps"]:
        if step[2] >= 0:
            return step[2], step[3]
    return None


def _lost_at(move: dict) -> tuple[int, int] | None:
    """Where the ball went: where the opponent took it, else where the last step ended (a pass that found nobody), else where it began."""
    if move.get("at"):
        return move["at"][0], move["at"][1]
    last = move["steps"][-1]
    if last[0] == K_PASS and last[4] >= 0:
        return last[4], last[5]
    return (last[2], last[3]) if last[2] >= 0 else None


def _cell(x: int, y: int) -> int:
    return min(NY - 1, max(0, y * NY // 1001)) * NX + min(NX - 1, max(0, x * NX // 1001))


def _thin(points: list, limit: int = MAX_POINTS) -> list:
    if len(points) <= limit:
        return points
    step = len(points) / limit
    return [points[int(i * step)] for i in range(limit)]


XgOf = Callable[[Match], dict[int, float]]   # a match -> {shot event index: Understat's xG}, for the shots Understat has


def _shot_events(moves: list[dict], came: list[bool]) -> list[int]:
    """Per move, the event index of the shot it came to: its own, or that of the corner, free kick or penalty it won; -1 when none."""
    out = []
    for k, move in enumerate(moves):
        if move["shot"] >= 0:
            out.append(move["shot"])
        elif came[k] and k + 1 < len(moves):
            out.append(moves[k + 1]["shot"])
        else:
            out.append(-1)
    return out


def _team_index(m: Match, team: str) -> int | None:
    return next((i for i, t in enumerate(m.teams) if t["name"] == team), None)


def team_moves(matches: Iterable[Match], team: str, *, xg_of: XgOf | None = None) -> dict:
    """A team's moves over these matches: how they ended, by where and how they began; where the ball was lost; who lost it most and
    who took it off the opponents most.

    ``ends``: counts per end group (see :func:`end_group`). ``zones`` and ``starts``: per group ``{n, shot, box, lost}`` where ``shot``
    counts moves that came to a shot (:func:`app.events.possessions.led_to_shot`: the move itself, or the corner, free kick or penalty
    it won). ``lost_grid``: a 24 by 16 grid (rows across the pitch, as every heat map here) of where its moves were lost in play.
    """
    ends = dict.fromkeys(("shot", "lost", "gave", "kept", "other"), 0)
    zones = {key: {"n": 0, "shot": 0, "box": 0, "lost": 0} for key, _label in ZONES}
    starts = {key: {"n": 0, "shot": 0, "box": 0, "lost": 0} for key, _label, _kinds in START_GROUPS}
    start_of = {kind: key for key, _label, kinds in START_GROUPS for kind in kinds}
    grid = [0] * (NX * NY)
    losers: dict[int, dict] = {}
    winners: dict[int, dict] = {}
    names: dict[int, str] = {}
    n = passes = games = came = xg_known = shots = 0
    xg_sum = 0.0
    for m in matches:
        tm = _team_index(m, team)
        if tm is None:
            continue
        games += 1
        for p in m.players:
            names.setdefault(p["id"], p["name"])
        moves = build_possessions(m)
        led = led_to_shot(moves)
        xg = xg_of(m) if xg_of is not None else {}
        seen: set[int] = set()
        for move, shot, at_shot in zip(moves, led, _shot_events(moves, led), strict=True):
            group = end_group(move)
            if move["tm"] == tm and shot and at_shot >= 0 and at_shot not in seen:
                seen.add(at_shot)             # a corner won and the corner itself came to the same shot: it is one shot
                shots += 1
                if at_shot in xg:
                    xg_sum += xg[at_shot]
                    xg_known += 1
            if move["tm"] != tm:
                # the other side's move: which of ours ended it, and how
                if move["by"] and move["end"] == "lost" and m.by_id.get(move["by"], {}).get("tm") == tm:
                    w = winners.setdefault(move["by"], {"n": 0, "how": {}, "final": 0})
                    w["n"] += 1
                    w["how"][move["how"]] = w["how"].get(move["how"], 0) + 1
                    at = _lost_at(move)
                    if at is not None and at[0] < 333:          # in the opponents' own third: high up the pitch for us
                        w["final"] += 1
                continue
            n += 1
            passes += move["n"]
            came += shot
            ends[group] += 1
            lost = group == "lost"
            began = _start(move)
            for bucket in ((zones[zone_of(began[0])],) if began is not None else ()) + ((starts[start_of[move["st"]]],) if move["st"] in start_of else ()):
                bucket["n"] += 1
                bucket["shot"] += shot
                bucket["box"] += move["box"]
                bucket["lost"] += lost
            if lost:
                at = _lost_at(move)
                if at is not None:
                    grid[_cell(*at)] += 1
                if move["lost"]:
                    who = losers.setdefault(move["lost"], {"n": 0, "own": 0})
                    who["n"] += 1
                    if at is not None and at[0] < 500:
                        who["own"] += 1
    top = lambda book, extra: [{"id": pid, "name": names.get(pid, ""), **extra(v)} for pid, v in sorted(book.items(), key=lambda kv: (-kv[1]["n"], names.get(kv[0], "")))[:8]]  # noqa: E731
    return {
        "n": n, "matches": games, "passes": passes, "shot": came, "ends": ends,
        # the shots the moves came to (each once), Understat's xG of them, and for how many it is known (None when it was not asked for)
        "shots": shots, "shot_xg": None if xg_of is None else round(xg_sum, 2), "shot_xg_known": None if xg_of is None else xg_known,
        "zones": [{"key": key, "label": label, **zones[key]} for key, label in ZONES],
        "starts": [{"key": key, "label": label, **starts[key]} for key, label, _kinds in START_GROUPS if starts[key]["n"]],
        "lost_grid": grid, "dims": [NX, NY],
        "losers": top(losers, lambda v: {"n": v["n"], "own_half": v["own"]}),
        "winners": top(winners, lambda v: {"n": v["n"], "high": v["final"], "how": max(v["how"], key=v["how"].get)}),
    }


def player_moves(matches: Iterable[tuple[int, Match]], player: int, *, xg_of: XgOf | None = None) -> dict:
    """One player's part in his side's moves over these ``(index, match)`` pairs: how many he was in and how many came to a shot,
    every place he lost the ball (and how), and every place he took it off the other side.

    ``lost`` and ``won`` are points ``[x, y, how, match index]`` in his own side's direction of play (so "won" high up the pitch is on
    the right, like every other map of his)."""
    part = shot_in = 0
    lost: list[list] = []
    won: list[list] = []
    lost_how: dict[str, int] = {}
    lost_zone = dict.fromkeys((key for key, _label in ZONES), 0)
    games = xg_known = shots = 0
    xg_sum = 0.0
    for index, m in matches:
        me = m.by_id.get(player)
        if me is None:
            continue
        games += 1
        tm = me["tm"]
        moves = build_possessions(m)
        led = led_to_shot(moves)
        xg = xg_of(m) if xg_of is not None else {}
        seen: set[int] = set()
        for move, shot, at_shot in zip(moves, led, _shot_events(moves, led), strict=True):
            if move["tm"] == tm:
                if any(step[1] == player for step in move["steps"]):
                    part += 1
                    shot_in += shot
                    if shot and at_shot >= 0 and at_shot not in seen:
                        seen.add(at_shot)     # in the move that won the corner and in the corner: still one shot
                        shots += 1
                        if at_shot in xg:
                            xg_sum += xg[at_shot]
                            xg_known += 1
                if move["lost"] == player and end_group(move) == "lost":
                    at = _lost_at(move)
                    how = move["how"] or "pass"            # nobody took it off him: his pass found no team-mate
                    lost_how[how] = lost_how.get(how, 0) + 1
                    if at is not None:
                        lost.append([at[0], at[1], how, index])
                        lost_zone[zone_of(at[0])] += 1
            elif move["by"] == player and move["end"] == "lost":
                at = _lost_at(move)
                if at is not None:
                    won.append([1000 - at[0], 1000 - at[1], move["how"], index])
    return {
        "matches": games, "n": part, "shot": shot_in, "lost_n": sum(lost_how.values()), "won_n": len(won),
        "shots": shots, "shot_xg": None if xg_of is None else round(xg_sum, 2), "shot_xg_known": None if xg_of is None else xg_known,
        "lost": _thin(lost), "won": _thin(won),
        "lost_how": [{"key": k, "label": HOW_LABEL.get(k, k), "n": v} for k, v in sorted(lost_how.items(), key=lambda kv: -kv[1])],
        "lost_zone": [{"key": key, "label": label, "n": lost_zone[key]} for key, label in ZONES],
    }
