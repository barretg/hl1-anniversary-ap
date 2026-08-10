"""Generate `apworld/half_life_sven/data/campaign.json` from the shipped BSPs.

The Half-Life campaign maps are the source of truth for what a location can be:
we only ever create a check for something that provably exists in the map file.
The generated JSON is committed, so neither the apworld nor the client needs Sven
Co-op installed -- only this tool does.

Usage:
    python tools/build_campaign_data.py --maps "<...>/svencoop/maps"
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from bsp_entities import load_map
from campaign_layout import (
    CHAPTERS,
    CLASSNAME_TO_ITEM,
    GOAL_CHAPTER,
    IGNORED_MONSTERS,
    ITEM_ID_BASE,
    KILL_MILESTONE_FRACTIONS,
    LOCATION_ID_BASE,
    MIN_LOCATIONS_PER_MAP,
    NOTABLE_MONSTERS,
    OPTIONAL_ITEMS,
    REQUIREMENT_GROUPS,
    STARTING_WEAPONS,
    WEAPON_ITEMS,
    CHAPTER_GATES,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "apworld" / "half_life_sven" / "data" / "campaign.json"

SUPPLY_CLASSNAMES = {
    "item_battery": "Battery",
    "item_healthkit": "Health Kit",
}


def part_label(chapter_maps: list[str], map_name: str) -> str:
    """`Part 3` for multi-map chapters, empty for single-map ones."""
    if len(chapter_maps) == 1:
        return ""
    return f"Part {chapter_maps.index(map_name) + 1}"


def weapon_display(classname: str) -> str:
    """Human name for a pickup classname, falling back to a tidied classname."""
    item = CLASSNAME_TO_ITEM.get(classname)
    if item:
        return item
    tidy = classname.replace("weapon_", "").replace("item_", "").replace("_", " ")
    return tidy.title()


class LocationBuilder:
    """Assigns stable ids and guarantees unique, readable location names."""

    def __init__(self) -> None:
        self.locations: list[dict] = []
        self._used_names: set[str] = set()

    def add(self, chapter: dict, map_name: str, base_name: str, trigger: dict,
            requires: str | None = None) -> dict:
        name = self._unique(f"{chapter['name']} - {base_name}")
        location = {
            "id": LOCATION_ID_BASE + len(self.locations),
            "name": name,
            "chapter": chapter["key"],
            "map": map_name,
            "trigger": trigger,
        }
        if requires:
            location["requires"] = requires
        self.locations.append(location)
        return location

    def _unique(self, name: str) -> str:
        if name not in self._used_names:
            self._used_names.add(name)
            return name
        for suffix in range(2, 100):
            candidate = f"{name} #{suffix}"
            if candidate not in self._used_names:
                self._used_names.add(candidate)
                return candidate
        raise RuntimeError(f"could not make {name!r} unique")


def build(maps_dir: Path) -> dict:
    chapters = [
        {"key": key, "name": name, "maps": maps, "index": index}
        for index, (key, name, maps) in enumerate(CHAPTERS)
    ]

    entities: dict[str, list[dict[str, str]]] = {}
    for chapter in chapters:
        for map_name in chapter["maps"]:
            bsp = maps_dir / f"{map_name}.bsp"
            if not bsp.exists():
                raise SystemExit(f"missing map: {bsp}")
            entities[map_name] = load_map(bsp)

    builder = LocationBuilder()

    for chapter in chapters:
        chapter_maps = chapter["maps"]
        for map_name in chapter_maps:
            ents = entities[map_name]
            label = part_label(chapter_maps, map_name)
            suffix = f" ({label})" if label else ""

            # Reaching a later map of a multi-map chapter is itself progress.
            if map_name != chapter_maps[0]:
                builder.add(
                    chapter,
                    map_name,
                    f"{label} Reached",
                    {"type": "map_reached", "map": map_name},
                )

            # Every distinct pickup classname present in the map becomes one
            # check -- collecting any instance of it fires the check once.
            pickups = sorted({
                e["classname"] for e in ents
                if e["classname"].startswith("weapon_")
                or e["classname"] in ("item_suit", "item_longjump")
            })
            for classname in pickups:
                builder.add(
                    chapter,
                    map_name,
                    f"{weapon_display(classname)}{suffix}",
                    {"type": "pickup", "map": map_name, "classnames": [classname]},
                )

            # First kill of each notable monster actually placed in the map.
            present = sorted({
                e["classname"] for e in ents if e["classname"] in NOTABLE_MONSTERS
            })
            for classname in present:
                display, requirement = NOTABLE_MONSTERS[classname]
                builder.add(
                    chapter,
                    map_name,
                    f"{display} Slain{suffix}",
                    {"type": "kill", "map": map_name, "classname": classname},
                    requires=requirement,
                )

    # Top up sparse maps so no map is a dead stretch with nothing to find.
    by_map: dict[str, int] = collections.Counter(
        location["map"] for location in builder.locations
    )
    for chapter in chapters:
        chapter_maps = chapter["maps"]
        for map_name in chapter_maps:
            ents = entities[map_name]
            label = part_label(chapter_maps, map_name)
            suffix = f" ({label})" if label else ""

            hostiles = [
                e for e in ents
                if e["classname"].startswith("monster_")
                and e["classname"] not in IGNORED_MONSTERS
            ]

            for classname, display in SUPPLY_CLASSNAMES.items():
                if by_map[map_name] >= MIN_LOCATIONS_PER_MAP:
                    break
                if any(e["classname"] == classname for e in ents):
                    builder.add(
                        chapter,
                        map_name,
                        f"{display}{suffix}",
                        {"type": "pickup", "map": map_name, "classnames": [classname]},
                    )
                    by_map[map_name] += 1

            for fraction in KILL_MILESTONE_FRACTIONS:
                if by_map[map_name] >= MIN_LOCATIONS_PER_MAP:
                    break
                threshold = int(len(hostiles) * fraction)
                if threshold < 5:
                    continue
                builder.add(
                    chapter,
                    map_name,
                    f"{threshold} Kills{suffix}",
                    {"type": "kill_count", "map": map_name, "count": threshold},
                )
                by_map[map_name] += 1

    # Chapter completion always comes last so it reads last in the list.
    for chapter in chapters:
        builder.add(
            chapter,
            chapter["maps"][-1],
            "Complete",
            {"type": "chapter_complete", "chapter": chapter["key"],
             "map": chapter["maps"][-1]},
        )

    items = build_items(chapters)

    return {
        "chapters": [
            {
                "key": chapter["key"],
                "name": chapter["name"],
                "maps": chapter["maps"],
                "index": chapter["index"],
                "is_goal": chapter["key"] == GOAL_CHAPTER,
                "gates": CHAPTER_GATES.get(chapter["key"], {}),
            }
            for chapter in chapters
        ],
        "items": items,
        "locations": builder.locations,
        "requirement_groups": REQUIREMENT_GROUPS,
        "starting_weapons": STARTING_WEAPONS,
    }


def build_items(chapters: list[dict]) -> list[dict]:
    items: list[dict] = []

    def add(name: str, classification: str, **extra) -> None:
        items.append({
            "id": ITEM_ID_BASE + len(items),
            "name": name,
            "classification": classification,
            **extra,
        })

    for chapter in chapters:
        if chapter["key"] == GOAL_CHAPTER:
            continue  # opened by mission count, never by an item
        add(
            f"{chapter['name']} Unlock",
            "progression",
            group="chapter",
            chapter=chapter["key"],
        )

    for name, classnames in WEAPON_ITEMS.items():
        add(name, "progression", group="weapon", classnames=classnames)

    for name, classnames in OPTIONAL_ITEMS.items():
        add(name, "progression", group="optional", classnames=classnames)

    for name, classnames, weight in (
        ("Ammo Cache", ["ammo_generic"], 40),
        ("Medkit", ["item_healthkit"], 25),
        ("Armor Battery", ["item_battery"], 25),
        ("Health Charge", ["item_healthkit"], 10),
    ):
        add(name, "filler", group="filler", classnames=classnames, weight=weight)

    return items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--maps",
        type=Path,
        required=True,
        help="path to the svencoop/maps directory",
    )
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args(argv)

    data = build(args.maps)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")

    progression = sum(1 for i in data["items"] if i["classification"] == "progression")
    print(f"wrote {args.out}")
    print(f"  chapters : {len(data['chapters'])}")
    print(f"  items    : {len(data['items'])} ({progression} progression)")
    print(f"  locations: {len(data['locations'])}")
    counts = collections.Counter(l["trigger"]["type"] for l in data["locations"])
    for kind, count in counts.most_common():
        print(f"    {kind:18} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
