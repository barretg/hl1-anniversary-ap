"""The Map Randomization option group (transitions mode foundation).

Nothing is supported in transitions mode yet, so these cover validation only:
hub mode's fallbacks, the refusal while no chapter is supported, and, with a
supported set patched in, the goal chapter requirement.
"""

import unittest
from argparse import Namespace
from unittest import mock

from BaseClasses import CollectionState, MultiWorld
from Options import OptionError
from worlds import AutoWorld

from . import HalfLifeTestBase
from .. import GAME_NAME
from ..options import MapShuffle


def generate_early(options: dict) -> AutoWorld.World:
    multiworld = MultiWorld(1)
    multiworld.game[1] = GAME_NAME
    multiworld.player_name = {1: "Tester"}
    multiworld.set_seed(0)
    args = Namespace()
    world_type = AutoWorld.AutoWorldRegister.world_types[GAME_NAME]
    for name, option in world_type.options_dataclass.type_hints.items():
        setattr(args, name, {1: option.from_any(options.get(name, option.default))})
    multiworld.set_options(args)
    multiworld.state = CollectionState(multiworld)
    world = multiworld.worlds[1]
    world.generate_early()
    return world


SUPPORTED = {
    "half_life": ["Anomalous Materials", "Nihilanth"],
    "opposing_force": [],
    "blue_shift": [],
}


class TestHubModeFallsBack(HalfLifeTestBase):
    options = {"map_shuffle": "total"}

    def test_total_becomes_chapter_maps(self) -> None:
        self.assertEqual(self.world.options.map_shuffle.value,
                         MapShuffle.option_chapter_maps)


class TestTransitionsValidation(unittest.TestCase):
    def test_refused_while_nothing_is_supported(self) -> None:
        with self.assertRaisesRegex(OptionError, "no chapters are supported"):
            generate_early({"progression_mode": "transitions"})

    @mock.patch.dict("worlds.half_life.SUPPORTED_CHAPTER_NAMES", SUPPORTED)
    def test_needs_a_goal_chapter(self) -> None:
        with self.assertRaisesRegex(OptionError, "goal chapter"):
            generate_early({"progression_mode": "transitions",
                            "half_life_chapters": ["Anomalous Materials"]})

    @mock.patch.dict("worlds.half_life.SUPPORTED_CHAPTER_NAMES", SUPPORTED)
    def test_unsupported_chapter_is_refused(self) -> None:
        with self.assertRaisesRegex(OptionError, "does not support"):
            generate_early({"progression_mode": "transitions",
                            "half_life_chapters": ["Nihilanth", "Surface Tension"]})

    @mock.patch.dict("worlds.half_life.SUPPORTED_CHAPTER_NAMES", SUPPORTED)
    def test_included_chapters_are_recorded(self) -> None:
        world = generate_early({"progression_mode": "transitions",
                                "half_life_chapters": ["Anomalous Materials",
                                                       "Nihilanth"]})
        self.assertEqual(world.transition_chapters, ["c1a0", "c4a3"])
