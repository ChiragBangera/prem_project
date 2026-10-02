"""Profile tags: short role labels (Poacher, Ball-playing defender, Set-piece threat ...) awarded by simple rules on percentiles.

A tag is declared once, as data: which role it applies to, which percentile conditions must all hold, and which metric orders the tags
of one player when he earns several. Because the rules are data, the same declaration drives

* the tags on each Scout row (``archetype_tags`` in :mod:`app.analytics.players` evaluates them),
* the Profile filter in Scout (the browser reads the list from the catalog), and
* the Data dictionary, which prints each rule in words.

Percentiles are within the player's role pool and always read "higher is better" (see the registry), so ``>= 85`` means "in the top 15%".
An unknown percentile (a metric the player has no data for) never satisfies a rule: unknown is not zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ROLE_PLURAL = {"ATT": "attackers", "MID": "midfielders", "DEF": "defenders", "GK": "goalkeepers"}
ROLE_ORDER = ("ATT", "MID", "DEF", "GK")


@dataclass(frozen=True)
class Rule:
    """``metrics`` hold the rule if *any* of them meets ``op level`` (one metric in nearly every case)."""

    metrics: tuple[str, ...]
    op: str            # ">=", "<=" or "<"
    level: float       # a percentile, 0-100

    def holds(self, pct: dict) -> bool:
        for m in self.metrics:
            p = pct.get(m)
            if p is None:
                continue
            if (p >= self.level) if self.op == ">=" else (p <= self.level) if self.op == "<=" else (p < self.level):
                return True
        return False


@dataclass(frozen=True)
class Tag:
    key: str
    label: str
    group: str                         # the role it applies to: ATT, MID, DEF or GK
    blurb: str                         # what it means, in a sentence
    rules: tuple[Rule, ...]            # all must hold
    lead: tuple[str, ...]              # the metric(s) whose percentile ranks this tag among a player's tags
    handicap: float = 0.0              # subtracted from the lead percentile when ordering (so broad tags do not always win)
    evidence: tuple[tuple[str, str], ...] = field(default_factory=tuple)   # (metric key, short name) shown in the "why"

    def matches(self, pct: dict) -> bool:
        return all(r.holds(pct) for r in self.rules)

    def strength(self, pct: dict) -> float:
        return max((pct[m] for m in self.lead if m in pct), default=0.0) - self.handicap

    def why(self, pct: dict) -> str:
        parts = ", ".join(f"top {max(1, round(100 - pct[m]))}% for {name}" for m, name in self.evidence if m in pct)
        return f"{parts} among {ROLE_PLURAL[self.group]}"


def _r(metric: str | tuple[str, ...], op: str, level: float) -> Rule:
    return Rule(metric if isinstance(metric, tuple) else (metric,), op, level)


TAGS: tuple[Tag, ...] = (
    # ---- attackers
    Tag("poacher", "Poacher", "ATT", "Lives in the box: far more threat from his own shots than from creating for others.",
        (_r("npxg90", ">=", 85), _r("xa90", "<", 55)), ("npxg90",), 0, (("npxg90", "npxG/90"),)),
    Tag("complete", "Complete forward", "ATT", "Scores and creates: strong on both his own chances and those he makes for others.",
        (_r("npxg90", ">=", 70), _r("xa90", ">=", 70)), ("npxg90", "xa90"), 0, (("npxg90", "npxG/90"), ("xa90", "xA/90"))),
    Tag("creator", "Chance creator", "ATT", "Sets up chances more than most attackers, with the key passes to back it up.",
        (_r("xa90", ">=", 85), _r("kp90", ">=", 75)), ("xa90",), 0, (("xa90", "xA/90"), ("kp90", "key passes"))),
    Tag("volume", "Volume shooter", "ATT", "Shoots a lot, from lower-quality positions.",
        (_r("shots90", ">=", 85), _r("xgps", "<=", 40)), ("shots90",), 10, (("shots90", "shots/90"),)),
    Tag("selective", "Selective finisher", "ATT", "Shoots rarely but from good positions: high quality per shot.",
        (_r("xgps", ">=", 85), _r("shots90", "<", 60)), ("xgps",), 10, (("xgps", "xG/shot"),)),
    Tag("dropper", "Link-up player", "ATT", "Drops into the build-up: involved in many moves that start deep.",
        (_r("xgbuildup90", ">=", 80),), ("xgbuildup90",), 5, (("xgbuildup90", "buildup"),)),
    Tag("target", "Target man", "ATT", "Wins the ball in the air, often. A focal point for long balls and crosses.",
        (_r("aerial_win", ">=", 85), _r("aerials90", ">=", 70)), ("aerial_win",), 5, (("aerial_win", "aerial win rate"), ("aerials90", "aerial duels"))),
    Tag("dribbler", "Dribbler", "ATT", "Beats defenders on the ball more than almost anyone in his role.",
        (_r("takeonswon90", ">=", 85),), ("takeonswon90",), 3, (("takeonswon90", "take-ons won"),)),
    Tag("presser", "Pressing forward", "ATT", "Wins the ball back high up the pitch.",
        (_r("recatt90", ">=", 88),), ("recatt90",), 5, (("recatt90", "high recoveries"),)),
    # ---- midfielders
    Tag("playmaker", "Playmaker", "MID", "Creates chances from midfield: assist quality and key passes both high.",
        (_r("xa90", ">=", 82), _r("kp90", ">=", 70)), ("xa90",), 0, (("xa90", "xA/90"), ("kp90", "key passes"))),
    Tag("progressor", "Deep progressor", "MID", "Starts and carries moves from deep: high build-up involvement.",
        (_r("xgbuildup90", ">=", 82),), ("xgbuildup90",), 0, (("xgbuildup90", "buildup"),)),
    Tag("boxcrasher", "Goal-scoring midfielder", "MID", "Arrives in the box and shoots: real goal threat for a midfielder.",
        (_r("npxg90", ">=", 82),), ("npxg90",), 0, (("npxg90", "npxG/90"),)),
    Tag("hub", "Attacking hub", "MID", "A large share of his team's shot-ending moves run through him.",
        (_r("xgchain90", ">=", 85),), ("xgchain90",), 5, (("xgchain90", "xGChain"),)),
    Tag("advanced", "Advanced creator", "MID", "Creates and scores high up the pitch rather than building from deep.",
        (_r("contrib90", ">=", 85), _r("xgbuildup90", "<", 50)), ("contrib90",), 5, (("contrib90", "npxG+xA"),)),
    Tag("winner", "Ball winner", "MID", "Wins the ball back: tackles and interceptions among the best in his role.",
        (_r("tklint90", ">=", 85),), ("tklint90",), 2, (("tklint90", "tackles + interceptions"),)),
    Tag("driver", "Ball driver", "MID", "Moves the team up the pitch with progressive passes and carries.",
        (_r("progact90", ">=", 85),), ("progact90",), 3, (("progact90", "progressive actions"),)),
    Tag("metronome", "Metronome", "MID", "Sees a lot of the ball and rarely gives it away.",
        (_r("passes90", ">=", 88), _r("pass_acc", ">=", 75)), ("passes90",), 6, (("passes90", "passes"), ("pass_acc", "pass accuracy"))),
    # ---- defenders
    Tag("builder", "Ball-playing defender", "DEF", "Starts attacks from the back: high build-up involvement for a defender.",
        (_r("xgbuildup90", ">=", 82),), ("xgbuildup90",), 0, (("xgbuildup90", "buildup"),)),
    Tag("wide", "Attacking full-back", "DEF", "Creates chances from defence: assist quality or key passes among the best in his role.",
        (_r(("xa90", "kp90"), ">=", 82),), ("xa90", "kp90"), 0, (("xa90", "xA/90"), ("kp90", "key passes"))),
    Tag("setpiece", "Set-piece threat", "DEF", "Scores or threatens from corners and free kicks: high xG for a defender.",
        (_r("npxg90", ">=", 85),), ("npxg90",), 0, (("npxg90", "npxG/90"),)),
    Tag("stopper", "Ball-winning defender", "DEF", "Wins the ball and the duel: tackles, interceptions and a good duel record.",
        (_r("tklint90", ">=", 85), _r("def_duel_win", ">=", 60)), ("tklint90",), 0, (("tklint90", "tackles + interceptions"), ("def_duel_win", "duel win rate"))),
    Tag("aerial", "Aerial dominator", "DEF", "Wins the aerial duels he contests, and contests plenty.",
        (_r("aerial_win", ">=", 88), _r("aerialwon90", ">=", 70)), ("aerial_win",), 3, (("aerial_win", "aerial win rate"),)),
    Tag("carrier", "Progressive carrier", "DEF", "Runs the ball up the pitch himself, more than almost any defender.",
        (_r("carryprog90", ">=", 88),), ("carryprog90",), 3, (("carryprog90", "progressive carries"),)),
    # ---- goalkeepers
    Tag("stopper_gk", "Shot-stopper", "GK", "Saves a high share of the shots on target he faces.",
        (_r("save_pct", ">=", 85),), ("save_pct",), 0, (("save_pct", "save %"),)),
    Tag("sweeper_gk", "Sweeper-keeper", "GK", "Plays off his line: sweeps up behind the defence.",
        (_r("sweeper90", ">=", 85),), ("sweeper90",), 5, (("sweeper90", "sweeper actions"),)),
    Tag("distributor", "Distributor", "GK", "Accurate with long balls and with his passing overall.",
        (_r("long_acc", ">=", 85), _r("pass_acc", ">=", 70)), ("long_acc",), 5, (("long_acc", "long ball accuracy"), ("pass_acc", "pass accuracy"))),
    Tag("commander", "Commanding", "GK", "Comes for crosses: claims more than almost any keeper.",
        (_r("claims90", ">=", 88),), ("claims90",), 5, (("claims90", "high claims"),)),
)

TAG_BY_KEY = {t.key: t for t in TAGS}
MAX_TAGS = 3


def earned(group: str, pct: dict) -> list[dict]:
    """The tags a player of ``group`` with these percentiles has earned, strongest first (at most three)."""
    scored = [(t.strength(pct), t) for t in TAGS if t.group == group and t.matches(pct)]
    scored.sort(key=lambda s: -s[0])
    return [{"key": t.key, "label": t.label, "why": t.why(pct)} for _s, t in scored[:MAX_TAGS]]


def _names(keys: tuple[str, ...], label_of) -> str:
    names = [label_of(k) for k in keys]
    return names[0] if len(names) == 1 else " or ".join(names)


def explain(tag: Tag, label_of) -> str:
    """The rule in words: "npxG per 90 in the top 15% of attackers, and xA per 90 below the 55th percentile"."""
    plural = ROLE_PLURAL[tag.group]
    bits = []
    for r in tag.rules:
        what = _names(r.metrics, label_of)
        if r.op == ">=":
            bits.append(f"{what} in the top {100 - r.level:g}% of {plural}")
        elif r.op == "<=":
            bits.append(f"{what} no better than the {r.level:g}th percentile of {plural}")
        else:
            bits.append(f"{what} below the {r.level:g}th percentile of {plural}")
    return ", and ".join(bits)


def public(label_of) -> list[dict]:
    """The tag list for the browser: ``label_of`` turns a metric key into its readable name."""
    return [
        {"key": t.key, "label": t.label, "group": t.group, "blurb": t.blurb, "explain": explain(t, label_of),
         "rules": [{"metrics": list(r.metrics), "op": r.op, "level": r.level} for r in t.rules]}
        for t in TAGS
    ]
