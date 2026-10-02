"""The Workbench: everything the UI can ask for, composed from data + analytics + insights.

One object owns the store, the repository, enrichment and derived-result
caches. API routes are thin wrappers around its methods, which keeps the HTTP
layer trivial and the behaviour testable without a server.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable

from app import __version__
from app.analytics import compare as compare_engine
from app.analytics import matchsum
from app.analytics.chances import MIN_LEAGUE_TEAMS, chance_insights, compare_to_league, league_baseline, prepare_breakdowns
from app.analytics.match import match_report
from app.analytics.player_detail import player_detail
from app.analytics.players import SeasonInput, build_dataset
from app.analytics.similarity import similar_players
from app.analytics.table import compute_table, league_context, rank_trajectories
from app.analytics.teams import TeamInput, build_team_dataset, squad_ages
from app.analytics.team import find_team, squad_rows, team_history, team_profile
from app.config import Settings
from app.data.demo import WORLD_VERSION, DemoProvider
from app.data.matchbook import MatchBook
from app.data.matchsync import MatchSync
from app.data.rosters import RosterClient, link_roster
from app.data.repository import Fetched, Repository
from app.data.store import Store
from app.data.understat import UnderstatClient
from app.data.normalize import normalize_league as parse_league, normalize_match_page, normalize_player_page
from app.data.wikidata import BirthdateResolver
from app.enrich import Enricher, FavoriteIndex
from app.events import maps as event_maps
from app.events.link import link_by_lineups, link_fixtures, link_season
from app.events.store import DERIVED_MARK, STATUS_PREFIX, EventStore
from app.errors import AppError, BadRequest, DataUnavailable, NotFound
from app.insights.briefing import compose_insights, movers, recent_matches
from app.insights.core import dicts, rank
from app.insights.league import league_insights
from app.insights.match import match_insights
from app.insights.player import player_insights, scouting_highlights
from app.insights.team import team_insights
from app.jobs import JobManager
from app.leagues import DEFAULT_LEAGUE, FIRST_SEASON, LEAGUES, available_seasons, current_season, fold, normalize_league, season_label
from app.metrics.catalog import build_catalog
from app.metrics.dictionary import build_dictionary
from app.sync.autosync import AutoSync
from app.sync.demofeed import DemoEventFeed

MIN_ROUNDS_FOR_DEFAULT = 3  # a season with fewer rounds than this is not yet worth defaulting to
CONTESTED_DAYS = 366  # a squad list and a club-confirmed Wikidata entry more than a year apart cannot both be right about one man
HISTORY_DEFAULT_SEASONS = 5
HISTORY_MAX_SEASONS = 8  # one colour each in the charts
PACKAGED_MANAGERS = Path(__file__).parent / "data" / "managers.json"


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


class Workbench:
    def __init__(self, settings: Settings | None = None, *, provider=None, today: date | None = None):
        self.settings = settings or Settings.from_env()
        self.store = Store(self.settings.db_path)
        if self.settings.demo:
            self._refresh_demo_world()
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
        self.events = EventStore(self.store)
        self.matchbook = MatchBook(self.repo)
        self.matchsync = MatchSync(self.repo)
        self._catalog = build_catalog()
        self.auto = AutoSync(self)
        self.demo_feed: DemoEventFeed | None = None
        self._boot_task: asyncio.Task | None = None
        self._links: dict[tuple[str, int], tuple[Any, dict]] = {}
        self.rosters = RosterClient(self.store, self.settings, today=lambda: self.today)
        self._roster_links: dict[tuple[str, int], tuple[Any, tuple[dict, list]]] = {}
        self._dob_index: tuple[tuple, dict[int, str]] | None = None
        self.enricher = Enricher(self.repo, self.store, self.resolver, self.favorites, roster_client=self.rosters)
        self.jobs = JobManager(self.repo, on_change=self.repo.invalidate, rosters=self.rosters)
        self.managers = self._load_managers()
        self.birthdates = self._load_birthdates()
        self._memo: dict[tuple, tuple[Any, Any]] = {}
        self._locks: dict[tuple, asyncio.Lock] = {}
        self._search_index: tuple[Any, list[dict], list[dict]] | None = None

    def _refresh_demo_world(self) -> None:
        """The demo world is made from code, so a copy stored by an older version of it would disagree with this one: start it afresh. Your shortlist stays."""
        if self.store.kv_get("demo:world") == WORLD_VERSION:
            return
        self.store.clear()
        for key in self.store.kv_prefix(STATUS_PREFIX):
            self.store.kv_delete(key)
        self.store.kv_delete(DERIVED_MARK)
        self.store.kv_set("demo:world", WORLD_VERSION)

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        """Begin the work that happens while the app runs: adopt stored event pages, bring derived layers up to date, start the updater."""
        self._boot_task = asyncio.create_task(self._boot())
        self.auto.start()
        if self.settings.demo and self.settings.demo_events:
            self.demo_feed = DemoEventFeed(self)
            self.demo_feed.start()

    async def _boot(self) -> None:
        """First thing after start: put every stored event page into the store and rebuild what older code made. Quick when nothing changed."""
        from app.events import raw as R

        try:
            self.store.kv_set("boot:state", {"stage": "importing", "at": time.time()})
            adopted = await asyncio.to_thread(R.import_soccerdata_cache, self.store, self.settings.data_dir)
            pending = await asyncio.to_thread(self.events.pending_rebuild)
            if pending:
                self.store.kv_set("boot:state", {"stage": "rebuilding", "total": pending, "at": time.time()})
                await asyncio.to_thread(self.events.ensure_current)
            self.store.kv_set("boot:state", {"stage": "done", "adopted": adopted["imported"], "rebuilt": pending, "at": time.time()})
        except Exception as exc:  # pragma: no cover - defensive: a failure here must not stop the app
            self.store.kv_set("boot:state", {"stage": "failed", "error": f"{type(exc).__name__}: {str(exc)[:160]}", "at": time.time()})

    async def close(self) -> None:
        if self.demo_feed is not None:
            await self.demo_feed.close()
        await self.auto.close()
        if self._boot_task is not None and not self._boot_task.done():
            self._boot_task.cancel()
            await asyncio.gather(self._boot_task, return_exceptions=True)
        await self.jobs.close()
        await self.enricher.close()
        await self.rosters.close()
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

    def _load_birthdates(self) -> dict[str, str]:
        """Your own corrections: ``<data dir>/birthdates.json`` as ``{"Name": "YYYY-MM-DD"}`` or ``{"Name|Club": ...}``.

        They win over Wikidata, which cannot always tell namesakes apart. Read once at start-up.
        """
        try:
            raw = json.loads((self.settings.data_dir / "birthdates.json").read_text())
        except (OSError, ValueError):
            return {}
        out: dict[str, str] = {}
        for key, value in (raw.items() if isinstance(raw, dict) else []):
            try:
                date.fromisoformat(str(value)[:10])
            except ValueError:
                continue
            name, _, club = str(key).partition("|")
            out[f"{fold(name)}|{fold(club)}" if club else fold(name)] = str(value)[:10]
        return out

    def eras_for(self, league: str, team: str) -> list[dict]:
        if self.settings.demo:
            return []  # the curated stints describe real clubs
        return [s for s in self.managers if s.get("league") == league and s.get("team") == team]

    def dob_info(self, name: str, teams, reference: date | None = None, pid: int | None = None, roster: dict[int, str] | None = None) -> tuple[str | None, str | None]:
        """``(dob, basis)``. In order of trust: your correction (``"manual"``), the club's squad list (``"roster"``: exact, and the
        person is already known to be at that club), then Wikidata matched on a ``"club"`` or on the ``"name"`` alone."""
        clubs = [t for t in ([teams] if isinstance(teams, str) else list(teams or [])) if t]
        key = fold(name)
        for club in clubs:
            if hit := self.birthdates.get(f"{key}|{fold(club)}"):
                return hit, "manual"
        if hit := self.birthdates.get(key):
            return hit, "manual"
        if roster and pid in roster:
            if self._contested(roster[pid], name, clubs, reference):
                return None, None  # two sources that cannot both be right: a blank age beats a coin toss (the Data page lists these)
            return roster[pid], "roster"
        if self.settings.demo:
            return getattr(self.provider, "birthdate", lambda n, t=None: None)(name, clubs[0] if clubs else None), None
        return self.resolver.cached_info(name, clubs, reference)

    def _contested(self, dob: str, name: str, clubs: list[str], reference: date | None) -> str | None:
        """Wikidata's date for him when it is sure of the club and is more than a year from ``dob``; otherwise None."""
        other, basis = self.resolver.cached_info(name, clubs, reference)
        if other and basis == "club" and abs((date.fromisoformat(other) - date.fromisoformat(dob)).days) > CONTESTED_DAYS:
            return other
        return None

    def dob_of(self, name: str, team: str | None, reference: date | None = None) -> str | None:
        return self.dob_info(name, team, reference)[0]

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
            "auto": self.auto.brief(),
        }

    def catalog(self) -> dict:
        """The metric registry for the browser: every metric, group, column preset and lens."""
        return self._catalog

    def dictionary(self) -> dict:
        """The data dictionary: every metric with its recipe, the raw sources and fields, the counters and the concepts."""
        return build_dictionary()

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
        """The scouting dataset for these league seasons, with every metric computed and ranked. Rebuilt only when something it is made from changes."""
        fetched = [await self._load(code, s) for code, s in code_seasons]
        version = (*self._v(*code_seasons), *(self.events.version(code, s) for code, s in code_seasons), self.repo.epochs.get("match", 0), self._roster_version())
        key = ("dataset", tuple(code_seasons))

        def compute():
            roster = self._roster_dobs()
            inputs = [self._season_input(f.data) for f in fetched]
            ds = build_dataset(inputs, favorite_of=self.favorite_of, today=self.today,
                               dob_info=lambda name, teams, reference, pid: self.dob_info(name, teams, reference, pid, roster))
            ds.coverage = {
                "shots": {f"{i.ls.league}:{i.ls.season}": list(self.matchbook.coverage(i.ls)) for i in inputs},
                "events": {f"{i.ls.league}:{i.ls.season}": len(self.events.match_ids(i.ls.league, i.ls.season)) for i in inputs},
            }
            return ds

        return await self._memo_async(key, version, compute), fetched

    # ------------------------------------------------------------------ what is known about a season, gathered for the analytics

    def _season_input(self, ls) -> SeasonInput:
        """Understat's season plus what the stored match pages and the event data add to it. Blocking: call from a worker thread."""
        pages = self.matchbook.pages(ls)
        complete = self.matchbook.complete(ls, pages)
        return SeasonInput(
            ls, shots=matchsum.player_shots(pages.values()) if complete else None,
            positions=matchsum.position_minutes(pages.values()) if complete else None, events=self._linked_events(ls, pages),
        )

    def _event_links(self, ls, pages=None) -> dict | None:
        """How WhoScored's matches, clubs and players line up with this Understat season, remembered until either side changes. None without event data."""
        agg = self.events.season(ls.league, ls.season)
        if not agg["games"]:
            return None
        version = (self.events.version(ls.league, ls.season), self.repo.version("league", f"{ls.league}:{ls.season}"), self.repo.epochs.get("match", 0))
        hit = self._links.get((ls.league, ls.season))
        if hit is not None and hit[0] == version:
            return hit[1]
        fixtures, alias, unlinked_matches = link_fixtures(agg, ls.fixtures)
        totals = {pid: {"id": pid, "name": p["name"], "teams": p["teams"], "min": p["c"].get("min", 0)} for pid, p in agg["players"].items()}
        linked, unlinked = link_season(totals, ls.players)
        players = {uid: t["id"] for uid, t in linked.items()}
        by_id = {}
        if unlinked:
            pages = self.matchbook.pages(ls) if pages is None else pages
            if pages:
                left = [agg["players"][u["id"]] for u in unlinked]
                extra = link_by_lineups(left, ls.players, pages, fixtures, alias, taken=players.keys())
                players.update(extra)
                by_id = {w: uid for uid, w in extra.items()}
        left_out = [u for u in unlinked if u["id"] not in by_id]
        info = {"agg": agg, "fixtures": fixtures, "alias": alias, "players": players, "unlinked_matches": unlinked_matches, "unlinked_players": left_out}
        self._links[(ls.league, ls.season)] = (version, info)
        return info

    def _linked_events(self, ls, pages=None) -> dict[int, dict] | None:
        """Understat player id -> his event counters for this season. None when no event data has been stored for it."""
        info = self._event_links(ls, pages)
        if info is None:
            return None
        players = info["agg"]["players"]
        return {uid: {"c": players[w]["c"], "matches": players[w]["matches"], "starts": players[w]["starts"], "pos": players[w]["pos"]} for uid, w in info["players"].items()}

    def _linked_team_events(self, ls) -> dict[str, dict] | None:
        """Understat club -> its event totals (for and against) for this season. None without event data."""
        info = self._event_links(ls)
        if info is None:
            return None
        out = {}
        for ws, t in info["agg"]["teams"].items():
            us = info["alias"].get(ws)
            if us in ls.teams:
                out[us] = {"c": t["c"], "a": t["a"], "matches": t["matches"], "formations": t["formations"], "managers": t["managers"]}
        return out

    def _team_shots(self, ls) -> dict[str, dict] | None:
        pages = self.matchbook.pages(ls)
        if not self.matchbook.complete(ls, pages):
            return None
        return matchsum.team_shots([(f, pages[f.id]) for f in ls.fixtures if f.id in pages])

    # ------------------------------------------------------------------ squad lists (exact birthdates)

    def _linked_roster(self, code: str, season: int, players=None) -> tuple[dict[int, dict], list[dict]]:
        """``({Understat id: squad-list player}, squad-list players matched to nobody)``, remembered until either side changes.

        ``players`` are the league season's players; left out, they are read from the local cache (so call it from a thread).
        """
        key = f"{code}:{season}"
        version = (self.rosters.fetched_at(code, season), self.repo.version("league", key))
        hit = self._roster_links.get((code, season))
        if hit is None or hit[0] != version:
            body = self.rosters.cached(code, season)
            if body is None:
                return {}, []
            if players is None:
                league = self.repo.cached_league(code, season)
                if league is None:
                    return {}, []
                players = league.players
            hit = self._roster_links[(code, season)] = (version, link_roster(body, players))
        return hit[1]

    def _roster_version(self) -> tuple:
        """A cheap token that changes when any stored squad list, or the league season it is matched against, does."""
        stamp = self.rosters.stamp()
        return stamp, tuple(self.repo.version("league", key) for key, _fetched, _complete in stamp)

    def _roster_dobs(self) -> dict[int, str]:
        """Understat player id -> exact date of birth, from every squad list on this computer, each matched within its own league season.

        A man has one birthdate whichever season or league a view shows, so someone who has since left his club (and is missing from
        its newer lists) is still found where he went. If two lists disagree about one player, one of the two matches is wrong, so he
        is left out: a blank age beats a wrong one.
        """
        version = self._roster_version()
        if self._dob_index is not None and self._dob_index[0] == version:
            return self._dob_index[1]
        found: dict[int, set[str]] = {}
        for league, season in self.rosters.seasons():
            linked, _unmatched = self._linked_roster(league, season)
            for pid, player in linked.items():
                found.setdefault(pid, set()).add(player["dob"])
        index = {pid: next(iter(dobs)) for pid, dobs in found.items() if len(dobs) == 1}
        self._dob_index = (version, index)
        return index

    async def event_status(self) -> list[dict]:
        """Per league-season: matches stored, how many exist, how well they line up with Understat, and the state of any fetching run."""
        seen: dict[tuple[str, int], None] = {(l, s): None for l, s, _n in self.events.seasons()}
        for key in self.store.kv_prefix(STATUS_PREFIX):
            league, _, season = key[len(STATUS_PREFIX):].partition(":")
            if season.isdigit():
                seen.setdefault((league, int(season)), None)
        out = []
        for league, season in sorted(seen):
            entry: dict = {"league": league, "season": season, "matches": len(self.events.match_ids(league, season)), "total": None,
                           "status": self.events.status(league, season), "linked": None, "unlinked": [], "unlinked_n": 0, "matches_linked": None}
            if self.store.meta("league", f"{league}:{season}") is not None:   # only from the cache: this must never go to the network
                try:
                    fetched = await self._load(league, season)
                    entry["total"] = len(fetched.data.played)
                    if entry["matches"]:
                        version = (self.events.version(league, season), self.repo.version("league", f"{league}:{season}"), self.repo.epochs.get("match", 0))

                        def report(ls=fetched.data):
                            info = self._event_links(ls)
                            if info is None:
                                return {}
                            left = sorted(info["unlinked_players"], key=lambda u: -u["minutes"])
                            return {"linked": len(info["players"]), "unlinked": left[:10], "unlinked_n": len(left),
                                    "matches_linked": len(info["fixtures"]), "matches_unlinked": len(info["unlinked_matches"])}

                        entry.update(await self._memo_async(("events-link", league, season), version, report))
                except AppError:
                    pass
            out.append(entry)
        return out

    def _roster_audit(self, league: str, season: int, fetched) -> dict:
        """How well one squad list matched Understat's players, and where Wikidata (when it is sure of the club) disagrees."""
        players = fetched.data.players
        linked, _unmatched = self._linked_roster(league, season, players)
        reference = min(self.today, date(season + 1, 6, 30))
        regulars = [p for p in players if p.minutes >= 450]
        missing = sorted((p for p in regulars if p.id not in linked), key=lambda p: -p.minutes)
        compared, disagree = 0, []
        for p in players:
            if p.id in linked:
                dob, basis = self.resolver.cached_info(p.name, p.teams, reference)
                if dob and basis == "club":
                    compared += 1
                    gap = abs((date.fromisoformat(dob) - date.fromisoformat(linked[p.id]["dob"])).days)
                    if gap:
                        disagree.append({"name": p.name, "team": p.team, "squad_list": linked[p.id]["dob"], "wikidata": dob, "days": gap, "blank": gap > CONTESTED_DAYS})
        disagree.sort(key=lambda x: -x["days"])
        return {"players_total": len(players), "linked": len(linked), "regulars": len(regulars), "regulars_linked": len(regulars) - len(missing),
                "missing": [{"id": p.id, "name": p.name, "team": p.team, "minutes": p.minutes} for p in missing[:8]],
                "compared": compared, "disagree": len(disagree), "blank": sum(x["blank"] for x in disagree), "disagree_examples": disagree[:6]}

    async def birthdate_status(self) -> list[dict]:
        """Per stored squad list: what it holds, how well it matched Understat's players, and what is left. Reads only what is stored."""
        out = []
        token = self._roster_version()
        for league, season in sorted(self.rosters.seasons(), key=lambda k: (k[0], -k[1])):
            body = self.rosters.cached(league, season)
            if body is None:
                continue
            entry: dict = {"league": league, "season": season, "clubs": len(body["teams"]), "players": sum(len(t["players"]) for t in body["teams"]),
                           "fetched": body["fetched"], "pending": [t["name"] for t in body.get("pending", [])], "final": self.rosters.is_final(season), "sparse": bool(body.get("sparse")),
                           "median_squad": sorted(len(t["players"]) for t in body["teams"])[len(body["teams"]) // 2],
                           "players_total": None, "linked": None, "regulars": None, "regulars_linked": None, "missing": [], "compared": 0, "disagree": 0, "blank": 0, "disagree_examples": []}
            if self.store.meta("league", f"{league}:{season}") is not None:   # only from the cache: this must never go to the network
                try:
                    fetched = await self._load(league, season)
                    version = (self.rosters.fetched_at(league, season), self.repo.version("league", f"{league}:{season}"), token, self.enricher.epoch)
                    entry.update(await self._memo_async(("roster-audit", league, season), version, lambda f=fetched: self._roster_audit(league, season, f)))
                except AppError:
                    pass
            out.append(entry)
        return out

    async def _targets(self, leagues: list[str], seasons: list[str | int]) -> tuple[list[tuple[str, int]], list[str]]:
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
        return targets, notes

    async def players_view(self, leagues: list[str], seasons: list[str | int], *, min_minutes: int = 1) -> dict:
        """Every player of the chosen league seasons with every metric and its percentile. Nothing is filtered here beyond a one-minute floor:
        filtering, sorting, top-N and the map all happen in the browser, on this one payload."""
        targets, notes = await self._targets(leagues, seasons)
        ds, fetched = await self._dataset(targets)
        rows = [r for r in ds.rows if r["minutes"] >= min_minutes]

        # background enrichment: exact birthdates from squad lists, then Wikidata for whoever they leave out (goalkeepers and
        # fringe players included, most minutes first), then positions for the ambiguous ones
        in_pool = [r for r in ds.rows if r["in_pool"] and r["group"] != "GK"]
        if not self.settings.offline:
            self.enricher.schedule_rosters(targets)
            if not self.settings.demo and not self.enricher.squads_pending(targets):
                unknown = sorted((r for r in ds.rows if r["age"] is None), key=lambda r: -r["minutes"])
                self.enricher.schedule_ages((r["name"], r["teams"][0] if r["teams"] else None) for r in unknown)
            self.enricher.schedule_roles([r["id"] for r in in_pool if r["group_source"] == "inferred"], limit=120)

        return {
            "scope": {
                "leagues": sorted({c for c, _ in targets}), "seasons": sorted({s for _, s in targets}),
                "labels": [season_label(s) for s in sorted({s for _, s in targets})], "notes": notes,
                "pool_minutes": ds.pool_minutes, "ev_pool_minutes": ds.ev_pool_minutes, "group_sizes": ds.group_sizes, "n": len(rows),
                "age_reference": ds.age_reference,
            },
            "meta": {"stale": any(f.meta.stale for f in fetched), "source": fetched[0].meta.source,
                     "fetched_at": fetched[0].meta.to_dict()["fetched_at"], "errors": [f.meta.error for f in fetched if f.meta.error]},
            "coverage": {"ages_known": ds.ages_known, "players": len(ds.rows), "inferred_roles": ds.inferred, "roles_known": len(self.favorites),
                         "event_players": ds.event_players, "event_pool_minutes": ds.ev_pool_minutes,
                         "event_matches": sum(len(self.events.match_ids(c, s)) for c, s in targets), **ds.coverage},
            "enrichment": self.enricher.status(),
            "keys": ds.keys, "pools": ds.pools, "rows": [compact_row(r, ds.keys) for r in rows],
            "highlights": dicts(rank(scouting_highlights(ds.rows), limit=12, per_kind=2, diversify=True)),
        }

    async def teams_view(self, leagues: list[str], seasons: list[str | int]) -> dict:
        """Every team of the chosen league seasons with every team metric and its percentile within its own league and season."""
        targets, notes = await self._targets(leagues, seasons)
        fetched = [await self._load(code, s) for code, s in targets]
        version = (*self._v(*targets), *(self.events.version(code, s) for code, s in targets), self.repo.epochs.get("match", 0), self._roster_version())

        def compute():
            inputs = []
            roster = self._roster_dobs()
            for f in fetched:
                ls = f.data
                reference = min(self.today, date(ls.season + 1, 6, 30))

                def age_of(p, ls=ls, reference=reference):
                    dob, basis = self.dob_info(p.name, p.teams, reference, p.id, roster)
                    if not dob or basis == "name":
                        return None
                    born = date.fromisoformat(dob[:10])
                    return reference.year - born.year - ((reference.month, reference.day) < (born.month, born.day))

                inputs.append(TeamInput(ls, shots=self._team_shots(ls), events=self._linked_team_events(ls), ages=squad_ages(ls, age_of)))
            return build_team_dataset(inputs)

        ds = await self._memo_async(("teams", tuple(targets)), version, compute)
        cfg = {code: LEAGUES[code] for code, _ in targets}
        keys = ds.keys
        rows = [{**{k: v for k, v in r.items() if k not in ("values", "pct")}, "v": [r["values"].get(k) for k in keys], "p": [None if r["pct"].get(k) is None else round(r["pct"][k]) for k in keys]} for r in ds.rows]
        return {
            "scope": {"leagues": sorted({c for c, _ in targets}), "seasons": sorted({s for _, s in targets}), "labels": [season_label(s) for s in sorted({s for _, s in targets})],
                      "notes": notes, "pools": ds.pools, "n": len(rows), "league_names": {c: cfg[c].name for c in cfg}},
            "meta": {"stale": any(f.meta.stale for f in fetched), "errors": [f.meta.error for f in fetched if f.meta.error]},
            "coverage": ds.coverage, "keys": keys, "rows": rows,
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
        detail = player_detail(row, page, want, team_ctx, ds.pools)
        if not detail["events"]["available"]:
            detail["events"]["stored"] = bool(self.events.seasons())  # lets the page say "not fetched for this season" only when event data exists elsewhere
        similar = similar_players(row, ds.rows, limit=8)
        insights = rank(player_insights(row, finishing=detail["finishing"], career=detail["career"], similar=similar, team_context=team_ctx))
        if not self.settings.offline:
            self.enricher.schedule_rosters([(code, s) for s in want])
            if not self.settings.demo and row.get("age") is None and not self.enricher.squads_pending([(code, s) for s in want]):
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
        return {"scope": scope, "meta": fetched.meta.to_dict(), "profile": profile, "insights": dicts(insights),
                "teams": [{"name": x.name, "short": x.short} for x in sorted(ls.teams.values(), key=lambda x: x.name)]}

    async def team_history_view(self, league: str, team: str, seasons: list[int]) -> dict:
        """One team's seasons side by side, by matchweek. Seasons the team was not in the league come back flagged, not as errors."""
        code = self._league_code(league)
        cfg = LEAGUES[code]
        if not seasons:
            newest, _ = await self.resolve_season(code, "auto")
            seasons = [s for s in range(newest, newest - HISTORY_DEFAULT_SEASONS, -1) if s >= FIRST_SEASON]
        seasons = list(dict.fromkeys(seasons))
        if len(seasons) > HISTORY_MAX_SEASONS:
            raise BadRequest(f"Pick at most {HISTORY_MAX_SEASONS} seasons to compare.")
        key = team.strip().lower()

        async def one(season: int):
            base = {"season": season, "label": season_label(season)}
            try:
                fetched = await self._load(code, season)
            except AppError as exc:
                return {**base, "available": False, "reason": exc.message}, None
            try:
                data = await self._memo_async(("team_history", code, season, key), self._v((code, season)), lambda: team_history(fetched.data, team))
            except NotFound:
                return {**base, "available": False, "missing": True, "reason": f"Not in the {cfg.name} in {base['label']}."}, fetched.meta
            return {**base, "available": True, **data}, fetched.meta

        results = await asyncio.gather(*(one(s) for s in seasons))
        rows = sorted((r for r, _ in results), key=lambda r: -r["season"])
        metas = [m for _, m in results if m is not None]
        found = [r for r in rows if r["available"]]
        if not found:
            if any(r.get("missing") for r in rows):
                raise NotFound(f"'{team}' was not in the {cfg.name} in any of the selected seasons.", hint="Pick other seasons, or check the spelling.")
            raise DataUnavailable("None of the selected seasons could be loaded.", hint="Open the Data page to sync, or try other seasons.")
        return {
            "scope": {"league": code, "league_name": cfg.name},
            "team": found[0]["team"],
            "short": found[0]["short"],
            "seasons": rows,
            "rounds_max": max(len(r["points"]) for r in found),
            "n_teams_max": max(r["n_teams"] for r in found),
            "meta": {"stale": any(m.stale for m in metas), "errors": [m.error for m in metas if m.error]},
        }

    async def team_chances_view(self, league: str, season, team: str) -> dict:
        """The team's own chance breakdowns: fast (one page), no league context. See team_chances_league_view for that."""
        code, s, fetched, scope = await self._scope(league, season)
        t = find_team(fetched.data, team)
        page = await self.repo.team_page(t.name, s)
        prepared = prepare_breakdowns(page.data.groups, max(len(t.history), 1))
        return {
            "scope": scope, "meta": page.meta.to_dict(), "team": t.name, "games": len(t.history),
            "breakdowns": prepared, "insights": chance_insights(t.name, prepared),
        }

    async def team_chances_league_view(self, league: str, season, team: str) -> dict:
        """The same breakdowns set against every other team: ranks, league averages and league-aware findings.

        Loads each team's page (cached; finished seasons are fetched once, ever). If it cannot, the tab keeps working without it.
        """
        code, s, fetched, scope = await self._scope(league, season)
        ls = fetched.data
        t = find_team(ls, team)

        async def page(name: str):
            try:
                return name, (await self.repo.team_page(name, s)).data.groups
            except AppError:
                return name, None

        try:
            results = await asyncio.wait_for(asyncio.gather(*(page(n) for n in ls.teams)), timeout=40)
        except asyncio.TimeoutError:
            return {"available": False, "reason": "Comparing with the rest of the league took too long. Open the tab again in a moment: the pages already fetched are kept.", "of": len(ls.teams)}
        pages = {n: g for n, g in results if g}
        if len(pages) < MIN_LEAGUE_TEAMS or t.name not in pages:
            return {"available": False, "reason": "Not enough of the league's team pages could be loaded to compare against.", "loaded": len(pages), "of": len(ls.teams)}
        prepared = {n: prepare_breakdowns(g, max(len(ls.teams[n].history), 1)) for n, g in pages.items()}
        comparison = compare_to_league(t.name, prepared[t.name], league_baseline(prepared))
        return {
            "available": True, "team": t.name, "loaded": len(pages), "of": len(ls.teams),
            "comparison": comparison, "insights": chance_insights(t.name, prepared[t.name], comparison),
        }

    # ------------------------------------------------------------------ pitch maps (from the stored events)

    @staticmethod
    def _pick_matches(log: list[dict], venue: str, last: int | None) -> list[dict]:
        rows = [r for r in log if venue == "all" or (venue == "h") == r["home"]]
        return rows[-last:] if last else rows

    def _map_payload(self, code: str, season: int, matches: list[tuple[int, int]], selection, *, team: str, extra: dict) -> dict:
        silver = [(i, self.events.silver(code, season, game)) for i, game in matches]
        silver = [(i, m) for i, m in silver if m is not None]
        layer = event_maps.collect(silver, selection)
        lines = {name: event_maps.lines_view(layer, flags=flag) for name, flag in
                 (("prog", event_maps.PF_PROG), ("key", event_maps.PF_KEY), ("box", event_maps.PF_BOX), ("f3", event_maps.PF_F3), ("long", event_maps.PF_LONG),
                  ("cross", event_maps.PF_CROSS), ("through", event_maps.PF_THROUGH))}
        return {
            "available": True, "dims": [event_maps.NX, event_maps.NY], "n": len(silver), "counts": layer["n"],
            "grids": {"touches": layer["touches"], "pass_from": layer["pass_from"], "def": layer["def_grid"], "recover": layer["recover_grid"]},
            "lines": lines, "all_passes": event_maps.lines_view(layer, limit=600), "carries": layer["carries"], "def": layer["def"], "takeons": layer["takeons"], "gk": layer["gk"],
            "zones": event_maps.zone_shares(layer), "network": event_maps.pass_network(silver, team) if selection.player is None else None, **extra,
        }

    async def team_maps_view(self, league: str, season, team: str, *, venue: str = "all", last: int | None = None) -> dict:
        """Where a team touches the ball, passes, defends and carries, from its stored matches: grids, pass lines, defensive actions, a pass network."""
        if venue not in ("all", "h", "a"):
            raise BadRequest("venue must be 'all', 'h' or 'a'.")
        code, s, fetched, scope = await self._scope(league, season)
        ls = fetched.data
        t = find_team(ls, team)
        key = ("team-maps", code, s, t.name, venue, last)
        version = (self.events.version(code, s), self.repo.version("league", f"{code}:{s}"), self.repo.epochs.get("match", 0))

        def compute():
            info = self._event_links(ls)
            if info is None:
                return {"available": False, "reason": "No event data has been stored for this league and season yet."}
            ws = next((w for w, us in info["alias"].items() if us == t.name), None)
            agg = info["agg"]["teams"].get(ws) if ws else None
            if agg is None:
                return {"available": False, "reason": f"{t.name} has no event data in this season."}
            log = self._pick_matches(agg["log"], venue, last)
            if not log:
                return {"available": False, "reason": "No matches fit those filters."}
            games = [(i, r["game"]) for i, r in enumerate(log)]
            fixtures = info["fixtures"]
            listing = [{"i": i, "game": r["game"], "date": r["date"], "opp": info["alias"].get(r["opp"], r["opp"]), "home": r["home"], "gf": r["gf"], "ga": r["ga"],
                        "match_id": fixtures[r["game"]].id if r["game"] in fixtures else None} for i, r in enumerate(log)]
            return self._map_payload(code, s, games, event_maps.Selection(team=ws), team=ws, extra={"matches": listing, "formations": agg["formations"], "manager": max(agg["managers"], key=agg["managers"].get) if agg["managers"] else None})

        out = await self._memo_async(key, version, compute)
        return {"scope": scope, "team": t.name, **out}

    async def player_maps_view(self, player_id: int, league: str | None, season, *, last: int | None = None) -> dict:
        """Where a player touches the ball, passes, defends and carries, from his stored matches."""
        code = self._league_code(league) if league else (await self._locate_player(player_id)) or DEFAULT_LEAGUE
        resolved, note = await self.resolve_season(code, season)
        fetched = await self._load(code, resolved)
        ls = fetched.data
        key = ("player-maps", code, resolved, player_id, last)
        version = (self.events.version(code, resolved), self.repo.version("league", f"{code}:{resolved}"), self.repo.epochs.get("match", 0))

        def compute():
            info = self._event_links(ls)
            if info is None:
                return {"available": False, "reason": "No event data has been stored for this league and season yet."}
            wid = info["players"].get(player_id)
            if wid is None:
                return {"available": False, "reason": "He could not be matched safely to the event data, so no map is drawn rather than a wrong one."}
            player = info["agg"]["players"][wid]
            log = [{"game": g, "club": c, "minutes": m, "started": st} for g, c, m, st in player["log"]]
            log = log[-last:] if last else log
            if not log:
                return {"available": False, "reason": "He has no matches in the event data."}
            fixtures = info["fixtures"]
            listing = []
            for i, r in enumerate(log):
                f = fixtures.get(r["game"])
                home = f is not None and info["alias"].get(r["club"]) == f.home
                listing.append({"i": i, "game": r["game"], "date": f.date if f else None, "opp": (f.away if home else f.home) if f else None, "home": home, "minutes": round(r["minutes"]),
                                "started": r["started"], "match_id": f.id if f else None})
            games = [(i, r["game"]) for i, r in enumerate(log)]
            return self._map_payload(code, resolved, games, event_maps.Selection(player=wid), team=log[-1]["club"], extra={"matches": listing, "ws_id": wid, "name": player["name"], "minutes": round(sum(r["minutes"] for r in log))})

        out = await self._memo_async(key, version, compute)
        return {"scope": {"league": code, "season": resolved, "label": season_label(resolved), "note": note}, "player_id": player_id, **out}

    async def team_shots_view(self, league: str, season, team: str, *, venue: str = "all", last: int | None = None) -> dict:
        """The team's shots and the shots it faced, from the stored Understat match pages: position, xG, result, scorer."""
        code, s, fetched, scope = await self._scope(league, season)
        ls = fetched.data
        t = find_team(ls, team)

        def compute():
            pages = self.matchbook.pages(ls)
            mine = [f for f in sorted(ls.fixtures, key=lambda f: (f.dt, f.id)) if f.played and t.name in (f.home, f.away) and f.id in pages]
            mine = [f for f in mine if venue == "all" or (venue == "h") == (f.home == t.name)]
            mine = mine[-last:] if last else mine
            for_, against = [], []
            for f in mine:
                side = "h" if f.home == t.name else "a"
                for sh in pages[f.id].shots.get(side, []):
                    for_.append([round(sh.x, 3), round(sh.y, 3), round(sh.xg, 3), sh.result, sh.minute, sh.player, sh.situation, sh.shot_type, f.id])
                for sh in pages[f.id].shots.get("a" if side == "h" else "h", []):
                    against.append([round(sh.x, 3), round(sh.y, 3), round(sh.xg, 3), sh.result, sh.minute, sh.player, sh.situation, sh.shot_type, f.id])
            have, total = self.matchbook.coverage(ls, pages)
            return {"for": for_, "against": against, "matches": len(mine), "coverage": [have, total]}

        out = await self._memo_async(("team-shots", code, s, t.name, venue, last), (self.repo.version("league", f"{code}:{s}"), self.repo.epochs.get("match", 0)), compute)
        return {"scope": scope, "team": t.name, **out}

    async def team_matches_view(self, league: str, season, team: str) -> dict:
        """One team's season match by match: result, the chances, and (where event data exists) possession, passing and pressing in that match."""
        code, s, fetched, scope = await self._scope(league, season)
        ls = fetched.data
        t = find_team(ls, team)

        def compute():
            info = self._event_links(ls)
            rows = {r["n"]: r for r in team_profile(ls, t.name)["matches"]}
            by_fixture = {}
            if info is not None:
                ws = next((w for w, us in info["alias"].items() if us == t.name), None)
                agg = info["agg"]["teams"].get(ws) if ws else None
                for r in (agg["log"] if agg else []):
                    f = info["fixtures"].get(r["game"])
                    if f is not None:
                        c, a = r["c"], r["a"]
                        pf, pa = c.get("passes", 0), a.get("passes", 0)
                        by_fixture[f.id] = {"poss": None if pf + pa == 0 else round(100 * pf / (pf + pa)), "passes": pf, "pass_acc": None if not pf else round(100 * c.get("pass_ok", 0) / pf),
                                            "prog": c.get("prog", 0), "tilt": None if not (c.get("touch_att3", 0) + a.get("touch_att3", 0)) else round(100 * c.get("touch_att3", 0) / (c.get("touch_att3", 0) + a.get("touch_att3", 0))),
                                            "tackles": c.get("tackles", 0), "interceptions": c.get("interceptions", 0), "recoveries": c.get("recoveries", 0),
                                            "fouls": c.get("fouls", 0), "corners": c.get("corners", 0), "formation": r["formation"], "manager": r["manager"]}
            return [{**row, **by_fixture.get(row["match_id"], {})} for row in rows.values()]

        out = await self._memo_async(("team-matches", code, s, t.name), (self.repo.version("league", f"{code}:{s}"), self.events.version(code, s), self.repo.epochs.get("match", 0)), compute)
        return {"scope": scope, "team": t.name, "matches": out}

    # ------------------------------------------------------------------ the dictionary's numbers

    async def dictionary_stats(self, league: str, season) -> dict:
        """For each metric, what typical, good and elite look like in this league season: the 10th, 25th, 50th, 75th and 90th percentiles of the
        values of players in the ranking pool (per role group) and of teams. This is what turns a definition into a way to read a number."""
        code, s, fetched, scope = await self._scope(league, season)
        ds, _ = await self._dataset([(code, s)])
        teams = await self.teams_view([code], [s])
        version = (self.repo.version("league", f"{code}:{s}"), self.events.version(code, s), self.repo.epochs.get("match", 0))

        def compute():
            import numpy as np
            qs = (10, 25, 50, 75, 90)
            players: dict[str, dict[str, list]] = {}
            for i, key in enumerate(ds.keys):
                per = {}
                for group in ("ATT", "MID", "DEF", "GK"):
                    vals = [r["v"][i] for r in rows_for(group) if r["v"][i] is not None]
                    if len(vals) >= 8:
                        per[group] = [len(vals), *[round(float(x), 4) for x in np.percentile(vals, qs)]]
                if per:
                    players[key] = per
            teams_out = {}
            for i, key in enumerate(teams["keys"]):
                vals = [r["v"][i] for r in teams["rows"] if r["v"][i] is not None]
                if len(vals) >= 8:
                    teams_out[key] = [len(vals), *[round(float(x), 4) for x in np.percentile(vals, qs)]]
            return {"quantiles": list(qs), "players": players, "teams": teams_out}

        compact = [compact_row(r, ds.keys) for r in ds.rows]
        by_group: dict[str, list] = {}
        for r in compact:
            if (r["in_pool"] and r["group"] != "GK") or (r["group"] == "GK" and r["in_pool"]):
                by_group.setdefault(r["group"], []).append(r)
        rows_for = lambda g: by_group.get(g, [])  # noqa: E731
        stats = await self._memo_async(("dict-stats", code, s), version, compute)
        return {"scope": scope, **stats}

    # ------------------------------------------------------------------ matches

    async def matches_view(self, league: str, season) -> dict:
        """Every fixture by matchweek, each with its score, who scored, and the numbers behind the result."""
        code, s, fetched, scope = await self._scope(league, season)
        ls = fetched.data
        summaries = await self._memo_async(("match-summaries", code, s), (self.repo.version("league", f"{code}:{s}"), self.repo.epochs.get("match", 0), self.events.version(code, s)),
                                           lambda: self._match_summaries(ls))
        by_round: dict[int, list] = {}
        for f in sorted(ls.fixtures, key=lambda f: (f.dt, f.id)):
            by_round.setdefault(f.round, []).append(f)
        recent = {m["id"]: m for m in recent_matches(ls, limit=len(ls.fixtures))}
        rounds = []
        for number, fixtures in sorted(by_round.items()):
            rounds.append({
                "round": number, "from": fixtures[0].date, "to": fixtures[-1].date, "played": all(f.played for f in fixtures),
                "matches": [self._fixture_card(f, summaries, recent) for f in fixtures],
            })
        latest = max((r["round"] for r in rounds if any(m["played"] for m in r["matches"])), default=None)
        have = sum(1 for r in rounds for m in r["matches"] if "scorers" in m)
        return {"scope": scope, "meta": fetched.meta.to_dict(), "rounds": rounds, "latest_round": latest,
                "coverage": {"scorers": have, "played": ls.n_played, "events": len(self.events.match_ids(code, s))}}

    @staticmethod
    def _fixture_card(f, summaries: dict, recent: dict) -> dict:
        """One fixture as the match card shows it: teams, score, kickoff (UTC), the result's flag, and whatever the stored pages add (scorers, possession ...)."""
        return {"id": f.id, "date": f.date, "dt": f.dt, "utc": f.dt[:10] + "T" + f.dt[11:19] + "Z" if len(f.dt) >= 19 else None, "round": f.round,
                "home": f.home, "away": f.away, "home_short": f.home_short, "away_short": f.away_short,
                "played": f.played, "hg": f.hg, "ag": f.ag, "hxg": None if f.hxg is None else round(f.hxg, 2), "axg": None if f.axg is None else round(f.axg, 2),
                "flag": recent.get(f.id, {}).get("flag"), **summaries.get(f.id, {})}

    def _match_summaries(self, ls) -> dict[int, dict]:
        """Per fixture id: scorers and shot counts from the stored match page, and possession and passing from the event data. Blocking."""
        pages = self.matchbook.pages(ls)
        out: dict[int, dict] = {}
        for f in ls.fixtures:
            page = pages.get(f.id)
            if page is not None:
                out[f.id] = matchsum.fixture_summary(f, page)
        info = self._event_links(ls, pages)
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

    async def match_view(self, match_id: int, league: str, season) -> dict:
        code, s, fetched, scope = await self._scope(league, season)
        fixture = next((f for f in fetched.data.fixtures if f.id == match_id), None)
        if fixture is None:
            raise NotFound(f"Match {match_id} is not in {scope['league_name']} {scope['label']}.", hint="Check the league and season.")
        if not fixture.played:
            raise BadRequest("That match has not been played yet: there are no shots to analyse.")
        page = await self.repo.match(match_id, final=self.matchsync.is_final(fixture), expect_shots=bool((fixture.hxg or 0) + (fixture.axg or 0) > 0))
        report = match_report(fixture, page.data)
        report["scorers"] = matchsum.scorers(page.data)
        insights = rank(match_insights(report))
        return {"scope": scope, "meta": page.meta.to_dict(), "report": report, "insights": dicts(insights),
                "stats": (await self._memo_async(("match-summaries", code, s), (self.repo.version("league", f"{code}:{s}"), self.repo.epochs.get("match", 0), self.events.version(code, s)),
                                                 lambda: self._match_summaries(fetched.data))).get(match_id, {}).get("stats")}

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
        n = len(table)
        gaps = {}
        if n >= 4 and not ctx["complete"]:
            pts = [r["pts"] for r in table]
            gaps = {"title": pts[0] - pts[1], "top": pts[cfg.ucl_places - 1] - pts[cfg.ucl_places] if cfg.ucl_places < n else None,
                    "safety": pts[n - cfg.relegation_places - 1] - pts[n - cfg.relegation_places] if cfg.relegation_places < n else None}
        summaries = await self._memo_async(("match-summaries", code, s), (self.repo.version("league", f"{code}:{s}"), self.repo.epochs.get("match", 0), self.events.version(code, s)),
                                           lambda: self._match_summaries(ls))
        latest = recent_matches(ls, limit=10)
        by_id = {f.id: f for f in ls.fixtures}
        recent_cards = [self._fixture_card(by_id[m["id"]], summaries, {m["id"]: m}) for m in latest if m["id"] in by_id]
        upcoming = []
        by_team = {r["team"]: r for r in table}
        for f in sorted(ls.upcoming, key=lambda f: (f.dt, f.id))[:10]:
            h, a = by_team.get(f.home), by_team.get(f.away)
            upcoming.append({"id": f.id, "date": f.date, "dt": f.dt, "utc": f.dt[:10] + "T" + f.dt[11:19] + "Z" if len(f.dt) >= 19 else None, "round": f.round, "home": f.home, "away": f.away,
                             "home_short": f.home_short, "away_short": f.away_short,
                             "home_rank": h and h["rank"], "away_rank": a and a["rank"], "home_form": h and h["form"], "away_form": a and a["form"],
                             "home_xgd": h and round(h["xgd_pg"], 2), "away_xgd": a and round(a["xgd_pg"], 2)})
        return {
            "scope": scope, "meta": fetched.meta.to_dict(), "context": ctx, "insights": dicts(front), "gaps": gaps,
            "table": [{k: r[k] for k in ("rank", "team", "short", "played", "pts", "gd", "xpts", "xpts_gap", "xgd_pg", "form", "trend_xgd", "rank_xpts")} for r in table],
            "recent": recent_cards, "movers": movers(ls), "upcoming": upcoming,
            "highlights": dicts(rank(scouting_highlights(ds.rows), limit=6, per_kind=2, diversify=True)),
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

    # ------------------------------------------------------------------ diagnostics

    async def check_connection(self) -> dict:
        """Walk the real data path once (league -> match -> player -> squad list -> birthdates) and say which step breaks.

        Nothing is written to the cache: this is what to run when Understat changes its pages or the network is odd.
        """
        steps: list[dict] = []
        state: dict[str, Any] = {}

        async def step(name: str, action) -> bool:
            started = time.perf_counter()
            entry = {"name": name, "ok": True, "detail": "", "hint": None}
            try:
                entry["detail"] = await action()
            except AppError as exc:
                entry.update(ok=False, detail=exc.message, hint=exc.hint)
            except Exception as exc:  # any surprise is exactly what this check exists to surface
                entry.update(ok=False, detail=f"{type(exc).__name__}: {str(exc)[:160]}", hint="Please report this with the detail above.")
            entry["ms"] = round((time.perf_counter() - started) * 1000)
            steps.append(entry)
            return entry["ok"]

        code = DEFAULT_LEAGUE
        season = current_season(self.today)

        async def fetch_league() -> str:
            for candidate in (season, season - 1):
                try:
                    raw = await self.provider.league(code, candidate)
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
            page = normalize_match_page(await self.provider.match(played[-1].id), played[-1].id)
            return f"Match {played[-1].id}: {sum(len(v) for v in page.shots.values())} shots, {sum(len(v) for v in page.rosters.values())} lineup rows"

        async def read_player() -> str:
            players = sorted(state["ls"].players, key=lambda p: -p.minutes)
            if not players:
                return "No players in the league page."
            page = normalize_player_page(await self.provider.player(players[0].id), players[0].id)
            return f"{players[0].name}: {len(page.shots)} career shots, {len(page.career)} seasons"

        async def read_birthdates() -> str:
            if self.settings.demo:
                return "Demo mode: birthdates come from the demo world."
            if self.settings.offline:
                return "Offline mode: Wikidata was not contacted."
            found = await self.resolver.resolve([("Erling Haaland", "Manchester City")])
            value = next(iter(found.values()), None)
            return f"Wikidata answered: Erling Haaland born {value}" if value else "Wikidata answered but had no birthdate for the test player."

        async def read_squads() -> str:
            if self.settings.demo:
                return "Demo mode: squad lists are not used."
            if self.settings.offline:
                return "Offline mode: ESPN was not contacted."
            return await self.rosters.probe(code, season)

        if await step("Reach Understat" if not self.settings.demo else "Load the league", fetch_league) and await step("Read the league page", read_league):
            await step("Read a match", read_match)
            await step("Read a player", read_player)
        await step("Read a squad list", read_squads)
        await step("Look up birthdates", read_birthdates)
        return {"ok": all(s["ok"] for s in steps), "mode": {"demo": self.settings.demo, "offline": self.settings.offline}, "steps": steps}

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

    def _coverage_matrix(self) -> list[dict]:
        """One row per league season that is tracked or stored: what is on this computer, against what exists. Reads only the local store."""
        seen = {(l["league"], l["season"]) for l in self.repo.cached_leagues()}
        seen.update(self.auto.tracked())
        seen.update((l, s) for l, s, _n in self.events.seasons())
        out = []
        for code, season in sorted(seen, key=lambda k: (-k[1], list(LEAGUES).index(k[0]) if k[0] in LEAGUES else 99)):
            meta = self.store.meta("league", f"{code}:{season}")
            row: dict = {"league": code, "season": season, "label": season_label(season), "league_state": None if meta is None else ("final" if meta[2] else "live"),
                         "fetched_at": None if meta is None else meta[0], "played": None, "pages": None, "events": len(self.events.match_ids(code, season)), "squads": None}
            ls = self.repo.cached_league(code, season) if meta is not None else None
            if ls is not None:
                row["played"] = ls.n_played
                row["pages"] = list(self.matchsync.coverage(ls))
                row["fixtures"] = len(ls.fixtures)
            body = self.rosters.cached(code, season)
            row["squads"] = None if body is None else {"clubs": len(body["teams"]), "players": sum(len(t["players"]) for t in body["teams"]), "sparse": bool(body.get("sparse"))}
            row["silver"] = len(self.store.keys_prefix("ws_silver", f"{code}:{season}:")) if row["events"] else 0
            out.append(row)
        return out

    async def reclaim_download_cache(self) -> dict:
        """Delete the browser tool's own copy of every event page that is safely in the store (about 1 MB each). Nothing in the store changes."""
        from app.events import raw as R

        if self.auto._proc_alive():
            raise BadRequest("The event fetcher is running: wait for it to finish before reclaiming space.")
        return await asyncio.to_thread(R.reclaim, self.store, self.settings.data_dir)

    async def data_status(self) -> dict:
        from app.events import raw as R

        stats = self.store.stats()
        matrix = await asyncio.to_thread(self._coverage_matrix)
        reclaim = await asyncio.to_thread(R.reclaimable_bytes, self.store, self.settings.data_dir)
        return {
            "mode": {"demo": self.settings.demo, "offline": self.settings.offline, "demo_events": self.demo_feed is not None},
            "store": {"path": str(self.settings.db_path), **stats},
            "leagues": self.repo.cached_leagues(),
            "enrichment": self.enricher.status(),
            "jobs": self.jobs.recent(6),
            "upstream": {"requests": getattr(self.provider, "requests_made", None)},
            "coverage": {"favorites": len(self.favorites)},
            "matrix": matrix,
            "auto": self.auto.state(),
            "boot": self.store.kv_get("boot:state"),
            "events": await self.event_status(),
            "birthdates": await self.birthdate_status(),
            "reclaimable_bytes": reclaim,
        }

    def start_sync(self, leagues: list[str], seasons: list[int], force: bool = False) -> dict:
        if self.settings.offline:
            raise DataUnavailable("Offline mode is on: syncing is disabled.", hint="Restart without PREM_OFFLINE to fetch new data.")
        codes = [self._league_code(l) for l in leagues]
        if not seasons:
            seasons = [current_season(self.today)]
        job = self.jobs.start_sync(codes, seasons, force=force)
        return job.to_dict()
