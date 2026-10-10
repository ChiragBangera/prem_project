"""The Matches page (every fixture by matchweek) and a single match's report."""

from __future__ import annotations

import dataclasses

from app.analytics import matchsum
from app.analytics.live_page import live_match_page, live_report, score
from app.data import matchclock
from app.analytics.match import match_report
from app.analytics.match_players import build_match_players
from app.data.repository import Meta
from app.errors import BadRequest, NotFound
from app.events import ledger
from app.insights.briefing import recent_matches
from app.insights.core import dicts, rank
from app.insights.match import match_insights
from app.sync.autosync import FT_GIVE_UP, ft_retry
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
                "matches": [{**self.card(f, summaries, recent), **({"still_playing": True} if self._still_playing(code, s, f) else {})} for f in fixtures],
            })
        latest = max((r["round"] for r in rounds if any(m["played"] for m in r["matches"])), default=None)
        have = sum(1 for r in rounds for m in r["matches"] if "scorers" in m)
        return {"scope": scope, "meta": fetched.meta.to_dict(), "rounds": rounds, "latest_round": latest,
                "coverage": {"scorers": have, "played": ls.n_played, "events": len(self.events.match_ids(code, s))}}

    async def report(self, match_id: int, league: str, season) -> dict:
        """One played match: the scoreboard, the shots, the story of the game and how it was played.

        A match Understat has not published yet (being played, or just finished) is reported from its latest WhoScored read instead:
        the same report, with every shot's xG estimated (see :mod:`app.analytics.live_page`) and a ``live`` block saying so."""
        code, s, fetched, scope = await self.wb.seasons.scope(league, season)
        fixture = next((f for f in fetched.data.fixtures if f.id == match_id), None)
        if fixture is None:
            raise NotFound(f"Match {match_id} is not in {scope['league_name']} {scope['label']}.", hint="Check the league and season.")
        if not fixture.played:
            src = self._live_source(code, s, fixture)
            if src is None:
                raise BadRequest("That match has not been played yet: there are no shots to analyse.")
            live_fixture, page = self._live_page(fetched.data, fixture, s, src)
            report = live_report(live_fixture, page, src["doc"])
            report["scorers"] = {side: [{**g, "xg": None} for g in goals] for side, goals in matchsum.scorers(page).items()}
            insights: list = []   # every match insight reads xG (an own goal shows in the scorers): they come with Understat's figures
            meta = Meta("whoscored", src["at"], complete=False).to_dict(now=self.wb.auto._clock())
            return {"scope": scope, "meta": meta, "report": report, "insights": dicts(insights), "stats": _team_stats(*_sides(src["gold"])) if src["gold"] else None,
                    "live": self._live_block(fixture, src)}
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
            src = self._live_source(code, s, fixture)
            if src is None:
                raise BadRequest("That match has not been played yet: there are no players to analyse.")
            live_fixture, live = self._live_page(ls, fixture, s, src)
            ds, _fetched = await wb.datasets.players([(code, s)])
            by_ws = {r["id"]: r["c"] for r in (src["gold"] or {}).get("players", [])}
            to_ws = self._links(ls)[1]

            def counters(player_id: int) -> dict | None:
                return by_ws.get(to_ws.get(player_id) if player_id > 0 else -player_id)

            out = await wb.memo(("match-players-live", code, s, match_id), (src["at"], wb.seasons.version((code, s))),
                                lambda: build_match_players(live_fixture, live, ds.rows, league=code, season=s, event_counters=counters, without_xg=True))
            meta = Meta("whoscored", src["at"], complete=False).to_dict(now=wb.auto._clock())
            return {"scope": scope, "meta": meta, "pool_minutes": ds.pool_minutes, "group_sizes": ds.group_sizes, "live": self._live_block(fixture, src), **out}
        page = await self.repo.match(match_id, final=wb.matchsync.is_final(fixture), expect_shots=bool((fixture.hxg or 0) + (fixture.axg or 0) > 0))
        ds, _fetched = await wb.datasets.players([(code, s)])
        version = (wb.seasons.version((code, s)), self.events.version(code, s), self.repo.epochs.get("match", 0), page.meta.fetched_at)

        def compute():
            return build_match_players(fixture, page.data, ds.rows, league=code, season=s, event_counters=self._event_reader(ls, fixture, code, s))

        out = await wb.memo(("match-players", code, s, match_id), version, compute)
        return {"scope": scope, "meta": page.meta.to_dict(), "pool_minutes": ds.pool_minutes, "group_sizes": ds.group_sizes, **out}

    # ------------------------------------------------------------------ a match Understat has not published: from its WhoScored read

    def _live_source(self, code: str, season: int, fixture) -> dict | None:
        """The latest WhoScored read of a fixture (half time, in play or full time): its page, when it was read, whether WhoScored called it
        finished, and its counters. None when it has not been read."""
        note = ledger.matchday(self.store, code, season, fixture.id) or {}
        if not note.get("game") or note.get("state") not in ("final", "live"):
            return None
        game = int(note["game"])
        if self.events.has_match(code, season, game):
            doc, at, final, gold = self.events.raw.get(code, season, game), note.get("at"), True, self.events.gold(code, season, game)
        else:
            found = self.events.live(code, season, game)
            if found is None:
                return None
            doc, at, final, gold = found["doc"], found["fetched_at"], False, found["gold"]
        return None if doc is None else {"doc": doc, "at": at, "final": final, "gold": gold, "note": note, "game": game}

    def _links(self, ls) -> tuple[dict[int, int], dict[int, int]]:
        """``(WhoScored player id -> Understat id, Understat id -> WhoScored id)`` for a season, from the links already made."""
        info = self.wb.links.for_season(ls, self.wb.matchbook.pages(ls)) or {}
        to_ws = dict(info.get("players") or {})
        return {w: u for u, w in to_ws.items()}, to_ws

    def _live_page(self, ls, fixture, season: int, src: dict):
        """The fixture with the read's score and estimated xG, and the Understat-shaped page built from the read."""
        to_us, _to_ws = self._links(ls)
        page = live_match_page(src["doc"], match_id=fixture.id, season=season, home=fixture.home, away=fixture.away, date=fixture.date,
                               understat_id=to_us.get)
        hg, ag = score(src["doc"])
        return dataclasses.replace(fixture, hg=hg, ag=ag, hxg=None, axg=None), page

    def _live_block(self, fixture, src: dict) -> dict:
        """What the page says about a report made from a WhoScored read: when it was read, at what point of the match, and from when
        Understat (and with it xG) is looked for."""
        wb = self.wb
        now = wb.auto._clock()
        note = src["note"]
        kickoff = matchclock.kickoff(fixture)
        return {
            "final": src["final"], "elapsed": "FT" if src["final"] else str(note.get("elapsed") or src["doc"].get("elapsed") or ""),
            "at": src["at"], "phase": "second_half" if self._still_playing_note(fixture, note, now) else matchclock.phase(fixture, now), "moment": note.get("moment"),
            "understat_from": None if kickoff is None else kickoff + matchclock.UNDERSTAT_FIRST,
        }

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
            doc = self.events.raw.get(code, s, game) if final else (found or {}).get("doc")
            if gold is not None:
                read = {"at": at, "final": final, "elapsed": note.get("elapsed") or ("FT" if final else ""), "score": note.get("score") or "",
                        "moment": note.get("moment"), "stats": _live_stats(gold), "players": _live_players(gold), **(_live_detail(doc) if doc else {})}
        followed = wb.auto.followed(code, s, fixture) if events_on else None
        nxt = None
        if events_on and kickoff is not None and not (read and read["final"]):
            ht, ft = kickoff + matchclock.HT_READ, kickoff + matchclock.FT_READ
            if followed and wb.auto._half_time_wanted(note) and now < kickoff + matchclock.HT_READ_LAST:
                nxt = {"at": max(ht if note.get("moment") != "ht" else float(note.get("at", now)) + matchclock.HT_RETRY, now), "moment": "ht"}
            elif now < kickoff + FT_GIVE_UP:
                nxt = {"at": max(ft, now) if note.get("moment") != "ft" else max(now, float(note.get("at", now)) + ft_retry(kickoff, now)), "moment": "ft"}
        phase = ("full_time" if read and read["final"] and not fixture.played    # the page beats the clock, both ways
                 else "second_half" if self._still_playing_note(fixture, note, now) else matchclock.phase(fixture, now))
        return {"scope": scope, "fixture": self.card(fixture, {}, {}), "phase": phase, "now": now,
                "events_on": events_on, "followed": followed, "favourite": {"home": wb.favourites.follows(code, fixture.home), "away": wb.favourites.follows(code, fixture.away)},
                "read": read, "next_read": nxt}

    # ------------------------------------------------------------------ the numbers behind each fixture (also used by the briefing)

    async def summaries(self, code: str, season: int, ls) -> dict[int, dict]:
        """Per fixture id: scorers and shot counts from the stored match page, and possession and passing from the event data. Remembered."""
        version = (self.repo.version("league", f"{code}:{season}"), self.repo.epochs.get("match", 0), self.events.version(code, season))
        return await self.wb.memo(("match-summaries", code, season), version, lambda: self._summarise(ls))

    def _still_playing(self, code: str, season: int, fixture) -> bool:
        """Past full time by the clock, but the last full-time read found the match still in play (long stoppage time, extra time)."""
        if fixture.played:
            return False
        now = self.wb.auto._clock()
        if matchclock.phase(fixture, now) != "full_time":
            return False
        return self._still_playing_note(fixture, ledger.matchday(self.store, code, season, fixture.id) or {}, now)

    @staticmethod
    def _still_playing_note(fixture, note: dict, now: float) -> bool:
        """What :meth:`_still_playing` decides, from the fixture's matchday note. Full-time reads go on every few minutes while the page
        says the match is in play, so a "live" note is fresh; after FT_GIVE_UP they stop and the clock is trusted again."""
        k = matchclock.kickoff(fixture)
        return (k is not None and not fixture.played and matchclock.phase(fixture, now) == "full_time" and now < k + FT_GIVE_UP
                and note.get("moment") == "ft" and note.get("state") == "live" and str(note.get("elapsed") or "").strip().upper() != "FT")

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
                out.setdefault(fixture.id, {})["stats"] = _team_stats(a, b)
        return out


LIVE_STATS = (("goals", "Goals"), ("shots", "Shots"), ("sot", "On target"), ("bigch", "Big chances"), ("passes", "Passes"), ("pass_f3", "Passes into the final third"),
              ("touch_box", "Touches in the box"), ("tackles", "Tackles"), ("interceptions", "Interceptions"), ("corners", "Corners"), ("fouls", "Fouls"), ("yellow", "Yellow cards"))


def _team_stats(a: dict, b: dict) -> dict:
    """How each side played, from its event counters (home first): possession as the share of passes, passing, corners, fouls, cards,
    formations and managers. The match card and the report read this."""
    pa, pb = a["c"].get("passes", 0), b["c"].get("passes", 0)
    return {
        "poss": None if pa + pb == 0 else [round(100 * pa / (pa + pb)), round(100 * pb / (pa + pb))],
        "passes": [pa, pb], "pass_acc": [None if not pa else round(100 * a["c"].get("pass_ok", 0) / pa), None if not pb else round(100 * b["c"].get("pass_ok", 0) / pb)],
        "corners": [a["c"].get("corners", 0), b["c"].get("corners", 0)], "fouls": [a["c"].get("fouls", 0), b["c"].get("fouls", 0)],
        "yellow": [a["c"].get("yellow", 0), b["c"].get("yellow", 0)], "red": [a["c"].get("red", 0), b["c"].get("red", 0)],
        "formations": [a.get("formation"), b.get("formation")], "managers": [a.get("manager"), b.get("manager")],
    }


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


def _live_players(gold: dict) -> list[dict]:
    """Every player who has touched the ball so far, both sides, with the numbers a person reads during a match."""
    home, _away = _sides(gold)
    out = []
    for p in gold["players"]:
        c = p["c"]
        if not c.get("touches"):
            continue
        passes = c.get("passes", 0)
        out.append({"name": p["name"], "side": "home" if gold["teams"][p.get("tm", 0)] is home else "away", "pos": p.get("pos"), "start": p.get("start"),
                    "touches": c.get("touches", 0), "passes": passes, "pass_acc": round(100 * c.get("pass_ok", 0) / passes) if passes else None,
                    "key_passes": c.get("key_passes", 0), "shots": c.get("shots", 0), "sot": c.get("sot", 0), "goals": c.get("goals", 0),
                    "takeons_won": c.get("takeons_won", 0), "tackles": c.get("tackles", 0), "interceptions": c.get("interceptions", 0),
                    "recoveries": c.get("recoveries", 0), "fouls": c.get("fouls", 0)})
    out.sort(key=lambda r: -r["touches"])
    return out


SHOT_TYPES = {"Goal", "SavedShot", "MissedShots", "ShotOnPost", "BlockedShot"}
SITUATION = {"Penalty": "Penalty", "FromCorner": "From a corner", "SetPiece": "Set piece", "DirectFreekick": "Direct free kick", "RegularPlay": "Open play",
             "FastBreak": "Counter-attack"}
BODY = {"Head": "Head", "RightFoot": "Right foot", "LeftFoot": "Left foot", "OtherBodyPart": "Other"}


def _live_detail(doc: dict) -> dict:
    """What WhoScored's page itself says, read straight from it: every shot with its position, the goals, cards and substitutions in
    order, and both line-ups. No xG: that is Understat's, and arrives after the match."""
    names = {int(k): v for k, v in (doc.get("playerIdNameDictionary") or {}).items() if str(k).isdigit()}
    home_id = (doc.get("home") or {}).get("teamId")
    shots: dict[str, list] = {"home": [], "away": []}
    timeline = []
    for e in doc.get("events") or []:
        kind = (e.get("type") or {}).get("displayName")
        quals = {(q.get("type") or {}).get("displayName") for q in e.get("qualifiers") or []}
        side = "home" if e.get("teamId") == home_id else "away"
        minute = int(e.get("minute", 0)) + 1
        player = names.get(int(e["playerId"]), "") if e.get("playerId") is not None else ""
        if kind in SHOT_TYPES and "OwnGoal" not in quals and e.get("x") is not None:
            result = "BlockedShot" if kind == "SavedShot" and "Blocked" in quals else kind
            shots[side].append({"id": e.get("eventId") or e.get("id"), "minute": minute, "player": player, "result": result, "xg": None,
                                "x": float(e["x"]) / 100, "y": 1 - float(e.get("y", 50)) / 100,
                                "situation": next((v for k, v in SITUATION.items() if k in quals), "Open play"),
                                "type": next((v for k, v in BODY.items() if k in quals), "")})
        if kind == "Goal":
            own = "OwnGoal" in quals
            timeline.append({"minute": minute, "kind": "own_goal" if own else "penalty" if "Penalty" in quals else "goal",
                             "side": ("away" if side == "home" else "home") if own else side, "player": player})
        elif kind == "Card":
            card = "red" if quals & {"Red", "SecondYellow"} else "yellow"
            timeline.append({"minute": minute, "kind": card, "side": side, "player": player})
        elif kind == "SubstitutionOn":
            timeline.append({"minute": minute, "kind": "sub", "side": side, "player": player})
    lineups = {}
    for side in ("home", "away"):
        team = doc.get(side) or {}
        players = sorted(team.get("players") or [], key=lambda p: (not p.get("isFirstEleven"), p.get("shirtNo") or 99))
        lineups[side] = [{"name": p.get("name"), "shirt": p.get("shirtNo"), "pos": p.get("position"), "start": bool(p.get("isFirstEleven"))} for p in players]
    timeline.sort(key=lambda t: t["minute"])
    return {"shots": shots, "timeline": timeline, "lineups": lineups}
