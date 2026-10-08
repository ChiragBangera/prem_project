"""Matching WhoScored players to Understat players: the shared strict matcher, fed with WhoScored's season totals.

See :mod:`app.data.people` for the rules. Here a WhoScored player is a person whose clubs are the ones he played minutes for
and whose weight is those minutes, so a clash between two people for one Understat player goes to the one who played more.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.data.models import PlayerSeason
from app.data.people import Person, link_people, name_words, plays_for as _plays_for  # noqa: F401  (re-exported for callers and tests)


def link_season(totals: dict[int, dict], players: Iterable[PlayerSeason], alias: dict[str, str] | None = None) -> tuple[dict[int, dict], list[dict]]:
    """``({understat id: WhoScored totals}, unlinked)`` for one league-season.

    ``alias`` maps WhoScored's club names to Understat's ("PSG" -> "Paris Saint Germain", "RBL" -> "RasenBallsport Leipzig"), as
    :func:`link_fixtures` found them from the matches both sources agree on. Without it a club that the two sources name with no word in
    common is a different club to the name matcher, and every player of it is left out unless his line-ups place him (three matches or more).

    ``unlinked`` lists the WhoScored players with real minutes that could not be matched, so coverage is honest and visible.
    """
    alias = alias or {}
    by_key = {t["id"]: t for t in totals.values()}
    people = [Person(key=t["id"], name=t["name"], clubs=sorted({alias.get(team, team) for team, minutes in t["teams"].items() if minutes > 0 and team}), weight=t["min"])
              for t in totals.values()]
    linked, left = link_people(people, players)
    unlinked = [
        {"id": p.key, "name": p.name, "teams": p.clubs, "minutes": p.weight, "candidates": [c.name for c in found]}
        for p, found in left if p.weight >= 90
    ]
    return {uid: by_key[p.key] for uid, p in linked.items()}, unlinked


# ---------------------------------------------------------------------- matches, teams and the players name matching misses

from datetime import date as _date  # noqa: E402
from collections.abc import Mapping  # noqa: E402

from app.data.models import Fixture, MatchPage  # noqa: E402
from app.leagues import fold  # noqa: E402


def _days(a: str, b: str) -> int | None:
    try:
        return abs((_date.fromisoformat(a[:10]) - _date.fromisoformat(b[:10])).days)
    except ValueError:
        return None


def link_fixtures(rollup: dict, fixtures: Iterable[Fixture]) -> tuple[dict[int, Fixture], dict[str, str], list[dict]]:
    """Line WhoScored's matches up with Understat's fixtures: ``(game id -> fixture, WhoScored club -> Understat club, unlinked)``.

    A match is the same match when both clubs are the same clubs (home with home), the date is within a day (the two sources keep time
    differently) and the final score is the same. Names alone can be ambiguous ("Man Utd"); a date and a score are not. Matches that
    names cannot place are placed by date and score alone, but only when exactly one fixture fits, and every pairing is voted on so one
    odd match cannot rename a club.
    """
    played = [f for f in fixtures if f.played]
    matches = []
    for team in rollup["teams"].values():
        for row in team["log"]:
            if row["home"]:
                matches.append({"game": row["game"], "date": row["date"], "home": team["name"], "away": row["opp"], "score": row.get("score")})
    links: dict[int, Fixture] = {}
    used: set[int] = set()

    def fits(m: dict, f: Fixture, *, names: bool) -> bool:
        gap = _days(m["date"], f.date)
        if gap is None or gap > 1:
            return False
        if m["score"] and (m["score"][0] != f.hg or m["score"][1] != f.ag):
            return False
        return not names or (_plays_for([m["home"]], [f.home]) and _plays_for([m["away"]], [f.away]))

    for names in (True, False):
        for m in matches:
            if m["game"] in links:
                continue
            found = [f for f in played if f.id not in used and fits(m, f, names=names)]
            if len(found) == 1:
                links[m["game"]] = found[0]
                used.add(found[0].id)
    votes: dict[str, dict[str, int]] = {}
    for m in matches:
        f = links.get(m["game"])
        if f is not None:
            for ws, us in ((m["home"], f.home), (m["away"], f.away)):
                votes.setdefault(ws, {}).setdefault(us, 0)
                votes[ws][us] += 1
    teams = {ws: max(v, key=v.__getitem__) for ws, v in votes.items()}
    unlinked = [m for m in matches if m["game"] not in links]
    return links, teams, unlinked


def link_by_lineups(
    ws_players: Iterable[dict], us_players: Iterable, pages: Mapping[int, MatchPage], game_fixture: Mapping[int, Fixture], teams: Mapping[str, str],
    *, taken: Iterable[int] = (),
) -> dict[int, int]:
    """Link the players name matching left over, by looking at the line-ups of the matches they both played in: ``{Understat id: WhoScored id}``.

    In one match the same side has the same eleven (and the same substitutes) in both sources, so a player the two spell differently
    ("Rayan Cherki" / "Mathis Cherki", "Tino Livramento" / "Valentino Livramento") is the one man on that side who shares a word of his
    name and did the same thing: started, or came on from the bench. (Minutes are no help: the two sources count stoppage time
    differently, and a substitute's minutes can differ by a third.) One match is a coincidence; the same man match after match is not, so
    it takes at least three matches that all point to him, a clear winner, and a candidate claimed by two people is left alone.

    ``ws_players`` are rollup entries (``log``: ``(game, club, minutes, started)`` per match); ``us_players`` have ``id`` and ``name``.
    """
    taken_ids = set(taken)
    candidates = {p.id: p for p in us_players if p.id not in taken_ids}
    words = {uid: set(fold(p.name).split()) for uid, p in candidates.items()}
    proposals: dict[int, tuple[int, int]] = {}  # ws id -> (understat id, matches in agreement)
    for w in ws_players:
        mine = set(fold(w["name"]).split())
        tally: dict[int, int] = {}
        seen = 0
        for game, club, minutes, started in w.get("log", []):
            fixture = game_fixture.get(game)
            if fixture is None:
                continue
            page = pages.get(fixture.id)
            if page is None or minutes <= 0:
                continue
            side = "h" if teams.get(club) == fixture.home else "a" if teams.get(club) == fixture.away else None
            if side is None:
                continue
            seen += 1
            for r in page.rosters.get(side, []):
                if r.player_id in candidates and r.minutes > 0 and (r.position != "Sub") == started and mine & words[r.player_id]:
                    tally[r.player_id] = tally.get(r.player_id, 0) + 1
        if not tally:
            continue
        best = max(tally, key=tally.__getitem__)
        ranked = sorted(tally.values(), reverse=True)
        clear_winner = len(ranked) == 1 or ranked[0] > ranked[1]
        if clear_winner and ranked[0] >= 3 and ranked[0] >= 0.7 * seen:
            proposals[w["id"]] = (best, tally[best])
    claimed: dict[int, list[tuple[int, int]]] = {}
    for wid, (uid, n) in proposals.items():
        claimed.setdefault(uid, []).append((wid, n))
    return {uid: ws[0][0] for uid, ws in claimed.items() if len(ws) == 1}
