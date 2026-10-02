"""The scouting dataset: merging, roles, shrinkage, percentiles, luck and tags."""

from __future__ import annotations

from datetime import date

import pytest

from app.analytics.players import (
    SeasonInput,
    archetype_tags,
    build_dataset,
    merge_players,
    pool_minutes_for,
    sample_label,
)
from app.analytics.roles import RoleModel, families_of, group_from_favorite
from app.data.models import LeagueSeason, PlayerSeason


def make_player(pid, name, position="F", minutes=1800, goals=8, xg=7.0, npxg=6.5, assists=2, xa=2.5, shots=50,
                kp=20, chain=9.0, buildup=2.0, team="Alpha FC", games=None, season=2025):
    return PlayerSeason(
        id=pid, name=name, teams=[team], position=position, games=games or max(1, minutes // 80), minutes=minutes,
        goals=goals, npg=goals, assists=assists, shots=shots, key_passes=kp, yellow=2, red=0, xg=xg, npxg=npxg,
        xa=xa, xgchain=chain, xgbuildup=buildup, league="EPL", season=season,
    )


def league_of(players, season=2025, rounds=10):
    from app.data.models import Team, TeamMatch

    def tm(i):
        return TeamMatch(f"2025-09-{i + 1:02d} 15:00:00", "h", 1, 1, 1, 1, 5, 5, 1, 1, 1.3, 1, "d", 200, 20, 200, 20)

    teams = {name: Team(1, name, name[:3], [tm(i) for i in range(rounds)]) for name in {p.teams[0] for p in players}}
    return LeagueSeason("EPL", season, teams, players, [])


# ------------------------------------------------------------------ roles


def test_families_and_favorites():
    assert families_of("F M S") == (("F", "M"), True)
    assert families_of("GK") == (("GK",), False)
    assert families_of("D") == (("D",), False)
    assert families_of("") == ((), False)
    assert [group_from_favorite(c) for c in ("FW", "AMR", "AML", "AMC", "MC", "DMC", "DL", "DC", "GK", "Sub", None)] == [
        "ATT", "ATT", "ATT", "MID", "MID", "MID", "DEF", "DEF", "GK", None, None,
    ]


def test_role_model_assigns_profile_to_the_closer_family():
    # features: [npxg90, shots90, xa90]
    samples = [("F", [0.45 + 0.02 * i, 3.0, 0.08]) for i in range(10)] + [("M", [0.08 + 0.01 * i, 1.0, 0.20]) for i in range(10)]
    model = RoleModel.fit(samples)
    assert model.classify(["F", "M"], [0.5, 3.2, 0.07])[0] == "F"
    assert model.classify(["F", "M"], [0.09, 0.9, 0.22])[0] == "M"
    family, confidence = model.classify(["F", "M"], [0.5, 3.2, 0.07])
    assert confidence > 0.3
    assert RoleModel.fit(samples[:3]) is None  # too little to trust


# ------------------------------------------------------------------ merge & pool


def test_merge_sums_seasons_and_keeps_latest_identity():
    a = league_of([make_player(1, "A", minutes=1000, goals=5, team="Alpha FC", season=2024)], season=2024)
    b = league_of([make_player(1, "A", minutes=2000, goals=10, team="Beta United", season=2025, position="M")], season=2025)
    (m,) = merge_players([SeasonInput(b), SeasonInput(a)])
    assert (m.c["minutes"], m.c["goals"]) == (3000, 15)
    assert m.teams == ["Beta United"] and m.position == "M" and m.seasons == [2024, 2025]
    assert m.available == 2 * 10 * 90  # two seasons of ten matches


def test_pool_minutes_scale_with_season_progress():
    early = league_of([make_player(1, "A")], rounds=6)
    full = league_of([make_player(1, "A")], rounds=38)
    assert pool_minutes_for([early]) == 180  # floor
    assert pool_minutes_for([full]) == 840  # 25% of 3420 minutes, floored to a multiple of 30
    assert pool_minutes_for([full, full]) == 900  # capped
    assert sample_label(100) == "low" and sample_label(900) == "ok" and sample_label(2500) == "solid"


# ------------------------------------------------------------------ dataset


def build(players, **kwargs):
    return build_dataset([league_of(players, rounds=38)], today=date(2026, 1, 1), **kwargs)


def by_name(ds, name):
    return next(r for r in ds.rows if r["name"] == name)


def field_of_forwards():
    players = [make_player(100 + i, f"Fwd {i}", minutes=2000, xa=1.0 + 0.2 * i, npxg=4 + 0.5 * i, xg=4.4 + 0.5 * i, goals=4 + i,
                           shots=30 + 3 * i) for i in range(12)]
    return players


def test_percentiles_rank_within_group_and_orient_correctly():
    ds = build(field_of_forwards() + [make_player(200, "Mid", position="M", minutes=2000, npxg=0.5, xa=6.0, kp=60, xg=0.6)])
    best, worst = by_name(ds, "Fwd 11"), by_name(ds, "Fwd 0")
    assert best["group"] == "ATT" and best["pct"]["npxg90"] > 90 and worst["pct"]["npxg90"] < 10
    assert best["output"] > worst["output"]
    assert by_name(ds, "Mid")["group"] == "MID"
    assert ds.group_sizes["ATT"] == 12 and ds.pool_minutes == 840


def test_yellow_cards_percentile_is_inverted():
    calm = make_player(1, "Calm", position="D", minutes=2000)
    calm.yellow = 0
    rough = make_player(2, "Rough", position="D", minutes=2000)
    rough.yellow = 12
    ds = build([calm, rough] + [make_player(10 + i, f"D{i}", position="D", minutes=2000) for i in range(8)])
    assert by_name(ds, "Calm")["pct"]["yellow90"] > by_name(ds, "Rough")["pct"]["yellow90"]


def test_small_samples_are_shrunk_so_cameos_cannot_top_the_table():
    regulars = field_of_forwards()
    cameo = make_player(300, "Cameo", minutes=90, goals=1, npxg=0.9, xg=0.9, xa=0.4, shots=5, kp=1)  # 0.9 npxG in one cameo = 3x the norm
    ds = build(regulars + [cameo])
    row = by_name(ds, "Cameo")
    assert row["npxg90"] == pytest.approx(0.9, abs=0.01)  # displayed rate is raw
    assert row["pct"]["npxg90"] < by_name(ds, "Fwd 11")["pct"]["npxg90"]  # ranking value is shrunk
    assert row["sample"] == "low" and not row["in_pool"]


def test_luck_z_scales_with_sample_size():
    lucky_small = make_player(1, "Small", goals=4, xg=1.0, npxg=1.0, shots=8, minutes=400)
    lucky_big = make_player(2, "Big", goals=24, xg=21.0, npxg=21.0, shots=120, minutes=3000)
    ds = build([lucky_small, lucky_big] + field_of_forwards())
    small, big = by_name(ds, "Small"), by_name(ds, "Big")
    assert small["g_xg"] == pytest.approx(3.0) and big["g_xg"] == pytest.approx(3.0)
    assert small["g_xg_z"] > big["g_xg_z"] > 0  # same surplus, fewer shots => more surprising


def test_age_uses_injected_birthdate_and_is_blank_when_unknown():
    players = field_of_forwards()
    ds = build(players, dob_of=lambda name, team: "2003-08-01" if name == "Fwd 3" else None)
    assert by_name(ds, "Fwd 3")["age"] == 22 and by_name(ds, "Fwd 4")["age"] is None
    assert ds.ages_known == 1


def test_favorite_position_overrides_listed_and_inferred_roles():
    winger = make_player(1, "Winger", position="F M S", minutes=2000)
    ds = build(field_of_forwards() + [winger], favorite_of=lambda pid: "AML" if pid == 1 else None)
    row = by_name(ds, "Winger")
    assert (row["group"], row["group_source"], row["favorite"]) == ("ATT", "favorite", "AML")


def test_multi_family_players_are_inferred_from_their_profile():
    strikers = [make_player(100 + i, f"Striker {i}", position="F", minutes=2000, npxg=9 + 0.1 * i, xg=9.5, xa=1.0, kp=10,
                            shots=90, chain=9, buildup=1) for i in range(10)]
    mids = [make_player(200 + i, f"Mid {i}", position="M", minutes=2000, npxg=1.5 + 0.1 * i, xg=1.6, xa=5 + 0.1 * i, kp=60,
                        shots=20, chain=16, buildup=8) for i in range(10)]
    hybrid_attacker = make_player(1, "Looks Like A Striker", position="F M S", minutes=2000, npxg=9.5, xg=10, xa=1.2, kp=11, shots=88, chain=9, buildup=1)
    hybrid_mid = make_player(2, "Looks Like A Mid", position="F M S", minutes=2000, npxg=1.7, xg=1.8, xa=5.2, kp=58, shots=19, chain=15, buildup=8)
    ds = build(strikers + mids + [hybrid_attacker, hybrid_mid])
    a, b = by_name(ds, "Looks Like A Striker"), by_name(ds, "Looks Like A Mid")
    assert (a["group"], a["group_source"]) == ("ATT", "inferred")
    assert (b["group"], b["group_source"]) == ("MID", "inferred")
    assert ds.role_model_ok and ds.inferred == 2


def test_goalkeepers_have_no_percentiles_or_tags():
    ds = build(field_of_forwards() + [make_player(999, "Keeper", position="GK", minutes=3000, goals=0, xg=0, npxg=0, shots=0, kp=0, xa=0)])
    keeper = by_name(ds, "Keeper")
    assert keeper["group"] == "GK" and keeper["output"] is None and keeper["tags"] == []
    assert not {"npxg90", "shots90", "xa90", "kp90", "xgchain90", "xgbuildup90", "contrib90"} & set(keeper["pct"])  # no shooting or creating percentiles for a goalkeeper


def test_archetype_tags_explain_themselves():
    row = {"group": "ATT", "pct": {"npxg90": 93.0, "xa90": 30.0, "kp90": 40.0, "shots90": 60.0, "xgps": 70.0, "xgbuildup90": 20.0}}
    tags = archetype_tags(row)
    assert tags[0]["key"] == "poacher" and "top 7% for npxG/90" in tags[0]["why"] and "attackers" in tags[0]["why"]
    creator = {"group": "ATT", "pct": {"npxg90": 40, "xa90": 92.0, "kp90": 88.0, "shots90": 50, "xgps": 50, "xgbuildup90": 50}}
    assert archetype_tags(creator)[0]["key"] == "creator"
    volume = {"group": "ATT", "pct": {"npxg90": 60, "xa90": 50, "kp90": 50, "shots90": 92.0, "xgps": 25.0, "xgbuildup90": 50}}
    assert "volume" in [t["key"] for t in archetype_tags(volume)]
    assert archetype_tags({"group": "DEF", "pct": {}}) == []


# ------------------------------------------------------------------ demo world end-to-end


def test_demo_league_dataset_is_sane(demo_league):
    ds = build_dataset([demo_league], today=date(2020, 6, 1))
    assert len(ds.rows) == len(demo_league.players) and ds.role_model_ok
    assert 700 <= ds.pool_minutes <= 900
    groups = {g: n for g, n in ds.group_sizes.items()}
    assert groups["ATT"] > 30 and groups["MID"] > 40 and groups["DEF"] > 60 and groups["GK"] >= 15
    starters = [r for r in ds.rows if r["in_pool"] and r["group"] != "GK"]
    for r in starters:
        assert 0 <= min(r["pct"].values()) and max(r["pct"].values()) <= 100
        assert r["output"] is not None
    # top output attackers really are the most productive by npxG+xA per 90
    attackers = sorted((r for r in starters if r["group"] == "ATT"), key=lambda r: -r["output"])
    assert sum(r["contrib90"] for r in attackers[:5]) / 5 > sum(r["contrib90"] for r in attackers[-5:]) / 5
    assert all(0 <= r["minutes_share"] <= 1 for r in ds.rows)
    shares = [r["minutes_share"] for r in starters]
    assert max(shares) > 0.85
    tagged = [r for r in starters if r["tags"]]
    assert len(tagged) > 20
