"""The Matches page (every fixture by matchweek) and a single match's report."""

from __future__ import annotations

from app.analytics import matchsum
from app.analytics.match import match_report
from app.errors import BadRequest, NotFound
from app.insights.briefing import recent_matches
from app.insights.core import dicts, rank
from app.insights.match import match_insights
from app.workbench.part import Part


class MatchesPage(Part):
    async def season(self, league: str, season) -> dict:
        """Every fixture by matchweek, each with its score, who scored, and the numbers behind the result."""
        code, s, fetched, scope = await self.wb.seasons.scope(league, season)
        ls = fetched.data
        summaries = await self.summaries(code, s, ls)
        by_round: dict[int, list] = {}
        for f in sorted(ls.fixtures, key=lambda f: (f.dt, f.id)):
            by_round.setdefault(f.round, []).append(f)
        recent = {m["id"]: m for m in recent_matches(ls, limit=len(ls.fixtures))}
        rounds = []
        for number, fixtures in sorted(by_round.items()):
            rounds.append({
                "round": number, "from": fixtures[0].date, "to": fixtures[-1].date, "played": all(f.played for f in fixtures),
                "matches": [self.card(f, summaries, recent) for f in fixtures],
            })
        latest = max((r["round"] for r in rounds if any(m["played"] for m in r["matches"])), default=None)
        have = sum(1 for r in rounds for m in r["matches"] if "scorers" in m)
        return {"scope": scope, "meta": fetched.meta.to_dict(), "rounds": rounds, "latest_round": latest,
                "coverage": {"scorers": have, "played": ls.n_played, "events": len(self.events.match_ids(code, s))}}

    async def report(self, match_id: int, league: str, season) -> dict:
        """One played match: the scoreboard, the shots, the story of the game and how it was played."""
        code, s, fetched, scope = await self.wb.seasons.scope(league, season)
        fixture = next((f for f in fetched.data.fixtures if f.id == match_id), None)
        if fixture is None:
            raise NotFound(f"Match {match_id} is not in {scope['league_name']} {scope['label']}.", hint="Check the league and season.")
        if not fixture.played:
            raise BadRequest("That match has not been played yet: there are no shots to analyse.")
        page = await self.repo.match(match_id, final=self.wb.matchsync.is_final(fixture), expect_shots=bool((fixture.hxg or 0) + (fixture.axg or 0) > 0))
        report = match_report(fixture, page.data)
        report["scorers"] = matchsum.scorers(page.data)
        insights = rank(match_insights(report))
        return {"scope": scope, "meta": page.meta.to_dict(), "report": report, "insights": dicts(insights),
                "stats": (await self.summaries(code, s, fetched.data)).get(match_id, {}).get("stats")}

    # ------------------------------------------------------------------ the numbers behind each fixture (also used by the briefing)

    async def summaries(self, code: str, season: int, ls) -> dict[int, dict]:
        """Per fixture id: scorers and shot counts from the stored match page, and possession and passing from the event data. Remembered."""
        version = (self.repo.version("league", f"{code}:{season}"), self.repo.epochs.get("match", 0), self.events.version(code, season))
        return await self.wb.memo(("match-summaries", code, season), version, lambda: self._summarise(ls))

    @staticmethod
    def card(f, summaries: dict, recent: dict) -> dict:
        """One fixture as the match card shows it: teams, score, kickoff (UTC), the result's flag, and whatever the stored pages add (scorers, possession ...)."""
        return {"id": f.id, "date": f.date, "dt": f.dt, "utc": f.dt[:10] + "T" + f.dt[11:19] + "Z" if len(f.dt) >= 19 else None, "round": f.round,
                "home": f.home, "away": f.away, "home_short": f.home_short, "away_short": f.away_short,
                "played": f.played, "hg": f.hg, "ag": f.ag, "hxg": None if f.hxg is None else round(f.hxg, 2), "axg": None if f.axg is None else round(f.axg, 2),
                "flag": recent.get(f.id, {}).get("flag"), **summaries.get(f.id, {})}

    def _summarise(self, ls) -> dict[int, dict]:
        """The work behind :meth:`summaries`. Blocking."""
        pages = self.matchbook.pages(ls)
        out: dict[int, dict] = {}
        for f in ls.fixtures:
            page = pages.get(f.id)
            if page is not None:
                out[f.id] = matchsum.fixture_summary(f, page)
        info = self.wb.links.for_season(ls, pages)
        if info is not None:
            for gid, fixture in info["fixtures"].items():
                gold = self.events.gold(ls.league, ls.season, gid)
                if gold is None:
                    continue
                home_name = info["alias"].get(gold["teams"][0]["name"])
                flip = home_name is not None and home_name != fixture.home
                a, b = (gold["teams"][1], gold["teams"][0]) if flip else (gold["teams"][0], gold["teams"][1])
                pa, pb = a["c"].get("passes", 0), b["c"].get("passes", 0)
                out.setdefault(fixture.id, {})["stats"] = {
                    "poss": None if pa + pb == 0 else [round(100 * pa / (pa + pb)), round(100 * pb / (pa + pb))],
                    "passes": [pa, pb], "pass_acc": [None if not pa else round(100 * a["c"].get("pass_ok", 0) / pa), None if not pb else round(100 * b["c"].get("pass_ok", 0) / pb)],
                    "corners": [a["c"].get("corners", 0), b["c"].get("corners", 0)], "fouls": [a["c"].get("fouls", 0), b["c"].get("fouls", 0)],
                    "yellow": [a["c"].get("yellow", 0), b["c"].get("yellow", 0)], "red": [a["c"].get("red", 0), b["c"].get("red", 0)],
                    "formations": [a["formation"], b["formation"]], "managers": [a["manager"], b["manager"]],
                }
        return out
