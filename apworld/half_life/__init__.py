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

import logging
from typing import Any, ClassVar

import settings
from BaseClasses import Tutorial
from Options import OptionError, OptionGroup
from worlds.AutoWorld import WebWorld, World
from worlds.LauncherComponents import Component, Type, components, launch_subprocess

from .client.settings import SETTINGS_KEY

from .data import (
    CAMPAIGNS,
    CAMPAIGNS_BY_KEY,
    CHAPTERS,
    CHARGER_TRIGGER,
    HALF_LIFE,
    MICROWAVE_TRIGGER,
    HEAL_PICKUP_TRIGGER,
    AMMO_PICKUP_TRIGGER,
    BARNEY_TRIGGER,
    CRITICAL_NPC_TRIGGER,
    SCIENTIST_TRIGGER,
    SOLDIER_TRIGGER,
    ITEMS,
    SUPPORTED_CHAPTER_NAMES,
    ABILITY_ITEM_NAMES,
    AIR_ACCELERATE_ITEM,
    OPTIONAL_ITEM_CAMPAIGNS,
    OPTIONAL_ITEM_NAMES,
    VANILLA_WHEN_UNSHUFFLED,
    VICTORY,
    air_accelerate_bounds,
    air_accelerate_steps,
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
    unlock_item_for_chapter,
    weapon_items,
)
from .locations import (
    location_in_seed,
    location_name_groups,
    location_name_to_id,
    location_table,
)
from .options import (
    AirAccelerationMaximum,
    AirAccelerationMinimum,
    AllyWeaponDrops,
    Ammosanity,
    Barneysanity,
    IncludeCriticalNpcs,
    Scientistsanity,
    Soldiersanity,
    BlueShiftChapters,
    BlueShiftMissionsRequired,
    GenerationDifficulty,
    AllowReverse,
    HalfLifeChapters,
    ButterfingersReissue,
    Chargesanity,
    HalfLifeOptions,
    Healsanity,
    IncludeBlueShift,
    IncludeHalfLife,
    IncludeMicrowave,
    IncludeOpposingForce,
    MapShuffle,
    MeleeThrow,
    MissionsRequired,
    OpposingForceChapters,
    OpposingForceMissionsRequired,
    ProgressionMode,
    ProgressiveAirAcceleration,
    RandomStartingWeapon,
    ShuffleFlashlight,
    TransitionHub,
    ShuffleHevSuit,
    ShuffleLongJump,
    TrapPercentage,
    ScientistTrapWeight,
    HeadcrabTrapWeight,
    ButterfingersTrapWeight,
    BotSwarmTrapWeight,
    BunnyHopTrapWeight,
    StickyKeyTrapWeight,
    ReloadTrapWeight,
    ViewmodelStyle,
)
from .regions import create_regions
from .transitions import (
    MAP_CHAPTER, connect_transitions, create_transition_regions, transition_slot_data,
)
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
            "A guide to setting up Half-Life Trilogy for Archipelago.",
            "English",
            "setup_en.md",
            "setup/en",
            ["hl1-anniversary-ap"],
        )
    ]

    # Which games the seed holds, and how much of each the goal asks, together.
    # The rest grouped by what they change: the item pool, which things are
    # checks, pickups and NPC deaths as checks, how the game plays, and traps.
    # Anything left out (logic difficulty, intro missions, DeathLink) stays in
    # Game Options.
    option_groups = [
        OptionGroup(
            "Games",
            [IncludeHalfLife, MissionsRequired,
             IncludeOpposingForce, OpposingForceMissionsRequired,
             IncludeBlueShift, BlueShiftMissionsRequired],
        ),
        OptionGroup(
            "Item Pool",
            [RandomStartingWeapon, ShuffleHevSuit, ShuffleLongJump,
             ShuffleFlashlight, MeleeThrow, ProgressiveAirAcceleration,
             AirAccelerationMinimum, AirAccelerationMaximum],
        ),
        OptionGroup(
            "Checks",
            [Chargesanity, IncludeMicrowave],
        ),
        OptionGroup(
            "Itemsanity",
            [Healsanity, Ammosanity],
        ),
        OptionGroup(
            "NPCSanity",
            [Scientistsanity, Barneysanity, Soldiersanity, IncludeCriticalNpcs],
        ),
        OptionGroup(
            "Gameplay",
            [ViewmodelStyle, AllyWeaponDrops],
        ),
        OptionGroup(
            "Traps",
            [TrapPercentage, ButterfingersReissue,
             ScientistTrapWeight, HeadcrabTrapWeight, ButterfingersTrapWeight,
             BotSwarmTrapWeight, BunnyHopTrapWeight, StickyKeyTrapWeight,
             ReloadTrapWeight],
        ),
        OptionGroup(
            "Map Randomization",
            [ProgressionMode, MapShuffle, GenerationDifficulty, AllowReverse, TransitionHub,
             HalfLifeChapters, OpposingForceChapters, BlueShiftChapters],
            start_collapsed=True,
        ),
    ]


class HalfLifeWorld(World):
    """Half-Life Trilogy: Half-Life, Opposing Force and Blue Shift, with every
    mission and every weapon locked behind Archipelago items."""

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
        # Whether an ally's dropped weapon is a way to its weapon check.
        self.ally_weapon_drops: bool = False
        # Transitions mode: the chapters whose maps make up the world, by key.
        self.transition_chapters: list[str] = []
        # Transitions mode's plan (`transitions.Plan`), exits by transition id,
        # regions by name, and the transitions left over in odd groups.
        self.transition_plan = None
        self.transition_exits: dict = {}
        self.transition_regions: dict = {}
        self.transition_odd: list[str] = []

    @property
    def transitions_mode(self) -> bool:
        return self.options.progression_mode == ProgressionMode.option_transitions

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

    def validate_map_options(self) -> None:
        """Settle the Map Randomization group before anything reads it.

        Hub mode only has missions to shuffle inside, so `area` and `total`
        fall back to `chapter_maps`. Transitions mode needs at least one
        supported chapter and at least one goal chapter among them.
        """
        options = self.options
        transitions = options.progression_mode == ProgressionMode.option_transitions
        if not transitions and options.map_shuffle.value in (
                MapShuffle.option_area, MapShuffle.option_total):
            logging.warning(
                f"{self.player_name}: map_shuffle {options.map_shuffle.current_key} "
                "needs progression_mode transitions; using chapter_maps")
            options.map_shuffle.value = MapShuffle.option_chapter_maps
        if not transitions:
            return

        lists = {
            HALF_LIFE: options.half_life_chapters,
            "opposing_force": options.opposing_force_chapters,
            "blue_shift": options.blue_shift_chapters,
        }
        if not any(SUPPORTED_CHAPTER_NAMES.values()):
            raise OptionError(
                f"{self.player_name}: progression_mode transitions is not playable "
                "yet: no chapters are supported yet")
        chapters: list[str] = []
        for key in list(self.campaigns):
            supported = SUPPORTED_CHAPTER_NAMES.get(key, [])
            unknown = sorted(set(lists[key].value) - set(supported))
            if unknown:
                raise OptionError(
                    f"{self.player_name}: {lists[key].display_name} names "
                    f"{', '.join(unknown)}, which this version does not support "
                    f"(supported: {', '.join(supported) or 'none'})")
            wanted = [c for c in CHAPTERS if campaign_of(c) == key
                      and c["name"] in lists[key].value]
            if self.options.exclude_intro_missions:
                intro = CAMPAIGNS_BY_KEY[key]["intro_chapter"]
                wanted = [c for c in wanted if c["key"] != intro]
            if not wanted:
                logging.warning(
                    f"{self.player_name}: no {CAMPAIGNS_BY_KEY[key]['name']} "
                    "chapters are included; leaving the game out")
                self.campaigns.remove(key)
                continue
            chapters.extend(c["key"] for c in wanted)
        goals = [c["goal_chapter"] for c in CAMPAIGNS]
        if not any(key in goals for key in chapters):
            names = [next(c["name"] for c in CHAPTERS if c["key"] == g) for g in goals]
            included = ", ".join(CAMPAIGNS_BY_KEY[k]["name"] for k in self.campaigns)
            raise OptionError(
                f"{self.player_name}: transitions mode needs a goal chapter "
                f"({', '.join(names)}) in the included chapter lists; included "
                f"games: {included or 'none'}")
        self.transition_chapters = chapters

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

        passthrough_mode = (passthrough or {}).get("progression_mode")
        if passthrough_mode == "transitions":
            self.options.progression_mode.value = ProgressionMode.option_transitions
            self.options.map_shuffle.value = MapShuffle.options[passthrough["map_shuffle"]]
            self.transition_chapters = list(passthrough.get("transition_chapters", []))
        else:
            self.validate_map_options()
        if self.transitions_mode:
            # The world is the chosen chapters' maps; every other chapter is
            # "not in this seed", as an excluded mission is in hub mode.
            self.excluded_chapters.update(
                c["key"] for c in CHAPTERS if c["key"] not in self.transition_chapters)

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
        if not self.options.include_microwave:
            self.excluded_triggers.add(MICROWAVE_TRIGGER)
        if not self.options.healsanity:
            self.excluded_triggers.add(HEAL_PICKUP_TRIGGER)
        if not self.options.ammosanity:
            self.excluded_triggers.add(AMMO_PICKUP_TRIGGER)
        if not self.options.scientistsanity:
            self.excluded_triggers.add(SCIENTIST_TRIGGER)
        if not self.options.barneysanity:
            self.excluded_triggers.add(BARNEY_TRIGGER)
        if not self.options.soldiersanity:
            self.excluded_triggers.add(SOLDIER_TRIGGER)
        if not self.options.include_critical_npcs:
            self.excluded_triggers.add(CRITICAL_NPC_TRIGGER)

        # Both sets come straight from the seed under the tracker: it may be
        # working without the YAML, in which case its options are defaults and
        # would give it a different set of locations than the server has.
        if passthrough:
            self.excluded_chapters = set(passthrough.get("excluded_chapters", ())) | {
                c["key"] for c in CHAPTERS if campaign_of(c) not in self.campaigns
            }
            self.excluded_triggers = set(passthrough.get("excluded_triggers", ()))
            # A seed from before the microwave was a check has none.
            if not passthrough.get("include_microwave", False):
                self.excluded_triggers.add(MICROWAVE_TRIGGER)
            # Nor did one from before these were checks have any pickups.
            if not passthrough.get("healsanity", False):
                self.excluded_triggers.add(HEAL_PICKUP_TRIGGER)
            if not passthrough.get("ammosanity", False):
                self.excluded_triggers.add(AMMO_PICKUP_TRIGGER)
            if not passthrough.get("scientistsanity", False):
                self.excluded_triggers.add(SCIENTIST_TRIGGER)
            if not passthrough.get("barneysanity", False):
                self.excluded_triggers.add(BARNEY_TRIGGER)
            if not passthrough.get("soldiersanity", False):
                self.excluded_triggers.add(SOLDIER_TRIGGER)
            if not passthrough.get("include_critical_npcs", False):
                self.excluded_triggers.add(CRITICAL_NPC_TRIGGER)

        self.ally_weapon_drops = bool(self.options.ally_weapon_drops)
        if passthrough:
            # A seed from before the option is one without it.
            self.ally_weapon_drops = bool(passthrough.get("ally_weapon_drops", False))

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
            owners = OPTIONAL_ITEM_CAMPAIGNS.get(name, (campaign_of(items_by_name[name]),))
            if not any(owner in self.campaigns for owner in owners):
                continue
            if getattr(self.options, OPTIONAL_ITEM_NAMES[name]):
                self.available_item_names.add(name)
            elif name in VANILLA_WHEN_UNSHUFFLED and location_in_seed(
                location_table[VANILLA_WHEN_UNSHUFFLED[name]],
                self.excluded_chapters, self.ally_weapon_drops,
            ):
                self.available_item_names.add(name)
                self.vanilla_placements[name] = VANILLA_WHEN_UNSHUFFLED[name]
        self.available_item_names.update(
            name for name, option in ABILITY_ITEM_NAMES.items()
            if getattr(self.options, option)
        )
        # No mission unlocks in transitions mode: the world is walked, not
        # warped into.
        if not self.transitions_mode:
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

        if self.transitions_mode:
            # The start is drawn with the rest of the world in `create_regions`.
            return

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
        if self.transitions_mode:
            create_transition_regions(self)
            self.starting_chapter = MAP_CHAPTER[self.transition_plan.start_map]
        else:
            create_regions(self)

    def connect_entrances(self) -> None:
        if self.transitions_mode:
            connect_transitions(self)

    def create_item(self, name: str) -> HalfLifeItem:
        return create_item(self, name)

    def create_items(self) -> None:
        pool: list[HalfLifeItem] = []

        starting_unlock = unlock_item_for_chapter.get(self.starting_chapter, "")
        for name in sorted(self.available_item_names):
            if name == starting_unlock:
                continue  # already in the starting inventory
            if name in self.vanilla_placements:
                location = self.get_location(self.vanilla_placements[name])
                location.place_locked_item(self.create_item(name))
                continue
            pool.append(self.create_item(name))
        pool += [
            self.create_item(AIR_ACCELERATE_ITEM)
            for _ in range(self.air_accelerate_item_count)
        ]

        remaining = len(self.multiworld.get_unfilled_locations(self.player)) - len(pool)
        if remaining < 0:
            raise AssertionError(
                f"{self.game}: {-remaining} more progression items than locations"
            )
        pool += [self.create_item(name) for name in self.get_filler_names(remaining)]

        self.multiworld.itempool += pool

    @property
    def air_accelerate_item_count(self) -> int:
        """How many Progressive Air Acceleration items this seed places."""
        if not self.options.progressive_air_acceleration:
            return 0
        return len(air_accelerate_steps(
            self.options.air_acceleration_minimum.value,
            self.options.air_acceleration_maximum.value,
        ))

    def get_filler_names(self, count: int) -> list[str]:
        """Fill the leftover locations, with `trap_percentage` of them traps."""
        weights = [self.trap_weight(name) for name in trap_items]
        traps = round(count * self.options.trap_percentage.value / 100)
        # Every trap weighted to 0 means no traps at all, not a crash.
        if not any(weights):
            traps = 0
        names = self.random.choices(trap_items, weights=weights, k=traps) if traps else []
        names += self.random.choices(
            filler_items, weights=filler_weights, k=count - traps
        )
        # Otherwise every trap lands in the same stretch of the pool.
        self.random.shuffle(names)
        return names

    def trap_weight(self, name: str) -> int:
        """The YAML's weight for one trap, e.g. `headcrab_trap_weight`."""
        return getattr(self.options, name.lower().replace(" ", "_") + "_weight").value

    def get_filler_item_name(self) -> str:
        return self.random.choices(filler_items, weights=filler_weights, k=1)[0]

    def set_rules(self) -> None:
        # Entrance rules are attached in `create_regions`; only the win condition
        # is left.
        player = self.player
        # One Victory per included game's finale, and the seed wants them all.
        # In transitions mode, one per included boss chapter.
        finales = (len(self.transition_plan.bosses) if self.transitions_mode
                   else len(self.campaigns))
        self.multiworld.completion_condition[player] = (
            lambda state: state.has(VICTORY, player, finales)
        )

    # -- runtime ---------------------------------------------------------

    def fill_slot_data(self) -> dict[str, Any]:
        """Everything the client needs to drive the game without shipping its own
        copy of the seed's settings."""
        goals = {key: CAMPAIGNS_BY_KEY[key]["goal_chapter"] for key in self.campaigns}
        # Transitions mode only, so a hub seed's slot data is as it was.
        extra = transition_slot_data(self) if self.transitions_mode else {}
        return extra | {
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
            # Also for the tracker: seeds from before this key had no microwave
            # check, though their `excluded_triggers` does not say so.
            "include_microwave": MICROWAVE_TRIGGER not in self.excluded_triggers,
            # The same for the pickups.
            "healsanity": HEAL_PICKUP_TRIGGER not in self.excluded_triggers,
            "ammosanity": AMMO_PICKUP_TRIGGER not in self.excluded_triggers,
            "scientistsanity": SCIENTIST_TRIGGER not in self.excluded_triggers,
            "barneysanity": BARNEY_TRIGGER not in self.excluded_triggers,
            "soldiersanity": SOLDIER_TRIGGER not in self.excluded_triggers,
            "include_critical_npcs": CRITICAL_NPC_TRIGGER not in self.excluded_triggers,
            # What the run opens with, and what the game must therefore never
            # take away.
            "starting_weapons": [self.starting_weapon],
            "death_link": bool(self.options.death_link),
            "death_link_amnesty": self.options.death_link_amnesty.value,
            "viewmodel_style": self.options.viewmodel_style.current_key,
            "shuffle_hev_suit": bool(self.options.shuffle_hev_suit),
            "shuffle_longjump": bool(self.options.shuffle_longjump),
            "shuffle_flashlight": bool(self.options.shuffle_flashlight),
            "melee_throw": bool(self.options.melee_throw),
            # [minimum, maximum] the client walks the items between, or None
            # when air acceleration is left to the game. Swapped and clamped
            # here so the client never has to second-guess them.
            "air_acceleration": list(air_accelerate_bounds(
                self.options.air_acceleration_minimum.value,
                self.options.air_acceleration_maximum.value,
            )) if self.options.progressive_air_acceleration else None,
            "butterfingers_reissue": bool(self.options.butterfingers_reissue),
            # Logic only, for Universal Tracker: whether killing an ally for
            # their weapon counts toward its check.
            "ally_weapon_drops": self.ally_weapon_drops,
            # Unshuffled equipment that is a real item at its vanilla location,
            # so the client must gate its pickup like any other. Seeds from
            # before this existed left the long jump module ungated instead.
            "placed_at_vanilla": sorted(self.vanilla_placements),
            # Seeds from before this key also took the First HEV Suit from Lambda
            # Core, where no suit spawns; the client sends it there for them.
            "lambda_core_suit": False,
            # Game -> the item that is armour on its maps, and the equipment
            # actually shuffled into this seed's pool. Named and shaped as the
            # Sven world writes them; nothing here reads them yet.
            "armour_items": {c["key"]: c["armour_item"] for c in CAMPAIGNS},
            "shuffled_equipment": sorted(
                name for name in optional_items
                if name in self.available_item_names
                and name not in self.vanilla_placements
            ),
        }
