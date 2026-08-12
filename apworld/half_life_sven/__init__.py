"""Archipelago world for the single-player campaigns shipped in Sven Co-op.

The Sven Co-op campaign portal (`-sp_campaign_portal`) is the hub, and it fronts
four campaigns: Half-Life, Opposing Force, Blue Shift and They Hunger. A YAML
toggle decides which of them a seed contains.

Within each, a mission is locked until its unlock item arrives and weapons must
be received before they can be picked up. Every enabled campaign hands you one of
its missions at the start, and every enabled campaign's finale is a goal: the
seed is won when all of them are done.
"""

from __future__ import annotations

from typing import Any, ClassVar

import settings
from BaseClasses import Tutorial
from worlds.AutoWorld import WebWorld, World
from worlds.LauncherComponents import Component, Type, components, launch_subprocess

from .client.settings import SETTINGS_KEY

from .data import (
    CAMPAIGNS,
    CAMPAIGN_MISSION_OPTIONS,
    CAMPAIGN_OPTIONS,
    CHAPTERS,
    CHARGER_TRIGGER,
    DEFAULT_CAMPAIGN,
    FIXED_STARTING_WEAPONS,
    INTRO_CHAPTER,
    OPTIONAL_ITEM_NAMES,
    STARTING_WEAPONS,
    melee_starters_for,
    victory_event,
)
from .items import (
    HalfLifeSvenItem,
    create_item,
    filler_items,
    filler_weights,
    item_campaign,
    item_campaigns,
    item_name_groups,
    item_name_to_id,
    optional_items,
    trap_items,
    trap_weights,
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
        # Campaigns this seed contains, in campaign.json order.
        self.included_campaigns: list[str] = []
        # One mission per enabled campaign, open from the first spawn.
        self.starting_chapters: set[str] = set()
        # Missions left out of this seed: no regions, no checks, no unlock item,
        # and they do not count toward `missions_required`.
        self.excluded_chapters: set[str] = set()
        # Whole categories of check switched off in the YAML, by trigger type.
        self.excluded_triggers: set[str] = set()
        # `missions_required` clamped to each campaign's own size, since a
        # campaign cannot ask for more missions than it has.
        self.missions_required_for: dict[str, int] = {}
        # Classnames granted from the first spawn and never taken away. The
        # melee half is chosen per seed when `random_starting_weapon` is on.
        self.starting_weapons: list[str] = list(STARTING_WEAPONS)
        # The item name of that melee weapon, when it has one. It leaves the pool:
        # you cannot be sent a wrench you are already holding.
        self.starting_melee_item: str = ""

    # -- generation ------------------------------------------------------

    def generate_early(self) -> None:
        self.included_campaigns = [
            campaign["key"] for campaign in CAMPAIGNS
            if getattr(self.options, CAMPAIGN_OPTIONS[campaign["key"]])
        ]
        # A seed has to contain something. Rather than refuse to generate, fall
        # back to the campaign this world started life as.
        if not self.included_campaigns:
            self.included_campaigns = [DEFAULT_CAMPAIGN]

        # A campaign that is switched off is excluded mission by mission, which
        # is machinery that already exists end to end: no regions, no checks, no
        # unlock items, and the game reports "not in this seed" at its consoles.
        for chapter in CHAPTERS:
            if chapter["campaign"] not in self.included_campaigns:
                self.excluded_chapters.add(chapter["key"])

        if not self.options.include_black_mesa_inbound:
            self.excluded_chapters.add(INTRO_CHAPTER)
        if not self.options.chargesanity:
            self.excluded_triggers.add(CHARGER_TRIGGER)

        self.choose_starting_weapons()

        # Weapons come from the campaigns in the seed. Everything they bring goes
        # into one pool, so an Opposing Force seed with Half-Life enabled can hand
        # you a displacer in Black Mesa and a crossbow on Gene Worm.
        #
        # Membership is "does any campaign in this seed actually contain one",
        # not "which campaign declared it". Half-Life declares the shotgun and
        # Opposing Force is full of them, so attributing it to Half-Life alone
        # left an Opposing Force seed with shotguns and no shotgun item, which
        # meant every one of them refused for the whole run.
        self.available_item_names = {
            name for name in weapon_items
            if set(item_campaigns.get(name, [item_campaign.get(name, DEFAULT_CAMPAIGN)]))
            & set(self.included_campaigns)
            and name != self.starting_melee_item
        }
        for name in optional_items:
            if getattr(self.options, OPTIONAL_ITEM_NAMES[name]):
                self.available_item_names.add(name)
        self.available_item_names.update(
            unlock_item_for_chapter[chapter["key"]]
            for chapter in self.included_chapters
            if chapter["key"] in unlock_item_for_chapter
        )

        # Every campaign in the seed opens with one of its own missions playable,
        # and each has to be one a player with nothing but a crowbar can actually
        # walk into. Picking a gated mission (anything from We've Got Hostiles on,
        # under strict logic) leaves sphere one empty and fill has nowhere to put
        # its first item.
        for campaign_key in self.included_campaigns:
            chapters = [
                chapter for chapter in self.included_chapters
                if chapter["campaign"] == campaign_key and not chapter["is_goal"]
            ]
            if not chapters:
                continue  # every mission of it was excluded some other way
            candidates = [c for c in chapters if chapter_is_startable(self, c)]
            starting = self.random.choice(candidates or chapters)
            self.starting_chapters.add(starting["key"])
            self.multiworld.push_precollected(
                self.create_item(unlock_item_for_chapter[starting["key"]])
            )

        # Each campaign's own setting, clamped to the missions it actually has in
        # this seed: excluding Black Mesa Inbound leaves Half-Life one short, and
        # asking for more than exist would seal a finale permanently.
        for campaign_key in self.included_campaigns:
            option = getattr(self.options, CAMPAIGN_MISSION_OPTIONS[campaign_key])
            available = len([
                chapter for chapter in self.included_chapters
                if chapter["campaign"] == campaign_key and not chapter["is_goal"]
            ])
            self.missions_required_for[campaign_key] = min(option.value, available)

    def choose_starting_weapons(self) -> None:
        """Decide what the run opens with.

        The medkit always, plus one melee weapon. Left alone that is the crowbar,
        exactly as before; with `random_starting_weapon` it is any melee weapon
        the seed's campaigns could hand out, so an Opposing Force run can open on
        a pipe wrench and a They Hunger run on a spanner.

        Whatever it lands on replaces the crowbar rather than joining it. The
        crowbar is gated on an item name the pool never contains, so the moment it
        stops being a starting weapon it is refused like any other ungranted
        weapon, and a wrench start means a wrench for the whole run.
        """
        candidates = melee_starters_for(self.included_campaigns)
        if not self.options.random_starting_weapon or not candidates:
            self.starting_weapons = list(STARTING_WEAPONS)
            return

        name = self.random.choice(sorted(candidates))
        self.starting_weapons = list(candidates[name]) + list(FIXED_STARTING_WEAPONS)
        # Only if it is an item at all: nothing ever sends you a crowbar.
        if name in weapon_items:
            self.starting_melee_item = name

    @property
    def included_chapters(self) -> list[dict[str, Any]]:
        """Every mission this seed actually contains, goal mission included."""
        return [c for c in CHAPTERS if c["key"] not in self.excluded_chapters]

    @property
    def goal_chapters(self) -> list[dict[str, Any]]:
        """The finale of each campaign in the seed. Every one has to be cleared."""
        return [c for c in self.included_chapters if c["is_goal"]]

    def create_regions(self) -> None:
        create_regions(self)

    def create_item(self, name: str) -> HalfLifeSvenItem:
        return create_item(self, name)

    def create_items(self) -> None:
        pool: list[HalfLifeSvenItem] = []

        starting_unlocks = {
            unlock_item_for_chapter[key] for key in self.starting_chapters
        }
        for name in sorted(self.available_item_names):
            if name in starting_unlocks:
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
        # is left. Every campaign in the seed has to be finished, so it is one
        # Victory event per campaign rather than a single shared one -- with one
        # name held four times, any finale would end the run.
        player = self.player
        victories = [victory_event(c["campaign"]) for c in self.goal_chapters]
        self.multiworld.completion_condition[player] = (
            lambda state, names=victories: all(state.has(name, player) for name in names)
        )

    # -- runtime ---------------------------------------------------------

    def fill_slot_data(self) -> dict[str, Any]:
        """Everything the client needs to drive the game without shipping its own
        copy of the seed's settings."""
        return {
            # Kept for a client older than multi-campaign seeds: it reads a single
            # number and a single goal, which is exactly Half-Life's pair.
            "missions_required": self.missions_required_for.get(
                DEFAULT_CAMPAIGN, self.options.missions_required.value
            ),
            "goal_chapter": next(
                (c["key"] for c in self.goal_chapters if c["campaign"] == DEFAULT_CAMPAIGN),
                self.goal_chapters[0]["key"] if self.goal_chapters else "",
            ),
            "campaigns": list(self.included_campaigns),
            # What each campaign's finale is waiting on. The client counts
            # completions per campaign and tells the game which finales are open.
            "campaign_missions_required": dict(self.missions_required_for),
            "goal_chapters": sorted(c["key"] for c in self.goal_chapters),
            "starting_chapters": sorted(self.starting_chapters),
            # Missions that are not in this seed. The client tells the plugin, so
            # the in-game list says "not in this seed" rather than showing a
            # mission that stays locked forever with no explanation.
            "excluded_chapters": sorted(self.excluded_chapters),
            # What the run opens with, and what the game must therefore never
            # take away. Per seed since `random_starting_weapon`, so the plugin
            # is told rather than reading the static list in checkdata.txt.
            "starting_weapons": list(self.starting_weapons),
            "death_link": bool(self.options.death_link),
            "death_link_amnesty": self.options.death_link_amnesty.value,
            "shuffle_hev_suit": bool(self.options.shuffle_hev_suit),
            "shuffle_longjump": bool(self.options.shuffle_longjump),
        }
