"""The shared strict matcher: names by their words, always together with the club."""

from __future__ import annotations

from types import SimpleNamespace as NS

from app.data.people import Person, canonical_club, link_people, name_words, plays_for


def us(pid, name, *teams):
    return NS(id=pid, name=name, teams=list(teams))


def person(key, name, *clubs, weight=0.0, alt=(), pos=None):
    return Person(key=key, name=name, clubs=list(clubs), weight=weight, alt_names=list(alt), pos=pos)


def us_pos(pid, name, position, *teams):
    return NS(id=pid, name=name, teams=list(teams), position=position)


def keys(linked):
    return {uid: p.key for uid, p in linked.items()}


def test_club_names_that_share_no_word_still_match_through_the_alias_groups():
    for a, b in [("RasenBallsport Leipzig", "RB Leipzig"), ("Borussia M.Gladbach", "Borussia Mönchengladbach"), ("Hamburger SV", "Hamburg SV"),
                 ("Rennes", "Stade Rennais"), ("Lyon", "Olympique Lyonnais"), ("Wolverhampton Wanderers", "Wolves"), ("Fortuna Duesseldorf", "Fortuna Düsseldorf")]:
        assert plays_for([a], [b]) and plays_for([b], [a]), (a, b)
    assert not plays_for(["Manchester City"], ["Manchester United"]) and not plays_for(["Rennes"], ["Lyon"])
    assert canonical_club("Some Unlisted FC") == "Some Unlisted FC"


def test_same_words_same_club_links_whatever_the_order_accents_or_nickname():
    players = [us(1, "Son Heung-Min", "Tottenham"), us(2, "João Pedro", "Brighton"), us(3, "Andrew Robertson", "Liverpool"), us(4, "Gabriel Magalhaes", "Arsenal")]
    people = [person("a", "Heung-Min Son", "Tottenham Hotspur"), person("b", "Joao Pedro", "Brighton & Hove Albion"), person("c", "Andy Robertson", "Liverpool"),
              person("d", "Gabriel dos Santos Magalhães", "Arsenal", alt=["Gabriel Magalhães"])]
    linked, left = link_people(people, players)
    assert keys(linked) == {1: "a", 2: "b", 3: "c", 4: "d"} and left == []


def test_a_first_name_spelt_differently_links_on_surname_and_initial_when_unambiguous():
    players = [us(1, "Vitalii Mykolenko", "Everton"), us(2, "Alex Grimaldo", "Bayer Leverkusen")]
    people = [person("a", "Vitaliy Mykolenko", "Everton"), person("b", "Alejandro Grimaldo", "Leverkusen")]
    linked, left = link_people(people, players)
    assert keys(linked) == {1: "a", 2: "b"} and left == []


def test_the_surname_and_initial_rule_refuses_to_guess():
    players = [us(1, "Jordan Ayew", "Leicester"), us(2, "Jonathan Ayew", "Leicester")]
    assert link_people([person("a", "Mark Ayew", "Leicester")], players)[0] == {}                 # no candidate with his initial
    linked, left = link_people([person("a", "Joel Ayew", "Leicester")], players)
    assert linked == {} and len(left) == 1                                                       # two candidates share the initial: a coin toss
    # a different club is never enough
    assert link_people([person("a", "Vitaliy Mykolenko", "Chelsea")], [us(1, "Vitalii Mykolenko", "Everton")])[0] == {}
    # two people competing for one Understat player: neither is trusted
    linked, left = link_people([person("a", "Vitaliy Mykolenko", "Everton"), person("b", "Vitalyi Mykolenko", "Everton")], [us(1, "Vitalii Mykolenko", "Everton")])
    assert linked == {} and len(left) == 2


def test_single_word_understat_names_and_the_heavier_person_wins_a_clash():
    players = [us(10, "Alisson", "Liverpool"), us(11, "Gabriel", "Arsenal"), us(12, "Gabriel Jesus", "Arsenal"), us(13, "Rodrigo", "Manchester City")]
    people = [person(1, "Alisson Becker", "Liverpool"), person(2, "Gabriel Magalhaes", "Arsenal"), person(3, "Gabriel Jesus", "Arsenal"),
              person(4, "Rodrigo Hernandez", "Manchester City"), person(5, "Rodrigo Munoz", "Manchester City")]
    linked, left = link_people(people, players)
    assert keys(linked) == {10: 1, 11: 2, 12: 3} and {p.name for p, _c in left} == {"Rodrigo Hernandez", "Rodrigo Munoz"}
    # the same Understat player claimed twice: the one with more minutes keeps him
    linked, left = link_people([person("few", "Jan Smith", "Reds", weight=100), person("many", "Jan Smith", "Reds", weight=900)], [us(1, "Jan Smith", "Reds")])
    assert keys(linked) == {1: "many"} and [p.key for p, _c in left] == ["few"]


def test_name_words_ignore_order_accents_punctuation_and_nicknames():
    assert name_words("Heung-Min Son") == name_words("Son Heung-min") and name_words("Matty Cash") == name_words("Matthew Cash")
    assert name_words("Zoë  O'Neil") == name_words("zoe oneil".replace("oneil", "o neil"))


def test_letters_that_other_sources_write_differently_fold_to_the_same_words():
    assert name_words("Albert Grønbæk") == name_words("Albert Gronbaek") and name_words("Łukasz Fabiański") == name_words("Lukasz Fabianski")
    assert name_words("Đorđe Petrović") == name_words("Dorde Petrovic") and name_words("Sæther") == name_words("Saether")


def test_common_nicknames_are_one_name_even_in_the_strict_matcher():
    players = [us(1, "Kike Salas", "Sevilla"), us(2, "Antonio Martínez", "Alaves"), us(3, "Tasos Douvikas", "Como")]
    people = [person("a", "Enrique Salas", "Sevilla FC"), person("b", "Toni Martínez", "Deportivo Alaves"), person("c", "Anastasios Douvikas", "Como")]
    assert keys(link_people(people, players)[0]) == {1: "a", 2: "b", 3: "c"}


def test_the_loose_passes_are_off_unless_asked_for():
    players = [us(1, "Jay Dasilva", "Coventry"), us_pos(2, "Yeray Álvarez", "D", "Athletic Club"), us(3, "Yehor Yarmolyuk", "Brentford")]
    people = [person("a", "Jay Da Silva", "Coventry City"), person("b", "Yeray", "Athletic Club", pos="D"), person("c", "Yehor Yarmoliuk", "Brentford")]
    linked, left = link_people(people, players)
    assert linked == {} and len(left) == 3
    assert keys(link_people(people, players, loose=True)[0]) == {1: "a", 2: "b", 3: "c"}


def test_a_name_split_differently_is_the_same_name_at_the_same_club():
    players = [us(1, "Jay Dasilva", "Coventry"), us(2, "Jay Dasilva", "Leeds")]
    linked, left = link_people([person("a", "Jay Da Silva", "Coventry City")], players, loose=True)
    assert keys(linked) == {1: "a"}                                                                # the one at his club, not his namesake elsewhere
    assert link_people([person("a", "Jay Da Silva", "Chelsea")], players, loose=True)[0] == {}


def test_a_one_word_squad_list_name_needs_a_longer_name_with_that_word_the_right_position_and_no_rival():
    players = [us_pos(1, "Yeray Álvarez", "D", "Athletic Club"), us_pos(2, "Pedro Lima", "D S", "Sevilla"), us_pos(3, "Pedro Silva", "F", "Sevilla")]
    assert keys(link_people([person("a", "Yeray", "Athletic", pos="D")], players, loose=True)[0]) == {1: "a"}
    assert link_people([person("a", "Yeray", "Athletic", pos="F")], players, loose=True)[0] == {}   # a forward cannot be a defender: not him
    assert link_people([person("a", "Pedro", "Sevilla", pos="D")], players, loose=True)[0] == {}    # two Pedros at the club (one fits): the other might be him
    assert keys(link_people([person("a", "Pedro", "Sevilla", pos="F")], [players[2]], loose=True)[0]) == {3: "a"}
    listed_in_full = [person("a", "Yeray", "Athletic", pos="D"), person("b", "Yeray Álvarez", "Athletic", pos="D")]
    linked, left = link_people(listed_in_full, players, loose=True)
    assert keys(linked) == {1: "b"} and [p.key for p, _ in left] == ["a"]                          # a full name takes the player first; the one-word entry is someone else
    assert link_people([person("a", "Yeray", "Villarreal", pos="D")], players, loose=True)[0] == {}   # his club, always


def test_one_word_a_couple_of_letters_off_links_only_when_it_is_the_one_candidate_on_both_sides():
    players = [us(1, "Mohamed Abdelmonem", "Nice"), us(2, "Ionut Radu", "Celta Vigo"), us(3, "Niakhate Ndiaye", "Parma"), us(4, "Jonas Ahn", "Nice")]
    people = [person("a", "Mohamed Abdelmoneim", "OGC Nice"), person("b", "Andrei Radu", "Celta Vigo"), person("c", "Abdoulaye Ndiaye", "Parma")]
    assert keys(link_people(people, players, loose=True)[0]) == {1: "a"}                          # different first names: other people, never matched
    twin = people[:1] + [person("d", "Mohamed Abdelmoneyn", "OGC Nice")]
    assert link_people(twin, players[:1], loose=True)[0] == {}                                    # two spellings compete for one player: neither is trusted
    short = [us(5, "Li Wei", "Nice")]                                                             # words under five letters are too short to call a typo
    assert link_people([person("e", "Li Wen", "Nice")], short, loose=True)[0] == {}
