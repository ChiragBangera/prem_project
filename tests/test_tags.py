"""Profile tags: declared as data, evaluated on role percentiles, explained in words, and listed in the catalog the browser reads."""

from __future__ import annotations

import pytest

from app.metrics import player as P
from app.metrics import tags as TG
from app.metrics.catalog import build_catalog

PLAYER_KEYS = {m.key for m in (*P.PLAYER_METRICS, *P.SCORE_METRICS)}


def test_every_tag_names_metrics_that_exist_and_is_explained():
    keys = [t.key for t in TG.TAGS]
    assert len(keys) == len(set(keys)) and all(t.group in TG.ROLE_ORDER for t in TG.TAGS)
    for t in TG.TAGS:
        assert t.label and t.blurb and t.rules and t.lead and t.evidence
        named = {m for r in t.rules for m in r.metrics} | set(t.lead) | {m for m, _name in t.evidence}
        assert named <= PLAYER_KEYS, f"{t.key} names {sorted(named - PLAYER_KEYS)}"
        assert all(r.op in (">=", "<=", "<") and 0 <= r.level <= 100 for r in t.rules)
        assert set(t.lead) <= {m for r in t.rules for m in r.metrics}, f"{t.key} is ranked by a metric none of its rules look at"


def test_a_rule_reads_the_percentile_the_way_it_says():
    top = TG.Rule(("a",), ">=", 85)
    assert top.holds({"a": 85}) and top.holds({"a": 99}) and not top.holds({"a": 84.9})
    bottom = TG.Rule(("a",), "<=", 40)
    assert bottom.holds({"a": 40}) and bottom.holds({"a": 0}) and not bottom.holds({"a": 41})
    below = TG.Rule(("a",), "<", 55)
    assert below.holds({"a": 54.9}) and not below.holds({"a": 55})
    either = TG.Rule(("a", "b"), ">=", 80)                                   # any one of the listed metrics will do
    assert either.holds({"a": 10, "b": 90}) and either.holds({"a": 90}) and not either.holds({"a": 70, "b": 79})


def test_an_unknown_percentile_never_earns_a_tag_and_is_never_read_as_zero():
    assert not TG.Rule(("a",), ">=", 85).holds({}) and not TG.Rule(("a",), ">=", 85).holds({"a": None})
    assert not TG.Rule(("a",), "<", 55).holds({"a": None}) and not TG.Rule(("a",), "<=", 40).holds({})   # "below" does not mean "unknown"
    pct = {"npxg90": 95.0}                                                     # a poacher also needs xA below the 55th percentile: unknown xA cannot show that
    assert TG.earned("ATT", pct) == []


def test_every_rule_must_hold_and_tags_are_only_for_their_own_role():
    poacher = {"npxg90": 93.0, "xa90": 30.0}
    assert [t["key"] for t in TG.earned("ATT", poacher)][:1] == ["poacher"]
    assert TG.earned("ATT", {"npxg90": 93.0, "xa90": 60.0}) == []             # high npxG alone is not enough: his xA is too good for a poacher
    assert "poacher" not in [t["key"] for t in TG.earned("MID", poacher)]
    assert TG.earned("GK", {"save_pct": 90.0})[0]["key"] == "stopper_gk"


def test_a_player_keeps_at_most_three_tags_strongest_first_and_each_says_why():
    everything = {m: 99.0 for t in TG.TAGS for r in t.rules for m in r.metrics}
    everything.update({"xa90": 60.0})                                          # keeps the poacher out, lets the creating tags in
    got = TG.earned("ATT", everything)
    assert 1 <= len(got) <= TG.MAX_TAGS == 3
    strengths = [TG.TAG_BY_KEY[t["key"]].strength(everything) for t in got]
    assert strengths == sorted(strengths, reverse=True)
    assert all(t["why"] and "among attackers" in t["why"] for t in got)
    assert "top 1% for" in got[0]["why"]                                       # a 99th percentile reads "top 1%", never "top 0%"


def test_a_broad_tag_does_not_always_beat_a_narrow_one():
    volume = TG.TAG_BY_KEY["volume"]
    assert volume.handicap > 0
    pct = {"shots90": 90.0, "xgps": 30.0, "npxg90": 88.0, "xa90": 20.0}
    order = [t["key"] for t in TG.earned("ATT", pct)]
    assert order.index("poacher") < order.index("volume")                      # the handicap lets the sharper description lead


def test_the_rule_is_written_in_words_a_reader_can_check():
    label = {"npxg90": "npxG/90", "xa90": "xA/90", "shots90": "shots/90", "xgps": "xG/shot"}.get
    text = TG.explain(TG.TAG_BY_KEY["poacher"], lambda k: label(k) or k)
    assert text == "npxG/90 in the top 15% of attackers, and xA/90 below the 55th percentile of attackers"
    assert "no better than the 40th percentile" in TG.explain(TG.TAG_BY_KEY["volume"], lambda k: label(k) or k)
    either = TG.explain(TG.TAG_BY_KEY["wide"], lambda k: k)
    assert " or " in either and "defenders" in either


def test_the_catalog_lists_every_tag_with_its_rules_for_the_browser():
    catalog = build_catalog()
    listed = catalog["player"]["tags"]
    assert [t["key"] for t in listed] == [t.key for t in TG.TAGS]
    poacher = next(t for t in listed if t["key"] == "poacher")
    assert poacher["group"] == "ATT" and poacher["explain"] == "npxG/90 in the top 15% of attackers, and xA/90 below the 55th percentile of attackers"
    assert poacher["rules"][0] == {"metrics": ["npxg90"], "op": ">=", "level": 85}
    assert all(set(r["metrics"]) <= set(catalog["player"]["metrics"]) for t in listed for r in t["rules"])
    import json

    json.dumps(listed)                                                         # plain data only: no functions leak into the payload


@pytest.mark.parametrize("group", TG.ROLE_ORDER)
def test_each_role_has_something_to_be_known_for(group):
    assert any(t.group == group for t in TG.TAGS)
