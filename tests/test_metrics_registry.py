"""The metric registry: every declaration is complete and consistent, and the arithmetic does what its definition says."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.events import counters as C
from app.metrics import player as P
from app.metrics import team as T
from app.metrics.lenses import PLAYER_LENSES, TEAM_LENSES
from app.metrics.registry import Frame, counter, percentile_of, rate, ratio, shrunk
from app.metrics.views import PLAYER_VIEWS, TEAM_VIEWS

PLAYER = (*P.PLAYER_METRICS, *P.SCORE_METRICS)
SHOT_FIELDS = {"n", "goals", "xg", "sot", "blocked", "off", "post", "big", "big_goals", "pens", "pen_goals", "pen_xg", "sp_shots", "sp_xg", "sp_goals", "op_shots", "op_xg",
               "head", "head_xg", "head_goals", "dist", "box", "assisted", "fk", "fk_goals", "fk_xg", "xg_np"}
UNDERSTAT = {"minutes", "games", "goals", "npg", "assists", "shots", "key_passes", "yellow", "red", "xg", "npxg", "xa", "xgchain", "xgbuildup", "available", "age", "starts",
             "npxg_xa", "g_xg", "npg_npxg", "a_xa", "g_xg_z", "mins_per_app", "minutes_share", "output"}
TEAM_HISTORY = {"matches", "pts", "wins", "draws", "losses", "gf", "ga", "xg", "xga", "npxg", "npxga", "xpts", "deep", "deep_allowed", "ppda_att", "ppda_def", "oppda_att", "oppda_def", "cs",
                "squad_age", "players_used"}


def known_input(name: str, level: str) -> bool:
    """Every input a metric names is something the dataset builder actually puts in the frame."""
    if name.startswith(("w_", "wa_")):
        return name.split("_", 1)[1] in C.COUNTERS or name in ("w_matches",)
    if name.startswith(("s_", "sa_")):
        return name.split("_", 1)[1] in SHOT_FIELDS
    return name in (UNDERSTAT if level == "player" else TEAM_HISTORY) or name in PLAYER_KEYS | TEAM_KEYS


PLAYER_KEYS = {m.key for m in PLAYER}
TEAM_KEYS = {m.key for m in T.TEAM_METRICS}


@pytest.mark.parametrize("metrics,groups", [(PLAYER, P.GROUPS), (T.TEAM_METRICS, T.GROUPS)], ids=["player", "team"])
def test_every_declaration_is_complete_and_consistent(metrics, groups):
    keys = [m.key for m in metrics]
    assert len(keys) == len(set(keys)), "metric keys must be unique within a level"
    known_groups = {g.key for g in groups}
    for m in metrics:
        assert m.group in known_groups, m.key
        assert m.label and m.short and m.what and m.formula and m.inputs, f"{m.key} needs a label, a short name, a definition, a formula and its inputs"
        assert m.needs in ("base", "shots", "events") and m.source in ("understat", "whoscored", "both", "espn", "derived") and m.kind in ("raw", "derived")
        assert m.unit in ("per90", "pergame", "total", "count", "share", "ratio", "rating", "age", "metres", "pitch", "score"), (m.key, m.unit)
        assert m.hib in (True, False, None) and m.decimals in (0, 1, 2, 3)
        assert set(m.roles) <= {"ATT", "MID", "DEF", "GK"} and m.roles
        assert m.needs != "events" or m.source in ("whoscored", "both"), m.key     # a metric that needs event data says its source is the event data
        assert m.needs != "shots" or m.source == "understat", m.key                # ...and one that needs match pages is an Understat figure
    assert all(any(m.group == g.key for m in metrics) for g in groups), "an empty group would be an empty heading in the column picker"


def test_every_input_a_metric_names_is_something_the_builders_provide():
    for m in P.PLAYER_METRICS:
        for name in m.inputs:
            assert known_input(name, "player"), (m.key, name)
    for m in T.TEAM_METRICS:
        for name in m.inputs:
            assert known_input(name, "team"), (m.key, name)


def test_raw_means_exactly_the_figure_the_source_publishes():
    by = {m.key: m for m in P.PLAYER_METRICS}
    assert by["xg"].kind == "raw" and by["goals"].kind == "raw" and by["npxg90"].kind == "derived" and by["tackles90"].kind == "derived"
    assert all(m.source == "understat" for m in P.PLAYER_METRICS if m.kind == "raw")


def test_lenses_and_views_only_name_metrics_that_exist_and_explain_themselves():
    for level, metrics, lenses, views in (("player", PLAYER_KEYS, PLAYER_LENSES, PLAYER_VIEWS), ("team", TEAM_KEYS, TEAM_LENSES, TEAM_VIEWS)):
        assert len({l.key for l in lenses}) == len(lenses) and len({v.key for v in views}) == len(views)
        for l in lenses:
            assert l.level == level and l.blurb and len(l.explain) > 40 and l.rules and all(r.metric in metrics and r.op in (">=", "<=") for r in l.rules), l.key
            assert all(m in metrics for m in l.show) and (l.sort is None or l.sort in metrics)
            assert all(r.on in ("value", "pct") for r in l.rules)
        for v in views:
            assert v.metrics and all(m in metrics for m in v.metrics) and len(set(v.metrics)) == len(v.metrics), v.key
    # a lens that needs event data says so, and says it in its own explanation
    for l in PLAYER_LENSES:
        if l.needs == "events":
            assert "event data" in l.explain, l.key


# ------------------------------------------------------------------ arithmetic


def frame(**arrays) -> Frame:
    n = len(next(iter(arrays.values())))
    f = Frame(n)
    for k, v in arrays.items():
        f.set(k, v)
    return f


def test_a_missing_array_reads_as_unknown_never_as_zero():
    f = frame(minutes=[900.0, 90.0])
    assert np.isnan(f["w_tackles"]).all() and f.has("minutes") and not f.has("w_tackles")
    m = rate("tackles90", "T", "T", "defending", "w_tackles", per="w_min", formula="x", inputs=("w_tackles", "w_min"), what="x", source="whoscored", needs="events")
    value, num, den = m.compute(f)
    assert np.isnan(value).all()                       # no event data: blank


def test_rates_ratios_and_plain_values():
    f = frame(minutes=[900.0, 0.0, 450.0], goals=[9.0, 3.0, 2.0], shots=[30.0, 0.0, 10.0], w_min=[900.0, 900.0, np.nan], w_passes=[0.0, 100.0, 50.0], w_pass_ok=[0.0, 90.0, 40.0])
    per90 = rate("goals90", "G", "G", "shooting", "goals", formula="x", inputs=("goals", "minutes"), what="x")
    assert per90.compute(f)[0][0] == pytest.approx(0.9) and np.isnan(per90.compute(f)[0][1]) and per90.compute(f)[0][2] == pytest.approx(0.4)   # no minutes: unknown, not infinite
    share = ratio("pass_acc", "P", "P", "passing", "w_pass_ok", "w_passes", formula="x", inputs=("w_pass_ok", "w_passes"), what="x")
    v = share.compute(f)[0]
    assert np.isnan(v[0]) and v[1] == pytest.approx(0.9) and v[2] == pytest.approx(0.8)                     # no attempts: unknown, not 0%
    guarded = ratio("p", "P", "P", "passing", "w_pass_ok", "w_passes", min_den=60, formula="x", inputs=("a",), what="x")
    assert np.isnan(guarded.compute(f)[0][2]) and guarded.compute(f)[0][1] == pytest.approx(0.9)            # too few attempts to call it a rate
    total = counter("goals", "G", "G", "shooting", formula="x", inputs=("goals",), what="x")
    assert total.kind == "raw" and list(total.compute(f)[0]) == [9.0, 3.0, 2.0]
    expr = rate("g_s", "x", "x", "shooting", lambda fr: fr["goals"] + fr["shots"], formula="x", inputs=("a",), what="x")
    assert expr.compute(f)[0][0] == pytest.approx(90 * 39 / 900)


def test_few_minutes_are_pulled_toward_the_pool_average_and_many_are_not():
    f = frame(minutes=[90.0, 3000.0, 3000.0, 3000.0], goals=[3.0, 6.0, 6.0, 6.0])      # a 90-minute hat-trick against three ordinary seasons
    m = rate("goals90", "G", "G", "shooting", "goals", formula="x", inputs=("goals", "minutes"), what="x", k=720.0)
    value, num, den = m.compute(f)
    pool = np.array([True, True, True, True])
    ranked = shrunk(m, value, num, den, pool)
    assert value[0] == pytest.approx(3.0) and ranked[0] < 0.6 and abs(ranked[1] - value[1]) < 0.02       # the raw 3.0 per 90 is shown; the ranking does not trust it
    assert ranked[0] > ranked[1]                                                                          # ...but he is still above average, just not absurdly


def test_percentiles_read_higher_is_better_and_invert_where_fewer_is_better():
    pool = np.sort(np.array([1.0, 2.0, 3.0, 4.0]))
    values = np.array([4.0, 1.0, 2.5, np.nan])
    up, down = percentile_of(pool, values, True), percentile_of(pool, values, False)
    assert up[0] == pytest.approx(87.5) and up[1] == pytest.approx(12.5) and np.isnan(up[3])
    assert down[0] == pytest.approx(12.5) and down[1] == pytest.approx(87.5)                              # fouls: the cleanest player is the 87th percentile
    assert percentile_of(np.array([]), values, True).shape == values.shape and np.isnan(percentile_of(np.array([]), values, True)).all()


def test_the_public_form_carries_no_functions():
    d = P.PLAYER_METRICS[0].public()
    assert "num" not in d and "den" not in d and isinstance(d["inputs"], list) and d["formula"]
    import json

    json.dumps({m.key: m.public() for m in PLAYER})
    json.dumps({m.key: m.public() for m in T.TEAM_METRICS})
    assert not any(isinstance(v, float) and math.isnan(v) for m in PLAYER for v in m.public().values() if isinstance(v, float))
