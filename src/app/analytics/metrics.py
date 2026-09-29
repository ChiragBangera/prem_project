"""The metric catalogue: one source of truth for what each number means.

The API ships this to the browser so every column header, tooltip and glossary
entry comes from the same words. ``higher_is_better`` drives colour direction
and percentile orientation (e.g. yellow cards per 90: lower is better).
"""

from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    short: str
    category: str
    unit: str  # per90 | total | ratio | share | count | age
    decimals: int
    higher_is_better: bool
    what: str
    read: str

    def to_dict(self) -> dict:
        return asdict(self)


def _m(key, label, short, category, unit, decimals, hib, what, read) -> Metric:
    return Metric(key, label, short, category, unit, decimals, hib, what, read)


PLAYER_METRICS: tuple[Metric, ...] = (
    # --- shooting
    _m("npxg90", "Non-penalty xG per 90", "npxG/90", "Shooting", "per90", 2, True,
       "The quality-weighted chances a player takes per 90 minutes, penalties excluded.",
       "The cleanest measure of goal threat. Around 0.4 per 90 is elite for a forward."),
    _m("shots90", "Shots per 90", "Shots/90", "Shooting", "per90", 1, True,
       "How often the player shoots.",
       "Volume alone is not quality: pair it with xG per shot."),
    _m("xgps", "xG per shot", "xG/shot", "Shooting", "ratio", 3, True,
       "Average quality of each shot (xG divided by shots).",
       "High means good positions (or penalties); low means speculative long shots."),
    _m("goals90", "Goals per 90", "Goals/90", "Shooting", "per90", 2, True,
       "Goals scored per 90 minutes, penalties included.", "What happened, not what should have."),
    # --- creation
    _m("xa90", "xA per 90", "xA/90", "Creation", "per90", 2, True,
       "The xG of the shots a player's passes created, per 90 minutes.",
       "Assist quality without depending on the finisher. 0.25+ per 90 is elite."),
    _m("kp90", "Key passes per 90", "KP/90", "Creation", "per90", 2, True,
       "Passes that directly led to a shot, per 90.", "Creation volume; check xA to see how good the chances were."),
    _m("contrib90", "npxG + xA per 90", "npxG+xA", "Creation", "per90", 2, True,
       "Expected non-penalty goal involvement: shots taken plus chances created.",
       "One number for attacking output. 0.6+ per 90 is elite."),
    # --- involvement
    _m("xgchain90", "xGChain per 90", "xGChain/90", "Involvement", "per90", 2, True,
       "The total xG of every possession the player touched on the way to a shot, per 90.",
       "How much of the team's attacking flow runs through them."),
    _m("xgbuildup90", "xGBuildup per 90", "Buildup/90", "Involvement", "per90", 2, True,
       "xGChain excluding the player's own shots and key passes: the earlier build-up.",
       "Deep progression. High buildup with modest chain means they start attacks rather than finish them."),
    _m("buildup_share", "Build-up share of chain", "Buildup %", "Involvement", "share", 0, True,
       "The part of a player's xGChain that comes from build-up rather than shooting or the final pass.",
       "Above ~60% is a deep, early-involvement player."),
    # --- results (what actually happened)
    _m("goals", "Goals", "G", "Results", "count", 0, True, "Goals scored.", "Compare with xG."),
    _m("npg", "Non-penalty goals", "npG", "Results", "count", 0, True, "Goals excluding penalties.", ""),
    _m("assists", "Assists", "A", "Results", "count", 0, True, "Assists.", "Compare with xA."),
    _m("xg", "Expected goals", "xG", "Results", "total", 1, True, "Sum of the xG of all shots taken.", ""),
    _m("npxg", "Non-penalty xG", "npxG", "Results", "total", 1, True, "xG excluding penalties.", ""),
    _m("xa", "Expected assists", "xA", "Results", "total", 1, True, "Sum of xG from shots created by the player's passes.", ""),
    _m("g_xg", "Goals minus xG", "G-xG", "Finishing", "total", 1, True,
       "Goals scored above (positive) or below (negative) what the chances were worth.",
       "Mostly luck over a season: see the significance (z) before believing it is skill."),
    _m("a_xa", "Assists minus xA", "A-xA", "Finishing", "total", 1, True,
       "Assists above or below what the created chances were worth.", "Depends on team-mates finishing."),
    # --- discipline & availability
    _m("yellow90", "Yellow cards per 90", "YC/90", "Discipline", "per90", 2, False, "Bookings per 90.", "Lower is better."),
    _m("minutes", "Minutes", "Min", "Availability", "count", 0, True, "League minutes played.", "The sample size behind every rate."),
    _m("games", "Appearances", "Apps", "Availability", "count", 0, True, "League appearances, including cameos.", ""),
    _m("minutes_share", "Share of team minutes", "Min %", "Availability", "share", 0, True,
       "Minutes played as a share of everything the team has played.",
       "Above 80% is a fixture in the side; under 40% is a rotation or bench player."),
    _m("mins_per_app", "Minutes per appearance", "Min/App", "Availability", "count", 0, True,
       "Average minutes when he plays.", "Under 45 means he is mostly a substitute."),
    _m("age", "Age", "Age", "Profile", "age", 0, False, "Age from Wikidata's date of birth.", "Blank when Wikidata has no unambiguous match."),
)

METRIC_BY_KEY = {m.key: m for m in PLAYER_METRICS}

# Which metrics tell the story for each role group, in display order.
# Understat only measures attacking output, so defenders are judged on
# build-up involvement, set-piece threat and reliability - and we say so.
PROFILE_METRICS: dict[str, tuple[str, ...]] = {
    "ATT": ("npxg90", "shots90", "xgps", "xa90", "kp90", "xgchain90", "xgbuildup90"),
    "MID": ("xa90", "kp90", "xgchain90", "xgbuildup90", "npxg90", "shots90", "contrib90"),
    "DEF": ("xgbuildup90", "xgchain90", "xa90", "kp90", "npxg90", "yellow90"),
}

GROUP_LABELS = {"GK": "Goalkeeper", "DEF": "Defender", "MID": "Midfielder", "ATT": "Attacker"}
GROUP_ORDER = ("ATT", "MID", "DEF", "GK")

# Rate metrics that are ranked on a shrunk (empirical-Bayes) per-90 value so a
# 90-minute cameo cannot top a leaderboard.
SHRUNK = {"npxg90", "shots90", "xa90", "kp90", "xgchain90", "xgbuildup90", "contrib90", "goals90", "yellow90"}
SHRINK_MINUTES = 720.0  # prior strength (~8 games of league-average play): xG rates need that long to settle

TEAM_METRICS = (
    _m("xg_pg", "xG per game", "xG/g", "Attack", "per90", 2, True, "Expected goals created per match.", "The best single measure of attacking quality."),
    _m("xga_pg", "xGA per game", "xGA/g", "Defence", "per90", 2, False, "Expected goals conceded per match.", "Lower is better."),
    _m("xgd_pg", "xG difference per game", "xGD/g", "Overall", "per90", 2, True, "xG minus xGA per match.", "Predicts future results better than the table."),
    _m("ppda", "PPDA", "PPDA", "Style", "ratio", 1, False, "Opponent passes allowed per defensive action in their build-up: how hard a team presses.", "Lower = more intense press."),
    _m("oppda", "Opponent PPDA", "OPPDA", "Style", "ratio", 1, True, "The same, for the pressing teams face from opponents.", "Higher = opponents let them play."),
    _m("deep_pg", "Deep completions per game", "DC/g", "Attack", "per90", 1, True, "Passes completed within ~20 yards of the opponent goal.", "Territory and penetration."),
    _m("deep_allowed_pg", "Deep completions allowed", "ODC/g", "Defence", "per90", 1, False, "Deep completions the opposition manage.", "Lower is better."),
)
