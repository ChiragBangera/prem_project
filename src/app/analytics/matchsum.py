"""What the stored Understat match pages say, summed up: scorers, positions played, shot-level aggregates.

Pure functions over :class:`~app.data.models.MatchPage` and :class:`~app.data.models.Fixture`. Nothing here touches the
network or the store; :class:`~app.data.matchbook.MatchBook` supplies the pages.

Conventions (Understat's own):
* a shot's position is 0-1 along the pitch (1 = the goal line being attacked) and 0-1 across it;
* an ``OwnGoal`` shot carries the *scorer's own* side, so the goal belongs to the other side;
* a roster entry with position ``Sub`` is a substitute who came on (his position that day is not recorded).
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable, Mapping

from app.data.models import Fixture, MatchPage, Shot

BIG_CHANCE = 0.30
PITCH_L, PITCH_W = 105.0, 68.0
BOX_X = 1 - 16.5 / PITCH_L            # the penalty area starts 16.5 m from the goal line
BOX_HALF_Y = 20.16 / PITCH_W          # ...and is 40.3 m wide
SET_PIECE = {"FromCorner", "SetPiece", "DirectFreekick"}
ON_TARGET = {"Goal", "SavedShot"}


def distance_m(shot: Shot) -> float:
    return math.hypot((1.0 - shot.x) * PITCH_L, (shot.y - 0.5) * PITCH_W)


def in_box(shot: Shot) -> bool:
    return shot.x >= BOX_X and abs(shot.y - 0.5) <= BOX_HALF_Y


# ------------------------------------------------------------------ scorers (the Matches page)


def _scorer(shot: Shot) -> dict:
    return {
        "player": shot.player, "id": shot.player_id, "minute": shot.minute, "kind": "og" if shot.result == "OwnGoal" else "pen" if shot.situation == "Penalty" else "goal",
        "assist": shot.assisted_by, "xg": round(shot.xg, 2),
    }


def scorers(page: MatchPage) -> dict[str, list[dict]]:
    """Goals per side in match order, own goals credited to the side that benefited."""
    out: dict[str, list[dict]] = {"h": [], "a": []}
    for side in ("h", "a"):
        for shot in page.shots.get(side, []):
            if shot.result == "Goal":
                out[side].append(_scorer(shot))
            elif shot.result == "OwnGoal":
                out["a" if side == "h" else "h"].append(_scorer(shot))
    for side in out:
        out[side].sort(key=lambda g: (g["minute"], g["player"]))
    return out


def sent_off(page: MatchPage) -> dict[str, list[dict]]:
    """Players shown a red card per side (Understat gives no minute for cards, so none is claimed)."""
    return {side: [{"player": r.player, "id": r.player_id} for r in page.rosters.get(side, []) if r.red] for side in ("h", "a")}


def fixture_summary(fixture: Fixture, page: MatchPage) -> dict:
    """One compact record per match for list pages: who scored, and the chances in numbers."""
    side = lambda s: [x for x in page.shots.get(s, []) if x.result != "OwnGoal"]  # noqa: E731
    h, a = side("h"), side("a")
    return {
        "scorers": scorers(page), "red": sent_off(page),
        "shots": {"h": len(h), "a": len(a)}, "sot": {"h": sum(s.result in ON_TARGET for s in h), "a": sum(s.result in ON_TARGET for s in a)},
        "big": {"h": sum(s.xg >= BIG_CHANCE for s in h), "a": sum(s.xg >= BIG_CHANCE for s in a)},
    }


# ------------------------------------------------------------------ positions (who plays where, from minutes actually played)


def position_minutes(pages: Iterable[MatchPage]) -> dict[int, dict]:
    """Per Understat player id: ``{"pos": {code: minutes at that position}, "starts": n, "subs": n}``.

    Only started matches carry a position (a substitute's is recorded as ``Sub``), so a player who is nearly always a
    substitute has little here; callers fall back to Understat's listed positions for him.
    """
    out: dict[int, dict] = defaultdict(lambda: {"pos": defaultdict(int), "starts": 0, "subs": 0})
    for page in pages:
        for side in ("h", "a"):
            for r in page.rosters.get(side, []):
                if r.minutes <= 0 or not r.player_id:
                    continue
                row = out[r.player_id]
                if r.position and r.position != "Sub":
                    row["pos"][r.position] += r.minutes
                    row["starts"] += 1
                else:
                    row["subs"] += 1
    return {pid: {"pos": dict(v["pos"]), "starts": v["starts"], "subs": v["subs"]} for pid, v in out.items()}


# ------------------------------------------------------------------ shot-level aggregates


class ShotTotals:
    """Sums over a group of shots (one player's, or one team's for or against). A plain accumulator."""

    __slots__ = ("n", "goals", "xg", "sot", "blocked", "off", "post", "big", "big_goals", "pens", "pen_goals", "pen_xg", "sp_shots", "sp_xg", "sp_goals",
                 "op_shots", "op_xg", "head", "head_xg", "head_goals", "dist", "box", "assisted", "fk", "fk_goals", "fk_xg", "xg_np")

    def __init__(self) -> None:
        for name in self.__slots__:
            setattr(self, name, 0.0 if name in ("xg", "pen_xg", "sp_xg", "op_xg", "head_xg", "dist", "fk_xg", "xg_np") else 0)

    def add(self, s: Shot) -> None:
        goal = s.result == "Goal"
        self.n += 1
        self.goals += goal
        self.xg += s.xg
        self.sot += s.result in ON_TARGET
        self.blocked += s.result == "BlockedShot"
        self.off += s.result == "MissedShots"
        self.post += s.result == "ShotOnPost"
        if s.xg >= BIG_CHANCE:
            self.big += 1
            self.big_goals += goal
        if s.situation == "Penalty":
            self.pens += 1
            self.pen_goals += goal
            self.pen_xg += s.xg
        else:
            self.xg_np += s.xg
            if s.situation in SET_PIECE:
                self.sp_shots += 1
                self.sp_xg += s.xg
                self.sp_goals += goal
            else:
                self.op_shots += 1
                self.op_xg += s.xg
        if s.situation == "DirectFreekick":
            self.fk += 1
            self.fk_goals += goal
            self.fk_xg += s.xg
        if s.shot_type == "Head":
            self.head += 1
            self.head_xg += s.xg
            self.head_goals += goal
        self.dist += distance_m(s)
        self.box += in_box(s)
        self.assisted += bool(s.assisted_by)

    def as_dict(self) -> dict[str, float]:
        return {k: round(getattr(self, k), 4) if isinstance(getattr(self, k), float) else getattr(self, k) for k in self.__slots__}


def player_shots(pages: Iterable[MatchPage]) -> dict[int, dict]:
    """Per Understat player id, shot-level sums over the pages given (own goals excluded: they are not shots)."""
    out: dict[int, ShotTotals] = defaultdict(ShotTotals)
    for page in pages:
        for side in ("h", "a"):
            for s in page.shots.get(side, []):
                if s.player_id and s.result != "OwnGoal":
                    out[s.player_id].add(s)
    return {pid: t.as_dict() for pid, t in out.items()}


def team_shots(fixtures_pages: Iterable[tuple[Fixture, MatchPage]]) -> dict[str, dict]:
    """Per team name: ``{"for": sums, "against": sums, "matches": n}`` from the pages given."""
    out: dict[str, dict] = {}
    for fixture, page in fixtures_pages:
        for side, team, other in (("h", fixture.home, fixture.away), ("a", fixture.away, fixture.home)):
            row = out.setdefault(team, {"for": ShotTotals(), "against": ShotTotals(), "matches": 0})
            opp = out.setdefault(other, {"for": ShotTotals(), "against": ShotTotals(), "matches": 0})
            row["matches"] += 1
            for s in page.shots.get(side, []):
                if s.result != "OwnGoal":
                    row["for"].add(s)
                    opp["against"].add(s)
    return {t: {"for": v["for"].as_dict(), "against": v["against"].as_dict(), "matches": v["matches"]} for t, v in out.items()}


def season_log(fixture_pages: Iterable[tuple[Fixture, MatchPage]], player_id: int) -> list[dict]:
    """One player's match-by-match line from the match pages: minutes, goals, xG, xA, key passes and the team he played for."""
    rows = []
    for fixture, page in fixture_pages:
        for side in ("h", "a"):
            for r in page.rosters.get(side, []):
                if r.player_id == player_id and r.minutes > 0:
                    home = side == "h"
                    rows.append({
                        "match_id": fixture.id, "date": fixture.date, "opponent": fixture.away if home else fixture.home, "home": home,
                        "gf": (fixture.hg if home else fixture.ag), "ga": (fixture.ag if home else fixture.hg), "position": r.position, "minutes": r.minutes,
                        "goals": r.goals, "assists": r.assists, "shots": r.shots, "xg": round(r.xg, 2), "xa": round(r.xa, 2), "key_passes": r.key_passes,
                        "xgchain": round(r.xgchain, 2), "xgbuildup": round(r.xgbuildup, 2), "yellow": r.yellow, "red": r.red,
                    })
    rows.sort(key=lambda r: (r["date"], r["match_id"]))
    return rows


def modal_position(positions: Mapping[str, int]) -> str | None:
    """The position code he played the most minutes at, if any."""
    return max(positions, key=lambda k: (positions[k], k)) if positions else None
