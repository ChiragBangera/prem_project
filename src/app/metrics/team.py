"""Every team metric, declared once. See :mod:`app.metrics.registry` for how a declaration is read.

Frame arrays a team metric may use (one entry per team in a league season; the team dataset builder fills them):

* Understat's team history:  ``matches pts wins draws losses gf ga xg xga npxg npxga xpts deep deep_allowed ppda_att ppda_def oppda_att oppda_def``
* its match pages, for / against (``s_*`` and ``sa_*``): shot-level sums
* event data, for / against (``w_*`` and ``wa_*``): every counter of :mod:`app.events.counters`; ``w_matches`` is how many
  matches have event data (event metrics are per *those* matches)
* the squad:  ``squad_age players_used``

"Against" metrics are the opponents' totals against this team, so ``wa_passes`` is passes the opposition made against it.
"""

from __future__ import annotations

from .registry import Group, Metric, counter, rate, ratio

GROUPS: tuple[Group, ...] = (
    Group("results", "Results", "What happened: points, goals and where that puts the team.", level="team"),
    Group("chances", "Chance creation", "The quality and quantity of the chances a team makes and allows (expected goals).", level="team"),
    Group("shooting", "Shooting", "How the team shoots: volume, accuracy and where from.", level="team"),
    Group("possession", "Possession and passing", "How the team keeps and moves the ball.", level="team"),
    Group("carrying", "Carrying and dribbling", "Moving the ball by running with it and beating opponents.", level="team"),
    Group("pressing", "Pressing and defending", "How hard, how high and how well the team defends.", level="team"),
    Group("setpieces", "Set pieces", "Corners, free kicks, throw-ins and penalties.", level="team"),
    Group("goalkeeping", "Goalkeeping", "Shot-stopping and the goals conceded against the chances faced.", level="team"),
    Group("discipline", "Discipline", "Fouls, cards and offsides.", level="team"),
    Group("squad", "Squad", "Who plays: age and how many players the manager has used.", level="team"),
)

U = {"source": "understat", "needs": "base", "level": "team"}
S = {"source": "understat", "needs": "shots", "level": "team"}
W = {"source": "whoscored", "needs": "events", "level": "team"}
BOTH = {"source": "both", "needs": "events", "level": "team"}


def pg(key, label, short, group, num, *, decimals=2, hib=True, per="matches", formula, inputs, what, read="", caveat="", src=U, unit="pergame", **kw):
    """Per-game rate: ``num ÷ matches``."""
    return rate(key, label, short, group, num, per=per, scale=1.0, unit=unit, decimals=decimals, hib=hib, formula=formula, inputs=inputs, what=what, read=read, caveat=caveat, k=0.0, **src, **kw)


TEAM_METRICS: tuple[Metric, ...] = (
    # ------------------------------------------------------------------ results
    counter("played", "Matches played", "P", "results", formula="Number of league matches played", inputs=("matches",), **U, what="League matches played.", num="matches"),
    counter("pts", "Points", "Pts", "results", formula="3 × wins + draws", inputs=("pts",), **U, what="League points."),
    pg("ppg", "Points per game", "PPG", "results", "pts", formula="points ÷ matches", inputs=("pts", "matches"), what="League points per match.", read="Above 2.0 is title-chasing, below 1.0 is relegation form."),
    counter("wins", "Wins", "W", "results", formula="Matches won", inputs=("wins",), **U, what="Matches won."),
    counter("draws", "Draws", "D", "results", formula="Matches drawn", inputs=("draws",), **U, what="Matches drawn."),
    counter("losses", "Losses", "L", "results", hib=False, formula="Matches lost", inputs=("losses",), **U, what="Matches lost."),
    ratio("win_pct", "Win rate", "Win %", "results", "wins", "matches", decimals=0, formula="wins ÷ matches", inputs=("wins", "matches"), **U, k=0.0, min_den=1.0, what="The share of matches won."),
    counter("gf", "Goals for", "GF", "results", formula="Goals scored", inputs=("gf",), **U, what="Goals scored."),
    counter("ga", "Goals against", "GA", "results", hib=False, formula="Goals conceded", inputs=("ga",), **U, what="Goals conceded."),
    counter("gd", "Goal difference", "GD", "results", formula="goals for − goals against", inputs=("gf", "ga"), **U, what="Goals scored minus conceded.", num=lambda f: f["gf"] - f["ga"]),
    pg("gf_pg", "Goals per game", "GF/g", "results", "gf", formula="goals for ÷ matches", inputs=("gf", "matches"), what="Goals scored per match."),
    pg("ga_pg", "Goals against per game", "GA/g", "results", "ga", hib=False, formula="goals against ÷ matches", inputs=("ga", "matches"), what="Goals conceded per match."),
    counter("xpts", "Expected points", "xPts", "results", unit="total", decimals=1, formula="Σ over matches of 3 × P(win) + P(draw), from replaying every shot", inputs=("xpts",), **U,
            what="The points the chances created and conceded were worth, match by match.", read="A fairer table than the real one: large gaps with real points usually close."),
    pg("xpts_pg", "Expected points per game", "xPts/g", "results", "xpts", formula="xPts ÷ matches", inputs=("xpts", "matches"), what="Expected points per match."),
    counter("pts_xpts", "Points minus xPts", "Pts-xPts", "results", unit="total", decimals=1, hib=None, formula="points − expected points", inputs=("pts", "xpts"), **U,
            what="Points above (positive) or below (negative) what the chances deserved.", read="Large positive gaps usually shrink (results outran performances); large negative gaps usually recover.", num=lambda f: f["pts"] - f["xpts"]),

    # ------------------------------------------------------------------ chance creation (Understat)
    pg("xg_pg", "xG per game", "xG/g", "chances", "xg", formula="xG ÷ matches", inputs=("xg", "matches"), what="Expected goals created per match.", read="The best single measure of attacking quality."),
    pg("xga_pg", "xGA per game", "xGA/g", "chances", "xga", hib=False, formula="xGA ÷ matches", inputs=("xga", "matches"), what="Expected goals conceded per match.", read="Lower is better."),
    pg("xgd_pg", "xG difference per game", "xGD/g", "chances", lambda f: f["xg"] - f["xga"], formula="(xG − xGA) ÷ matches", inputs=("xg", "xga", "matches"), what="xG minus xGA per match.", read="Predicts future results better than the table does."),
    pg("npxg_pg", "npxG per game", "npxG/g", "chances", "npxg", formula="npxG ÷ matches", inputs=("npxg", "matches"), what="Non-penalty xG created per match: open-play and set-piece threat without penalties."),
    pg("npxga_pg", "npxGA per game", "npxGA/g", "chances", "npxga", hib=False, formula="npxGA ÷ matches", inputs=("npxga", "matches"), what="Non-penalty xG conceded per match."),
    pg("npxgd_pg", "npxG difference per game", "npxGD/g", "chances", lambda f: f["npxg"] - f["npxga"], formula="(npxG − npxGA) ÷ matches", inputs=("npxg", "npxga", "matches"), what="Net non-penalty chance quality per match."),
    pg("g_xg_pg", "Goals minus xG per game", "G-xG/g", "chances", lambda f: f["gf"] - f["xg"], hib=None, formula="(goals − xG) ÷ matches", inputs=("gf", "xg", "matches"),
       what="Attack luck: goals scored above or below the chances created.", read="Large positive values usually fade."),
    pg("xga_ga_pg", "xGA minus goals against per game", "xGA-GA/g", "chances", lambda f: f["xga"] - f["ga"], hib=None, formula="(xGA − goals against) ÷ matches", inputs=("xga", "ga", "matches"),
       what="Defence luck: fewer goals conceded than the chances allowed (positive is fortunate).", read="Large positive values usually fade."),
    pg("deep_pg", "Deep completions per game", "Deep/g", "chances", "deep", decimals=1, formula="deep completions ÷ matches", inputs=("deep", "matches"),
       what="Passes completed within about 20 yards of the opponent's goal, per match.", read="Territory and penetration."),
    pg("deepa_pg", "Deep completions allowed per game", "DeepA/g", "chances", "deep_allowed", decimals=1, hib=False, formula="deep completions allowed ÷ matches", inputs=("deep_allowed", "matches"),
       what="Deep completions the opposition manage against the team, per match.", read="Lower is better."),

    # ------------------------------------------------------------------ shooting (Understat match pages)
    pg("shots_pg", "Shots per game", "Shots/g", "shooting", "s_n", decimals=1, hib=None, formula="shots ÷ matches", inputs=("s_n", "matches"), src=S, what="Shots taken per match.", read="Volume, not quality: see xG per shot."),
    pg("sot_pg", "Shots on target per game", "SoT/g", "shooting", "s_sot", decimals=1, formula="shots on target ÷ matches", inputs=("s_sot", "matches"), src=S, what="Shots that were goals or saved, per match."),
    ratio("xg_shot", "xG per shot", "xG/shot", "shooting", "xg", "s_n", unit="ratio", decimals=3, formula="xG ÷ shots", inputs=("xg", "s_n"), **S, k=0.0, what="The average quality of the team's shots.", read="High means patient, high-quality chances; low means speculative shooting."),
    ratio("sot_pct", "Shots on target", "SoT %", "shooting", "s_sot", "s_n", decimals=0, formula="shots on target ÷ shots", inputs=("s_sot", "s_n"), **S, k=0.0, what="The share of shots that were goals or saves."),
    ratio("conv_pct", "Shot conversion", "Conv %", "shooting", "s_goals", "s_n", decimals=0, formula="goals ÷ shots", inputs=("s_goals", "s_n"), **S, k=0.0, what="The share of shots that were goals."),
    pg("big_pg", "Big chances per game", "Big/g", "shooting", "s_big", decimals=2, formula="shots worth 0.30+ xG ÷ matches", inputs=("s_big", "matches"), src=S, what="Shots worth at least 0.30 xG, per match."),
    ratio("box_pct", "Shots from inside the box", "Box %", "shooting", "s_box", "s_n", decimals=0, hib=None, formula="shots in the penalty area ÷ shots", inputs=("s_box", "s_n"), **S, k=0.0, what="The share of shots taken inside the penalty area."),
    ratio("shot_dist", "Average shot distance", "Dist (m)", "shooting", "s_dist", "s_n", unit="metres", decimals=1, hib=None, formula="mean distance from goal of the team's shots", inputs=("s_dist", "s_n"), **S, k=0.0, what="How far from goal the team shoots, on average."),
    pg("shots_against_pg", "Shots against per game", "ShotsA/g", "shooting", "sa_n", decimals=1, hib=False, formula="shots faced ÷ matches", inputs=("sa_n", "matches"), src=S, what="Shots the opposition take against the team, per match."),
    pg("sot_against_pg", "Shots on target against per game", "SoTA/g", "shooting", "sa_sot", decimals=1, hib=False, formula="shots on target faced ÷ matches", inputs=("sa_sot", "matches"), src=S, what="Shots on target faced, per match."),
    ratio("xg_shot_against", "xG per shot against", "xG/shotA", "shooting", "sa_xg", "sa_n", unit="ratio", decimals=3, hib=False, formula="xG conceded ÷ shots faced", inputs=("sa_xg", "sa_n"), **S, k=0.0, what="The average quality of the shots the team allows.", read="Low means opponents are pushed into poor shots."),
    pg("big_against_pg", "Big chances against per game", "BigA/g", "shooting", "sa_big", decimals=2, hib=False, formula="shots worth 0.30+ xG faced ÷ matches", inputs=("sa_big", "matches"), src=S, what="Big chances conceded per match."),

    # ------------------------------------------------------------------ possession and passing (events)
    ratio("poss", "Possession", "Poss %", "possession", "w_passes", lambda f: f["w_passes"] + f["wa_passes"], hib=None, decimals=0, formula="team's open-play passes ÷ (team's + opponents') open-play passes", inputs=("w_passes", "wa_passes"), **W, k=0.0,
          what="The share of all passes in the team's matches that the team made. This is how WhoScored itself reports possession.", read="Style, not quality: plenty of good sides have less than half the ball.", caveat="Pass share, not time on the ball."),
    pg("passes_pg", "Passes per game", "Passes/g", "possession", "w_passes", per="w_matches", decimals=0, hib=None, formula="open-play passes ÷ matches with event data", inputs=("w_passes", "w_matches"), src=W, what="Open-play passes attempted per match."),
    ratio("pass_acc", "Pass accuracy", "Pass %", "possession", "w_pass_ok", "w_passes", decimals=0, formula="completed open-play passes ÷ open-play passes", inputs=("w_pass_ok", "w_passes"), **W, k=0.0, what="The share of passes that found a team-mate."),
    ratio("fwd_pct", "Forward pass share", "Fwd %", "possession", "w_fwd", "w_passes", decimals=0, hib=None, formula="passes advancing ≥ 5% of the pitch ÷ open-play passes", inputs=("w_fwd", "w_passes"), **W, k=0.0, what="The share of passes that move the ball forward by at least 5 metres.", read="Directness."),
    ratio("long_pct", "Long ball share", "Long %", "possession", "w_pass_long", "w_passes", decimals=0, hib=None, formula="long balls ÷ open-play passes", inputs=("w_pass_long", "w_passes"), **W, k=0.0, what="The share of passes that are long balls."),
    ratio("avg_pass_len", "Average pass length", "Pass len (m)", "possession", "w_pass_len", "w_pass_len_n", unit="metres", decimals=1, hib=None, formula="total pass length ÷ passes", inputs=("w_pass_len", "w_pass_len_n"), **W, k=0.0, what="How far the team's passes travel, on average."),
    pg("prog_pg", "Progressive passes per game", "Prog/g", "possession", "w_prog", per="w_matches", decimals=0, formula="progressive passes ÷ matches with event data", inputs=("w_prog", "w_matches"), src=W, what="Completed passes that move the ball ≥ 10% of the pitch toward goal into the attacking 60%."),
    pg("passf3_pg", "Passes into the final third per game", "→F3/g", "possession", "w_pass_f3_ok", per="w_matches", decimals=0, formula="completed passes into the final third ÷ matches", inputs=("w_pass_f3_ok", "w_matches"), src=W, what="Completed passes that carry the ball into the attacking third."),
    pg("passbox_pg", "Passes into the box per game", "→Box/g", "possession", "w_pass_box_ok", per="w_matches", decimals=1, formula="completed passes into the penalty area ÷ matches", inputs=("w_pass_box_ok", "w_matches"), src=W, what="Completed open-play passes into the penalty area."),
    pg("crosses_pg", "Crosses per game", "Cross/g", "possession", "w_crosses", per="w_matches", decimals=1, hib=None, formula="crosses ÷ matches", inputs=("w_crosses", "w_matches"), src=W, what="Crosses attempted from open play and free kicks."),
    ratio("cross_acc", "Cross accuracy", "Cross %", "possession", "w_crosses_ok", "w_crosses", decimals=0, formula="crosses that found a team-mate ÷ crosses", inputs=("w_crosses_ok", "w_crosses"), **W, k=0.0, what="The share of crosses that found a team-mate."),
    pg("through_pg", "Through balls per game", "Thru/g", "possession", "w_pass_through", per="w_matches", decimals=1, formula="through balls ÷ matches", inputs=("w_pass_through", "w_matches"), src=W, what="Passes into space behind the defence."),
    ratio("tilt", "Field tilt", "Tilt %", "possession", "w_touch_att3", lambda f: f["w_touch_att3"] + f["wa_touch_att3"], hib=None, decimals=0, formula="team's touches in the attacking third ÷ (team's + opponents' touches in their attacking thirds)", inputs=("w_touch_att3", "wa_touch_att3"), **W, k=0.0,
          what="Who spends more of the match near the other's goal: the team's final-third touches as a share of both sides'.", read="Above 50 means the team lives in the opponent's half."),
    ratio("pass_x", "Build-up height", "Pass x", "possession", "w_pass_x", "w_passes", unit="pitch", decimals=0, hib=None, formula="mean pitch position (0 = own goal line) where the team's passes start", inputs=("w_pass_x", "w_passes"), **W, k=0.0,
          what="How high up the pitch the team's passing happens.", read="A high number means a high, territorial team; a low one a team that builds from deep or sits back."),
    ratio("touch_def3", "Touches in own third", "Own 3rd %", "possession", "w_touch_def3", "w_touches", decimals=0, hib=None, formula="touches in own third ÷ all touches", inputs=("w_touch_def3", "w_touches"), **W, k=0.0, what="The share of the team's touches in its own defensive third."),
    ratio("touch_att3", "Touches in final third", "Final 3rd %", "possession", "w_touch_att3", "w_touches", decimals=0, hib=None, formula="touches in the attacking third ÷ all touches", inputs=("w_touch_att3", "w_touches"), **W, k=0.0, what="The share of the team's touches in the attacking third."),
    pg("touchbox_pg", "Touches in the box per game", "Box touches/g", "possession", "w_touch_box", per="w_matches", decimals=1, formula="touches in the opponent's penalty area ÷ matches", inputs=("w_touch_box", "w_matches"), src=W, what="Touches inside the opponent's penalty area."),
    pg("seq_pg", "Possession sequences per game", "Seqs/g", "possession", "w_seq", per="w_matches", decimals=0, hib=None, formula="sequences ÷ matches", inputs=("w_seq", "w_matches"), src=W, what="Runs of touches the team strung together before losing the ball."),
    ratio("seq_len", "Passes per sequence", "Pass/seq", "possession", "w_seq_passes", "w_seq", unit="ratio", decimals=1, hib=None, formula="passes ÷ possession sequences", inputs=("w_seq_passes", "w_seq"), **W, k=0.0, what="How long the team's possessions are, in passes.", read="Style: patient build-up has long sequences, direct play short ones."),
    pg("seq10_pg", "10+ pass sequences per game", "10+ pass/g", "possession", "w_seq_10p", per="w_matches", decimals=1, hib=None, formula="sequences of ten or more passes ÷ matches", inputs=("w_seq_10p", "w_matches"), src=W, what="Long, patient possessions."),
    pg("direct_pg", "Direct attacks per game", "Direct/g", "possession", "w_seq_fast", per="w_matches", decimals=1, hib=None, formula="sequences gaining ≥ 40% of the pitch in ≤ 15 seconds ÷ matches", inputs=("w_seq_fast", "w_matches"), src=W, what="Fast attacks that go from deep to the final third quickly (counters, quick transitions)."),
    ratio("seq_shot", "Sequences ending in a shot", "Seq→shot %", "possession", "w_seq_shot", "w_seq", decimals=1, formula="sequences with a shot ÷ sequences", inputs=("w_seq_shot", "w_seq"), **W, k=0.0, what="How often a possession ends in a shot."),

    # ------------------------------------------------------------------ carrying and dribbling (events)
    pg("carries_pg", "Carries per game", "Carries/g", "carrying", "w_carries", per="w_matches", decimals=0, hib=None, formula="carries ÷ matches", inputs=("w_carries", "w_matches"), src=W, what="Times a player ran with the ball at least 3 metres (estimated)."),
    pg("carryprog_pg", "Progressive carries per game", "ProgC/g", "carrying", "w_carry_prog", per="w_matches", decimals=1, formula="progressive carries ÷ matches", inputs=("w_carry_prog", "w_matches"), src=W, what="Carries that move the ball well toward goal (estimated)."),
    pg("carrym_pg", "Distance carried per game", "Carry m/g", "carrying", "w_carry_m", per="w_matches", decimals=0, hib=None, formula="Σ carry distance (m) ÷ matches", inputs=("w_carry_m", "w_matches"), src=W, what="Metres covered running with the ball (estimated)."),
    pg("takeons_pg", "Take-ons per game", "Takeons/g", "carrying", "w_takeons", per="w_matches", decimals=1, hib=None, formula="take-ons attempted ÷ matches", inputs=("w_takeons", "w_matches"), src=W, what="Dribbles attempted past an opponent."),
    ratio("takeon_pct", "Take-on success", "Takeon %", "carrying", "w_takeons_won", "w_takeons", decimals=0, formula="successful take-ons ÷ take-ons", inputs=("w_takeons_won", "w_takeons"), **W, k=0.0, what="The share of dribbles that beat the opponent."),
    pg("disp_pg", "Dispossessed per game", "Disp/g", "carrying", "w_dispossessed", per="w_matches", decimals=1, hib=False, formula="times tackled and losing the ball ÷ matches", inputs=("w_dispossessed", "w_matches"), src=W, what="Times a player lost the ball to a tackle."),

    # ------------------------------------------------------------------ pressing and defending
    Metric("ppda", "PPDA", "PPDA", "team", "pressing", "ratio", 1, False, "understat", "base", "derived", "opponent passes ÷ defensive actions, in the opponent's build-up (Understat's definition)", ("ppda_att", "ppda_def"),
           "Opponent passes allowed per defensive action in their build-up: how hard a team presses.", "Lower is more intense. Around 7 is a very high press; 14 or more is a low block.",
           num="ppda_att", den="ppda_def", shape="ratio", min_den=1.0),
    Metric("oppda", "Opponent PPDA", "OPPDA", "team", "pressing", "ratio", 1, None, "understat", "base", "derived", "PPDA measured the other way: passes this team makes per defensive action of the opponent's press", ("oppda_att", "oppda_def"),
           "PPDA measured the other way: how hard opponents press this team.", "Higher means opponents let the team play.", num="oppda_att", den="oppda_def", shape="ratio", min_den=1.0),
    pg("tackles_pg", "Tackles per game", "Tackles/g", "pressing", "w_tackles", per="w_matches", decimals=1, hib=None, formula="tackles won ÷ matches", inputs=("w_tackles", "w_matches"), src=W, what="Tackles won."),
    pg("int_pg", "Interceptions per game", "Int/g", "pressing", "w_interceptions", per="w_matches", decimals=1, hib=None, formula="interceptions ÷ matches", inputs=("w_interceptions", "w_matches"), src=W, what="Passes read and cut out."),
    pg("tklint_pg", "Tackles + interceptions per game", "Tkl+Int/g", "pressing", lambda f: f["w_tackles"] + f["w_interceptions"], per="w_matches", decimals=1, hib=None, formula="(tackles + interceptions) ÷ matches", inputs=("w_tackles", "w_interceptions", "w_matches"), src=W, what="The two main ways of winning the ball back."),
    pg("clear_pg", "Clearances per game", "Clr/g", "pressing", "w_clearances", per="w_matches", decimals=1, hib=None, formula="clearances ÷ matches", inputs=("w_clearances", "w_matches"), src=W, what="Balls cleared away from danger.", read="High for teams that defend deep."),
    pg("blocks_pg", "Blocks per game", "Blocks/g", "pressing", lambda f: f["w_blocks_pass"] + f["w_blocks_shot"], per="w_matches", decimals=1, hib=None, formula="(shots + passes blocked) ÷ matches", inputs=("w_blocks_shot", "w_blocks_pass", "w_matches"), src=W, what="Shots and passes the team's players got in the way of."),
    pg("rec_pg", "Ball recoveries per game", "Recov/g", "pressing", "w_recoveries", per="w_matches", decimals=0, formula="loose balls won back ÷ matches", inputs=("w_recoveries", "w_matches"), src=W, what="Loose or contested balls won back."),
    pg("recatt_pg", "High recoveries per game", "High rec/g", "pressing", "w_rec_att3", per="w_matches", decimals=1, formula="recoveries in the attacking third ÷ matches", inputs=("w_rec_att3", "w_matches"), src=W, what="Balls won back in the attacking third: a marker of pressing.", read="Higher means the team wins the ball near the opponent's goal."),
    ratio("def_height", "Defensive action height", "Def height", "pressing", "w_defx", "w_defx_n", unit="pitch", decimals=0, hib=None, formula="mean pitch position of tackles, interceptions, challenges and pass blocks", inputs=("w_defx", "w_defx_n"), **W, k=0.0, what="How high up the pitch the team defends.", read="A high number is a high line and a front-foot team; a low one, a deep block."),
    pg("beaten_pg", "Dribbled past per game", "Beaten/g", "pressing", "w_challenges", per="w_matches", decimals=1, hib=False, formula="times a dribbler got past a defender ÷ matches", inputs=("w_challenges", "w_matches"), src=W, what="Times the opposition dribbled past the team's defenders."),
    ratio("aerial_pct", "Aerial duel win rate", "Aerial win %", "pressing", "w_aerial_won", "w_aerials", decimals=0, formula="aerial duels won ÷ aerial duels", inputs=("w_aerial_won", "w_aerials"), **W, k=0.0, what="The share of aerial duels the team won."),
    pg("opp_passes_pg", "Opposition passes per game", "OppPass/g", "pressing", "wa_passes", per="w_matches", decimals=0, hib=None, formula="the opposition's open-play passes ÷ matches", inputs=("wa_passes", "w_matches"), src=W, what="How many passes opponents make against the team: how much of the ball it gives away."),
    pg("errors_pg", "Errors per game", "Err/g", "pressing", "w_errors", per="w_matches", decimals=2, hib=False, formula="errors leading to chances ÷ matches", inputs=("w_errors", "w_matches"), src=W, what="Mistakes that gave the opponent a chance or a goal."),
    pg("opp_prog_pg", "Opposition progressive passes per game", "OppProg/g", "pressing", "wa_prog", per="w_matches", decimals=0, hib=False, formula="the opposition's progressive passes ÷ matches", inputs=("wa_prog", "w_matches"), src=W, what="How easily opponents move the ball forward against the team.", read="Lower means the team stops progression."),

    # ------------------------------------------------------------------ set pieces
    pg("corners_pg", "Corners per game", "Corners/g", "setpieces", "w_corners", per="w_matches", decimals=1, hib=None, formula="corner kicks taken ÷ matches", inputs=("w_corners", "w_matches"), src=W, what="Corner kicks the team took."),
    pg("corners_against_pg", "Corners conceded per game", "CornersA/g", "setpieces", "wa_corners", per="w_matches", decimals=1, hib=False, formula="corner kicks taken by the opposition ÷ matches", inputs=("wa_corners", "w_matches"), src=W, what="Corner kicks the opposition took."),
    pg("spxg_pg", "Set-piece xG per game", "SP xG/g", "setpieces", "s_sp_xg", decimals=2, formula="xG from corners, free kicks and set pieces ÷ matches", inputs=("s_sp_xg", "matches"), src=S, what="The chances the team creates from dead balls."),
    pg("spxga_pg", "Set-piece xG against per game", "SP xGA/g", "setpieces", "sa_sp_xg", decimals=2, hib=False, formula="xG conceded from set pieces ÷ matches", inputs=("sa_sp_xg", "matches"), src=S, what="The chances the team concedes from dead balls.", read="Lower means solid set-piece defending."),
    ratio("sp_share", "Share of xG from set pieces", "SP xG %", "setpieces", "s_sp_xg", "s_xg_np", decimals=0, hib=None, formula="set-piece xG ÷ non-penalty xG", inputs=("s_sp_xg", "s_xg_np"), **S, k=0.0, what="How much of the team's non-penalty xG comes from dead balls."),
    pg("head_pg", "Headed shots per game", "Head/g", "setpieces", "s_head", decimals=1, hib=None, formula="headed shots ÷ matches", inputs=("s_head", "matches"), src=S, what="Shots taken with the head."),
    pg("pens_pg", "Penalties won per game", "Pens/g", "setpieces", "s_pens", decimals=2, formula="penalty kicks taken ÷ matches", inputs=("s_pens", "matches"), src=S, what="Penalties taken by the team."),
    pg("pens_against_pg", "Penalties conceded per game", "PensA/g", "setpieces", "sa_pens", decimals=2, hib=False, formula="penalty kicks taken by the opposition ÷ matches", inputs=("sa_pens", "matches"), src=S, what="Penalties awarded against the team."),
    pg("throwins_pg", "Throw-ins per game", "Throws/g", "setpieces", "w_throwins", per="w_matches", decimals=1, hib=None, formula="throw-ins ÷ matches", inputs=("w_throwins", "w_matches"), src=W, what="Throw-ins the team took."),

    # ------------------------------------------------------------------ goalkeeping
    pg("saves_pg", "Saves per game", "Saves/g", "goalkeeping", "w_gk_saves", per="w_matches", decimals=1, hib=None, formula="saves ÷ matches", inputs=("w_gk_saves", "w_matches"), src=W, what="Shots the team's goalkeepers saved."),
    ratio("save_pct", "Save percentage", "Save %", "goalkeeping", "w_gk_saves", lambda f: f["w_gk_saves"] + f["wa_goals"], decimals=0, formula="saves ÷ (saves + goals conceded excluding own goals)", inputs=("w_gk_saves", "wa_goals"), **W, k=0.0, what="The share of shots on target the team's goalkeepers saved.", caveat="Not adjusted for shot quality."),
    ratio("cs_pct", "Clean sheets", "CS %", "goalkeeping", "cs", "matches", decimals=0, formula="matches without conceding ÷ matches", inputs=("cs", "matches"), **U, k=0.0, what="The share of matches without conceding."),
    pg("claims_pg", "High claims per game", "Claims/g", "goalkeeping", "w_gk_claims", per="w_matches", decimals=2, hib=None, formula="high claims ÷ matches", inputs=("w_gk_claims", "w_matches"), src=W, what="Crosses the team's goalkeepers claimed."),

    # ------------------------------------------------------------------ discipline
    pg("yellow_pg", "Yellow cards per game", "YC/g", "discipline", "w_yellow", per="w_matches", decimals=2, hib=False, formula="yellow cards ÷ matches", inputs=("w_yellow", "w_matches"), src=W, what="Bookings per match."),
    counter("red", "Red cards", "RC", "discipline", hib=False, formula="Red cards (including second yellows)", inputs=("red",), **W, what="Red cards shown to the team.", num="w_red"),
    pg("fouls_pg", "Fouls per game", "Fouls/g", "discipline", "w_fouls", per="w_matches", decimals=1, hib=False, formula="fouls committed ÷ matches", inputs=("w_fouls", "w_matches"), src=W, what="Fouls the team committed."),
    pg("fouled_pg", "Fouls won per game", "Fouled/g", "discipline", "w_fouled", per="w_matches", decimals=1, formula="fouls suffered ÷ matches", inputs=("w_fouled", "w_matches"), src=W, what="Fouls committed against the team."),
    pg("offsides_pg", "Offsides per game", "Offside/g", "discipline", "w_offsides", per="w_matches", decimals=1, hib=False, formula="times flagged offside ÷ matches", inputs=("w_offsides", "w_matches"), src=W, what="Times the team's players were caught offside."),
    pg("offsides_won_pg", "Offsides won per game", "OffsideW/g", "discipline", "w_offside_won", per="w_matches", decimals=1, formula="opponents caught offside by the team's line ÷ matches", inputs=("w_offside_won", "w_matches"), src=W, what="Times the team's defence caught an opponent offside.", read="Higher means an active offside trap."),

    # ------------------------------------------------------------------ squad
    counter("squad_age", "Squad age", "Age", "squad", level="team", unit="age", decimals=1, hib=None, formula="minutes-weighted mean age of the team's players", inputs=("squad_age",), source="espn", needs="base", what="The average age of the team, weighted by minutes played.", read="Players without a confirmed age are left out."),
    counter("players_used", "Players used", "Used", "squad", hib=None, formula="Players who have played at least one minute", inputs=("players_used",), **U, what="How many different players the team has used.", read="A high number means injuries, rotation or an unsettled squad."),
)

TEAM_METRIC_KEYS = tuple(m.key for m in TEAM_METRICS)
