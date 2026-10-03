"""The connection check: walk the real data path once and say which step breaks."""

from __future__ import annotations

import time
from typing import Any

from app.data.normalize import normalize_league as parse_league
from app.data.normalize import normalize_match_page, normalize_player_page
from app.errors import AppError, DataUnavailable
from app.leagues import DEFAULT_LEAGUE, LEAGUES, current_season, season_label
from app.workbench.part import Part


class Diagnostics(Part):
    async def check(self) -> dict:
        """Walk the real data path once (league -> match -> player -> squad list -> birthdates) and say which step breaks.

        Nothing is written to the cache: this is what to run when Understat changes its pages or the network is odd.
        """
        wb = self.wb
        steps: list[dict] = []
        state: dict[str, Any] = {}

        async def step(name: str, action) -> bool:
            started = time.perf_counter()
            entry: dict[str, Any] = {"name": name, "ok": True, "detail": "", "hint": None}
            try:
                entry["detail"] = await action()
            except AppError as exc:
                entry.update(ok=False, detail=exc.message, hint=exc.hint)
            except Exception as exc:  # noqa: BLE001 - any surprise is exactly what this check exists to surface
                entry.update(ok=False, detail=f"{type(exc).__name__}: {str(exc)[:160]}", hint="Please report this with the detail above.")
            entry["ms"] = round((time.perf_counter() - started) * 1000)
            steps.append(entry)
            return entry["ok"]

        code = DEFAULT_LEAGUE
        season = current_season(self.today)

        async def fetch_league() -> str:
            for candidate in (season, season - 1):
                try:
                    raw = await wb.provider.league(code, candidate)
                except AppError:
                    if candidate == season - 1:
                        raise
                    continue
                state["raw_league"], state["season"] = raw, candidate
                return f"{season_label(candidate)} {LEAGUES[code].name}: received {len(raw)} sections"
            raise DataUnavailable("No league data came back.")

        async def read_league() -> str:
            ls = parse_league(state["raw_league"], code, state["season"])
            state["ls"] = ls
            if not ls.teams or not ls.fixtures:
                raise DataUnavailable("The page arrived but no teams or fixtures could be read from it.", hint="Understat may have changed its page format.")
            note = f"; {len(ls.warnings)} rows skipped" if ls.warnings else ""
            return f"{len(ls.teams)} teams, {len(ls.fixtures)} fixtures ({ls.n_played} played), {len(ls.players)} players{note}"

        async def read_match() -> str:
            played = state["ls"].played
            if not played:
                return "No match has been played yet, so there is nothing to read."
            page = normalize_match_page(await wb.provider.match(played[-1].id), played[-1].id)
            return f"Match {played[-1].id}: {sum(len(v) for v in page.shots.values())} shots, {sum(len(v) for v in page.rosters.values())} lineup rows"

        async def read_player() -> str:
            players = sorted(state["ls"].players, key=lambda p: -p.minutes)
            if not players:
                return "No players in the league page."
            page = normalize_player_page(await wb.provider.player(players[0].id), players[0].id)
            return f"{players[0].name}: {len(page.shots)} career shots, {len(page.career)} seasons"

        async def read_birthdates() -> str:
            if self.settings.demo:
                return "Demo mode: birthdates come from the demo world."
            if self.settings.offline:
                return "Offline mode: Wikidata was not contacted."
            found = await wb.resolver.resolve([("Erling Haaland", "Manchester City")])
            value = next(iter(found.values()), None)
            return f"Wikidata answered: Erling Haaland born {value}" if value else "Wikidata answered but had no birthdate for the test player."

        async def read_squads() -> str:
            if self.settings.demo:
                return "Demo mode: squad lists are not used."
            if self.settings.offline:
                return "Offline mode: ESPN was not contacted."
            return await wb.rosters.probe(code, season)

        if await step("Reach Understat" if not self.settings.demo else "Load the league", fetch_league) and await step("Read the league page", read_league):
            await step("Read a match", read_match)
            await step("Read a player", read_player)
        await step("Read a squad list", read_squads)
        await step("Look up birthdates", read_birthdates)
        return {"ok": all(s["ok"] for s in steps), "mode": {"demo": self.settings.demo, "offline": self.settings.offline}, "steps": steps}
