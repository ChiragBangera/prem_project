"""Matching WhoScored players to Understat players: the shared strict matcher, fed with WhoScored's season totals.

See :mod:`app.data.people` for the rules. Here a WhoScored player is a person whose clubs are the ones he played minutes for
and whose weight is those minutes, so a clash between two people for one Understat player goes to the one who played more.
"""

from __future__ import annotations

from typing import Iterable

from app.data.models import PlayerSeason
from app.data.people import Person, link_people, name_words, plays_for as _plays_for  # noqa: F401  (re-exported for callers and tests)


def link_season(totals: dict[int, dict], players: Iterable[PlayerSeason]) -> tuple[dict[int, dict], list[dict]]:
    """``({understat id: WhoScored totals}, unlinked)`` for one league-season.

    ``unlinked`` lists the WhoScored players with real minutes that could not be matched, so coverage is honest and visible.
    """
    by_key = {t["id"]: t for t in totals.values()}
    people = [Person(key=t["id"], name=t["name"], clubs=[team for team, minutes in t["teams"].items() if minutes > 0 and team], weight=t["min"]) for t in totals.values()]
    linked, left = link_people(people, players)
    unlinked = [
        {"id": p.key, "name": p.name, "teams": p.clubs, "minutes": p.weight, "candidates": [c.name for c in found]}
        for p, found in left if p.weight >= 90
    ]
    return {uid: by_key[p.key] for uid, p in linked.items()}, unlinked
