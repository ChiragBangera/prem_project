"""What the browser is told about the registry: metrics, groups, column presets, lenses, roles and positions.

One payload, built once, cached by the browser. Every table column, filter, tooltip, lens and dictionary entry reads it, so a
metric added to the registry appears everywhere with no page change.
"""

from __future__ import annotations

from app.events import schema as ES

from . import player as P
from . import tags as TG
from . import team as T
from .lenses import PLAYER_LENSES, TEAM_LENSES
from .views import PLAYER_VIEWS, TEAM_VIEWS

CATALOG_VERSION = 4
ROLE_LABELS = {"GK": "Goalkeeper", "DEF": "Defender", "MID": "Midfielder", "ATT": "Attacker"}
ROLE_PLURAL = {"GK": "Goalkeepers", "DEF": "Defenders", "MID": "Midfielders", "ATT": "Attackers"}
ROLE_ORDER = ("ATT", "MID", "DEF", "GK")


def _level(groups, metrics, views, lenses, profile=None) -> dict:
    out = {
        "groups": [g.public() for g in groups],
        "metrics": {m.key: m.public() for m in metrics},
        "order": [m.key for m in metrics],
        "views": [v.public() for v in views],
        "lenses": [l.public() for l in lenses],
    }
    if profile is not None:
        out["profile"] = {name: {role: list(keys) for role, keys in table.items()} for name, table in profile.items()}
    return out


def build_catalog() -> dict:
    player_metrics = (*P.PLAYER_METRICS, *P.SCORE_METRICS)
    label_of = {m.key: m.short for m in player_metrics}.get
    player = _level(P.GROUPS, player_metrics, PLAYER_VIEWS, PLAYER_LENSES, {"role": P.PROFILE, "full": P.PROFILE_FULL})
    player["tags"] = TG.public(lambda k: label_of(k) or k)
    return {
        "version": CATALOG_VERSION,
        "player": player,
        "team": _level(T.GROUPS, T.TEAM_METRICS, TEAM_VIEWS, TEAM_LENSES),
        "roles": {"labels": ROLE_LABELS, "plural": ROLE_PLURAL, "order": list(ROLE_ORDER)},
        "positions": {"labels": ES.POSITION_LABEL, "order": list(ES.POSITION_ORDER), "group": ES.POSITION_GROUP, "codes": ES.POSITION_CODE},
    }
