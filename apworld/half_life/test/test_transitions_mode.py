"""Transitions mode generation (TRANSITION_RANDO.md 9.2 step 5).

No chapter is supported yet, so each case patches a supported set in for the
length of its generation, and lists its chapters explicitly. The default
world tests (everything reachable with all items, something reachable with
none, a fill that completes) run on each.
"""

import unittest
from unittest import mock

from . import HalfLifeTestBase
from ..transitions import ENDING_MAPS, TRANSITIONS_BY_ID, Plan

FIRST_STEP = ["Anomalous Materials", "Nihilanth"]
SEVERAL = ["Anomalous Materials", "Unforeseen Consequences", "Office Complex",
           "We've Got Hostiles", "Power Up", "Nihilanth"]
SUPPORTED = {"half_life": [
    "Anomalous Materials", "Unforeseen Consequences", "Office Complex",
    "We've Got Hostiles", "Power Up", "Nihilanth"],
    "opposing_force": [], "blue_shift": []}


class TransitionsTestBase(HalfLifeTestBase):
    chapters: list[str] = FIRST_STEP
    shuffle = "total"
    difficulty = "standard"
    reverse = False

    def setUp(self) -> None:
        patch = mock.patch.dict("worlds.half_life.SUPPORTED_CHAPTER_NAMES", SUPPORTED)
        patch.start()
        self.addCleanup(patch.stop)
        self.options = {"progression_mode": "transitions", "map_shuffle": self.shuffle,
                        "generation_difficulty": self.difficulty,
                        "allow_reverse": self.reverse,
                        "half_life_chapters": self.chapters}
        super().setUp()

    @property
    def plan(self) -> Plan:
        return self.world.transition_plan

    def test_every_transition_is_accounted_for_once(self) -> None:
        plan = self.plan
        seen: list[str] = [t for pair in plan.pairs for t in pair]
        seen += plan.inert + list(plan.one_way)
        self.assertEqual(sorted(seen), sorted(plan.pool))
        for tid in plan.pool:
            self.assertNotIn(TRANSITIONS_BY_ID[tid]["to"], ENDING_MAPS)

    def test_every_exit_is_connected(self) -> None:
        for tid, exit_ in self.world.transition_exits.items():
            self.assertIsNotNone(exit_.connected_region, tid)

    def test_no_unlock_items(self) -> None:
        names = {item.name for item in self.multiworld.itempool}
        self.assertFalse(any(name.endswith("Unlock") for name in names))

    def test_slot_data_names_the_world(self) -> None:
        data = self.world.fill_slot_data()
        self.assertEqual(data["progression_mode"], "transitions")
        self.assertEqual(data["start_map"], self.plan.start_map)
        self.assertIn(data["final_boss"], self.plan.bosses)
        for a, b in data["transition_pairs"]:
            self.assertNotEqual(TRANSITIONS_BY_ID[a].get("partner"), b)


class TestFirstStepOff(TransitionsTestBase):
    shuffle = "off"


class TestFirstStepArea(TransitionsTestBase):
    shuffle = "area"


class TestFirstStepChapterMaps(TransitionsTestBase):
    shuffle = "chapter_maps"


class TestFirstStepTotal(TransitionsTestBase):
    shuffle = "total"

    def test_start_is_the_first_map(self) -> None:
        self.assertEqual(self.plan.start_map, "c1a0")
        self.assertIn("c1a0:0", self.plan.inert)


class TestSeveralTotal(TransitionsTestBase):
    chapters = SEVERAL
    shuffle = "total"


class TestSeveralChapterMaps(TransitionsTestBase):
    chapters = SEVERAL
    shuffle = "chapter_maps"

    def test_chapters_keep_their_own_maps_inside(self) -> None:
        from ..transitions import MAP_CHAPTER, cross_chapter
        for a, b in self.plan.pairs:
            ta, tb = TRANSITIONS_BY_ID[a], TRANSITIONS_BY_ID[b]
            if not cross_chapter(ta) and not cross_chapter(tb):
                self.assertEqual(MAP_CHAPTER[ta["map"]], MAP_CHAPTER[tb["map"]], (a, b))


class TestSeveralTotalReverse(TransitionsTestBase):
    chapters = SEVERAL
    reverse = True


class TestSeveralAreaReverse(TransitionsTestBase):
    chapters = SEVERAL
    shuffle = "area"
    reverse = True


class TestSeveralChaotic(TransitionsTestBase):
    chapters = SEVERAL
    shuffle = "total"
    difficulty = "chaotic"


class TestTrackerRebuildsThePairs(TransitionsTestBase):
    chapters = SEVERAL
    shuffle = "total"

    def test_passthrough_connects_the_same_way(self) -> None:
        from test.general import gen_steps
        from BaseClasses import MultiWorld
        from argparse import Namespace
        from worlds import AutoWorld

        slot = self.world.fill_slot_data()
        multiworld = MultiWorld(1)
        multiworld.game[1] = self.game
        multiworld.player_name = {1: "Tester"}
        multiworld.set_seed(12345)
        args = Namespace()
        for name, option in self.world.options_dataclass.type_hints.items():
            setattr(args, name, {1: option.from_any(option.default)})
        multiworld.set_options(args)
        multiworld.re_gen_passthrough = {self.game: slot}
        for step in gen_steps:
            if step == "pre_fill":
                break
            AutoWorld.call_all(multiworld, step)
        again = multiworld.worlds[1]
        self.assertEqual(again.transition_plan.start_map, self.plan.start_map)
        mine = {tid: e.connected_region.name for tid, e in self.world.transition_exits.items()}
        theirs = {tid: e.connected_region.name for tid, e in again.transition_exits.items()}
        self.assertEqual(mine, theirs)


class TestWayBack(unittest.TestCase):
    """A one-way edge's reverse (3.3): free with a teleporter, absent with
    another route back, and gated on the item that crosses it back."""

    def world(self, pool: set[str]):
        from types import SimpleNamespace

        from ..options import LogicDifficulty
        return SimpleNamespace(player=1, available_item_names=pool, options=SimpleNamespace(
            logic_difficulty=SimpleNamespace(value=LogicDifficulty.option_loose)))

    def test_each_way_back(self) -> None:
        from ..transitions import way_back_rule

        world = self.world({"Long Jump Module"})
        edge = {"from": "a", "to": "b", "one_way": True}
        self.assertIsNone(way_back_rule(world, edge))
        self.assertIs(way_back_rule(world, dict(edge, way_back="alt")), False)
        rule = way_back_rule(world, dict(edge, way_back="item", back=["longjump"]))
        has = mock.Mock(**{"has_any.return_value": True})
        lacks = mock.Mock(**{"has_any.return_value": False})
        self.assertTrue(rule(has))
        self.assertFalse(rule(lacks))

    def test_an_item_not_in_the_pool_crosses_nothing_back(self) -> None:
        from ..transitions import way_back_rule

        edge = {"from": "a", "to": "b", "one_way": True, "way_back": "item", "back": ["longjump"]}
        self.assertIs(way_back_rule(self.world(set()), edge), False)
