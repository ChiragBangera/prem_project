"""The persistent part of the demo world: clubs, players, and how they evolve.

Real club names (facts), *fictional* players. A world is deterministic given its
seed, so every run - and every test - sees the same players and seasons.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from .names import NameFactory

FIRST_DEMO_SEASON = 2019

# (name, short, quality tier 1 = strongest ... 5 = weakest)
CLUBS: dict[str, list[tuple[str, str, int]]] = {
    "EPL": [
        ("Arsenal", "ARS", 1), ("Manchester City", "MCI", 1), ("Liverpool", "LIV", 1),
        ("Chelsea", "CHE", 2), ("Tottenham", "TOT", 2), ("Newcastle United", "NEW", 2),
        ("Manchester United", "MUN", 2), ("Aston Villa", "AVL", 2), ("Brighton", "BHA", 3),
        ("West Ham", "WHU", 3), ("Crystal Palace", "CRY", 3), ("Fulham", "FUL", 3),
        ("Brentford", "BRE", 3), ("Bournemouth", "BOU", 3), ("Everton", "EVE", 3),
        ("Wolverhampton Wanderers", "WOL", 4), ("Nottingham Forest", "NFO", 4), ("Leeds", "LEE", 4),
        ("Burnley", "BUR", 5), ("Sunderland", "SUN", 5),
    ],
    "La_liga": [
        ("Real Madrid", "RMA", 1), ("Barcelona", "BAR", 1), ("Atletico Madrid", "ATM", 1),
        ("Athletic Club", "ATH", 2), ("Real Sociedad", "RSO", 2), ("Villarreal", "VIL", 2),
        ("Real Betis", "BET", 2), ("Sevilla", "SEV", 3), ("Valencia", "VAL", 3), ("Girona", "GIR", 3),
        ("Celta Vigo", "CEL", 3), ("Osasuna", "OSA", 3), ("Getafe", "GET", 3), ("Rayo Vallecano", "RAY", 4),
        ("Mallorca", "MAL", 4), ("Alaves", "ALA", 4), ("Espanyol", "ESP", 4), ("Elche", "ELC", 5),
        ("Levante", "LEV", 5), ("Oviedo", "OVI", 5),
    ],
    "Bundesliga": [
        ("Bayern Munich", "BAY", 1), ("Bayer Leverkusen", "LEV", 1), ("Borussia Dortmund", "BVB", 2),
        ("RB Leipzig", "RBL", 2), ("VfB Stuttgart", "STU", 2), ("Eintracht Frankfurt", "SGE", 3),
        ("Freiburg", "SCF", 3), ("Hoffenheim", "TSG", 3), ("Wolfsburg", "WOB", 3), ("Werder Bremen", "SVW", 3),
        ("Mainz 05", "M05", 4), ("Borussia M.Gladbach", "BMG", 4), ("Augsburg", "FCA", 4),
        ("Union Berlin", "FCU", 4), ("FC Cologne", "KOE", 4), ("Hamburger SV", "HSV", 5),
        ("St. Pauli", "STP", 5), ("Heidenheim", "HDH", 5),
    ],
    "Serie_A": [
        ("Inter", "INT", 1), ("Napoli", "NAP", 1), ("Juventus", "JUV", 1), ("AC Milan", "MIL", 2),
        ("Atalanta", "ATA", 2), ("Roma", "ROM", 2), ("Lazio", "LAZ", 2), ("Bologna", "BOL", 3),
        ("Fiorentina", "FIO", 3), ("Torino", "TOR", 3), ("Como", "COM", 3), ("Genoa", "GEN", 4),
        ("Udinese", "UDI", 4), ("Sassuolo", "SAS", 4), ("Cagliari", "CAG", 4), ("Parma Calcio 1913", "PAR", 4),
        ("Lecce", "LEC", 5), ("Hellas Verona", "VER", 5), ("Cremonese", "CRE", 5), ("Pisa", "PIS", 5),
    ],
    "Ligue_1": [
        ("Paris Saint Germain", "PSG", 1), ("Monaco", "MON", 2), ("Marseille", "MAR", 2), ("Lille", "LIL", 2),
        ("Lyon", "LYO", 2), ("Lens", "LEN", 3), ("Nice", "NIC", 3), ("Rennes", "REN", 3),
        ("Strasbourg", "STR", 3), ("Brest", "BRE", 4), ("Toulouse", "TOU", 4), ("Nantes", "NAN", 4),
        ("Auxerre", "AUX", 4), ("Angers", "ANG", 5), ("Le Havre", "HAC", 5), ("Lorient", "LOR", 5),
        ("Metz", "MET", 5), ("Paris FC", "PFC", 5),
    ],
}
LEAGUE_INDEX = {code: i for i, code in enumerate(CLUBS)}

ROSTER_TEMPLATE = {"GK": 3, "CB": 5, "FB": 4, "DM": 3, "CM": 3, "AM": 3, "W": 4, "ST": 3}
FORMATIONS = {
    "4-3-3": ["GK", "CB", "CB", "FB", "FB", "DM", "CM", "CM", "W", "W", "ST"],
    "4-2-3-1": ["GK", "CB", "CB", "FB", "FB", "DM", "DM", "AM", "W", "W", "ST"],
    "3-5-2": ["GK", "CB", "CB", "CB", "FB", "FB", "DM", "CM", "CM", "ST", "ST"],
    "4-4-2": ["GK", "CB", "CB", "FB", "FB", "CM", "CM", "W", "W", "ST", "ST"],
}
# role -> Understat position code(s) for lineups / favourite position
ROLE_CODES = {"GK": ["GK"], "CB": ["DC"], "FB": ["DL", "DR"], "DM": ["DMC"], "CM": ["MC"], "AM": ["AMC"], "W": ["AML", "AMR"], "ST": ["FW"]}
# role -> family letters (Understat league-table 'position' string)
ROLE_FAMILY = {"GK": "GK", "CB": "D", "FB": "D", "DM": "M", "CM": "M", "AM": "M", "W": "M", "ST": "F"}
ROLE_EXTRA_FAMILY = {"FB": ("M", 0.3), "DM": ("D", 0.25), "AM": ("F", 0.3), "W": ("F", 0.6), "ST": ("M", 0.2)}

ROLE_SHOOT = {"GK": 0.0, "CB": 0.35, "FB": 0.5, "DM": 0.6, "CM": 1.0, "AM": 1.9, "W": 2.3, "ST": 3.4}
ROLE_CREATE = {"GK": 0.02, "CB": 0.25, "FB": 1.0, "DM": 0.7, "CM": 1.4, "AM": 2.6, "W": 2.3, "ST": 0.9}
ROLE_INVOLVE = {"GK": 0.9, "CB": 1.6, "FB": 1.5, "DM": 1.9, "CM": 2.0, "AM": 1.4, "W": 1.1, "ST": 0.6}
ROLE_AERIAL = {"GK": 0.0, "CB": 2.0, "FB": 0.5, "DM": 0.8, "CM": 0.7, "AM": 0.5, "W": 0.4, "ST": 1.6}
ROLE_YELLOW_PER90 = {"GK": 0.03, "CB": 0.14, "FB": 0.12, "DM": 0.17, "CM": 0.11, "AM": 0.07, "W": 0.07, "ST": 0.08}
ROLE_AGE = {"GK": (29, 5.5), "CB": (27, 4.5), "FB": (26, 4.0), "DM": (26, 4.2), "CM": (25.5, 4.2), "AM": (25, 4.0), "W": (24.5, 4.0), "ST": (26, 4.5)}
TIER_ABILITY = {1: 0.12, 2: 0.06, 3: 0.0, 4: -0.05, 5: -0.09}


@dataclass(slots=True)
class Player:
    id: int
    name: str
    role: str
    dob: date
    ability: float  # 0..1 current level
    potential: float
    retire_age: int
    shoot: float  # log-normal multipliers around the role baseline
    create: float
    involve: float
    aerial: float
    finish: float  # persistent finishing skill (log-multiplier on goal probability)
    pen_taker: bool = False
    set_piece: bool = False
    side: str = ""  # "L"/"R" for FB / W
    team: str = ""

    def age_on(self, day: date) -> int:
        return day.year - self.dob.year - ((day.month, day.day) < (self.dob.month, self.dob.day))

    def code(self) -> str:
        codes = ROLE_CODES[self.role]
        if self.role == "FB":
            return "DL" if self.side == "L" else "DR"
        if self.role == "W":
            return "AML" if self.side == "L" else "AMR"
        return codes[0]


@dataclass(slots=True)
class ClubSeason:
    name: str
    short: str
    quality: float  # continuous tier (1 strongest)
    attack: float  # log-multiplier on expected xG for
    defence: float  # log-multiplier on expected xG against (lower = better)
    finishing: float  # team-level finishing luck/skill
    goalkeeping: float
    ppda: float
    formations: list[tuple[str, float]]


@dataclass
class League:
    code: str
    seed: int
    names: NameFactory
    rng: random.Random
    next_id: int
    quality: dict[str, float] = field(default_factory=dict)
    bias: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    players: dict[int, Player] = field(default_factory=dict)
    rosters: dict[int, dict[str, list[int]]] = field(default_factory=dict)  # season -> team -> player ids
    club_seasons: dict[int, dict[str, ClubSeason]] = field(default_factory=dict)


def make_league(code: str, seed: int = 7) -> League:
    idx = LEAGUE_INDEX[code]
    league = League(code, seed, NameFactory(seed * 31 + idx), random.Random(seed * 1009 + idx), (idx + 1) * 100_000)
    for name, _short, tier in CLUBS[code]:
        league.quality[name] = float(tier)
        league.bias[name] = (league.rng.gauss(0, 0.07), league.rng.gauss(0, 0.07), league.rng.gauss(0, 0.6))
    return league


def _new_player(league: League, role: str, season: int, tier_quality: float, *, youth: bool = False) -> Player:
    rng = league.rng
    mean_age, sd_age = ROLE_AGE[role]
    age = rng.randint(17, 21) if youth else int(min(38, max(17, rng.gauss(mean_age, sd_age))))
    dob = date(season - age, rng.randint(1, 12), rng.randint(1, 28))
    base = 0.5 + TIER_ABILITY[max(1, min(5, round(tier_quality)))]
    ability = min(0.95, max(0.15, rng.gauss(base, 0.13)))
    potential = min(0.97, max(ability, ability + abs(rng.gauss(0.05 if age > 24 else 0.14, 0.07))))
    star = rng.random() < 0.06
    if star:
        ability, potential = min(0.97, ability + 0.16), min(0.99, potential + 0.14)
    league.next_id += 1
    return Player(
        id=league.next_id,
        name=league.names.make(league.code),
        role=role,
        dob=dob,
        ability=ability,
        potential=potential,
        retire_age=rng.randint(33, 38) if role != "GK" else rng.randint(36, 41),
        shoot=math.exp(rng.gauss(0, 0.3)),
        create=math.exp(rng.gauss(0, 0.3)),
        involve=math.exp(rng.gauss(0, 0.25)),
        aerial=math.exp(rng.gauss(0, 0.35)),
        finish=rng.gauss(0.0, 0.10) + (0.09 if star and role in ("ST", "W", "AM") else 0.0),
        side=rng.choice("LR"),
    )


def _assign_dead_ball_takers(league: League, team: str, ids: list[int]) -> None:
    squad = [league.players[i] for i in ids]
    for p in squad:
        p.pen_taker = p.set_piece = False
    attackers = sorted((p for p in squad if p.role != "GK"), key=lambda p: -(p.ability * p.shoot))
    if attackers:
        attackers[0].pen_taker = True
    creators = sorted((p for p in squad if p.role != "GK"), key=lambda p: -(p.ability * p.create))
    for p in creators[:2]:
        p.set_piece = True


def build_initial_rosters(league: League, season: int) -> None:
    rosters: dict[str, list[int]] = {}
    for name, _short, _tier in CLUBS[league.code]:
        ids = []
        for role, count in ROSTER_TEMPLATE.items():
            for _ in range(count):
                player = _new_player(league, role, season, league.quality[name])
                player.team = name
                league.players[player.id] = player
                ids.append(player.id)
        _assign_dead_ball_takers(league, name, ids)
        rosters[name] = ids
    league.rosters[season] = rosters


def evolve_rosters(league: League, season: int) -> None:
    """Carry the previous season's squads forward: age, retire, transfer, refill."""
    rng = league.rng
    previous = league.rosters[season - 1]
    teams = list(previous)
    on_day = date(season, 8, 1)

    survivors: dict[str, list[int]] = {t: [] for t in teams}
    movers: list[Player] = []
    for team, ids in previous.items():
        for pid in ids:
            p = league.players[pid]
            age = p.age_on(on_day)
            # development curve
            if age < 24:
                p.ability += (p.potential - p.ability) * 0.28 + rng.gauss(0, 0.03)
            elif age <= 29:
                p.ability += rng.gauss(0, 0.025)
            else:
                p.ability += -0.022 * (age - 29) ** 0.5 + rng.gauss(0, 0.025)
            p.ability = min(0.98, max(0.1, p.ability))
            if age >= p.retire_age or p.ability < 0.22:
                continue  # retired / released
            roll = rng.random()
            if roll < 0.05:
                continue  # leaves the league
            if roll < 0.05 + (0.16 if p.ability > 0.6 else 0.10):
                movers.append(p)
            else:
                survivors[team].append(pid)

    # transfers: stronger players drift to stronger clubs
    weights_by_team = {t: 1.0 / (league.quality[t] ** 1.3) for t in teams}
    for p in movers:
        candidates = [t for t in teams if t != p.team]
        boost = 1.0 if p.ability <= 0.62 else 2.2
        weights = [weights_by_team[t] ** boost for t in candidates]
        target = rng.choices(candidates, weights)[0]
        p.team = target
        survivors[target].append(p.id)

    for team in teams:
        drift = rng.gauss(0, 0.28)
        league.quality[team] = min(5.4, max(0.7, league.quality[team] + drift + 0.15 * (round(_initial_tier(league.code, team)) - league.quality[team])))
        ids = survivors[team]
        counts: dict[str, int] = {}
        for pid in ids:
            counts[league.players[pid].role] = counts.get(league.players[pid].role, 0) + 1
        for role, want in ROSTER_TEMPLATE.items():
            while counts.get(role, 0) < want:
                youth = rng.random() < 0.45
                player = _new_player(league, role, season, league.quality[team], youth=youth)
                player.team = team
                league.players[player.id] = player
                ids.append(player.id)
                counts[role] = counts.get(role, 0) + 1
        _assign_dead_ball_takers(league, team, ids)
    league.rosters[season] = survivors


def _initial_tier(code: str, team: str) -> float:
    for name, _short, tier in CLUBS[code]:
        if name == team:
            return float(tier)
    return 3.0


def club_seasons(league: League, season: int) -> dict[str, ClubSeason]:
    """Team-level strengths for a season (deterministic per league/season)."""
    if season in league.club_seasons:
        return league.club_seasons[season]
    rng = random.Random(league.seed * 7919 + LEAGUE_INDEX[league.code] * 131 + season)
    out: dict[str, ClubSeason] = {}
    for name, short, _tier in CLUBS[league.code]:
        q = league.quality[name]
        att_bias, def_bias, press_bias = league.bias[name]
        attack = 0.32 - 0.106 * q + att_bias + rng.gauss(0, 0.05)
        defence = 0.30 - 0.100 * q + def_bias + rng.gauss(0, 0.05)  # higher = concedes fewer xG
        pool = list(FORMATIONS)
        rng.shuffle(pool)
        main = rng.random() * 0.35 + 0.5
        formations = [(pool[0], main), (pool[1], 1 - main - 0.08), (pool[2], 0.08)]
        out[name] = ClubSeason(
            name=name,
            short=short,
            quality=q,
            attack=attack,
            defence=defence,
            finishing=rng.gauss(0, 0.07),
            goalkeeping=rng.gauss(0, 0.07),
            ppda=max(6.5, 8.0 + 1.5 * (q - 1) + press_bias + rng.gauss(0, 0.8)),
            formations=formations,
        )
    league.club_seasons[season] = out
    return out


def season_start(season: int) -> date:
    day = date(season, 8, 12)
    return day + timedelta(days=(5 - day.weekday()) % 7)  # first Saturday on/after 12 Aug
