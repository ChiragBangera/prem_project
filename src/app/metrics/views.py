"""Column presets: ready-made sets of columns for the table, so nobody has to build a view from scratch.

A preset is only a list of metric keys, in display order. The table also lets anyone pick their own columns from every
metric in the registry (the "Custom" view); presets are the quick start, never a limit.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class View:
    key: str
    label: str
    blurb: str
    level: str
    metrics: tuple[str, ...]

    def public(self) -> dict:
        d = asdict(self)
        d["metrics"] = list(self.metrics)
        return d


PLAYER_VIEWS: tuple[View, ...] = (
    View("overview", "Overview", "The headline numbers: output, chances, passing and defending.", "player",
         ("goals", "assists", "npxg90", "xa90", "contrib90", "xgchain90", "pass_acc", "tklint90", "g_xg")),
    View("attacking", "Attacking", "Shooting volume, quality and finishing.", "player",
         ("goals", "xg", "npxg90", "shots90", "xgps", "sot_pct", "goal_conv", "g_xg", "big90", "box_share", "touchbox90")),
    View("creation", "Creating", "Chances made for others.", "player",
         ("assists", "xa", "xa90", "kp90", "contrib90", "bigcreated90", "through90", "crosses90", "cross_acc", "xgchain90")),
    View("passing", "Passing", "Volume, accuracy and how forward.", "player",
         ("passes90", "pass_acc", "fwd_pass_ratio", "prog_passes90", "fwdm90", "passf3_90", "passbox90", "long_ratio", "long_acc", "avg_pass_len")),
    View("possession", "Carrying & possession", "Running with the ball, dribbling, and where he is on it.", "player",
         ("touches90", "touchatt90", "touchbox90", "carries90", "carryprog90", "carrym90", "progact90", "takeons90", "takeon_success", "disp90")),
    View("defending", "Defending", "Winning the ball back and stopping attacks.", "player",
         ("tackles90", "tackle_success", "interceptions90", "tklint90", "clearances90", "blocks90", "recoveries90", "recatt90", "def_height", "challenges90")),
    View("duels", "Duels", "One-against-one contests and who wins them.", "player",
         ("def_duels90", "def_duel_win", "tackles90", "tackle_success", "aerials90", "aerial_win", "aerialwon90", "takeons90", "takeon_success")),
    View("goalkeeping", "Goalkeeping", "Stopping shots and commanding the box.", "player",
         ("saves90", "save_pct", "sotfaced90", "ga90", "cs_pct", "claims90", "punches90", "sweeper90", "pickups90", "pass_acc", "long_acc")),
    View("setpieces", "Set pieces", "Dead-ball threat and delivery.", "player",
         ("spxg90", "head90", "head_share", "fkshots90", "fktaken90", "corners90", "throwins90", "pens_taken", "aerial_win")),
    View("discipline", "Discipline", "Fouls, cards and offsides.", "player",
         ("yellow", "yellow90", "red", "fouls90", "fouled90", "offsides90", "pen_conceded", "pen_won", "errors90")),
)

TEAM_VIEWS: tuple[View, ...] = (
    View("overview", "Overview", "Results, chances, possession and pressing in one line.", "team",
         ("ppg", "gf_pg", "ga_pg", "xg_pg", "xga_pg", "xgd_pg", "pts_xpts", "poss", "ppda")),
    View("results", "Results", "What happened.", "team",
         ("played", "wins", "draws", "losses", "pts", "ppg", "gf", "ga", "gd", "xpts", "pts_xpts")),
    View("chances", "Chances", "Quality of chances made and allowed.", "team",
         ("xg_pg", "xga_pg", "xgd_pg", "npxg_pg", "npxga_pg", "g_xg_pg", "xga_ga_pg", "deep_pg", "deepa_pg")),
    View("attack", "Shooting", "How the team shoots, and how it is shot at.", "team",
         ("shots_pg", "sot_pg", "xg_shot", "sot_pct", "conv_pct", "big_pg", "box_pct", "shot_dist", "shots_against_pg", "xg_shot_against", "big_against_pg")),
    View("possession", "Possession & passing", "How the team keeps and moves the ball.", "team",
         ("poss", "passes_pg", "pass_acc", "fwd_pct", "long_pct", "prog_pg", "passf3_pg", "passbox_pg", "tilt", "pass_x", "seq_len")),
    View("style", "Style", "How directly, how high and how patiently the team plays.", "team",
         ("poss", "pass_x", "tilt", "seq_len", "seq10_pg", "direct_pg", "long_pct", "crosses_pg", "def_height", "ppda")),
    View("pressing", "Pressing & defending", "How hard, how high and how well the team defends.", "team",
         ("ppda", "oppda", "def_height", "recatt_pg", "tklint_pg", "clear_pg", "blocks_pg", "beaten_pg", "opp_passes_pg", "errors_pg")),
    View("setpieces", "Set pieces", "Dead-ball threat and defence.", "team",
         ("corners_pg", "spxg_pg", "spxga_pg", "sp_share", "head_pg", "throwins_pg", "pens_pg", "pens_against_pg", "corners_against_pg")),
    View("goalkeeping", "Goalkeeping", "Shot-stopping against the chances faced.", "team",
         ("saves_pg", "save_pct", "sot_against_pg", "xga_ga_pg", "cs_pct", "claims_pg", "ga_pg", "xga_pg")),
    View("discipline", "Discipline", "Fouls, cards and offsides.", "team",
         ("yellow_pg", "red", "fouls_pg", "fouled_pg", "offsides_pg", "offsides_won_pg")),
)


def view_set(level: str) -> tuple[View, ...]:
    return PLAYER_VIEWS if level == "player" else TEAM_VIEWS
