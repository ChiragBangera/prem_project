"""How WhoScored's event data lines up with Understat's seasons: the same matches, clubs and players, found under two different names."""

from __future__ import annotations

import json
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

from app.data.people import plays_for
from app.errors import AppError
from app.events import ledger
from app.events.link import link_by_lineups, link_fixtures, link_season
from app.events.store import STATUS_PREFIX
from app.leagues import fold
from app.workbench.part import Part

OVERRIDE_PREFIX = "links:override:"   # a person's own links for a league season: {"players": {WhoScored id: Understat id or 0}, "matches": {game: fixture id}}

if TYPE_CHECKING:  # pragma: no cover
    from app.workbench.core import Workbench


class EventLinks(Part):
    def __init__(self, wb: Workbench) -> None:
        super().__init__(wb)
        self._links: dict[tuple[str, int], tuple[Any, dict]] = {}

    # ------------------------------------------------------------------ a person's own links

    def overrides(self, league: str, season: int) -> dict:
        saved = self.store.kv_get(f"{OVERRIDE_PREFIX}{league}:{season}") or {}
        return {"players": {int(k): int(v) for k, v in (saved.get("players") or {}).items()},
                "matches": {int(k): int(v) for k, v in (saved.get("matches") or {}).items()}}

    def set_override(self, league: str, season: int, kind: str, ws: int, us: int | None) -> dict:
        """Link a WhoScored player (or match) to an Understat one by hand; ``us=0`` says a player is not in Understat at all (leave him out,
        and stop listing him); ``us=None`` forgets the person's choice and lets the automatic matching decide again."""
        if kind not in ("players", "matches"):
            raise AppError("kind must be players or matches")
        current = self.overrides(league, season)
        book = current[kind]
        if us is None:
            book.pop(int(ws), None)
        else:
            if kind == "matches" and not us:
                raise AppError("A match can only be linked to a fixture.")
            for other in [w for w, u in book.items() if u and u == us and w != ws]:
                book.pop(other)                       # one Understat player (or fixture) belongs to one WhoScored one
            book[int(ws)] = int(us)
        self.store.kv_set(f"{OVERRIDE_PREFIX}{league}:{season}", {k: {str(a): b for a, b in v.items()} for k, v in current.items()})
        self._links.pop((league, season), None)
        return current

    def _override_version(self, league: str, season: int) -> str:
        return json.dumps(self.store.kv_get(f"{OVERRIDE_PREFIX}{league}:{season}") or {}, sort_keys=True)

    def for_season(self, ls, pages=None) -> dict | None:
        """How WhoScored's matches, clubs and players line up with this Understat season, remembered until either side changes. None without event data.

        A person's own links (:meth:`set_override`) come first and always win: the WhoScored and Understat players (and matches) they name are
        taken out of the automatic matching, so it can neither undo nor duplicate them.
        """
        agg = self.events.season(ls.league, ls.season)
        if not agg["games"]:
            return None
        version = (self.events.version(ls.league, ls.season), self.repo.version("league", f"{ls.league}:{ls.season}"), self.repo.epochs.get("match", 0),
                   self._override_version(ls.league, ls.season))
        hit = self._links.get((ls.league, ls.season))
        if hit is not None and hit[0] == version:
            return hit[1]
        manual = self.overrides(ls.league, ls.season)
        fixtures, alias, unlinked_matches = link_fixtures(agg, ls.fixtures)
        by_fixture = {f.id: f for f in ls.fixtures}
        for game, fid in manual["matches"].items():
            f = by_fixture.get(fid)
            if f is None:
                continue
            for other in [g for g, fx in fixtures.items() if fx.id == fid and g != game]:
                fixtures.pop(other)
            fixtures[game] = f
        unlinked_matches = [m for m in unlinked_matches if m["game"] not in fixtures]
        manual_ws = set(manual["players"])
        manual_us = {u for u in manual["players"].values() if u}
        totals = {pid: {"id": pid, "name": p["name"], "teams": p["teams"], "min": p["c"].get("min", 0)} for pid, p in agg["players"].items() if pid not in manual_ws}
        linked, unlinked = link_season(totals, [p for p in ls.players if p.id not in manual_us], alias)
        players = {uid: t["id"] for uid, t in linked.items()}
        by_id = {}
        if unlinked:
            pages = self.matchbook.pages(ls) if pages is None else pages
            if pages:
                left = [agg["players"][u["id"]] for u in unlinked]
                extra = link_by_lineups(left, ls.players, pages, fixtures, alias, taken=set(players) | manual_us)
                players.update(extra)
                by_id = {w: uid for uid, w in extra.items()}
        for ws, us in manual["players"].items():
            if us and ws in agg["players"]:
                players[us] = ws
        left_out = [u for u in unlinked if u["id"] not in by_id]
        info = {"agg": agg, "fixtures": fixtures, "alias": alias, "players": players, "unlinked_matches": unlinked_matches, "unlinked_players": left_out, "manual": manual}
        self._links[(ls.league, ls.season)] = (version, info)
        return info

    def player_events(self, ls, pages=None) -> dict[int, dict] | None:
        """Understat player id -> his event counters for this season. None when no event data has been stored for it."""
        info = self.for_season(ls, pages)
        if info is None:
            return None
        players = info["agg"]["players"]
        return {uid: {"c": players[w]["c"], "matches": players[w]["matches"], "starts": players[w]["starts"], "pos": players[w]["pos"]} for uid, w in info["players"].items()}

    def team_events(self, ls) -> dict[str, dict] | None:
        """Understat club -> its event totals (for and against) for this season. None without event data."""
        info = self.for_season(ls)
        if info is None:
            return None
        out = {}
        for ws, t in info["agg"]["teams"].items():
            us = info["alias"].get(ws)
            if us in ls.teams:
                out[us] = {"c": t["c"], "a": t["a"], "matches": t["matches"], "formations": t["formations"], "managers": t["managers"]}
        return out

    async def status(self) -> list[dict]:
        """Per league-season: matches stored, how many exist, how well they line up with Understat, and the state of any fetching run."""
        seen: dict[tuple[str, int], None] = {(lg, s): None for lg, s, _n in self.events.seasons()}
        for key in self.store.kv_prefix(STATUS_PREFIX):
            name, _, year = key[len(STATUS_PREFIX):].partition(":")
            if year.isdigit():
                seen.setdefault((name, int(year)), None)
        out = []
        for league, season in sorted(seen):
            entry: dict = {"league": league, "season": season, "matches": len(self.events.match_ids(league, season)), "total": None,
                           "failed_n": len(ledger.failures(self.store, league, season)),
                           "status": self.events.status(league, season), "linked": None, "unlinked": [], "unlinked_n": 0, "matches_linked": None}
            if self.store.meta("league", f"{league}:{season}") is not None:   # only from the cache: this must never go to the network
                try:
                    fetched = await self.wb.seasons.load(league, season)
                    entry["total"] = len(fetched.data.played)
                    if entry["matches"]:
                        version = (self.events.version(league, season), self.repo.version("league", f"{league}:{season}"), self.repo.epochs.get("match", 0),
                                   self._override_version(league, season))

                        def report(ls=fetched.data):
                            info = self.for_season(ls)
                            if info is None:
                                return {}
                            left = sorted(info["unlinked_players"], key=lambda u: -u["minutes"])
                            return {"linked": len(info["players"]), "unlinked": left[:10], "unlinked_n": len(left),
                                    "matches_linked": len(info["fixtures"]), "matches_unlinked": len(info["unlinked_matches"])}

                        entry.update(await self.wb.memo(("events-link", league, season), version, report))
                except AppError:
                    pass
            out.append(entry)
        return out

    # ------------------------------------------------------------------ what the Data page shows for a person to review

    def review(self, league: str, season: int) -> dict:
        """The players and matches the automatic matching could not place (with the likeliest Understat candidates for each), the person's own
        links, and the matches the fetcher could not read. From the store only: this never goes to the network."""
        ls = self.repo.cached_league(league, season)
        failed = [{"game": g, **e, "waiting": ledger.waiting_for_person(e)} for g, e in sorted(ledger.failures(self.store, league, season).items())]
        empty = {"league": league, "season": season, "players": [], "matches": [], "manual": [], "failed": failed}
        if ls is None:
            return {**empty, "available": False}
        info = self.for_season(ls)
        if info is None:
            return {**empty, "available": True}
        agg, alias = info["agg"], info["alias"]
        taken = set(info["players"])
        free = [p for p in ls.players if p.id not in taken]
        players = []
        for u in sorted(info["unlinked_players"], key=lambda x: -x["minutes"]):
            clubs = [alias.get(c, c) for c in u["teams"]]
            mine = fold(u["name"])

            def likeness(p, mine=mine):
                return round(SequenceMatcher(None, mine, fold(p.name)).ratio(), 2)

            def rank(p, clubs=clubs, likeness=likeness) -> tuple[bool, float]:
                return (not plays_for(clubs, p.teams), -likeness(p))

            ranked = sorted(free, key=rank)[:6]
            players.append({"ws": u["id"], "name": u["name"], "clubs": clubs, "minutes": round(u["minutes"]),
                            "candidates": [{"id": p.id, "name": p.name, "team": " / ".join(p.teams), "same_club": plays_for(clubs, p.teams), "likeness": likeness(p),
                                            "minutes": round(p.minutes or 0)} for p in ranked]})
        used = {f.id for f in info["fixtures"].values()}
        matches = []
        for m in info["unlinked_matches"]:
            home, away = alias.get(m["home"], m["home"]), alias.get(m["away"], m["away"])
            near = []
            for f in ls.fixtures:
                gap = _gap(m["date"], f.date)
                if f.id not in used and gap is not None and gap <= 3 and (home in (f.home, f.away) or away in (f.home, f.away)):
                    near.append((gap, f))
            pair = {home, away}
            near.sort(key=lambda t: (pair != {t[1].home, t[1].away}, t[0]))  # the same two clubs first, then the closest date
            matches.append({"game": m["game"], "date": m["date"][:10], "home": m["home"], "away": m["away"], "score": m.get("score"),
                            "candidates": [{"id": f.id, "date": f.date[:10], "home": f.home, "away": f.away, "hg": f.hg, "ag": f.ag, "played": f.played, "days": gap}
                                           for gap, f in near[:5]]})
        names = {p.id: p.name for p in ls.players}
        fixtures = {f.id: f for f in ls.fixtures}
        manual = [{"kind": "players", "ws": ws, "ws_name": agg["players"].get(ws, {}).get("name", str(ws)), "us": us, "us_name": names.get(us) if us else None}
                  for ws, us in info["manual"]["players"].items()]
        manual += [{"kind": "matches", "ws": g, "ws_name": _game_label(agg, g), "us": fid,
                    "us_name": f"{fixtures[fid].home} v {fixtures[fid].away}, {fixtures[fid].date[:10]}" if fid in fixtures else str(fid)}
                   for g, fid in info["manual"]["matches"].items()]
        return {"league": league, "season": season, "available": True, "players": players, "matches": matches, "manual": manual, "failed": failed}


def _gap(a: str, b: str) -> int | None:
    from datetime import date as _d

    try:
        return abs((_d.fromisoformat(a[:10]) - _d.fromisoformat(b[:10])).days)
    except ValueError:
        return None


def _game_label(agg: dict, game: int) -> str:
    for team in agg["teams"].values():
        for row in team["log"]:
            if row["game"] == game and row["home"]:
                return f"{team['name']} v {row['opp']}, {row['date'][:10]}"
    return str(game)
