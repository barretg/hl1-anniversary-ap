"""World-specific logic tests.

Run these from an Archipelago source checkout:

    pytest test/general -k half_life
    pytest worlds/half_life/test
"""

from . import HalfLifeTestBase
from ..data import CHAPTERS, CHAPTERS_BY_KEY, LOCATIONS, MAX_MISSIONS
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
        state = self.multiworld.get_state(self.multiworld)

        chapter = CHAPTERS_BY_KEY[world.starting_chapter]
        self.assertTrue(
            self.can_reach_entrance(f"Enter {chapter['name']}", state),
            f"{chapter['name']} was handed out as the starting mission but "
            f"cannot be entered with only its unlock item",
        )

    def test_the_starting_mission_is_in_the_seed(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertNotIn(world.starting_chapter, world.excluded_chapters)

    def test_something_is_reachable_at_the_start(self) -> None:
        state = self.multiworld.get_state(self.multiworld)
        reachable = [
            location for location in self.multiworld.get_locations(self.player)
            if location.can_reach(state)
        ]
        self.assertTrue(reachable, "sphere one is empty; fill cannot start")


class TestDefaults(StartingMissionMixin, HalfLifeTestBase):
    options = {}

    def test_one_mission_is_precollected(self) -> None:
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

    def test_the_goal_mission_has_no_unlock_item(self) -> None:
        for chapter in CHAPTERS:
            if chapter["is_goal"]:
                self.assertNotIn(chapter["key"], unlock_item_for_chapter)

    def test_crowbar_is_not_an_item(self) -> None:
        """You always have it, so nothing can be sent for it."""
        names = self.multiworld.worlds[self.player].item_name_to_id
        self.assertNotIn("Crowbar", names)

    def test_victory_needs_every_mission_by_default(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertEqual(world.options.missions_required.value, MAX_MISSIONS)

        state = self.multiworld.get_all_state(False)
        self.assertTrue(self.multiworld.completion_condition[self.player](state))

    def test_the_intro_is_excluded_by_default(self) -> None:
        """`exclude_intro_missions` defaults on: the tram ride is not a level."""
        world = self.multiworld.worlds[self.player]
        self.assertIn("c0a0", world.excluded_chapters)


class TestMinimumMissions(StartingMissionMixin, HalfLifeTestBase):
    options = {"missions_required": 1}

    def test_goal_opens_after_a_single_mission(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertEqual(world.missions_required, 1)
        state = self.multiworld.get_all_state(False)
        self.assertTrue(self.multiworld.completion_condition[self.player](state))


class TestEquipmentShuffled(StartingMissionMixin, HalfLifeTestBase):
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


class TestXenWeapons(HalfLifeTestBase):
    options = {"logic_difficulty": "strict"}

    def test_xen_needs_both_the_tau_cannon_and_the_rpg(self) -> None:
        """Strict logic names these two outright, not a weapon tier."""
        world = self.multiworld.worlds[self.player]

        for missing in ("Tau Cannon", "RPG"):
            state = self.multiworld.get_all_state(False)
            state.remove(world.create_item(missing))
            state.sweep_for_advancements()

            for chapter in ("Xen", "Gonarch's Lair", "Interloper", "Nihilanth"):
                self.assertFalse(
                    self.can_reach_entrance(f"Enter {chapter}", state),
                    f"{chapter} is reachable without the {missing}",
                )

    def test_the_rest_of_the_campaign_is_not_tightened(self) -> None:
        """Only Xen onward names weapons; Surface Tension still takes any gun."""
        world = self.multiworld.worlds[self.player]
        state = self.multiworld.get_all_state(False)
        state.remove(world.create_item("Tau Cannon"))
        state.sweep_for_advancements()

        self.assertTrue(self.can_reach_entrance("Enter Surface Tension", state))


class TestEquipmentNotShuffled(StartingMissionMixin, HalfLifeTestBase):
    options = {"shuffle_hev_suit": False, "shuffle_longjump": False}

    def test_equipment_is_absent_from_the_pool(self) -> None:
        pool = {item.name for item in self.multiworld.itempool if item.player == self.player}
        self.assertNotIn("HEV Suit", pool)
        self.assertNotIn("Long Jump Module", pool)

    def test_xen_is_reachable_without_equipment(self) -> None:
        state = self.multiworld.get_all_state(False)
        self.assertTrue(self.can_reach_entrance("Enter Xen", state))


class TestTraps(HalfLifeTestBase):
    options = {"trap_percentage": 50}

    def test_traps_replace_filler_not_progression(self) -> None:
        from BaseClasses import ItemClassification

        pool = [item for item in self.multiworld.itempool if item.player == self.player]
        traps = [i for i in pool if i.classification == ItemClassification.trap]
        progression = [
            i for i in pool if i.classification == ItemClassification.progression
        ]

        self.assertTrue(traps)
        # Every progression item is still in the pool; only filler gave way.
        self.assertEqual(len(progression), len(self.available_progression()))

    def available_progression(self) -> set:
        world = self.multiworld.worlds[self.player]
        return world.available_item_names - {
            unlock_item_for_chapter[world.starting_chapter]
        }


class TestNoTraps(HalfLifeTestBase):
    options = {"trap_percentage": 0}

    def test_the_default_pool_has_none(self) -> None:
        from BaseClasses import ItemClassification

        pool = [item for item in self.multiworld.itempool if item.player == self.player]
        self.assertFalse(
            [i for i in pool if i.classification == ItemClassification.trap]
        )


class TestChargesanityOff(StartingMissionMixin, HalfLifeTestBase):
    options = {"chargesanity": False}

    def test_no_charger_locations_exist(self) -> None:
        charger_names = {
            entry["name"] for entry in LOCATIONS
            if entry["trigger"]["type"] == "charger"
        }
        names = {
            location.name for location in self.multiworld.get_locations(self.player)
        }
        self.assertFalse(names & charger_names)

    def test_the_weapon_and_mission_checks_survive(self) -> None:
        names = {
            location.name for location in self.multiworld.get_locations(self.player)
        }
        self.assertIn("First Shotgun", names)
        self.assertIn("Office Complex - Part 1 Reached", names)

    def test_the_pool_shrinks_with_the_location_set(self) -> None:
        """Filler is sized from this slot's locations, so both drop together."""
        pool = [item for item in self.multiworld.itempool if item.player == self.player]
        non_event = [
            location for location in self.multiworld.get_locations(self.player)
            if location.address is not None
        ]
        self.assertEqual(len(pool), len(non_event))


class TestChargesanityOn(HalfLifeTestBase):
    options = {"chargesanity": True}

    def test_charger_locations_exist(self) -> None:
        names = {
            location.name for location in self.multiworld.get_locations(self.player)
        }
        self.assertIn("Office Complex - Health Charger 1 (Part 1)", names)


class TestIntroIncluded(StartingMissionMixin, HalfLifeTestBase):
    options = {"exclude_intro_missions": False}

    def test_the_tram_ride_is_in_the_seed(self) -> None:
        names = {
            location.name for location in self.multiworld.get_locations(self.player)
        }
        self.assertIn("Black Mesa Inbound - Part 1 Reached", names)

    def test_it_has_an_unlock_item(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertIn("c0a0", unlock_item_for_chapter)
        self.assertIn(unlock_item_for_chapter["c0a0"], world.available_item_names)

    def test_missions_required_covers_it(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertEqual(world.missions_required, MAX_MISSIONS)


class TestIntroExcluded(StartingMissionMixin, HalfLifeTestBase):
    options = {"exclude_intro_missions": True}

    def test_its_unlock_is_not_in_the_pool(self) -> None:
        pool = {item.name for item in self.multiworld.itempool if item.player == self.player}
        self.assertNotIn(unlock_item_for_chapter["c0a0"], pool)

    def test_its_locations_do_not_exist(self) -> None:
        names = {
            location.name for location in self.multiworld.get_locations(self.player)
        }
        self.assertNotIn("Black Mesa Inbound - Part 1 Reached", names)

    def test_missions_required_drops_by_one(self) -> None:
        """Asking for more missions than the seed has would seal the finale."""
        world = self.multiworld.worlds[self.player]
        self.assertEqual(world.missions_required, MAX_MISSIONS - 1)

    def test_the_goal_is_still_reachable(self) -> None:
        state = self.multiworld.get_all_state(False)
        self.assertTrue(self.multiworld.completion_condition[self.player](state))


class TestLooseLogic(StartingMissionMixin, HalfLifeTestBase):
    options = {"logic_difficulty": "loose"}

    def test_weapon_gates_are_dropped(self) -> None:
        """Surface Tension with a crowbar is loose logic's whole proposition."""
        state = self.multiworld.get_state(self.multiworld)
        world = self.multiworld.worlds[self.player]
        state.collect(
            world.create_item(unlock_item_for_chapter["c2a5"]), prevent_sweep=True
        )

        self.assertTrue(self.can_reach_entrance("Enter Surface Tension", state))
