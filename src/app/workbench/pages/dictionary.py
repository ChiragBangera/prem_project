"""The Dictionary page: what every metric means, and what a typical, good and elite value looks like in a league season."""

from __future__ import annotations

from app.metrics.dictionary import build_dictionary
from app.workbench.pages.scout import compact_row
from app.workbench.part import Part

QUANTILES = (10, 25, 50, 75, 90)
MIN_VALUES = 8     # fewer values than this make a percentile meaningless


class DictionaryPage(Part):
    def entries(self) -> dict:
        """The data dictionary: every metric with its recipe, the raw sources and fields, the counters and the concepts."""
        return build_dictionary()

    async def stats(self, league: str, season) -> dict:
        """For each metric, what typical, good and elite look like in this league season: the 10th, 25th, 50th, 75th and 90th percentiles of the
        values of players in the ranking pool (per role group) and of teams. This is what turns a definition into a way to read a number."""
        wb = self.wb
        code, s, _fetched, scope = await wb.seasons.scope(league, season)
        ds, _ = await wb.datasets.players([(code, s)])
        teams = await wb.scout.teams([code], [s])
        version = (self.repo.version("league", f"{code}:{s}"), self.events.version(code, s), self.repo.epochs.get("match", 0))

        by_group: dict[str, list] = {}
        for r in (compact_row(r, ds.keys) for r in ds.rows):
            if r["in_pool"]:
                by_group.setdefault(r["group"], []).append(r)

        def compute():
            import numpy as np

            players: dict[str, dict[str, list]] = {}
            for i, key in enumerate(ds.keys):
                per = {}
                for group in ("ATT", "MID", "DEF", "GK"):
                    vals = [r["v"][i] for r in by_group.get(group, []) if r["v"][i] is not None]
                    if len(vals) >= MIN_VALUES:
                        per[group] = [len(vals), *[round(float(x), 4) for x in np.percentile(vals, QUANTILES)]]
                if per:
                    players[key] = per
            teams_out = {}
            for i, key in enumerate(teams["keys"]):
                vals = [r["v"][i] for r in teams["rows"] if r["v"][i] is not None]
                if len(vals) >= MIN_VALUES:
                    teams_out[key] = [len(vals), *[round(float(x), 4) for x in np.percentile(vals, QUANTILES)]]
            return {"quantiles": list(QUANTILES), "players": players, "teams": teams_out}

        stats = await wb.memo(("dict-stats", code, s), version, compute)
        return {"scope": scope, **stats}
