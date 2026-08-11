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
import hashlib
import json
from pathlib import Path

from bsp_entities import load_map
from campaign_layout import (
    CHAPTERS,
    CLASSNAME_TO_ITEM,
    ENABLED_LOCATION_TYPES,
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

# Append-only registry of every id ever handed out.
#
# Ids used to be positional, which meant changing which location types are
# generated silently reassigned all of them: an existing seed would resolve a
# check to whatever location now happened to sit at that index. Keys here are
# derived from what a location *is*, not where it lands in the list, and an id is
# never reused for something else.
IDS_PATH = REPO_ROOT / "apworld" / "half_life_sven" / "data" / "ids.json"

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


class IdRegistry:
    """Append-only map of stable key -> id, persisted across regenerations."""

    def __init__(self, path: Path) -> None:
        self.path = path
        if path.exists():
            self.data: dict[str, dict[str, int]] = json.loads(
                path.read_text(encoding="utf-8")
            )
        else:
            self.data = {}
        self.data.setdefault("locations", {})
        self.data.setdefault("items", {})

    def get(self, kind: str, key: str, base: int) -> int:
        table = self.data[kind]
        if key not in table:
            # Next free id, never one that has been retired: an id must not come
            # to mean a different location than it did in an existing seed.
            table[key] = base + len(table)
        return table[key]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=1, sort_keys=True) + "\n",
                             encoding="utf-8")

    def fingerprint(self) -> str:
        """Short digest of the whole id map.

        Written into both the apworld and the plugin's data file so a mismatched
        pair can be detected instead of quietly sending the wrong checks.
        """
        payload = json.dumps(self.data, sort_keys=True).encode("utf-8")
        return hashlib.sha1(payload).hexdigest()[:12]


def location_key(chapter_key: str, map_name: str, trigger: dict) -> str:
    """Identity of a location, independent of its wording or list position."""
    kind = trigger["type"]
    if kind == "pickup":
        arg = ",".join(trigger["classnames"])
    elif kind == "kill":
        arg = trigger["classname"]
    elif kind == "kill_count":
        arg = str(trigger["count"])
    elif kind == "chapter_complete":
        arg = trigger["chapter"]
    else:
        arg = ""
    return f"{chapter_key}|{map_name}|{kind}|{arg}"


class LocationBuilder:
    """Assigns stable ids and guarantees unique, readable location names."""

    def __init__(self, registry: IdRegistry) -> None:
        self.registry = registry
        self.locations: list[dict] = []
        self._used_names: set[str] = set()

    def add(self, chapter: dict, map_name: str, base_name: str, trigger: dict,
            requires: str | None = None) -> dict:
        name = self._unique(f"{chapter['name']} - {base_name}")
        key = location_key(chapter["key"], map_name, trigger)
        location = {
            "id": self.registry.get("locations", key, LOCATION_ID_BASE),
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


def build(maps_dir: Path, registry: IdRegistry) -> dict:
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

    builder = LocationBuilder(registry)

    enabled = ENABLED_LOCATION_TYPES

    for chapter in chapters:
        chapter_maps = chapter["maps"]
        for map_name in chapter_maps:
            ents = entities[map_name]
            label = part_label(chapter_maps, map_name)
            suffix = f" ({label})" if label else ""

            # Getting to a part of the campaign is the check. Every map counts,
            # including a mission's first, since entering it at all requires the
            # mission unlock.
            if "map_reached" in enabled:
                builder.add(
                    chapter,
                    map_name,
                    f"{label} Reached" if label else "Reached",
                    {"type": "map_reached", "map": map_name},
                )

            # Every distinct pickup classname present in the map becomes one
            # check -- collecting any instance of it fires the check once.
            if "pickup" in enabled:
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
            if "kill" in enabled:
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

    # Top up sparse maps so no map is a dead stretch with nothing to find. Only
    # relevant when the entity-derived types are on; with one check per map by
    # definition, no map is sparse.
    if enabled & {"pickup", "kill_count"}:
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

                if "pickup" in enabled:
                    for classname, display in SUPPLY_CLASSNAMES.items():
                        if by_map[map_name] >= MIN_LOCATIONS_PER_MAP:
                            break
                        if any(e["classname"] == classname for e in ents):
                            builder.add(
                                chapter,
                                map_name,
                                f"{display}{suffix}",
                                {"type": "pickup", "map": map_name,
                                 "classnames": [classname]},
                            )
                            by_map[map_name] += 1

                if "kill_count" in enabled:
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
    if "chapter_complete" in enabled:
        for chapter in chapters:
            builder.add(
                chapter,
                chapter["maps"][-1],
                "Complete",
                {"type": "chapter_complete", "chapter": chapter["key"],
                 "map": chapter["maps"][-1]},
            )

    items = build_items(chapters, registry)

    return {
        "data_version": registry.fingerprint(),
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


def build_items(chapters: list[dict], registry: IdRegistry) -> list[dict]:
    items: list[dict] = []

    def add(name: str, classification: str, **extra) -> None:
        # The item's name is already a stable identity.
        items.append({
            "id": registry.get("items", name, ITEM_ID_BASE),
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
    parser.add_argument("--ids", type=Path, default=IDS_PATH)
    args = parser.parse_args(argv)

    registry = IdRegistry(args.ids)
    known = len(registry.data["locations"])

    data = build(args.maps, registry)
    registry.save()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")

    added = len(registry.data["locations"]) - known
    progression = sum(1 for i in data["items"] if i["classification"] == "progression")
    print(f"wrote {args.out}")
    print(f"  data version: {data['data_version']}"
          + (f"  ({added} new location ids)" if added else ""))
    print(f"  chapters : {len(data['chapters'])}")
    print(f"  items    : {len(data['items'])} ({progression} progression)")
    print(f"  locations: {len(data['locations'])}")
    counts = collections.Counter(l["trigger"]["type"] for l in data["locations"])
    for kind, count in counts.most_common():
        print(f"    {kind:18} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
