from __future__ import annotations

"""pi-ratings: the Constantinou & Fenton (2013) dynamic rating system.

Each team carries an attack rating (alpha) and a defence rating (beta); both
update sequentially after every match in proportion to the discrepancy
between the actual score and the expected score, with draws relaxing the
updates (a draw says little about superiority). Home advantage is a shared
parameter. This is the rating family that the soccer-prediction literature
consistently ranks as the best feature set for gradient-boosted tree models
(Razali et al. 2022, Yeung et al. 2023).

Reference: Constantinou, A. & Fenton, N. (2013), "Determining the level of
ability of football teams by dynamic ratings based on the relative
discrepancies in scores between adversaries", Journal of Quantitative
Analysis in Sports 9(1).
"""

import numpy as np

HOME_ADVANTAGE = 0.46
LEARNING_RATE = 0.045
DRAW_RELAXATION = 0.55
CLIP = 1.5


def fit_pi_ratings(
    matches: list[dict],
    home_advantage: float = HOME_ADVANTAGE,
    learning_rate: float = LEARNING_RATE,
    draw_relaxation: float = DRAW_RELAXATION,
    initial: float = 1.0,
) -> dict:
    """Sequentially fit attack/defence pi-ratings over dated matches.

    `matches` rows: {"home", "away", "home_goals", "away_goals", "date"}.
    Returns {"attack", "defense", "home_advantage", "n_matches", "history":
    per-match ratings-before-update (for leakage-free feature building), and
    "predict(home, away)" returning expected goals via the Poisson link}.
    """
    ordered = sorted(matches, key=lambda m: (m.get("date") or "", m.get("home") or ""))
    attack: dict[str, float] = {}
    defense: dict[str, float] = {}
    history: list[dict] = []

    for m in ordered:
        home, away = m["home"], m["away"]
        alpha_h = attack.setdefault(home, initial)
        beta_h = defense.setdefault(home, 0.0)
        alpha_a = attack.setdefault(away, initial)
        beta_a = defense.setdefault(away, 0.0)

        history.append(
            {
                "home": home,
                "away": away,
                "date": m.get("date", ""),
                "attack_home": alpha_h,
                "defense_home": beta_h,
                "attack_away": alpha_a,
                "defense_away": beta_a,
            }
        )

        hg = int(m.get("home_goals", 0))
        ag = int(m.get("away_goals", 0))
        expected_home = max(alpha_h - beta_a + home_advantage, 0.0)
        expected_away = max(alpha_a - beta_h, 0.0)

        relaxation = 1.0 if hg != ag else draw_relaxation
        if hg > ag:
            score_effect_h = 1.0
            score_effect_a = 0.0
        elif ag > hg:
            score_effect_h = 0.0
            score_effect_a = 1.0
        else:
            score_effect_h = 0.5
            score_effect_a = 0.5

        delta_h = learning_rate * relaxation * ((hg - expected_home) + 2.0 * (score_effect_h - 0.5))
        delta_a = learning_rate * relaxation * ((ag - expected_away) + 2.0 * (score_effect_a - 0.5))

        attack[home] = float(np.clip(alpha_h + delta_h, 0.0, CLIP))
        defense[away] = float(np.clip(beta_a - 0.5 * delta_h, -CLIP, CLIP))
        attack[away] = float(np.clip(alpha_a + delta_a, 0.0, CLIP))
        defense[home] = float(np.clip(beta_h - 0.5 * delta_a, -CLIP, CLIP))

    def predict(home: str, away: str) -> dict:
        if home not in attack or away not in attack:
            raise ValueError(f"Both '{home}' and '{away}' must be teams in the fitted pi-ratings.")
        lam_h = max(attack[home] - defense[away] + home_advantage, 0.05)
        lam_a = max(attack[away] - defense[home], 0.05)
        return {"lambda_home": round(lam_h, 3), "lambda_away": round(lam_a, 3)}

    return {
        "attack": {team: round(value, 4) for team, value in sorted(attack.items(), key=lambda kv: -kv[1])},
        "defense": {team: round(value, 4) for team, value in sorted(defense.items(), key=lambda kv: kv[1])},
        "home_advantage": home_advantage,
        "n_matches": len(ordered),
        "history": history,
        "predict": predict,
    }


PI_LIMITATIONS = [
    "pi-ratings update sequentially from final scores only; no xG, no game-state.",
    "Ratings drift slowly — a manager change or key injury takes many matches to absorb.",
    "The update constants (learning rate, draw relaxation) are the published defaults, not fitted per league.",
]
