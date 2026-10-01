"""Matching WhoScored players to Understat players.

The two sources spell names differently ("Heung-Min Son" / "Son Heung-Min", missing accents) so the match is
on the *set of name words*, and a player must also have played for the same club in that season. If that still
leaves more than one candidate, or none, the player is left unlinked: a blank is better than another man's stats.
A single-word Understat name ("Alisson") links to a longer WhoScored one ("Alisson Becker") only when, once everyone else is matched,
it is the one unmatched candidate on both sides at that club.
"""

from __future__ import annotations

import re
from typing import Iterable

from app.data.models import PlayerSeason
from app.data.wikidata import same_club
from app.leagues import fold

# WhoScored's short club names that share no word with Understat's
CLUB_ALIASES = {
    "wolves": "wolverhampton wanderers",
    "spurs": "tottenham",
    "man utd": "manchester united",
    "man city": "manchester city",
    "newcastle utd": "newcastle united",
}


# the same given name written two ways; applied to every word, and a match still needs the same club
NICKNAMES = {
    "andy": "andrew", "matty": "matthew", "matt": "matthew", "josh": "joshua", "joe": "joseph", "tom": "thomas", "ben": "benjamin",
    "dan": "daniel", "danny": "daniel", "sam": "samuel", "will": "william", "alex": "alexander", "mike": "michael", "nick": "nicholas",
    "chris": "christopher", "jon": "jonathan", "rob": "robert", "ollie": "oliver",
}


def name_words(name: str) -> frozenset[str]:
    return frozenset(NICKNAMES.get(w, w) for w in re.findall(r"[a-z0-9]+", fold(name)) if w)


def _club(name: str) -> str:
    return CLUB_ALIASES.get(fold(name), name)


def _plays_for(teams: Iterable[str], club_names: Iterable[str]) -> bool:
    return any(same_club(_club(a), _club(b)) for a in teams for b in club_names)


def link_season(totals: dict[int, dict], players: Iterable[PlayerSeason]) -> tuple[dict[int, dict], list[dict]]:
    """``({understat id: WhoScored totals}, unlinked)`` for one league-season.

    ``unlinked`` lists the WhoScored players with real minutes that could not be matched, so coverage is honest and visible.
    """
    players = list(players)
    by_words: dict[frozenset[str], list[PlayerSeason]] = {}
    for p in players:
        by_words.setdefault(name_words(p.name), []).append(p)

    linked: dict[int, dict] = {}
    pending: list[tuple[dict, list[str], list[PlayerSeason]]] = []
    ordered = sorted(totals.values(), key=lambda t: -t["min"])  # most minutes first, so a clash is settled by playing time
    for ws in ordered:
        words = name_words(ws["name"])
        clubs = [t for t, m in ws["teams"].items() if m > 0 and t]
        found = [p for p in by_words.get(words, []) if _plays_for(clubs, p.teams)]
        if not found and len(words) >= 2:
            # one name is the other plus an extra word ("Joao Pedro" / "Joao Pedro Junior"): only for full names, only on the same club
            found = [p for p in players if (name_words(p.name) < words or words < name_words(p.name)) and len(name_words(p.name)) >= 2 and _plays_for(clubs, p.teams)]
        if len(found) == 1 and found[0].id not in linked:
            linked[found[0].id] = ws
        else:
            pending.append((ws, clubs, found))

    # Understat lists many players by one word ("Alisson", "Gabriel"). Link such a name to a longer WhoScored one only when, after
    # everyone else is matched, it is the only unmatched candidate on both sides at that club.
    still: list[tuple[dict, list[str], list[PlayerSeason]]] = []
    for ws, clubs, found in pending:
        words = name_words(ws["name"])
        singles = [p for p in players if p.id not in linked and len(name_words(p.name)) == 1 and next(iter(name_words(p.name))) in words and _plays_for(clubs, p.teams)]
        if len(words) >= 2 and len(singles) == 1:
            single = singles[0]
            word = next(iter(name_words(single.name)))
            # a second unmatched WhoScored player at that club with the same word in his name makes it a coin toss
            rivals = [other for other, other_clubs, _f in pending if other is not ws and word in name_words(other["name"]) and _plays_for(other_clubs, single.teams)]
            if not rivals:
                linked[single.id] = ws
                continue
        still.append((ws, clubs, found))

    unlinked = [
        {"id": ws["id"], "name": ws["name"], "teams": clubs, "minutes": ws["min"], "candidates": [p.name for p in found]}
        for ws, clubs, found in still if ws["min"] >= 90
    ]
    return linked, unlinked
