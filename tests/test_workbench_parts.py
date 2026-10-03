"""The workbench's own pieces, each on its own: the memo, the shortlist, and that every part is wired to the same workbench."""

from __future__ import annotations

import asyncio
import time
from datetime import date
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.data.store import Store
from app.workbench import Workbench
from app.workbench.memo import DROP_ENTRIES, MAX_ENTRIES, Memo
from app.workbench.part import Part
from app.workbench.shortlist import Shortlist

PARTS = ("seasons", "ages", "links", "datasets", "shortlist", "diagnostics",
         "briefing", "league", "scout", "player", "team", "compare", "matches", "search", "dictionary", "data")


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def store(tmp_path):
    opened = Store(tmp_path / "t.sqlite")
    yield opened
    opened.close()


def memo_on(day: date = date(2026, 10, 2)) -> Memo:
    return Memo(lambda: day)


def test_a_result_is_built_once_per_version_and_again_when_an_input_changes():
    memo, built = memo_on(), []

    def build():
        built.append(1)
        return len(built)

    async def go():
        assert await memo(("k",), "v1", build) == 1
        assert await memo(("k",), "v1", build) == 1          # the same inputs: remembered
        assert await memo(("k",), "v2", build) == 2          # an input changed: built again
        assert await memo(("other",), "v2", build) == 3      # keys do not share results

    run(go())


def test_requests_that_ask_at_the_same_moment_share_one_build():
    memo, started = memo_on(), []

    def slow():
        started.append(1)
        time.sleep(0.05)
        return "done"

    async def go():
        assert await asyncio.gather(*(memo(("k",), 1, slow) for _ in range(6))) == ["done"] * 6
        assert len(started) == 1

    run(go())


def test_a_failed_build_is_not_remembered_and_the_next_request_tries_again():
    memo, attempts = memo_on(), []

    def flaky():
        attempts.append(1)
        if len(attempts) == 1:
            raise ValueError("the source was down")
        return "ok"

    async def go():
        with pytest.raises(ValueError, match="source was down"):
            await memo(("k",), 1, flaky)
        assert await memo(("k",), 1, flaky) == "ok" and len(attempts) == 2

    run(go())


def test_the_memo_forgets_the_oldest_entries_when_it_grows_and_everything_when_the_day_changes():
    today = [date(2026, 10, 2)]
    memo = Memo(lambda: today[0])

    async def go():
        for i in range(MAX_ENTRIES + 1):
            await memo((i,), 1, lambda i=i: i, threaded=False)
        assert len(memo._values) == MAX_ENTRIES + 1 - DROP_ENTRIES and (0,) not in memo._values and (MAX_ENTRIES,) in memo._values
        today[0] = date(2026, 10, 3)
        built = []
        await memo((MAX_ENTRIES,), 1, lambda: built.append(1) or "again", threaded=False)
        assert built == [1] and len(memo._values) == 1       # a view that reads the date must not outlive it

    run(go())


def test_the_shortlist_puts_the_newest_first_and_keeps_what_it_already_knew_about_a_player(store):
    shortlist = Shortlist(SimpleNamespace(store=store))
    assert shortlist.items() == [] and shortlist.ids() == set()
    shortlist.add({"id": 1, "name": "A", "team": "X", "league": "La_liga"})
    shortlist.add({"id": 2, "name": "B"})
    assert [i["id"] for i in shortlist.items()] == [2, 1]
    added = shortlist.items()[1]["added"]
    shortlist.add({"id": 1, "note": "watch him"})            # starring again only adds to what was there, and moves him up
    first = shortlist.items()[0]
    assert (first["id"], first["name"], first["team"], first["league"], first["note"], first["added"]) == (1, "A", "X", "La_liga", "watch him", added)
    assert shortlist.items()[1]["league"] == "EPL"           # a league that was never given falls back to the default
    assert shortlist.ids() == {1, 2}
    assert [i["id"] for i in shortlist.remove(2)] == [1] and shortlist.ids() == {1}


def test_every_part_of_the_workbench_is_wired_to_that_workbench(tmp_path):
    async def go():
        wb = Workbench(Settings(data_dir=tmp_path, demo=True, auto=False, min_interval=0))
        try:
            for name in PARTS:
                part = getattr(wb, name)
                assert isinstance(part, Part) and part.wb is wb, name
        finally:
            await wb.close()

    run(go())
