"""Pitch-map payloads: what the Team and Player pages draw from a set of stored matches."""

from __future__ import annotations

from app.events import maps as event_maps
from app.events.store import EventStore


def pick_matches(log: list[dict], venue: str, last: int | None) -> list[dict]:
    """A team's match log narrowed to home or away games and to its last few."""
    rows = [r for r in log if venue == "all" or (venue == "h") == r["home"]]
    return rows[-last:] if last else rows


def map_payload(events: EventStore, code: str, season: int, matches: list[tuple[int, int]], selection, *, team: str, extra: dict) -> dict:
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
        "zones": event_maps.zone_shares(layer), "network": event_maps.pass_network(silver, team) if selection.player is None else None, **extra,
    }
