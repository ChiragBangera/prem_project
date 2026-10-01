"""Matching people from another source to Understat players, strictly: by the words of the name *and* the club.

Names are spelt differently between sources ("Heung-Min Son" / "Son Heung-Min", accents, nicknames, "Vitalii" /
"Vitaliy"), so a match is never on a string: it is on the *set of name words*, and the person must also be at the same
club that season. If that leaves no candidate or more than one, the person is left unlinked, because a blank is better
than another man's birthdate or statistics.

Passes, in order, each only for people still unmatched:

1. the same name words at the same club;
2. one name is the other plus an extra word ("Joao Pedro" / "Joao Pedro Junior"): full names only;
3. Understat's single-word names ("Alisson", "Gabriel"): linked to a longer name only when, once everyone else is matched,
   it is the one unmatched candidate on both sides at that club;
4. the same last word and the same first initial at the same club ("Vitalii" / "Vitaliy Mykolenko"), again only when it is the
   one candidate on both sides.

With ``loose=True`` (for sources that also say what position a person plays) three more spelling-variant passes follow, each still
needing the same club and exactly one candidate on both sides: the same letters split differently ("Dasilva" / "Da Silva"); a
one-word name that is one word of a longer name and the position fits ("Yeray" / "Yeray Álvarez"); and one word a couple of
keystrokes off ("Yarmolyuk" / "Yarmoliuk"). They stay off for WhoScored, where a wrong link would put another man's statistics on a player.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Iterable, Sequence

from app.data.wikidata import same_club
from app.leagues import fold

# Spellings of one club that share no word, as groups of equivalent (folded, punctuation-free) names
CLUB_GROUPS: tuple[frozenset[str], ...] = tuple(frozenset(g) for g in (
    {"wolves", "wolverhampton wanderers"},
    {"spurs", "tottenham", "tottenham hotspur"},
    {"man utd", "manchester united"},
    {"man city", "manchester city"},
    {"newcastle utd", "newcastle united"},
    {"rb leipzig", "rasenballsport leipzig"},
    {"hertha berlin", "hertha bsc"},
    {"borussia monchengladbach", "borussia m gladbach", "monchengladbach", "gladbach"},
    {"hamburg sv", "hamburger sv", "hamburg"},
    {"fc cologne", "1 fc koln", "fc koln", "koln", "cologne"},
    {"bayern munich", "bayern munchen", "fc bayern munchen"},
    {"rennes", "stade rennais"},
    {"lyon", "olympique lyonnais"},
    {"atletico madrid", "atl madrid", "club atletico de madrid"},
    {"inter", "internazionale", "inter milan"},
    {"nurnberg", "nuernberg", "1 fc nurnberg"},
    {"fortuna dusseldorf", "fortuna duesseldorf"},
))

# the same given name written two ways; applied to every word, and a match still needs the same club
NICKNAMES = {
    "andy": "andrew", "matty": "matthew", "matt": "matthew", "josh": "joshua", "joe": "joseph", "tom": "thomas", "ben": "benjamin",
    "dan": "daniel", "danny": "daniel", "sam": "samuel", "will": "william", "alex": "alexander", "mike": "michael", "nick": "nicholas",
    "chris": "christopher", "jon": "jonathan", "rob": "robert", "ollie": "oliver",
    "kike": "enrique", "toni": "antonio", "tasos": "anastasios", "paco": "francisco", "nacho": "ignacio",
}
POSITION = {"G": "GK", "D": "D", "M": "M", "F": "F"}  # a squad list's position letter -> Understat's


def _plain(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", fold(text)).strip()


_CLUB_CANON = {name: sorted(group)[0] for group in CLUB_GROUPS for name in group}


def canonical_club(name: str) -> str:
    return _CLUB_CANON.get(_plain(name), name)


@lru_cache(maxsize=65536)
def _same(a: str, b: str) -> bool:
    return same_club(canonical_club(a), canonical_club(b))


def plays_for(teams: Iterable[str], club_names: Iterable[str]) -> bool:
    names = tuple(club_names)
    return any(_same(a, b) for a in teams for b in names)


def name_words(name: str) -> frozenset[str]:
    return frozenset(NICKNAMES.get(w, w) for w in re.findall(r"[a-z0-9]+", fold(name)) if w)


def _letters(words: frozenset[str]) -> str:
    """The letters of a name, whatever the spaces: "Jay Da Silva" and "Jay Dasilva" have the same ones."""
    return "".join(sorted("".join(words)))


def _surname_initial(name: str) -> tuple[str, str] | None:
    """(last word, first letter of the first word) for a name of two or more words: how a spelling variant of a first name is told apart."""
    tokens = [NICKNAMES.get(w, w) for w in re.findall(r"[a-z0-9]+", fold(name)) if w]
    return (tokens[-1], tokens[0][0]) if len(tokens) >= 2 else None


def _edits(a: str, b: str) -> int:
    """Number of single-letter changes between two words."""
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def _near(a: frozenset[str], b: frozenset[str]) -> bool:
    """Two names with the same number of words that differ in exactly one word, and those two words are at most two letters apart."""
    if len(a) != len(b):
        return False
    mine, theirs = a - b, b - a
    if len(mine) != 1 or len(theirs) != 1:
        return False
    x, y = next(iter(mine)), next(iter(theirs))
    return min(len(x), len(y)) >= 5 and abs(len(x) - len(y)) <= 2 and _edits(x, y) <= 2


def _fits(pos: str | None, player: Any) -> bool:
    """Whether a squad list's position is one of the positions Understat gives the player. Unknown on either side rules nothing out."""
    want = POSITION.get((pos or "")[:1].upper())
    have = {t for t in str(getattr(player, "position", "") or "").split() if t != "S"}
    return want is None or not have or want in have


@dataclass
class Person:
    """Someone from another source: a name (and optionally other spellings), the clubs he is at, a priority weight (e.g. minutes)
    and, if the source says, the position he plays (a letter: G, D, M or F)."""

    key: Any
    name: str
    clubs: list[str]
    weight: float = 0.0
    alt_names: list[str] = field(default_factory=list)
    pos: str | None = None

    def all_names(self) -> list[str]:
        return [self.name, *self.alt_names]


def link_people(people: Sequence[Person], players: Iterable[Any], *, loose: bool = False) -> tuple[dict[int, Person], list[tuple[Person, list[Any]]]]:
    """``({understat id: person}, [(person, candidate players)] for everyone left unmatched)``.

    ``players`` need only have ``id``, ``name`` and ``teams`` (``position`` is used by the loose passes). Most-weighted people are
    matched first, so a clash is settled by playing time.
    """
    players = list(players)
    words_of = {p.id: name_words(p.name) for p in players}
    initial_of = {p.id: _surname_initial(p.name) for p in players}
    multi = [p for p in players if len(words_of[p.id]) >= 2]
    by_words: dict[frozenset[str], list[Any]] = {}
    by_letters: dict[str, list[Any]] = {}
    for p in players:
        by_words.setdefault(words_of[p.id], []).append(p)
        by_letters.setdefault(_letters(words_of[p.id]), []).append(p)

    linked: dict[int, Person] = {}
    pending: list[tuple[Person, list[Any]]] = []
    for person in sorted(people, key=lambda x: -x.weight):
        found: list[Any] = []
        for name in person.all_names():
            words = name_words(name)
            hits = [p for p in by_words.get(words, []) if plays_for(person.clubs, p.teams)]
            if not hits and len(words) >= 2:
                hits = [p for p in multi if (words_of[p.id] < words or words < words_of[p.id]) and plays_for(person.clubs, p.teams)]
            if not hits and loose:
                hits = [p for p in by_letters.get(_letters(words), []) if plays_for(person.clubs, p.teams)]
            if hits:
                found = hits
                break
        unique = {p.id: p for p in found}
        if len(unique) == 1 and next(iter(unique)) not in linked:
            linked[next(iter(unique))] = person
        else:
            pending.append((person, list(unique.values())))

    # pass 3: Understat's one-word names
    singles_all = [p for p in players if len(words_of[p.id]) == 1]
    still: list[tuple[Person, list[Any]]] = []
    for person, found in pending:
        words = name_words(person.name)
        singles = [p for p in singles_all if p.id not in linked and next(iter(words_of[p.id])) in words and plays_for(person.clubs, p.teams)] if len(words) >= 2 else []
        if len(singles) == 1:
            single = singles[0]
            word = next(iter(words_of[single.id]))
            rivals = [other for other, _f in pending if other is not person and word in name_words(other.name) and plays_for(other.clubs, single.teams)]
            if not rivals:
                linked[single.id] = person
                continue
        still.append((person, found))

    # pass 4: same surname and same first initial at the same club (spelling variants of a first name)
    last: list[tuple[Person, list[Any]]] = []
    for person, found in still:
        key = _surname_initial(person.name)
        if key is not None:
            candidates = [p for p in players if p.id not in linked and initial_of[p.id] == key and plays_for(person.clubs, p.teams)]
            if len(candidates) == 1:
                rivals = [other for other, _f in still if other is not person and plays_for(other.clubs, candidates[0].teams) and _surname_initial(other.name) == key]
                if not rivals:
                    linked[candidates[0].id] = person
                    continue
        last.append((person, found))

    if loose:
        def settle(waiting, finder):
            """Link each waiting person to the one player ``finder`` offers him, when no other waiting person is offered that player too."""
            offers = {id(person): {p.id: p for name in person.all_names() for p in finder(person, name_words(name)) if p.id not in linked} for person, _f in waiting}
            rest = []
            for person, found in waiting:
                mine = offers[id(person)]
                if len(mine) == 1 and not any(next(iter(mine)) in offers[id(other)] for other, _f in waiting if other is not person):
                    linked[next(iter(mine))] = person
                else:
                    rest.append((person, found))
            return rest

        def by_mononym(person, words):  # "Yeray" on a squad list, "Yeray Álvarez" on Understat
            if len(words) != 1:
                return []
            found = [p for p in multi if p.id not in linked and next(iter(words)) in words_of[p.id] and plays_for(person.clubs, p.teams)]
            return found if len(found) != 1 or _fits(person.pos, found[0]) else []   # one candidate by name first, then his position must fit

        def by_spelling(person, words):  # one word spelt a little differently
            return [p for p in players if _near(words, words_of[p.id]) and plays_for(person.clubs, p.teams)] if len(words) >= 2 else []

        last = settle(settle(last, by_mononym), by_spelling)
    return linked, last
