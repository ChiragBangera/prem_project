"""The Player page: the profile, the finishing story, similar players, and where he touches the ball."""

from __future__ import annotations

from app.analytics.player_detail import player_detail
from app.analytics.player_trend import build_trend, role_reference
from app.analytics.similarity import similar_players
from app.analytics.team import squad_rows
from app.errors import AppError, NotFound
from app.events import maps as event_maps
from app.insights.core import dicts, rank
from app.analytics.metrics import GROUP_LABELS
from app.insights.player import player_insights
from app.leagues import DEFAULT_LEAGUE, FIRST_SEASON, LEAGUES, season_label
from app.workbench.pages.mapdata import map_payload
from app.workbench.part import Part


class PlayerPage(Part):
    async def page(self, player_id: int, league: str | None, season, seasons: list[int] | None = None) -> dict:
        wb = self.wb
        code = wb.seasons.league_code(league) if league else None
        if code is None:
            located = await self.locate(player_id)
            if located is None:
                raise NotFound(f"Player {player_id} is not in any cached league.", hint="Search for the player, or sync the league first.")
            code = located
        resolved, note = await wb.seasons.resolve(code, season)
        want = sorted(set(seasons or [resolved]))
        ds, fetched = await wb.datasets.players([(code, s) for s in want])
        row = next((r for r in ds.rows if r["id"] == player_id), None)
        if row is None and not seasons:
            for fallback in range(resolved - 1, max(resolved - 4, FIRST_SEASON - 1), -1):
                try:
                    ds, fetched = await wb.datasets.players([(code, fallback)])
                except AppError:
                    continue
                row = next((r for r in ds.rows if r["id"] == player_id), None)
                if row is not None:
                    want, note = [fallback], f"He has no {season_label(resolved)} minutes in this league, so showing {season_label(fallback)}."
                    break
        if row is None:
            raise NotFound(f"Player {player_id} has no minutes in {code} for {', '.join(season_label(s) for s in want)}.",
                           hint="Try another season, or another league if he moved.")

        warnings: list[str] = []
        page = None
        try:
            page = (await self.repo.player(player_id)).data
            if not wb.favorites.known(player_id):
                wb.favorites.put(player_id, page.favorite_position)
                wb.enricher.epoch += 1
                ds, fetched = await wb.datasets.players([(code, s) for s in want])
                row = next(r for r in ds.rows if r["id"] == player_id)
        except AppError as exc:
            warnings.append(f"Shot and career detail unavailable: {exc.message}")

        ls_latest = fetched[-1].data
        team_name = row["teams"][-1] if row["teams"] else None
        team_ctx = None
        if team_name and team_name in ls_latest.teams:
            squad = {r["id"]: r for r in squad_rows(ls_latest, ls_latest.teams[team_name])}
            mine = squad.get(player_id)
            if mine:
                team_ctx = {"team": team_name, "chain_share": mine["chain_share"], "share_npxg": mine["share_npxg"], "share_xa": mine["share_xa"]}
        detail = player_detail(row, page, want, team_ctx, ds.pools)
        if not detail["events"]["available"]:
            detail["events"]["stored"] = bool(self.events.seasons())  # lets the page say "not fetched for this season" only when event data exists elsewhere
        similar = similar_players(row, ds.rows, limit=8)
        insights = rank(player_insights(row, finishing=detail["finishing"], career=detail["career"], similar=similar, team_context=team_ctx))
        if not self.settings.offline:
            wb.enricher.schedule_rosters([(code, s) for s in want])
            if not self.settings.demo and row.get("age") is None and not wb.enricher.squads_pending([(code, s) for s in want]):
                wb.enricher.schedule_ages([(row["name"], team_name)])
        return {
            "scope": {"league": code, "league_name": LEAGUES[code].name, "seasons": want, "labels": [season_label(s) for s in want], "note": note,
                      "pool_minutes": ds.pool_minutes},
            "meta": {**fetched[-1].meta.to_dict(), "warnings": warnings},
            "detail": detail, "similar": similar, "insights": dicts(insights), "shortlisted": player_id in wb.shortlist.ids(),
        }

    async def similar(self, player_id: int, league: str, seasons: list[int], *, max_age: int | None, min_age: int | None,
                      min_minutes: int | None, other_leagues: list[str], limit: int = 12) -> dict:
        """Players who play like him, in his league and, if asked, in others."""
        wb = self.wb
        code = wb.seasons.league_code(league)
        targets = [(code, s) for s in seasons]
        ds, _ = await wb.datasets.players(targets)
        row = next((r for r in ds.rows if r["id"] == player_id), None)
        if row is None:
            raise NotFound(f"Player {player_id} not found in {code}.")
        rows = list(ds.rows)
        for other in other_leagues:
            oc = wb.seasons.league_code(other)
            if oc != code:
                extra, _ = await wb.datasets.players([(oc, s) for s in seasons])
                rows += extra.rows
        return {"target": row["name"], "similar": similar_players(row, rows, limit=limit, max_age=max_age, min_age=min_age, min_minutes=min_minutes)}

    async def locate(self, player_id: int) -> str | None:
        """The league a player belongs to: from his id in the demo world, otherwise from the search index of cached leagues."""
        prefix = player_id // 100_000
        if self.settings.demo and 1 <= prefix <= len(LEAGUES):
            return list(LEAGUES)[prefix - 1]
        rows = (await self.wb.search.index())[0]
        for r in rows:
            if r["id"] == player_id:
                return r["league"]
        return None

    async def maps(self, player_id: int, league: str | None, season, *, last: int | None = None) -> dict:
        """Where a player touches the ball, passes, defends and carries, from his stored matches."""
        wb = self.wb
        code = wb.seasons.league_code(league) if league else (await self.locate(player_id)) or DEFAULT_LEAGUE
        resolved, note = await wb.seasons.resolve(code, season)
        fetched = await wb.seasons.load(code, resolved)
        ls = fetched.data
        key = ("player-maps", code, resolved, player_id, last)
        version = (self.events.version(code, resolved), self.repo.version("league", f"{code}:{resolved}"), self.repo.epochs.get("match", 0))

        def compute():
            info = wb.links.for_season(ls)
            if info is None:
                return {"available": False, "reason": "No event data has been stored for this league and season yet."}
            wid = info["players"].get(player_id)
            if wid is None:
                return {"available": False, "reason": "He could not be matched safely to the event data, so no map is drawn rather than a wrong one."}
            player = info["agg"]["players"][wid]
            log = [{"game": g, "club": c, "minutes": m, "started": st} for g, c, m, st in player["log"]]
            log = log[-last:] if last else log
            if not log:
                return {"available": False, "reason": "He has no matches in the event data."}
            fixtures = info["fixtures"]
            listing = []
            for i, r in enumerate(log):
                f = fixtures.get(r["game"])
                home = f is not None and info["alias"].get(r["club"]) == f.home
                listing.append({"i": i, "game": r["game"], "date": f.date if f else None, "opp": (f.away if home else f.home) if f else None, "home": home, "minutes": round(r["minutes"]),
                                "started": r["started"], "match_id": f.id if f else None})
            games = [(i, r["game"]) for i, r in enumerate(log)]
            return map_payload(self.events, code, resolved, games, event_maps.Selection(player=wid), team=log[-1]["club"],
                               extra={"matches": listing, "ws_id": wid, "name": player["name"], "minutes": round(sum(r["minutes"] for r in log))})

        out = await wb.memo(key, version, compute)
        return {"scope": {"league": code, "season": resolved, "label": season_label(resolved), "note": note}, "player_id": player_id, **out}

    async def trend(self, player_id: int, league: str | None, season) -> dict:
        """One season of his, match by match: every metric for each match alone, as it stood after each match and over his last few appearances,
        with the opponent behind each number. Built from the stored match pages (and the event data, where there is some): nothing is fetched."""
        wb = self.wb
        code = wb.seasons.league_code(league) if league else (await self.locate(player_id)) or DEFAULT_LEAGUE
        resolved, note = await wb.seasons.resolve(code, season)
        ds, fetched = await wb.datasets.players([(code, resolved)])
        row = next((r for r in ds.rows if r["id"] == player_id), None)
        if row is None:
            raise NotFound(f"Player {player_id} has no minutes in {code} for {season_label(resolved)}.", hint="Pick another season, or another league if he moved.")
        ls = fetched[0].data
        key = ("player-trend", code, resolved, player_id)
        version = (wb.seasons.version((code, resolved)), self.events.version(code, resolved), self.repo.epochs.get("match", 0))

        def compute():
            pages = wb.matchbook.pages(ls)
            info = wb.links.for_season(ls, pages)
            out = build_trend(player_id, ls, pages, group=row["group"], name=row["name"], team=row["team"], event_counters=self._event_reader(info, player_id, code, resolved))
            if out["available"]:
                out["reference"] = role_reference(ds.rows, row["group"], out["keys"])
            return out

        out = await wb.memo(key, version, compute)
        return {
            "scope": {"league": code, "league_name": LEAGUES[code].name, "season": resolved, "label": season_label(resolved), "note": note},
            "player": {"id": player_id, "name": row["name"], "team": row["team"], "group": row["group"], "group_label": GROUP_LABELS.get(row["group"], row["group"]),
                       "pool_n": ds.group_sizes.get(row["group"], 0), "pool_minutes": ds.pool_minutes, "games": row["games"], "minutes": row["minutes"]},
            "meta": fetched[0].meta.to_dict(), **out,
        }

    def _event_reader(self, info: dict | None, player_id: int, league: str, season: int):
        """``fixture id -> his event counters in that match``; ``None`` where the match has no event data, or he could not be matched to it."""
        if info is None:
            return None
        games = {fixture.id: game for game, fixture in info["fixtures"].items()}
        wid = info["players"].get(player_id)

        def read(fixture_id: int) -> dict | None:
            game = games.get(fixture_id)
            gold = self.events.gold(league, season, game) if game is not None and wid is not None else None
            if gold is None:
                return None
            return next((r["c"] for r in gold["players"] if r["id"] == wid), None)

        return read
