"""Region graph.

    Menu -> Hub -> (first map of each mission) -> ... -> (last map of that mission)

Each Sven Co-op map is its own region so that a check in part 4 of Surface
Tension is correctly gated behind reaching parts 1-3. Missions are entered only
from the Hub, which mirrors how the game actually works: you leave the campaign
portal into a mission and come back to it when the mission ends.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from BaseClasses import Region

from .data import MISSION_COMPLETE, VICTORY
from .locations import HalfLifeSvenLocation, locations_by_map
from .rules import chapter_entry_rule, location_rule

if TYPE_CHECKING:
    from . import HalfLifeSvenWorld

MENU = "Menu"
HUB = "Hub"


def create_regions(world: "HalfLifeSvenWorld") -> None:
    multiworld = world.multiworld
    player = world.player

    menu = Region(MENU, player, multiworld)
    hub = Region(HUB, player, multiworld)
    multiworld.regions += [menu, hub]
    menu.connect(hub)

    # An excluded mission gets no regions at all, so its checks never enter the
    # datapackage-backed location pool for this slot. Leaving them in place with
    # no way to unlock the mission would make them permanently unreachable, which
    # `accessibility: full` correctly refuses to generate.
    for chapter in world.included_chapters:
        previous: Region | None = None
        for map_name in chapter["maps"]:
            region = Region(map_name, player, multiworld)
            multiworld.regions.append(region)

            for entry in locations_by_map.get(map_name, []):
                location = HalfLifeSvenLocation(
                    player, entry["name"], entry["id"], region
                )
                rule = location_rule(world, entry)
                if rule is not None:
                    location.access_rule = rule
                region.locations.append(location)

            if previous is None:
                hub.connect(
                    region,
                    f"Enter {chapter['name']}",
                    chapter_entry_rule(world, chapter),
                )
            else:
                previous.connect(region, f"{chapter['name']}: {map_name}")
            previous = region

        assert previous is not None
        add_event(world, previous, chapter)


def add_event(world: "HalfLifeSvenWorld", region: Region, chapter: dict) -> None:
    """Finishing a mission grants an event item.

    Non-goal missions grant `Mission Complete`, which is what `missions_required`
    counts. The goal mission grants `Victory`.
    """
    name = VICTORY if chapter["is_goal"] else MISSION_COMPLETE
    location = HalfLifeSvenLocation(
        world.player, f"{chapter['name']} - Mission Cleared", None, region
    )
    location.place_locked_item(world.create_item(name))
    region.locations.append(location)
