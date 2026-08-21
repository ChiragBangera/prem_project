from __future__ import annotations

"""Metric glossary: every metric, derived metric, and projection the product
surfaces, with a plain-language definition and a "how to read it" line.

The dashboard renders these as hover tooltips / an Info tab; the API exposes
them at GET /api/v1/glossary so any client can explain what it is showing.
"""


GLOSSARY_GROUPS: list[dict] = [
    {
        "group": "Basics & Table Columns",
        "entries": [
            ("rank", "№ (Rank)", "League table position based on Points and Goal Difference.",
             "Standard championship standing. Top 4 qualify for Champions League; bottom 3 face relegation."),
            ("team", "Team", "Club name.",
             "Click any team name to drill down into in-depth tactical team analytics."),
            ("matches", "M (Matches)", "Completed league matches played.",
             "Total number of fixtures played in the selected season or date window."),
            ("wins", "W (Wins)", "Matches won.",
             "Each win awards 3 championship points."),
            ("draws", "D (Draws)", "Matches drawn / tied.",
             "Each draw awards 1 championship point."),
            ("losses", "L (Losses)", "Matches lost.",
             "Zero points awarded."),
            ("goals", "G (Goals)", "Actual goals scored in league matches.",
             "A count of what happened, not what should have happened. Compare against xG to see finishing luck."),
            ("ga", "GA (Goals Against)", "Actual goals conceded in league matches.",
             "The realized defensive count. Compare against xGA to see defensive luck or goalkeeper quality."),
            ("gd", "GD (Goal Difference)", "Goals scored minus goals conceded (G − GA).",
             "First tiebreaker in standard league standings."),
            ("pts", "PTS (Points)", "Total actual points earned: (W × 3) + D.",
             "The official table points. Compare with xPTS to isolate results variance from process."),
            ("assists", "Assists (A)", "Passes that directly led to a goal.",
             "Assists depend on the finisher converting the chance; xA removes that dependency."),
            ("shots", "Shots", "Total shot attempts by the player or team.",
             "Volume without quality: pair with xG/shot to see if shots are high- or low-value."),
            ("key_passes", "Key passes", "Passes that directly created a shot.",
             "A creation-volume metric. Understat counts the pass before the shot as key."),
            ("minutes", "Minutes", "Minutes played in league matches.",
             "The denominator for all per-90 metrics; use it to judge sample size."),
            ("games", "Games", "League appearances.",
             "Appearances can include short cameos; minutes is the better workload measure."),
            ("cards", "Yellow / red cards", "Bookings received.",
             "Style and discipline signal; red cards also cost the team future availability."),
        ],
    },
    {
        "group": "Expected goals (xG) family",
        "entries": [
            ("xG", "xG (expected goals)", "Probability-weighted shot quality: each shot is worth the chance a similar shot goes in (0–1), summed.",
             "The core 'how good were the chances' measure. High xG with low goals = unlucky finishing (or great goalkeeping)."),
            ("xGA", "xGA (expected goals against)", "The xG value of the chances a team conceded.",
             "The defensive mirror of xG; xG − xGA per game is the best single quality measure."),
            ("big_chance", "Big chance", "A shot with xG ≥ 0.20 — roughly a 1-in-5 or better scoring opportunity.",
             "Big-chance counts separate genuine openings from speculative volume."),
            ("npxG", "NP xG (non-penalty xG)", "xG excluding penalties.",
             "Removes the penalty kick distorting effect; fairer for open-play comparison."),
            ("npg", "Non-penalty goals", "Goals scored excluding penalties.",
             "The realised counterpart of npxG."),
            ("xG_chain", "xGChain", "Total xG of every possession the player participated in (their own shot or the build-up).",
             "A participation metric: how much attacking flow the player touches. Penalises nothing, rewards involvement."),
            ("xG_buildup", "xGBuildup", "xGChain minus the player's own shots and key passes — the earlier build-up xG.",
             "Isolates deep progress: high buildup = the player starts attacks; high chain + low buildup = finishes them."),
            ("xA", "xA (expected assists)", "The xG of the shots a player's passes created.",
             "Assist quality independent of the finisher; a better vision metric than raw assists."),
            ("xG_per_shot", "xG per shot", "Average shot quality: total xG divided by shots.",
             "High = shoots from good locations; low = volume from range. A style fingerprint."),
        ],
    },
    {
        "group": "Derived per-90 metrics",
        "entries": [
            ("per90", "Per 90", "Any counting stat divided by minutes and multiplied by 90 — a rate per full match.",
             "The honest way to compare players or seasons with different minute loads."),
            ("goal_involvement", "npxG + xA (goal involvement)", "Non-penalty xG plus expected assists — the xG value of everything the player creates and takes.",
             "One number for attacking output. League-leading values are ~0.8+ per 90."),
            ("conversion", "Conversion rate", "Goals divided by shots.",
             "Realised finishing efficiency. Small-sample noisy; xG per shot is the stable cousin."),
        ],
    },
    {
        "group": "Finishing & performance vs expectation",
        "entries": [
            ("g_minus_xg", "G − xG (finishing overperformance)", "Goals scored minus xG.",
             "Positive = scored more than chance quality suggests. Mostly luck + goalkeeping + composure; regresses to the mean."),
            ("finishing_ci", "95% confidence interval", "The range around G − xG within which the true overperformance lies with 95% confidence.",
             "If the interval includes 0, the player is statistically indistinguishable from expectation."),
            ("percentile", "Percentile", "The share of same-position peers (same league/season) the player beats on a metric.",
             "50 = league average; 90 = top 10%. Always relative to the chosen season's pool."),
            ("radar", "Radar / pizza chart", "Percentile profile across several metrics plotted on one chart.",
             "The shape, not the size, is the style fingerprint. Axes are independent percentiles."),
            ("similar_players", "Similar players", "Nearest neighbours by cosine similarity over a standardised metric vector (league-wide pool).",
             "Statistically alike players from any team — a scouting-style shortcut, not an eye-test verdict."),
        ],
    },
    {
        "group": "Team style metrics",
        "entries": [
            ("position_trend", "Position trend", "League rank, points and xPTS after each matchday, rebuilt from all teams' histories.",
             "The table was a journey: early leaders vs late risers; rank after every one of the team's matches."),
            ("half_split", "First vs second half", "The season split in two: points and xG per game in each half.",
             "Positive delta = improving team; negative = fading. Small samples, so read with the schedule in mind."),
            ("luck_curve", "Luck curve", "Cumulative goals minus xG across the season.",
             "Steady climb = results kept outrunning chances; a dive = chances went unrewarded for a stretch."),
            ("strength_of_schedule", "Strength of schedule", "Record against opponents with positive vs negative season npxGD per game.",
             "The flat-track-bully check: does the team beat weak sides and fold against strong ones?"),
            ("team_press", "Team press (PPDA)", "The team's season PPDA: opponent passes allowed per defensive action.",
             "Lower = more intense press. Understat has no per-player pressing counts, so this is the honest pressing context."),
            ("age", "Age", "Player age from Wikidata's date of birth (CC0), not Understat.",
             "Shown as '—' when Wikidata has no unambiguous entry for the name."),
            ("regain_xg", "Chances after possession regains", "The player's shots and xG from situations where the previous action was a BallRecovery, Dispossessed, BlockedPass or Rebound.",
             "Press reward, not pressing activity: it measures chances finished after the team won the ball back."),
            ("ppda", "PPDA (passes per defensive action)", "Opponent passes allowed per defensive action (tackle/interception/foul) in the attacking 60% of the pitch.",
             "Lower = more intense press. Understat's proxy — no pressure-event data."),
            ("oppda", "OPPDA", "PPDA faced: how much pressing the team's opponents apply.",
             "Shows whether opponents press the team hard — useful for style matchups."),
            ("npxga", "NPxGA (Non-Penalty xGA)", "Expected goals against excluding opponent penalty kicks.",
             "Cleanest measure of pure open-play and set-piece defensive concession."),
            ("dc", "DC (Deep Completions)", "Non-cross passes completed within 20 yards of the opponent's goal.",
             "Final-third danger: measures how regularly a team penetrates the penalty box."),
            ("odc", "ODC (Opponent Deep Completions)", "Opponent non-cross passes completed within 20 yards of your goal.",
             "Defensive box security: measures how often opponents breach the penalty area."),
            ("xpts_gap", "PTS − xPTS (Points Gap)", "Actual league points minus Expected Points (xPTS).",
             "Quantifies 'table lies' and outcome variance: positive values show overperformance; negative show underperformance."),
            ("g_minus_xg", "G − xG (Finishing Variance)", "Goals scored minus expected goals (xG).",
             "Finishing overperformance: mostly variance and goalkeeping opposition; regresses to zero over long samples."),
            ("xga_minus_ga", "xGA − GA (Defensive Overperformance)", "Expected goals against minus actual goals conceded.",
             "Defensive overperformance: mixes goalkeeper save quality, opponent finishing wastefulness, and luck."),
            ("form_momentum", "Form momentum", "Rolling 5-match xG difference (xGD) trajectory.",
             "Short-term quality trend, less noisy than results-based form."),
        ],
    },
    {
        "group": "Prediction models",
        "entries": [
            ("dixon_coles", "Dixon-Coles model", "A bivariate Poisson model (Dixon & Coles 1997) that fits each team's attack and defence strength from match xG, with a low-score correction (rho) and home advantage.",
             "The engine behind scoreline probabilities. Fit on xG here, so it predicts underlying quality rather than lucky results."),
            ("elo", "Elo ratings", "A sequential rating system: each result transfers points between teams based on expectation.",
             "A pure results-based cross-check; it sees no xG and no scorelines."),
            ("pi_ratings", "pi-ratings", "Constantinou & Fenton's dynamic rating system: attack/defence ratings updated per match by the discrepancy between actual and expected scores, with draws relaxed.",
             "The rating family the research literature ranks as the best feature set for gradient-boosted models."),
            ("xgboost", "XGBoost hybrid", "Gradient-boosted trees trained on pre-match features (ratings, rolling xG form, PPDA, rest, H2H, Understat forecast, availability proxy); the goals variant regresses expected goals and converts them through the scoreline machinery.",
             "The literature's strongest goals-only recipe (Hubáček et al. 2019; Razali et al. 2022). Features are strictly pre-match — no leakage."),
            ("feature_importance", "Feature importance", "Share of total tree-split gain each feature contributed (XGBoost gain-based).",
             "What the model leaned on, not a causal claim. Ratings and Understat forecast usually dominate."),
            ("pooled_training", "Pooled training", "Training the model on all four leagues' matches of the same season, testing only on the target league.",
             "More training data per season — the recipe behind the best published accuracy (55.8%)."),
            ("lambda", "λ (expected goals)", "The model's predicted goals for each side in a match.",
             "λ_home 1.4 vs λ_away 0.9 → the model expects roughly 1.4–0.9. These ARE the goal projections."),
            ("rho", "ρ (rho)", "The Dixon-Coles low-score correction: adjusts the probability of 0-0, 1-0, 0-1, 1-1.",
             "Typically slightly negative because draws/1-0s happen a bit more than independent Poissons predict."),
            ("home_advantage", "Home advantage", "The fitted boost (in expected-goals log-scale, or Elo points) a team gets at home.",
             "~0.2–0.35 goals in top leagues. Model-fit from the season's data, not assumed."),
            ("most_likely_score", "Most likely scoreline", "The single scoreline with the highest probability in the model.",
             "Often only ~10–15% likely — it is the mode, not a forecast of certainty."),
            ("scoreline_matrix", "Scoreline matrix", "Full 0–8 by 0–8 probability grid for every possible score.",
             "The source of over/under and clean-sheet probabilities."),
            ("over_under", "Over / under 2.5 goals", "Probability the match total goals exceed (or stay under) the line, from the scoreline matrix.",
             "Total-goals market probabilities — model-implied, not bookmaker odds."),
            ("btts", "Both teams to score", "Probability both sides score at least once.",
             "High when both attacks are strong and both defences weak."),
            ("clean_sheet", "Clean sheet probability", "Chance a team concedes zero goals.",
             "Reads off the scoreline matrix for the specific matchup."),
            ("ensemble", "Ensemble", "A blend of Dixon-Coles and Elo probabilities, weighted to minimise Brier score on a holdout of the season.",
             "Two different lenses (chance quality vs results) usually beat either alone."),
            ("venue_factor", "Team-specific venue effect", "Each team's own home/away xG split vs the league-average split, applied as an adjustment to predicted goals.",
             "Some teams have stronger (or weaker) home identities than the league average."),
            ("form_overlay", "Recent-form overlay", "A small adjustment from the last 5 matches' xG vs the season baseline.",
             "Captures hot/cold streaks; deliberately damped so noise doesn't dominate."),
            ("availability", "Availability sensitivity", "How a team's xG per game changes when its top creators (by xGChain) are absent vs present, and what the prediction becomes in each scenario.",
             "Injuries are unknowable in advance — this shows the conditional downside honestly."),
        ],
    },
    {
        "group": "Season projections",
        "entries": [
            ("monte_carlo", "Monte-Carlo simulation", "Simulating the remaining fixtures thousands of times using the fitted model and tallying outcomes.",
             "Each simulation is one possible future; the average is the projection, the spread is the uncertainty."),
            ("expected_points", "Expected points (projection)", "Average final points across all simulations.",
             "The model's season-end projection, including current points banked."),
            ("p_top_4", "Top-4 probability", "Share of simulations in which the team finishes 1st–4th.",
             "Champions League qualification likelihood under the model."),
            ("p_relegation", "Relegation probability", "Share of simulations finishing in the bottom three.",
             "Bottom-three cutoff differs per league; the model uses each league's size."),
            ("champion", "Champion probability", "Share of simulations finishing 1st.",
             "The title race in one number."),
            ("position_distribution", "Position distribution", "For each finishing position, the share of simulations the team lands there.",
             "The full uncertainty picture, not just the most likely slot."),
            ("season_end_goals", "Season-end goal projection", "Current goals plus average simulated goals in remaining fixtures.",
             "A team-level 'goals for' projection; player-level versions scale by each player's share of team npxG."),
            ("top_scorer_projection", "Top scorer projection", "Current goals plus projected additions from remaining fixtures, using each player's npxG/90 and typical minutes.",
             "A rough, minutes-assuming projection — injuries and role changes will break it."),
        ],
    },
    {
        "group": "Calibration & honesty",
        "entries": [
            ("calibration", "Walk-forward calibration", "Refit the model repeatedly as the season progresses and score every prediction out-of-sample.",
             "The honest test: only predictions made before each match count."),
            ("brier", "Brier score", "Mean squared error of probability forecasts (0 = perfect, 1 = perfectly wrong).",
             "Lower is better; a coin-flip baseline is ~0.65. The number to compare models with."),
            ("log_loss", "Log loss", "Negative log of the probability assigned to the actual outcome, averaged.",
             "Punishes confident wrongness heavily. Lower is better."),
            ("rps", "RPS (ranked probability score)", "Squared error between cumulative predicted and observed outcome probabilities over the ordered home-draw-away categories.",
             "The literature's standard proper scoring rule for football (lower is better); punishes near-misses less than accuracy does."),
            ("accuracy", "Prediction accuracy", "Share of predictions where the model's most likely outcome happened.",
             "The intuitive but weakest measure — a 60%-confident correct call and a 33%-confident correct call both count."),
            ("baseline", "Naive baseline", "The historical home/draw/away frequency of the training window.",
             "If a model can't beat this, it adds nothing. Shown on every calibration."),
            ("limitations", "Limitations", "What a metric cannot tell you, stated with every report.",
             "Read these before betting on anything: no lineups, no game-state, no tracking data."),
        ],
    },
    {
        "group": "Shot profile",
        "entries": [
            ("situations", "Situations", "How a player's shots split across OpenPlay, SetPiece, FromCorner, CounterAttack, Penalty, DirectFreekick.",
             "Penalty-heavy xG inflates totals; the split shows what's reproducible from open play."),
            ("shot_zones", "Shot zones", "Shots from the six-yard box, penalty area, and outside the box.",
             "Where the player generates chances — poacher profile vs range shooter."),
            ("shot_types", "Shot types", "Left foot / right foot / head split of shots and xG.",
             "Body-part balance: one-dimensional finishers are easier to defend."),
            ("starter_sub", "Starter vs sub minutes", "Minutes played as a starter vs off the bench, per season.",
             "Role evolution: declining starters often move to impact-sub roles before minutes drop."),
        ],
    },
]


def glossary_entries() -> list[dict]:
    entries = []
    for group in GLOSSARY_GROUPS:
        for key, label, short, long in group["entries"]:
            entries.append(
                {
                    "key": key,
                    "group": group["group"],
                    "label": label,
                    "short": short,
                    "long": long,
                }
            )
    return entries


def glossary_response() -> dict:
    by_key = {entry["key"]: entry for entry in glossary_entries()}
    return {
        "groups": [
            {
                "group": group["group"],
                "entries": [
                    {"key": key, "label": label, "short": short, "long": long}
                    for key, label, short, long in group["entries"]
                ],
            }
            for group in GLOSSARY_GROUPS
        ],
        "by_key": by_key,
        "feature_labels": _feature_labels(),
    }


def _feature_labels() -> dict:
    from app.ml.features import FEATURE_EXPLANATIONS

    return {key: label for key, (label, _) in FEATURE_EXPLANATIONS.items()}
