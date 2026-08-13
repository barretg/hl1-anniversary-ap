"""World tests.

These run under an Archipelago source checkout (`pytest test/general` picks the
world up automatically, and these add world-specific cases on top). They are
excluded from the packaged .apworld by tools/build_apworld.py.
"""

from test.bases import WorldTestBase

from .. import GAME_NAME


class HalfLifeTestBase(WorldTestBase):
    game = GAME_NAME
    player: int = 1
