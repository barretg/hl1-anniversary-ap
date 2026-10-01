from __future__ import annotations

from BaseClasses import Location

from .data import CHAPTERS, LOCATIONS
from .items import RENAMED_ITEMS

GAME_NAME = "Half-Life"

location_table: dict[str, dict] = {entry["name"]: entry for entry in LOCATIONS}
location_name_to_id: dict[str, int] = {entry["name"]: entry["id"] for entry in LOCATIONS}



def weapon_sources(
    entry: dict, excluded_chapters: set[str], ally_drops: bool = False
) -> list[dict]:
    """The ways to a weapon check this seed counts: each source in an included
    mission, and an ally's drop only with `ally_weapon_drops` on."""
    return [
        source for source in entry.get("sources", ())
        if source["chapter"] not in excluded_chapters
        and (ally_drops or source.get("drop") != "ally")
    ]


def location_in_seed(
    entry: dict, excluded_chapters: set[str], ally_drops: bool = False
) -> bool:
    """Whether a seed leaving these missions out still contains this check.

    A weapon check is there while any source it counts is.
    """
    if "sources" in entry:
        return bool(weapon_sources(entry, excluded_chapters, ally_drops))
    return entry["chapter"] not in excluded_chapters


# Locations grouped by the map region they live in.
locations_by_map: dict[str, list[dict]] = {}
for _entry in LOCATIONS:
    locations_by_map.setdefault(_entry["map"], []).append(_entry)

location_name_groups: dict[str, set[str]] = {
    chapter["name"]: {e["name"] for e in LOCATIONS if e["chapter"] == chapter["key"]}
    for chapter in CHAPTERS
}
location_name_groups["Mission Completions"] = {
    e["name"] for e in LOCATIONS if e["trigger"]["type"] == "chapter_complete"
}
location_name_groups["Weapon Pickups"] = {
    e["name"] for e in LOCATIONS if e["trigger"]["type"] in ("pickup", "weapon_pickup")
}
location_name_groups["Chargers"] = {
    e["name"] for e in LOCATIONS if e["trigger"]["type"] == "charger"
}

# Older releases named locations `Mission - Thing`. Each old name is a group of
# its one location, so a YAML written for them still generates. The old name is
# built from the mission name, not by replacing the first `: `, since a mission
# name may hold one.
_chapter_names = {chapter["key"]: chapter["name"] for chapter in CHAPTERS}
for _entry in LOCATIONS:
    _prefix = _chapter_names[_entry["chapter"]] + ": "
    if _entry["name"].startswith(_prefix):
        _old = _chapter_names[_entry["chapter"]] + " - " + _entry["name"][len(_prefix):]
        location_name_groups[_old] = {_entry["name"]}

# Weapon checks are named after their item, so a renamed item renamed its check.
for _entry in LOCATIONS:
    for _old, _new in RENAMED_ITEMS.items():
        if _entry["name"].endswith("First " + _new):
            location_name_groups[_entry["name"][:-len(_new)] + _old] = {_entry["name"]}

# Drop groups with no members; Archipelago rejects empty location name groups.
location_name_groups = {k: v for k, v in location_name_groups.items() if v}


class HalfLifeLocation(Location):
    game = GAME_NAME
