"""Synthetic WhoScored-shaped matches for the demo world, so every event feature (maps, passing and defending metrics, possession, the
style profile ...) works with ``prem serve --demo``.

Each demo match already has simulated shots, line-ups and formations (see :mod:`.sim`). This adds what an event feed contains besides
them: passes, defensive actions, duels, set pieces, fouls and cards, per player in proportion to his role and minutes, with pitch
positions that fit his role and a team's possession that follows its chances. The shots, goals, cards and substitutions are the
simulation's own, so everything agrees with the Understat-shaped data.

A match's document depends only on the match (its own seed): the same match always yields the same document, and the real parser
(:mod:`app.events.silver`) reads it exactly as it reads a real one. Nothing here is real football.
"""

from __future__ import annotations

import math
import random
import zlib
from datetime import date
from typing import Any

from app.events import schema as S

from .names import NameFactory
from .sim import Appearance, MatchSim, SeasonData, ShotSim
from .world import Player

WS_PLAYER = 5_000_000   # a WhoScored player id is this plus the demo player's id: stable, and never equal to an Understat id
WS_TEAM = 9_000
WS_GAME = 10_000_000    # ... and a game id this plus the fixture id

# where each role is on the ball: (x mean, x sd, y mean or None for "by side", y sd). x runs 0 (own goal) to 100; y 0 (right) to 100 (left)
ZONE = {
    "GK": (7, 3, 50, 9), "CB": (27, 8, 50, 15), "FB": (42, 12, None, 7), "DM": (41, 9, 50, 15),
    "CM": (51, 10, 50, 19), "AM": (62, 9, 50, 17), "W": (68, 10, None, 9), "ST": (76, 8, 50, 14),
}
PASSES90 = {"GK": 24, "CB": 56, "FB": 46, "DM": 55, "CM": 49, "AM": 35, "W": 27, "ST": 17}
FORWARD = {"GK": 22, "CB": 8, "FB": 7, "DM": 7, "CM": 7, "AM": 8, "W": 6, "ST": 3}   # mean forward gain of a pass, metres
RATES90 = {  # events per 90 minutes on the pitch, by role
    "tackle": {"GK": 0.0, "CB": 1.3, "FB": 2.3, "DM": 2.7, "CM": 2.0, "AM": 1.0, "W": 1.2, "ST": 0.5},
    "challenge": {"GK": 0.0, "CB": 0.5, "FB": 1.0, "DM": 0.9, "CM": 0.7, "AM": 0.5, "W": 0.7, "ST": 0.3},
    "interception": {"GK": 0.1, "CB": 1.6, "FB": 1.3, "DM": 1.7, "CM": 1.1, "AM": 0.6, "W": 0.5, "ST": 0.3},
    "clearance": {"GK": 0.2, "CB": 4.8, "FB": 2.0, "DM": 1.2, "CM": 0.6, "AM": 0.3, "W": 0.3, "ST": 0.6},
    "recovery": {"GK": 1.0, "CB": 4.5, "FB": 5.3, "DM": 6.2, "CM": 5.2, "AM": 3.6, "W": 3.4, "ST": 2.2},
    "aerial": {"GK": 0.1, "CB": 4.2, "FB": 1.4, "DM": 2.0, "CM": 1.4, "AM": 0.9, "W": 0.8, "ST": 4.0},
    "takeon": {"GK": 0.0, "CB": 0.2, "FB": 1.4, "DM": 0.5, "CM": 1.0, "AM": 2.0, "W": 3.2, "ST": 1.4},
    "dispossessed": {"GK": 0.0, "CB": 0.2, "FB": 0.7, "DM": 0.6, "CM": 0.9, "AM": 1.1, "W": 1.4, "ST": 1.1},
    "foul": {"GK": 0.0, "CB": 1.15, "FB": 1.25, "DM": 1.6, "CM": 1.15, "AM": 0.8, "W": 0.8, "ST": 1.05},
    "blocked_pass": {"GK": 0.0, "CB": 0.5, "FB": 0.4, "DM": 0.4, "CM": 0.2, "AM": 0.1, "W": 0.1, "ST": 0.1},
    "touch": {"GK": 1.5, "CB": 3.0, "FB": 4.0, "DM": 4.0, "CM": 4.0, "AM": 4.0, "W": 4.5, "ST": 4.5},
}
LANE = {"GK": 0, "CB": 17, "FB": 0, "DM": 14, "CM": 20, "AM": 18, "W": 0, "ST": 12}   # how far left or right of centre a player's own spot can sit
PERIOD = {1: "FirstHalf", 2: "SecondHalf"}


def _lane(player_id: int) -> float:
    """A steady number in [-1, 1] for a player: where across the pitch his own spot sits, the same in every match."""
    return zlib.crc32(f"lane|{player_id}".encode()) % 2001 / 1000 - 1


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _horizontal(player: Player) -> float:
    """Where a player stands across the pitch in the lineup, on the 0-10 scale of a formation slot."""
    y = ZONE[player.role][2]
    return y / 10 if y else (8.4 if player.side == "L" else 1.6)


def _clip(v: float, lo: float = 0.5, hi: float = 99.5) -> float:
    return max(lo, min(hi, v))


class _Match:
    """Builds one document. Events are collected unordered, then sorted by the clock and numbered."""

    def __init__(self, data: SeasonData, match: MatchSim):
        self.data, self.m = data, match
        self.rng = random.Random(match.id * 7919 + 13)
        self.team = {"h": match.home, "a": match.away}
        clubs = data.clubs
        self.tid = {v: WS_TEAM + 1 + list(clubs).index(t) for v, t in self.team.items()}
        self.events: list[dict] = []
        self.apps = match.lineups
        self.full_time = 90 + self.rng.randint(3, 8)
        xh, xa = match.hxg, match.axg
        edge = (xh - xa) / (xh + xa + 0.8)
        self.poss = {"h": min(0.7, max(0.3, 0.5 + 0.3 * edge + 0.03 + self.rng.gauss(0, 0.035)))}
        self.poss["a"] = 1 - self.poss["h"]

    # ------------------------------------------------------------------ plumbing

    def _span(self, app: Appearance) -> tuple[int, int]:
        end = self.full_time if app.end >= 999 else app.end
        return max(1, app.start), max(app.start + 1, end)

    def _on(self, venue: str, minute: int) -> list[Appearance]:
        return [a for a in self.apps[venue] if a.start <= minute < (self.full_time if a.end >= 999 else a.end)]

    def add(self, venue: str, player: Player | None, kind: str, minute: int, x: float | None, y: float | None, *, ok: bool = True, end: tuple[float, float] | None = None,
            quals: tuple = (), touch: bool = True, **extra) -> dict:
        minute = max(0, min(minute, self.full_time))
        period = 1 if minute <= 45 else 2
        e = {
            "type": {"displayName": kind, "value": S.EVENT[kind]}, "outcomeType": {"displayName": "Successful" if ok else "Unsuccessful", "value": 1 if ok else 0},
            "teamId": self.tid[venue], "minute": minute, "second": self.rng.randint(0, 59), "expandedMinute": minute,
            "period": {"displayName": PERIOD[period], "value": period}, "isTouch": touch,
            "qualifiers": [{"type": {"displayName": q[0] if isinstance(q, tuple) else q, "value": 1}, **({"value": str(q[1])} if isinstance(q, tuple) else {})} for q in quals],
            "_venue": venue,
        }
        if player is not None:
            e["playerId"] = WS_PLAYER + player.id
        if x is not None and y is not None:
            e["x"], e["y"] = round(_clip(x), 1), round(_clip(y), 1)
        if end is not None:
            e["endX"], e["endY"] = round(_clip(end[0]), 1), round(_clip(end[1]), 1)
        e.update(extra)
        self.events.append(e)
        return e

    def spot(self, player: Player, shift: float = 0.0) -> tuple[float, float]:
        mx, sx, my, sy = ZONE[player.role]
        line: float
        if my is None:
            line = 84 if player.side == "L" else 16
        else:
            line = my + _lane(player.id) * LANE[player.role]       # two centre-backs or three midfielders do not all stand on the same line
        return _clip(self.rng.gauss(mx + shift, sx), 1, 99), _clip(self.rng.gauss(line, sy), 1, 99)

    # ------------------------------------------------------------------ passes

    def passes(self, venue: str) -> None:
        rng, club = self.rng, self.data.clubs[self.team[venue]]
        total = int(max(140, min(640, rng.gauss(300, 40) + 700 * (self.poss[venue] - 0.5))))
        accuracy = 0.83 + 0.035 * (3.5 - club.quality) + 0.2 * (self.poss[venue] - 0.5)
        apps = self.apps[venue]
        weights = []
        for a in apps:
            lo, hi = self._span(a)
            weights.append(PASSES90[a.player.role] * (hi - lo) / 90 * a.player.involve ** 0.6 + 0.01)
        for a in rng.choices(apps, weights, k=total):
            lo, hi = self._span(a)
            p = a.player
            minute = rng.randint(lo, max(lo, hi - 1))
            x0, y0 = self.spot(p)
            quals: list = []
            if p.role == "GK":
                long = rng.random() < 0.7
                if long:
                    quals.append("GoalKick" if rng.random() < 0.55 else "Longball")
            else:
                long = rng.random() < 0.075
            gain = rng.gauss(FORWARD[p.role], 9)
            if long:
                gain = rng.gauss(32, 8)
                if "Longball" not in quals and "GoalKick" not in quals:
                    quals.append("Longball")
            x1 = _clip(x0 + gain / 1.05)
            y1 = _clip(y0 + rng.gauss(0, 14 if not long else 22))
            wide = y0 < 22 or y0 > 78
            if p.role in ("W", "FB", "AM") and x0 > 70 and wide and rng.random() < 0.22:
                quals.append("Cross")
                x1, y1 = rng.uniform(86, 97), rng.uniform(34, 66)
            elif p.role in ("AM", "CM", "ST", "W") and x0 > 45 and rng.random() < 0.016:
                quals.append("Throughball")
                x1, y1 = _clip(x0 + rng.uniform(12, 28)), _clip(y0 + rng.gauss(0, 10))
            if "Cross" not in quals and "Throughball" not in quals and not long and rng.random() < 0.04:
                quals.append("HeadPass" if rng.random() < 0.6 else "Chipped")
            dist = math.hypot((x1 - x0) * 1.05, (y1 - y0) * 0.68)
            p_ok = accuracy - 0.0042 * dist - (0.13 if x0 > 72 else 0) + (0.05 if p.role == "CB" else 0) - (0.2 if "Cross" in quals else 0) - (0.3 if "Throughball" in quals else 0)
            ok = rng.random() < max(0.2, min(0.97, p_ok))
            quals += [("Length", round(dist, 1))]
            self.add(venue, p, "Pass", minute, x0, y0, ok=ok, end=(x1, y1), quals=tuple(quals))

    # ------------------------------------------------------------------ everything a player does without or against the ball

    def actions(self, venue: str) -> None:
        rng, club = self.rng, self.data.clubs[self.team[venue]]
        defend = 1 + 0.9 * (0.5 - self.poss[venue])          # a side without the ball defends more
        press = max(-6, min(8, (10.5 - club.ppda) * 1.6))      # a pressing side wins the ball higher up
        for a in self.apps[venue]:
            p = a.player
            lo, hi = self._span(a)
            share = (hi - lo) / 90
            for key, rates in RATES90.items():
                lam = rates[p.role] * share * (defend if key in ("tackle", "interception", "clearance", "recovery", "challenge", "blocked_pass") else 1.0)
                if key == "aerial":
                    lam *= p.aerial ** 0.5
                if key == "takeon":
                    lam *= p.create ** 0.4
                for _ in range(_poisson(rng, lam)):
                    minute = rng.randint(lo, max(lo, hi - 1))
                    shift = press if key in ("tackle", "interception", "recovery") else 0.0
                    x, y = self.spot(p, shift)
                    if key == "tackle":
                        self.add(venue, p, "Tackle", minute, x, y, ok=rng.random() < 0.74)
                    elif key == "challenge":
                        self.add(venue, p, "Challenge", minute, x, y, ok=False)
                    elif key == "interception":
                        self.add(venue, p, "Interception", minute, x, y)
                    elif key == "clearance":
                        self.add(venue, p, "Clearance", minute, min(x, 38), y, quals=(("Head",) if rng.random() < 0.4 else ()))
                    elif key == "recovery":
                        self.add(venue, p, "BallRecovery", minute, x, y)
                    elif key == "aerial":
                        self.add(venue, p, "Aerial", minute, x, y, ok=rng.random() < min(0.8, 0.46 + 0.09 * p.aerial), quals=("Defensive" if x < 50 else "Offensive",))
                    elif key == "takeon":
                        self.add(venue, p, "TakeOn", minute, max(x, 35), y, ok=rng.random() < 0.5)
                    elif key == "dispossessed":
                        self.add(venue, p, "Dispossessed", minute, x, y, ok=False)
                    elif key == "blocked_pass":
                        self.add(venue, p, "BlockedPass", minute, x, y)
                    elif key == "touch":
                        self.add(venue, p, "BallTouch", minute, x, y)
                    elif key == "foul":
                        self.add(venue, p, "Foul", minute, x, y, ok=False, touch=False)
                        victims = self._on("a" if venue == "h" else "h", minute)
                        if victims:
                            v = rng.choice(victims).player
                            self.add("a" if venue == "h" else "h", v, "Foul", minute, 100 - x, 100 - y, ok=True, touch=False)
            if p.role == "GK":
                for kind, lam in (("Claim", 1.0), ("KeeperPickup", 2.4), ("KeeperSweeper", 0.8), ("Punch", 0.3)):
                    for _ in range(_poisson(rng, lam * share)):
                        minute = rng.randint(lo, max(lo, hi - 1))
                        self.add(venue, p, kind, minute, rng.uniform(3, 20) if kind == "KeeperSweeper" else rng.uniform(3, 8), rng.gauss(50, 12))

    # ------------------------------------------------------------------ set pieces

    def set_pieces(self, venue: str) -> None:
        rng = self.rng
        xg = self.m.hxg if venue == "h" else self.m.axg
        for _ in range(max(0, int(rng.gauss(2.0 + 2.6 * xg, 1.4)))):                       # corners
            minute = rng.randint(2, self.full_time - 2)
            on = [a for a in self._on(venue, minute) if a.player.role != "GK"]
            if not on:
                continue
            taker = (next((a for a in on if a.player.set_piece), None) or rng.choice(on)).player
            top = rng.random() < 0.5
            self.add(venue, taker, "CornerAwarded", minute, 99.5, 0.5 if top else 99.5, touch=False)
            self.add(venue, taker, "Pass", minute, 99.5, 0.5 if top else 99.5, ok=rng.random() < 0.34, end=(rng.uniform(88, 97), rng.uniform(32, 68)),
                     quals=("CornerTaken", "Cross", "Longball", ("Length", round(rng.uniform(18, 32), 1))))
        for _ in range(int(rng.gauss(18, 3))):                                              # throw-ins
            minute = rng.randint(1, self.full_time - 1)
            on = [a for a in self._on(venue, minute) if a.player.role in ("FB", "W", "CM", "DM")]
            if not on:
                continue
            p = rng.choice(on).player
            x = rng.uniform(15, 90)
            y = 0.5 if rng.random() < 0.5 else 99.5
            self.add(venue, p, "Pass", minute, x, y, ok=rng.random() < 0.8, end=(_clip(x + rng.gauss(4, 8)), _clip(abs(y - rng.uniform(8, 25)))),
                     quals=("ThrowIn", ("Length", round(rng.uniform(6, 20), 1))))
        for _ in range(int(rng.gauss(3, 1.2))):                                             # free kicks
            minute = rng.randint(3, self.full_time - 1)
            on = [a for a in self._on(venue, minute) if a.player.role != "GK"]
            if not on:
                continue
            p = (next((a for a in on if a.player.set_piece), None) or rng.choice(on)).player
            x, y = rng.uniform(25, 75), rng.uniform(15, 85)
            self.add(venue, p, "Pass", minute, x, y, ok=rng.random() < 0.7, end=(_clip(x + rng.uniform(5, 25)), _clip(y + rng.gauss(0, 14))), quals=("FreekickTaken", ("Length", round(rng.uniform(12, 35), 1))))

    # ------------------------------------------------------------------ shots, saves, assists (the simulation's own)

    def shots(self) -> None:
        rng = self.rng
        for venue in ("h", "a"):
            other = "a" if venue == "h" else "h"
            for s in self.m.shots[venue]:
                self._shot(venue, other, s, rng)

    def _shot(self, venue: str, other: str, s: ShotSim, rng: random.Random) -> None:
        kind = {"Goal": "Goal", "SavedShot": "SavedShot", "BlockedShot": "SavedShot", "MissedShots": "MissedShots", "ShotOnPost": "ShotOnPost"}.get(s.result, "MissedShots")
        x, y = s.x * 100, s.y * 100
        quals: list = [{"Head": "Head", "RightFoot": "RightFoot", "LeftFoot": "LeftFoot"}.get(s.shot_type, "OtherBodyPart")]
        quals.append({"FromCorner": "FromCorner", "SetPiece": "SetPiece", "DirectFreekick": "DirectFreekick", "Penalty": "Penalty"}.get(s.situation, "RegularPlay"))
        if s.xg >= 0.3 and s.situation != "Penalty":
            quals.append("BigChance")
        if s.result == "BlockedShot":
            quals.append("Blocked")
        goal = kind == "Goal"
        if s.assister is not None:
            ax, ay = _clip(x - rng.uniform(4, 22)), _clip(y + rng.gauss(0, 14))
            aq = ["KeyPass"] + (["BigChanceCreated"] if s.xg >= 0.3 else []) + (["Cross"] if s.last_action == "Cross" else []) + (["Throughball"] if s.last_action == "Throughball" else [])
            self.add(venue, s.assister, "Pass", s.minute, ax, ay, ok=True, end=(x, y), quals=tuple(aq) + (("Length", round(math.hypot((x - ax) * 1.05, (y - ay) * 0.68), 1)),))
        self.add(venue, s.shooter, kind, s.minute, x, y, ok=goal, isShot=True, isGoal=goal, quals=tuple(quals),
                 goalMouthY=round(rng.uniform(44, 56) if s.result != "MissedShots" else rng.uniform(30, 70), 1), goalMouthZ=round(rng.uniform(0, 30), 1))
        if s.result == "SavedShot":
            keepers = [a for a in self._on(other, s.minute) if a.player.role == "GK"]
            if keepers:
                self.add(other, keepers[0].player, "Save", s.minute, rng.uniform(1, 4), 100 - y, touch=True)
        elif s.result == "BlockedShot":
            defenders = [a for a in self._on(other, s.minute) if a.player.role in ("CB", "FB", "DM")]
            if defenders:
                self.add(other, rng.choice(defenders).player, "Save", s.minute, 100 - x, 100 - y, quals=("OutfielderBlock",))

    def own_goals(self) -> None:
        """Understat's convention is WhoScored's too: a Goal event by the unlucky player, for his own team, flagged as an own goal and not a shot."""
        for og in self.m.own:
            self.add(og.venue, og.player, "Goal", og.minute, self.rng.uniform(2, 9), self.rng.uniform(38, 62), ok=True, isGoal=True, isOwnGoal=True, quals=("OwnGoal",))

    # ------------------------------------------------------------------ cards and substitutions

    def discipline_and_subs(self) -> None:
        rng = self.rng
        for venue in ("h", "a"):
            for a in self.apps[venue]:
                lo, hi = self._span(a)
                x, y = self.spot(a.player)
                for _ in range(a.yellow):
                    self.add(venue, a.player, "Card", rng.randint(lo, max(lo, hi - 1)), x, y, touch=False, cardType={"displayName": "Yellow", "value": 1}, quals=("Yellow",))
                for _ in range(a.red):
                    self.add(venue, a.player, "Card", rng.randint(lo, max(lo, hi - 1)), x, y, touch=False, cardType={"displayName": "Red", "value": 2}, quals=("Red",))
                if a.code == "Sub":
                    self.add(venue, a.player, "SubstitutionOn", a.start, None, None, touch=False)
                elif a.end < 999 and not a.red:
                    self.add(venue, a.player, "SubstitutionOff", a.end, None, None, touch=False)

    # ------------------------------------------------------------------ the document

    def document(self) -> dict:
        m = self.m
        for venue in ("h", "a"):
            self.passes(venue)
            self.actions(venue)
            self.set_pieces(venue)
        self.shots()
        self.own_goals()
        self.discipline_and_subs()
        self.events.sort(key=lambda e: (e["period"]["value"], e["minute"], e["second"]))
        counters = {"h": 0, "a": 0}
        numbered = []
        for i, e in enumerate(self.events, start=1):
            v = e.pop("_venue")
            counters[v] += 1
            numbered.append({**e, "eventId": counters[v], "id": 1000 + i})
        for period, minute in ((1, 46), (2, self.full_time)):
            numbered.append({"type": {"displayName": "End", "value": S.EVENT["End"]}, "outcomeType": {"displayName": "Successful", "value": 1}, "teamId": self.tid["h"], "eventId": 0,
                             "id": 900000 + period, "minute": minute, "second": 0, "expandedMinute": minute, "period": {"displayName": PERIOD[period], "value": period}, "isTouch": False, "qualifiers": []})
        half = {v: sum(1 for s in m.shots[v] if s.result == "Goal" and s.minute <= 45) + sum(1 for og in m.own if og.venue != v and og.minute <= 45) for v in ("h", "a")}
        ht = f"{half['h']} : {half['a']}"
        best: dict[tuple[str, int], float] = {}
        sides: dict[str, list[dict[str, Any]]] = {}
        for venue in ("h", "a"):
            players: list[dict[str, Any]] = []
            for a in self.apps[venue]:
                p = a.player
                goals = sum(1 for s in m.shots[venue] if s.shooter.id == p.id and s.result == "Goal")
                assists = sum(1 for s in m.shots[venue] if s.assister is not None and s.assister.id == p.id and s.result == "Goal")
                own = sum(1 for og in m.own if og.player.id == p.id)
                rating = round(max(4.6, min(9.9, 6.3 + 0.9 * p.ability + 0.9 * goals + 0.5 * assists - 0.9 * own + self.rng.gauss(0, 0.45))), 1)
                best[(venue, p.id)] = rating
                players.append({
                    "playerId": WS_PLAYER + p.id, "name": p.name, "position": "Sub" if a.code == "Sub" else p.code(), "isFirstEleven": a.code != "Sub", "shirtNo": 1 + (p.id % 98),
                    "age": p.age_on(date.fromisoformat(m.dt[:10])), "height": 165 + (p.id * 7) % 33, "weight": 62 + (p.id * 5) % 28, "isManOfTheMatch": False,
                    "stats": {"ratings": {"90": rating}}, "field": "home" if venue == "h" else "away",
                })
            sides[venue] = players
        top = max(best, key=best.__getitem__)
        for venue, players in sides.items():
            for pl in players:
                if (venue, pl["playerId"] - WS_PLAYER) == top:
                    pl["isManOfTheMatch"] = True

        def team_doc(venue: str) -> dict:
            club = self.data.clubs[self.team[venue]]
            name = NameFactory(zlib.crc32(f"{self.team[venue]}|{self.data.season}".encode())).make(self.data.league)
            starters = [a for a in self.apps[venue] if a.code != "Sub"]
            shape = self.m.formations[venue].replace("-", "")
            return {
                "teamId": self.tid[venue], "name": self.team[venue], "managerName": name, "averageAge": round(sum(p["age"] for p in sides[venue] if p["isFirstEleven"]) / max(1, len(starters)), 1),
                "players": sides[venue],
                "formations": [{
                    "formationName": shape, "startMinuteExpanded": 0, "endMinuteExpanded": self.full_time, "formationSlots": list(range(1, len(starters) + 1)),
                    "playerIds": [WS_PLAYER + a.player.id for a in starters],
                    "formationPositions": [{"horizontal": round(_horizontal(a.player), 1), "vertical": round(ZONE[a.player.role][0] / 10, 1)} for a in starters],
                    "captainPlayerId": WS_PLAYER + starters[0].player.id if starters else None,
                }],
                "_quality": club.quality,
            }

        home, away = team_doc("h"), team_doc("a")
        for side in (home, away):
            side.pop("_quality")
        names = {pl["playerId"]: pl["name"] for venue in sides.values() for pl in venue}
        return {
            "events": numbered, "score": f"{m.hg} : {m.ag}", "ftScore": f"{m.hg} : {m.ag}", "htScore": ht, "startTime": m.dt.replace(" ", "T"), "venueName": f"{m.home} Stadium",
            "attendance": 18_000 + self.rng.randint(0, 40_000), "referee": {"name": f"Referee {1 + m.id % 24}"}, "elapsed": "FT", "maxMinute": self.full_time,
            "periodEndMinutes": {"1": 46, "2": self.full_time}, "playerIdNameDictionary": {str(k): v for k, v in names.items()}, "home": home, "away": away,
        }



def synthesize_match(data: SeasonData, match: MatchSim) -> dict:
    """The raw event document for one demo match."""
    return _Match(data, match).document()


def game_id(match: MatchSim) -> int:
    return WS_GAME + match.id
