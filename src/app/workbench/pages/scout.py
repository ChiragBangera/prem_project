"""The Scout and Teams pages: every player (or team) of the chosen league seasons, with every metric and its percentile, in one payload.

Nothing is filtered here beyond a one-minute floor: filtering, sorting, top-N and the map all happen in the browser.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.insights.core import dicts, rank
from app.insights.player import scouting_highlights
from app.leagues import LEAGUES, season_label
from app.workbench.part import Part


def compact_row(row: dict, keys: list[str]) -> dict:
    """One scouting row for the wire: who he is, and two arrays (values and percentiles) aligned with the dataset's ``keys``."""
    pct = row["full_pct"]
    return {
        "id": row["id"], "name": row["name"], "team": row["team"], "teams": row["teams"], "league": row["league"], "seasons": row["seasons"],
        "group": row["group"], "group_source": row["group_source"], "pos2": row["pos2"], "pos_min": dict(list(row["pos_min"].items())[:3]),
        "dob": row["dob"], "dob_basis": row["dob_basis"], "age": row["age"], "sample": row["sample"], "in_pool": row["in_pool"],
        "ev_minutes": row["ev_minutes"], "ev_matches": row["ev_matches"], "ev_in_pool": row["ev_in_pool"], "tags": row["tags"],
        "v": [row.get(k) if k not in ("age",) else row["age"] for k in keys],
        "p": [None if pct.get(k) is None else round(pct[k]) for k in keys],
    }


class ScoutPage(Part):
    async def players(self, leagues: Sequence[str], seasons: Sequence[str | int], *, min_minutes: int = 1) -> dict:
        """Every player of the chosen league seasons with every metric and its percentile. Nothing is filtered here beyond a one-minute floor:
        filtering, sorting, top-N and the map all happen in the browser, on this one payload."""
        wb = self.wb
        targets, notes = await wb.seasons.targets(leagues, seasons)
        ds, fetched = await wb.datasets.players(targets)
        rows = [r for r in ds.rows if r["minutes"] >= min_minutes]

        # background enrichment: exact birthdates from squad lists, then Wikidata for whoever they leave out (goalkeepers and
        # fringe players included, most minutes first), then positions for the ambiguous ones
        in_pool = [r for r in ds.rows if r["in_pool"] and r["group"] != "GK"]
        if not self.settings.offline:
            wb.enricher.schedule_rosters(targets)
            if not self.settings.demo and not wb.enricher.squads_pending(targets):
                unknown = sorted((r for r in ds.rows if r["age"] is None), key=lambda r: -r["minutes"])
                wb.enricher.schedule_ages((r["name"], r["teams"][0] if r["teams"] else None) for r in unknown)
            wb.enricher.schedule_roles([r["id"] for r in in_pool if r["group_source"] == "inferred"], limit=120)

        return {
            "scope": {
                "leagues": sorted({c for c, _ in targets}), "seasons": sorted({s for _, s in targets}),
                "labels": [season_label(s) for s in sorted({s for _, s in targets})], "notes": notes,
                "pool_minutes": ds.pool_minutes, "ev_pool_minutes": ds.ev_pool_minutes, "group_sizes": ds.group_sizes, "n": len(rows),
                "age_reference": ds.age_reference,
            },
            "meta": {"stale": any(f.meta.stale for f in fetched), "source": fetched[0].meta.source,
                     "fetched_at": fetched[0].meta.to_dict()["fetched_at"], "errors": [f.meta.error for f in fetched if f.meta.error]},
            "coverage": {"ages_known": ds.ages_known, "players": len(ds.rows), "inferred_roles": ds.inferred, "roles_known": len(wb.favorites),
                         "event_players": ds.event_players, "event_pool_minutes": ds.ev_pool_minutes,
                         "event_matches": sum(len(self.events.match_ids(c, s)) for c, s in targets), **ds.coverage},
            "enrichment": wb.enricher.status(),
            "keys": ds.keys, "pools": ds.pools, "rows": [compact_row(r, ds.keys) for r in rows],
            "highlights": dicts(rank(scouting_highlights(ds.rows), limit=12, per_kind=2, diversify=True)),
        }

    async def teams(self, leagues: Sequence[str], seasons: Sequence[str | int]) -> dict:
        """Every team of the chosen league seasons with every team metric and its percentile within its own league and season."""
        targets, notes = await self.wb.seasons.targets(leagues, seasons)
        ds, fetched = await self.wb.datasets.teams(targets)
        cfg = {code: LEAGUES[code] for code, _ in targets}
        keys = ds.keys
        rows = [{**{k: v for k, v in r.items() if k not in ("values", "pct")}, "v": [r["values"].get(k) for k in keys], "p": [None if r["pct"].get(k) is None else round(r["pct"][k]) for k in keys]} for r in ds.rows]
        return {
            "scope": {"leagues": sorted({c for c, _ in targets}), "seasons": sorted({s for _, s in targets}), "labels": [season_label(s) for s in sorted({s for _, s in targets})],
                      "notes": notes, "pools": ds.pools, "n": len(rows), "league_names": {c: cfg[c].name for c in cfg}},
            "meta": {"stale": any(f.meta.stale for f in fetched), "errors": [f.meta.error for f in fetched if f.meta.error]},
            "coverage": ds.coverage, "keys": keys, "rows": rows,
        }
