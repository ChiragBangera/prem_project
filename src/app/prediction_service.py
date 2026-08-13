from __future__ import annotations

from .ml import engine
from .stat_data import UnderstatData


class PredictionService:
    """Runs the ML forecast engines over Understat data."""

    def __init__(self, client: UnderstatData | None = None):
        self.client = client or UnderstatData()

    async def predict_match(
        self,
        league_name: str = "EPL",
        season: int = 2025,
        home: str | None = None,
        away: str | None = None,
        use_xg: bool = True,
        pool_leagues: bool = True,
    ) -> dict:
        if not home or not away:
            raise ValueError("Both home and away team names are required.")
        return await engine.predict_match(
            self.client, league_name, season, home.strip(), away.strip(), use_xg=use_xg,
            pool_leagues=pool_leagues,
        )

    async def simulate_season(
        self,
        league_name: str = "EPL",
        season: int = 2025,
        n_sims: int = 2000,
        use_xg: bool = True,
    ) -> dict:
        return await engine.simulate_rest_of_season(
            self.client, league_name, season, n_sims=max(100, min(n_sims, 20000)), use_xg=use_xg
        )

    async def calibrate(
        self,
        league_name: str = "EPL",
        season: int = 2025,
        use_xg: bool = True,
        min_train: int = 30,
        step: int = 5,
        pool_leagues: bool = True,
    ) -> dict:
        return await engine.forecast_calibration(
            self.client, league_name, season, use_xg=use_xg, min_train=min_train, step=step,
            pool_leagues=pool_leagues,
        )
