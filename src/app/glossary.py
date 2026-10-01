"""Plain-language definitions for every term the app uses (shown as tooltips and on the Method page)."""

from __future__ import annotations

GROUPS: list[dict] = [
    {
        "group": "Chances",
        "blurb": "Expected-goals metrics measure the quality of chances, not just whether they went in.",
        "entries": [
            ("xg", "xG (expected goals)", "How likely a shot is to score, from 0 to 1, based on where and how it was taken.",
             "Add up a player's or team's shot xG and you get the goals they 'should' have scored from those chances. It removes finishing luck from the picture."),
            ("npxg", "npxG (non-penalty xG)", "xG without penalties.",
             "A penalty is worth about 0.76 xG in a single shot, which inflates totals for penalty takers. npxG is the cleaner measure of open-play threat."),
            ("xa", "xA (expected assists)", "The xG of the shots a player's passes created.",
             "Assist quality without depending on the finisher. A creator's xA barely changes if a team-mate misses; his assist count does."),
            ("xgchain", "xGChain", "The total xG of every possession a player took part in that ended in a shot.",
             "A measure of involvement: how much of the team's attacking flow runs through him, counting his own shots and passes."),
            ("xgbuildup", "xGBuildup", "xGChain without the player's own shots and key passes.",
             "Isolates the earlier, deeper involvement. High build-up with modest chain means he starts attacks rather than finishes them."),
            ("xgps", "xG per shot", "Average quality of each shot.", "High means good positions (or penalties); low means speculative shooting."),
            ("big_chance", "Big chance", "A shot worth 0.30 xG or more.", "Roughly a one-in-three chance or better. Understat has no official flag, so this app uses 0.30."),
            ("g_xg", "Goals minus xG", "Goals scored above or below what the chances were worth.",
             "Positive means scoring more than expected. Over a season most of it is luck, which is why the app always shows how significant it is."),
            ("luck_z", "Significance (z)", "How surprising a goal tally is given the chances: about ±1 is ordinary, beyond ±2 is rare.",
             "For a player with shot data it comes from the exact distribution of goals over his shots. A +2.4 means a run this good happens about 1 time in 100 on those chances."),
        ],
    },
    {
        "group": "Rates and samples",
        "blurb": "Stats mean little without knowing how much football stands behind them.",
        "entries": [
            ("per90", "Per 90", "A stat scaled to a full match of 90 minutes.", "The fair way to compare players with different minutes."),
            ("sample", "Sample size", "Minutes played. Under about 450 minutes, per-90 rates swing wildly.", "The app flags small samples and treats them cautiously when ranking."),
            ("shrinkage", "Small-sample adjustment", "Rankings pull rates toward the role average in proportion to how little a player has played.",
             "A substitute with one lucky cameo does not top a leaderboard. The number you see in a table is the raw rate; only the ranking uses the adjusted one."),
            ("percentile", "Percentile", "The share of same-role peers a player is above on a metric.", "50 is average, 90 means better than 90% of comparable players. Peers must have played enough minutes to count."),
            ("pool", "Peer pool", "The players a percentile is measured against: same role group, above a minutes threshold.",
             "The threshold scales with how far into the season it is (about a quarter of the minutes a full-time player could have played)."),
            ("output", "Role score", "The average percentile across the metrics that define a player's role.", "A quick summary for sorting, not a verdict: open the profile to see the shape."),
            ("minutes_share", "Share of team minutes", "Minutes played as a share of everything his team has played.", "Above 80% is a fixture; below 40% is rotation or bench."),
        ],
    },
    {
        "group": "Passing and defending (event data)",
        "blurb": "Optional extras from WhoScored that Understat does not have. They exist only for the league seasons you have fetched with `prem events sync`.",
        "entries": [
            ("events", "Event data", "Every pass, tackle, duel and interception, fetched from WhoScored on request and kept on this computer.",
             "Only players the app can match safely to Understat by name and club are included, so some are left out rather than guessed. Playing time is scaled so a full match is 90 minutes."),
            ("fwd_pass_ratio", "Forward pass ratio", "The share of open-play passes that move the ball at least 5% of the pitch (about 5 metres) toward goal.",
             "How direct a player's passing is. Compare within a role: centre-backs and holding midfielders naturally pass less forward than attackers."),
            ("prog_passes", "Progressive passes", "Completed passes that move the ball at least 10% of the pitch (about 10 metres) toward goal and end in the attacking 60% of the pitch.",
             "Who moves the team up the pitch with the ball. Compare with xGBuildup, which measures involvement in possessions that end in shots."),
            ("restarts", "Open-play passes", "Passes without throw-ins, goal kicks, corners, keeper throws and crosses.", "Restarts are not play, and crosses are chance creation, so they would distort passing ratios."),
            ("def_duel", "Defensive duel", "A tackle, a challenge (the defender is dribbled past) or an aerial duel in which he was the defending side. A tackle or a won aerial is a win; being dribbled past or losing in the air is a loss.",
             "This is the app's own definition: the source has no event with that name. A busy defender may simply play for a team that defends a lot, so read the win rate and the volume together."),
            ("tackle", "Tackle", "A tackle in which the defender took the ball off an opponent.", "Being beaten by a dribble is not a tackle. It counts as a lost duel."),
            ("interception", "Interception", "A pass the defender read and cut out.", "Positioning and anticipation rather than one-on-one defending."),
            ("recovery", "Ball recovery", "Winning back a loose or contested ball.", "A measure of work rate off the ball."),
        ],
    },
    {
        "group": "Roles and scouting",
        "blurb": "Understat lists broad positions only. Here is how the app deals with that.",
        "entries": [
            ("role_group", "Role group", "Attacker, midfielder, defender or goalkeeper: the peer group for percentiles.",
             "When Understat lists several roles for a player, the app assigns the group his own numbers most resemble, and marks it as inferred. If his favourite position is known, that wins."),
            ("inferred", "Inferred role", "The group was worked out from his per-90 profile because Understat lists more than one role for him.", "Usually right; check the profile when it matters."),
            ("archetype", "Archetype tags", "Labels such as Poacher or Deep progressor, awarded by simple rules on percentiles.", "Each tag says which numbers earned it. They are descriptions, not black-box classifications."),
            ("similarity", "Similarity", "100 minus the average percentile gap between two players across their role's key metrics.",
             "A similarity of 90 means that on average the two are within 10 percentile points on every metric."),
            ("age", "Age", "From the exact date of birth on the club's squad list (ESPN), or, for players a list leaves out, from Wikidata (CC0) matched by name and club.", "Blank when there is no unambiguous match. The app never guesses, and the Scout age filter hides players whose age is blank unless you ask for them."),
            ("shortlist", "Shortlist", "Players you have starred, with your own notes.", "Stored in the local database next to the cached data."),
        ],
    },
    {
        "group": "Team style and table",
        "blurb": "What a team creates and concedes, beyond points.",
        "entries": [
            ("xpts", "xPTS (expected points)", "The points a team would have earned on average from the chances created and conceded in each match.",
             "Each match's shots are replayed thousands of times to get win/draw/loss probabilities. Summed over a season, xPTS is a fairer table than the real one."),
            ("xpts_gap", "Points minus xPTS", "Actual points minus expected points.", "Large positive gaps usually shrink (results outran performances); large negative gaps usually recover."),
            ("xgd", "xG difference", "xG created minus xG conceded, usually per game.", "The best single quality measure: it predicts future results better than the table does."),
            ("ppda", "PPDA", "Opponent passes allowed per defensive action in their build-up: how hard a team presses.", "Lower is more intense. Around 7 is a very high press; 14 or more is a low block."),
            ("oppda", "OPPDA", "PPDA measured the other way: how hard opponents press this team.", "Higher means opponents let the team play."),
            ("deep", "Deep completions", "Passes completed within about 20 yards of the opponent's goal.", "A proxy for territory and penetration."),
            ("form", "Rolling form", "A five-match rolling average of xG difference.", "Underlying form moves before results do, and is far less noisy than a run of scorelines."),
            ("sos", "Strength of schedule", "How strong recent or coming opponents are, by their season xG difference per game.", "A team's run-in can be easier or harder than its record so far suggests."),
            ("deserved", "Deserved result", "How often each result would happen if the same chances were replayed.",
             "Computed exactly from every shot's xG. A team that wins with a 9% chance won against the run of play."),
        ],
    },
    {
        "group": "Forecasts",
        "blurb": "How match and season predictions are made, and how they are checked.",
        "entries": [
            ("ratings", "Ratings model", "Each team gets an attack and a defence strength fitted to match xG, with a home-advantage term.",
             "Recent matches count more, last season's matches carry over with decay, and ratings are shrunk toward the league average when evidence is thin (early season, newly promoted teams)."),
            ("elo", "Elo", "A results-only rating: teams gain and lose points from results, more for bigger margins.", "An independent cross-check that ignores chances entirely."),
            ("blend", "Blended forecast", "70% ratings model, 30% Elo.", "Two different views usually beat either alone. The scoreline grid is rescaled so it agrees with the blended win/draw/loss."),
            ("rho", "Low-score correlation (rho)", "A small correction so draws and 1-0s are not under-predicted (Dixon and Coles, 1997).", "Fitted on real goals, not xG, because it only exists in whole-number scorelines."),
            ("montecarlo", "Season simulation", "The rest of the season is played thousands of times from the fitted model.", "Averages give expected points; the spread gives title, top-four and relegation probabilities."),
            ("brier", "Brier score", "Squared error of the three probabilities against what happened (lower is better).", "Always-predict-the-base-rate scores about 0.65; good models score around 0.58 to 0.60."),
            ("rps", "Ranked probability score", "Like Brier but respects that a win is 'closer' to a draw than to a loss (lower is better).", "The standard proper score for football forecasts."),
            ("calibration", "Walk-forward calibration", "Refit the models as the season progresses and score every prediction before the match is played.", "The honest test: only information available at the time is used."),
            ("reliability", "Reliability", "Among predictions of '30%', did about 30% happen?", "Points on the diagonal mean the probabilities can be taken at face value."),
        ],
    },
    {
        "group": "Data and limits",
        "blurb": "What the source can and cannot tell you.",
        "entries": [
            ("source", "Understat", "The source of all match, shot and player data.", "Free, public, covering the top five European leagues from 2014/15. Not affiliated with this app."),
            ("no_defence", "No defensive data in Understat", "Understat has no tackles, interceptions, pressures or goalkeeper metrics.",
             "Defenders are judged on build-up and set-piece threat; goalkeepers cannot be assessed at all. Take defender percentiles as partial. The optional event data adds duels, tackles, interceptions and passing for the seasons you fetch, but it is still not a full picture of defending."),
            ("coords", "Shot coordinates", "The position where the shot ended up being taken from, on a 0-1 pitch.", "There is no ball path, goalkeeper position or pass origin."),
            ("cache", "Local cache", "Everything fetched is stored on this machine.", "Finished seasons never need refreshing; the current season refreshes automatically around matchdays."),
        ],
    },
]


def glossary_payload() -> dict:
    return {
        "groups": [
            {
                "group": g["group"],
                "blurb": g["blurb"],
                "entries": [{"key": k, "term": t, "short": s, "long": l} for k, t, s, l in g["entries"]],
            }
            for g in GROUPS
        ]
    }


def flat() -> dict[str, dict]:
    return {k: {"term": t, "short": s, "long": l} for g in GROUPS for k, t, s, l in g["entries"]}
