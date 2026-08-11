"""World-specific logic tests.

Run these from an Archipelago source checkout:

    pytest test/general -k half_life
    pytest worlds/half_life_sven/test
"""

from . import HalfLifeSvenTestBase
from ..data import CHAPTERS, CHAPTERS_BY_KEY, UNLOCKABLE_CHAPTERS
from ..items import chapter_unlock_items, unlock_item_for_chapter


class StartingMissionMixin:
    """The starting mission must be enterable with nothing but its unlock.

    Every location sits behind a mission entrance, so a gated starting mission
    means an empty sphere one and a fill failure. Asserted for each option set,
    because which missions qualify depends on logic difficulty and on whether the
    suit and long jump module are shuffled.
    """

    def test_the_starting_mission_is_reachable_from_nothing(self) -> None:
        world = self.multiworld.worlds[self.player]
        chapter = CHAPTERS_BY_KEY[world.starting_chapter]

        state = self.multiworld.get_state(self.multiworld)

        self.assertTrue(
            self.can_reach_entrance(f"Enter {chapter['name']}", state),
            f"{chapter['name']} was handed out as the starting mission but cannot "
            f"be entered with only its unlock item",
        )

    def test_something_is_reachable_at_the_start(self) -> None:
        state = self.multiworld.get_state(self.multiworld)
        reachable = [
            location for location in self.multiworld.get_locations(self.player)
            if location.can_reach(state)
        ]
        self.assertTrue(reachable, "sphere one is empty; fill cannot start")


class TestDefaults(StartingMissionMixin, HalfLifeSvenTestBase):
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


class TestMinimumMissions(StartingMissionMixin, HalfLifeSvenTestBase):
    options = {"missions_required": 1}

    def test_goal_opens_after_a_single_mission(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertEqual(world.options.missions_required.value, 1)
        state = self.multiworld.get_all_state(False)
        self.assertTrue(self.multiworld.completion_condition[self.player](state))


class TestEquipmentShuffled(StartingMissionMixin, HalfLifeSvenTestBase):
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


class TestEquipmentNotShuffled(StartingMissionMixin, HalfLifeSvenTestBase):
    options = {"shuffle_hev_suit": False, "shuffle_longjump": False}

    def test_equipment_is_absent_from_the_pool(self) -> None:
        pool = {item.name for item in self.multiworld.itempool if item.player == self.player}
        self.assertNotIn("HEV Suit", pool)
        self.assertNotIn("Long Jump Module", pool)

    def test_xen_is_reachable_without_equipment(self) -> None:
        state = self.multiworld.get_all_state(False)
        self.assertTrue(self.can_reach_entrance("Enter Xen", state))


class TestBlackMesaInboundExcluded(StartingMissionMixin, HalfLifeSvenTestBase):
    options = {"include_black_mesa_inbound": False}

    def test_its_unlock_is_not_in_the_pool(self) -> None:
        pool = {item.name for item in self.multiworld.itempool if item.player == self.player}
        precollected = {
            item.name for item in self.multiworld.precollected_items[self.player]
        }
        unlock = unlock_item_for_chapter["black_mesa_inbound"]

        self.assertNotIn(unlock, pool)
        self.assertNotIn(unlock, precollected)

    def test_its_locations_do_not_exist(self) -> None:
        names = {
            location.name for location in self.multiworld.get_locations(self.player)
        }
        for name in names:
            self.assertFalse(name.startswith("Black Mesa Inbound"), name)

    def test_missions_required_drops_by_one(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertEqual(
            world.options.missions_required.value, len(UNLOCKABLE_CHAPTERS) - 1
        )

    def test_the_goal_is_still_reachable(self) -> None:
        state = self.multiworld.get_all_state(False)
        self.assertTrue(self.multiworld.completion_condition[self.player](state))


class TestLooseLogic(StartingMissionMixin, HalfLifeSvenTestBase):
    options = {"logic_difficulty": "loose"}

    def test_weapon_gates_are_dropped(self) -> None:
        """Loose logic lets you into a late mission on its unlock alone."""
        world = self.multiworld.worlds[self.player]
        state = self.multiworld.get_state(self.multiworld)
        state.collect(world.create_item(unlock_item_for_chapter["surface_tension"]), True)

        self.assertTrue(self.can_reach_entrance("Enter Surface Tension", state))
