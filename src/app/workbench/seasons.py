"""Which league season a request means, and the loaded data for it."""

from __future__ import annotations

from collections.abc import Sequence

from app.analytics.table import league_context
from app.data.repository import Fetched
from app.errors import AppError, BadRequest, DataUnavailable
from app.leagues import DEFAULT_LEAGUE, FIRST_SEASON, LEAGUES, current_season, normalize_league, season_label
from app.workbench.part import Part

MIN_ROUNDS_FOR_DEFAULT = 3  # a season with fewer rounds than this is not yet worth defaulting to


class Seasons(Part):
    async def load(self, league: str, season: int) -> Fetched:
        return await self.repo.league(league, season)

    async def resolve(self, league: str, season: str | int | None) -> tuple[int, str | None]:
        """'auto' -> the newest season with enough matches played to be worth showing."""
        if season not in (None, "", "auto"):
            return int(season), None
        current = current_season(self.today)
        try:
            fetched = await self.load(league, current)
            rounds = max((len(t.history) for t in fetched.data.teams.values()), default=0)
            if rounds >= MIN_ROUNDS_FOR_DEFAULT:
                return current, None
            note = f"{season_label(current)} has only {rounds} round(s) played, so showing {season_label(current - 1)}."
        except AppError:
            note = f"{season_label(current)} is not available yet, so showing {season_label(current - 1)}."
        if current - 1 < FIRST_SEASON:
            raise DataUnavailable("No season data is available.")
        return current - 1, note

    async def scope(self, league: str, season: str | int | None) -> tuple[str, int, Fetched, dict]:
        """``(league code, season, its data, the scope block every page starts with)``."""
        code = self.league_code(league)
        resolved, note = await self.resolve(code, season)
        fetched = await self.load(code, resolved)
        ctx = league_context(fetched.data)
        cfg = LEAGUES[code]
        scope = {
            "league": code, "league_name": cfg.name, "season": resolved, "label": season_label(resolved), "requested": season or "auto",
            "note": note, "as_of": ctx["as_of"], "rounds_played": ctx["rounds_played"], "rounds_total": ctx["rounds_total"],
            "complete": ctx["complete"], "ucl_places": cfg.ucl_places, "relegation_places": cfg.relegation_places, "n_teams": ctx["teams"],
        }
        return code, resolved, fetched, scope

    @staticmethod
    def league_code(value: str | None) -> str:
        try:
            return normalize_league(value)
        except ValueError as exc:
            raise BadRequest(str(exc)) from exc

    async def targets(self, leagues: Sequence[str], seasons: Sequence[str | int]) -> tuple[list[tuple[str, int]], list[str]]:
        """The league seasons a multi-league request means, and a note for each one that had to be replaced or could not be loaded."""
        codes = [self.league_code(lg) for lg in leagues] or [DEFAULT_LEAGUE]
        targets: list[tuple[str, int]] = []
        notes: list[str] = []
        for code in codes:
            for s in seasons or ["auto"]:
                try:
                    resolved, note = await self.resolve(code, s)
                    targets.append((code, resolved))
                    if note:
                        notes.append(note)
                except AppError as exc:
                    notes.append(f"{code} {s}: {exc.message}")
        targets = list(dict.fromkeys(targets))
        if not targets:
            raise DataUnavailable("None of the requested league seasons could be loaded.", hint="Open the Data page to sync, or try another season.")
        return targets, notes

    def version(self, *pairs: tuple[str, int]) -> tuple:
        """A token that changes when any of these league seasons, or the enrichment of their players, does."""
        return tuple(self.repo.version("league", f"{lg}:{s}") for lg, s in pairs) + (self.wb.enricher.epoch,)
