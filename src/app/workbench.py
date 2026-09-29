"""The Workbench: everything the UI can ask for, composed from data + analytics + insights.

One object owns the store, the repository, enrichment and derived-result
caches. API routes are thin wrappers around its methods, which keeps the HTTP
layer trivial and the behaviour testable without a server.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any, Callable

from app import __version__, glossary
from app.analytics import compare as compare_engine
from app.analytics.match import match_report
from app.analytics.metrics import GROUP_LABELS, PLAYER_METRICS, PROFILE_METRICS, TEAM_METRICS
from app.analytics.player_detail import player_detail
from app.analytics.players import build_dataset
from app.analytics.similarity import similar_players
from app.analytics.table import compute_table, league_context, rank_trajectories
from app.analytics.team import find_team, squad_rows, team_profile
from app.config import Settings
from app.data.demo import DemoProvider
from app.data.repository import Fetched, Repository
from app.data.store import Store
from app.data.understat import UnderstatClient
from app.data.wikidata import BirthdateResolver
from app.enrich import Enricher, FavoriteIndex
from app.errors import AppError, BadRequest, DataUnavailable, NotFound, UpstreamError
from app.forecast.calibrate import calibrate
from app.forecast.model import Forecaster, build_forecaster, fixtures_forecast
from app.forecast.simulate import simulate_season
from app.insights.briefing import compose_insights, movers, recent_matches
from app.insights.core import Insight, dicts, rank
from app.insights.league import league_insights
from app.insights.match import match_insights
from app.insights.player import player_insights, scouting_highlights
from app.insights.team import team_insights
from app.jobs import JobManager
from app.leagues import DEFAULT_LEAGUE, FIRST_SEASON, LEAGUES, available_seasons, current_season, fold, normalize_league, season_label

MIN_ROUNDS_FOR_DEFAULT = 3  # a season with fewer rounds than this is not yet worth defaulting to
PACKAGED_MANAGERS = Path(__file__).parent / "data" / "managers.json"


class Workbench:
    def __init__(self, settings: Settings | None = None, *, provider=None, today: date | None = None):
        self.settings = settings or Settings.from_env()
        self.store = Store(self.settings.db_path)
        if provider is None:
            if self.settings.demo:
                override = os.getenv("PREM_TODAY")
                provider = DemoProvider(today=today or (date.fromisoformat(override) if override else None))
            else:
                provider = UnderstatClient(
                    timeout=self.settings.request_timeout,
                    max_concurrency=self.settings.max_concurrency,
                    min_interval=self.settings.min_interval,
                    retries=self.settings.retries,
                )
        self.provider = provider
        override = os.getenv("PREM_TODAY")
        self.today = today or (date.fromisoformat(override) if override else None) or getattr(provider, "today", None) or date.today()
        self.repo = Repository(self.store, provider, self.settings)
        self.resolver = BirthdateResolver(self.store, self.settings)
        self.favorites = FavoriteIndex(self.store)
        self.enricher = Enricher(self.repo, self.store, self.resolver, self.favorites)
        self.jobs = JobManager(self.repo, on_change=self.repo.invalidate)
        self.managers = self._load_managers()
        self._memo: dict[tuple, tuple[Any, Any]] = {}
        self._locks: dict[tuple, asyncio.Lock] = {}
        self._search_index: tuple[Any, list[dict], list[dict]] | None = None

    # ------------------------------------------------------------------ lifecycle

    async def close(self) -> None:
        await self.jobs.close()
        await self.enricher.close()
        await self.repo.close()
        self.store.close()

    # ------------------------------------------------------------------ small helpers

    def _load_managers(self) -> list[dict]:
        stints: list[dict] = []
        for path in (PACKAGED_MANAGERS, self.settings.data_dir / "managers.json"):
            try:
                stints += json.loads(path.read_text())["stints"]
            except (OSError, ValueError, KeyError):
                continue
        return stints

    def eras_for(self, league: str, team: str) -> list[dict]:
        if self.settings.demo:
            return []  # the curated stints describe real clubs
        return [s for s in self.managers if s.get("league") == league and s.get("team") == team]

    def dob_of(self, name: str, team: str | None) -> str | None:
        if self.settings.demo:
            return getattr(self.provider, "birthdate", lambda n: None)(name)
        return self.resolver.cached(name, team)

    def favorite_of(self, pid: int) -> str | None:
        return self.favorites.get(pid)

    async def _memo_async(self, key: tuple, version: Any, compute: Callable[[], Any], *, threaded: bool = True):
        hit = self._memo.get(key)
        if hit is not None and hit[0] == version:
            return hit[1]
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            hit = self._memo.get(key)
            if hit is not None and hit[0] == version:
                return hit[1]
            value = await asyncio.to_thread(compute) if threaded else compute()
            self._memo[key] = (version, value)
            if len(self._memo) > 96:
                for stale in list(self._memo)[:32]:
                    self._memo.pop(stale, None)
            return value

    def _v(self, *pairs: tuple[str, int]) -> tuple:
        return tuple(self.repo.version("league", f"{l}:{s}") for l, s in pairs) + (self.enricher.epoch,)

    # ------------------------------------------------------------------ meta

    async def meta(self) -> dict:
        seasons = self.provider.seasons() if hasattr(self.provider, "seasons") else available_seasons(self.today)
        stats = self.store.stats()
        return {
            "app": {"name": "Prem Lab", "version": __version__},
            "mode": {"demo": self.settings.demo, "offline": self.settings.offline, "source": "demo" if self.settings.demo else "understat"},
            "today": self.today.isoformat(),
            "leagues": [{"code": l.code, "name": l.name, "short": l.short, "country": l.country} for l in LEAGUES.values()],
            "seasons": [{"season": s, "label": season_label(s)} for s in seasons],
            "current_season": current_season(self.today),
            "defaults": {"league": DEFAULT_LEAGUE, "season": "auto"},
            "cache": {"leagues": self.repo.cached_leagues(), "items": stats["total_items"], "bytes": stats["total_bytes"]},
            "enrichment": self.enricher.status(),
            "jobs": self.jobs.recent(3),
        }

    def catalog(self) -> dict:
        return {
            "metrics": {m.key: m.to_dict() for m in PLAYER_METRICS},
            "team_metrics": {m.key: m.to_dict() for m in TEAM_METRICS},
            "profiles": {g: list(keys) for g, keys in PROFILE_METRICS.items()},
            "groups": GROUP_LABELS,
            "glossary": glossary.glossary_payload(),
        }

    # ------------------------------------------------------------------ league loading

    async def _load(self, league: str, season: int) -> Fetched:
        return await self.repo.league(league, season)

    async def resolve_season(self, league: str, season: str | int | None) -> tuple[int, str | None]:
        """'auto' -> the newest season with enough matches played to be worth showing."""
        if season not in (None, "", "auto"):
            return int(season), None
        current = current_season(self.today)
        try:
            fetched = await self._load(league, current)
            rounds = max((len(t.history) for t in fetched.data.teams.values()), default=0)
            if rounds >= MIN_ROUNDS_FOR_DEFAULT:
                return current, None
            note = f"{season_label(current)} has only {rounds} round(s) played, so showing {season_label(current - 1)}."
        except AppError:
            note = f"{season_label(current)} is not available yet, so showing {season_label(current - 1)}."
        if current - 1 < FIRST_SEASON:
            raise DataUnavailable("No season data is available.")
        return current - 1, note

    async def _scope(self, league: str, season: str | int | None) -> tuple[str, int, Fetched, dict]:
        code = self._league_code(league)
        resolved, note = await self.resolve_season(code, season)
        fetched = await self._load(code, resolved)
        ctx = league_context(fetched.data)
        cfg = LEAGUES[code]
        scope = {
            "league": code, "league_name": cfg.name, "season": resolved, "label": season_label(resolved), "requested": season or "auto",
            "note": note, "as_of": ctx["as_of"], "rounds_played": ctx["rounds_played"], "rounds_total": ctx["rounds_total"],
            "complete": ctx["complete"], "ucl_places": cfg.ucl_places, "relegation_places": cfg.relegation_places, "n_teams": ctx["teams"],
        }
        return code, resolved, fetched, scope

    @staticmethod
    def _league_code(value: str | None) -> str:
        try:
            return normalize_league(value)
        except ValueError as exc:
            raise BadRequest(str(exc)) from exc

    # ------------------------------------------------------------------ league & table

    async def league_view(self, league: str, season, *, venue: str = "all", last: int | None = None,
                          date_from: str | None = None, date_to: str | None = None) -> dict:
        code, s, fetched, scope = await self._scope(league, season)
        if venue not in ("all", "h", "a"):
            raise BadRequest("venue must be 'all', 'h' or 'a'.")
        ls = fetched.data
        table = compute_table(ls, venue=venue, last_n=last, date_from=date_from, date_to=date_to)
        ctx = league_context(ls)
        cfg = LEAGUES[code]
        paths = rank_trajectories(ls)
        insights = rank(league_insights(compute_table(ls), ctx, relegation_places=cfg.relegation_places))
        return {
            "scope": scope, "meta": fetched.meta.to_dict(), "context": ctx,
            "filter": {"venue": venue, "last": last, "date_from": date_from, "date_to": date_to},
            "table": table, "trajectories": paths, "insights": dicts(insights),
        }

    # ------------------------------------------------------------------ players (scouting)

    async def _dataset(self, code_seasons: list[tuple[str, int]]):
        fetched = [await self._load(code, s) for code, s in code_seasons]
        version = self._v(*code_seasons)
        key = ("dataset", tuple(code_seasons))

        def compute():
            return build_dataset([f.data for f in fetched], dob_of=self.dob_of, favorite_of=self.favorite_of, today=self.today)

        return await self._memo_async(key, version, compute), fetched

    async def players_view(self, leagues: list[str], seasons: list[str | int], *, min_minutes: int = 90) -> dict:
        codes = [self._league_code(l) for l in leagues] or [DEFAULT_LEAGUE]
        targets: list[tuple[str, int]] = []
        notes: list[str] = []
        for code in codes:
            for s in seasons or ["auto"]:
                try:
                    resolved, note = await self.resolve_season(code, s)
                    targets.append((code, resolved))
                    if note:
                        notes.append(note)
                except AppError as exc:
                    notes.append(f"{code} {s}: {exc.message}")
        targets = list(dict.fromkeys(targets))
        if not targets:
            raise DataUnavailable("None of the requested league seasons could be loaded.", hint="Open the Data page to sync, or try another season.")
        ds, fetched = await self._dataset(targets)
        rows = [r for r in ds.rows if r["minutes"] >= min_minutes]

        # background enrichment: ages for players who count, positions for the ambiguous ones
        in_pool = [r for r in ds.rows if r["in_pool"] and r["group"] != "GK"]
        if not self.settings.offline:
            if not self.settings.demo:
                self.enricher.schedule_ages((r["name"], r["teams"][0] if r["teams"] else None) for r in in_pool)
            self.enricher.schedule_roles([r["id"] for r in in_pool if r["group_source"] == "inferred"], limit=120)

        return {
            "scope": {
                "leagues": sorted({c for c, _ in targets}), "seasons": sorted({s for _, s in targets}),
                "labels": [season_label(s) for s in sorted({s for _, s in targets})], "notes": notes,
                "pool_minutes": ds.pool_minutes, "group_sizes": ds.group_sizes, "n": len(rows),
            },
            "meta": {"stale": any(f.meta.stale for f in fetched), "source": fetched[0].meta.source,
                     "fetched_at": fetched[0].meta.to_dict()["fetched_at"], "errors": [f.meta.error for f in fetched if f.meta.error]},
            "coverage": {"ages_known": ds.ages_known, "players": len(ds.rows), "inferred_roles": ds.inferred, "roles_known": len(self.favorites)},
            "enrichment": self.enricher.status(),
            "rows": rows,
            "highlights": dicts(rank(scouting_highlights(ds.rows), limit=12, per_kind=3)),
        }

    async def player_view(self, player_id: int, league: str | None, season, seasons: list[int] | None = None) -> dict:
        code = self._league_code(league) if league else None
        if code is None:
            located = await self._locate_player(player_id)
            if located is None:
                raise NotFound(f"Player {player_id} is not in any cached league.", hint="Search for the player, or sync the league first.")
            code = located
        resolved, note = await self.resolve_season(code, season)
        want = sorted(set(seasons or [resolved]))
        ds, fetched = await self._dataset([(code, s) for s in want])
        row = next((r for r in ds.rows if r["id"] == player_id), None)
        if row is None and not seasons:
            for fallback in range(resolved - 1, max(resolved - 4, FIRST_SEASON - 1), -1):
                try:
                    ds, fetched = await self._dataset([(code, fallback)])
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
            if not self.favorites.known(player_id):
                self.favorites.put(player_id, page.favorite_position)
                self.enricher.epoch += 1
                ds, fetched = await self._dataset([(code, s) for s in want])
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
        detail = player_detail(row, page, want, team_ctx)
        similar = similar_players(row, ds.rows, limit=8)
        insights = rank(player_insights(row, finishing=detail["finishing"], career=detail["career"], similar=similar, team_context=team_ctx))
        if not self.settings.demo and row.get("age") is None:
            self.enricher.schedule_ages([(row["name"], team_name)])
        shortlist = {item["id"] for item in self.store.kv_get("shortlist", [])}
        return {
            "scope": {"league": code, "league_name": LEAGUES[code].name, "seasons": want, "labels": [season_label(s) for s in want], "note": note,
                      "pool_minutes": ds.pool_minutes},
            "meta": {**fetched[-1].meta.to_dict(), "warnings": warnings},
            "detail": detail, "similar": similar, "insights": dicts(insights), "shortlisted": player_id in shortlist,
        }

    async def similar_view(self, player_id: int, league: str, seasons: list[int], *, max_age: int | None, min_age: int | None,
                           min_minutes: int | None, other_leagues: list[str], limit: int = 12) -> dict:
        code = self._league_code(league)
        targets = [(code, s) for s in seasons]
        ds, _ = await self._dataset(targets)
        row = next((r for r in ds.rows if r["id"] == player_id), None)
        if row is None:
            raise NotFound(f"Player {player_id} not found in {code}.")
        rows = list(ds.rows)
        for other in other_leagues:
            oc = self._league_code(other)
            if oc != code:
                extra, _ = await self._dataset([(oc, s) for s in seasons])
                rows += extra.rows
        return {"target": row["name"], "similar": similar_players(row, rows, limit=limit, max_age=max_age, min_age=min_age, min_minutes=min_minutes)}

    async def _locate_player(self, player_id: int) -> str | None:
        prefix = player_id // 100_000
        if self.settings.demo and 1 <= prefix <= len(LEAGUES):
            return list(LEAGUES)[prefix - 1]
        rows = (await self._index())[0]
        for r in rows:
            if r["id"] == player_id:
                return r["league"]
        return None

    async def compare_players_view(self, ids: list[int], league: str, season) -> dict:
        code, s, fetched, scope = await self._scope(league, season)
        ds, _ = await self._dataset([(code, s)])
        by_id = {r["id"]: r for r in ds.rows}
        missing = [i for i in ids if i not in by_id]
        if missing:
            raise NotFound(f"Player(s) {missing} have no minutes in {scope['league_name']} {scope['label']}.")
        rows = [by_id[i] for i in ids]
        result = compare_engine.compare_players(rows)
        result["facts"] = compare_engine.player_comparison_facts(rows)
        result["scope"] = scope
        return result

    async def compare_teams_view(self, league: str, season, a: str, b: str) -> dict:
        code, s, fetched, scope = await self._scope(league, season)
        result = compare_engine.compare_teams(fetched.data, a, b)
        result["scope"] = scope
        return result

    # ------------------------------------------------------------------ teams

    async def team_view(self, league: str, season, team: str) -> dict:
        code, s, fetched, scope = await self._scope(league, season)
        ls = fetched.data
        t = find_team(ls, team)
        profile = team_profile(ls, t.name, eras=self.eras_for(code, t.name))
        cfg = LEAGUES[code]
        insights = rank(team_insights(profile, ucl_places=cfg.ucl_places, relegation_places=cfg.relegation_places))
        forecasts = []
        try:
            fc = await self._forecaster(code, s)
            forecasts = [fc.row(f) for f in sorted(ls.upcoming, key=lambda f: f.dt) if t.name in (f.home, f.away)][:6]
        except (AppError, ValueError):
            pass
        return {"scope": scope, "meta": fetched.meta.to_dict(), "profile": profile, "insights": dicts(insights), "forecasts": forecasts,
                "teams": [{"name": x.name, "short": x.short} for x in sorted(ls.teams.values(), key=lambda x: x.name)]}

    async def team_chances_view(self, league: str, season, team: str) -> dict:
        code, s, fetched, scope = await self._scope(league, season)
        t = find_team(fetched.data, team)
        page = await self.repo.team_page(t.name, s)
        groups = page.data.groups
        situation = {r["name"]: r for r in groups.get("situation", [])}
        total_xg = sum(r["xg"] for r in situation.values()) or 1.0
        set_piece = sum(situation.get(k, {"xg": 0})["xg"] for k in ("FromCorner", "SetPiece", "DirectFreekick"))
        notes = []
        if total_xg > 5:
            share = set_piece / total_xg
            notes.append({
                "id": "chances.setpiece", "kind": "style", "tone": "neutral", "score": 50, "confidence": "medium",
                "headline": f"{round(100 * share)}% of {t.name}'s xG comes from set pieces.",
                "detail": "Most teams sit at roughly a fifth to a quarter; well above that suggests a dead-ball identity, well below an open-play one.",
                "evidence": [{"label": "Set-piece xG", "value": f"{set_piece:.1f}"}, {"label": "Total xG", "value": f"{total_xg:.1f}"}], "entities": [], "link": None,
            })
        return {"scope": scope, "meta": page.meta.to_dict(), "team": t.name, "groups": groups, "insights": notes}

    # ------------------------------------------------------------------ matches

    async def matches_view(self, league: str, season) -> dict:
        code, s, fetched, scope = await self._scope(league, season)
        ls = fetched.data
        by_round: dict[int, list] = {}
        for f in sorted(ls.fixtures, key=lambda f: (f.dt, f.id)):
            by_round.setdefault(f.round, []).append(f)
        rounds = []
        recent = {m["id"]: m for m in recent_matches(ls, limit=len(ls.fixtures))}
        for number, fixtures in sorted(by_round.items()):
            rounds.append({
                "round": number, "from": fixtures[0].date, "to": fixtures[-1].date, "played": all(f.played for f in fixtures),
                "matches": [
                    {"id": f.id, "date": f.date, "dt": f.dt, "home": f.home, "away": f.away, "home_short": f.home_short, "away_short": f.away_short,
                     "played": f.played, "hg": f.hg, "ag": f.ag, "hxg": None if f.hxg is None else round(f.hxg, 2), "axg": None if f.axg is None else round(f.axg, 2),
                     "flag": recent.get(f.id, {}).get("flag"),
                     "forecast": None if f.forecast is None else {"home": round(f.forecast[0], 3), "draw": round(f.forecast[1], 3), "away": round(f.forecast[2], 3)}}
                    for f in fixtures
                ],
            })
        latest = max((r["round"] for r in rounds if any(m["played"] for m in r["matches"])), default=None)
        return {"scope": scope, "meta": fetched.meta.to_dict(), "rounds": rounds, "latest_round": latest}

    async def match_view(self, match_id: int, league: str, season) -> dict:
        code, s, fetched, scope = await self._scope(league, season)
        fixture = next((f for f in fetched.data.fixtures if f.id == match_id), None)
        if fixture is None:
            raise NotFound(f"Match {match_id} is not in {scope['league_name']} {scope['label']}.", hint="Check the league and season.")
        if not fixture.played:
            raise BadRequest("That match has not been played yet: there are no shots to analyse.")
        page = await self.repo.match(match_id, final=True)
        report = match_report(fixture, page.data)
        insights = rank(match_insights(report))
        return {"scope": scope, "meta": page.meta.to_dict(), "report": report, "insights": dicts(insights)}

    # ------------------------------------------------------------------ forecast

    async def _forecaster(self, code: str, season: int) -> Forecaster:
        fetched = await self._load(code, season)
        prior = None
        try:
            prior = (await self._load(code, season - 1)).data if season - 1 >= FIRST_SEASON else None
        except AppError:
            prior = None
        version = self._v((code, season), *(((code, season - 1),) if prior is not None else ()))
        return await self._memo_async(("forecaster", code, season), version, lambda: build_forecaster(fetched.data, prior, as_of=self.today.isoformat()))

    async def forecast_fixtures_view(self, league: str, season, limit: int = 12) -> dict:
        code, s, fetched, scope = await self._scope(league, season)
        try:
            fc = await self._forecaster(code, s)
        except ValueError as exc:
            raise DataUnavailable(str(exc), hint="Forecasts appear once about eight matches have been played.") from exc
        rows = fixtures_forecast(fc, fetched.data, limit=limit)
        return {"scope": scope, "meta": fetched.meta.to_dict(), "fixtures": rows, "model": {"used_previous_season": fc.used_previous_season,
                "rho": round(fc.ratings.rho, 3), "home_advantage": round(float(math.exp(fc.ratings.home) - 1), 3),
                "matches": fc.ratings.n_matches, "weights": {"ratings": fc.weight, "elo": round(1 - fc.weight, 2)}}}

    async def forecast_match_view(self, league: str, season, home: str, away: str) -> dict:
        code, s, fetched, scope = await self._scope(league, season)
        ls = fetched.data
        h, a = find_team(ls, home), find_team(ls, away)
        if h.name == a.name:
            raise BadRequest("Pick two different teams.")
        try:
            fc = await self._forecaster(code, s)
        except ValueError as exc:
            raise DataUnavailable(str(exc)) from exc
        understat = next((f.forecast for f in ls.upcoming if f.home == h.name and f.away == a.name), None)
        return {"scope": scope, "meta": fetched.meta.to_dict(), "forecast": fc.predict(h.name, a.name, understat=understat),
                "teams": [{"name": x.name, "short": x.short} for x in sorted(ls.teams.values(), key=lambda x: x.name)]}

    async def forecast_season_view(self, league: str, season, n_sims: int = 4000) -> dict:
        code, s, fetched, scope = await self._scope(league, season)
        try:
            fc = await self._forecaster(code, s)
        except ValueError as exc:
            raise DataUnavailable(str(exc), hint="The season simulation needs at least eight played matches.") from exc
        n_sims = max(500, min(int(n_sims), 20000))
        version = self._v((code, s), (code, s - 1))
        sim = await self._memo_async(("sim", code, s, n_sims), version, lambda: simulate_season(fc, fetched.data, n_sims=n_sims))
        return {"scope": scope, "meta": fetched.meta.to_dict(), "simulation": sim}

    async def calibration_view(self, league: str, season) -> dict:
        code, s, fetched, scope = await self._scope(league, season)
        prior = None
        try:
            prior = (await self._load(code, s - 1)).data if s - 1 >= FIRST_SEASON else None
        except AppError:
            pass
        version = self._v((code, s), (code, s - 1))
        try:
            result = await self._memo_async(("calibration", code, s), version, lambda: calibrate(fetched.data, prior))
        except ValueError as exc:
            raise DataUnavailable(str(exc)) from exc
        return {"scope": scope, "meta": fetched.meta.to_dict(), "calibration": result}

    # ------------------------------------------------------------------ briefing

    async def briefing_view(self, league: str, season) -> dict:
        code, s, fetched, scope = await self._scope(league, season)
        ls = fetched.data
        cfg = LEAGUES[code]
        ctx = league_context(ls)
        table = compute_table(ls)
        league_side = league_insights(table, ctx, relegation_places=cfg.relegation_places)
        ds, _ = await self._dataset([(code, s)])
        front = compose_insights(league_side, scouting_highlights(ds.rows), limit=8)

        upcoming: list[dict] = []
        race = None
        try:
            fc = await self._forecaster(code, s)
            upcoming = fixtures_forecast(fc, ls, limit=10)
            if not ctx["complete"]:
                sim = await self._memo_async(("sim", code, s, 2000), self._v((code, s), (code, s - 1)), lambda: simulate_season(fc, ls, n_sims=2000))
                race = [{k: t[k] for k in ("team", "short", "points", "exp_points", "p_title", "p_top4", "p_relegation", "played")} for t in sim["teams"]]
        except (AppError, ValueError):
            pass

        return {
            "scope": scope, "meta": fetched.meta.to_dict(), "context": ctx, "insights": dicts(front),
            "table": [{k: r[k] for k in ("rank", "team", "short", "played", "pts", "gd", "xpts", "xpts_gap", "xgd_pg", "form", "trend_xgd", "rank_xpts")} for r in table],
            "recent": recent_matches(ls, limit=10), "movers": movers(ls), "upcoming": upcoming, "race": race,
            "highlights": dicts(rank(scouting_highlights(ds.rows), limit=6, per_kind=2)),
        }

    # ------------------------------------------------------------------ search

    async def _index(self):
        cached = self.repo.cached_leagues()
        latest: dict[str, list[int]] = {}
        for item in cached:
            latest.setdefault(item["league"], []).append(item["season"])
        keep = [(l, s) for l, seasons in latest.items() for s in sorted(seasons, reverse=True)[:2]]
        token = tuple(sorted(keep)) + self._v(*keep)
        if self._search_index is not None and self._search_index[0] == token:
            return self._search_index[1], self._search_index[2]
        players: dict[int, dict] = {}
        teams: dict[tuple[str, str], dict] = {}
        for league, season in sorted(keep, key=lambda t: t[1]):  # newest season last, so it wins
            try:
                ls = (await self._load(league, season)).data
            except AppError:
                continue
            for team in ls.teams.values():
                teams[(league, team.name)] = {"name": team.name, "short": team.short, "league": league, "season": season}
            for p in ls.players:
                players[p.id] = {"id": p.id, "name": p.name, "team": p.team, "league": league, "season": season, "minutes": p.minutes, "key": fold(p.name)}
        rows, team_rows = list(players.values()), list(teams.values())
        self._search_index = (token, rows, team_rows)
        return rows, team_rows

    async def search_view(self, query: str, limit: int = 8) -> dict:
        needle = fold(query)
        if len(needle) < 2:
            return {"players": [], "teams": []}
        rows, teams = await self._index()
        tokens = needle.split()

        def score(text: str) -> int | None:
            if not all(t in text for t in tokens):
                return None
            if text.startswith(needle):
                return 0
            if any(w.startswith(needle) for w in text.split()):
                return 1
            return 2 if all(any(w.startswith(t) for w in text.split()) for t in tokens) else 3

        found = []
        for r in rows:
            s = score(r["key"])
            if s is not None:
                found.append((s, -r["minutes"], r))
        found.sort(key=lambda x: (x[0], x[1]))
        team_hits = []
        for t in teams:
            s = score(fold(t["name"])) if score(fold(t["name"])) is not None else score(fold(t["short"]))
            if s is not None:
                team_hits.append((s, t["name"], t))
        team_hits.sort(key=lambda x: (x[0], x[1]))
        return {"players": [{k: v for k, v in r.items() if k != "key"} for _s, _m, r in found[:limit]], "teams": [t for _s, _n, t in team_hits[:5]]}

    # ------------------------------------------------------------------ shortlist

    def shortlist(self) -> list[dict]:
        return self.store.kv_get("shortlist", [])

    def shortlist_add(self, item: dict) -> list[dict]:
        pid = int(item["id"])
        items = [i for i in self.shortlist() if i["id"] != pid]
        existing = next((i for i in self.shortlist() if i["id"] == pid), {})
        items.insert(0, {"id": pid, "name": item.get("name", existing.get("name", "")), "team": item.get("team", existing.get("team", "")),
                         "league": item.get("league", existing.get("league", DEFAULT_LEAGUE)), "note": item.get("note", existing.get("note", "")),
                         "added": existing.get("added") or int(time.time())})
        self.store.kv_set("shortlist", items)
        return items

    def shortlist_remove(self, player_id: int) -> list[dict]:
        items = [i for i in self.shortlist() if i["id"] != player_id]
        self.store.kv_set("shortlist", items)
        return items

    # ------------------------------------------------------------------ data status & sync

    async def data_status(self) -> dict:
        stats = self.store.stats()
        return {
            "mode": {"demo": self.settings.demo, "offline": self.settings.offline},
            "store": {"path": str(self.settings.db_path), **stats},
            "leagues": self.repo.cached_leagues(),
            "enrichment": self.enricher.status(),
            "jobs": self.jobs.recent(6),
            "upstream": {"requests": getattr(self.provider, "requests_made", None)},
            "coverage": {"favorites": len(self.favorites)},
        }

    def start_sync(self, leagues: list[str], seasons: list[int], force: bool = False) -> dict:
        if self.settings.offline:
            raise DataUnavailable("Offline mode is on: syncing is disabled.", hint="Restart without PREM_OFFLINE to fetch new data.")
        codes = [self._league_code(l) for l in leagues]
        if not seasons:
            seasons = [current_season(self.today)]
        job = self.jobs.start_sync(codes, seasons, force=force)
        return job.to_dict()
