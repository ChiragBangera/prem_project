"""Pitch-map payloads: what the Team and Player pages draw from a set of stored matches."""

from __future__ import annotations

from app.events import maps as event_maps
from app.events import movestats
from app.events.store import EventStore


def pick_matches(log: list[dict], venue: str, last: int | None) -> list[dict]:
    """A team's match log narrowed to home or away games and to its last few."""
    rows = [r for r in log if venue == "all" or (venue == "h") == r["home"]]
    return rows[-last:] if last else rows


def xg_reader(info: dict, pages: dict):
    """``match -> {shot event index: Understat's xG}`` for a season's links (``info`` from the workbench's links, ``pages`` the stored
    Understat match pages). A match Understat has not published, or whose page is not stored, gives nothing: its xG is unknown."""
    from app.analytics.match_centre import shot_xg

    fixtures, alias = info["fixtures"], info["alias"]

    def read(m) -> dict[int, float]:
        fixture = fixtures.get(m.game)
        page = pages.get(fixture.id) if fixture is not None else None
        if fixture is None or page is None:
            return {}
        home = alias.get(m.teams[0]["name"])
        return shot_xg(m, page.shots, flip=home is not None and home != fixture.home)

    return read


def map_payload(events: EventStore, code: str, season: int, matches: list[tuple[int, int]], selection, *, team: str, extra: dict, xg_of=None) -> dict:
    """Grids, pass lines, defensive actions, carries and the pass network of the given ``(index, game)`` matches, for one team or one player."""
    silver = []
    for i, game in matches:
        match = events.silver(code, season, game)
        if match is not None:
            silver.append((i, match))
    layer = event_maps.collect(silver, selection)
    lines = {name: event_maps.lines_view(layer, flags=flag) for name, flag in
             (("prog", event_maps.PF_PROG), ("key", event_maps.PF_KEY), ("box", event_maps.PF_BOX), ("f3", event_maps.PF_F3), ("long", event_maps.PF_LONG),
              ("cross", event_maps.PF_CROSS), ("through", event_maps.PF_THROUGH))}
    # the passes that were not completed, thinned on their own: a map of just those should not be what is left of a sample made of everything
    lost = {name: event_maps.lines_view(layer, flags=flag, ok=False) for name, flag in
            (("key", event_maps.PF_KEY), ("box", event_maps.PF_BOX), ("f3", event_maps.PF_F3), ("long", event_maps.PF_LONG), ("cross", event_maps.PF_CROSS), ("through", event_maps.PF_THROUGH))}
    lost["all"] = event_maps.lines_view(layer, ok=False, limit=600)
    return {
        "available": True, "dims": [event_maps.NX, event_maps.NY], "n": len(silver), "counts": layer["n"],
        "grids": {"touches": layer["touches"], "pass_from": layer["pass_from"], "def": layer["def_grid"], "recover": layer["recover_grid"]},
        "lines": lines, "lost": lost, "all_passes": event_maps.lines_view(layer, limit=600), "carries": layer["carries"], "def": layer["def"], "takeons": layer["takeons"], "gk": layer["gk"],
        "zones": event_maps.zone_shares(layer), "network": event_maps.pass_network(silver, team) if selection.player is None else None,
        "goal_mouth": event_maps.goal_mouth(silver, selection),
        "names": {str(p["id"]): p["name"] for _i, m in silver for p in m.players} if selection.player is None else None,
        # the same moves the Match page lists, summed: how the team's end and where it loses the ball; for a player, where he lost it and won it
        "moves": (movestats.team_moves([m for _i, m in silver], team, xg_of=xg_of) if selection.player is None
                  else movestats.player_moves(silver, selection.player, xg_of=xg_of)), **extra,
    }
