"""Every player metric, declared once. See :mod:`app.metrics.registry` for how a declaration is read.

Frame arrays a player metric may use (the player dataset builder fills them; a missing one reads as unknown, never zero):

* Understat season table:  ``minutes games goals npg assists shots key_passes yellow red xg npxg xa xgchain xgbuildup available age``
* derived from those:      ``npxg_xa g_xg npg_npxg a_xa mins_per_app minutes_share``
* match pages (``s_*``):   shot-level sums over the season's stored Understat match pages (only when nearly every match is stored),
                           plus ``starts``
* event data (``w_*``):    every counter of :mod:`app.events.counters` for the player, prefixed ``w_`` (``w_min`` is event minutes)

Reading a declaration: ``rate("tackles90", ..., num="w_tackles", per="w_min")`` is ``90 * w_tackles / w_min``.
"""

from __future__ import annotations

from .registry import Group, Metric, counter, rate, ratio

GROUPS: tuple[Group, ...] = (
    Group("availability", "Availability", "How much he plays: the sample size behind everything else."),
    Group("shooting", "Shooting", "How often and how well he shoots, and how his goals compare with his chances."),
    Group("creation", "Creating chances", "Chances he makes for others, from the pass that sets up the shot."),
    Group("involvement", "Involvement", "How much of the team's attacking play runs through him (every possession that ended in a shot)."),
    Group("passing", "Passing", "How he uses the ball: volume, accuracy, how forward and how long."),
    Group("carrying", "Carrying", "Moving the ball up the pitch by running with it (estimated from the order of events)."),
    Group("possession", "Dribbling and possession", "Beating opponents, keeping the ball, and where he is on the ball."),
    Group("defending", "Defending", "Winning the ball back and stopping attacks."),
    Group("duels", "Duels", "One-against-one contests: tackles, aerial duels and who wins them."),
    Group("goalkeeping", "Goalkeeping", "Stopping shots, claiming crosses and sweeping up."),
    Group("setpieces", "Set pieces", "Corners, free kicks, throw-ins and penalties."),
    Group("discipline", "Discipline", "Fouls, cards and offsides."),
    Group("impact", "On-pitch impact", "What the team did while he was on the pitch. Noisy: it also reflects the team."),
    Group("rating", "Match rating", "WhoScored's own 1-10 rating for each match: a proprietary, black-box score."),
    Group("scores", "Role scores", "One-number summaries of a player's percentiles for his role."),
)

U = {"source": "understat", "needs": "base"}     # Understat's league table
S = {"source": "understat", "needs": "shots"}    # Understat's match pages (shot by shot)
W = {"source": "whoscored", "needs": "events"}   # WhoScored event data
BOTH = {"source": "both", "needs": "events"}

PLAYER_METRICS: tuple[Metric, ...] = (
    # ------------------------------------------------------------------ availability
    counter("minutes", "Minutes", "Min", "availability", formula="Sum of league minutes played", inputs=("minutes",), **U,
            what="League minutes played.", read="The sample size behind every rate: under about 450 minutes, per-90 numbers swing wildly."),
    counter("games", "Appearances", "Apps", "availability", formula="Number of league matches he played in, however briefly", inputs=("games",), **U,
            what="League appearances, including cameos."),
    counter("starts", "Starts", "Starts", "availability", formula="Matches in which he was in the starting line-up", inputs=("starts",), source="understat", needs="shots", kind="derived",
            what="Matches he started, from the line-ups of the stored match pages.", read="A fixture starts most matches; a rotation player far fewer."),
    counter("mins_per_app", "Minutes per appearance", "Min/App", "availability", formula="minutes ÷ appearances", inputs=("minutes", "games"), hib=True, **U,
            what="Average minutes when he plays.", read="Under 45 means he is mostly a substitute.",
            num=lambda f: f["minutes"] / f["games"].clip(min=1)),
    counter("minutes_share", "Share of team minutes", "Min %", "availability", unit="share", formula="minutes ÷ (90 × matches his club played while he could have been in the squad)",
            inputs=("minutes", "available"), **U, what="Minutes played as a share of everything his team has played.",
            read="Above 80% is a fixture in the side; under 40% is a rotation or bench player.", num=lambda f: (f["minutes"] / f["available"]).clip(max=1.0)),
    counter("age", "Age", "Age", "availability", unit="age", hib=None, formula="Years between his date of birth and the season's reference date", inputs=("age",), source="espn", needs="base",
            what="Age on the reference date (the end of the season shown, or today for a live season). From the exact date of birth on his club's squad list, or Wikidata.",
            read="Blank when no source could be matched to him with certainty: the app does not guess.", caveat="An age matched by name alone (marked ?) is shown but never used by a filter."),

    # ------------------------------------------------------------------ shooting
    counter("goals", "Goals", "G", "shooting", formula="Goals scored, penalties included", inputs=("goals",), **U, what="Goals scored.", read="Compare with xG: it is what happened, not what should have."),
    counter("npg", "Non-penalty goals", "npG", "shooting", formula="goals − penalty goals", inputs=("npg",), **U, what="Goals excluding penalties."),
    counter("shots", "Shots", "Sh", "shooting", formula="Shots taken, blocked shots included, own goals excluded", inputs=("shots",), **U, what="Shots taken."),
    counter("xg", "Expected goals", "xG", "shooting", unit="total", decimals=1, formula="Sum of the xG of every shot he took", inputs=("xg",), **U,
            what="The goals his shots were worth, by the quality of each chance (where and how it was taken).", read="The goals a typical finisher would have scored from the same shots."),
    counter("npxg", "Non-penalty xG", "npxG", "shooting", unit="total", decimals=1, formula="xG excluding penalties", inputs=("npxg",), **U,
            what="xG without penalties, which are worth about 0.76 each and inflate the totals of penalty takers."),
    rate("shots90", "Shots per 90", "Shots/90", "shooting", "shots", decimals=1, formula="shots × 90 ÷ minutes", inputs=("shots", "minutes"), **U,
         what="How often he shoots.", read="Volume alone is not quality: pair it with xG per shot."),
    rate("npxg90", "Non-penalty xG per 90", "npxG/90", "shooting", "npxg", formula="npxG × 90 ÷ minutes", inputs=("npxg", "minutes"), **U,
         what="The quality-weighted chances he takes per 90 minutes, penalties excluded.", read="The cleanest measure of goal threat. Around 0.4 per 90 is elite for a forward."),
    rate("goals90", "Goals per 90", "Goals/90", "shooting", "goals", formula="goals × 90 ÷ minutes", inputs=("goals", "minutes"), **U,
         what="Goals scored per 90 minutes, penalties included.", read="What happened, not what should have."),
    Metric("xgps", "xG per shot", "xG/shot", "player", "shooting", "ratio", 3, True, "understat", "base", "derived", "xG ÷ shots", ("xg", "shots"),
           "The average quality of each shot.", "High means good positions (or penalties); low means speculative long shots.", num="xg", den="shots", shape="ratio", min_den=1.0),
    counter("g_xg", "Goals minus xG", "G-xG", "shooting", unit="total", decimals=1, formula="goals − xG", inputs=("goals", "xg"), **U,
            what="Goals above (positive) or below (negative) what the chances were worth.", read="Mostly luck over a season: see its significance (z) before believing it is skill.", num="g_xg"),
    counter("npg_npxg", "Non-penalty goals minus npxG", "npG-npxG", "shooting", unit="total", decimals=1, formula="npG − npxG", inputs=("npg", "npxg"), **U,
            what="Open-play finishing against the chances: goals above or below npxG.", num="npg_npxg"),
    counter("g_xg_z", "Finishing significance (z)", "G-xG z", "shooting", unit="ratio", decimals=1, hib=None, formula="(goals − xG) ÷ √(shots × p × (1 − p)), p = xG ÷ shots", inputs=("goals", "xg", "shots"), **U,
            what="How surprising his goal tally is given his shots: about ±1 is ordinary, beyond ±2 is rare.", read="Beyond +2 he is running hot (expect a slowdown); below −2 goals may be overdue.",
            caveat="A conservative estimate assuming every shot is equally likely; the player page uses the exact distribution over his actual shots.", num="g_xg_z"),
    rate("sot90", "Shots on target per 90", "SoT/90", "shooting", "s_sot", decimals=1, formula="(goals + saved shots) × 90 ÷ minutes", inputs=("s_sot", "minutes"), **S,
         what="Shots that were goals or were saved, per 90.", read="Blocked shots and misses are not on target."),
    ratio("sot_pct", "Shots on target", "SoT %", "shooting", "s_sot", "s_n", decimals=0, formula="shots on target ÷ shots", inputs=("s_sot", "s_n"), **S, k=25.0,
          what="The share of his shots that were goals or saves.", read="A high share means he gets his shots on frame; a low one means blocked or wasted shots."),
    ratio("goal_conv", "Shot conversion", "Conv %", "shooting", "s_goals", "s_n", decimals=0, formula="goals ÷ shots", inputs=("s_goals", "s_n"), **S, k=25.0,
          what="The share of his shots that were goals.", read="Depends on shot quality: compare with xG per shot."),
    ratio("avg_dist", "Average shot distance", "Dist (m)", "shooting", "s_dist", "s_n", unit="metres", decimals=1, hib=None, formula="mean distance from the goal centre to where each shot was taken", inputs=("s_dist", "s_n"), **S, k=0.0,
          what="How far from goal his shots are, on average.", read="Shorter usually means better chances; long averages point to speculative shooting."),
    ratio("box_share", "Shots from inside the box", "Box %", "shooting", "s_box", "s_n", decimals=0, formula="shots in the penalty area ÷ shots", inputs=("s_box", "s_n"), **S, k=25.0, hib=None,
          what="The share of his shots taken inside the penalty area.", read="Poachers live above 80%; creators and long-range shooters sit lower."),
    rate("big90", "Big chances per 90", "Big/90", "shooting", "s_big", decimals=2, formula="shots worth 0.30+ xG × 90 ÷ minutes", inputs=("s_big", "minutes"), **S,
         what="Shots worth at least 0.30 xG (roughly a one-in-three chance or better), per 90.", read="How often he is in the best positions.", caveat="Understat has no official big-chance flag, so 0.30 xG is this app's line."),
    ratio("big_conv", "Big chance conversion", "Big conv %", "shooting", "s_big_goals", "s_big", decimals=0, formula="goals from 0.30+ xG shots ÷ such shots", inputs=("s_big_goals", "s_big"), **S, k=8.0,
          what="How often he scores when given a big chance.", read="Elite finishers convert more than half; the rest hover around 35-40%."),
    rate("head90", "Headers per 90", "Head/90", "shooting", "s_head", decimals=2, formula="headed shots × 90 ÷ minutes", inputs=("s_head", "minutes"), **S, what="Shots taken with the head, per 90."),
    ratio("head_share", "Share of xG from headers", "Head xG %", "shooting", "s_head_xg", "s_xg", decimals=0, hib=None, formula="xG of headed shots ÷ xG of all shots", inputs=("s_head_xg", "s_xg"), **S, k=1.0,
          what="How much of his chance quality comes from his head.", read="High for target men and centre-backs attacking set pieces."),
    rate("op90", "Open-play xG per 90", "OP xG/90", "shooting", "s_op_xg", decimals=2, formula="xG of open-play shots × 90 ÷ minutes", inputs=("s_op_xg", "minutes"), **S,
         what="xG from shots in open play (not set pieces or penalties), per 90.", read="The repeatable part of his threat."),
    rate("spxg90", "Set-piece xG per 90", "SP xG/90", "shooting", "s_sp_xg", decimals=2, formula="xG of shots from corners, free kicks and set pieces × 90 ÷ minutes", inputs=("s_sp_xg", "minutes"), **S,
         what="xG from shots that came from corners, free kicks and other set pieces, per 90.", read="High for defenders and target men who attack dead balls."),

    # ------------------------------------------------------------------ creation
    counter("assists", "Assists", "A", "creation", formula="Goals he set up", inputs=("assists",), **U, what="Assists.", read="Compare with xA: it depends on team-mates finishing."),
    counter("xa", "Expected assists", "xA", "creation", unit="total", decimals=1, formula="Sum of the xG of the shots his passes created", inputs=("xa",), **U,
            what="The xG of the shots his passes created.", read="Assist quality without depending on the finisher."),
    counter("a_xa", "Assists minus xA", "A-xA", "creation", unit="total", decimals=1, formula="assists − xA", inputs=("assists", "xa"), **U,
            what="Assists above or below what the created chances were worth.", read="Depends on team-mates finishing.", num="a_xa"),
    rate("xa90", "xA per 90", "xA/90", "creation", "xa", formula="xA × 90 ÷ minutes", inputs=("xa", "minutes"), **U,
         what="The xG of the shots his passes created, per 90 minutes.", read="Assist quality without depending on the finisher. 0.25+ per 90 is elite."),
    rate("kp90", "Key passes per 90", "KP/90", "creation", "key_passes", formula="key passes × 90 ÷ minutes", inputs=("key_passes", "minutes"), **U,
         what="Passes that directly led to a shot, per 90.", read="Creation volume; check xA to see how good the chances were."),
    rate("contrib90", "npxG + xA per 90", "npxG+xA", "creation", "npxg_xa", formula="(npxG + xA) × 90 ÷ minutes", inputs=("npxg", "xa", "minutes"), **U,
         what="Expected non-penalty goal involvement: shots taken plus chances created.", read="One number for attacking output. 0.6+ per 90 is elite."),
    rate("bigcreated90", "Big chances created per 90", "BCC/90", "creation", "w_bc_created", per="w_min", decimals=2, k=360.0, formula="passes that created a big chance × 90 ÷ event minutes", inputs=("w_bc_created", "w_min"), **W,
         what="Passes that set up a chance Opta marks as a big chance, per 90.", read="Cleaner than key passes for the very best passes."),
    rate("through90", "Through balls per 90", "Thru/90", "creation", "w_pass_through", per="w_min", decimals=2, k=360.0, formula="through balls × 90 ÷ event minutes", inputs=("w_pass_through", "w_min"), **W,
         what="Passes played into space behind the defence, per 90.", read="A marker of line-breaking passers."),
    rate("crosses90", "Crosses per 90", "Cross/90", "creation", "w_crosses", per="w_min", decimals=1, k=360.0, hib=None, formula="crosses × 90 ÷ event minutes", inputs=("w_crosses", "w_min"), **W,
         what="Crosses attempted from open play and free kicks, per 90.", read="High for wingers and full-backs; volume says nothing about quality."),
    ratio("cross_acc", "Cross accuracy", "Cross %", "creation", "w_crosses_ok", "w_crosses", formula="crosses that found a team-mate ÷ crosses", inputs=("w_crosses_ok", "w_crosses"), **W, k=30.0,
          what="The share of crosses that found a team-mate.", read="Rarely above 35%: crossing is hard."),

    # ------------------------------------------------------------------ involvement
    rate("xgchain90", "xGChain per 90", "xGChain/90", "involvement", "xgchain", formula="xGChain × 90 ÷ minutes", inputs=("xgchain", "minutes"), **U,
         what="The total xG of every possession he touched that ended in a shot, per 90.", read="How much of the team's attacking flow runs through him."),
    rate("xgbuildup90", "xGBuildup per 90", "Buildup/90", "involvement", "xgbuildup", formula="xGBuildup × 90 ÷ minutes", inputs=("xgbuildup", "minutes"), **U,
         what="xGChain excluding his own shots and key passes: the earlier build-up.", read="High buildup with modest chain means he starts attacks rather than finishes them."),
    Metric("buildup_share", "Build-up share of chain", "Buildup %", "player", "involvement", "share", 0, None, "understat", "base", "derived", "xGBuildup ÷ xGChain", ("xgbuildup", "xgchain"),
           "The part of his xGChain that comes from build-up rather than shooting or the final pass.", "Above ~60% is a deep, early-involvement player.", num="xgbuildup", den="xgchain", shape="ratio", min_den=0.5),

    # ------------------------------------------------------------------ passing
    rate("passes90", "Passes per 90", "Passes/90", "passing", "w_passes", per="w_min", decimals=0, hib=None, k=360.0, formula="open-play passes × 90 ÷ event minutes", inputs=("w_passes", "w_min"), **W,
         what="Open-play passes attempted per 90 minutes. Throw-ins, goal kicks, corners, keeper throws and crosses are left out.", read="Volume: how much of the team's play goes through him. Not quality on its own."),
    ratio("pass_acc", "Pass accuracy", "Pass %", "passing", "w_pass_ok", "w_passes", formula="completed open-play passes ÷ open-play passes", inputs=("w_pass_ok", "w_passes"), **W, k=60.0,
          what="The share of open-play passes that found a team-mate.", read="Depends on how risky the passes are: a high figure with few forward passes is safe play, not necessarily good play."),
    ratio("fwd_pass_ratio", "Forward pass ratio", "Fwd pass %", "passing", "w_fwd", "w_passes", hib=None, formula="passes that advance the ball ≥ 5% of the pitch ÷ open-play passes", inputs=("w_fwd", "w_passes"), **W, k=60.0,
          what="The share of open-play passes that move the ball at least 5% of the pitch (about 5 metres) toward the opponent's goal.",
          read="How direct his passing is. Compare within a role: centre-backs and holding midfielders naturally pass less forward than attackers."),
    rate("prog_passes90", "Progressive passes per 90", "Prog/90", "passing", "w_prog", per="w_min", decimals=1, k=360.0, formula="completed passes advancing ≥ 10% of the pitch and ending in the attacking 60% × 90 ÷ event minutes", inputs=("w_prog", "w_min"), **W,
         what="Completed passes that move the ball at least 10% of the pitch (about 10 metres) toward goal and end in the attacking 60% of the pitch.",
         read="Who moves the team up the pitch with the ball. Compare with xGBuildup, which measures involvement in possessions that end in shots."),
    rate("fwdm90", "Metres gained by passing per 90", "Fwd m/90", "passing", "w_pass_fwd_m", per="w_min", decimals=0, k=360.0, formula="Σ forward distance of completed open-play passes × 90 ÷ event minutes", inputs=("w_pass_fwd_m", "w_min"), **W,
         what="The distance the ball was moved toward goal by his completed passes, per 90.", read="Rewards long, forward distribution."),
    rate("passf3_90", "Passes into the final third per 90", "→F3/90", "passing", "w_pass_f3_ok", per="w_min", decimals=1, k=360.0, formula="completed passes from outside the final third into it × 90 ÷ event minutes", inputs=("w_pass_f3_ok", "w_min"), **W,
         what="Completed passes that carry the ball into the attacking third, per 90.", read="Who feeds the front line."),
    rate("passbox90", "Passes into the box per 90", "→Box/90", "passing", "w_pass_box_ok", per="w_min", decimals=1, k=360.0, formula="completed passes into the penalty area × 90 ÷ event minutes", inputs=("w_pass_box_ok", "w_min"), **W,
         what="Completed open-play passes into the penalty area, per 90.", read="High for creators and wide players."),
    ratio("long_ratio", "Long ball share", "Long %", "passing", "w_pass_long", "w_passes", hib=None, formula="open-play long balls ÷ open-play passes", inputs=("w_pass_long", "w_passes"), **W, k=60.0,
          what="The share of his passes that are long balls (Opta's own marker).", read="Style, not quality: high for goalkeepers and centre-backs who go long."),
    ratio("long_acc", "Long ball accuracy", "Long acc %", "passing", "w_pass_long_ok", "w_pass_long", formula="completed long balls ÷ long balls", inputs=("w_pass_long_ok", "w_pass_long"), **W, k=20.0,
          what="The share of long balls that found a team-mate.", read="Above 60% is excellent for a long passer."),
    ratio("avg_pass_len", "Average pass length", "Pass len (m)", "passing", "w_pass_len", "w_pass_len_n", unit="metres", decimals=1, hib=None, formula="total length of open-play passes ÷ passes", inputs=("w_pass_len", "w_pass_len_n"), **W, k=60.0,
          what="How far his passes travel, on average.", read="Style: short passers sit under 17 m, long distributors over 22 m."),

    # ------------------------------------------------------------------ carrying
    rate("carries90", "Carries per 90", "Carries/90", "carrying", "w_carries", per="w_min", decimals=1, hib=None, k=360.0, formula="carries × 90 ÷ event minutes", inputs=("w_carries", "w_min"), **W,
         what="Times he ran with the ball at least 3 metres, per 90.", read="Estimated from consecutive on-ball events (see the dictionary); volume, not progress.", caveat="An estimate: the data has no carry event."),
    rate("carrym90", "Distance carried per 90", "Carry m/90", "carrying", "w_carry_m", per="w_min", decimals=0, hib=None, k=360.0, formula="Σ carry distance (m) × 90 ÷ event minutes", inputs=("w_carry_m", "w_min"), **W,
         what="Metres covered running with the ball, per 90.", caveat="An estimate."),
    rate("carryprog90", "Progressive carries per 90", "ProgC/90", "carrying", "w_carry_prog", per="w_min", decimals=1, k=360.0, formula="carries advancing ≥ 10% of the pitch into the attacking 60%, or into the box × 90 ÷ event minutes", inputs=("w_carry_prog", "w_min"), **W,
         what="Carries that move the ball well toward goal, per 90.", read="Who drives the team forward with the ball at his feet.", caveat="An estimate."),
    rate("carryf3_90", "Carries into the final third per 90", "C→F3/90", "carrying", "w_carry_f3", per="w_min", decimals=1, k=360.0, formula="carries from outside the final third into it × 90 ÷ event minutes", inputs=("w_carry_f3", "w_min"), **W,
         what="Carries that take the ball into the attacking third, per 90.", caveat="An estimate."),
    rate("carrybox90", "Carries into the box per 90", "C→Box/90", "carrying", "w_carry_box", per="w_min", decimals=2, k=360.0, formula="carries from outside the penalty area into it × 90 ÷ event minutes", inputs=("w_carry_box", "w_min"), **W,
         what="Carries that take the ball into the penalty area, per 90.", caveat="An estimate."),
    rate("progact90", "Progressive actions per 90", "ProgAct/90", "carrying", lambda f: f["w_prog"] + f["w_carry_prog"], per="w_min", decimals=1, k=360.0,
         formula="(progressive passes + progressive carries) × 90 ÷ event minutes", inputs=("w_prog", "w_carry_prog", "w_min"), **W,
         what="Every way he moves the ball up the pitch: progressive passes plus progressive carries, per 90.", read="The broadest measure of who drives the team forward."),

    # ------------------------------------------------------------------ dribbling and possession
    rate("takeons90", "Take-ons per 90", "Takeons/90", "possession", "w_takeons", per="w_min", decimals=1, hib=None, k=360.0, formula="dribbles attempted past an opponent × 90 ÷ event minutes", inputs=("w_takeons", "w_min"), **W,
         what="Times he tried to dribble past an opponent, per 90.", read="High for wingers; volume, not success."),
    ratio("takeon_success", "Take-on success", "Takeon %", "possession", "w_takeons_won", "w_takeons", formula="take-ons that beat the opponent ÷ take-ons", inputs=("w_takeons_won", "w_takeons"), **W, k=25.0,
          what="The share of his dribbles that got past the defender.", read="Above 55% is excellent for someone who dribbles a lot."),
    rate("takeonswon90", "Take-ons won per 90", "TakeonsW/90", "possession", "w_takeons_won", per="w_min", decimals=1, k=360.0, formula="successful take-ons × 90 ÷ event minutes", inputs=("w_takeons_won", "w_min"), **W,
         what="Dribbles that beat the opponent, per 90."),
    rate("disp90", "Dispossessed per 90", "Disp/90", "possession", "w_dispossessed", per="w_min", decimals=1, hib=False, k=360.0, formula="times he lost the ball to a tackle × 90 ÷ event minutes", inputs=("w_dispossessed", "w_min"), **W,
         what="Times he was tackled and lost the ball, per 90.", read="Lower is better, but players who carry the ball a lot are dispossessed more."),
    rate("touches90", "Touches per 90", "Touches/90", "possession", "w_touches", per="w_min", decimals=0, hib=None, k=360.0, formula="events on the ball × 90 ÷ event minutes", inputs=("w_touches", "w_min"), **W,
         what="Every event on the ball (passes, take-ons, tackles, shots), per 90.", read="How involved he is."),
    rate("touchbox90", "Touches in the box per 90", "Box touches/90", "possession", "w_touch_box", per="w_min", decimals=1, k=360.0, formula="touches in the opponent's penalty area × 90 ÷ event minutes", inputs=("w_touch_box", "w_min"), **W,
         what="Touches inside the opponent's penalty area, per 90.", read="The best simple marker of a penalty-box threat."),
    rate("touchatt90", "Touches in the final third per 90", "F3 touches/90", "possession", "w_touch_att3", per="w_min", decimals=0, hib=None, k=360.0, formula="touches in the attacking third × 90 ÷ event minutes", inputs=("w_touch_att3", "w_min"), **W,
         what="Touches in the attacking third, per 90."),
    rate("fouled90", "Fouls won per 90", "Fouled/90", "possession", "w_fouled", per="w_min", decimals=1, k=360.0, formula="fouls suffered × 90 ÷ event minutes", inputs=("w_fouled", "w_min"), **W,
         what="Fouls committed against him, per 90.", read="Good dribblers and strikers draw many."),

    # ------------------------------------------------------------------ defending
    rate("tackles90", "Tackles per 90", "Tackles/90", "defending", "w_tackles", per="w_min", decimals=1, k=360.0, formula="tackles won × 90 ÷ event minutes", inputs=("w_tackles", "w_min"), **W,
         what="Times he took the ball off an opponent with a tackle (being dribbled past is not counted here).", read="Compare within a role."),
    ratio("tackle_success", "Tackle success", "Tackle %", "defending", "w_tackles", lambda f: f["w_tackles"] + f["w_challenges"], formula="tackles won ÷ (tackles won + times dribbled past)", inputs=("w_tackles", "w_challenges"), **W, k=15.0,
          what="Of the times he went in for the ball, how often he won it rather than being beaten.", read="A high rate on few tackles can mean he avoids contact."),
    rate("challenges90", "Dribbled past per 90", "Beaten/90", "defending", "w_challenges", per="w_min", decimals=1, hib=False, k=360.0, formula="times beaten by a dribble × 90 ÷ event minutes", inputs=("w_challenges", "w_min"), **W,
         what="Times a dribbler got past him, per 90.", read="Lower is better; defenders who defend high up face more."),
    rate("interceptions90", "Interceptions per 90", "Int/90", "defending", "w_interceptions", per="w_min", decimals=1, k=360.0, formula="interceptions × 90 ÷ event minutes", inputs=("w_interceptions", "w_min"), **W,
         what="Passes he read and cut out, per 90.", read="Positioning and anticipation rather than one-on-one defending."),
    rate("tklint90", "Tackles + interceptions per 90", "Tkl+Int/90", "defending", lambda f: f["w_tackles"] + f["w_interceptions"], per="w_min", decimals=1, k=360.0, formula="(tackles + interceptions) × 90 ÷ event minutes", inputs=("w_tackles", "w_interceptions", "w_min"), **W,
         what="The two main ways of winning the ball back, per 90.", read="The standard one-number summary of ball-winning."),
    rate("clearances90", "Clearances per 90", "Clr/90", "defending", "w_clearances", per="w_min", decimals=1, hib=None, k=360.0, formula="clearances × 90 ÷ event minutes", inputs=("w_clearances", "w_min"), **W,
         what="Balls cleared away from danger, per 90.", read="High for centre-backs of teams that defend deep."),
    rate("blocks90", "Blocks per 90", "Blocks/90", "defending", lambda f: f["w_blocks_pass"] + f["w_blocks_shot"], per="w_min", decimals=1, k=360.0, formula="(shots blocked + passes blocked) × 90 ÷ event minutes", inputs=("w_blocks_shot", "w_blocks_pass", "w_min"), **W,
         what="Shots and passes he got in the way of, per 90."),
    rate("recoveries90", "Ball recoveries per 90", "Recov/90", "defending", "w_recoveries", per="w_min", decimals=1, k=360.0, formula="loose balls won back × 90 ÷ event minutes", inputs=("w_recoveries", "w_min"), **W,
         what="Loose or contested balls he won back for his team, per 90.", read="Work rate off the ball."),
    rate("recatt90", "High recoveries per 90", "High rec/90", "defending", "w_rec_att3", per="w_min", decimals=2, k=360.0, formula="recoveries in the attacking third × 90 ÷ event minutes", inputs=("w_rec_att3", "w_min"), **W,
         what="Balls won back in the attacking third, per 90.", read="A marker of pressing: regains close to the opponent's goal."),
    ratio("def_height", "Defensive action height", "Def height", "defending", "w_defx", "w_defx_n", unit="pitch", decimals=0, hib=None, formula="mean pitch position (0 = own goal line, 100 = opponent's) of tackles, interceptions, challenges and pass blocks", inputs=("w_defx", "w_defx_n"), **W, k=30.0,
          what="How high up the pitch he does his defending.", read="Style: above 45 is a front-foot defender or a pressing forward; below 30, a deep one."),
    rate("errors90", "Errors per 90", "Err/90", "defending", "w_errors", per="w_min", decimals=2, hib=False, k=720.0, formula="errors by him × 90 ÷ event minutes", inputs=("w_errors", "w_min"), **W,
         what="Mistakes recorded against him (a slip, a bad touch) that gave the opponent something, per 90.", read="Lower is better; rare, so read it over a full season."),

    # ------------------------------------------------------------------ duels
    rate("def_duels90", "Defensive duels per 90", "Duels/90", "duels", lambda f: f["w_tackles"] + f["w_challenges"] + f["w_aerial_def"], per="w_min", decimals=1, k=360.0,
         formula="(tackles + times dribbled past + defensive aerial duels) × 90 ÷ event minutes", inputs=("w_tackles", "w_challenges", "w_aerial_def", "w_min"), **W,
         what="Tackles, challenges (beaten by a dribble) and aerial duels where he was the defending side, per 90 minutes. This is our own definition: the data has no event with that name.",
         read="How often he is asked to defend one-on-one. A busy defender may simply play for a team that defends a lot, so read it with the win rate."),
    ratio("def_duel_win", "Defensive duel win rate", "Duel win %", "duels", lambda f: f["w_tackles"] + f["w_aerial_def_won"], lambda f: f["w_tackles"] + f["w_challenges"] + f["w_aerial_def"],
          formula="(tackles won + defensive aerials won) ÷ (tackles + times dribbled past + defensive aerials)", inputs=("w_tackles", "w_aerial_def_won", "w_challenges", "w_aerial_def"), **W, k=15.0,
          what="The share of those duels he won: a tackle or an aerial duel won counts as a win, being dribbled past or losing in the air as a loss.", read="A high rate on few duels can mean he avoids contact: check the volume."),
    rate("aerials90", "Aerial duels per 90", "Aerials/90", "duels", "w_aerials", per="w_min", decimals=1, hib=None, k=360.0, formula="aerial duels contested × 90 ÷ event minutes", inputs=("w_aerials", "w_min"), **W,
         what="Aerial duels he took part in anywhere on the pitch, per 90.", read="High for target men and centre-backs."),
    ratio("aerial_win", "Aerial duel win rate", "Aerial win %", "duels", "w_aerial_won", "w_aerials", formula="aerial duels won ÷ aerial duels", inputs=("w_aerial_won", "w_aerials"), **W, k=10.0,
          what="The share of all aerial duels (anywhere on the pitch) he won.", read="Matters most for centre-backs and target forwards."),
    rate("aerialwon90", "Aerial duels won per 90", "AerialsW/90", "duels", "w_aerial_won", per="w_min", decimals=1, k=360.0, formula="aerial duels won × 90 ÷ event minutes", inputs=("w_aerial_won", "w_min"), **W,
         what="Aerial duels he won, per 90."),

    # ------------------------------------------------------------------ goalkeeping
    rate("saves90", "Saves per 90", "Saves/90", "goalkeeping", "w_gk_saves", per="w_min", decimals=2, hib=None, k=720.0, roles=("GK",), formula="saves × 90 ÷ event minutes", inputs=("w_gk_saves", "w_min"), **W,
         what="Shots he saved, per 90.", read="Mostly a measure of how many shots his team faces."),
    ratio("save_pct", "Save percentage", "Save %", "goalkeeping", "w_gk_saves", "w_sot_faced", decimals=0, k=30.0, roles=("GK",), formula="saves ÷ shots on target faced", inputs=("w_gk_saves", "w_sot_faced"), **W,
          what="The share of shots on target he saved (shots on target faced = saves + goals conceded, own goals excluded).", read="Around 70% is typical; 75%+ is excellent.",
          caveat="Not adjusted for shot quality: a keeper facing easy shots will look better."),
    rate("sotfaced90", "Shots on target faced per 90", "SoT faced/90", "goalkeeping", "w_sot_faced", per="w_min", decimals=2, hib=None, k=720.0, roles=("GK",), formula="(saves + goals conceded) × 90 ÷ event minutes", inputs=("w_sot_faced", "w_min"), **W,
         what="Shots on target he had to deal with, per 90."),
    rate("ga90", "Goals conceded per 90", "GA/90", "goalkeeping", "w_ga_on", per="w_min", decimals=2, hib=False, k=720.0, roles=("GK",), formula="goals the team conceded while he was on the pitch × 90 ÷ event minutes", inputs=("w_ga_on", "w_min"), **W,
         what="Goals conceded while he was in goal, per 90.", read="Lower is better, but it reflects the whole defence.", caveat="Own goals count."),
    ratio("cs_pct", "Clean sheets", "CS %", "goalkeeping", "w_clean_sheet", "w_apps", decimals=0, k=10.0, roles=("GK",), formula="matches with 60+ minutes played and no goal conceded by the team ÷ appearances", inputs=("w_clean_sheet", "w_apps"), **W,
          what="The share of his appearances that finished without the team conceding.", read="Mostly a team measure."),
    rate("claims90", "High claims per 90", "Claims/90", "goalkeeping", "w_gk_claims", per="w_min", decimals=2, hib=None, k=720.0, roles=("GK",), formula="high claims of crosses × 90 ÷ event minutes", inputs=("w_gk_claims", "w_min"), **W,
         what="Crosses he claimed in the air, per 90.", read="Command of the box."),
    rate("punches90", "Punches per 90", "Punch/90", "goalkeeping", "w_gk_punches", per="w_min", decimals=2, hib=None, k=720.0, roles=("GK",), formula="punches × 90 ÷ event minutes", inputs=("w_gk_punches", "w_min"), **W,
         what="Times he punched the ball clear, per 90."),
    rate("sweeper90", "Sweeper actions per 90", "Sweep/90", "goalkeeping", "w_gk_sweeper", per="w_min", decimals=2, hib=None, k=720.0, roles=("GK",), formula="sweeper actions outside the box × 90 ÷ event minutes", inputs=("w_gk_sweeper", "w_min"), **W,
         what="Times he came off his line to clear up, per 90.", read="High for sweeper-keepers on teams with a high line."),
    rate("pickups90", "Pick-ups per 90", "Pickup/90", "goalkeeping", "w_gk_pickups", per="w_min", decimals=1, hib=None, k=720.0, roles=("GK",), formula="loose balls picked up × 90 ÷ event minutes", inputs=("w_gk_pickups", "w_min"), **W,
         what="Balls he gathered, per 90."),

    # ------------------------------------------------------------------ set pieces
    rate("corners90", "Corners taken per 90", "Corners/90", "setpieces", "w_corners", per="w_min", decimals=2, hib=None, k=720.0, formula="corner kicks taken × 90 ÷ event minutes", inputs=("w_corners", "w_min"), **W,
         what="Corner kicks he took, per 90."),
    rate("fktaken90", "Free kicks taken per 90", "FK/90", "setpieces", "w_fk_taken", per="w_min", decimals=2, hib=None, k=720.0, formula="free kicks played as passes × 90 ÷ event minutes", inputs=("w_fk_taken", "w_min"), **W,
         what="Free kicks he took as passes, per 90."),
    rate("fkshots90", "Direct free-kick shots per 90", "FK shots/90", "setpieces", "s_fk", decimals=2, hib=None, k=720.0, formula="shots from direct free kicks × 90 ÷ minutes", inputs=("s_fk", "minutes"), **S,
         what="Shots he took straight from a free kick, per 90."),
    rate("throwins90", "Throw-ins per 90", "Throws/90", "setpieces", "w_throwins", per="w_min", decimals=1, hib=None, k=720.0, formula="throw-ins taken × 90 ÷ event minutes", inputs=("w_throwins", "w_min"), **W,
         what="Throw-ins he took, per 90."),
    counter("pens_taken", "Penalties taken", "Pens", "setpieces", formula="Penalty kicks he took (from the stored match pages)", inputs=("s_pens",), **S, what="Penalties taken.", num="s_pens"),
    counter("pen_won", "Penalties won", "Pens won", "setpieces", formula="Penalties awarded after a foul on him", inputs=("w_pen_won",), **W, what="Penalties he won for his team.", num="w_pen_won"),

    # ------------------------------------------------------------------ discipline
    rate("yellow90", "Yellow cards per 90", "YC/90", "discipline", "yellow", hib=False, formula="yellow cards × 90 ÷ minutes", inputs=("yellow", "minutes"), **U, what="Bookings per 90.", read="Lower is better."),
    counter("yellow", "Yellow cards", "YC", "discipline", hib=False, formula="Yellow cards", inputs=("yellow",), **U, what="Yellow cards."),
    counter("red", "Red cards", "RC", "discipline", hib=False, formula="Red cards", inputs=("red",), **U, what="Red cards, including a second yellow."),
    rate("fouls90", "Fouls committed per 90", "Fouls/90", "discipline", "w_fouls", per="w_min", decimals=1, hib=False, k=360.0, formula="fouls committed × 90 ÷ event minutes", inputs=("w_fouls", "w_min"), **W,
         what="Fouls he committed, per 90.", read="Lower is better, but tackling players foul more."),
    rate("offsides90", "Offsides per 90", "Offside/90", "discipline", "w_offsides", per="w_min", decimals=2, hib=False, k=720.0, formula="times flagged offside × 90 ÷ event minutes", inputs=("w_offsides", "w_min"), **W,
         what="Times he was caught offside, per 90.", read="High for strikers who run in behind."),
    counter("pen_conceded", "Penalties conceded", "Pens con.", "discipline", hib=False, formula="Penalties awarded after a foul by him", inputs=("w_pen_conceded",), **W, what="Penalties he gave away.", num="w_pen_conceded"),

    # ------------------------------------------------------------------ impact
    rate("gfon90", "Team goals for while on pitch, per 90", "GF on/90", "impact", "w_gf_on", per="w_min", decimals=2, k=720.0, formula="goals his team scored while he was on × 90 ÷ event minutes", inputs=("w_gf_on", "w_min"), **W,
         what="Goals his team scored while he was on the pitch, per 90.", caveat="Reflects the whole team and who he plays with."),
    rate("gaon90", "Team goals against while on pitch, per 90", "GA on/90", "impact", "w_ga_on", per="w_min", decimals=2, hib=False, k=720.0, formula="goals his team conceded while he was on × 90 ÷ event minutes", inputs=("w_ga_on", "w_min"), **W,
         what="Goals his team conceded while he was on the pitch, per 90.", caveat="Reflects the whole team and who he plays with."),
    rate("gdon90", "Team goal difference while on pitch, per 90", "GD on/90", "impact", lambda f: f["w_gf_on"] - f["w_ga_on"], per="w_min", decimals=2, k=720.0, formula="(goals for − goals against while on the pitch) × 90 ÷ event minutes", inputs=("w_gf_on", "w_ga_on", "w_min"), **W,
         what="Net goals while he was on the pitch, per 90.", read="Noisy over a season: treat as context, not a verdict."),

    # ------------------------------------------------------------------ rating
    ratio("ws_rating", "WhoScored rating", "Rating", "rating", "w_rating", "w_rated", unit="rating", decimals=2, formula="mean of his match ratings (1-10)", inputs=("w_rating", "w_rated"), **W, k=5.0, min_den=1.0,
          what="WhoScored's own rating of his performances, averaged over the matches he played.", read="6.5 is average; 7.0 is a very good season; 7.5+ is exceptional.",
          caveat="Proprietary and not explained by its source. Treat as one more opinion, and it leans toward goal involvement."),
    counter("motm", "Man of the match", "MOTM", "rating", formula="Matches in which WhoScored named him man of the match", inputs=("w_motm",), **W, what="Man of the match awards.", num="w_motm"),
)

# Role scores are filled in by the dataset builder (they are averages of the player's own percentiles), so they carry no recipe here.
SCORE_METRICS: tuple[Metric, ...] = (
    Metric("output", "Role score", "Role score", "player", "scores", "score", 0, True, "understat", "base", "derived",
           "mean of his percentiles on the Understat metrics that define his role", ("npxg90", "shots90", "xgps", "xa90", "kp90", "xgchain90", "xgbuildup90"),
           "The average percentile across the Understat metrics that define a player's role (see Roles in the dictionary).",
           "A quick summary for sorting, not a verdict: open the profile to see the shape. Always available and unchanged by whether event data exists.",
           "Understat only measures attacking output, so a defender's score rests on build-up and set-piece threat."),
    Metric("score_full", "All-data score", "All-data", "player", "scores", "score", 0, True, "both", "events", "derived",
           "mean of his percentiles on the Understat and event metrics that define his role", ("output", "tklint90", "progact90", "aerial_win"),
           "The average percentile across a wider set of metrics for his role, including defending, passing and carrying from the event data.",
           "Only for players with event data. For defenders and goalkeepers it says far more than the Role score.", "Needs event data fetched for the league season."),
)

# What tells the story of each role in the role score (unchanged from the first version of the app: percentile lists, in display order)
PROFILE: dict[str, tuple[str, ...]] = {
    "ATT": ("npxg90", "shots90", "xgps", "xa90", "kp90", "xgchain90", "xgbuildup90"),
    "MID": ("xa90", "kp90", "xgchain90", "xgbuildup90", "npxg90", "shots90", "contrib90"),
    "DEF": ("xgbuildup90", "xgchain90", "xa90", "kp90", "npxg90"),
}
PROFILE_FULL: dict[str, tuple[str, ...]] = {
    "ATT": ("npxg90", "shots90", "xgps", "xa90", "kp90", "xgchain90", "takeonswon90", "touchbox90", "recatt90"),
    "MID": ("xa90", "kp90", "xgchain90", "xgbuildup90", "npxg90", "progact90", "tklint90", "recoveries90", "pass_acc"),
    "DEF": ("xgbuildup90", "progact90", "tklint90", "def_duel_win", "aerial_win", "clearances90", "pass_acc", "interceptions90"),
    "GK": ("save_pct", "ga90", "claims90", "sweeper90", "pass_acc", "long_acc"),
}
