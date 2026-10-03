"""Role groups (GK / DEF / MID / ATT) for scouting pools.

Understat's league table lists a player as e.g. "F M S": the families he has
appeared in, alphabetically, plus "S" for substitute appearances. That is *not*
his main role, and picking the first letter (as the old code did) put wingers
in defence. Instead:

1. one family listed            -> that group ("listed");
2. several families listed      -> the one whose typical per-90 profile his own
                                   profile is closest to ("inferred");
3. Understat's ``favorite_position`` known (from his player page) -> that ("favorite").
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from collections.abc import Sequence

FAMILY_GROUP = {"GK": "GK", "D": "DEF", "M": "MID", "F": "ATT"}
GROUP_FAMILY = {v: k for k, v in FAMILY_GROUP.items()}
DEFAULT_PRIORITY = ("F", "M", "D")  # tie-break when no profile information exists


def families_of(raw: str | None) -> tuple[tuple[str, ...], bool]:
    """('D','M') and has_sub for "D M S"."""
    found: list[str] = []
    has_sub = False
    for token in (raw or "").upper().split():
        if token == "S":
            has_sub = True
        elif token.startswith("GK") or token == "G":
            found.append("GK")
        elif token[0] in "DMF":
            found.append(token[0])
    return tuple(dict.fromkeys(found)), has_sub


def group_from_favorite(code: str | None) -> str | None:
    """Understat favourite-position code -> group. ``AML/AMR`` are wide attackers."""
    if not code:
        return None
    head = code.strip().upper()
    if head in ("NON", "SUB", ""):
        return None
    if head.startswith("GK"):
        return "GK"
    if head.startswith(("FW", "ST", "AML", "AMR")):
        return "ATT"
    if head.startswith(("DMC", "DML", "DMR", "MC", "ML", "MR", "AMC", "AM")):
        return "MID"
    if head.startswith(("DC", "DL", "DR", "SW", "WB", "D")):
        return "DEF"
    return None


@dataclass
class RoleModel:
    """Nearest-centroid classifier over standardised per-90 profiles."""

    centroids: dict[str, list[float]]  # family letter -> centroid
    mean: list[float]
    scale: list[float]

    @classmethod
    def fit(cls, samples: Sequence[tuple[str, Sequence[float]]], min_per_family: int = 8) -> RoleModel | None:
        """``samples``: (family, feature vector) for players with exactly one listed family."""
        by_family: dict[str, list[Sequence[float]]] = {}
        for family, vector in samples:
            by_family.setdefault(family, []).append(vector)
        usable = {f: v for f, v in by_family.items() if f in ("D", "M", "F") and len(v) >= min_per_family}
        if len(usable) < 2:
            return None
        width = len(next(iter(usable.values()))[0])
        everyone = [vec for vectors in usable.values() for vec in vectors]
        mean = [sum(v[i] for v in everyone) / len(everyone) for i in range(width)]
        scale = [
            (math.sqrt(sum((v[i] - mean[i]) ** 2 for v in everyone) / len(everyone)) or 1.0) for i in range(width)
        ]
        centroids = {
            family: [sum((v[i] - mean[i]) / scale[i] for v in vectors) / len(vectors) for i in range(width)]
            for family, vectors in usable.items()
        }
        return cls(centroids, mean, scale)

    def classify(self, families: Sequence[str], vector: Sequence[float]) -> tuple[str, float]:
        """Pick among ``families``; confidence is the relative margin over the runner-up (0..1)."""
        candidates = [f for f in families if f in self.centroids]
        if not candidates:
            return _priority(families), 0.0
        z = [(vector[i] - self.mean[i]) / self.scale[i] for i in range(len(vector))]
        scored = sorted(
            (math.sqrt(sum((z[i] - c[i]) ** 2 for i in range(len(z)))), f)
            for f, c in ((f, self.centroids[f]) for f in candidates)
        )
        if len(scored) == 1:
            return scored[0][1], 0.5
        (d1, best), (d2, _second) = scored[0], scored[1]
        return best, (d2 - d1) / (d1 + d2) if (d1 + d2) > 0 else 0.0


def _priority(families: Sequence[str]) -> str:
    for family in DEFAULT_PRIORITY:
        if family in families:
            return family
    return families[0] if families else "M"
