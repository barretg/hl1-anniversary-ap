"""Region graph.

    Menu -> Hub -> (first map of each mission) -> ... -> (last map of that mission)

Each map is its own region so that a check in part 4 of Surface Tension is
correctly gated behind reaching parts 1-3. Missions are entered only from the
Hub, which mirrors how the game is played here: you warp into a mission from the
hub and come back to it when the mission ends. Retail's own transitions inside a
mission are left alone; only the ones crossing a mission boundary are taken over.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from BaseClasses import Region

from .data import MISSION_COMPLETE, VICTORY
from .locations import HalfLifeLocation, locations_by_map
from .rules import chapter_entry_rule, location_rule

if TYPE_CHECKING:
    from . import HalfLifeWorld

MENU = "Menu"
HUB = "Hub"


def create_regions(world: "HalfLifeWorld") -> None:
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
                # A check category the YAML turned off is left out of the seed
                # rather than placed and made unreachable.
                if entry["trigger"]["type"] in world.excluded_triggers:
                    continue

                location = HalfLifeLocation(player, entry["name"], entry["id"], region)
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


def add_event(world: "HalfLifeWorld", region: Region, chapter: dict) -> None:
    """Finishing a mission grants an event item.

    `Mission Complete` is what `missions_required` counts, so the finale is not
    one: it is the thing the count opens, and clearing it grants `Victory`
    instead, which is the seed's win condition.
    """
    name = VICTORY if chapter["is_goal"] else MISSION_COMPLETE
    location = HalfLifeLocation(
        world.player, f"{chapter['name']} - Mission Cleared", None, region
    )
    location.place_locked_item(world.create_item(name))
    region.locations.append(location)
