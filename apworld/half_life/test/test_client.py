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
    ctx.ammo_relief = False
    ctx.gordon_hands = False
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
