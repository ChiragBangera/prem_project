"""Synthetic, clearly-labelled demo world (real club names, fictional players)."""

from .provider import DemoProvider
from .world import FIRST_DEMO_SEASON

#: Bump when the world's data changes in a way an older stored copy would disagree with (a score without its scorer, say).
WORLD_VERSION = 3

__all__ = ["DemoProvider", "FIRST_DEMO_SEASON", "WORLD_VERSION"]
