"""Your shortlist: the players you starred, with a note each. It lives in the store and survives everything but a deliberate delete."""

from __future__ import annotations

import time

from app.leagues import DEFAULT_LEAGUE
from app.workbench.part import Part

KEY = "shortlist"


class Shortlist(Part):
    def items(self) -> list[dict]:
        return self.store.kv_get(KEY, [])

    def ids(self) -> set[int]:
        return {item["id"] for item in self.items()}

    def add(self, item: dict) -> list[dict]:
        pid = int(item["id"])
        items = [i for i in self.items() if i["id"] != pid]
        existing = next((i for i in self.items() if i["id"] == pid), {})
        items.insert(0, {"id": pid, "name": item.get("name", existing.get("name", "")), "team": item.get("team", existing.get("team", "")),
                         "league": item.get("league", existing.get("league", DEFAULT_LEAGUE)), "note": item.get("note", existing.get("note", "")),
                         "added": existing.get("added") or int(time.time())})
        self.store.kv_set(KEY, items)
        return items

    def remove(self, player_id: int) -> list[dict]:
        items = [i for i in self.items() if i["id"] != player_id]
        self.store.kv_set(KEY, items)
        return items
