"""Shared fixtures. No test in this suite touches the real network."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.data.repository import Repository
from app.data.store import Store


def _double_round_robin(teams):
    """Circle-method schedule: every team plays exactly once per round."""
    n, ring, first = len(teams), list(teams), []
    for r in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = ring[i], ring[n - 1 - i]
            pairs.append((a, b) if (r + i) % 2 == 0 else (b, a))
        first.append(pairs)
        ring = [ring[0], ring[-1]] + ring[1:-1]
    second = [[(b, a) for a, b in pairs] for pairs in first]
    return [(r, h, a) for r, pairs in enumerate(first + second) for h, a in pairs]


def raw_league(teams=("Alpha FC", "Beta United", "Gamma City", "Delta Town"), played=True, start="2025-08-16"):
    """A tiny but realistic Understat ``getLeagueData`` payload (double round robin).

    Numbers are strings where Understat sends strings (players, fixtures) and
    numeric in team history, exactly like the live site.
    """
    from datetime import date, timedelta

    schedule = _double_round_robin(teams)
    day0 = date.fromisoformat(start)
    dates, history = [], {t: [] for t in teams}
    for i, (round_index, home, away) in enumerate(schedule):
        when = (day0 + timedelta(days=7 * round_index)).isoformat() + " 15:00:00"
        is_played = played if isinstance(played, bool) else i < played
        hg, ag = (i % 3), ((i + 1) % 2)
        hxg, axg = 1.0 + 0.3 * (i % 4), 0.6 + 0.2 * (i % 3)
        dates.append(
            {
                "id": str(1000 + i),
                "isResult": is_played,
                "h": {"id": str(teams.index(home) + 1), "title": home, "short_title": home[:3].upper()},
                "a": {"id": str(teams.index(away) + 1), "title": away, "short_title": away[:3].upper()},
                "goals": {"h": str(hg) if is_played else None, "a": str(ag) if is_played else None},
                "xG": {"h": f"{hxg:.5f}" if is_played else None, "a": f"{axg:.5f}" if is_played else None},
                "datetime": when,
                "forecast": {"w": "0.5", "d": "0.3", "l": "0.2"} if not is_played else {"w": "0.4", "d": "0.3", "l": "0.3"},
            }
        )
        if not is_played:
            continue
        for team, venue, gf, ga, xg, xga in (
            (home, "h", hg, ag, hxg, axg),
            (away, "a", ag, hg, axg, hxg),
        ):
            pts = 3 if gf > ga else 1 if gf == ga else 0
            history[team].append(
                {
                    "h_a": venue,
                    "xG": xg,
                    "xGA": xga,
                    "npxG": xg - 0.1,
                    "npxGA": xga - 0.1,
                    "deep": 5 + i % 4,
                    "deep_allowed": 4 + i % 3,
                    "scored": gf,
                    "missed": ga,
                    "xpts": round(1.4 + (xg - xga) * 0.5, 4),
                    "result": "w" if gf > ga else "d" if gf == ga else "l",
                    "date": when,
                    "wins": int(gf > ga),
                    "draws": int(gf == ga),
                    "loses": int(gf < ga),
                    "pts": pts,
                    "npxGD": round(xg - xga, 4),
                    "ppda": {"att": 200 + 10 * (i % 5), "def": 20 + (i % 4)},
                    "ppda_allowed": {"att": 180 + 5 * (i % 5), "def": 18 + (i % 3)},
                }
            )
    players = [
        {
            "id": "101", "player_name": "Ann Striker", "games": "8", "time": "640", "goals": "6", "xG": "4.8",
            "assists": "1", "xA": "0.9", "shots": "22", "key_passes": "5", "yellow_cards": "1", "red_cards": "0",
            "position": "F S", "team_title": teams[0], "npg": "5", "npxG": "4.0", "xGChain": "6.1", "xGBuildup": "1.2",
        },
        {
            "id": "102", "player_name": "Bo Playmaker", "games": "8", "time": "700", "goals": "1", "xG": "0.9",
            "assists": "4", "xA": "3.1", "shots": "6", "key_passes": "21", "yellow_cards": "0", "red_cards": "0",
            "position": "M", "team_title": teams[0], "npg": "1", "npxG": "0.9", "xGChain": "8.0", "xGBuildup": "5.5",
        },
        {
            "id": "103", "player_name": "Cy Traveller", "games": "6", "time": "420", "goals": "2", "xG": "1.7",
            "assists": "0", "xA": "0.3", "shots": "9", "key_passes": "3", "yellow_cards": "0", "red_cards": "0",
            "position": "F M S", "team_title": f"{teams[1]},{teams[2]}", "npg": "2", "npxG": "1.7", "xGChain": "2.0",
            "xGBuildup": "0.4",
        },
        {
            "id": "104", "player_name": "Di Keeper", "games": "8", "time": "720", "goals": "0", "xG": "0",
            "assists": "0", "xA": "0", "shots": "0", "key_passes": "0", "yellow_cards": "0", "red_cards": "0",
            "position": "GK", "team_title": teams[3], "npg": "0", "npxG": "0", "xGChain": "0.3", "xGBuildup": "0.3",
        },
    ]
    return {
        "teams": {
            str(i + 1): {"id": str(i + 1), "title": t, "history": history[t]} for i, t in enumerate(teams)
        },
        "players": players,
        "dates": dates,
    }


def raw_player_page():
    shots = [
        {
            "id": "9001", "minute": "23", "result": "Goal", "X": "0.912", "Y": "0.48", "xG": "0.35", "player": "Ann Striker",
            "h_a": "h", "player_id": "101", "situation": "OpenPlay", "season": "2025", "shotType": "RightFoot",
            "match_id": "1000", "h_team": "Alpha FC", "a_team": "Beta United", "h_goals": "2", "a_goals": "1",
            "date": "2025-08-16 15:00:00", "player_assisted": "Bo Playmaker", "lastAction": "Pass",
        },
        {
            "id": "9002", "minute": "71", "result": "SavedShot", "X": "0.85", "Y": "0.62", "xG": "0.08", "player": "Ann Striker",
            "h_a": "a", "player_id": "101", "situation": "FromCorner", "season": "2024", "shotType": "Head",
            "match_id": "900", "h_team": "Beta United", "a_team": "Alpha FC", "h_goals": "0", "a_goals": "0",
            "date": "2025-01-11 15:00:00", "player_assisted": None, "lastAction": "Cross",
        },
    ]
    return {
        "player": {"favorite_position": "FW"},
        "shots": shots,
        "matches": [],
        "groups": {
            "season": [
                {"season": "2024", "team": "Alpha FC", "position": "FW", "games": "30", "time": "2400", "goals": "15",
                 "xG": "13.2", "assists": "3", "xA": "2.5", "shots": "80", "key_passes": "20", "yellow_cards": "2",
                 "red_cards": "0", "npg": "13", "npxG": "11.9", "xGChain": "20", "xGBuildup": "5"},
                {"season": "2025", "team": "Alpha FC", "position": "FW", "games": "8", "time": "640", "goals": "6",
                 "xG": "4.8", "assists": "1", "xA": "0.9", "shots": "22", "key_passes": "5", "yellow_cards": "1",
                 "red_cards": "0", "npg": "5", "npxG": "4.0", "xGChain": "6.1", "xGBuildup": "1.2"},
            ],
            "situation": {
                "2025": [
                    {"situation": "OpenPlay", "shots": "18", "goals": "4", "xG": "3.1"},
                    {"situation": "Penalty", "shots": "1", "goals": "1", "xG": "0.76"},
                ]
            },
            "shotZones": {"2025": [{"shotZones": "shotPenaltyArea", "shots": "15", "goals": "4", "xG": "3.3"}]},
            "shotTypes": {"2025": {"0": {"shotTypes": "RightFoot", "shots": "14", "goals": "4", "xG": "3.0"}}},
            "position": {"2025": [{"position": "FW", "games": "8", "time": "640", "goals": "6", "xG": "4.8"}]},
        },
    }


def raw_match_page():
    def shot(minute, xg, result, venue, player, x=0.88, y=0.5):
        return {
            "id": str(minute), "minute": str(minute), "result": result, "X": str(x), "Y": str(y), "xG": str(xg),
            "player": player, "h_a": venue, "situation": "OpenPlay", "season": "2025", "shotType": "LeftFoot",
            "match_id": "1000", "h_team": "Alpha FC", "a_team": "Beta United", "date": "2025-08-16 15:00:00",
            "lastAction": "Pass", "player_id": "101",
        }

    return {
        "shots": {
            "h": [shot(10, 0.3, "Goal", "h", "Ann Striker"), shot(55, 0.1, "SavedShot", "h", "Bo Playmaker")],
            "a": [shot(33, 0.6, "Goal", "a", "Eve Winger"), shot(80, 0.05, "MissedShots", "a", "Eve Winger")],
        },
        "rosters": {
            "h": {"1": {"id": "1", "player_id": "101", "player": "Ann Striker", "position": "FW", "time": "90",
                        "goals": "1", "own_goals": "0", "shots": "1", "xG": "0.3", "key_passes": "0", "assists": "0",
                        "xA": "0", "xGChain": "0.4", "xGBuildup": "0", "yellow_card": "0", "red_card": "0"}},
            "a": {"2": {"id": "2", "player_id": "201", "player": "Eve Winger", "position": "AMR", "time": "90",
                        "goals": "1", "own_goals": "0", "shots": "2", "xG": "0.65", "key_passes": "1", "assists": "0",
                        "xA": "0.1", "xGChain": "0.9", "xGBuildup": "0.1", "yellow_card": "1", "red_card": "0"}},
        },
    }


class FakeProvider:
    """Stands in for Understat: canned payloads, call counting, injectable failures."""

    source = "understat"

    def __init__(self, league=None, delay=0.0):
        self.league_payload = league if league is not None else raw_league()
        self.calls: list[tuple] = []
        self.fail: Exception | None = None
        self.delay = delay

    async def _maybe_fail(self):
        import asyncio

        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail is not None:
            raise self.fail

    async def league(self, league, season):
        self.calls.append(("league", league, season))
        await self._maybe_fail()
        return self.league_payload

    async def team(self, team, season):
        self.calls.append(("team", team, season))
        await self._maybe_fail()
        return {"statistics": {"situation": {"OpenPlay": {"shots": 100, "goals": 10, "xG": 9.5, "against": {"shots": 90, "goals": 8, "xG": 8.1}}}}}

    async def player(self, player_id):
        self.calls.append(("player", player_id))
        await self._maybe_fail()
        return raw_player_page()

    async def match(self, match_id):
        self.calls.append(("match", match_id))
        await self._maybe_fail()
        return raw_match_page()

    async def search_players(self, query):
        self.calls.append(("search", query))
        return [{"id": "101", "player": "Ann Striker", "team": "Alpha FC"}]

    async def close(self):
        pass


class Clock:
    def __init__(self, now=1_780_000_000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path, min_interval=0.0, max_concurrency=4)


@pytest.fixture
def store(tmp_path: Path):
    s = Store(tmp_path / "test.sqlite")
    yield s
    s.close()


@pytest.fixture
def provider():
    return FakeProvider()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def repo(store, provider, settings, clock):
    return Repository(store, provider, settings, clock=clock)


# ---------------------------------------------------------------------- demo data (shared, built once)


@pytest.fixture(scope="session")
def demo_provider():
    from datetime import date

    from app.data.demo import DemoProvider

    return DemoProvider(today=date(2021, 1, 15))  # 2019 complete, 2020 mid-season


@pytest.fixture(scope="session")
def demo_league(demo_provider):
    """A complete, simulated EPL season as typed models (2019)."""
    import asyncio

    from app.data.normalize import normalize_league

    return normalize_league(asyncio.run(demo_provider.league("EPL", 2019)), "EPL", 2019)


@pytest.fixture(scope="session")
def demo_league_partial(demo_provider):
    import asyncio

    from app.data.normalize import normalize_league

    return normalize_league(asyncio.run(demo_provider.league("EPL", 2020)), "EPL", 2020)
