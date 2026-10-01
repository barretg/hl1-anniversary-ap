"""The client's reading of slot data, old seeds and new.

A seed generated before Opposing Force and Blue Shift existed has none of the
new keys, and must play exactly as it did: Half-Life alone, one finale.
"""

import logging
import unittest

from ..client.launcher import HALF_LIFE, HalfLifeContext, load_campaign


def context() -> HalfLifeContext:
    """The client's state without a connection, a window or a game folder."""
    ctx = HalfLifeContext.__new__(HalfLifeContext)
    ctx.campaign = load_campaign()
    ctx.game_dir = ""
    ctx.goal_chapter = ctx.campaign["goal_chapter"]
    ctx.campaign_of_chapter = {
        c["key"]: c.get("campaign", HALF_LIFE) for c in ctx.campaign["chapters"]
    }
    ctx.missions_required = 17
    ctx.campaigns = [HALF_LIFE]
    ctx.goal_chapters = {HALF_LIFE: ctx.goal_chapter}
    ctx.missions_required_by_campaign = {HALF_LIFE: 17}
    ctx.starting_weapons = ["weapon_crowbar"]
    ctx.death_link_amnesty = 4
    ctx.gordon_hands = False
    ctx.ally_weapon_drops = False
    ctx.completed_missions = set()
    ctx.unlocked_chapters = set()
    return ctx


# Slot data exactly as a seed from before this update wrote it.
OLD_SLOT_DATA = {
    "missions_required": 17,
    "goal_chapter": "c4a3",
    "starting_chapters": ["c1a0"],
    "excluded_chapters": ["c0a0"],
    "excluded_triggers": [],
    "starting_weapons": ["weapon_crowbar"],
    "death_link": False,
    "death_link_amnesty": 4,
    "ammo_relief": False,
    "shuffle_hev_suit": True,
    "shuffle_longjump": False,
    "placed_at_vanilla": ["Long Jump Module"],
}

HALF_LIFE_CHAPTERS = 18


class TestOldSeed(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = context()
        self.ctx.apply_slot_data(OLD_SLOT_DATA)

    def test_it_is_half_life_alone(self) -> None:
        self.assertEqual(self.ctx.campaigns, [HALF_LIFE])
        self.assertEqual(self.ctx.goal_chapters, {HALF_LIFE: "c4a3"})

    def test_the_other_games_are_not_in_the_seed(self) -> None:
        others = {
            c["key"] for c in self.ctx.campaign["chapters"]
            if c.get("campaign", HALF_LIFE) != HALF_LIFE
        }
        self.assertTrue(others)
        self.assertTrue(others <= self.ctx.excluded_chapters)
        self.assertIn("c0a0", self.ctx.excluded_chapters)

    def test_the_finale_opens_on_seventeen_half_life_missions(self) -> None:
        keys = [c["key"] for c in self.ctx.campaign["chapters"]][:HALF_LIFE_CHAPTERS]
        self.ctx.completed_missions = set(keys[:16])
        self.assertFalse(self.ctx.goal_open)
        self.assertNotIn("c4a3", self.ctx.open_chapters)
        self.ctx.completed_missions = set(keys[:17])
        self.assertTrue(self.ctx.goal_open)
        self.assertIn("c4a3", self.ctx.open_chapters)

    def test_finishing_nihilanth_wins(self) -> None:
        self.assertFalse(self.ctx.run_complete)
        self.ctx.completed_missions.add("c4a3")
        self.assertTrue(self.ctx.run_complete)

    def test_the_suit_is_still_the_only_armour_gate(self) -> None:
        # Shuffled suit: nothing granted up front, as before.
        self.assertNotIn("HEV Suit", self.ctx.always_unlocked)

    def test_ally_drops_stay_off(self) -> None:
        self.assertFalse(self.ctx.ally_weapon_drops)

    def test_the_flashlight_works_as_before(self) -> None:
        self.assertTrue({"Flashlight", "Night Vision Goggles"} <= self.ctx.always_unlocked)
        self.assertNotIn("Melee Throw", self.ctx.always_unlocked)


class TestSvenShapedSlotData(unittest.TestCase):
    """The Sven world's spellings read the same, so one parser serves both."""

    def setUp(self) -> None:
        self.ctx = context()
        self.ctx.apply_slot_data({
            **OLD_SLOT_DATA,
            "campaigns": [HALF_LIFE, "opposing_force"],
            "goal_chapters": ["c4a3", "of6a4b"],
            "campaign_missions_required": {HALF_LIFE: 2, "opposing_force": 1},
        })

    def test_a_list_of_finales_maps_to_their_games(self) -> None:
        self.assertEqual(self.ctx.goal_chapters,
                         {HALF_LIFE: "c4a3", "opposing_force": "of6a4b"})

    def test_the_other_seal_name_is_read(self) -> None:
        self.assertEqual(self.ctx.missions_required_by_campaign,
                         {HALF_LIFE: 2, "opposing_force": 1})


class TestEveryGameSeed(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = context()
        self.ctx.apply_slot_data({
            **OLD_SLOT_DATA,
            "campaigns": [HALF_LIFE, "opposing_force", "blue_shift"],
            "goal_chapters": {HALF_LIFE: "c4a3", "opposing_force": "of6a4b",
                              "blue_shift": "ba_teleport2"},
            "missions_required_by_campaign": {HALF_LIFE: 1, "opposing_force": 1,
                                              "blue_shift": 1},
            "viewmodel_style": "always_gordon",
            "ally_weapon_drops": True,
        })

    def test_each_seal_counts_its_own_game(self) -> None:
        self.ctx.completed_missions = {"of1a1"}
        self.assertIn("of6a4b", self.ctx.open_chapters)
        self.assertNotIn("c4a3", self.ctx.open_chapters)
        self.assertNotIn("ba_teleport2", self.ctx.open_chapters)

    def test_the_run_needs_every_finale(self) -> None:
        self.ctx.completed_missions = {"c4a3", "of6a4b"}
        self.assertFalse(self.ctx.run_complete)
        self.ctx.completed_missions.add("ba_teleport2")
        self.assertTrue(self.ctx.run_complete)

    def test_presentation_option(self) -> None:
        self.assertTrue(self.ctx.gordon_hands)

    def test_ally_drops_reach_the_game(self) -> None:
        self.assertTrue(self.ctx.ally_weapon_drops)


class TestMissingGameWarning(unittest.TestCase):
    """What the client says about a seed's games this install cannot load."""

    def setUp(self) -> None:
        import tempfile
        from pathlib import Path
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "valve/maps").mkdir(parents=True)
        (self.root / "valve/maps/c0a0.bsp").write_bytes(b"")
        (self.root / "gearbox/maps").mkdir(parents=True)
        (self.root / "gearbox/maps/of1a1.bsp").write_bytes(b"")
        self.ctx = context()
        self.ctx.game_dir = str(self.root)
        self.ctx.campaigns = [HALF_LIFE, "opposing_force", "blue_shift"]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def warnings(self) -> str:
        with self.assertLogs("Client", level="WARNING") as logs:
            self.ctx.warn_missing_games()
            logging.getLogger("Client").warning("end")
        return "\n".join(logs.output)

    def write_installed(self, of: str) -> None:
        store = self.root / "hlap/archipelago"
        store.mkdir(parents=True, exist_ok=True)
        (store / "installed.txt").write_text(
            f"I|half_life|valve|installed\nI|opposing_force|gearbox|{of}\n"
            "I|blue_shift|bshift|missing\n")

    def test_before_any_install_the_files_decide(self) -> None:
        out = self.warnings()
        self.assertNotIn("Opposing Force", out)
        self.assertIn("Blue Shift, which is not installed", out)

    def test_owned_but_not_linked_asks_for_install(self) -> None:
        self.write_installed("missing")
        self.assertIn("Opposing Force, which is installed but was not linked", self.warnings())

    def test_linked_says_nothing(self) -> None:
        self.write_installed("installed")
        self.assertNotIn("Opposing Force", self.warnings())


class TestLegacyChecks(unittest.TestCase):
    """A check a later release removed, still in an older seed, is sent for the
    player once they have reached the map it was on."""

    REMOVED = 7760052  # We've Got Hostiles, Part 2 (c1a3d)

    def setUp(self) -> None:
        self.ctx = context()
        self.ctx.legacy_sent = set()
        self.ctx.reached_id_by_map = {
            entry["map"]: entry["id"] for entry in self.ctx.campaign["locations"]
            if entry["trigger"]["type"] == "map_reached"
        }
        self.reached = self.ctx.reached_id_by_map["c1a3d"]
        self.ctx.checked_locations = set()
        self.ctx.missing_locations = {self.REMOVED, self.reached}

    def test_not_before_the_map_is_reached(self) -> None:
        self.assertEqual(self.ctx.legacy_checks_due([]), [])

    def test_on_reaching_the_map(self) -> None:
        self.assertEqual(self.ctx.legacy_checks_due([self.reached]), [self.REMOVED])

    def test_on_connect_when_reached_long_ago(self) -> None:
        self.ctx.checked_locations = {self.reached}
        self.assertEqual(self.ctx.legacy_checks_due([]), [self.REMOVED])

    def test_once(self) -> None:
        self.ctx.legacy_sent = {self.REMOVED}
        self.assertEqual(self.ctx.legacy_checks_due([self.reached]), [])

    def test_never_for_a_seed_without_it(self) -> None:
        self.ctx.missing_locations = {self.reached}
        self.assertEqual(self.ctx.legacy_checks_due([self.reached]), [])
