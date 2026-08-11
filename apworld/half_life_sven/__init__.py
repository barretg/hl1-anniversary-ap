"""Archipelago world for the Half-Life campaign as shipped in Sven Co-op.

The Sven Co-op campaign portal (`-sp_campaign_portal`) is the hub. Each Half-Life
mission is locked until its unlock item arrives, weapons must be received before
they can be picked up, and the Nihilanth mission opens once enough other missions
are finished.
"""

from __future__ import annotations

from typing import Any, ClassVar

import settings
from BaseClasses import Tutorial
from worlds.AutoWorld import WebWorld, World
from worlds.LauncherComponents import Component, Type, components, launch_subprocess

from .client.settings import SETTINGS_KEY

from .data import (
    CHAPTERS,
    CHARGER_TRIGGER,
    GOAL_CHAPTER,
    INTRO_CHAPTER,
    OPTIONAL_ITEM_NAMES,
    STARTING_WEAPONS,
    VICTORY,
)
from .items import (
    HalfLifeSvenItem,
    create_item,
    filler_items,
    filler_weights,
    item_name_groups,
    item_name_to_id,
    optional_items,
    unlock_item_for_chapter,
    weapon_items,
)
from .locations import location_name_groups, location_name_to_id
from .options import HalfLifeSvenOptions
from .regions import create_regions
from .rules import chapter_is_startable

GAME_NAME = "Half-Life (Sven Co-op)"


def launch_client(*args: str) -> None:
    from .client.launcher import launch

    launch_subprocess(launch, name="HalfLifeSvenClient", args=args)


components.append(
    Component(
        "Half-Life (Sven Co-op) Client",
        func=launch_client,
        component_type=Type.CLIENT,
        game_name=GAME_NAME,
        supports_uri=True,
    )
)


class HalfLifeSvenSettings(settings.Group):
    """This world's section of `host.yaml`."""

    class GameFolder(settings.UserFolderPath):
        """Your Sven Co-op installation: the folder that contains 'svencoop'.

        The client fills this in the first time you pick a folder, so you should
        not have to set it by hand.
        """

        description = "Sven Co-op installation folder"

    game_folder: GameFolder = GameFolder("")


class HalfLifeSvenWeb(WebWorld):
    theme = "dirt"
    tutorials = [
        Tutorial(
            "Multiworld Setup Guide",
            "A guide to setting up Half-Life (Sven Co-op) for Archipelago.",
            "English",
            "setup_en.md",
            "setup/en",
            ["hl1-sven-ap"],
        )
    ]


class HalfLifeSvenWorld(World):
    """Half-Life's campaign, played co-operatively in Sven Co-op, with every
    mission and every weapon locked behind Archipelago items."""

    game = GAME_NAME
    options_dataclass = HalfLifeSvenOptions
    options: HalfLifeSvenOptions
    web = HalfLifeSvenWeb()

    settings_key = SETTINGS_KEY
    settings: ClassVar[HalfLifeSvenSettings]

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
        self.starting_chapter: str = ""
        # Missions left out of this seed: no regions, no checks, no unlock item,
        # and they do not count toward `missions_required`.
        self.excluded_chapters: set[str] = set()
        # Whole categories of check switched off in the YAML, by trigger type.
        self.excluded_triggers: set[str] = set()

    # -- generation ------------------------------------------------------

    def generate_early(self) -> None:
        if not self.options.include_black_mesa_inbound:
            self.excluded_chapters.add(INTRO_CHAPTER)
        if not self.options.chargesanity:
            self.excluded_triggers.add(CHARGER_TRIGGER)

        self.available_item_names = set(weapon_items)
        for name in optional_items:
            if getattr(self.options, OPTIONAL_ITEM_NAMES[name]):
                self.available_item_names.add(name)
        self.available_item_names.update(
            unlock_item_for_chapter[chapter["key"]]
            for chapter in self.included_chapters
            if chapter["key"] in unlock_item_for_chapter
        )

        # Exactly one mission is playable from the word go, and it has to be one
        # that a player with nothing but a crowbar can actually walk into. Picking
        # a gated mission (anything from We've Got Hostiles on, under strict logic)
        # leaves sphere one empty and fill has nowhere to put its first item.
        candidates = [
            chapter for chapter in self.included_chapters
            if not chapter["is_goal"] and chapter_is_startable(self, chapter)
        ]
        fallback = [c for c in self.included_chapters if not c["is_goal"]]
        starting = self.random.choice(candidates or fallback)
        self.starting_chapter = starting["key"]
        self.multiworld.push_precollected(
            self.create_item(unlock_item_for_chapter[self.starting_chapter])
        )

        # `missions_required` cannot exceed the number of missions in the seed.
        unlockable = len([c for c in self.included_chapters if not c["is_goal"]])
        if self.options.missions_required.value > unlockable:
            self.options.missions_required.value = unlockable

    @property
    def included_chapters(self) -> list[dict[str, Any]]:
        """Every mission this seed actually contains, goal mission included."""
        return [c for c in CHAPTERS if c["key"] not in self.excluded_chapters]

    def create_regions(self) -> None:
        create_regions(self)

    def create_item(self, name: str) -> HalfLifeSvenItem:
        return create_item(self, name)

    def create_items(self) -> None:
        pool: list[HalfLifeSvenItem] = []

        for name in sorted(self.available_item_names):
            if name == unlock_item_for_chapter.get(self.starting_chapter):
                continue  # already in the starting inventory
            pool.append(self.create_item(name))

        remaining = len(self.multiworld.get_unfilled_locations(self.player)) - len(pool)
        if remaining < 0:
            raise AssertionError(
                f"{self.game}: {-remaining} more progression items than locations"
            )
        pool += [self.create_item(name) for name in self.get_filler_names(remaining)]

        self.multiworld.itempool += pool

    def get_filler_names(self, count: int) -> list[str]:
        return self.random.choices(filler_items, weights=filler_weights, k=count)

    def get_filler_item_name(self) -> str:
        return self.random.choices(filler_items, weights=filler_weights, k=1)[0]

    def set_rules(self) -> None:
        # Entrance rules are attached in `create_regions`; only the win condition
        # is left, and it is simply "hold the Victory event".
        self.multiworld.completion_condition[self.player] = (
            lambda state: state.has(VICTORY, self.player)
        )

    # -- runtime ---------------------------------------------------------

    def fill_slot_data(self) -> dict[str, Any]:
        """Everything the client needs to drive the game without shipping its own
        copy of the seed's settings."""
        return {
            "missions_required": self.options.missions_required.value,
            "goal_chapter": GOAL_CHAPTER["key"],
            "starting_chapter": self.starting_chapter,
            # Missions that are not in this seed. The client tells the plugin, so
            # the in-game list says "not in this seed" rather than showing a
            # mission that stays locked forever with no explanation.
            "excluded_chapters": sorted(self.excluded_chapters),
            "starting_weapons": STARTING_WEAPONS,
            "death_link": bool(self.options.death_link),
            "death_link_amnesty": self.options.death_link_amnesty.value,
            "shuffle_hev_suit": bool(self.options.shuffle_hev_suit),
            "shuffle_longjump": bool(self.options.shuffle_longjump),
        }
