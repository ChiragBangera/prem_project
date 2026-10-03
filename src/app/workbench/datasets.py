"""The scouting datasets: every player and every team of some league seasons, with every metric computed and ranked."""

from __future__ import annotations

from datetime import date

from app.analytics import matchsum
from app.analytics.players import SeasonInput, build_dataset
from app.analytics.teams import TeamInput, build_team_dataset, squad_ages
from app.workbench.part import Part


class Datasets(Part):
    async def players(self, code_seasons: list[tuple[str, int]]):
        """The scouting dataset for these league seasons, with every metric computed and ranked, and the league seasons it was built from.

        Rebuilt only when something it is made from changes.
        """
        wb = self.wb
        fetched = [await wb.seasons.load(code, s) for code, s in code_seasons]
        version = (*wb.seasons.version(*code_seasons), *(self.events.version(code, s) for code, s in code_seasons), self.repo.epochs.get("match", 0), wb.ages.roster_version())
        key = ("dataset", tuple(code_seasons))

        def compute():
            roster = wb.ages.roster_dobs()
            inputs = [self.season_input(f.data) for f in fetched]
            ds = build_dataset(inputs, favorite_of=wb.favorites.get, today=self.today,
                               dob_info=lambda name, teams, reference, pid: wb.ages.dob_info(name, teams, reference, pid, roster))
            ds.coverage = {
                "shots": {f"{i.ls.league}:{i.ls.season}": list(self.matchbook.coverage(i.ls)) for i in inputs},
                "events": {f"{i.ls.league}:{i.ls.season}": len(self.events.match_ids(i.ls.league, i.ls.season)) for i in inputs},
            }
            return ds

        return await wb.memo(key, version, compute), fetched

    async def teams(self, targets: list[tuple[str, int]]):
        """The team dataset for these league seasons (every team metric, ranked within its own league and season), and the seasons it was built from."""
        wb = self.wb
        fetched = [await wb.seasons.load(code, s) for code, s in targets]
        version = (*wb.seasons.version(*targets), *(self.events.version(code, s) for code, s in targets), self.repo.epochs.get("match", 0), wb.ages.roster_version())

        def compute():
            inputs = []
            roster = wb.ages.roster_dobs()
            for f in fetched:
                ls = f.data
                reference = min(self.today, date(ls.season + 1, 6, 30))

                def age_of(p, ls=ls, reference=reference):
                    dob, basis = wb.ages.dob_info(p.name, p.teams, reference, p.id, roster)
                    if not dob or basis == "name":
                        return None
                    born = date.fromisoformat(dob[:10])
                    return reference.year - born.year - ((reference.month, reference.day) < (born.month, born.day))

                inputs.append(TeamInput(ls, shots=self.team_shots(ls), events=wb.links.team_events(ls), ages=squad_ages(ls, age_of)))
            return build_team_dataset(inputs)

        return await wb.memo(("teams", tuple(targets)), version, compute), fetched

    # ------------------------------------------------------------------ what is known about a season, gathered for the analytics

    def season_input(self, ls) -> SeasonInput:
        """Understat's season plus what the stored match pages and the event data add to it. Blocking: call from a worker thread."""
        pages = self.matchbook.pages(ls)
        complete = self.matchbook.complete(ls, pages)
        return SeasonInput(
            ls, shots=matchsum.player_shots(pages.values()) if complete else None,
            positions=matchsum.position_minutes(pages.values()) if complete else None, events=self.wb.links.player_events(ls, pages),
        )

    def team_shots(self, ls) -> dict[str, dict] | None:
        pages = self.matchbook.pages(ls)
        if not self.matchbook.complete(ls, pages):
            return None
        return matchsum.team_shots([(f, pages[f.id]) for f in ls.fixtures if f.id in pages])
