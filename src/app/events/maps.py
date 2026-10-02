"""Pitch maps from stored events: where a player or a team touched the ball, passed it, defended, carried it.

Every function reads silver matches (see :mod:`app.events.silver`) and returns small, plain structures the browser draws:

* **display coordinates**: x runs 0-1000 in the acting team's attacking direction (their own goal line at 0), y runs 0-1000 downward with
  the team's left wing at the top, so a map is a straight plot with no flipping. Every team attacks left to right;
* **grids** are counts per cell (24 columns by 16 rows), row-major; the browser smooths and colours them;
* **lines** and **points** carry integers only and are capped (deterministically thinned) so a payload stays small.

Nothing here is a model: it is selection and counting. Inferred things say so (a pass network's receiver is the next team-mate to
touch the ball, since the data has no receiver).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from . import counters as C
from . import schema as S
from .silver import FL_TOUCH, Match

NX, NY = 24, 16
MAX_LINES = 900      # passes / carries drawn as lines
MAX_POINTS = 1500    # defensive actions and similar

# pass flags (bit set) the browser can filter on
PF_PROG, PF_KEY, PF_BOX, PF_F3, PF_LONG, PF_CROSS, PF_THROUGH, PF_ASSIST, PF_RESTART = 1, 2, 4, 8, 16, 32, 64, 128, 256
# defensive point types
D_TACKLE, D_INTERCEPT, D_CLEAR, D_BLOCK_PASS, D_BLOCK_SHOT, D_RECOVER, D_BEATEN, D_AERIAL = 1, 2, 3, 4, 5, 6, 7, 8
# goalkeeper action types
G_SAVE, G_CLAIM, G_PUNCH, G_SWEEP, G_PICKUP, G_SMOTHER = 1, 2, 3, 4, 5, 6


def _disp(x: int, y: int) -> tuple[int, int]:
    """WhoScored tenths -> display tenths: y flipped so the left wing is at the top."""
    return x, 1000 - y


def _cell(x: int, y: int) -> int:
    cx = min(NX - 1, max(0, x * NX // 1001))
    cy = min(NY - 1, max(0, y * NY // 1001))
    return cy * NX + cx


def thin(items: list, limit: int) -> list:
    """At most ``limit`` items, evenly spread (so a thinned map keeps its shape and the same input always gives the same output)."""
    if len(items) <= limit:
        return items
    step = len(items) / limit
    return [items[int(i * step)] for i in range(limit)]


class Selection:
    """Which events of a match count: one player's, or one team's."""

    def __init__(self, *, player: int | None = None, team: str | None = None):
        self.player, self.team = player, team

    def team_index(self, m: Match) -> int | None:
        if self.team is not None:
            for i, t in enumerate(m.teams):
                if t["name"] == self.team:
                    return i
            return None
        if self.player is not None and self.player in m.by_id:
            return m.by_id[self.player]["tm"]
        return None

    def takes(self, m: Match, i: int, tm: int) -> bool:
        if m.ev["tm"][i] != tm:
            return False
        return self.player is None or m.ev["p"][i] == self.player


def _empty() -> dict:
    return {"touches": [0] * (NX * NY), "pass_from": [0] * (NX * NY), "def_grid": [0] * (NX * NY), "recover_grid": [0] * (NX * NY),
            "passes": [], "def": [], "takeons": [], "carries": [], "gk": [], "n": {"touches": 0, "passes": 0, "pass_ok": 0, "def": 0}}


def collect(matches: Iterable[tuple[int, Match]], selection: Selection) -> dict:
    """The map layers for a selection over several matches. ``matches`` pairs a number (shown on the map as the match index) with a match."""
    out = _empty()
    for index, m in matches:
        tm = selection.team_index(m)
        if tm is None:
            continue
        ev = m.ev
        q = [ev["q0"][i] | (ev["q1"][i] << S.WORD_BITS) for i in range(m.n)]
        for i in m.play_indices():
            if not selection.takes(m, i, tm):
                continue
            code, ok = ev["t"][i], ev["o"][i]
            x, y = ev["x"][i], ev["y"][i]
            if x < 0 or y < 0:
                continue
            dx, dy = _disp(x, y)
            minute = ev["em"][i]
            if ev["fl"][i] & FL_TOUCH:
                out["touches"][_cell(dx, dy)] += 1
                out["n"]["touches"] += 1
            qq = q[i]
            if code == S.E_PASS:
                ex, ey = ev["ex"][i], ev["ey"][i]
                if ex < 0 or ey < 0:
                    continue
                edx, edy = _disp(ex, ey)
                flags = 0
                restart = bool(qq & C.M_RESTART)
                gain = (ex - x) / 10.0
                if ok and not restart and not qq & C.M_CROSS and gain >= S.PROGRESSIVE_MIN and ex / 10.0 >= S.PROGRESSIVE_END_X:
                    flags |= PF_PROG
                if qq & C.M_KEY:
                    flags |= PF_KEY
                if S.in_box(ex / 10.0, ey / 10.0) and not S.in_box(x / 10.0, y / 10.0):
                    flags |= PF_BOX
                if x / 10.0 < S.FINAL_THIRD_X <= ex / 10.0:
                    flags |= PF_F3
                if qq & C.M_LONG:
                    flags |= PF_LONG
                if qq & C.M_CROSS:
                    flags |= PF_CROSS
                if qq & C.M_THROUGH:
                    flags |= PF_THROUGH
                if restart:
                    flags |= PF_RESTART
                out["passes"].append([dx, dy, edx, edy, ok, flags, minute, index])
                if not restart:
                    out["n"]["passes"] += 1
                    out["n"]["pass_ok"] += ok
                    if ok:
                        out["pass_from"][_cell(dx, dy)] += 1
            elif code in (S.E_TACKLE, S.E_INTERCEPTION, S.E_CLEARANCE, S.E_BLOCKED_PASS, S.E_RECOVERY, S.E_CHALLENGE) or (code == S.E_SAVE and qq & C.M_OUTFIELD_BLOCK) \
                    or (code == S.E_AERIAL and qq & C.M_DEFENSIVE):
                kind = {S.E_TACKLE: D_TACKLE, S.E_INTERCEPTION: D_INTERCEPT, S.E_CLEARANCE: D_CLEAR, S.E_BLOCKED_PASS: D_BLOCK_PASS, S.E_RECOVERY: D_RECOVER,
                        S.E_CHALLENGE: D_BEATEN, S.E_SAVE: D_BLOCK_SHOT, S.E_AERIAL: D_AERIAL}[code]
                out["def"].append([dx, dy, kind, ok, minute, index])
                out["n"]["def"] += 1
                out["def_grid"][_cell(dx, dy)] += 1
                if code == S.E_RECOVERY:
                    out["recover_grid"][_cell(dx, dy)] += 1
            elif code == S.E_TAKEON:
                out["takeons"].append([dx, dy, ok, minute, index])
            elif code in (S.E_SAVE, S.E_CLAIM, S.E_PUNCH, S.E_SWEEPER, S.E_PICKUP, S.E_SMOTHER):
                kind = {S.E_SAVE: G_SAVE, S.E_CLAIM: G_CLAIM, S.E_PUNCH: G_PUNCH, S.E_SWEEPER: G_SWEEP, S.E_PICKUP: G_PICKUP, S.E_SMOTHER: G_SMOTHER}[code]
                out["gk"].append([dx, dy, kind, ok, minute, index])
        for pid, t, x0, y0, x1, y1, i in C.carries(m):
            if t != tm or (selection.player is not None and pid != selection.player):
                continue
            prog = (x1 - x0) >= S.PROGRESSIVE_MIN and x1 >= S.PROGRESSIVE_END_X
            a, b = _disp(int(x0 * 10), int(y0 * 10)), _disp(int(x1 * 10), int(y1 * 10))
            out["carries"].append([a[0], a[1], b[0], b[1], 1 if prog else 0, ev["em"][i], index])
    out["passes"] = thin(out["passes"], MAX_LINES * 3)
    out["carries"] = thin(out["carries"], MAX_LINES)
    out["def"] = thin(out["def"], MAX_POINTS)
    return out


def lines_view(layer: dict, *, flags: int = 0, limit: int = MAX_LINES) -> list:
    """The pass lines that carry any of ``flags`` (all open-play passes when 0), thinned to ``limit``."""
    picked = [p for p in layer["passes"] if (not flags and not p[5] & PF_RESTART) or p[5] & flags]
    return thin(picked, limit)


def pass_network(matches: Iterable[tuple[int, Match]], team: str, *, max_gap: int = 8, min_edge: int = 3) -> dict:
    """Who passes to whom, and where each player operates, for one team over several matches.

    A pass is assumed to reach the next team-mate to touch the ball within ``max_gap`` seconds with no opponent touch in between; the
    data has no receiver, so this is an estimate. Nodes sit at the average position of each player's touches.
    """
    nodes: dict[int, dict] = {}
    edges: dict[tuple[int, int], int] = defaultdict(int)
    total_matches = 0
    for _index, m in matches:
        tm = Selection(team=team).team_index(m)
        if tm is None:
            continue
        total_matches += 1
        ev = m.ev
        touches = [i for i in m.play_indices() if ev["fl"][i] & FL_TOUCH and ev["x"][i] >= 0 and ev["p"][i]]
        for i in touches:
            if ev["tm"][i] == tm:
                pid = ev["p"][i]
                n = nodes.setdefault(pid, {"id": pid, "name": m.by_id.get(pid, {}).get("name", ""), "x": 0.0, "y": 0.0, "touches": 0})
                n["x"] += ev["x"][i]
                n["y"] += 1000 - ev["y"][i]
                n["touches"] += 1
        for pos, i in enumerate(touches):
            if ev["tm"][i] != tm or ev["t"][i] != S.E_PASS or not ev["o"][i]:
                continue
            if (ev["q0"][i] | (ev["q1"][i] << S.WORD_BITS)) & C.M_RESTART:
                continue
            t0 = ev["mi"][i] * 60 + ev["se"][i]
            for j in touches[pos + 1: pos + 6]:
                if ev["pe"][j] != ev["pe"][i]:
                    break
                if ev["mi"][j] * 60 + ev["se"][j] - t0 > max_gap:
                    break
                if ev["tm"][j] != tm:
                    break  # the other side touched it: the move ended
                if ev["p"][j] != ev["p"][i]:
                    edges[(ev["p"][i], ev["p"][j])] += 1
                    break
    played = max(1, total_matches)
    keep = {pid for pid, n in nodes.items() if n["touches"] >= 8 * played}
    out_nodes = [{"id": n["id"], "name": n["name"], "x": round(n["x"] / n["touches"]), "y": round(n["y"] / n["touches"]), "touches": n["touches"]} for n in nodes.values() if n["id"] in keep]
    pairs: dict[tuple[int, int], int] = defaultdict(int)
    for (a, b), c in edges.items():
        if a in keep and b in keep:
            pairs[(min(a, b), max(a, b))] += c
    out_edges = [{"a": a, "b": b, "n": c} for (a, b), c in pairs.items() if c >= min_edge * played]
    return {"nodes": sorted(out_nodes, key=lambda n: -n["touches"]), "edges": sorted(out_edges, key=lambda e: -e["n"]), "matches": total_matches}


def zone_shares(layer: dict) -> dict:
    """Touches split into thirds (own, middle, final) and three lanes (left, centre, right), as counts."""
    thirds, lanes = [0, 0, 0], [0, 0, 0]
    for idx, c in enumerate(layer["touches"]):
        cx, cy = idx % NX, idx // NX
        thirds[min(2, cx * 3 // NX)] += c
        lanes[min(2, cy * 3 // NY)] += c
    return {"thirds": thirds, "lanes": lanes}
