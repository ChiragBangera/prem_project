"""The base of every part of the workbench."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from app.config import Settings
    from app.data.matchbook import MatchBook
    from app.data.repository import Repository
    from app.data.store import Store
    from app.events.store import EventStore
    from app.workbench.core import Workbench


class Part:
    """One part of the workbench: it owns one area of the logic and reaches the shared runtime (store, repository, caches) through ``wb``.

    The shortcuts below are the collaborators nearly every part uses; anything else is read from ``self.wb`` where it is needed.
    """

    def __init__(self, wb: Workbench) -> None:
        self.wb = wb

    @property
    def settings(self) -> Settings:
        return self.wb.settings

    @property
    def store(self) -> Store:
        return self.wb.store

    @property
    def repo(self) -> Repository:
        return self.wb.repo

    @property
    def events(self) -> EventStore:
        return self.wb.events

    @property
    def matchbook(self) -> MatchBook:
        return self.wb.matchbook

    @property
    def today(self) -> date:
        return self.wb.today
