"""Lenses: saved questions that are nothing more than a set of filter rules.

A lens never touches anything but the filters. It does not change the role, the sort, the columns or the season, and every
rule it adds is shown as a chip the user can read, edit or remove. That is the whole point: a lens is *explained* by its own
rules, so nobody has to trust a black box.

A rule compares one metric either as its **value** or as its **percentile** among role peers (players) or league teams (teams):
``Rule("npxg90", ">=", 80, "pct")`` reads "non-penalty xG per 90 is in the top 20% of his role".
All rules of a lens must hold (AND). Where a metric is unknown for a row (no event data, no confirmed age) the rule is false: the
app does not guess.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Rule:
    metric: str
    op: str            # ">=" | "<="
    value: float
    on: str = "value"  # "value" | "pct"

    def public(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Lens:
    key: str
    label: str
    level: str                      # "player" | "team"
    blurb: str                      # one line, shown on the chip
    explain: str                    # the longer reading, shown in the lens panel
    rules: tuple[Rule, ...]
    needs: str = "base"             # base | shots | events: the data a row must have for the lens to mean anything
    roles: tuple[str, ...] = ()     # restrict to these role groups (players); empty = any
    show: tuple[str, ...] = ()      # metrics worth looking at once the lens is on (offered as columns, never forced)
    sort: str | None = None         # the metric worth sorting by (offered, never forced)
    tags: tuple[str, ...] = field(default_factory=tuple)

    def public(self) -> dict:
        d = asdict(self)
        d["rules"] = [r.public() for r in self.rules]
        d["roles"], d["show"], d["tags"] = list(self.roles), list(self.show), list(self.tags)
        return d


MIN450 = Rule("minutes", ">=", 450)

PLAYER_LENSES: tuple[Lens, ...] = (
    Lens("goal_threats", "Goal threats", "player", "Top 20% of their role for non-penalty xG per 90",
         "Players whose shots are worth more than almost everyone else's in their role: the chances they take, not the goals they happen to score. "
         "Judged on non-penalty xG per 90 against role peers, and only with 450+ minutes so a lucky cameo cannot qualify.",
         (Rule("npxg90", ">=", 80, "pct"), MIN450), show=("npxg90", "shots90", "xgps", "goals90", "g_xg"), sort="npxg90"),
    Lens("creators", "Chance creators", "player", "Top 20% for xA per 90 and top 40% for key passes",
         "Players who set up the best chances: assist quality (xA) in the top 20% of their role, with plenty of key passes too, so it is not one lucky assist.",
         (Rule("xa90", ">=", 80, "pct"), Rule("kp90", ">=", 60, "pct"), MIN450), show=("xa90", "kp90", "assists", "xa", "bigcreated90"), sort="xa90"),
    Lens("progressors", "Ball progressors", "player", "Top 20% for progressive passes + carries per 90",
         "Players who move the team up the pitch, by passing or by running with the ball: progressive passes plus progressive carries per 90 in the top 20% of their role. Needs event data.",
         (Rule("progact90", ">=", 80, "pct"),), needs="events", show=("progact90", "prog_passes90", "carryprog90", "fwdm90", "passf3_90"), sort="progact90"),
    Lens("ball_winners", "Ball winners", "player", "Top 20% for tackles + interceptions per 90",
         "Players who win the ball back most often: tackles plus interceptions per 90 in the top 20% of their role. Needs event data.",
         (Rule("tklint90", ">=", 80, "pct"),), needs="events", show=("tklint90", "tackles90", "interceptions90", "recoveries90", "tackle_success"), sort="tklint90"),
    Lens("duel_winners", "Duel winners", "player", "Busy in duels (top 40%) and winning at least 75th percentile of them",
         "Players asked to defend one-on-one often (defensive duels per 90 in the top 40%) who also win them (win rate in the top 25%). Needs event data.",
         (Rule("def_duels90", ">=", 60, "pct"), Rule("def_duel_win", ">=", 75, "pct")), needs="events", show=("def_duels90", "def_duel_win", "tackles90", "aerial_win"), sort="def_duel_win"),
    Lens("aerial", "Aerial threats", "player", "Top 20% for aerial duel win rate, in plenty of duels",
         "Players who win the ball in the air: aerial duel win rate in the top 20% of their role while taking part in a fair number of duels (top 40% for volume). Needs event data.",
         (Rule("aerial_win", ">=", 80, "pct"), Rule("aerials90", ">=", 60, "pct")), needs="events", show=("aerial_win", "aerials90", "aerialwon90", "head90"), sort="aerialwon90"),
    Lens("unlucky", "Unlucky finishers", "player", "Goals well below xG (significance z ≤ −1.2)",
         "Players scoring noticeably fewer goals than their shots deserve: the significance of goals minus xG (z) is −1.2 or lower. Over a season much of this is luck, so goals may follow.",
         (Rule("g_xg_z", "<=", -1.2), Rule("xg", ">=", 2)), show=("g_xg", "g_xg_z", "xg", "goals", "shots"), sort="g_xg_z"),
    Lens("hot", "Running hot", "player", "Goals well above xG (significance z ≥ 1.2)",
         "Players scoring noticeably more than their shots deserve: the significance of goals minus xG (z) is +1.2 or higher. Expect a slowdown unless it is genuine finishing quality.",
         (Rule("g_xg_z", ">=", 1.2), Rule("xg", ">=", 2)), show=("g_xg", "g_xg_z", "xg", "goals", "shots"), sort="g_xg_z"),
    Lens("gems", "Hidden gems", "player", "Role score 70+ but not a regular starter",
         "Strong numbers for their role (role score 70 or more) from players who have played under 60% of their team's minutes: good output in limited time, who might do more with more of it.",
         (Rule("output", ">=", 70), Rule("minutes_share", "<=", 0.6), MIN450), show=("output", "minutes_share", "contrib90", "minutes"), sort="output"),
    Lens("young", "Young and good", "player", "Aged 23 or under with a role score of 60+",
         "Players 23 or younger (by an exact, confirmed date of birth) whose role score is already 60 or more. Players with no confirmed age are left out, not guessed.",
         (Rule("age", "<=", 23), Rule("output", ">=", 60), MIN450), show=("age", "output", "contrib90", "minutes"), sort="output"),
    Lens("setpiece", "Set-piece threats", "player", "Top 15% for xG from set pieces per 90",
         "Players who score or create from dead balls: xG from corners, free kicks and other set pieces per 90 in the top 15% of their role. Needs the season's match pages.",
         (Rule("spxg90", ">=", 85, "pct"), MIN450), needs="shots", show=("spxg90", "head90", "head_share", "fkshots90", "corners90"), sort="spxg90"),
    Lens("dribblers", "Dribblers", "player", "Top 20% for take-ons won and winning at least half",
         "Players who beat opponents with the ball: successful take-ons per 90 in the top 20% of their role, and at least half of their attempts succeed. Needs event data.",
         (Rule("takeonswon90", ">=", 80, "pct"), Rule("takeon_success", ">=", 0.5)), needs="events", show=("takeonswon90", "takeon_success", "takeons90", "disp90", "fouled90"), sort="takeonswon90"),
    Lens("box_presence", "Penalty-box presence", "player", "Top 15% for touches in the opponent's box",
         "Players who spend their time in the penalty area: touches in the opponent's box per 90 in the top 15% of their role. Needs event data.",
         (Rule("touchbox90", ">=", 85, "pct"),), needs="events", show=("touchbox90", "npxg90", "shots90", "big90"), sort="touchbox90"),
    Lens("playmakers", "Deep playmakers", "player", "Heavy passers (top 20%) who also pass forward well (top 25%)",
         "Midfielders and defenders who see a lot of the ball and use it: passes per 90 in the top 20% and progressive passes per 90 in the top 25%. Needs event data.",
         (Rule("passes90", ">=", 80, "pct"), Rule("prog_passes90", ">=", 75, "pct")), needs="events", roles=("MID", "DEF"), show=("passes90", "pass_acc", "prog_passes90", "passf3_90", "xgbuildup90"), sort="prog_passes90"),
    Lens("carriers", "Ball carriers", "player", "Top 15% for progressive carries per 90",
         "Players who drive forward with the ball at their feet: progressive carries per 90 in the top 15% of their role. Estimated from the order of events; needs event data.",
         (Rule("carryprog90", ">=", 85, "pct"),), needs="events", show=("carryprog90", "carrym90", "carryf3_90", "takeons90"), sort="carryprog90"),
    Lens("pressers", "High regains", "player", "Top 15% for winning the ball in the attacking third",
         "Players who win the ball back high up the pitch: recoveries in the attacking third per 90 in the top 15% of their role. A marker of pressing. Needs event data.",
         (Rule("recatt90", ">=", 85, "pct"),), needs="events", show=("recatt90", "recoveries90", "tackles90", "def_height"), sort="recatt90"),
    Lens("shot_stoppers", "Shot-stoppers", "player", "Goalkeepers in the top 25% for save percentage",
         "Goalkeepers who save a high share of the shots on target they face: save percentage in the top 25% of goalkeepers. Not adjusted for shot quality. Needs event data.",
         (Rule("save_pct", ">=", 75, "pct"),), needs="events", roles=("GK",), show=("save_pct", "saves90", "sotfaced90", "ga90", "cs_pct"), sort="save_pct"),
    Lens("sweeper_keepers", "Sweeper-keepers", "player", "Goalkeepers who come off the line and pass well",
         "Goalkeepers in the top 25% for sweeper actions outside the box who are also in the top 40% for pass accuracy. Needs event data.",
         (Rule("sweeper90", ">=", 75, "pct"), Rule("pass_acc", ">=", 60, "pct")), needs="events", roles=("GK",), show=("sweeper90", "pass_acc", "long_acc", "avg_pass_len", "claims90"), sort="sweeper90"),
    Lens("regulars", "Ever-present", "player", "Played 85%+ of the team's minutes",
         "Players who have been in the side almost every minute: 85% or more of the minutes their club has played (and at least 900 of their own).",
         (Rule("minutes_share", ">=", 0.85), Rule("minutes", ">=", 900)), show=("minutes", "minutes_share", "starts", "mins_per_app")),
)

PCT = "pct"
TEAM_LENSES: tuple[Lens, ...] = (
    Lens("high_press", "High press", "team", "Top 25% for pressing intensity (lowest PPDA)",
         "Teams that hassle the opposition's build-up the most: opponent passes per defensive action (PPDA) in the lowest 25% of the league.",
         (Rule("ppda", ">=", 75, PCT),), show=("ppda", "recatt_pg", "def_height", "tklint_pg"), sort="ppda"),
    Lens("possession_side", "Possession-dominant", "team", "55%+ of the passes, and accurate",
         "Teams that keep the ball: at least 55% of all passes in their matches, with pass accuracy in the top 40%. Needs event data.",
         (Rule("poss", ">=", 0.55), Rule("pass_acc", ">=", 60, PCT)), needs="events", show=("poss", "pass_acc", "passes_pg", "seq_len", "tilt"), sort="poss"),
    Lens("counter", "Counter-attacking", "team", "Little of the ball, plenty of direct attacks",
         "Teams that do not dominate possession (under 48% of passes) but launch plenty of fast attacks (direct attacks per game in the top 25%). Needs event data.",
         (Rule("poss", "<=", 0.48), Rule("direct_pg", ">=", 75, PCT)), needs="events", show=("poss", "direct_pg", "long_pct", "fwd_pct", "xg_pg"), sort="direct_pg"),
    Lens("patient", "Patient build-up", "team", "Long possessions, few long balls",
         "Teams that work the ball patiently: passes per possession sequence in the top 25%, and a share of long balls in the bottom 40%. Needs event data.",
         (Rule("seq_len", ">=", 75, PCT), Rule("long_pct", "<=", 40, PCT)), needs="events", show=("seq_len", "seq10_pg", "long_pct", "pass_acc", "poss"), sort="seq_len"),
    Lens("set_piece", "Set-piece reliant", "team", "30%+ of their non-penalty xG comes from dead balls",
         "Teams whose chances lean on corners, free kicks and other set pieces: set-piece xG is at least 30% of their non-penalty xG. Needs the season's match pages.",
         (Rule("sp_share", ">=", 0.3),), needs="shots", show=("sp_share", "spxg_pg", "head_pg", "corners_pg", "xg_pg"), sort="sp_share"),
    Lens("overperforming", "Overperforming results", "team", "4+ points more than their chances earned",
         "Teams whose points are at least 4 above their expected points: results ahead of performances, which usually close.", (Rule("pts_xpts", ">=", 4),), show=("pts", "xpts", "pts_xpts", "xgd_pg", "g_xg_pg"), sort="pts_xpts"),
    Lens("underperforming", "Underperforming results", "team", "4+ points fewer than their chances earned",
         "Teams whose points are at least 4 below their expected points: performances ahead of results, which usually recover.", (Rule("pts_xpts", "<=", -4),), show=("pts", "xpts", "pts_xpts", "xgd_pg", "g_xg_pg"), sort="pts_xpts"),
    Lens("tight_defence", "Tight defence", "team", "Top 25% for the fewest xG conceded",
         "Teams that allow the least: expected goals against per game in the best 25% of the league.", (Rule("xga_pg", ">=", 75, PCT),), show=("xga_pg", "shots_against_pg", "big_against_pg", "ga_pg", "blocks_pg"), sort="xga_pg"),
    Lens("leaky", "Leaky defence", "team", "Bottom 25% for xG conceded",
         "Teams that allow the most: expected goals against per game in the worst 25% of the league.", (Rule("xga_pg", "<=", 25, PCT),), show=("xga_pg", "shots_against_pg", "big_against_pg", "ga_pg", "xga_ga_pg"), sort="xga_pg"),
    Lens("wide", "Crossing teams", "team", "Top 25% for crosses per game",
         "Teams that play through the wings: crosses attempted per game in the top 25% of the league. Needs event data.", (Rule("crosses_pg", ">=", 75, PCT),), needs="events", show=("crosses_pg", "cross_acc", "xg_pg", "head_pg"), sort="crosses_pg"),
    Lens("high_line", "High defensive line", "team", "Top 25% for how high up the pitch they defend",
         "Teams whose defensive actions happen high up the pitch: defensive action height in the top 25%. Needs event data.", (Rule("def_height", ">=", 75, PCT),), needs="events", show=("def_height", "ppda", "recatt_pg", "offsides_won_pg"), sort="def_height"),
    Lens("best_xgd", "Best chance difference", "team", "Top 15% for xG difference per game",
         "The sides that create far more than they allow: xG difference per game in the top 15% of the league.", (Rule("xgd_pg", ">=", 85, PCT),), show=("xgd_pg", "xg_pg", "xga_pg", "ppg", "xpts_pg"), sort="xgd_pg"),
    Lens("clinical", "Clinical attack", "team", "Scoring well above their xG",
         "Teams scoring more than their chances deserve (goals minus xG per game in the top 25%): either quality finishing or luck that may fade.", (Rule("g_xg_pg", ">=", 75, PCT),), show=("g_xg_pg", "gf_pg", "xg_pg", "conv_pct"), sort="g_xg_pg"),
)


def lens_set(level: str) -> tuple[Lens, ...]:
    return PLAYER_LENSES if level == "player" else TEAM_LENSES
