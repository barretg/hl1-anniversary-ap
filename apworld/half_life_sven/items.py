from __future__ import annotations

from typing import TYPE_CHECKING

from BaseClasses import Item, ItemClassification

from .data import EVENT_ITEM_NAMES, ITEMS

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

trap_items: list[str] = [e["name"] for e in ITEMS if e["classification"] == "trap"]
trap_weights: list[int] = [e.get("weight", 1) for e in ITEMS if e["classification"] == "trap"]

chapter_unlock_items: list[str] = [e["name"] for e in ITEMS if e.get("group") == "chapter"]
weapon_items: list[str] = [e["name"] for e in ITEMS if e.get("group") == "weapon"]
optional_items: list[str] = [e["name"] for e in ITEMS if e.get("group") == "optional"]

# Chapter key -> the item that unlocks it.
unlock_item_for_chapter: dict[str, str] = {
    entry["chapter"]: entry["name"] for entry in ITEMS if entry.get("group") == "chapter"
}

# Item name -> the campaign that brought it. Weapons and mission unlocks carry
# one; filler and traps belong to no campaign and are always in the pool.
item_campaign: dict[str, str] = {
    entry["name"]: entry["campaign"] for entry in ITEMS if "campaign" in entry
}

# Item name -> every campaign whose maps actually contain it, which is the
# question that decides whether a seed needs the item at all. Half-Life declares
# the shotgun but Opposing Force is full of them, so an Opposing Force seed needs
# the Shotgun item even with Half-Life switched off.
item_campaigns: dict[str, list[str]] = {
    entry["name"]: entry["campaigns"] for entry in ITEMS if "campaigns" in entry
}

item_name_groups: dict[str, set[str]] = {
    "Weapons": set(weapon_items),
    "Mission Unlocks": set(chapter_unlock_items),
    "Equipment": set(optional_items),
    "Filler": set(filler_items),
    "Traps": set(trap_items),
}

# Events carry no id -- they exist only to express logic. There is a pair per
# campaign, since both are counted and the counts must stay separate.
EVENT_ITEMS = EVENT_ITEM_NAMES


class HalfLifeSvenItem(Item):
    game = "Half-Life (Sven Co-op)"


def create_item(world: "HalfLifeSvenWorld", name: str) -> HalfLifeSvenItem:
    if name in EVENT_ITEMS:
        return HalfLifeSvenItem(name, ItemClassification.progression, None, world.player)
    entry = item_table[name]
    classification = CLASSIFICATIONS[entry["classification"]]
    return HalfLifeSvenItem(name, classification, entry["id"], world.player)
