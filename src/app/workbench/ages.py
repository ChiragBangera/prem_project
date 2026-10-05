"""Dates of birth: where they come from, in what order they are trusted, and how well the sources agree.

In order of trust: a correction you made yourself, the club's squad list (exact, and the person is already known to be at that club),
then Wikidata matched on the club or, failing that, on the name alone. Two sources that cannot both be right give a blank, not a guess.
"""

from __future__ import annotations

import json
from datetime import date
from functools import partial
from typing import TYPE_CHECKING

from app.data.rosters import link_roster
from app.errors import AppError
from app.leagues import fold
from app.workbench.part import Part

if TYPE_CHECKING:  # pragma: no cover
    from app.workbench.core import Workbench

CONTESTED_DAYS = 366  # a squad list and a club-confirmed Wikidata entry more than a year apart cannot both be right about one man


class Ages(Part):
    def __init__(self, wb: Workbench) -> None:
        super().__init__(wb)
        self.birthdates = self._load_birthdates()
        self._roster_links: dict[tuple[str, int], tuple] = {}
        self._dob_index: tuple[tuple, dict[int, str]] | None = None

    def _load_birthdates(self) -> dict[str, str]:
        """Your own corrections: ``<data dir>/birthdates.json`` as ``{"Name": "YYYY-MM-DD"}`` or ``{"Name|Club": ...}``.

        They win over Wikidata, which cannot always tell namesakes apart. Read once at start-up.
        """
        try:
            raw = json.loads((self.settings.data_dir / "birthdates.json").read_text(encoding="utf-8"))
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
            return getattr(self.wb.provider, "birthdate", lambda n, t=None: None)(name, clubs[0] if clubs else None), None
        return self.wb.resolver.cached_info(name, clubs, reference)

    def _contested(self, dob: str, name: str, clubs: list[str], reference: date | None) -> str | None:
        """Wikidata's date for him when it is sure of the club and is more than a year from ``dob``; otherwise None."""
        other, basis = self.wb.resolver.cached_info(name, clubs, reference)
        if other and basis == "club" and abs((date.fromisoformat(other) - date.fromisoformat(dob)).days) > CONTESTED_DAYS:
            return other
        return None

    def dob_of(self, name: str, team: str | None, reference: date | None = None) -> str | None:
        return self.dob_info(name, team, reference)[0]

    # ------------------------------------------------------------------ squad lists (exact birthdates)

    def linked_roster(self, code: str, season: int, players=None) -> tuple[dict[int, dict], list[dict]]:
        """``({Understat id: squad-list player}, squad-list players matched to nobody)``, remembered until either side changes.

        ``players`` are the league season's players; left out, they are read from the local cache (so call it from a thread).
        """
        key = f"{code}:{season}"
        rosters = self.wb.rosters
        version = (rosters.fetched_at(code, season), self.repo.version("league", key))
        hit = self._roster_links.get((code, season))
        if hit is None or hit[0] != version:
            body = rosters.cached(code, season)
            if body is None:
                return {}, []
            if players is None:
                league = self.repo.cached_league(code, season)
                if league is None:
                    return {}, []
                players = league.players
            hit = self._roster_links[(code, season)] = (version, link_roster(body, players))
        return hit[1]

    def roster_version(self) -> tuple:
        """A cheap token that changes when any stored squad list, or the league season it is matched against, does."""
        stamp = self.wb.rosters.stamp()
        return stamp, tuple(self.repo.version("league", key) for key, _fetched, _complete in stamp)

    def roster_dobs(self) -> dict[int, str]:
        """Understat player id -> exact date of birth, from every squad list on this computer, each matched within its own league season.

        A man has one birthdate whichever season or league a view shows, so someone who has since left his club (and is missing from
        its newer lists) is still found where he went. If two lists disagree about one player, one of the two matches is wrong, so he
        is left out: a blank age beats a wrong one.
        """
        version = self.roster_version()
        if self._dob_index is not None and self._dob_index[0] == version:
            return self._dob_index[1]
        found: dict[int, set[str]] = {}
        for league, season in self.wb.rosters.seasons():
            linked, _unmatched = self.linked_roster(league, season)
            for pid, player in linked.items():
                found.setdefault(pid, set()).add(player["dob"])
        index = {pid: next(iter(dobs)) for pid, dobs in found.items() if len(dobs) == 1}
        self._dob_index = (version, index)
        return index

    def _audit(self, league: str, season: int, fetched) -> dict:
        """How well one squad list matched Understat's players, and where Wikidata (when it is sure of the club) disagrees."""
        players = fetched.data.players
        linked, _unmatched = self.linked_roster(league, season, players)
        reference = min(self.today, date(season + 1, 6, 30))
        regulars = [p for p in players if p.minutes >= 450]
        missing = sorted((p for p in regulars if p.id not in linked), key=lambda p: -p.minutes)
        compared, disagree = 0, []
        for p in players:
            if p.id in linked:
                dob, basis = self.wb.resolver.cached_info(p.name, p.teams, reference)
                if dob and basis == "club":
                    compared += 1
                    gap = abs((date.fromisoformat(dob) - date.fromisoformat(linked[p.id]["dob"])).days)
                    if gap:
                        disagree.append({"name": p.name, "team": p.team, "squad_list": linked[p.id]["dob"], "wikidata": dob, "days": gap, "blank": gap > CONTESTED_DAYS})
        disagree.sort(key=lambda x: -x["days"])
        return {"players_total": len(players), "linked": len(linked), "regulars": len(regulars), "regulars_linked": len(regulars) - len(missing),
                "missing": [{"id": p.id, "name": p.name, "team": p.team, "minutes": p.minutes} for p in missing[:8]],
                "compared": compared, "disagree": len(disagree), "blank": sum(x["blank"] for x in disagree), "disagree_examples": disagree[:6]}

    async def status(self) -> list[dict]:
        """Per stored squad list: what it holds, how well it matched Understat's players, and what is left. Reads only what is stored."""
        rosters = self.wb.rosters
        out = []
        token = self.roster_version()
        for league, season in sorted(rosters.seasons(), key=lambda k: (k[0], -k[1])):
            body = rosters.cached(league, season)
            if body is None:
                continue
            entry: dict = {"league": league, "season": season, "clubs": len(body["teams"]), "players": sum(len(t["players"]) for t in body["teams"]),
                           "fetched": body["fetched"], "pending": [t["name"] for t in body.get("pending", [])], "final": rosters.is_final(season), "sparse": bool(body.get("sparse")),
                           "median_squad": sorted(len(t["players"]) for t in body["teams"])[len(body["teams"]) // 2],
                           "players_total": None, "linked": None, "regulars": None, "regulars_linked": None, "missing": [], "compared": 0, "disagree": 0, "blank": 0, "disagree_examples": []}
            if self.store.meta("league", f"{league}:{season}") is not None:   # only from the cache: this must never go to the network
                try:
                    fetched = await self.wb.seasons.load(league, season)
                    version = (rosters.fetched_at(league, season), self.repo.version("league", f"{league}:{season}"), token, self.wb.enricher.epoch)
                    entry.update(await self.wb.memo(("roster-audit", league, season), version, partial(self._audit, league, season, fetched)))
                except AppError:
                    pass
            out.append(entry)
        return out
