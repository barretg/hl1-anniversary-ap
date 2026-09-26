"""Archipelago world for retail Half-Life, the 25th anniversary build.

Half-Life's campaign is cut into its own 18 chapters. Each is a mission that
stays locked until its unlock item arrives, and weapons must be received before
they can be picked up. The run opens with one mission playable and is won by
finishing Nihilanth, which no item unlocks: it opens once `missions_required`
other missions are done.

Opposing Force (12 missions) and Blue Shift (6) can be added, or played without
Half-Life. Each has its own finale, sealed by its own mission count, and a seed
is won with every included game's finale.

A mission is entered from a hub rather than by playing through, so warps load the
map fresh and the loadout is reapplied on spawn. Transitions inside a mission are
the game's own.
"""

from __future__ import annotations

from typing import Any, ClassVar

import settings
from BaseClasses import Tutorial
from Options import OptionGroup
from worlds.AutoWorld import WebWorld, World
from worlds.LauncherComponents import Component, Type, components, launch_subprocess

from .client.settings import SETTINGS_KEY

from .data import (
    CAMPAIGNS,
    CAMPAIGNS_BY_KEY,
    CHAPTERS,
    CHARGER_TRIGGER,
    HALF_LIFE,
    ITEMS,
    OPTIONAL_ITEM_NAMES,
    VANILLA_WHEN_UNSHUFFLED,
    VICTORY,
    campaign_of,
)
from .items import (
    HalfLifeItem,
    create_item,
    filler_items,
    filler_weights,
    item_name_groups,
    item_name_to_id,
    melee_items,
    optional_items,
    trap_items,
    trap_weights,
    unlock_item_for_chapter,
    weapon_items,
)
from .locations import location_name_groups, location_name_to_id
from .options import (
    AmmoRelief,
    BlueShiftMissionsRequired,
    HalfLifeOptions,
    IncludeBlueShift,
    IncludeOpposingForce,
    OpposingForceMissionsRequired,
    RandomStartingWeapon,
    ViewmodelStyle,
)
from .regions import create_regions
from .rules import chapter_is_startable

GAME_NAME = "Half-Life"


def launch_client(*args: str) -> None:
    from .client.launcher import launch

    launch_subprocess(launch, name="HalfLifeClient", args=args)


components.append(
    Component(
        "Half-Life Client",
        func=launch_client,
        component_type=Type.CLIENT,
        game_name=GAME_NAME,
        supports_uri=True,
    )
)


class HalfLifeSettings(settings.Group):
    """This world's section of `host.yaml`."""

    class GameFolder(settings.UserFolderPath):
        """Your Half-Life installation: the folder that contains 'valve'.

        The client fills this in the first time you pick a folder, so you should
        not have to set it by hand.
        """

        description = "Half-Life installation folder"

    game_folder: GameFolder = GameFolder("")


class HalfLifeWeb(WebWorld):
    theme = "dirt"
    tutorials = [
        Tutorial(
            "Multiworld Setup Guide",
            "A guide to setting up Half-Life for Archipelago.",
            "English",
            "setup_en.md",
            "setup/en",
            ["hl1-anniversary-ap"],
        )
    ]

    # Anything here is off by default and known to be rough. Grouping it says so
    # in the template YAML and on the website without the player having to read
    # the option's own description first, and keeps it out of the run of settings
    # that are safe to turn on without thinking about it.
    option_groups = [
        OptionGroup(
            "Experimental Features",
            [AmmoRelief, IncludeOpposingForce, IncludeBlueShift,
             OpposingForceMissionsRequired, BlueShiftMissionsRequired,
             RandomStartingWeapon, ViewmodelStyle],
            start_collapsed=True,
        )
    ]


class HalfLifeWorld(World):
    """Half-Life, with every mission and every weapon locked behind Archipelago
    items."""

    game = GAME_NAME
    options_dataclass = HalfLifeOptions
    options: HalfLifeOptions
    web = HalfLifeWeb()

    settings_key = SETTINGS_KEY
    settings: ClassVar[HalfLifeSettings]

    item_name_to_id = item_name_to_id
    location_name_to_id = location_name_to_id
    item_name_groups = item_name_groups
    location_name_groups = location_name_groups

    unlock_item_for_chapter: ClassVar[dict[str, str]] = unlock_item_for_chapter

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Items that exist in *this* slot's pool. Logic groups are filtered
        # against it so a rule never asks for an item nobody will ever receive.
        self.available_item_names: set[str] = set()
        # The one mission open from the first spawn.
        self.starting_chapter: str = ""
        # Missions left out of this seed: no regions, no checks, no unlock item,
        # and they do not count toward `missions_required`.
        self.excluded_chapters: set[str] = set()
        # Whole categories of check switched off in the YAML, by trigger type.
        self.excluded_triggers: set[str] = set()
        # `missions_required` clamped to the missions this seed actually has.
        # Filled in `generate_early`, not here: Archipelago constructs the world
        # first and assigns `self.options` afterwards, so reading an option in
        # `__init__` raises AttributeError before generation has begun.
        self.missions_required: int = 0
        # The same, per included game. Each finale counts its own game only.
        self.missions_required_by_campaign: dict[str, int] = {}
        # Included games, in mission-numbering order.
        self.campaigns: list[str] = []
        # The melee weapon the run opens with.
        self.starting_weapon: str = ""

    # -- generation ------------------------------------------------------

    @property
    def tracker_passthrough(self) -> dict[str, Any] | None:
        """The real seed's slot data, when Universal Tracker is re-generating.

        UT runs this world's generation locally to work out what is in logic, but
        which mission the run opens with is rolled rather than derived, so a local
        roll would disagree with the server. `interpret_slot_data` hands the real
        answer back and UT re-runs generation with it here.
        """
        return getattr(self.multiworld, "re_gen_passthrough", {}).get(self.game)

    def interpret_slot_data(self, slot_data: dict[str, Any]) -> dict[str, Any]:
        """Universal Tracker's hook. Returning it asks UT to generate again.

        Everything it needs is already in slot data, because the client needed it
        too: which mission was handed out at the start, what is excluded, and what
        the finale is waiting on.
        """
        return slot_data

    def generate_early(self) -> None:
        passthrough = self.tracker_passthrough

        # Which games are in. Half-Life comes back on when nothing is, since a
        # seed needs something to play. Under the tracker, the seed's own list;
        # a seed from before there was one is Half-Life alone.
        toggles = {
            HALF_LIFE: self.options.include_half_life,
            "opposing_force": self.options.include_opposing_force,
            "blue_shift": self.options.include_blue_shift,
        }
        self.campaigns = [c["key"] for c in CAMPAIGNS if toggles.get(c["key"])]
        if not self.campaigns:
            self.campaigns = [HALF_LIFE]
        if passthrough:
            self.campaigns = list(passthrough.get("campaigns", [HALF_LIFE]))

        # A game that is out is out entirely: its missions are "not in this
        # seed" to the game, exactly like an excluded intro.
        self.excluded_chapters.update(
            c["key"] for c in CHAPTERS if campaign_of(c) not in self.campaigns
        )
        if self.options.exclude_intro_missions:
            self.excluded_chapters.update(
                CAMPAIGNS_BY_KEY[key]["intro_chapter"] for key in self.campaigns
            )
        if not self.options.chargesanity:
            self.excluded_triggers.add(CHARGER_TRIGGER)

        # Both sets come straight from the seed under the tracker: it may be
        # working without the YAML, in which case its options are defaults and
        # would give it a different set of locations than the server has.
        if passthrough:
            self.excluded_chapters = set(passthrough.get("excluded_chapters", ())) | {
                c["key"] for c in CHAPTERS if campaign_of(c) not in self.campaigns
            }
            self.excluded_triggers = set(passthrough.get("excluded_triggers", ()))

        items_by_name = {entry["name"]: entry for entry in ITEMS}

        # Half-Life's weapons are always in: every game places them, and their
        # content is Half-Life's own, which every install has. Another game's
        # weapons need that game's content, so only when it is included.
        self.available_item_names = {
            name for name in weapon_items
            if campaign_of(items_by_name[name]) in (HALF_LIFE, *self.campaigns)
        }
        # Unshuffled equipment that still exists as an item, locked to where the
        # campaign puts it. See `VANILLA_WHEN_UNSHUFFLED`.
        self.vanilla_placements: dict[str, str] = {}
        for name in optional_items:
            if campaign_of(items_by_name[name]) not in self.campaigns:
                continue
            if getattr(self.options, OPTIONAL_ITEM_NAMES[name]):
                self.available_item_names.add(name)
            elif name in VANILLA_WHEN_UNSHUFFLED:
                self.available_item_names.add(name)
                self.vanilla_placements[name] = VANILLA_WHEN_UNSHUFFLED[name]
        self.available_item_names.update(
            unlock_item_for_chapter[chapter["key"]]
            for chapter in self.included_chapters
            if chapter["key"] in unlock_item_for_chapter
        )

        # The starting melee weapon. Every included game offers its own, and
        # with one candidate (Half-Life, Blue Shift, or both) there is nothing
        # to roll: the crowbar, as always, and no RNG is drawn, so those seeds
        # generate exactly as they did before. Every candidate that does not
        # start the run is an item.
        candidates: list[str] = []
        for key in self.campaigns:
            for classname in CAMPAIGNS_BY_KEY[key].get("melee", ()):
                if classname not in candidates:
                    candidates.append(classname)
        if passthrough and passthrough.get("starting_weapons"):
            self.starting_weapon = passthrough["starting_weapons"][0]
        elif len(candidates) > 1 and self.options.random_starting_weapon:
            self.starting_weapon = self.random.choice(candidates)
        else:
            self.starting_weapon = candidates[0]
        melee_by_classname = {
            items_by_name[name]["classnames"][0]: name for name in melee_items
        }
        self.available_item_names.update(
            melee_by_classname[classname] for classname in candidates
            if classname != self.starting_weapon and classname in melee_by_classname
        )

        # Each finale's seal, clamped to the missions this seed contains:
        # excluding an intro leaves one fewer, and asking for more than exist
        # would seal that finale permanently.
        wanted = {
            HALF_LIFE: self.options.missions_required.value,
            "opposing_force": self.options.opposing_force_missions_required.value,
            "blue_shift": self.options.blue_shift_missions_required.value,
        }
        for key in self.campaigns:
            available = len([
                c for c in self.included_chapters
                if not c["is_goal"] and campaign_of(c) == key
            ])
            self.missions_required_by_campaign[key] = min(wanted[key], available)
        if passthrough:
            # The server's numbers. A tracker running without the YAML would
            # otherwise use the option defaults and seal a finale too long.
            self.missions_required_by_campaign.update(
                passthrough.get("missions_required_by_campaign", {})
            )
            if "missions_required" in passthrough and HALF_LIFE in self.campaigns:
                self.missions_required_by_campaign[HALF_LIFE] = int(
                    passthrough["missions_required"]
                )
        self.missions_required = self.missions_required_by_campaign.get(
            HALF_LIFE, next(iter(self.missions_required_by_campaign.values()))
        )

        # The run opens with one mission playable, and it has to be one a player
        # with nothing but a crowbar can actually walk into. Picking a gated
        # mission (anything from We've Got Hostiles on, under strict logic)
        # leaves sphere one empty and fill has nowhere to put its first item.
        chapters = [
            chapter for chapter in self.included_chapters
            if chapter["key"] in unlock_item_for_chapter
        ]
        starting = None
        # Under the tracker, the mission the *server* handed out, not a fresh
        # roll: opening the wrong one would put the whole run's logic one mission
        # out of step.
        if passthrough:
            given = set(passthrough.get("starting_chapters", ()))
            starting = next((c for c in chapters if c["key"] in given), None)
        if starting is None:
            candidates = [c for c in chapters if chapter_is_startable(self, c)]
            starting = self.random.choice(candidates or chapters)

        self.starting_chapter = starting["key"]
        self.multiworld.push_precollected(
            self.create_item(unlock_item_for_chapter[starting["key"]])
        )

    @property
    def included_chapters(self) -> list[dict[str, Any]]:
        """Every mission this seed actually contains, the finale included."""
        return [c for c in CHAPTERS if c["key"] not in self.excluded_chapters]

    def create_regions(self) -> None:
        create_regions(self)

    def create_item(self, name: str) -> HalfLifeItem:
        return create_item(self, name)

    def create_items(self) -> None:
        pool: list[HalfLifeItem] = []

        starting_unlock = unlock_item_for_chapter[self.starting_chapter]
        for name in sorted(self.available_item_names):
            if name == starting_unlock:
                continue  # already in the starting inventory
            if name in self.vanilla_placements:
                location = self.get_location(self.vanilla_placements[name])
                location.place_locked_item(self.create_item(name))
                continue
            pool.append(self.create_item(name))

        remaining = len(self.multiworld.get_unfilled_locations(self.player)) - len(pool)
        if remaining < 0:
            raise AssertionError(
                f"{self.game}: {-remaining} more progression items than locations"
            )
        pool += [self.create_item(name) for name in self.get_filler_names(remaining)]

        self.multiworld.itempool += pool

    def get_filler_names(self, count: int) -> list[str]:
        """Fill the leftover locations, with `trap_percentage` of them traps."""
        traps = round(count * self.options.trap_percentage.value / 100)
        names = self.random.choices(trap_items, weights=trap_weights, k=traps)
        names += self.random.choices(
            filler_items, weights=filler_weights, k=count - traps
        )
        # Otherwise every trap lands in the same stretch of the pool.
        self.random.shuffle(names)
        return names

    def get_filler_item_name(self) -> str:
        return self.random.choices(filler_items, weights=filler_weights, k=1)[0]

    def set_rules(self) -> None:
        # Entrance rules are attached in `create_regions`; only the win condition
        # is left.
        player = self.player
        # One Victory per included game's finale, and the seed wants them all.
        finales = len(self.campaigns)
        self.multiworld.completion_condition[player] = (
            lambda state: state.has(VICTORY, player, finales)
        )

    # -- runtime ---------------------------------------------------------

    def fill_slot_data(self) -> dict[str, Any]:
        """Everything the client needs to drive the game without shipping its own
        copy of the seed's settings."""
        goals = {key: CAMPAIGNS_BY_KEY[key]["goal_chapter"] for key in self.campaigns}
        return {
            # The first included game's seal and finale, under the names every
            # client before there was more than one game reads.
            "missions_required": self.missions_required,
            "goal_chapter": goals.get(HALF_LIFE, next(iter(goals.values()))),
            # Every included game, its finale and its seal. A seed without these
            # is Half-Life alone.
            "campaigns": list(self.campaigns),
            "goal_chapters": goals,
            "missions_required_by_campaign": dict(self.missions_required_by_campaign),
            "starting_chapters": [self.starting_chapter],
            # Missions that are not in this seed. The client tells the game, so
            # the in-game list says "not in this seed" rather than showing a
            # mission that stays locked forever with no explanation.
            "excluded_chapters": sorted(self.excluded_chapters),
            # Whole categories of check the YAML switched off, by trigger type.
            # The client does not need it, but Universal Tracker does: it may be
            # working without the YAML, and would otherwise expect chargers a
            # `chargesanity: false` seed does not contain.
            "excluded_triggers": sorted(self.excluded_triggers),
            # What the run opens with, and what the game must therefore never
            # take away.
            "starting_weapons": [self.starting_weapon],
            "death_link": bool(self.options.death_link),
            "death_link_amnesty": self.options.death_link_amnesty.value,
            "ammo_relief": bool(self.options.ammo_relief.value),
            "viewmodel_style": self.options.viewmodel_style.current_key,
            "shuffle_hev_suit": bool(self.options.shuffle_hev_suit),
            "shuffle_longjump": bool(self.options.shuffle_longjump),
            # Unshuffled equipment that is a real item at its vanilla location,
            # so the client must gate its pickup like any other. Seeds from
            # before this existed left the long jump module ungated instead.
            "placed_at_vanilla": sorted(self.vanilla_placements),
        }
