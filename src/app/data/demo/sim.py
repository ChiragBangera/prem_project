"""Shot-level simulation of a league season.

Everything the demo serves is derived from simulated *shots*: each shot has a
location, an xG computed from geometry, a shooter, a passer, and an outcome
drawn from the xG. Match scores, team histories, player season totals, xGChain
and shot maps are all sums over those same shots, so every endpoint agrees with
every other - exactly the consistency a real dataset has.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np

from app.stats import outcome_probs, poisson_binomial

from .world import (
    FORMATIONS,
    LEAGUE_INDEX,
    ROLE_AERIAL,
    ROLE_CREATE,
    ROLE_EXTRA_FAMILY,
    ROLE_FAMILY,
    ROLE_INVOLVE,
    ROLE_SHOOT,
    ROLE_YELLOW_PER90,
    ClubSeason,
    League,
    Player,
    club_seasons,
    season_start,
)

BASE_XG = 1.24  # a league-average side's expected xG per match
MEAN_XG_PER_SHOT = 0.106  # average non-penalty xG per shot; sets shot volume from expected xG
HOME_ADV = 0.13  # log-uplift for the home side
PITCH_L, PITCH_W, GOAL_W = 105.0, 68.0, 7.32
MATCH_MIN = 90
KICKOFFS = [(0, "12:30"), (0, "15:00"), (0, "15:00"), (0, "15:00"), (0, "17:30"), (1, "14:00"), (1, "16:30"), (1, "16:30"), (1, "20:00")]

PASS_ACTIONS = ("Pass", "Cross", "Throughball", "Chipped", "HeadPass")
SOLO_ACTIONS = ("TakeOn", "Rebound", "BallRecovery", "Dispossessed", "BlockedPass", "Clearance")


# ---------------------------------------------------------------------- geometry & xG


def xg_at(x: float, y: float) -> float:
    """Logistic xG from distance and goal-mouth angle (fitted to typical values)."""
    dx = max((1.0 - x) * PITCH_L, 0.3)
    dy = (y - 0.5) * PITCH_W
    dist = math.hypot(dx, dy)
    angle = math.atan2(GOAL_W * dx, dx * dx + dy * dy - (GOAL_W / 2) ** 2)
    if angle < 0:
        angle += math.pi
    logit = -2.35 - 0.0696 * dist + 2.129 * angle
    return 1.0 / (1.0 + math.exp(-logit))


def zone_of(x: float, y: float) -> str:
    dx, dy = (1.0 - x) * PITCH_L, abs(y - 0.5) * PITCH_W
    if dx <= 5.5 and dy <= 9.16:
        return "shotSixYardBox"
    if dx <= 16.5 and dy <= 20.16:
        return "shotPenaltyArea"
    return "shotOboxTotal"


def _place(rng: random.Random, d_lo: float, d_hi: float, spread: float, central: float = 0.0) -> tuple[float, float]:
    d = rng.uniform(d_lo, d_hi)
    phi = max(-1.25, min(1.25, rng.gauss(0, spread)))
    if d < 12:
        phi *= 0.7
    dx, dy = d * math.cos(phi), d * math.sin(phi)
    x = min(0.995, max(0.5, 1.0 - dx / PITCH_L))
    y = min(0.98, max(0.02, 0.5 + dy / PITCH_W + central))
    return x, y


def sample_location(rng: random.Random, situation: str) -> tuple[float, float]:
    if situation == "OpenPlay":
        zone = rng.random()
        if zone < 0.46:
            return _place(rng, 5.0, 16.5, 0.62)
        if zone < 0.80:
            return _place(rng, 16.5, 26.0, 0.55)
        return _place(rng, 26.0, 38.0, 0.5)
    if situation == "FromCorner":
        return _place(rng, 4.5, 14.0, 0.36)
    if situation == "DirectFreekick":
        return _place(rng, 17.0, 30.0, 0.35)
    if situation == "Penalty":
        return 1.0 - 11.0 / PITCH_L, 0.5
    return _place(rng, 7.0, 22.0, 0.5)  # SetPiece / indirect


# ---------------------------------------------------------------------- records


@dataclass(slots=True)
class ShotSim:
    id: int
    minute: int
    x: float
    y: float
    xg: float
    result: str
    situation: str
    shot_type: str
    last_action: str
    venue: str  # "h" | "a"
    shooter: Player
    assister: Player | None
    speed: str
    diff: int = 0  # shooter's goal difference before the shot


@dataclass(slots=True)
class Appearance:
    player: Player
    start: int
    end: int  # exclusive; 999 = until the final whistle incl. added time
    code: str
    goals: int = 0
    own_goals: int = 0
    shots: int = 0
    xg: float = 0.0
    npxg: float = 0.0
    key_passes: int = 0
    assists: int = 0
    xa: float = 0.0
    xgchain: float = 0.0
    xgbuildup: float = 0.0
    yellow: int = 0
    red: int = 0

    @property
    def minutes(self) -> int:
        return min(self.end, MATCH_MIN) - self.start


@dataclass(slots=True)
class MatchSim:
    id: int
    dt: str
    home: str
    away: str
    hg: int
    ag: int
    hxg: float
    axg: float
    shots: dict[str, list[ShotSim]]
    lineups: dict[str, list[Appearance]]
    formations: dict[str, str]
    forecast: tuple[float, float, float]
    xpts: tuple[float, float]
    ppda: dict[str, tuple[float, float]]  # venue -> (att, def)
    deep: dict[str, int]


@dataclass(slots=True)
class FixtureSim:
    id: int
    dt: str
    home: str
    away: str
    forecast: tuple[float, float, float]
    match: MatchSim | None = None


@dataclass(slots=True)
class PlayerAgg:
    player: Player
    teams: list[str] = field(default_factory=list)
    games: int = 0
    minutes: int = 0
    goals: int = 0
    npg: int = 0
    assists: int = 0
    shots: int = 0
    key_passes: int = 0
    yellow: int = 0
    red: int = 0
    xg: float = 0.0
    npxg: float = 0.0
    xa: float = 0.0
    xgchain: float = 0.0
    xgbuildup: float = 0.0
    sub_apps: int = 0
    role_minutes: dict[str, int] = field(default_factory=dict)  # code -> minutes


@dataclass
class SeasonData:
    league: str
    season: int
    clubs: dict[str, ClubSeason]
    rosters: dict[str, list[Player]]
    fixtures: list[FixtureSim]
    matches: dict[int, MatchSim]
    players: dict[int, PlayerAgg]
    letters: dict[int, str]  # Understat-style position string per player


# ---------------------------------------------------------------------- season


def _schedule(rng: random.Random, teams: list[str]) -> list[list[tuple[str, str]]]:
    ring = list(teams)
    rng.shuffle(ring)
    n = len(ring)
    first = []
    for r in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = ring[i], ring[n - 1 - i]
            pairs.append((a, b) if (r + i) % 2 == 0 else (b, a))
        first.append(pairs)
        ring = [ring[0], ring[-1]] + ring[1:-1]
    rng.shuffle(first)
    second = [[(b, a) for a, b in pairs] for pairs in first]
    return first + second


def _form_paths(rng: random.Random, teams: list[str], rounds: int) -> dict[str, list[float]]:
    """Slowly varying hot/cold spells per team (AR(1)), so form charts have shape."""
    paths = {}
    for team in teams:
        level, path = rng.gauss(0, 0.05), []
        for _ in range(rounds):
            level = 0.88 * level + rng.gauss(0, 0.045)
            path.append(level)
        paths[team] = path
    return paths


def _outcome_forecast(mu_h: float, mu_a: float) -> tuple[float, float, float]:
    def pmf(mu):
        return np.array([math.exp(-mu) * mu**k / math.factorial(k) for k in range(9)])

    return outcome_probs(pmf(mu_h), pmf(mu_a))


def simulate_season(league: League, season: int, today: date) -> SeasonData:
    clubs = club_seasons(league, season)
    teams = list(clubs)
    rng = random.Random(league.seed * 104729 + LEAGUE_INDEX[league.code] * 977 + season)
    league_idx = LEAGUE_INDEX[league.code]

    rosters = {t: [league.players[i] for i in league.rosters[season][t]] for t in teams}
    data = SeasonData(league.code, season, clubs, rosters, [], {}, {}, {})

    rounds = _schedule(rng, teams)
    forms = _form_paths(rng, teams, len(rounds))
    start = season_start(season)
    shot_id = season * 1_000_000 + league_idx * 100_000
    counter = 0

    for r, pairs in enumerate(rounds):
        for home, away in pairs:
            counter += 1
            offset, hhmm = rng.choice(KICKOFFS)
            when = datetime.fromisoformat(f"{(start + timedelta(days=7 * r + offset)).isoformat()} {hhmm}:00")
            mid = (league_idx + 1) * 10_000_000 + (season - 2000) * 10_000 + counter
            ch, ca = clubs[home], clubs[away]
            mu_h = BASE_XG * math.exp(ch.attack - ca.defence + HOME_ADV + forms[home][r])
            mu_a = BASE_XG * math.exp(ca.attack - ch.defence + forms[away][r])
            forecast = _outcome_forecast(mu_h, mu_a)
            fixture = FixtureSim(mid, when.strftime("%Y-%m-%d %H:%M:%S"), home, away, forecast)
            if when.date() < today:
                shot_id, match = _simulate_match(rng, data, fixture, mu_h, mu_a, shot_id)
                fixture.match = match
                data.matches[mid] = match
            data.fixtures.append(fixture)
    _finalise_letters(rng, data)
    return data


# ---------------------------------------------------------------------- one match


def _pick_lineup(rng: random.Random, squad: list[Player], formation: str) -> tuple[list[Player], list[Player]]:
    available = [p for p in squad if rng.random() > 0.06]
    if not any(p.role == "GK" for p in available):
        available.append(rng.choice([p for p in squad if p.role == "GK"]))  # someone always keeps goal
    if len(available) < 14:
        available = list(squad)
    starters: list[Player] = []
    taken: set[int] = set()
    for role in FORMATIONS[formation]:
        pool = (
            [p for p in available if p.role == role and p.id not in taken]
            or [p for p in available if p.id not in taken and (p.role == "GK") == (role == "GK")]
            or [p for p in squad if p.id not in taken and (p.role == "GK") == (role == "GK")]
            or [p for p in squad if p.id not in taken]
        )
        best = max(pool, key=lambda p: p.ability + rng.gauss(0, 0.06))
        starters.append(best)
        taken.add(best.id)
    bench = [p for p in available if p.id not in taken]
    return starters, bench


def _simulate_match(rng, data: SeasonData, fixture: FixtureSim, mu_h: float, mu_a: float, shot_id: int):
    home, away = fixture.home, fixture.away
    clubs = data.clubs
    sides = {"h": (home, away, mu_h), "a": (away, home, mu_a)}
    formations, lineups, appearances = {}, {}, {}

    for venue, (team, _opp, _mu) in sides.items():
        club = clubs[team]
        names, weights = zip(*club.formations)
        formation = rng.choices(names, weights)[0]
        formations[venue] = formation
        starters, bench = _pick_lineup(rng, data.rosters[team], formation)
        apps = [Appearance(p, 0, 999, p.code()) for p in starters]
        bench_pool = list(bench)
        for _ in range(rng.choice([3, 3, 4, 5])):
            if not bench_pool:
                break
            outgoing = rng.choice([a for a in apps if a.end == 999 and a.player.role != "GK" and a.start == 0] or [None])
            if outgoing is None:
                break
            same_role = [p for p in bench_pool if p.role == outgoing.player.role]
            incoming = max(same_role or bench_pool, key=lambda p: p.ability + rng.gauss(0, 0.1))
            bench_pool.remove(incoming)
            minute = rng.randint(46, 86)
            outgoing.end = minute
            apps.append(Appearance(incoming, minute, 999, "Sub"))
        lineups[venue] = apps
        appearances[venue] = apps

    shots: dict[str, list[ShotSim]] = {"h": [], "a": []}
    own_goals = {"h": 0, "a": 0}
    for venue, (team, opp, mu) in sides.items():
        other = "a" if venue == "h" else "h"
        club, rival = clubs[team], clubs[opp]
        # Quality of chances follows team quality: better sides get slightly better shots.
        quality = math.exp(0.35 * (club.attack - rival.defence))
        n_open = _poisson(rng, mu / MEAN_XG_PER_SHOT)
        situations = rng.choices(
            ["OpenPlay", "FromCorner", "SetPiece", "DirectFreekick"], [0.71, 0.13, 0.07, 0.035], k=n_open
        )
        if rng.random() < 0.06:
            situations.append("Penalty")
        if rng.random() < 0.02:
            own_goals[other] += 1  # own goal credited to the other side
        for situation in situations:
            shots[venue].append(
                _make_shot(rng, situation, venue, appearances[venue], club, rival, quality, shot_id := shot_id + 1)
            )

    # game state (score before each shot), needed for the team page's game-state split
    merged = sorted(
        [(s.minute, v, s) for v in ("h", "a") for s in shots[v]], key=lambda item: (item[0], item[2].id)
    )
    score = {"h": 0, "a": 0}
    for _minute, venue, shot in merged:
        other = "a" if venue == "h" else "h"
        shot.diff = score[venue] - score[other]
        if shot.result == "Goal":
            score[venue] += 1

    hg = sum(1 for s in shots["h"] if s.result == "Goal") + own_goals["h"]
    ag = sum(1 for s in shots["a"] if s.result == "Goal") + own_goals["a"]
    hxg, axg = sum(s.xg for s in shots["h"]), sum(s.xg for s in shots["a"])

    _credit_players(rng, shots, appearances)
    _cards(rng, appearances)

    ph, pd, pa = outcome_probs(poisson_binomial(s.xg for s in shots["h"]), poisson_binomial(s.xg for s in shots["a"]))
    ppda = {}
    deep = {}
    for venue, (team, opp, _mu) in sides.items():
        other = "a" if venue == "h" else "h"
        att = max(90.0, rng.gauss(265, 42))
        ppda[venue] = (att, max(6.0, att / max(5.5, clubs[team].ppda * math.exp(rng.gauss(0, 0.16)))))
        own_xg = hxg if venue == "h" else axg
        deep[venue] = max(0, round(2.2 + 6.4 * own_xg + rng.gauss(0, 1.7)))

    match = MatchSim(
        id=fixture.id,
        dt=fixture.dt,
        home=home,
        away=away,
        hg=hg,
        ag=ag,
        hxg=hxg,
        axg=axg,
        shots=shots,
        lineups=lineups,
        formations=formations,
        forecast=fixture.forecast,
        xpts=(3 * ph + pd, 3 * pa + pd),
        ppda=ppda,
        deep=deep,
    )
    _aggregate_players(data, match)
    return shot_id, match


def _state_label(diff: int) -> str:
    if diff == 0:
        return "Goal diff 0"
    if diff > 1:
        return "Goal diff > +1"
    if diff == 1:
        return "Goal diff +1"
    if diff < -1:
        return "Goal diff < -1"
    return "Goal diff -1"


def _poisson(rng: random.Random, lam: float) -> int:
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _on_pitch(apps: list[Appearance], minute: int) -> list[Appearance]:
    return [a for a in apps if a.start <= minute < a.end]


def _ability_mult(p: Player) -> float:
    return 0.55 + 0.9 * p.ability


def _make_shot(rng, situation, venue, apps, club: ClubSeason, rival: ClubSeason, quality: float, shot_id: int) -> ShotSim:
    minute = min(97, int((rng.random() ** 0.92) * 90) + 1) if rng.random() > 0.07 else rng.randint(91, 97)
    on = _on_pitch(apps, minute) or _on_pitch(apps, 45)
    outfield = [a for a in on if a.player.role != "GK"] or on
    x, y = sample_location(rng, situation)
    header = False

    if situation == "Penalty":
        taker = next((a for a in outfield if a.player.pen_taker), None) or max(outfield, key=lambda a: a.player.ability * a.player.shoot)
        shooter, shot_type, last_action, assister = taker.player, "RightFoot", "Standard", None
        xg = 0.76
    else:
        if situation in ("FromCorner", "SetPiece"):
            header = rng.random() < (0.62 if situation == "FromCorner" else 0.45)
        if situation == "DirectFreekick":
            pool = [a for a in outfield if a.player.set_piece] or outfield
            weights = [a.player.ability * a.player.shoot * (2.5 if a.player.set_piece else 1) + 0.1 for a in pool]
        elif header:
            pool = outfield
            weights = [ROLE_AERIAL[a.player.role] * a.player.aerial * _ability_mult(a.player) + 0.02 for a in pool]
        else:
            pool = outfield
            weights = [ROLE_SHOOT[a.player.role] * a.player.shoot * _ability_mult(a.player) + 0.02 for a in pool]
        shooter_app = rng.choices(pool, weights)[0]
        shooter = shooter_app.player
        if header:
            shot_type = "Head"
        else:
            r = rng.random()
            shot_type = "RightFoot" if r < 0.6 else "LeftFoot" if r < 0.93 else "OtherBodyPart"
        assister = None
        if situation == "FromCorner":
            takers = [a for a in outfield if a.player.set_piece and a.player.id != shooter.id] or [a for a in outfield if a.player.id != shooter.id]
            assister = rng.choice(takers).player if takers else None
            last_action = "Aerial" if header else "Pass"
        elif situation == "DirectFreekick":
            last_action = "Standard"
        elif situation == "SetPiece":
            others = [a for a in outfield if a.player.id != shooter.id]
            assister = rng.choice(others).player if others and rng.random() < 0.7 else None
            last_action = "Pass" if assister else "Standard"
        else:
            last_action = rng.choices(
                ["Pass", "Cross", "Throughball", "Chipped", "TakeOn", "Rebound", "BallRecovery", "Dispossessed", "BlockedPass", "Clearance"],
                [0.44, 0.13, 0.06, 0.02, 0.08, 0.07, 0.07, 0.04, 0.05, 0.04],
            )[0]
            if last_action in PASS_ACTIONS:
                others = [a for a in outfield if a.player.id != shooter.id]
                cw = [ROLE_CREATE[a.player.role] * a.player.create * _ability_mult(a.player) + 0.01 for a in others]
                assister = rng.choices(others, cw)[0].player if others else None
        xg = xg_at(x, y)
        if header:
            xg *= 0.72
        if situation == "DirectFreekick":
            xg *= 0.55
        elif situation in ("FromCorner", "SetPiece"):
            xg *= 0.92
        if last_action == "Throughball":
            xg *= 1.25
        elif last_action == "Cross":
            xg *= 0.9
        xg = min(0.95, max(0.006, xg * quality * math.exp(rng.gauss(0, 0.14))))

    p_goal = min(0.97, xg * math.exp(shooter.finish + club.finishing - rival.goalkeeping))
    if rng.random() < p_goal:
        result = "Goal"
    else:
        result = _non_goal_result(rng, xg)
    if last_action in PASS_ACTIONS or situation in ("FromCorner",):
        speed = "Fast" if last_action in ("Throughball", "Chipped") or rng.random() < 0.1 else "Slow" if rng.random() < 0.18 else "Normal"
    elif situation in ("SetPiece", "DirectFreekick", "Penalty"):
        speed = "Standard"
    else:
        speed = "Fast" if last_action in ("TakeOn", "BallRecovery") and rng.random() < 0.5 else "Normal"
    return ShotSim(shot_id, minute, x, y, xg, result, situation, shot_type, last_action, venue, shooter, assister, speed)


def _non_goal_result(rng: random.Random, xg: float) -> str:
    r = rng.random()
    saved = 0.34 + 0.3 * min(xg * 3, 1)  # bigger chances are more often on target
    if r < saved:
        return "SavedShot"
    if r < saved + 0.28:
        return "MissedShots"
    if r < saved + 0.31:
        return "ShotOnPost"
    return "BlockedShot"


def _credit_players(rng, shots: dict[str, list[ShotSim]], apps: dict[str, list[Appearance]]) -> None:
    for venue, side_shots in shots.items():
        by_player = {a.player.id: a for a in apps[venue]}
        for shot in side_shots:
            on = _on_pitch(apps[venue], shot.minute) or apps[venue]
            shooter = by_player[shot.shooter.id]
            shooter.shots += 1
            shooter.xg += shot.xg
            if shot.situation != "Penalty":
                shooter.npxg += shot.xg
            if shot.result == "Goal":
                shooter.goals += 1
            involved = {shot.shooter.id}
            key_passer = None
            if shot.assister is not None and shot.assister.id in by_player:
                key_passer = by_player[shot.assister.id]
                key_passer.key_passes += 1
                key_passer.xa += shot.xg
                if shot.result == "Goal":
                    key_passer.assists += 1
                involved.add(key_passer.player.id)
            extras_n = rng.choices([0, 1, 2, 3], [0.25, 0.35, 0.25, 0.15])[0] if shot.situation != "Penalty" else 0
            candidates = [a for a in on if a.player.id not in involved]
            extras: list[Appearance] = []
            for _ in range(min(extras_n, len(candidates))):
                weights = [ROLE_INVOLVE[a.player.role] * a.player.involve + 0.05 for a in candidates]
                pick = rng.choices(candidates, weights)[0]
                extras.append(pick)
                candidates.remove(pick)
            shooter.xgchain += shot.xg
            if key_passer is not None:
                key_passer.xgchain += shot.xg
            for a in extras:
                a.xgchain += shot.xg
                a.xgbuildup += shot.xg


def _cards(rng: random.Random, apps: dict[str, list[Appearance]]) -> None:
    for venue_apps in apps.values():
        for a in venue_apps:
            if rng.random() < ROLE_YELLOW_PER90[a.player.role] * a.minutes / 90:
                a.yellow = 1
                if rng.random() < 0.05:  # second booking
                    a.red = 1
            elif rng.random() < 0.0035 * a.minutes / 90:
                a.red = 1


def _aggregate_players(data: SeasonData, match: MatchSim) -> None:
    for venue, apps in match.lineups.items():
        team = match.home if venue == "h" else match.away
        for a in apps:
            if a.minutes <= 0:
                continue
            agg = data.players.get(a.player.id)
            if agg is None:
                agg = data.players[a.player.id] = PlayerAgg(a.player)
            if team not in agg.teams:
                agg.teams.append(team)
            agg.games += 1
            agg.minutes += a.minutes
            agg.goals += a.goals
            agg.npg += a.goals - sum(
                1 for s in match.shots[venue] if s.shooter.id == a.player.id and s.situation == "Penalty" and s.result == "Goal"
            )
            agg.assists += a.assists
            agg.shots += a.shots
            agg.key_passes += a.key_passes
            agg.yellow += a.yellow
            agg.red += a.red
            agg.xg += a.xg
            agg.npxg += a.npxg
            agg.xa += a.xa
            agg.xgchain += a.xgchain
            agg.xgbuildup += a.xgbuildup
            if a.start > 0:
                agg.sub_apps += 1
            agg.role_minutes[a.code] = agg.role_minutes.get(a.code, 0) + a.minutes


def _finalise_letters(rng: random.Random, data: SeasonData) -> None:
    for pid, agg in data.players.items():
        role = agg.player.role
        letters = {ROLE_FAMILY[role]}
        extra = ROLE_EXTRA_FAMILY.get(role)
        if extra and rng.random() < extra[1]:
            letters.add(extra[0])
        ordered = sorted(letters - {"GK"}) if "GK" not in letters else ["GK"]
        if agg.sub_apps and "GK" not in letters:
            ordered.append("S")
        data.letters[pid] = " ".join(ordered)
