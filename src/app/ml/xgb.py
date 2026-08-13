from __future__ import annotations

"""XGBoost hybrids for match forecasting (native Booster API — no sklearn).

Three variants, all trained on the leakage-free feature store:
- goals-poisson: regress home/away GOALS with `count:poisson` objective, then
  feed the expected goals through the Dixon-Coles scoreline machinery
  (Groll et al. 2018/2019 "hybrid" pattern) — full scoreline distributions.
- xg-regression: regress home/away xG with squared error — the denoised twin.
- outcome-softmax: direct W/D/L classification (multiclass logloss).

Feature importance is gain-based and exposed for the explainability view.
"""

import numpy as np
import xgboost as xgb

N_ESTIMATORS = 250

BASE_PARAMS = {
    "max_depth": 4,
    "eta": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "reg_lambda": 1.0,
    "tree_method": "hist",
    "nthread": 2,
    "verbosity": 0,
}


def matrix(features: dict[str, np.ndarray], names: list[str], rows_mask: np.ndarray | None = None) -> np.ndarray:
    cols = [features[name] for name in names]
    stacked = np.column_stack(cols)
    if rows_mask is None:
        return stacked
    return stacked[rows_mask]


def _train(X: np.ndarray, y: np.ndarray, objective: str, extra: dict | None = None):
    dtrain = xgb.DMatrix(X, label=y.astype(float))
    params = {**BASE_PARAMS, "objective": objective, **(extra or {})}
    return xgb.train(params, dtrain, num_boost_round=N_ESTIMATORS)


def train_poisson(X_train: np.ndarray, home_goals: np.ndarray, away_goals: np.ndarray) -> tuple:
    """Two count:poisson boosters (home and away expected goals)."""
    model_h = _train(X_train, home_goals, "count:poisson")
    model_a = _train(X_train, away_goals, "count:poisson")
    return model_h, model_a


def train_xg(X_train: np.ndarray, home_xg: np.ndarray, away_xg: np.ndarray) -> tuple:
    """Two squared-error boosters on xG (denoised targets)."""
    model_h = _train(X_train, home_xg, "reg:squarederror")
    model_a = _train(X_train, away_xg, "reg:squarederror")
    return model_h, model_a


def train_softmax(X_train: np.ndarray, outcomes: np.ndarray):
    """Multiclass W/D/L booster (0 = home, 1 = draw, 2 = away)."""
    return _train(X_train, outcomes, "multi:softprob", extra={"num_class": 3})


def predict_lambdas(models: tuple, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    home_model, away_model = models
    dmatrix = xgb.DMatrix(X)
    lam_h = np.clip(home_model.predict(dmatrix), 1e-6, None)
    lam_a = np.clip(away_model.predict(dmatrix), 1e-6, None)
    return lam_h, lam_a


def predict_softmax(model, X: np.ndarray) -> np.ndarray:
    return model.predict(xgb.DMatrix(X))


def importance(model, names: list[str], top_k: int = 20) -> list[dict]:
    gains = model.get_score(importance_type="gain")
    total = sum(gains.values()) or 1.0
    feature_map = {f"f{i}": names[i] for i in range(len(names))}
    entries = [
        {
            "feature": feature_map.get(key, key),
            "importance": round(value / total, 4),
        }
        for key, value in gains.items()
    ]
    entries.sort(key=lambda e: -e["importance"])
    return entries[:top_k]


XGB_LIMITATIONS = [
    "Tree models on one league-season see at most a few hundred training matches; single-season fits are noisy.",
    "Draws are the hardest class everywhere in the literature; softmax accuracy is not the whole story.",
    "No lineup or injury feed: the model sees availability only through the key-creator minutes proxy.",
    "Feature importance (gain) reflects what the model used, not causal effects.",
]
