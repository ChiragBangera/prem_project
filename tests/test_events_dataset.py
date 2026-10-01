"""Event data inside the scouting dataset: additive, ranked among role peers, honest about who has it."""

from __future__ import annotations

from datetime import date

import pytest

from app.analytics.players import build_dataset
from app.events.aggregate import COUNTS
from app.events.rates import EVENT_KEYS

TODAY = date(2020, 6, 1)


def totals_for(pid: int, minutes: float = 1800.0) -> dict:
    """Synthetic event counts that grow with the id, so rankings are predictable: a higher id duels more and wins more."""
    scale = 1 + pid % 7
    t = {k: 0 for k in COUNTS}
    t.update(passes=600 * scale // 4, pass_ok=420 * scale // 4, fwd=150 * scale // 4, prog=20 * scale, tackles=10 * scale, challenges=20, aer=30,
             aer_won=10 + scale * 2, aer_def=20, aer_def_won=5 + scale * 2, **{"int": 8 * scale, "rec": 30 * scale})
    return {**t, "id": pid, "name": f"P{pid}", "teams": {"X": minutes}, "min": minutes, "matches": 20, "starts": 20}


def test_event_data_is_additive_and_players_without_it_stay_blank(demo_league):
    base = build_dataset([demo_league], today=TODAY)
    with_events = build_dataset([demo_league], events_of=lambda pid: totals_for(pid) if pid % 2 == 0 else None, today=TODAY)

    # nothing that already existed moves
    assert [(r["id"], r["output"], r["pct"], r["rank"]) for r in base.rows] == [(r["id"], r["output"], r["pct"], r["rank"]) for r in with_events.rows]
    assert base.event_players == 0 and with_events.event_players == len([r for r in with_events.rows if r["id"] % 2 == 0])

    have = [r for r in with_events.rows if r["ev_minutes"] > 0]
    none = [r for r in with_events.rows if r["ev_minutes"] == 0]
    assert have and none
    assert all(all(r[k] is None for k in EVENT_KEYS) and r["evpct"] == {} and not r["ev_in_pool"] for r in none)
    assert all(r["passes90"] is not None and r["def_duels90"] is not None for r in have)
    assert all(all(0 <= v <= 100 for v in r["evpct"].values()) for r in have)
    # goalkeepers are not ranked on these, like the Understat metrics
    assert all(r["evpct"] == {} for r in have if r["group"] == "GK")
    assert base.rows[0]["ev_minutes"] == 0 and all(r[k] is None for r in base.rows for k in EVENT_KEYS)


def test_event_percentiles_rank_among_role_peers_who_have_events(demo_league):
    ds = build_dataset([demo_league], events_of=totals_for, today=TODAY)
    defenders = [r for r in ds.rows if r["group"] == "DEF" and r["ev_in_pool"]]
    assert len(defenders) >= 4
    low = min(defenders, key=lambda r: r["tackles90"])
    high = max(defenders, key=lambda r: r["tackles90"])
    assert high["evpct"]["tackles90"] > low["evpct"]["tackles90"] and high["evrank"]["tackles90"] < low["evrank"]["tackles90"]
    assert all(1 <= r["evrank"]["tackles90"] <= r["ev_pool_n"] for r in defenders)
    assert ds.event_pool_minutes == 450 and all(r["ev_pool_n"] > 0 for r in defenders)   # a quarter of the most any player has, clamped


def test_few_attempts_are_pulled_toward_the_average_not_ranked_on_a_lucky_streak(demo_league):
    def events_of(pid):
        t = totals_for(pid)
        if pid % 5 == 0:   # a player who won his only 2 duels outright must not outrank someone who won most of 60
            t.update(tackles=2, challenges=0, aer_def=0, aer_def_won=0)
        return t

    ds = build_dataset([demo_league], events_of=events_of, today=TODAY)
    lucky = [r for r in ds.rows if r["id"] % 5 == 0 and r["group"] != "GK" and r["ev_in_pool"]]
    steady = [r for r in ds.rows if r["id"] % 5 != 0 and r["group"] != "GK" and r["ev_in_pool"] and r["def_duel_win"] and r["def_duel_win"] > 0.5]
    assert lucky and steady
    assert all(r["def_duel_win"] == 1.0 for r in lucky)                       # the raw rate is shown as it is...
    best_steady = max(r["evpct"].get("def_duel_win", 0) for r in steady)
    assert all(r["evpct"]["def_duel_win"] < best_steady for r in lucky)       # ...but the ranking does not trust 2 duels


def test_player_detail_carries_an_event_card_only_when_events_exist(demo_league):
    from app.analytics.player_detail import player_detail

    ds = build_dataset([demo_league], events_of=lambda pid: totals_for(pid) if pid % 2 == 0 else None, today=TODAY)
    with_ev = next(r for r in ds.rows if r["id"] % 2 == 0 and r["group"] == "DEF" and r["ev_in_pool"])
    without = next(r for r in ds.rows if r["id"] % 2 == 1)
    card = player_detail(with_ev, None, [2019])["events"]
    assert card["available"] and card["pool_n"] > 0 and card["pool_minutes"] == 450 and card["matches"] == 20
    keys = [i["key"] for i in card["items"]]
    assert keys[:3] == ["def_duels90", "def_duel_win", "tackles90"]          # a defender's own measures come first
    assert all(i["focus"] for i in card["items"][:8]) and all(0 <= i["pct"] <= 100 for i in card["items"] if i["pct"] is not None)
    assert player_detail(without, None, [2019])["events"] == {"available": False}


def test_a_barely_fetched_season_still_has_a_ranking_pool(demo_league):
    def one_match(pid):
        return totals_for(pid, minutes=90.0)

    ds = build_dataset([demo_league], events_of=one_match, today=TODAY)
    assert ds.event_pool_minutes == 45                      # half of the busiest player's 90, not an unreachable 180
    outfield = [r for r in ds.rows if r["group"] != "GK" and r["ev_in_pool"]]
    assert outfield and all(r["evpct"] for r in outfield)


def test_player_insights_use_event_data_only_when_the_ranking_is_meaningful(demo_league):
    from app.insights.player import player_insights

    def events_of(pid):
        t = totals_for(pid)
        if pid == star_id:
            t.update(tackles=400, challenges=10, aer_def=40, aer_def_won=35, aer=60, aer_won=50)        # wins nearly every duel, and plenty of them
        if pid == loser_id:
            t.update(tackles=2, challenges=60, aer_def=40, aer_def_won=4, aer=60, aer_won=8)             # loses nearly every duel
        return t

    base = build_dataset([demo_league], today=TODAY)
    defenders = [r for r in base.rows if r["group"] == "DEF" and r["minutes"] >= 900]
    star_id, loser_id = defenders[0]["id"], defenders[1]["id"]
    ds = build_dataset([demo_league], events_of=events_of, today=TODAY)
    by = {r["id"]: r for r in ds.rows}

    star = [i for i in player_insights(by[star_id]) if i.id.endswith("event_strength")]
    assert star and "defensive duels" in star[0].headline and star[0].tone == "positive" and star[0].evidence
    loser = [i for i in player_insights(by[loser_id]) if i.id.endswith("event_duels")]
    assert loser and loser[0].tone == "negative" and "Loses most" in loser[0].headline

    # no event data, or too few peers to rank against: no event findings at all
    assert not any(i.id.endswith(("event_strength", "event_duels")) for i in player_insights(next(r for r in base.rows if r["group"] == "DEF")))
    thin = build_dataset([demo_league], events_of=lambda pid: totals_for(pid) if pid in {star_id, loser_id} else None, today=TODAY)
    assert not any(i.id.endswith(("event_strength", "event_duels")) for r in thin.rows for i in player_insights(r) if r["group"] != "GK")


def test_scouting_highlights_add_event_cards_only_with_solid_event_data(demo_league):
    from app.insights.player import scouting_highlights

    base = build_dataset([demo_league], today=TODAY)
    defenders = [r for r in base.rows if r["group"] == "DEF" and r["minutes"] >= 900]
    star_id = defenders[0]["id"]

    def events_of(pid):
        t = totals_for(pid)
        if pid == star_id:   # wins almost every duel, plenty of them, and moves the ball forward accurately
            t.update(tackles=300, challenges=10, aer_def=60, aer_def_won=55, prog=900, passes=900, pass_ok=860, fwd=300)
        return t

    ds = build_dataset([demo_league], events_of=events_of, today=TODAY)
    ids = [i.id for i in scouting_highlights(ds.rows)]
    assert f"scout.winner.DEF.{star_id}" in ids and f"scout.progressor.DEF.{star_id}" in ids
    assert not [i for i in scouting_highlights(base.rows) if i.id.startswith(("scout.winner", "scout.progressor"))]
    cameo = build_dataset([demo_league], events_of=lambda pid: totals_for(pid, minutes=90.0), today=TODAY)   # one match each: too little to headline anyone
    assert not [i for i in scouting_highlights(cameo.rows) if i.id.startswith(("scout.winner", "scout.progressor"))]
