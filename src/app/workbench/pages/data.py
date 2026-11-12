"""The Data page: what is stored, what is missing, how fresh it is, and the controls that fetch more."""

from __future__ import annotations

import asyncio

from app.errors import BadRequest, DataUnavailable
from app.leagues import LEAGUES, current_season, season_label
from app.workbench.part import Part


class DataPage(Part):
    async def status(self) -> dict:
        from app.events import raw as R

        wb = self.wb
        boot = self.store.kv_get("boot:state") or {}
        # after an update that changed a definition, every stored match is re-derived once (a few minutes for thousands). The page must
        # answer meanwhile and say so, not wait for it: the parts that read every match are left out until it is done
        working = boot.get("stage") in ("importing", "rebuilding")
        if working:
            boot = {**boot, "done": await asyncio.to_thread(self._rebuilt_since, float(boot.get("at") or 0.0))}
        stats = self.store.stats()
        matrix = await asyncio.to_thread(self.coverage_matrix)
        reclaim = await asyncio.to_thread(R.reclaimable_bytes, self.store, self.settings.data_dir)
        return {
            "mode": {"demo": self.settings.demo, "offline": self.settings.offline, "demo_events": wb.demo_feed is not None},
            "store": {"path": str(self.settings.db_path), **stats},
            "leagues": self.repo.cached_leagues(),
            "enrichment": wb.enricher.status(),
            "jobs": wb.jobs.recent(6),
            "upstream": {"requests": getattr(wb.provider, "requests_made", None)},
            "coverage": {"favorites": len(wb.favorites)},
            "matrix": matrix,
            "auto": wb.auto.state(),
            "boot": boot or None,
            "events": await wb.links.status(light=working),
            "birthdates": await wb.ages.status(),
            "reclaimable_bytes": reclaim,
        }

    def _rebuilt_since(self, since: float) -> int:
        """How many stored matches have had their counters written since the start-up work began (read from the store's index)."""
        from app.events import counters as C

        return sum(1 for _key, written, _complete in self.store.keys(C.GOLD_KIND) if written >= since)

    def coverage_matrix(self) -> list[dict]:
        """One row per league season that is tracked or stored: what is on this computer, against what exists. Reads only the local store."""
        wb = self.wb
        seen = {(item["league"], item["season"]) for item in self.repo.cached_leagues()}
        seen.update(wb.auto.tracked())
        seen.update((lg, s) for lg, s, _n in self.events.seasons())
        out = []
        for code, season in sorted(seen, key=lambda k: (-k[1], list(LEAGUES).index(k[0]) if k[0] in LEAGUES else 99)):
            meta = self.store.meta("league", f"{code}:{season}")
            row: dict = {"league": code, "season": season, "label": season_label(season), "league_state": None if meta is None else ("final" if meta[2] else "live"),
                         "fetched_at": None if meta is None else meta[0], "played": None, "pages": None, "events": len(self.events.match_ids(code, season)), "squads": None}
            ls = self.repo.cached_league(code, season) if meta is not None else None
            if ls is not None:
                row["played"] = ls.n_played
                row["pages"] = list(wb.matchsync.coverage(ls))
                row["fixtures"] = len(ls.fixtures)
            body = wb.rosters.cached(code, season)
            row["squads"] = None if body is None else {"clubs": len(body["teams"]), "players": sum(len(t["players"]) for t in body["teams"]), "sparse": bool(body.get("sparse"))}
            row["silver"] = len(self.store.keys_prefix("ws_silver", f"{code}:{season}:")) if row["events"] else 0
            out.append(row)
        return out

    async def reclaim(self) -> dict:
        """Delete the browser tool's own copy of every event page that is safely in the store (about 1 MB each). Nothing in the store changes."""
        from app.events import raw as R

        if self.wb.auto._proc_alive():
            raise BadRequest("The event fetcher is running: wait for it to finish before reclaiming space.")
        return await asyncio.to_thread(R.reclaim, self.store, self.settings.data_dir)

    def start_sync(self, leagues: list[str], seasons: list[int], force: bool = False) -> dict:
        """Fetch these league seasons in the background; returns the job to follow."""
        if self.settings.offline:
            raise DataUnavailable("Offline mode is on: syncing is disabled.", hint="Restart without PREM_OFFLINE to fetch new data.")
        codes = [self.wb.seasons.league_code(lg) for lg in leagues]
        if not seasons:
            seasons = [current_season(self.today)]
        job = self.wb.jobs.start_sync(codes, seasons, force=force)
        return job.to_dict()
