"""The Matches page (every fixture by matchweek) and a single match's report."""

from __future__ import annotations

from app.analytics import matchsum
from app.data import matchclock
from app.analytics.match import match_report
from app.analytics.match_players import build_match_players
from app.errors import BadRequest, NotFound
from app.events import ledger
from app.insights.briefing import recent_matches
from app.insights.core import dicts, rank
from app.insights.match import match_insights
from app.sync.autosync import FT_GIVE_UP, FT_RETRY
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

    async def players(self, match_id: int, league: str, season) -> dict:
        """Every player who played in the match with every Scout metric for that match alone, ranked against the season numbers of role peers."""
        wb = self.wb
        code, s, fetched, scope = await wb.seasons.scope(league, season)
        ls = fetched.data
        fixture = next((f for f in ls.fixtures if f.id == match_id), None)
        if fixture is None:
            raise NotFound(f"Match {match_id} is not in {scope['league_name']} {scope['label']}.", hint="Check the league and season.")
        if not fixture.played:
            raise BadRequest("That match has not been played yet: there are no players to analyse.")
        page = await self.repo.match(match_id, final=wb.matchsync.is_final(fixture), expect_shots=bool((fixture.hxg or 0) + (fixture.axg or 0) > 0))
        ds, _fetched = await wb.datasets.players([(code, s)])
        version = (wb.seasons.version((code, s)), self.events.version(code, s), self.repo.epochs.get("match", 0), page.meta.fetched_at)

        def compute():
            return build_match_players(fixture, page.data, ds.rows, league=code, season=s, event_counters=self._event_reader(ls, fixture, code, s))

        out = await wb.memo(("match-players", code, s, match_id), version, compute)
        return {"scope": scope, "meta": page.meta.to_dict(), "pool_minutes": ds.pool_minutes, "group_sizes": ds.group_sizes, **out}

    def _event_reader(self, ls, fixture, code: str, season: int):
        """``Understat player id -> his event counters in this match``; ``None`` for everyone when the match has no event data."""
        wb = self.wb
        info = wb.links.for_season(ls, wb.matchbook.pages(ls))
        if info is None:
            return None
        game = next((g for g, f in info["fixtures"].items() if f.id == fixture.id), None)
        gold = self.events.gold(code, season, game) if game is not None else None
        if gold is None:
            return None
        by_ws = {r["id"]: r["c"] for r in gold["players"]}
        to_ws = info["players"]

        def read(player_id: int) -> dict | None:
            wid = to_ws.get(player_id)
            return by_ws.get(wid) if wid is not None else None

        return read

    # ------------------------------------------------------------------ a match being played (or just finished, before Understat has it)

    async def live(self, match_id: int, league: str, season, *, follow: bool = False) -> dict:
        """A match by the clock and by its latest matchday read: where it is (first half, half time ...), what WhoScored's page said when it
        was last read (minute, score, and the team numbers so far: provisional until full time), and when the next read happens.

        ``follow`` says someone has the match open: while it is being played it is then followed (read at half time too)."""
        wb = self.wb
        code, s, fetched, scope = await wb.seasons.scope(league, season)
        fixture = next((f for f in fetched.data.fixtures if f.id == match_id), None)
        if fixture is None:
            raise NotFound(f"Match {match_id} is not in {scope['league_name']} {scope['label']}.", hint="Check the league and season.")
        now = wb.auto._clock()
        kickoff = matchclock.kickoff(fixture)
        events_on = wb.auto.events_enabled() and code in wb.auto.prefs()["events"]["leagues"]
        window = kickoff is not None and kickoff - 30 * 60 <= now < kickoff + FT_GIVE_UP
        if follow and events_on and window and not fixture.played and kickoff is not None:
            wb.auto.follow(code, s, fixture.id, kickoff + FT_GIVE_UP)
        note = ledger.matchday(self.store, code, s, fixture.id) or {}
        read = None
        if note.get("game") and note.get("state") in ("final", "live"):
            game = int(note["game"])
            if self.events.has_match(code, s, game):
                gold, at, final = self.events.gold(code, s, game), note.get("at"), True
            else:
                found = self.events.live(code, s, game)
                gold, at, final = (found["gold"], found["fetched_at"], False) if found else (None, None, False)
            if gold is not None:
                read = {"at": at, "final": final, "elapsed": note.get("elapsed") or ("FT" if final else ""), "score": note.get("score") or "",
                        "moment": note.get("moment"), "stats": _live_stats(gold), "players": _live_players(gold)}
        followed = wb.auto.followed(code, s, fixture) if events_on else None
        nxt = None
        if events_on and kickoff is not None and not (read and read["final"]):
            ht, ft = kickoff + matchclock.HALF_TIME, kickoff + matchclock.FULL_TIME
            if followed and note.get("moment") not in ("ht", "ft") and now < kickoff + matchclock.HALF_TIME_END:
                nxt = {"at": max(ht, now), "moment": "ht"}
            elif now < kickoff + FT_GIVE_UP:
                nxt = {"at": max(ft, now) if note.get("moment") != "ft" else max(now, float(note.get("at", now)) + FT_RETRY), "moment": "ft"}
        return {"scope": scope, "fixture": self.card(fixture, {}, {}), "phase": matchclock.phase(fixture, now), "now": now,
                "events_on": events_on, "followed": followed, "favourite": {"home": wb.favourites.follows(code, fixture.home), "away": wb.favourites.follows(code, fixture.away)},
                "read": read, "next_read": nxt}

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


LIVE_STATS = (("goals", "Goals"), ("shots", "Shots"), ("sot", "On target"), ("bigch", "Big chances"), ("passes", "Passes"), ("pass_f3", "Passes into the final third"),
              ("touch_box", "Touches in the box"), ("tackles", "Tackles"), ("interceptions", "Interceptions"), ("corners", "Corners"), ("fouls", "Fouls"), ("yellow", "Yellow cards"))


def _sides(gold: dict) -> tuple[dict, dict]:
    teams = gold["teams"]
    home = next((t for t in teams if t.get("side") == "home"), teams[0])
    away = next((t for t in teams if t is not home), teams[-1])
    return home, away


def _live_stats(gold: dict) -> dict:
    """The team numbers of a match read on matchday, home first: possession (share of passes), then the counts the live view lists."""
    home, away = _sides(gold)
    a, b = home["c"], away["c"]
    pa, pb = a.get("passes", 0), b.get("passes", 0)
    return {
        "teams": [home["name"], away["name"]], "formations": [home.get("formation"), away.get("formation")],
        "poss": None if pa + pb == 0 else [round(100 * pa / (pa + pb)), round(100 * pb / (pa + pb))],
        "pass_acc": [None if not pa else round(100 * a.get("pass_ok", 0) / pa), None if not pb else round(100 * b.get("pass_ok", 0) / pb)],
        "rows": [{"key": k, "label": label, "home": a.get(k, 0), "away": b.get(k, 0)} for k, label in LIVE_STATS],
    }


def _live_players(gold: dict, n: int = 5) -> dict:
    """Each side's most involved players so far (by touches), with their shots, key passes and tackles."""
    home, away = _sides(gold)
    out: dict[str, list] = {"home": [], "away": []}
    for side, team in (("home", home), ("away", away)):
        rows = [p for p in gold["players"] if gold["teams"][p.get("tm", 0)] is team and p["c"].get("touches", 0) > 0]
        rows.sort(key=lambda p: -p["c"].get("touches", 0))
        out[side] = [{"name": p["name"], "pos": p.get("pos"), "touches": p["c"].get("touches", 0), "shots": p["c"].get("shots", 0),
                      "key_passes": p["c"].get("key_passes", 0), "tackles": p["c"].get("tackles", 0)} for p in rows[:n]]
    return out
