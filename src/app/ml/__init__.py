from __future__ import annotations

"""ML layer: Dixon-Coles Poisson + Elo forecasting over Understat data.

Public surface:
- poisson: fit_dixon_coles, match_probabilities, simulate_season
- elo: fit_elo
- engine: build_match_rows, dc_input, elo_input, predict_match,
          simulate_rest_of_season, forecast_calibration
"""

from . import elo, engine, poisson
from .elo import fit_elo
from .engine import (
    build_match_rows,
    dc_input,
    elo_input,
    forecast_calibration,
    predict_match,
    simulate_rest_of_season,
)
from .poisson import fit_dixon_coles, match_probabilities, simulate_season

__all__ = [
    "elo",
    "engine",
    "poisson",
    "build_match_rows",
    "dc_input",
    "elo_input",
    "fit_dixon_coles",
    "fit_elo",
    "forecast_calibration",
    "match_probabilities",
    "predict_match",
    "simulate_rest_of_season",
    "simulate_season",
]
