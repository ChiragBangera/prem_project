"""The vocabulary of WhoScored match data: event types, qualifiers and pitch geometry.

WhoScored serves Opta-style event streams. A match is ~1,500 events, each with a type, an outcome, a player, a position
on a 0-100 x 0-100 pitch (always in the acting team's attacking direction: x=0 is their own goal line, x=100 the one
they attack) and a list of *qualifiers* that say how the event happened ("Longball", "KeyPass", "BigChance" ...).

This module is the one place that knows those names. The numeric ids are WhoScored's own, so a type or qualifier we have
never seen keeps its id and nothing is silently renamed. Everything here is data, not logic.
"""

from __future__ import annotations

# ------------------------------------------------------------------ event types (name -> WhoScored's numeric id)

EVENT: dict[str, int] = {
    "Pass": 1, "OffsidePass": 2, "TakeOn": 3, "Foul": 4, "CornerAwarded": 6, "Tackle": 7, "Interception": 8,
    "Save": 10, "Claim": 11, "Clearance": 12, "MissedShots": 13, "ShotOnPost": 14, "SavedShot": 15, "Goal": 16,
    "Card": 17, "SubstitutionOff": 18, "SubstitutionOn": 19, "Start": 32, "FormationSet": 34, "End": 30,
    "FormationChange": 40, "Punch": 41, "GoodSkill": 42, "Aerial": 44, "Challenge": 45, "BallRecovery": 49,
    "Dispossessed": 50, "Error": 51, "CrossNotClaimed": 53, "Smother": 54, "OffsideProvoked": 55, "ShieldBallOpp": 56,
    "KeeperPickup": 52, "PenaltyFaced": 58, "KeeperSweeper": 59, "ChanceMissed": 60, "BallTouch": 61, "BlockedPass": 74,
    "OffsideGiven": 10000,
}
EVENT_NAME: dict[int, str] = {code: name for name, code in EVENT.items()}

E_PASS, E_TAKEON, E_FOUL, E_TACKLE, E_INTERCEPTION = EVENT["Pass"], EVENT["TakeOn"], EVENT["Foul"], EVENT["Tackle"], EVENT["Interception"]
E_SAVE, E_CLAIM, E_CLEARANCE = EVENT["Save"], EVENT["Claim"], EVENT["Clearance"]
E_MISS, E_POST, E_SAVED, E_GOAL = EVENT["MissedShots"], EVENT["ShotOnPost"], EVENT["SavedShot"], EVENT["Goal"]
E_CARD, E_SUB_OFF, E_SUB_ON = EVENT["Card"], EVENT["SubstitutionOff"], EVENT["SubstitutionOn"]
E_PUNCH, E_AERIAL, E_CHALLENGE, E_RECOVERY = EVENT["Punch"], EVENT["Aerial"], EVENT["Challenge"], EVENT["BallRecovery"]
E_DISPOSSESSED, E_ERROR, E_PICKUP, E_SWEEPER = EVENT["Dispossessed"], EVENT["Error"], EVENT["KeeperPickup"], EVENT["KeeperSweeper"]
E_BLOCKED_PASS, E_SMOTHER, E_PEN_FACED = EVENT["BlockedPass"], EVENT["Smother"], EVENT["PenaltyFaced"]
E_OFFSIDE_GIVEN, E_OFFSIDE_PROVOKED, E_BALL_TOUCH = EVENT["OffsideGiven"], EVENT["OffsideProvoked"], EVENT["BallTouch"]
E_CROSS_NOT_CLAIMED, E_CHANCE_MISSED = EVENT["CrossNotClaimed"], EVENT["ChanceMissed"]

SHOT_EVENTS = frozenset({E_MISS, E_POST, E_SAVED, E_GOAL})
DEFENSIVE_EVENTS = frozenset({E_TACKLE, E_INTERCEPTION, E_CLEARANCE, E_RECOVERY, E_BLOCKED_PASS, E_CHALLENGE})

# WhoScored period ids: 1 first half, 2 second half, (3/4 extra time), 5 penalties, 14 post-game, 16 pre-match
PLAY_PERIODS = frozenset({1, 2})
CARD_YELLOW, CARD_RED, CARD_SECOND_YELLOW = 1, 2, 3
CARD_CODE = {"Yellow": CARD_YELLOW, "Red": CARD_RED, "SecondYellow": CARD_SECOND_YELLOW}

# ------------------------------------------------------------------ qualifiers

#: Qualifiers that only say "this is so". Each becomes one bit of the event's flag word, in this order (so never reorder
#: or remove: append, and bump ``silver.SILVER_VERSION``).
FLAGS: tuple[str, ...] = (
    "Longball", "Cross", "Throughball", "HeadPass", "Chipped", "LayOff", "ThrowIn", "GoalKick", "CornerTaken", "FreekickTaken",
    "IndirectFreekickTaken", "DirectFreekick", "KeeperThrow", "FirstTouch", "FastBreak", "SetPiece", "FromCorner", "RegularPlay",
    "IndividualPlay", "Penalty", "ThrowinSetPiece", "DirectCorner", "OneOnOne", "LastMan", "BigChance", "BigChanceCreated",
    "KeyPass", "Assisted", "ShotAssist", "IntentionalAssist", "IntentionalGoalAssist", "Head", "RightFoot", "LeftFoot", "OtherBodyPart",
    "Volley", "OverRun", "Blocked", "OutfielderBlock", "BlockedCross", "SixYardBlock", "SavedOffline", "Hands", "Feet",
    "StandingSave", "DivingSave", "ParriedSafe", "ParriedDanger", "Collected", "HighClaim", "KeeperSaveInTheBox", "KeeperSaveObox",
    "KeeperSaveInSixYard", "KeeperMissed", "KeeperSaved", "KeeperWentWide", "MissLeft", "MissRight", "MissHigh", "HighLeft",
    "HighCentre", "HighRight", "LowLeft", "LowCentre", "LowRight", "SmallBoxCentre", "SmallBoxLeft", "SmallBoxRight", "BoxCentre",
    "BoxLeft", "BoxRight", "DeepBoxLeft", "DeepBoxRight", "OutOfBoxCentre", "OutOfBoxLeft", "OutOfBoxRight", "OutOfBoxDeepLeft",
    "OutOfBoxDeepRight", "ThirtyFivePlusCentre", "ThirtyFivePlusLeft", "ThirtyFivePlusRight", "FromShotOffTarget",
    "Offensive", "Defensive", "AerialFoul", "Foul", "Yellow", "Red", "SecondYellow", "VoidYellowCard", "OwnGoal", "GoalDisallowed",
    "Obstruction", "LeadingToAttempt", "LeadingToGoal", "PlayerCaughtOffside",
)
assert len(set(FLAGS)) == len(FLAGS) and len(FLAGS) <= 106, "flags must be unique and fit two 53-bit words"
FLAG_BIT: dict[str, int] = {name: i for i, name in enumerate(FLAGS)}
WORD_BITS = 53  # a word stays an exact integer in JavaScript too
assert len(FLAGS) <= 2 * WORD_BITS


def flag_mask(*names: str) -> tuple[int, int]:
    """The (low word, high word) mask that has the bits of these qualifier names set."""
    lo = hi = 0
    for name in names:
        bit = FLAG_BIT[name]
        if bit < WORD_BITS:
            lo |= 1 << bit
        else:
            hi |= 1 << (bit - WORD_BITS)
    return lo, hi


# Qualifiers that carry a value are read into their own columns (see silver.py): where the pass ends, how long it was,
# where a shot was aimed, where it was blocked, which event a save belongs to, and which part of the pitch the event was in.
VALUE_QUALIFIERS = frozenset({
    "Zone", "PassEndX", "PassEndY", "Length", "Angle", "GoalMouthY", "GoalMouthZ", "BlockedX", "BlockedY",
    "RelatedEventId", "OppositeRelatedEvent",
})
IGNORED_QUALIFIERS = frozenset({
    "PlayerPosition", "JerseyNumber", "FormationSlot", "InvolvedPlayers", "CaptainPlayerId", "TeamPlayerFormation", "TeamFormation",
})  # these live on substitution / formation events and are read into the lineup instead
ZONE_CODE = {"Back": 1, "Left": 2, "Center": 3, "Right": 4}

# ------------------------------------------------------------------ pitch geometry (WhoScored 0-100 units)

PITCH_LENGTH_M, PITCH_WIDTH_M = 105.0, 68.0
THIRD = 100.0 / 3
FINAL_THIRD_X = 100.0 - THIRD          # x >= 66.7
DEF_THIRD_X = THIRD                    # x < 33.3
BOX_X = 83.3                           # the penalty area starts 16.5 m from the goal line
BOX_Y = (21.1, 78.9)                   # ...and is 40.3 m wide
SIX_YARD_X = 94.2
SIX_YARD_Y = (36.8, 63.2)
OWN_HALF_X = 50.0
FORWARD_MIN = 5.0                      # a forward pass advances the ball at least this much (~5 m)
PROGRESSIVE_MIN = 10.0                 # a progressive pass advances it at least this much (~10 m) ...
PROGRESSIVE_END_X = 40.0               # ... and ends in the attacking 60 % of the pitch
LONG_PASS_M = 32.0                     # Opta's "long ball" qualifier is the primary source; this is the distance cut-off for the rest


def metres_x(units: float) -> float:
    return units * PITCH_LENGTH_M / 100.0


def metres_y(units: float) -> float:
    return units * PITCH_WIDTH_M / 100.0


def in_box(x: float | None, y: float | None) -> bool:
    return x is not None and y is not None and x >= BOX_X and BOX_Y[0] <= y <= BOX_Y[1]


def in_six_yard_box(x: float | None, y: float | None) -> bool:
    return x is not None and y is not None and x >= SIX_YARD_X and SIX_YARD_Y[0] <= y <= SIX_YARD_Y[1]


# ------------------------------------------------------------------ positions (WhoScored lineup codes -> a plain taxonomy)

#: The detailed position taxonomy used for filters: where a player spends his minutes, not who he is.
POSITION_LABEL = {
    "GK": "Goalkeeper", "CB": "Centre-back", "FB": "Full-back", "DM": "Defensive midfielder", "CM": "Central midfielder",
    "AM": "Attacking midfielder", "WM": "Wide midfielder", "W": "Winger", "ST": "Striker",
}
POSITION_ORDER = ("GK", "CB", "FB", "DM", "CM", "AM", "WM", "W", "ST")
# Understat and WhoScored use the same lineup codes (DC, DR, AML ...)
POSITION_CODE = {
    "GK": "GK", "DC": "CB", "DL": "FB", "DR": "FB", "DMC": "DM", "DML": "DM", "DMR": "DM", "MC": "CM", "ML": "WM", "MR": "WM",
    "AMC": "AM", "AML": "W", "AMR": "W", "FW": "ST", "FWL": "W", "FWR": "W",  # FWL / FWR are the wide forwards of a front three
}
POSITION_GROUP = {"GK": "GK", "CB": "DEF", "FB": "DEF", "DM": "MID", "CM": "MID", "AM": "MID", "WM": "MID", "W": "ATT", "ST": "ATT"}
