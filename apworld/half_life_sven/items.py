from __future__ import annotations

from typing import TYPE_CHECKING

from BaseClasses import Item, ItemClassification

from .data import ITEMS, MISSION_COMPLETE, VICTORY

if TYPE_CHECKING:
    from . import HalfLifeSvenWorld

CLASSIFICATIONS = {
    "progression": ItemClassification.progression,
    "useful": ItemClassification.useful,
    "filler": ItemClassification.filler,
    "trap": ItemClassification.trap,
}

item_table: dict[str, dict] = {entry["name"]: entry for entry in ITEMS}
item_name_to_id: dict[str, int] = {entry["name"]: entry["id"] for entry in ITEMS}

filler_items: list[str] = [e["name"] for e in ITEMS if e["classification"] == "filler"]
filler_weights: list[int] = [e.get("weight", 1) for e in ITEMS if e["classification"] == "filler"]

chapter_unlock_items: list[str] = [e["name"] for e in ITEMS if e.get("group") == "chapter"]
weapon_items: list[str] = [e["name"] for e in ITEMS if e.get("group") == "weapon"]
optional_items: list[str] = [e["name"] for e in ITEMS if e.get("group") == "optional"]

# Chapter key -> the item that unlocks it.
unlock_item_for_chapter: dict[str, str] = {
    entry["chapter"]: entry["name"] for entry in ITEMS if entry.get("group") == "chapter"
}

item_name_groups: dict[str, set[str]] = {
    "Weapons": set(weapon_items),
    "Mission Unlocks": set(chapter_unlock_items),
    "Equipment": set(optional_items),
    "Filler": set(filler_items),
}

# Events carry no id -- they exist only to express logic.
EVENT_ITEMS = (MISSION_COMPLETE, VICTORY)


class HalfLifeSvenItem(Item):
    game = "half_life_sven"


def create_item(world: "HalfLifeSvenWorld", name: str) -> HalfLifeSvenItem:
    if name in EVENT_ITEMS:
        return HalfLifeSvenItem(name, ItemClassification.progression, None, world.player)
    entry = item_table[name]
    classification = CLASSIFICATIONS[entry["classification"]]
    return HalfLifeSvenItem(name, classification, entry["id"], world.player)
