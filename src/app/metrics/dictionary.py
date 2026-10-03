"""The data dictionary: every raw field, every derived number, and the ideas they rest on, in plain language.

The metric entries come straight from the registry, so the dictionary can never drift from what the app computes. This module adds
what the registry does not know: where raw data comes from and what its fields mean, what each event counter counts, and the
concepts (percentile, peer pool, shrinkage, role groups ...) that every page relies on.
"""

from __future__ import annotations

from app.events import counters as C
from app.events import schema as ES

from . import player as P
from . import tags as TG
from . import team as T
from .catalog import ROLE_LABELS
from .lenses import PLAYER_LENSES, TEAM_LENSES
from .views import PLAYER_VIEWS, TEAM_VIEWS

SOURCES: list[dict] = [
    {
        "key": "understat", "name": "Understat", "kind": "web service (public JSON)",
        "what": "Shot-by-shot data for the top five European leagues from 2014/15, with its own expected-goals (xG) model. It is where every xG, xA, xGChain and PPDA figure comes from.",
        "how": "Read at a slow, polite pace and kept on this computer: the league season, each match page, team pages and player pages. A finished match never changes, so it is fetched once.",
        "limits": "Only shots and who was involved in them. No tackles, interceptions, passing, carries, pressures or goalkeeping: those come from the event data below.",
        "parts": [
            {"name": "League season (players)", "fields": [
                ("player_name, id, team_title", "The player, his Understat id, and the club or clubs (comma-separated when he moved mid-season)."),
                ("games, time", "Appearances and minutes. Minutes count real minutes on the pitch up to the final whistle of 90, so a substitute's differ from the event data's scaled minutes."),
                ("goals, npg", "Goals scored, and goals excluding penalties."),
                ("shots", "Shots taken (blocked shots included)."),
                ("xG, npxG", "The expected goals of every shot he took, and the same without penalties. Each shot is worth the chance a typical shot from that position and in that way would be scored."),
                ("assists, xA", "Goals he set up, and the xG of the shots his passes created."),
                ("key_passes", "Passes that directly led to a shot."),
                ("xGChain", "The total xG of every possession he touched that ended in a shot (his own shots and passes included)."),
                ("xGBuildup", "xGChain without the shots and key passes he made himself: the earlier build-up."),
                ("yellow_cards, red_cards", "Cards."),
                ("position", "The positions he played, as letters (F forward, M midfield, D defence, GK, and S for substitute appearances), alphabetically."),
            ]},
            {"name": "Team history (one row per match)", "fields": [
                ("xG, xGA, npxG, npxGA", "Expected goals created and conceded, with and without penalties."),
                ("scored, missed, result, pts", "The real score, result and points."),
                ("xpts", "Expected points: the points the chances were worth, found by replaying every shot of the match."),
                ("deep, deep_allowed", "Passes completed within about 20 yards of the opponent's goal, by the team and against it."),
                ("ppda (att, def)", "Opponent passes allowed in the opponent's build-up (att) and defensive actions made there (def). PPDA is att ÷ def."),
                ("ppda_allowed", "The same figures for the pressing this team faced from the opponent."),
            ]},
            {"name": "Match page", "fields": [
                ("shots[].X, Y", "Where a shot was taken, 0-1 along the pitch (1 is the goal line being attacked) and across it."),
                ("shots[].xG, result", "The chance's value and what happened: Goal, SavedShot, BlockedShot, MissedShots, ShotOnPost, or OwnGoal (credited to the opposing side)."),
                ("shots[].situation, shotType, lastAction", "How the move started (OpenPlay, FromCorner, SetPiece, DirectFreekick, Penalty), the body part (Head, RightFoot, LeftFoot, OtherBodyPart) and the action before the shot."),
                ("shots[].player_assisted", "The player whose pass created the shot, if any."),
                ("rosters[]", "Everyone who played: minutes (time), position played (a substitute's is recorded only as Sub), goals, shots, xG, xA, key passes, xGChain, xGBuildup, cards."),
            ]},
            {"name": "Team page", "fields": [
                ("statistics.situation / shotZone / timing / gameState / attackSpeed / formation / result", "The team's shots and xG, for and against, grouped by how the chance came about, where it was taken, when, at what score, how fast the move was, in which formation and how it ended."),
            ]},
        ],
    },
    {
        "key": "whoscored", "name": "WhoScored (event data)", "kind": "web page, read by a browser (soccerdata)",
        "what": "Opta-style event data: every pass, tackle, duel, shot, save and card of a match (about 1,500 events), each with its position on the pitch, plus line-ups, formations, referee and a performance rating for each player.",
        "how": "Read match by match through a hidden browser (about 15 seconds each) the first time, then kept in this computer's own store exactly as it was served. Everything else is worked out from that stored copy, so a new definition or chart never needs the website again.",
        "limits": "Positions are on a 0-100 pitch seen from the acting team's attacking direction. There is no ball tracking, no pressure event and no carry event (carries here are estimated). Its ratings are proprietary.",
        "parts": [
            {"name": "Match document", "fields": [
                ("events[]", "Every event: type, outcome, team, player, minute and second, where it happened (x, y) and where it ended (endX, endY), and qualifiers that say how."),
                ("home / away .players", "The squad: shirt number, age, height, weight, whether he started, the position he started in, when he came on or off, and his match rating."),
                ("home / away .formations", "Each formation the team played, when it started and ended, and where each player stood in it."),
                ("home / away .managerName, averageAge", "The manager and the average age of the side that day."),
                ("referee, venueName, attendance, startTime, ftScore, htScore", "The match facts."),
            ]},
        ],
    },
    {
        "key": "espn", "name": "ESPN squad lists", "kind": "web service (public JSON)",
        "what": "Each club's squad for a season, with every player's exact date of birth.",
        "how": "About 20 requests per league and season, matched to Understat players by the words of the name and the club, never by a looser guess.",
        "limits": "Some seasons are sparse (only a few players per club). A player is left without an age rather than matched wrongly.",
        "parts": [{"name": "Roster", "fields": [("fullName, displayName, dateOfBirth", "The player's names and his date of birth."), ("position", "A coarse position (goalkeeper, defender, midfielder, forward).")]}],
    },
    {
        "key": "wikidata", "name": "Wikidata", "kind": "open database",
        "what": "The date of birth of players the squad lists leave out, found by name and club.",
        "how": "Used only as a fallback and only when exactly one footballer plausibly fits; an age matched by the name alone is shown with a question mark and never used by a filter.",
        "limits": "Many retired namesakes, so the app is strict and prefers a blank to a guess.", "parts": [],
    },
]

EVENT_TYPE_DOC = {
    "Pass": "A pass, including crosses, through balls, corners, free kicks, throw-ins, goal kicks. Successful when it reached a team-mate.",
    "TakeOn": "An attempt to dribble past an opponent. Successful when he got past.",
    "Foul": "A foul. Unsuccessful is the player who committed it; successful is the player who was fouled.",
    "Tackle": "A tackle won: the defender took the ball off an opponent.",
    "Challenge": "A defender beaten by a dribble: the opposite of a tackle.",
    "Interception": "A pass read and cut out.", "Clearance": "A ball cleared away from danger.", "BallRecovery": "A loose or contested ball won back.",
    "BlockedPass": "A pass or cross blocked by a defender.", "Aerial": "An aerial duel. Successful for the player who won it.", "Dispossessed": "A player lost the ball to a tackle.",
    "Save": "A shot saved by the goalkeeper, or (with the outfielder-block marker) blocked by an outfield player.", "SavedShot": "A shot that was saved or blocked.",
    "MissedShots": "A shot off target.", "ShotOnPost": "A shot that hit the woodwork.", "Goal": "A goal (an own goal carries its own marker).",
    "Claim": "A goalkeeper claimed a cross.", "Punch": "A goalkeeper punched the ball clear.", "KeeperPickup": "A goalkeeper gathered a loose ball.", "KeeperSweeper": "A goalkeeper came off his line to clear.",
    "Smother": "A goalkeeper dived at an attacker's feet.", "PenaltyFaced": "A goalkeeper faced a penalty.", "CrossNotClaimed": "A goalkeeper failed to claim a cross.",
    "Card": "A yellow card, red card or second yellow.", "Error": "A mistake that gave the opponent a chance or a goal.", "OffsideGiven": "A player flagged offside.",
    "OffsideProvoked": "A defender whose line caught an attacker offside.", "OffsidePass": "The pass that played an attacker offside.",
    "SubstitutionOn": "A substitute came on.", "SubstitutionOff": "A player was replaced.", "FormationSet": "A team's starting formation.", "FormationChange": "A change of formation.",
    "CornerAwarded": "A corner was awarded.", "BallTouch": "A touch of the ball that is not a pass, dribble or shot.", "ShieldBallOpp": "Shielding the ball from an opponent.",
    "GoodSkill": "A piece of skill (a flick, a nutmeg).", "ChanceMissed": "A big chance missed.", "Start": "The start of a half.", "End": "The end of a half or the match.",
}

QUALIFIER_DOC = {
    "Longball": "A long ball.", "Cross": "A cross.", "Throughball": "A through ball.", "HeadPass": "A headed pass.", "Chipped": "A chipped pass.",
    "ThrowIn": "A throw-in.", "GoalKick": "A goal kick.", "CornerTaken": "A corner kick.", "FreekickTaken": "A free kick.", "KeeperThrow": "A goalkeeper's throw.",
    "KeyPass": "The action led directly to a shot.", "BigChanceCreated": "A pass that set up a big chance.", "BigChance": "The shot was a big chance.", "Assisted": "The goal or shot had an assist.",
    "Penalty": "A penalty (on a foul, a kick or a save).", "OwnGoal": "An own goal.", "Blocked": "The shot was blocked.", "OutfielderBlock": "A shot blocked by an outfield player (on a Save event).",
    "Head": "The body part was the head.", "KeeperSaveInTheBox": "A save from inside the box.", "KeeperSaveObox": "A save from outside the box.", "KeeperSaveInSixYard": "A save from inside the six-yard box.",
    "DivingSave": "A diving save.", "AerialFoul": "A foul in the air.", "Defensive": "The defending side of a duel.", "Offensive": "The attacking side of a duel.",
    "VoidYellowCard": "A yellow card later rescinded.", "LeadingToAttempt": "An error that led to a shot.", "LeadingToGoal": "An error that led to a goal.",
    "DirectFreekick": "A direct free kick.", "Red": "A straight red card.", "SecondYellow": "A second yellow card.",
}

CONCEPTS: list[dict] = [
    {"group": "Reading the numbers", "entries": [
        ("per90", "Per 90", "A count scaled to a full match: count × 90 ÷ minutes.", "The fair way to compare players with different minutes. Event data uses its own scaled minutes (a full match is 90 whatever the stoppage time)."),
        ("pergame", "Per game", "For teams: a count divided by the matches played.", "Event metrics use only the matches that have event data."),
        ("percentile", "Percentile", "The share of comparable players (or teams) he is above on a metric. 50 is average, 90 is better than nine in ten.", "Every percentile reads higher is better, including cards and fouls, where fewer is better. For style metrics (possession, long-ball share) higher simply means more of it."),
        ("pool", "Peer pool", "The players a percentile is measured against: same role group, enough minutes.", "The minutes needed scale with how far into the season it is (about a quarter of a full-time player's minutes, between 180 and 900). Event metrics have their own pool: only players who have event data."),
        ("shrinkage", "Small-sample adjustment", "Rankings pull a rate toward the pool average in proportion to how little football stands behind it.", "A substitute with one lucky cameo does not top a leaderboard. The table shows the raw value; only the percentile uses the adjusted one. Ratios are pulled by their attempts (a pass rate from ten passes is pulled hard)."),
        ("unknown", "Blank, not zero", "A value the data cannot give is left blank.", "A player with no event data has no tackles recorded, which is not the same as none. A statistic built from match pages is blank unless nearly every match of the season is stored. The app never guesses an age or a link."),
        ("sample", "Sample size", "Minutes played. Under about 450 minutes, per-90 rates swing wildly.", "Players below the pool minimum are marked small sample and faded."),
    ]},
    {"group": "Roles and positions", "entries": [
        ("role_group", "Role group", "Attacker, midfielder, defender or goalkeeper: the peer group for percentiles.",
         "Decided, in order, by the position he started at most often (from the line-ups of the stored matches, at least 270 minutes), Understat's favourite position, the one position family Understat lists, or his profile. The Roles column says which."),
        ("position", "Position", "The detailed position: goalkeeper, centre-back, full-back, defensive midfielder, central midfielder, attacking midfielder, wide midfielder, winger or striker.",
         "From where he started most matches. Substitute appearances carry no position, so someone who mostly comes off the bench may have none."),
        ("output", "Role score", "The average percentile across the Understat metrics that define a role.", "Always available. Understat measures only attacking output, so a defender's role score rests on build-up and set-piece threat."),
        ("score_full", "All-data score", "The same idea over a wider set that includes defending, passing and carrying from the event data.", "Only for players with event data. For defenders and goalkeepers it says far more than the role score."),
        ("tags", "Profile tags", "Labels such as Poacher or Ball-playing defender, awarded by simple rules on percentiles.", "Each tag says which numbers earned it. They are descriptions, not black-box classifications."),
        ("similarity", "Similarity", "100 minus the average percentile gap between two players across their role's key metrics.", "A similarity of 90 means that on average the two are within 10 percentile points on every metric."),
    ]},
    {"group": "Lenses and filters", "entries": [
        ("lens", "Lens", "A saved question that is only a set of filter rules.", "A lens changes nothing but the filters, and every rule it adds is shown as a chip you can read and remove. It never touches the role, the sort, the columns or the season."),
        ("rule", "Metric filter", "A condition on one metric: its value, or its percentile among role peers.", "All filters apply together. A row where the metric is unknown fails the condition: the app does not guess."),
        ("topn", "Top N", "Keep only the first N rows of the current ordering.", "Applies after every filter and follows the sort, in both the table and the map."),
    ]},
    {"group": "Event data ideas", "entries": [
        ("open_play", "Open-play passes", "Passes without throw-ins, goal kicks, corners, keeper throws and crosses.", "Restarts are not play, and crosses are chance creation, so they would distort passing ratios."),
        ("progressive", "Progressive pass", "A completed pass that moves the ball at least 10% of the pitch (about 10 metres) toward goal and ends in the attacking 60% of the pitch.", "Who moves the team up the pitch with the ball."),
        ("carry", "Carry", "The ball moved at least 3 metres with the same team on it between two events.", "Estimated from the order of events (the data has no carry event). A progressive carry advances the ball at least 10% of the pitch into the attacking 60%, or into the box."),
        ("duel", "Defensive duel", "A tackle, a challenge (beaten by a dribble) or an aerial duel as the defending side.", "This app's own definition: a tackle or a won aerial is a win, being dribbled past or losing in the air is a loss."),
        ("possession", "Possession", "The share of all passes in a team's matches that the team made.", "How WhoScored itself reports possession. It is pass share, not time on the ball."),
        ("tilt", "Field tilt", "A team's touches in the attacking third as a share of both sides' final-third touches.", "Above 50% means the team spends more of the match near the opponent's goal."),
        ("sequence", "Possession sequence", "A run of touches by one team, ended by a touch from the other.", "Long sequences mean patient play; direct attacks gain at least 40% of the pitch in 15 seconds or less."),
        ("coords", "Pitch coordinates", "Event positions run 0-100 in the acting team's attacking direction, so x = 0 is their own goal line.", "All pitch drawings show every team attacking left to right; the left wing is at the top."),
    ]},
    {"group": "How the data is kept", "entries": [
        ("layers", "Raw, silver, gold", "Raw: exactly what a website served, stored once. Silver: that, parsed into compact tables. Gold: counters worked out from silver. Metrics: worked out from the counters.", "If a definition changes, the layers above it are rebuilt from the layer below, offline. Nothing is fetched again."),
        ("local", "Local first", "Everything fetched is stored on this computer, and the browser keeps what it has loaded.", "Finished matches and seasons are never requested twice. A failed request leaves what you already have untouched and is retried later."),
        ("auto", "Automatic updates", "While the app runs, a background updater looks for new finished matches and fetches only those.", "Progress, failures and the next check are shown on the Data page."),
    ]},
]


def _where_used(key: str, level: str) -> dict:
    views = PLAYER_VIEWS if level == "player" else TEAM_VIEWS
    lenses = PLAYER_LENSES if level == "player" else TEAM_LENSES
    profile = []
    if level == "player":
        profile += [f"Role score ({r})" for r, keys in P.PROFILE.items() if key in keys]
        profile += [f"All-data score ({r})" for r, keys in P.PROFILE_FULL.items() if key in keys]
    return {
        "views": [v.label for v in views if key in v.metrics],
        "lenses": [lens.label for lens in lenses if any(r.metric == key for r in lens.rules)],
        "scores": profile,
    }


def build_dictionary() -> dict:
    """The static dictionary: metrics (with where each is used), raw sources, event counters, event types, qualifiers and concepts."""
    metrics = []
    player_short = {m.key: m.short for m in (*P.PLAYER_METRICS, *P.SCORE_METRICS)}
    for level, groups, items in (("player", P.GROUPS, (*P.PLAYER_METRICS, *P.SCORE_METRICS)), ("team", T.GROUPS, T.TEAM_METRICS)):
        label = {g.key: g.label for g in groups}
        for m in items:
            metrics.append({**m.public(), "group_label": label[m.group], "used": _where_used(m.key, level)})
    return {
        "metrics": metrics,
        "sources": [{**s, "parts": [{"name": p["name"], "fields": [{"name": n, "meaning": d} for n, d in p["fields"]]} for p in s["parts"]]} for s in SOURCES],
        "counters": [{"key": k, "meaning": v, "team_only": k in C.TEAM_ONLY} for k, v in C.COUNTERS.items()],
        "events": [{"name": name, "id": code, "meaning": EVENT_TYPE_DOC.get(name, "")} for name, code in sorted(ES.EVENT.items(), key=lambda kv: kv[1])],
        "qualifiers": [{"name": name, "meaning": QUALIFIER_DOC.get(name, "")} for name in ES.FLAGS if name in QUALIFIER_DOC],
        "concepts": [{"group": g["group"], "entries": [{"key": k, "term": t, "short": s, "long": long} for k, t, s, long in g["entries"]]} for g in CONCEPTS],
        "roles": ROLE_LABELS,
        "tags": TG.public(lambda k: player_short.get(k, k)),
        "lenses": [lens.public() for lens in (*PLAYER_LENSES, *TEAM_LENSES)],
        "views": [v.public() for v in (*PLAYER_VIEWS, *TEAM_VIEWS)],
    }
