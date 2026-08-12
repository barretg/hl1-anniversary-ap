"""World-specific logic tests.

Run these from an Archipelago source checkout:

    pytest test/general -k half_life
    pytest worlds/half_life_sven/test
"""

from . import HalfLifeSvenTestBase
from ..data import (
    CHAPTERS,
    CHAPTERS_BY_KEY,
    LOCATIONS,
    MELEE_STARTERS,
    UNLOCKABLE_CHAPTERS,
    unlockable_chapters_of,
)
from ..items import chapter_unlock_items, unlock_item_for_chapter


class StartingMissionMixin:
    """Every starting mission must be enterable with nothing but its unlock.

    Every location sits behind a mission entrance, so a gated starting mission
    means an empty sphere one and a fill failure. Asserted for each option set,
    because which missions qualify depends on logic difficulty and on whether the
    suit and long jump module are shuffled.
    """

    def test_the_starting_missions_are_reachable_from_nothing(self) -> None:
        world = self.multiworld.worlds[self.player]
        state = self.multiworld.get_state(self.multiworld)

        for key in world.starting_chapters:
            chapter = CHAPTERS_BY_KEY[key]
            self.assertTrue(
                self.can_reach_entrance(f"Enter {chapter['name']}", state),
                f"{chapter['name']} was handed out as a starting mission but "
                f"cannot be entered with only its unlock item",
            )

    def test_every_included_campaign_starts_somewhere(self) -> None:
        world = self.multiworld.worlds[self.player]
        started = {CHAPTERS_BY_KEY[key]["campaign"] for key in world.starting_chapters}
        self.assertEqual(started, set(world.included_campaigns))

    def test_something_is_reachable_at_the_start(self) -> None:
        state = self.multiworld.get_state(self.multiworld)
        reachable = [
            location for location in self.multiworld.get_locations(self.player)
            if location.can_reach(state)
        ]
        self.assertTrue(reachable, "sphere one is empty; fill cannot start")


class TestDefaults(StartingMissionMixin, HalfLifeSvenTestBase):
    options = {}

    def test_one_mission_per_campaign_is_precollected(self) -> None:
        world = self.multiworld.worlds[self.player]
        precollected = [
            item for item in self.multiworld.precollected_items[self.player]
            if item.name in chapter_unlock_items
        ]
        self.assertEqual(len(precollected), len(world.included_campaigns))

    def test_precollected_unlock_is_not_also_in_the_pool(self) -> None:
        starting = {
            item.name for item in self.multiworld.precollected_items[self.player]
        }
        pool = [item.name for item in self.multiworld.itempool if item.player == self.player]
        for name in starting & set(chapter_unlock_items):
            self.assertNotIn(name, pool)

    def test_goal_missions_have_no_unlock_item(self) -> None:
        for chapter in CHAPTERS:
            if chapter["is_goal"]:
                self.assertNotIn(chapter["key"], unlock_item_for_chapter)

    def test_only_half_life_is_enabled_by_default(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertEqual(world.included_campaigns, ["half_life"])
        # And nothing from another campaign leaked into the pool.
        pool = {item.name for item in self.multiworld.itempool if item.player == self.player}
        self.assertNotIn("Displacer Cannon", pool)
        self.assertNotIn("Tommy Gun", pool)

    def test_crowbar_is_not_an_item(self) -> None:
        names = self.multiworld.worlds[self.player].item_name_to_id
        self.assertNotIn("Crowbar", names)

    def test_victory_needs_every_mission_by_default(self) -> None:
        """With the default missions_required, holding one mission short fails."""
        world = self.multiworld.worlds[self.player]
        self.assertEqual(
            world.options.missions_required.value,
            len(unlockable_chapters_of("half_life")),
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


class TestXenWeapons(HalfLifeSvenTestBase):
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


class TestEquipmentNotShuffled(StartingMissionMixin, HalfLifeSvenTestBase):
    options = {"shuffle_hev_suit": False, "shuffle_longjump": False}

    def test_equipment_is_absent_from_the_pool(self) -> None:
        pool = {item.name for item in self.multiworld.itempool if item.player == self.player}
        self.assertNotIn("HEV Suit", pool)
        self.assertNotIn("Long Jump Module", pool)

    def test_xen_is_reachable_without_equipment(self) -> None:
        state = self.multiworld.get_all_state(False)
        self.assertTrue(self.can_reach_entrance("Enter Xen", state))


class TestTraps(HalfLifeSvenTestBase):
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
            unlock_item_for_chapter[key] for key in world.starting_chapters
        }


class TestNoTraps(HalfLifeSvenTestBase):
    options = {"trap_percentage": 0}

    def test_the_default_pool_has_none(self) -> None:
        from BaseClasses import ItemClassification

        pool = [item for item in self.multiworld.itempool if item.player == self.player]
        self.assertFalse(
            [i for i in pool if i.classification == ItemClassification.trap]
        )


class TestChargesanityOff(StartingMissionMixin, HalfLifeSvenTestBase):
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
        self.assertIn("Office Complex - Reached", names)

    def test_the_pool_shrinks_with_the_location_set(self) -> None:
        """Filler is sized from this slot's locations, so both drop together."""
        pool = [item for item in self.multiworld.itempool if item.player == self.player]
        non_event = [
            location for location in self.multiworld.get_locations(self.player)
            if location.address is not None
        ]
        self.assertEqual(len(pool), len(non_event))


class TestChargesanityOn(HalfLifeSvenTestBase):
    options = {"chargesanity": True}

    def test_charger_locations_exist(self) -> None:
        names = {
            location.name for location in self.multiworld.get_locations(self.player)
        }
        self.assertIn("Office Complex - Health Charger 1", names)


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
            world.missions_required_for["half_life"],
            len(unlockable_chapters_of("half_life")) - 1,
        )

    def test_the_goal_is_still_reachable(self) -> None:
        state = self.multiworld.get_all_state(False)
        self.assertTrue(self.multiworld.completion_condition[self.player](state))


class TestEveryCampaign(StartingMissionMixin, HalfLifeSvenTestBase):
    options = {
        "include_half_life": True,
        "include_opposing_force": True,
        "include_blue_shift": True,
        "include_they_hunger": True,
    }

    def test_all_four_are_in_the_seed(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertEqual(
            world.included_campaigns,
            ["half_life", "opposing_force", "blue_shift", "they_hunger"],
        )

    def test_every_campaign_contributes_its_weapons(self) -> None:
        pool = {item.name for item in self.multiworld.itempool if item.player == self.player}
        precollected = {
            item.name for item in self.multiworld.precollected_items[self.player]
        }
        held = pool | precollected
        for name in ("Shotgun", "Displacer Cannon", "Tommy Gun"):
            self.assertIn(name, held)

    def test_winning_needs_all_four_finales(self) -> None:
        """One campaign cleared is not the seed cleared."""
        from ..data import victory_event

        world = self.multiworld.worlds[self.player]
        state = self.multiworld.get_all_state(False)
        self.assertTrue(self.multiworld.completion_condition[self.player](state))

        for campaign in world.included_campaigns:
            short = self.multiworld.get_all_state(False)
            short.remove(world.create_item(victory_event(campaign)))
            self.assertFalse(
                self.multiworld.completion_condition[self.player](short),
                f"the seed was won without finishing {campaign}",
            )


class TestOpposingForceOnly(StartingMissionMixin, HalfLifeSvenTestBase):
    options = {
        "include_half_life": False,
        "include_opposing_force": True,
    }

    def test_no_half_life_missions_are_in_the_seed(self) -> None:
        names = {
            location.name for location in self.multiworld.get_locations(self.player)
        }
        self.assertFalse([n for n in names if n.startswith("Office Complex")])
        self.assertTrue([n for n in names if n.startswith("Boot Camp")])

    def test_it_keeps_its_own_weapon_checks(self) -> None:
        """A shared weapon's only check used to sit in a Half-Life map."""
        names = {
            location.name for location in self.multiworld.get_locations(self.player)
        }
        self.assertIn("Opposing Force - First Shotgun", names)

    def test_its_finale_is_the_only_goal(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertEqual(
            [c["key"] for c in world.goal_chapters], ["of_worlds_collide"]
        )


class TestRandomStartingWeapon(StartingMissionMixin, HalfLifeSvenTestBase):
    options = {
        "include_half_life": True,
        "include_opposing_force": True,
        "include_they_hunger": True,
        "random_starting_weapon": True,
    }

    def test_it_starts_with_exactly_one_melee_weapon_and_the_medkit(self) -> None:
        world = self.multiworld.worlds[self.player]
        melee = {
            classname
            for campaign in ("half_life", "opposing_force", "they_hunger")
            for classnames in MELEE_STARTERS[campaign].values()
            for classname in classnames
        }

        self.assertIn("weapon_medkit", world.starting_weapons)
        chosen = [c for c in world.starting_weapons if c in melee]
        self.assertEqual(len(chosen), 1, world.starting_weapons)

    def test_the_chosen_weapon_is_not_also_in_the_pool(self) -> None:
        """You cannot be sent a wrench you are already holding."""
        world = self.multiworld.worlds[self.player]
        if not world.starting_melee_item:
            self.skipTest("this seed rolled the crowbar, which is never an item")

        pool = {item.name for item in self.multiworld.itempool if item.player == self.player}
        self.assertNotIn(world.starting_melee_item, pool)
        self.assertNotIn(world.starting_melee_item, world.available_item_names)


class TestStartingWeaponLeftAlone(StartingMissionMixin, HalfLifeSvenTestBase):
    options = {"include_opposing_force": True, "random_starting_weapon": False}

    def test_it_is_still_the_crowbar(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertEqual(world.starting_weapons, ["weapon_crowbar", "weapon_medkit"])
        self.assertEqual(world.starting_melee_item, "")

    def test_the_wrench_is_a_normal_item(self) -> None:
        pool = {item.name for item in self.multiworld.itempool if item.player == self.player}
        self.assertIn("Pipe Wrench", pool)


class TestSharedWeaponsWithoutHalfLife(HalfLifeSvenTestBase):
    """A weapon Half-Life declared but another campaign is full of."""

    options = {"include_half_life": False, "include_opposing_force": True}

    def test_the_shotgun_is_still_an_item(self) -> None:
        world = self.multiworld.worlds[self.player]
        for name in ("Shotgun", "MP5", "RPG"):
            self.assertIn(name, world.available_item_names)

    def test_weapons_no_campaign_holds_are_left_out(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertNotIn("Tommy Gun", world.available_item_names)


class TestNoCampaignsEnabled(StartingMissionMixin, HalfLifeSvenTestBase):
    """A YAML can switch everything off; a seed still has to contain something."""

    options = {
        "include_half_life": False,
        "include_opposing_force": False,
        "include_blue_shift": False,
        "include_they_hunger": False,
    }

    def test_it_falls_back_to_half_life(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertEqual(world.included_campaigns, ["half_life"])


class TestIndependentMissionCounts(HalfLifeSvenTestBase):
    """Each campaign's finale answers to its own setting and no other."""

    options = {
        "include_half_life": True,
        "include_opposing_force": True,
        "missions_required": 1,
        "opposing_force_missions_required": 9,
    }

    def test_each_campaign_keeps_its_own_number(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertEqual(world.missions_required_for["half_life"], 1)
        self.assertEqual(world.missions_required_for["opposing_force"], 9)

    def test_finishing_one_campaign_does_not_open_the_other(self) -> None:
        from ..data import mission_complete_event

        world = self.multiworld.worlds[self.player]
        state = self.multiworld.get_state(self.multiworld)
        # Nine Half-Life missions is more than enough for Nihilanth and nothing
        # at all for Worlds Collide.
        for _ in range(9):
            state.collect(world.create_item(mission_complete_event("half_life")), True)
        state.sweep_for_advancements()

        self.assertFalse(self.can_reach_entrance("Enter Worlds Collide", state))


class TestLooseLogic(StartingMissionMixin, HalfLifeSvenTestBase):
    options = {"logic_difficulty": "loose"}

    def test_weapon_gates_are_dropped(self) -> None:
        """Loose logic lets you into a late mission on its unlock alone."""
        world = self.multiworld.worlds[self.player]
        state = self.multiworld.get_state(self.multiworld)
        state.collect(world.create_item(unlock_item_for_chapter["surface_tension"]), True)

        self.assertTrue(self.can_reach_entrance("Enter Surface Tension", state))


class TestPairedFinale(StartingMissionMixin, HalfLifeSvenTestBase):
    """Blue Shift's finale is the tail of Power Struggle, not a mission of its own.

    A Leap Of Faith is the escape cutscene: watching it means nothing until the
    mission it follows is behind you, so its entrance asks for that mission by
    name on top of `blue_shift_missions_required`.
    """

    options = {
        "include_half_life": False,
        "include_blue_shift": True,
        "blue_shift_missions_required": 1,
        "logic_difficulty": "loose",
    }

    def test_the_count_alone_does_not_open_it(self) -> None:
        from ..data import chapter_cleared_event, mission_complete_event

        world = self.multiworld.worlds[self.player]
        state = self.multiworld.get_state(self.multiworld)
        # Far more missions than the one it asks for, and none of them the one.
        for _ in range(6):
            state.collect(world.create_item(mission_complete_event("blue_shift")), True)
        state.sweep_for_advancements()
        self.assertFalse(self.can_reach_entrance("Enter A Leap Of Faith", state))

        state.collect(
            world.create_item(chapter_cleared_event("bs_power_struggle")), True
        )
        state.sweep_for_advancements()
        self.assertTrue(self.can_reach_entrance("Enter A Leap Of Faith", state))

    def test_power_struggle_has_no_unlock_item(self) -> None:
        """It shares the finale's seal, so nothing in any pool opens it."""
        self.assertNotIn("bs_power_struggle", unlock_item_for_chapter)

        pool = {
            item.name for item in self.multiworld.itempool if item.player == self.player
        }
        starting = {
            item.name for item in self.multiworld.precollected_items[self.player]
        }
        self.assertNotIn("Power Struggle Unlock", pool | starting)

    def test_the_count_opens_power_struggle(self) -> None:
        from ..data import mission_complete_event

        world = self.multiworld.worlds[self.player]
        state = self.multiworld.get_state(self.multiworld)

        # Nothing finished yet: sealed, however many unlock items are held.
        self.assertFalse(self.can_reach_entrance("Enter Power Struggle", state))

        # One mission is what this seed asks for, and it is all it asks for --
        # no item, and no clearing of the mission it is paired with.
        state.collect(world.create_item(mission_complete_event("blue_shift")), True)
        state.sweep_for_advancements()
        self.assertTrue(self.can_reach_entrance("Enter Power Struggle", state))

    def test_clearing_power_struggle_grants_the_event(self) -> None:
        names = {
            location.name for location in self.multiworld.get_locations(self.player)
        }
        self.assertIn("Power Struggle - Cleared", names)

    def test_the_seed_is_still_winnable(self) -> None:
        state = self.multiworld.get_all_state(False)
        self.assertTrue(self.multiworld.completion_condition[self.player](state))
