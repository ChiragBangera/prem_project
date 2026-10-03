"""The metric registry: what every number in the app is, where it comes from, and how it is computed.

A metric is *declared* here once and then used everywhere: it becomes a table column and a filter, it is ranked
against role peers, it is explained in the tooltips and the data dictionary, and a lens can be built from it. Adding a
metric means adding one declaration to :mod:`app.metrics.player` or :mod:`app.metrics.team`; no page changes.

A declaration says *what* (``num`` over ``den``, times ``scale``) and the registry computes it for everyone at once
over a :class:`Frame` of named arrays. Three shapes cover almost everything:

``rate``    a counter per 90 minutes (or per game, for teams): ``scale * num / den`` with ``den`` = playing time;
``ratio``   one counter over another (a pass completion rate): ``scale * num / den`` with ``den`` = the attempts;
``plain``   a quantity as it is (minutes, age, a total) or any expression of the frame.

Rates and ratios are *shrunk* before ranking: a value from few minutes or attempts is pulled toward the pool average in
proportion to how little stands behind it (empirical Bayes), so a ten-minute cameo cannot top a leaderboard. The number
shown in a table is always the raw value; only the percentile uses the shrunk one.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from collections.abc import Callable, Iterable

import numpy as np

Expr = str | Callable[["Frame"], np.ndarray] | None
ROLES = ("ATT", "MID", "DEF", "GK")
NAN = float("nan")


class Frame:
    """Named float arrays for N entities (players or teams). A missing name reads as all-unknown (NaN), never as zero.

    Unknown and zero are different things: a player with no event data has *no* tackles recorded, not zero tackles,
    and every metric built on them must come out blank instead of as a (wrong) zero.
    """

    def __init__(self, n: int):
        self.n = n
        self.a: dict[str, np.ndarray] = {}

    def set(self, name: str, values: Iterable[float] | np.ndarray) -> None:
        arr = np.asarray(list(values) if not isinstance(values, np.ndarray) else values, dtype=float)
        if arr.shape != (self.n,):
            raise ValueError(f"{name}: expected {self.n} values, got {arr.shape}")
        self.a[name] = arr

    def has(self, name: str) -> bool:
        return name in self.a

    def __getitem__(self, name: str) -> np.ndarray:
        found = self.a.get(name)
        return found if found is not None else np.full(self.n, NAN)

    def eval(self, expr: Expr) -> np.ndarray | None:
        if expr is None:
            return None
        if callable(expr):
            return np.asarray(expr(self), dtype=float)
        return self[expr]


def safe_div(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        out = num / den
    out = np.where((den > 0) & np.isfinite(out), out, NAN)
    return out


# ------------------------------------------------------------------ declarations

#: Metrics that are a difference (above or below an expectation): the browser prints their sign and colours them by it.
SIGNED = frozenset({"g_xg", "npg_npxg", "g_xg_z", "a_xa", "gdon90", "gd", "pts_xpts", "xgd_pg", "npxgd_pg", "g_xg_pg", "xga_ga_pg"})


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    short: str
    level: str                     # "player" | "team"
    group: str                     # a key of the level's groups
    unit: str                      # per90 | pergame | total | count | share | ratio | rating | age | metres | score
    decimals: int
    hib: bool | None               # higher is better; None when it describes style rather than quality
    source: str                    # understat | whoscored | both | espn | derived
    needs: str                     # base | shots | events: which data must exist for it to have a value
    kind: str                      # raw (as the source supplies it) | derived (computed here)
    formula: str                   # the exact recipe, in words and symbols
    inputs: tuple[str, ...]        # the counters / raw fields it is built from
    what: str                      # what it measures
    read: str                      # how to read it, what is good
    caveat: str = ""
    num: Expr = None
    den: Expr = None
    scale: float = 1.0
    k: float = 0.0                 # shrink strength, in units of ``den`` (0: not shrunk)
    min_den: float = 0.0           # below this denominator the value is left blank (a rate from two attempts is not a rate)
    roles: tuple[str, ...] = ROLES
    shape: str = "plain"           # rate | ratio | plain
    tags: tuple[str, ...] = field(default_factory=tuple)

    def public(self) -> dict:
        """What the browser needs: everything except the functions."""
        d = asdict(self)
        for k in ("num", "den"):
            d.pop(k, None)
        d["inputs"] = list(self.inputs)
        d["roles"] = list(self.roles)
        d["tags"] = list(self.tags)
        d["signed"] = self.key in SIGNED
        return d

    def compute(self, f: Frame) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]:
        """``(value, numerator, denominator)`` over the frame. Unknown where either input is unknown or the denominator is not positive."""
        num = f.eval(self.num)
        if num is None:
            return np.full(f.n, NAN), None, None
        den = f.eval(self.den)
        if den is None:
            return num * self.scale if self.scale != 1.0 else num, num, None
        value = safe_div(num, den) * self.scale
        if self.min_den > 0:
            value = np.where(den >= self.min_den, value, NAN)
        return value, num, den


def counter(key, label, short, group, *, unit="total", decimals=0, hib=True, source="understat", needs="base", level="player",
            formula, inputs, what, read="", caveat="", num=None, roles=ROLES, tags=(), kind=None) -> Metric:
    """A total or a plain quantity."""
    raw = source == "understat" and tuple(inputs) == (key,)  # raw = exactly the figure Understat publishes; a count of events we read is derived
    return Metric(key, label, short, level, group, unit, decimals, hib, source, needs, kind or ("raw" if raw else "derived"),
                  formula, tuple(inputs), what, read, caveat, num=num if num is not None else key, roles=roles, shape="plain", tags=tuple(tags))


def rate(key, label, short, group, num, *, per="minutes", scale=90.0, unit="per90", decimals=2, hib=True, source="understat", needs="base", level="player",
         formula, inputs, what, read="", caveat="", k=720.0, roles=ROLES, min_den=0.0, tags=()) -> Metric:
    """``scale * num / den``: a count per 90 minutes (``per`` names the minutes array) or per game."""
    return Metric(key, label, short, level, group, unit, decimals, hib, source, needs, "derived", formula, tuple(inputs), what, read, caveat,
                  num=num, den=per, scale=scale, k=k, min_den=min_den, roles=roles, shape="rate", tags=tuple(tags))


def ratio(key, label, short, group, num, den, *, scale=1.0, unit="share", decimals=0, hib=True, source="whoscored", needs="events", level="player",
          formula, inputs, what, read="", caveat="", k=60.0, roles=ROLES, min_den=1.0, tags=()) -> Metric:
    """``scale * num / den``: one count over another, e.g. completed over attempted passes."""
    return Metric(key, label, short, level, group, unit, decimals, hib, source, needs, "derived", formula, tuple(inputs), what, read, caveat,
                  num=num, den=den, scale=scale, k=k, min_den=min_den, roles=roles, shape="ratio", tags=tuple(tags))


# ------------------------------------------------------------------ groups (the headings of the column picker and the dictionary)


@dataclass(frozen=True)
class Group:
    key: str
    label: str
    blurb: str
    level: str = "player"

    def public(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------ ranking


def pool_values(values: np.ndarray, mask: np.ndarray) -> np.ndarray:
    return np.sort(values[mask & np.isfinite(values)])


def percentile_of(sorted_pool: np.ndarray, values: np.ndarray, hib: bool | None) -> np.ndarray:
    """Mid-rank percentile (0-100) of each value within the pool; ties count half. Reads "higher is better" unless ``hib`` is False."""
    n = len(sorted_pool)
    out = np.full(values.shape, NAN)
    if n == 0:
        return out
    ok = np.isfinite(values)
    below = np.searchsorted(sorted_pool, values[ok], side="left")
    equal = np.searchsorted(sorted_pool, values[ok], side="right") - below
    pct = 100.0 * (below + 0.5 * equal) / n
    out[ok] = 100.0 - pct if hib is False else pct
    return out


def shrunk(metric: Metric, value: np.ndarray, num: np.ndarray | None, den: np.ndarray | None, pool: np.ndarray) -> np.ndarray:
    """The value ranking is done on: pulled toward the pool average in proportion to how little stands behind it."""
    if metric.k <= 0 or num is None or den is None or not pool.any():
        return value
    ok = pool & np.isfinite(num) & np.isfinite(den) & (den > 0)
    total = den[ok].sum()
    if total <= 0:
        return value
    prior = metric.scale * num[ok].sum() / total
    with np.errstate(invalid="ignore"):
        out = (value * den + prior * metric.k) / (den + metric.k)
    return np.where(np.isfinite(value), out, NAN)
