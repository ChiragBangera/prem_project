"""Typed views of Understat data.

Raw payloads are stringly typed and positionally fragile; analytics never sees
them. :mod:`app.data.normalize` turns each payload into these small dataclasses
once, at the edge, and everything downstream uses named fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TeamMatch:
    """One league match from a single team's perspective (a ``history`` row)."""

    dt: str  # "YYYY-MM-DD HH:MM:SS"
    venue: str  # "h" | "a"
    xg: float
    xga: float
    npxg: float
    npxga: float
    deep: float
    deep_allowed: float
    gf: int
    ga: int
    xpts: float
    pts: int
    result: str  # "w" | "d" | "l"
    ppda_att: float  # opponent passes allowed in our press ...
    ppda_def: float  # ... per defensive action of ours
    oppda_att: float  # same, from the opponent's press against us
    oppda_def: float
    opponent: str | None = None
    match_id: int | None = None
    matchweek: int = 0  # this team's nth league match of the season

    @property
    def date(self) -> str:
        return self.dt[:10]

    @property
    def ppda(self) -> float | None:
        return self.ppda_att / self.ppda_def if self.ppda_def > 0 else None

    @property
    def oppda(self) -> float | None:
        return self.oppda_att / self.oppda_def if self.oppda_def > 0 else None

    @property
    def xgd(self) -> float:
        return self.xg - self.xga


@dataclass(slots=True)
class Team:
    id: int
    name: str
    short: str
    history: list[TeamMatch] = field(default_factory=list)


@dataclass(slots=True)
class Fixture:
    id: int
    dt: str
    home: str
    away: str
    home_short: str
    away_short: str
    played: bool
    hg: int | None = None
    ag: int | None = None
    hxg: float | None = None
    axg: float | None = None
    forecast: tuple[float, float, float] | None = None  # Understat's own (home, draw, away)
    round: int = 0

    @property
    def date(self) -> str:
        return self.dt[:10]


@dataclass(slots=True)
class PlayerSeason:
    """A player's league totals for one season (a row of the league player table)."""

    id: int
    name: str
    teams: list[str]  # >1 when the player moved clubs mid-season
    position: str  # raw Understat string, e.g. "F M S"
    games: int
    minutes: int
    goals: int
    npg: int
    assists: int
    shots: int
    key_passes: int
    yellow: int
    red: int
    xg: float
    npxg: float
    xa: float
    xgchain: float
    xgbuildup: float
    league: str = ""
    season: int = 0

    @property
    def team(self) -> str:
        return " / ".join(self.teams)


@dataclass(slots=True)
class LeagueSeason:
    league: str
    season: int
    teams: dict[str, Team]
    players: list[PlayerSeason]
    fixtures: list[Fixture]
    warnings: list[str] = field(default_factory=list)

    @property
    def played(self) -> list[Fixture]:
        return [f for f in self.fixtures if f.played]

    @property
    def upcoming(self) -> list[Fixture]:
        return [f for f in self.fixtures if not f.played]

    @property
    def n_played(self) -> int:
        return sum(1 for f in self.fixtures if f.played)


@dataclass(slots=True)
class Shot:
    id: int
    minute: int
    xg: float
    result: str  # Goal | SavedShot | MissedShots | BlockedShot | ShotOnPost | OwnGoal
    x: float  # 0..1, 1 = the goal being attacked
    y: float  # 0..1 across the pitch
    situation: str
    shot_type: str
    last_action: str
    player: str
    player_id: int | None
    venue: str  # "h" | "a" (the shooter's side)
    season: int
    match_id: int | None
    home: str
    away: str
    date: str
    assisted_by: str | None = None

    @property
    def is_goal(self) -> bool:
        return self.result == "Goal"


@dataclass(slots=True)
class CareerSeason:
    season: int
    team: str
    position: str
    games: int
    minutes: int
    goals: int
    npg: int
    assists: int
    shots: int
    key_passes: int
    yellow: int
    red: int
    xg: float
    npxg: float
    xa: float
    xgchain: float
    xgbuildup: float


@dataclass(slots=True)
class SplitRow:
    name: str
    shots: int
    goals: int
    xg: float


@dataclass(slots=True)
class PlayerPage:
    id: int
    name: str | None
    favorite_position: str | None
    shots: list[Shot]
    career: list[CareerSeason]
    # season -> {"situations": [...], "zones": [...], "types": [...], "positions": [...]}
    splits: dict[int, dict[str, list[SplitRow]]]
    positions_minutes: dict[int, list[dict]] = field(default_factory=dict)


@dataclass(slots=True)
class RosterEntry:
    player_id: int
    player: str
    position: str
    minutes: int
    goals: int
    own_goals: int
    shots: int
    xg: float
    key_passes: int
    assists: int
    xa: float
    xgchain: float
    xgbuildup: float
    yellow: int
    red: int
    venue: str


@dataclass(slots=True)
class MatchPage:
    id: int
    shots: dict[str, list[Shot]]  # "h" | "a"
    rosters: dict[str, list[RosterEntry]]


@dataclass(slots=True)
class TeamPage:
    """Understat's team-season "statistics" block, flattened.

    ``groups[name]`` is a list of rows; each row has for/against shots, goals,
    xG so the UI can show both what a team creates and what it concedes.
    """

    team: str
    season: int
    groups: dict[str, list[dict]]
