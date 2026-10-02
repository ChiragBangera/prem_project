"""Compatibility view of the metric registry for code written before it existed.

The registry (:mod:`app.metrics`) is the single source of truth. This module only re-exposes it under the names older
modules import (``METRIC_BY_KEY``, ``PROFILE_METRICS`` ...) so insights, similarity, compare and the player page keep working.
New code should import from :mod:`app.metrics` directly.
"""

from __future__ import annotations

from app.metrics import player as _player
from app.metrics import team as _team

GROUP_LABELS = {"GK": "Goalkeeper", "DEF": "Defender", "MID": "Midfielder", "ATT": "Attacker"}
GROUP_ORDER = ("ATT", "MID", "DEF", "GK")
_GROUP_TITLE = {g.key: g.label for g in (*_player.GROUPS, *_team.GROUPS)}


class LegacyMetric:
    """The attribute names the first version of the app used, over a registry metric."""

    __slots__ = ("m",)

    def __init__(self, m):
        self.m = m

    key = property(lambda s: s.m.key)
    label = property(lambda s: s.m.label)
    short = property(lambda s: s.m.short)
    category = property(lambda s: _GROUP_TITLE.get(s.m.group, s.m.group))
    unit = property(lambda s: s.m.unit)
    decimals = property(lambda s: s.m.decimals)
    higher_is_better = property(lambda s: s.m.hib is not False)
    what = property(lambda s: s.m.what)
    read = property(lambda s: s.m.read)

    def to_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "short": self.short, "category": self.category, "unit": self.unit, "decimals": self.decimals,
                "higher_is_better": self.higher_is_better, "what": self.what, "read": self.read}


PLAYER_METRICS = tuple(LegacyMetric(m) for m in _player.PLAYER_METRICS if m.needs != "events")
EVENT_METRICS = tuple(LegacyMetric(m) for m in _player.PLAYER_METRICS if m.needs == "events")
TEAM_METRICS = tuple(LegacyMetric(m) for m in _team.TEAM_METRICS)
METRIC_BY_KEY = {m.key: m for m in PLAYER_METRICS}
METRIC_BY_KEY.update({m.key: LegacyMetric(m) for m in _player.SCORE_METRICS})
EVENT_BY_KEY = {m.key: m for m in EVENT_METRICS}

PROFILE_METRICS = dict(_player.PROFILE)
# What tells the story of each role among the event metrics, in display order (Scout columns and the player page card).
EVENT_PROFILE = {
    "DEF": ("def_duels90", "def_duel_win", "tackles90", "interceptions90", "aerial_win", "fwd_pass_ratio", "prog_passes90", "pass_acc"),
    "MID": ("prog_passes90", "fwd_pass_ratio", "pass_acc", "passes90", "tackles90", "interceptions90", "recoveries90", "def_duels90"),
    "ATT": ("prog_passes90", "fwd_pass_ratio", "pass_acc", "passes90", "recoveries90", "tackles90", "aerial_win"),
    "GK": ("save_pct", "ga90", "claims90", "sweeper90", "pass_acc", "long_acc"),
}
EVENT_MIXED = ("def_duels90", "def_duel_win", "tackles90", "interceptions90", "prog_passes90", "fwd_pass_ratio", "pass_acc")
