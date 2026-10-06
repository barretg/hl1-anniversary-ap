"""World-specific logic tests.

Run these from an Archipelago source checkout:

    pytest test/general -k half_life
    pytest worlds/half_life/test
"""

import unittest

from BaseClasses import CollectionState

from . import HalfLifeTestBase
from ..data import (
    AIR_ACCELERATE_CAP,
    AIR_ACCELERATE_LADDER,
    CHAPTERS,
    CHAPTERS_BY_KEY,
    LOCATIONS,
    MAX_MISSIONS,
    air_accelerate_steps,
    air_accelerate_value,
)
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
        state = CollectionState(self.multiworld)

        chapter = CHAPTERS_BY_KEY[world.starting_chapter]
        self.assertTrue(
            state.can_reach_entrance(f"Enter {chapter['name']}", self.player),
            f"{chapter['name']} was handed out as the starting mission but "
            f"cannot be entered with only its unlock item",
        )

    def test_the_starting_mission_is_in_the_seed(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertNotIn(world.starting_chapter, world.excluded_chapters)

    def test_something_is_reachable_at_the_start(self) -> None:
        state = CollectionState(self.multiworld)
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
        """A Half-Life-only seed always starts with it, so nothing can be sent
        for it. (It is an item in the datapackage for seeds where Opposing
        Force's knife or wrench may start the run instead.)"""
        pool = [item.name for item in self.multiworld.itempool if item.player == self.player]
        self.assertNotIn("Crowbar", pool)
        world = self.multiworld.worlds[self.player]
        self.assertEqual(world.starting_weapon, "weapon_crowbar")

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


XEN_CHAPTERS = ("c4a1", "c4a2", "c4a1a", "c4a3")


class XenNeedsLongJumpMixin:
    """Every Xen mission and check is out of logic until the long jump module
    arrives, whether it is shuffled or locked to its vanilla location."""

    def test_xen_requires_the_long_jump_module(self) -> None:
        world = self.multiworld.worlds[self.player]
        name = "Long Jump Module"

        # Take the module out of the world entirely: from the pool when shuffled,
        # off its locked location when not, so sweeping cannot pick it back up.
        for location in self.multiworld.get_locations(self.player):
            if location.item is not None and location.item.name == name:
                location.item = None
        self.multiworld.itempool = [
            item for item in self.multiworld.itempool
            if not (item.player == self.player and item.name == name)
        ]
        state = self.multiworld.get_all_state(False)
        self.assertEqual(state.count(name, self.player), 0)

        xen_names = {e["name"] for e in LOCATIONS if e["chapter"] in XEN_CHAPTERS}
        xen_locations = [
            location for location in self.multiworld.get_locations(self.player)
            if location.name in xen_names
        ]
        self.assertTrue(xen_locations)

        for key in XEN_CHAPTERS:
            entrance = f"Enter {CHAPTERS_BY_KEY[key]['name']}"
            self.assertFalse(
                state.can_reach_entrance(entrance, self.player),
                f"{entrance} is reachable without the {name}",
            )
        self.assertEqual(
            [location.name for location in xen_locations if location.can_reach(state)], []
        )

        state.collect(world.create_item(name), True)
        state.sweep_for_advancements()
        for key in XEN_CHAPTERS:
            self.assertTrue(
                state.can_reach_entrance(f"Enter {CHAPTERS_BY_KEY[key]['name']}", self.player)
            )
        self.assertTrue(all(location.can_reach(state) for location in xen_locations))


class TestEquipmentShuffled(XenNeedsLongJumpMixin, StartingMissionMixin, HalfLifeTestBase):
    options = {"shuffle_hev_suit": True, "shuffle_longjump": True}

    def test_equipment_is_in_the_pool(self) -> None:
        pool = {item.name for item in self.multiworld.itempool if item.player == self.player}
        self.assertIn("HEV Suit", pool)
        self.assertIn("Long Jump Module", pool)


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
                    state.can_reach_entrance(f"Enter {chapter}", self.player),
                    f"{chapter} is reachable without the {missing}",
                )

    def test_the_rest_of_the_campaign_is_not_tightened(self) -> None:
        """Only Xen onward names weapons; Surface Tension still takes any gun."""
        world = self.multiworld.worlds[self.player]
        state = self.multiworld.get_all_state(False)
        state.remove(world.create_item("Tau Cannon"))
        state.sweep_for_advancements()

        self.assertTrue(state.can_reach_entrance("Enter Surface Tension", self.player))


class TestEquipmentNotShuffled(XenNeedsLongJumpMixin, StartingMissionMixin, HalfLifeTestBase):
    options = {"shuffle_hev_suit": False, "shuffle_longjump": False}

    def test_equipment_is_absent_from_the_pool(self) -> None:
        pool = {item.name for item in self.multiworld.itempool if item.player == self.player}
        self.assertNotIn("HEV Suit", pool)
        self.assertNotIn("Long Jump Module", pool)

    def test_xen_is_reachable_without_equipment(self) -> None:
        state = self.multiworld.get_all_state(False)
        self.assertTrue(state.can_reach_entrance("Enter Xen", self.player))

    def test_long_jump_module_is_locked_to_its_vanilla_location(self) -> None:
        location = self.multiworld.get_location("First Long Jump Module", self.player)
        self.assertIsNotNone(location.item)
        self.assertEqual(location.item.name, "Long Jump Module")
        self.assertEqual(location.item.player, self.player)
        self.assertTrue(location.locked)

    def test_slot_data_names_the_vanilla_placement(self) -> None:
        slot_data = self.multiworld.worlds[self.player].fill_slot_data()
        self.assertEqual(slot_data["placed_at_vanilla"], ["Long Jump Module"])


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
        } - world.vanilla_placements.keys()


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
        self.assertIn("Office Complex: Part 1 Reached", names)

    def test_the_pool_shrinks_with_the_location_set(self) -> None:
        """Filler is sized from this slot's locations, so both drop together."""
        pool = [item for item in self.multiworld.itempool if item.player == self.player]
        non_event = [
            location for location in self.multiworld.get_locations(self.player)
            if location.address is not None and not location.locked
        ]
        self.assertEqual(len(pool), len(non_event))


class TestChargesanityOn(HalfLifeTestBase):
    options = {"chargesanity": True}

    def test_charger_locations_exist(self) -> None:
        names = {
            location.name for location in self.multiworld.get_locations(self.player)
        }
        self.assertIn("Office Complex: Health Charger 1 (Part 1)", names)


MICROWAVE = "Anomalous Materials: Microwave"


class TestMicrowaveDefault(HalfLifeTestBase):
    options = {}

    def test_off_by_default(self) -> None:
        names = {
            location.name for location in self.multiworld.get_locations(self.player)
        }
        self.assertNotIn(MICROWAVE, names)
        self.assertFalse(self.world.fill_slot_data()["include_microwave"])
        self.assertIn("microwave", self.world.fill_slot_data()["excluded_triggers"])


class TestMicrowaveIncluded(HalfLifeTestBase):
    options = {"include_microwave": True}

    def test_microwave_is_a_check(self) -> None:
        names = {
            location.name for location in self.multiworld.get_locations(self.player)
        }
        self.assertIn(MICROWAVE, names)
        self.assertTrue(self.world.fill_slot_data()["include_microwave"])
        self.assertNotIn("microwave", self.world.fill_slot_data()["excluded_triggers"])


class TestItemGroups(HalfLifeTestBase):
    """The groups the Sven world also has, with the same membership rules."""

    def test_weapons_holds_the_melee_weapons(self) -> None:
        from ..items import item_name_groups, melee_items
        self.assertTrue(melee_items)
        self.assertLessEqual(set(melee_items), item_name_groups["Weapons"])

    def test_abilities_holds_melee_throw(self) -> None:
        from ..items import item_name_groups
        self.assertIn("Melee Throw", item_name_groups["Abilities"])

    def test_renamed_items_keep_their_old_names(self) -> None:
        from ..items import item_name_groups
        from ..locations import location_name_groups
        self.assertEqual(item_name_groups["Displacer"], {"Displacer Cannon"})
        self.assertEqual(item_name_groups["Barnacle"], {"Barnacle Grapple"})
        self.assertEqual(location_name_groups["Opposing Force: First Displacer"],
                         {"Opposing Force: First Displacer Cannon"})
        self.assertEqual(location_name_groups["Opposing Force: First Barnacle"],
                         {"Opposing Force: First Barnacle Grapple"})


class TestEquipmentSlotData(HalfLifeTestBase):
    options = {"shuffle_hev_suit": True, "shuffle_longjump": False}

    def test_armour_items_and_shuffled_equipment(self) -> None:
        slot_data = self.multiworld.worlds[self.player].fill_slot_data()
        self.assertEqual(slot_data["armour_items"]["half_life"], "HEV Suit")
        self.assertIn("HEV Suit", slot_data["shuffled_equipment"])
        # Locked to its vanilla spot, so not shuffled.
        self.assertNotIn("Long Jump Module", slot_data["shuffled_equipment"])


class TestOldLocationNames(HalfLifeTestBase):
    """Names from before `Mission: Thing` still name exactly their location."""

    def test_every_old_name_resolves_to_its_location(self) -> None:
        from ..locations import location_name_groups
        chapter_names = {chapter["key"]: chapter["name"] for chapter in CHAPTERS}
        checked = 0
        for entry in LOCATIONS:
            prefix = chapter_names[entry["chapter"]] + ": "
            if not entry["name"].startswith(prefix):
                continue
            old = chapter_names[entry["chapter"]] + " - " + entry["name"][len(prefix):]
            self.assertEqual(location_name_groups.get(old), {entry["name"]}, old)
            checked += 1
        self.assertGreater(checked, 0)

    def test_an_old_name_can_be_excluded(self) -> None:
        from ..locations import location_name_groups
        self.assertIn("Office Complex - Part 1 Reached", location_name_groups)


class TestIntroIncluded(StartingMissionMixin, HalfLifeTestBase):
    options = {"exclude_intro_missions": False}

    def test_the_tram_ride_is_in_the_seed(self) -> None:
        names = {
            location.name for location in self.multiworld.get_locations(self.player)
        }
        self.assertIn("Black Mesa Inbound: Part 1 Reached", names)

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
        self.assertNotIn("Black Mesa Inbound: Part 1 Reached", names)

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
        state = CollectionState(self.multiworld)
        world = self.multiworld.worlds[self.player]
        state.collect(
            world.create_item(unlock_item_for_chapter["c2a5"]), prevent_sweep=True
        )

        self.assertTrue(state.can_reach_entrance("Enter Surface Tension", self.player))


# --- More than one game -----------------------------------------------------

HL_WEAPONS = {"Shotgun", "MP5", "Glock", "RPG"}
OF_WEAPONS = {"Desert Eagle", "M249", "Sniper Rifle", "Displacer Cannon",
              "Spore Launcher", "Barnacle Grapple", "Shock Roach"}


class CampaignMixin:
    campaigns: set[str] = set()

    def pool(self) -> list[str]:
        return [item.name for item in self.multiworld.itempool if item.player == self.player]

    def test_only_included_games_have_missions(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertEqual(set(world.campaigns), self.campaigns)
        for chapter in world.included_chapters:
            self.assertIn(chapter.get("campaign", "half_life"), self.campaigns)

    def test_half_life_weapons_are_always_items(self) -> None:
        """Every game places them, so an Opposing Force- or Blue Shift-only
        seed still needs them."""
        self.assertTrue(HL_WEAPONS <= set(self.pool()))

    def test_opposing_force_weapons_only_with_opposing_force(self) -> None:
        present = OF_WEAPONS & set(self.pool())
        self.assertEqual(present, OF_WEAPONS if "opposing_force" in self.campaigns else set())

    def test_every_finale_is_needed(self) -> None:
        world = self.multiworld.worlds[self.player]
        state = self.multiworld.get_all_state(False)
        self.assertTrue(self.multiworld.completion_condition[self.player](state))
        self.assertEqual(set(world.missions_required_by_campaign), self.campaigns)
        slot = world.fill_slot_data()
        self.assertEqual(set(slot["goal_chapters"]), self.campaigns)

    def test_starting_weapon_is_never_also_an_item(self) -> None:
        world = self.multiworld.worlds[self.player]
        melee = {"weapon_crowbar": "Crowbar", "weapon_knife": "Combat Knife",
                 "weapon_pipewrench": "Pipe Wrench"}
        self.assertNotIn(melee[world.starting_weapon], self.pool())
        self.assertEqual(world.fill_slot_data()["starting_weapons"], [world.starting_weapon])


class TestOpposingForceOnly(CampaignMixin, StartingMissionMixin, HalfLifeTestBase):
    options = {"include_half_life": False, "include_opposing_force": True}
    campaigns = {"opposing_force"}

    def test_the_other_melee_weapon_is_an_item(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertIn(world.starting_weapon, ("weapon_knife", "weapon_pipewrench"))
        other = "Pipe Wrench" if world.starting_weapon == "weapon_knife" else "Combat Knife"
        self.assertIn(other, self.pool())
        self.assertNotIn("Crowbar", self.pool())

    def test_armour_is_the_pcv(self) -> None:
        self.assertNotIn("HEV Suit", self.pool())


class TestOpposingForceGrapple(HalfLifeTestBase):
    options = {"include_half_life": False, "include_opposing_force": True,
               "logic_difficulty": "loose"}

    def test_vicarious_reality_part_3_on_needs_the_barnacle_at_any_difficulty(self) -> None:
        world = self.multiworld.worlds[self.player]
        state = self.multiworld.get_all_state(False)
        state.remove(world.create_item("Barnacle Grapple"))
        state.sweep_for_advancements()
        self.assertTrue(state.can_reach_region("of4a2", self.player))
        self.assertTrue(state.can_reach_location("Vicarious Reality: Part 2 Reached",
                                                 self.player))
        self.assertFalse(state.can_reach_location(
            "Vicarious Reality: Health Charger 1 (Part 2)", self.player))
        self.assertFalse(state.can_reach_region("of4a3", self.player))
        for mission in ("Pit Worm's Nest", "Foxtrot Uniform",
                        "The Package"):
            self.assertFalse(state.can_reach_entrance(f"Enter {mission}", self.player),
                             mission)


class TestBlueShiftOnly(CampaignMixin, StartingMissionMixin, HalfLifeTestBase):
    options = {"include_half_life": False, "include_blue_shift": True,
               "shuffle_hev_suit": True}
    campaigns = {"blue_shift"}

    def test_security_armor_replaces_the_suit(self) -> None:
        self.assertIn("Security Armor", self.pool())
        self.assertNotIn("HEV Suit", self.pool())


class TestDutyCallsBarrel(HalfLifeTestBase):
    options = {"include_half_life": False, "include_blue_shift": True,
               "logic_difficulty": "loose"}

    def test_past_the_barrel_needs_a_ranged_weapon_at_any_difficulty(self) -> None:
        from ..data import REQUIREMENT_GROUPS
        world = self.multiworld.worlds[self.player]
        state = self.multiworld.get_all_state(False)
        for item in state.multiworld.itempool:
            if item.player == self.player and item.name in REQUIREMENT_GROUPS["barrel_shooter"]:
                state.remove(item)
        state.sweep_for_advancements()
        self.assertTrue(state.can_reach_region("ba_canal1", self.player))
        self.assertFalse(state.can_reach_region("ba_canal1b", self.player))
        state.collect(world.create_item("Glock"))
        self.assertTrue(state.can_reach_region("ba_canal1b", self.player))

    def test_the_rpg_alone_gets_past_the_barrel(self) -> None:
        from ..data import REQUIREMENT_GROUPS
        world = self.multiworld.worlds[self.player]
        state = self.multiworld.get_all_state(False)
        for item in state.multiworld.itempool:
            if item.player == self.player and item.name in REQUIREMENT_GROUPS["barrel_shooter"]:
                state.remove(item)
        state.sweep_for_advancements()
        state.collect(world.create_item("RPG"))
        self.assertTrue(state.can_reach_region("ba_canal1b", self.player))

    def test_which_weapons_alone_get_past_the_barrel(self) -> None:
        from ..data import REQUIREMENT_GROUPS
        world = self.multiworld.worlds[self.player]
        for name, passes in (("Hand Grenade", True), ("Satchel Charge", True),
                             ("Snarks", True), ("Hivehand", False),
                             ("Tripmine", False)):
            with self.subTest(name):
                state = self.multiworld.get_all_state(False)
                for item in state.multiworld.itempool:
                    if (item.player == self.player
                            and item.name in REQUIREMENT_GROUPS["barrel_shooter"]):
                        state.remove(item)
                state.sweep_for_advancements()
                state.collect(world.create_item(name))
                self.assertEqual(state.can_reach_region("ba_canal1b", self.player), passes)


class TestEveryGame(CampaignMixin, StartingMissionMixin, HalfLifeTestBase):
    options = {"include_opposing_force": True, "include_blue_shift": True,
               "shuffle_hev_suit": True}
    campaigns = {"half_life", "opposing_force", "blue_shift"}

    def test_each_game_brings_its_armour(self) -> None:
        self.assertTrue({"HEV Suit", "PCV", "Security Armor"} <= set(self.pool()))


class TestNothingIncluded(HalfLifeTestBase):
    options = {"include_half_life": False}

    def test_half_life_comes_back(self) -> None:
        self.assertEqual(self.multiworld.worlds[self.player].campaigns, ["half_life"])


class EquipmentPoolMixin:
    def pool(self) -> set[str]:
        return {item.name for item in self.multiworld.itempool if item.player == self.player}


class TestFlashlightDefault(EquipmentPoolMixin, HalfLifeTestBase):
    options = {"include_opposing_force": True}

    def test_neither_light_nor_throw_is_an_item(self) -> None:
        self.assertFalse({"Flashlight", "Night Vision Goggles", "Melee Throw"} & self.pool())


class TestFlashlightHalfLife(EquipmentPoolMixin, HalfLifeTestBase):
    options = {"shuffle_flashlight": True, "melee_throw": True}

    def test_flashlight_and_throw_without_goggles(self) -> None:
        self.assertIn("Flashlight", self.pool())
        self.assertIn("Melee Throw", self.pool())
        self.assertNotIn("Night Vision Goggles", self.pool())


class TestAirAccelerationDefault(EquipmentPoolMixin, HalfLifeTestBase):
    def test_no_air_acceleration_items(self) -> None:
        self.assertNotIn("Progressive Air Acceleration", self.pool())

    def test_slot_data_leaves_it_to_the_game(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertIsNone(world.fill_slot_data()["air_acceleration"])


class TestAirAccelerationOn(HalfLifeTestBase):
    # Given the wrong way round on purpose: the bounds are swapped.
    options = {"progressive_air_acceleration": True,
               "air_acceleration_minimum": 150, "air_acceleration_maximum": 0}

    def test_one_item_per_step_of_the_curve(self) -> None:
        copies = [item for item in self.multiworld.itempool
                  if item.player == self.player
                  and item.name == "Progressive Air Acceleration"]
        self.assertEqual(len(copies), len(air_accelerate_steps(0, 150)))
        self.assertEqual(len(copies), 23)

    def test_slot_data_bounds(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertEqual(world.fill_slot_data()["air_acceleration"], [0, 150])


class TestAirAccelerationCurve(unittest.TestCase):
    def test_steps_start_at_two_and_grow(self) -> None:
        ladder = AIR_ACCELERATE_LADDER
        gaps = [b - a for a, b in zip(ladder, ladder[1:-1])]
        self.assertEqual(gaps[0], 2)
        self.assertEqual(gaps, sorted(gaps))
        self.assertEqual(ladder[-1], AIR_ACCELERATE_CAP)

    def test_count_rounds_up_and_ends_on_the_maximum(self) -> None:
        self.assertEqual(air_accelerate_steps(10, 100)[-1], 100)
        self.assertEqual(len(air_accelerate_steps(10, 100)), 15)
        self.assertEqual(air_accelerate_steps(10, 11), [11])
        self.assertEqual(air_accelerate_steps(10, 10), [])

    def test_value(self) -> None:
        self.assertEqual(air_accelerate_value(10, 100, 0), 10)
        self.assertEqual(air_accelerate_value(10, 100, 1), 12)
        self.assertEqual(air_accelerate_value(10, 100, 99), 100)
        self.assertEqual(air_accelerate_value(10, 10, 5), 10)


class TestFlashlightEveryGame(EquipmentPoolMixin, HalfLifeTestBase):
    options = {"include_opposing_force": True, "include_blue_shift": True,
               "shuffle_flashlight": True}

    def test_both_lights(self) -> None:
        self.assertTrue({"Flashlight", "Night Vision Goggles"} <= self.pool())


class TestFlashlightBlueShiftOnly(EquipmentPoolMixin, HalfLifeTestBase):
    options = {"include_half_life": False, "include_blue_shift": True,
               "shuffle_flashlight": True}

    def test_blue_shift_brings_the_flashlight(self) -> None:
        self.assertIn("Flashlight", self.pool())
        self.assertNotIn("Night Vision Goggles", self.pool())


class TestFlashlightOpposingForceOnly(EquipmentPoolMixin, HalfLifeTestBase):
    options = {"include_half_life": False, "include_opposing_force": True,
               "shuffle_flashlight": True}

    def test_only_the_goggles(self) -> None:
        self.assertIn("Night Vision Goggles", self.pool())
        self.assertNotIn("Flashlight", self.pool())


# --- Weapon checks: any mission's first copy ----------------------------------


def only_unlocks(test: HalfLifeTestBase, *chapters: str) -> CollectionState:
    """A state holding nothing but these missions' unlocks."""
    world = test.multiworld.worlds[test.player]
    state = CollectionState(test.multiworld)
    # A fresh state already holds the mission the run opens with.
    state.remove(world.create_item(unlock_item_for_chapter[world.starting_chapter]))
    for key in chapters:
        state.collect(world.create_item(unlock_item_for_chapter[key]), prevent_sweep=True)
    return state


def all_but(test: HalfLifeTestBase, *items: str) -> CollectionState:
    """Everything, less these items. Unswept until they are gone, or the sweep
    collects the events they open and removing them takes none back."""
    world = test.multiworld.worlds[test.player]
    state = test.multiworld.get_all_state(perform_sweep=False)
    for name in items:
        state.remove(world.create_item(name))
    state.sweep_for_advancements()
    return state


class TestOpposingForceWeaponSources(HalfLifeTestBase):
    options = {"include_half_life": False, "include_opposing_force": True,
               "logic_difficulty": "loose"}

    def test_a_later_mission_with_a_copy_reaches_the_check(self) -> None:
        """Crush Depth has its own Glock; the earliest one is missions away."""
        state = only_unlocks(self, "of3a4")
        self.assertTrue(state.can_reach_location("Opposing Force: First Glock", self.player))

    def test_a_mission_with_no_copy_does_not(self) -> None:
        state = only_unlocks(self, "of3a1")
        self.assertFalse(state.can_reach_location("Opposing Force: First Glock", self.player))

    def test_weapon_checks_hang_on_the_hub(self) -> None:
        location = self.multiworld.get_location("Opposing Force: First Glock", self.player)
        self.assertEqual(location.parent_region.name, "Hub")

    def test_a_source_past_a_teleport_needs_the_displacer(self) -> None:
        """We Are Not Alone's only shotgun is past a displacer teleport."""
        state = only_unlocks(self, "of3a1")
        self.assertFalse(state.can_reach_location("Opposing Force: First Shotgun", self.player))
        state.collect(self.multiworld.worlds[self.player].create_item("Displacer Cannon"),
                      prevent_sweep=True)
        self.assertTrue(state.can_reach_location("Opposing Force: First Shotgun", self.player))

    def test_the_displacer_xen_rooms_need_the_displacer(self) -> None:
        names = [
            "We Are Not Alone: Health Charger (Part 3)",
            "Crush Depth: Healing Pool (Part 1)",
            "Vicarious Reality: Healing Pool (Part 1)",
            "Foxtrot Uniform: Healing Pool (Part 1)",
            "Foxtrot Uniform: Healing Pool (Part 2)",
            "The Package: Healing Pool (Part 1)",
            "The Package: Healing Pool (Part 4)",
            "Worlds Collide: Healing Pool (Part 1)",
        ]
        without = all_but(self, "Displacer Cannon")
        with_it = self.multiworld.get_all_state(False)
        for name in names:
            self.assertFalse(without.can_reach_location(name, self.player), name)
            self.assertTrue(with_it.can_reach_location(name, self.player), name)

    def test_a_hostile_drop_is_a_source(self) -> None:
        """The Shock Roach is only ever dropped, and The Package's troopers
        drop one. The Package itself needs the grapple at any difficulty."""
        state = only_unlocks(self, "of6a1")
        state.collect(self.multiworld.worlds[self.player].create_item("Barnacle Grapple"),
                      prevent_sweep=True)
        self.assertTrue(state.can_reach_location("Opposing Force: First Shock Roach",
                                                 self.player))


class TestAllyDropsOff(HalfLifeTestBase):
    options = {"exclude_intro_missions": False, "logic_difficulty": "loose"}

    def test_an_allys_drop_is_not_a_source(self) -> None:
        """Anomalous Materials' guards carry Glocks; killing one is not logic."""
        state = only_unlocks(self, "c1a0")
        self.assertFalse(state.can_reach_location("First Glock", self.player))

    def test_slot_data_says_so(self) -> None:
        world = self.multiworld.worlds[self.player]
        self.assertFalse(world.fill_slot_data()["ally_weapon_drops"])


class TestAllyDropsOn(HalfLifeTestBase):
    options = {"exclude_intro_missions": False, "logic_difficulty": "loose",
               "ally_weapon_drops": True}

    def test_an_allys_drop_is_a_source(self) -> None:
        state = only_unlocks(self, "c1a0")
        self.assertTrue(state.can_reach_location("First Glock", self.player))

    def test_a_grunts_drop_is_a_source_either_way(self) -> None:
        """Apprehension's grunts drop MP5s; no MP5 lies in it before."""
        state = only_unlocks(self, "c2a1")
        self.assertTrue(state.can_reach_location("First MP5", self.player))


class TestOnARailCratesLoose(HalfLifeTestBase):
    options = {"logic_difficulty": "loose"}

    def test_the_grenade_launcher_clears_them(self) -> None:
        state = all_but(self, "Hand Grenade", "Satchel Charge")
        self.assertTrue(state.can_reach_region("c2a2e", self.player))

    def test_nothing_explosive_does_not(self) -> None:
        state = all_but(self, "Hand Grenade", "Satchel Charge", "MP5")
        self.assertTrue(state.can_reach_region("c2a2d", self.player))
        self.assertFalse(state.can_reach_region("c2a2e", self.player))


class TestOnARailCratesStrict(HalfLifeTestBase):
    options = {"logic_difficulty": "strict"}

    def test_the_grenade_launcher_is_not_enough(self) -> None:
        state = all_but(self, "Hand Grenade", "Satchel Charge")
        self.assertFalse(state.can_reach_region("c2a2e", self.player))

    def test_a_grenade_is(self) -> None:
        state = all_but(self, "Satchel Charge", "MP5")
        self.assertTrue(state.can_reach_region("c2a2e", self.player))


class TestEveryGameStrictAllyDrops(HalfLifeTestBase):
    """The default tests (fill, every location reachable) on the widest seed."""
    options = {"include_opposing_force": True, "include_blue_shift": True,
               "logic_difficulty": "strict", "ally_weapon_drops": True,
               "exclude_intro_missions": False}
