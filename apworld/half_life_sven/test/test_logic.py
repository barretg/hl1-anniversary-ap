"""World-specific logic tests.

Run these from an Archipelago source checkout:

    pytest test/general -k half_life
    pytest worlds/half_life_sven/test
"""

from . import HalfLifeSvenTestBase
from ..data import CHAPTERS, UNLOCKABLE_CHAPTERS
from ..items import chapter_unlock_items, unlock_item_for_chapter


class TestDefaults(HalfLifeSvenTestBase):
    options = {}

    def test_exactly_one_mission_is_precollected(self) -> None:
        precollected = [
            item for item in self.multiworld.precollected_items[self.player]
            if item.name in chapter_unlock_items
        ]
        self.assertEqual(len(precollected), 1)

    def test_precollected_unlock_is_not_also_in_the_pool(self) -> None:
        starting = {
            item.name for item in self.multiworld.precollected_items[self.player]
        }
        pool = [item.name for item in self.multiworld.itempool if item.player == self.player]
        for name in starting & set(chapter_unlock_items):
            self.assertNotIn(name, pool)

    def test_goal_mission_has_no_unlock_item(self) -> None:
        goal = next(chapter for chapter in CHAPTERS if chapter["is_goal"])
        self.assertNotIn(goal["key"], unlock_item_for_chapter)

    def test_crowbar_is_not_an_item(self) -> None:
        names = self.multiworld.worlds[self.player].item_name_to_id
        self.assertNotIn("Crowbar", names)

    def test_victory_needs_every_mission_by_default(self) -> None:
        """With the default missions_required, holding one mission short fails."""
        world = self.multiworld.worlds[self.player]
        self.assertEqual(
            world.options.missions_required.value, len(UNLOCKABLE_CHAPTERS)
        )

        state = self.multiworld.get_all_state(False)
        self.assertTrue(self.multiworld.completion_condition[self.player](state))


class TestMinimumMissions(HalfLifeSvenTestBase):
    options = {"missions_required": 1}

    def test_goal_opens_after_a_single_mission(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertEqual(world.options.missions_required.value, 1)
        state = self.multiworld.get_all_state(False)
        self.assertTrue(self.multiworld.completion_condition[self.player](state))


class TestEquipmentShuffled(HalfLifeSvenTestBase):
    options = {"shuffle_hev_suit": True, "shuffle_longjump": True}

    def test_equipment_is_in_the_pool(self) -> None:
        pool = {item.name for item in self.multiworld.itempool if item.player == self.player}
        self.assertIn("HEV Suit", pool)
        self.assertIn("Long Jump Module", pool)

    def test_xen_requires_the_long_jump_module(self) -> None:
        """Xen is unreachable on its unlock alone once the module is shuffled."""
        world = self.multiworld.worlds[self.player]
        state = self.multiworld.get_all_state(False)
        state.remove(world.create_item("Long Jump Module"))
        state.sweep_for_advancements()

        self.assertFalse(self.can_reach_entrance("Enter Xen", state))


class TestEquipmentNotShuffled(HalfLifeSvenTestBase):
    options = {"shuffle_hev_suit": False, "shuffle_longjump": False}

    def test_equipment_is_absent_from_the_pool(self) -> None:
        pool = {item.name for item in self.multiworld.itempool if item.player == self.player}
        self.assertNotIn("HEV Suit", pool)
        self.assertNotIn("Long Jump Module", pool)

    def test_xen_is_reachable_without_equipment(self) -> None:
        state = self.multiworld.get_all_state(False)
        self.assertTrue(self.can_reach_entrance("Enter Xen", state))


class TestLooseLogic(HalfLifeSvenTestBase):
    options = {"logic_difficulty": "loose"}

    def test_weapon_gates_are_dropped(self) -> None:
        """Loose logic lets you into a late mission on its unlock alone."""
        world = self.multiworld.worlds[self.player]
        state = self.multiworld.get_state(self.multiworld)
        state.collect(world.create_item(unlock_item_for_chapter["surface_tension"]), True)

        self.assertTrue(self.can_reach_entrance("Enter Surface Tension", state))
