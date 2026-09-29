"""DemoProvider: the same interface as the Understat client, backed by the simulator.

Payloads are built in *Understat's own shapes* (string numbers in player and
fixture rows, ``history`` per team, ``groups`` on player pages ...) so the real
normalizers and analytics run over demo data exactly as they will over live
data. Nothing here is real: clubs are real names, players and results are
invented.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import date

from app.errors import UpstreamError
from app.leagues import current_season, fold

from .sim import SeasonData, ShotSim, _state_label, zone_of
from .world import (
    CLUBS,
    FIRST_DEMO_SEASON,
    LEAGUE_INDEX,
    League,
    build_initial_rosters,
    evolve_rosters,
    make_league,
)
from .sim import simulate_season

LEAGUE_CODES = list(LEAGUE_INDEX)
TIMING = (("1-15", 0, 15), ("16-30", 16, 30), ("31-45", 31, 45), ("46-60", 46, 60), ("61-75", 61, 75), ("76+", 76, 200))


def _s(value) -> str:
    return str(value)


class DemoProvider:
    source = "demo"

    def __init__(self, *, today: date | None = None, seed: int = 7):
        self.today = today or date.today()
        self._seed = seed
        self._leagues: dict[str, League] = {}
        self._seasons: dict[tuple[str, int], SeasonData] = {}
        self._dobs: dict[str, dict[str, str]] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ world

    def seasons(self) -> list[int]:
        return list(range(current_season(self.today), FIRST_DEMO_SEASON - 1, -1))

    def _league(self, code: str) -> League:
        if code not in LEAGUE_INDEX:
            raise UpstreamError(f"The demo world has no league '{code}'.", upstream_status=404)
        if code not in self._leagues:
            self._leagues[code] = make_league(code, self._seed)
        return self._leagues[code]

    def season_data(self, code: str, season: int) -> SeasonData:
        with self._lock:
            league = self._league(code)
            if season < FIRST_DEMO_SEASON or season > current_season(self.today):
                raise UpstreamError(
                    f"The demo world covers {FIRST_DEMO_SEASON}-{current_season(self.today)}; {season} is outside it.",
                    upstream_status=404,
                )
            for s in range(FIRST_DEMO_SEASON, season + 1):
                if (code, s) in self._seasons:
                    continue
                if s == FIRST_DEMO_SEASON:
                    build_initial_rosters(league, s)
                else:
                    evolve_rosters(league, s)
                self._seasons[(code, s)] = simulate_season(league, s, self.today)
            return self._seasons[(code, season)]

    def _all_seasons(self, code: str) -> list[SeasonData]:
        self.season_data(code, current_season(self.today))
        return [self._seasons[(code, s)] for s in range(FIRST_DEMO_SEASON, current_season(self.today) + 1)]

    def birthdate(self, name: str, team: str | None = None) -> str | None:
        """Look a demo player up by name. The world is built on demand (one league, once), so cached payloads still get ages."""
        key = fold(name)
        codes = [c for c, clubs in CLUBS.items() if team and any(club[0] == team for club in clubs)] or list(self._leagues)
        for code in codes:
            with self._lock:
                if code not in self._dobs:
                    self.season_data(code, current_season(self.today))
                    self._dobs[code] = {fold(p.name): p.dob.isoformat() for p in self._leagues[code].players.values()}
                if key in self._dobs[code]:
                    return self._dobs[code][key]
        return None

    # ------------------------------------------------------------------ provider API

    async def league(self, league: str, season: int) -> dict:
        return await asyncio.to_thread(self._league_payload, league, season)

    async def team(self, team: str, season: int) -> dict:
        return await asyncio.to_thread(self._team_payload, team.replace("_", " "), season)

    async def player(self, player_id: int) -> dict:
        return await asyncio.to_thread(self._player_payload, int(player_id))

    async def match(self, match_id: int) -> dict:
        return await asyncio.to_thread(self._match_payload, int(match_id))

    async def search_players(self, query: str) -> list[dict]:
        return await asyncio.to_thread(self._search, query)

    async def close(self) -> None:
        return None

    # ------------------------------------------------------------------ league payload

    def _team_ids(self, code: str) -> dict[str, int]:
        base = (LEAGUE_INDEX[code] + 1) * 1000
        return {name: base + i + 1 for i, (name, _s_, _t) in enumerate(CLUBS[code])}

    def _league_payload(self, code: str, season: int) -> dict:
        data = self.season_data(code, season)
        ids = self._team_ids(code)
        shorts = {name: short for name, short, _t in CLUBS[code]}
        matches = [f.match for f in data.fixtures if f.match is not None]

        history: dict[str, list[dict]] = {name: [] for name in data.clubs}
        for m in sorted(matches, key=lambda m: m.dt):
            for venue, team in (("h", m.home), ("a", m.away)):
                other = "a" if venue == "h" else "h"
                gf, ga = (m.hg, m.ag) if venue == "h" else (m.ag, m.hg)
                xg, xga = (m.hxg, m.axg) if venue == "h" else (m.axg, m.hxg)
                npxg = sum(s.xg for s in m.shots[venue] if s.situation != "Penalty")
                npxga = sum(s.xg for s in m.shots[other] if s.situation != "Penalty")
                pts = 3 if gf > ga else 1 if gf == ga else 0
                history[team].append(
                    {
                        "h_a": venue,
                        "xG": xg,
                        "xGA": xga,
                        "npxG": npxg,
                        "npxGA": npxga,
                        "deep": m.deep[venue],
                        "deep_allowed": m.deep[other],
                        "scored": gf,
                        "missed": ga,
                        "xpts": m.xpts[0] if venue == "h" else m.xpts[1],
                        "result": "w" if gf > ga else "d" if gf == ga else "l",
                        "date": m.dt,
                        "wins": int(gf > ga),
                        "draws": int(gf == ga),
                        "loses": int(gf < ga),
                        "pts": pts,
                        "npxGD": npxg - npxga,
                        "ppda": {"att": round(m.ppda[venue][0]), "def": round(m.ppda[venue][1])},
                        "ppda_allowed": {"att": round(m.ppda[other][0]), "def": round(m.ppda[other][1])},
                    }
                )

        dates = []
        for f in sorted(data.fixtures, key=lambda f: (f.dt, f.id)):
            m = f.match
            dates.append(
                {
                    "id": _s(f.id),
                    "isResult": m is not None,
                    "h": {"id": _s(ids[f.home]), "title": f.home, "short_title": shorts[f.home]},
                    "a": {"id": _s(ids[f.away]), "title": f.away, "short_title": shorts[f.away]},
                    "goals": {"h": _s(m.hg) if m else None, "a": _s(m.ag) if m else None},
                    "xG": {"h": _s(m.hxg) if m else None, "a": _s(m.axg) if m else None},
                    "datetime": f.dt,
                    "forecast": {"w": _s(round(f.forecast[0], 4)), "d": _s(round(f.forecast[1], 4)), "l": _s(round(f.forecast[2], 4))},
                }
            )

        players = []
        for pid, agg in data.players.items():
            players.append(
                {
                    "id": _s(pid),
                    "player_name": agg.player.name,
                    "games": _s(agg.games),
                    "time": _s(agg.minutes),
                    "goals": _s(agg.goals),
                    "xG": _s(agg.xg),
                    "assists": _s(agg.assists),
                    "xA": _s(agg.xa),
                    "shots": _s(agg.shots),
                    "key_passes": _s(agg.key_passes),
                    "yellow_cards": _s(agg.yellow),
                    "red_cards": _s(agg.red),
                    "position": data.letters[pid],
                    "team_title": ",".join(agg.teams),
                    "npg": _s(agg.npg),
                    "npxG": _s(agg.npxg),
                    "xGChain": _s(agg.xgchain),
                    "xGBuildup": _s(agg.xgbuildup),
                }
            )
        players.sort(key=lambda p: int(p["id"]))
        return {
            "teams": {_s(ids[name]): {"id": _s(ids[name]), "title": name, "history": rows} for name, rows in history.items()},
            "players": players,
            "dates": dates,
        }

    # ------------------------------------------------------------------ team payload

    def _team_payload(self, team: str, season: int) -> dict:
        found = None
        for code in LEAGUE_CODES:
            if any(name == team for name, _s_, _t in CLUBS[code]):
                found = code
                break
        if found is None:
            raise UpstreamError(f"The demo world has no team '{team}'.", upstream_status=404)
        data = self.season_data(found, season)

        groups: dict[str, dict[str, dict]] = {k: {} for k in ("situation", "formation", "gameState", "timing", "shotZone", "attackSpeed", "result")}

        def bucket(group: str, key: str) -> dict:
            slot = groups[group].setdefault(
                key, {"stat": key, "shots": 0, "goals": 0, "xG": 0.0, "against": {"shots": 0, "goals": 0, "xG": 0.0}}
            )
            return slot

        def add(slot: dict, shot: ShotSim, against: bool) -> None:
            target = slot["against"] if against else slot
            target["shots"] += 1
            target["goals"] += int(shot.result == "Goal")
            target["xG"] += shot.xg

        for m in data.matches.values():
            if team not in (m.home, m.away):
                continue
            venue = "h" if m.home == team else "a"
            other = "a" if venue == "h" else "h"
            bucket("formation", m.formations[venue]).setdefault("time", 0)
            groups["formation"][m.formations[venue]]["time"] += 90
            for own, side in ((False, venue), (True, other)):
                for shot in m.shots[side]:
                    diff = -shot.diff if own else shot.diff  # always from this team's point of view
                    keys = {
                        "situation": shot.situation,
                        "formation": m.formations[venue],
                        "gameState": _state_label(diff),
                        "timing": next(name for name, lo, hi in TIMING if lo <= shot.minute <= hi),
                        "shotZone": zone_of(shot.x, shot.y),
                        "attackSpeed": shot.speed,
                        "result": shot.result,
                    }
                    for group, key in keys.items():
                        add(bucket(group, key), shot, own)

        def clean(slot: dict) -> dict:
            slot["xG"] = round(slot["xG"], 4)
            slot["against"]["xG"] = round(slot["against"]["xG"], 4)
            return slot

        return {
            "statistics": {g: {k: clean(v) for k, v in rows.items()} for g, rows in groups.items()},
            "players": [],
            "dates": [],
        }

    # ------------------------------------------------------------------ player payload

    def _shot_row(self, s: ShotSim, m, season: int, player_id: int | None = None) -> dict:
        return {
            "id": _s(s.id),
            "minute": _s(s.minute),
            "result": s.result,
            "X": _s(round(s.x, 6)),
            "Y": _s(round(s.y, 6)),
            "xG": _s(s.xg),
            "player": s.shooter.name,
            "h_a": s.venue,
            "player_id": _s(s.shooter.id),
            "situation": s.situation,
            "season": _s(season),
            "shotType": s.shot_type,
            "match_id": _s(m.id),
            "h_team": m.home,
            "a_team": m.away,
            "h_goals": _s(m.hg),
            "a_goals": _s(m.ag),
            "date": m.dt,
            "player_assisted": s.assister.name if s.assister else None,
            "lastAction": s.last_action,
        }

    def _player_payload(self, pid: int) -> dict:
        index = pid // 100_000 - 1
        if not 0 <= index < len(LEAGUE_CODES):
            raise UpstreamError(f"Unknown demo player {pid}.", upstream_status=404)
        code = LEAGUE_CODES[index]
        seasons = self._all_seasons(code)
        player = self._leagues[code].players.get(pid)
        if player is None:
            raise UpstreamError(f"Unknown demo player {pid}.", upstream_status=404)

        shots, season_rows = [], []
        situation, zones, types, positions = {}, {}, {}, {}
        minutes_by_code: dict[str, int] = {}
        for data in seasons:
            agg = data.players.get(pid)
            if agg is None:
                continue
            season_rows.append(
                {
                    "season": _s(data.season),
                    "team": ",".join(agg.teams),
                    "position": data.letters[pid],
                    "games": _s(agg.games),
                    "time": _s(agg.minutes),
                    "goals": _s(agg.goals),
                    "xG": _s(agg.xg),
                    "assists": _s(agg.assists),
                    "xA": _s(agg.xa),
                    "shots": _s(agg.shots),
                    "key_passes": _s(agg.key_passes),
                    "yellow_cards": _s(agg.yellow),
                    "red_cards": _s(agg.red),
                    "npg": _s(agg.npg),
                    "npxG": _s(agg.npxg),
                    "xGChain": _s(agg.xgchain),
                    "xGBuildup": _s(agg.xgbuildup),
                }
            )
            by_sit, by_zone, by_type = {}, {}, {}
            for m in sorted(data.matches.values(), key=lambda m: m.dt):
                for venue in ("h", "a"):
                    for s in m.shots[venue]:
                        if s.shooter.id != pid:
                            continue
                        shots.append(self._shot_row(s, m, data.season))
                        for table, key in ((by_sit, s.situation), (by_zone, zone_of(s.x, s.y)), (by_type, s.shot_type)):
                            row = table.setdefault(key, {"shots": 0, "goals": 0, "xG": 0.0})
                            row["shots"] += 1
                            row["goals"] += int(s.result == "Goal")
                            row["xG"] += s.xg
            situation[_s(data.season)] = [{"situation": k, "shots": _s(v["shots"]), "goals": _s(v["goals"]), "xG": _s(v["xG"])} for k, v in by_sit.items()]
            zones[_s(data.season)] = [{"shotZones": k, "shots": _s(v["shots"]), "goals": _s(v["goals"]), "xG": _s(v["xG"])} for k, v in by_zone.items()]
            types[_s(data.season)] = [{"shotTypes": k, "shots": _s(v["shots"]), "goals": _s(v["goals"]), "xG": _s(v["xG"])} for k, v in by_type.items()]
            positions[_s(data.season)] = [
                {"position": c, "games": _s(agg.games), "time": _s(mins), "goals": "0", "xG": "0"} for c, mins in sorted(agg.role_minutes.items())
            ]
            for c, mins in agg.role_minutes.items():
                if c != "Sub":
                    minutes_by_code[c] = minutes_by_code.get(c, 0) + mins

        favorite = max(minutes_by_code, key=minutes_by_code.get) if minutes_by_code else player.code()
        return {
            "player": {"favorite_position": favorite},
            "shots": shots,
            "matches": [],
            "groups": {"season": season_rows, "situation": situation, "shotZones": zones, "shotTypes": types, "position": positions},
            "minMaxPlayerStats": {},
        }

    # ------------------------------------------------------------------ match payload

    def _match_payload(self, mid: int) -> dict:
        index = mid // 10_000_000 - 1
        season = 2000 + (mid % 10_000_000) // 10_000
        if not 0 <= index < len(LEAGUE_CODES):
            raise UpstreamError(f"Unknown demo match {mid}.", upstream_status=404)
        data = self.season_data(LEAGUE_CODES[index], season)
        m = data.matches.get(mid)
        if m is None:
            raise UpstreamError(f"Unknown demo match {mid}.", upstream_status=404)
        ids = self._team_ids(LEAGUE_CODES[index])
        rosters = {}
        for venue, apps in m.lineups.items():
            team = m.home if venue == "h" else m.away
            rosters[venue] = {
                _s(i): {
                    "id": _s(i),
                    "goals": _s(a.goals),
                    "own_goals": "0",
                    "shots": _s(a.shots),
                    "xG": _s(a.xg),
                    "time": _s(a.minutes),
                    "player_id": _s(a.player.id),
                    "team_id": _s(ids[team]),
                    "position": a.code,
                    "player": a.player.name,
                    "h_a": venue,
                    "yellow_card": _s(a.yellow),
                    "red_card": _s(a.red),
                    "roster_in": _s(a.start),
                    "roster_out": _s(min(a.end, 90)),
                    "key_passes": _s(a.key_passes),
                    "assists": _s(a.assists),
                    "xA": _s(a.xa),
                    "xGChain": _s(a.xgchain),
                    "xGBuildup": _s(a.xgbuildup),
                    "positionOrder": _s(i),
                }
                for i, a in enumerate(apps, start=1)
                if a.minutes > 0
            }
        return {
            "shots": {v: [self._shot_row(s, m, season) for s in m.shots[v]] for v in ("h", "a")},
            "rosters": rosters,
        }

    # ------------------------------------------------------------------ search

    def _search(self, query: str) -> list[dict]:
        needle = fold(query)
        out = []
        with self._lock:
            for code, league in self._leagues.items():
                if not league.rosters:
                    continue
                latest = max(league.rosters)
                for team, ids in league.rosters[latest].items():
                    for pid in ids:
                        player = league.players[pid]
                        if needle and needle in fold(player.name):
                            out.append({"id": _s(pid), "player": player.name, "team": team})
        return out[:20]
