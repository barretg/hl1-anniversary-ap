"""Generate `apworld/half_life/data/campaign.json` from the shipped BSPs.

The Half-Life campaign maps are the source of truth for what a location can be:
we only ever create a check for something that provably exists in the map file.
The generated JSON is committed, so neither the apworld nor the client needs the
game installed -- only this tool does.

Usage:
    python tools/build_campaign_data.py --maps "<...>/Half-Life/valve/maps"
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
from collections.abc import Iterable
from pathlib import Path

from bsp_entities import brush_model_centres, load_map
from campaign_layout import (
    CHAPTER_GATES,
    CHAPTERS,
    CHARGER_CLASSNAMES,
    CHARGER_POSITION_GRID,
    CLASSNAME_TO_ITEM,
    ENABLED_LOCATION_TYPES,
    GOAL_CHAPTER,
    IGNORED_MONSTERS,
    INTRO_CHAPTER,
    ITEM_ID_BASE,
    KILL_MILESTONE_FRACTIONS,
    LOCATION_ID_BASE,
    MIN_LOCATIONS_PER_MAP,
    NOTABLE_MONSTERS,
    OPTIONAL_ITEMS,
    REQUIREMENT_GROUPS,
    STARTING_WEAPONS,
    UNRANDOMISED_WEAPON_LOCATIONS,
    WEAPON_ITEMS,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "apworld" / "half_life" / "data" / "campaign.json"

# Append-only registry of every id ever handed out.
#
# Ids used to be positional, which meant changing which location types are
# generated silently reassigned all of them: an existing seed would resolve a
# check to whatever location now happened to sit at that index. Keys here are
# derived from what a location *is*, not where it lands in the list, and an id is
# never reused for something else.
IDS_PATH = REPO_ROOT / "apworld" / "half_life" / "data" / "ids.json"

SUPPLY_CLASSNAMES = {
    "item_battery": "Battery",
    "item_healthkit": "Health Kit",
}


def part_label(chapter_maps: list[str], map_name: str) -> str:
    """`Part 3` for multi-map chapters, empty for single-map ones."""
    if len(chapter_maps) == 1:
        return ""
    return f"Part {chapter_maps.index(map_name) + 1}"


def spawn_point(ents: list[dict[str, str]]) -> tuple[float, float, float] | None:
    """Where players arrive, for numbering things in the order they meet them."""
    for classname in ("info_player_start", "info_player_deathmatch"):
        for entity in ents:
            if entity.get("classname", "") == classname and entity.get("origin"):
                return entity_origin(entity["origin"])
    return None


# How much dearer a unit of height is than a unit of floor, for judging how far
# away something really is. The same weighting `ap_find` uses in game: 800 units
# across a floor is a walk, 800 units up is a hunt for the stairs.
VERTICAL_PENALTY = 3.0


def walk_score(
    origin: tuple[float, float, float], target: tuple[float, float, float]
) -> float:
    dx = target[0] - origin[0]
    dy = target[1] - origin[1]
    dz = target[2] - origin[2]
    return math.hypot(dx, dy) + VERTICAL_PENALTY * abs(dz)


def entity_origin(raw: str) -> tuple[float, float, float]:
    parts = raw.split()
    if len(parts) != 3:
        return (0.0, 0.0, 0.0)
    try:
        return (float(parts[0]), float(parts[1]), float(parts[2]))
    except ValueError:
        return (0.0, 0.0, 0.0)


def charger_key_position(
    position: tuple[float, float, float]
) -> tuple[int, int, int]:
    """A charger's position as its identity: snapped to a coarse grid.

    Identity is position rather than brush model index because the anniversary
    update recompiled single-player maps and a recompile can renumber brush
    models, which would silently repoint every charger id in that map. The grid
    absorbs the difference between the float the compiler wrote and the float the
    running game computes from the entity's absolute bounding box, while staying
    far finer than the distance between two real chargers.
    """
    grid = CHARGER_POSITION_GRID
    return tuple(int(round(value / grid)) * grid for value in position)


def format_position(position: tuple[int, int, int] | tuple[float, float, float]) -> str:
    return " ".join(str(int(round(value))) for value in position)


def brush_model_index(entity: dict[str, str]) -> int:
    """Numeric part of a brush entity's `*N` model, for a deterministic order."""
    model = entity.get("model", "")
    return int(model[1:]) if model[1:].isdigit() else -1


def charger_position(
    entity: dict[str, str], centres: dict[str, tuple[float, float, float]]
) -> tuple[float, float, float] | None:
    """Where a charger actually is: its brush centre plus the entity's `origin`.

    A brush entity has no origin of its own unless the mapper gave it one, so the
    centre of the model the compiler emitted is the position, and the `origin`
    key -- where present -- is the offset the engine will apply on top of it.
    """
    centre = centres.get(entity.get("model", ""))
    if centre is None:
        return None
    offset = entity_origin(entity.get("origin", ""))
    return tuple(centre[i] + offset[i] for i in range(3))


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

    def fingerprint(self, live: Iterable[str] = ()) -> str:
        """Short digest of the id map *and* of what this build actually ships.

        Written into both the apworld and the game's data file so a mismatched
        pair can be detected instead of quietly sending the wrong checks.

        The registry alone is not enough, because it is append-only: *removing* a
        location leaves it untouched, so the two halves would agree on the
        version while disagreeing on the location set. That is the worse
        direction of the mismatch, since an apworld holding a check the game will
        never send is a seed nobody can finish, and it is exactly what a pass
        over the `map_reached` set would produce.
        """
        payload = json.dumps(
            {"registry": self.data, "live": sorted(live)}, sort_keys=True
        ).encode("utf-8")
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
    elif kind == "charger":
        arg = f"{trigger['classname']}@{trigger['at']}"
    elif kind == "weapon_pickup":
        # A campaign-wide location: its identity is the weapon, not where the
        # earliest copy happens to sit. Anchoring the key to the map would
        # renumber it if a nearer pickup were ever found.
        return f"*|*|{kind}|{','.join(sorted(trigger['classnames']))}"
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
            requires: str | None = None, prefixed: bool = True,
            position: tuple[float, float, float] | None = None) -> dict:
        # Campaign-wide locations skip the mission prefix: the mission is only
        # where logic hangs them, not where the player will find the thing.
        name = self._unique(f"{chapter['name']} - {base_name}" if prefixed else base_name)
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
        # Where it is in the world, for `ap_find`. Whole units: the command is a
        # compass, and nobody needs a check located to the nearest thousandth.
        if position is not None:
            location["position"] = [int(round(value)) for value in position]
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


def changelevel_targets(entities: list[dict[str, str]]) -> set[str]:
    """Every map this one can hand the player to, from its `trigger_changelevel`s."""
    return {
        entity["map"]
        for entity in entities
        if entity.get("classname", "") == "trigger_changelevel" and entity.get("map")
    }


def has_forward_exit(
    chapter: dict, chapters: list[dict],
    entities: dict[str, list[dict[str, str]]],
) -> bool:
    """Can this mission be left by walking on into a later one?

    Every mission but the last can: that transition is the moment it is over, and
    the game intercepts it. The last one cannot, which is why it needs a
    different rule -- see `complete_on_arrival` below.

    "Later" matters. Half-Life's transitions are two-way, so a player can walk
    back through the door they came in and land in the previous mission. That is
    leaving the mission too, but it is not finishing it.
    """
    index_of = {
        map_name: c["index"] for c in chapters for map_name in c["maps"]
    }
    own = set(chapter["maps"])

    for map_name in chapter["maps"]:
        for target in changelevel_targets(entities[map_name]):
            if target in own:
                continue
            if index_of.get(target, -1) > chapter["index"]:
                return True
    return False


def earliest_map_with(
    chapters: list[dict], entities: dict[str, list[dict[str, str]]],
    classnames: list[str],
) -> tuple[dict, str] | None:
    """First `(chapter, map)` in campaign order that contains one of these."""
    wanted = set(classnames)
    for chapter in chapters:
        for map_name in chapter["maps"]:
            if any(e.get("classname", "") in wanted for e in entities[map_name]):
                return chapter, map_name
    return None


def build(maps_dir: Path, registry: IdRegistry) -> dict:
    # `index` is what `ap_warp <n>` takes in game.
    chapters = [
        {"key": key, "name": name, "maps": maps, "index": index}
        for index, (key, name, maps) in enumerate(CHAPTERS)
    ]

    entities: dict[str, list[dict[str, str]]] = {}
    # `*N` -> bounding box centre, per map. The only way to place a brush entity,
    # which is what every charger is.
    centres: dict[str, dict[str, tuple[float, float, float]]] = {}
    for chapter in chapters:
        for map_name in chapter["maps"]:
            bsp = maps_dir / f"{map_name}.bsp"
            if not bsp.exists():
                raise SystemExit(f"missing map: {bsp}")
            entities[map_name] = load_map(bsp)
            centres[map_name] = brush_model_centres(bsp)

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

            # Every health and HEV charger placed in the map is its own check,
            # identified by where it stands. See `charger_key_position`.
            if "charger" in enabled:
                spawn = spawn_point(ents)
                for classname, display in CHARGER_CLASSNAMES.items():
                    found = []
                    for entity in ents:
                        if entity.get("classname", "") != classname:
                            continue
                        at = charger_position(entity, centres[map_name])
                        if at is None:
                            # No brush model, so nothing in the running game can
                            # ever be matched to it. Silently skipping would hide
                            # a check that simply never fires.
                            raise SystemExit(
                                f"{map_name}: {classname} with no brush model"
                            )
                        found.append((entity, at))

                    # Numbered by how far they are from where players arrive,
                    # not by compile order, which means nothing in play: Office
                    # Complex's two nearest units came out 5 and 6 because that
                    # is when the compiler happened to emit them, which reads as
                    # a mistake.
                    #
                    # Only the display name depends on this. Ids key on the
                    # position, so renumbering moves nothing.
                    def charger_score(item: tuple[dict[str, str], tuple]) -> tuple:
                        entity, at = item
                        if spawn is None:
                            return (float(brush_model_index(entity)), at)
                        return (walk_score(spawn, at), at)

                    chargers = sorted(found, key=charger_score)
                    keys: set[tuple[int, int, int]] = set()
                    for number, (entity, at) in enumerate(chargers, start=1):
                        rounded = charger_key_position(at)
                        if rounded in keys:
                            # Two units rounding together would share one id and
                            # one of them could never be checked.
                            raise SystemExit(
                                f"{map_name}: two {classname} units share the "
                                f"rounded position {format_position(rounded)}"
                            )
                        keys.add(rounded)

                        count = f" {number}" if len(chargers) > 1 else ""
                        builder.add(
                            chapter,
                            map_name,
                            f"{display}{count}{suffix}",
                            {
                                "type": "charger",
                                "map": map_name,
                                "classname": classname,
                                # What the game matches a pressed entity against.
                                "at": format_position(rounded),
                            },
                            position=at,
                        )

            # Every distinct pickup classname present in the map becomes one
            # check -- collecting any instance of it fires the check once.
            if "pickup" in enabled:
                pickups = sorted({
                    e.get("classname", "") for e in ents
                    if e.get("classname", "").startswith("weapon_")
                    or e.get("classname", "") in ("item_suit", "item_longjump")
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
                    e.get("classname", "") for e in ents
                    if e.get("classname", "") in NOTABLE_MONSTERS
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
                    if e.get("classname", "").startswith("monster_")
                    and e.get("classname", "") not in IGNORED_MONSTERS
                ]

                if "pickup" in enabled:
                    for classname, display in SUPPLY_CLASSNAMES.items():
                        if by_map[map_name] >= MIN_LOCATIONS_PER_MAP:
                            break
                        if any(e.get("classname", "") == classname for e in ents):
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

    # One check per weapon, at the place Half-Life would first have handed it to
    # you: the earliest map in campaign order that contains one. Deliberately not
    # "anywhere": finding a shotgun six missions later is not the moment the
    # check is about, and the per-map `pickup` type that fired on every copy is
    # what read as noise. The crowbar is here too even though you start with one.
    if "weapon_pickup" in enabled:
        for item_name, classnames in {
            **WEAPON_ITEMS, **OPTIONAL_ITEMS, **UNRANDOMISED_WEAPON_LOCATIONS
        }.items():
            anchor = earliest_map_with(chapters, entities, classnames)
            if anchor is None:
                continue  # not in the campaign; the check could never fire
            chapter, map_name = anchor
            # Where the earliest copy sits. There may be several in the map; the
            # first is as good as any, and `ap_find` says "one of them".
            wanted = set(classnames)
            placed = next(
                (e for e in entities[map_name] if e.get("classname", "") in wanted),
                None,
            )
            position = entity_origin(placed.get("origin", "")) if placed else None

            builder.add(
                chapter,
                map_name,
                f"First {item_name}",
                {"type": "weapon_pickup", "map": map_name,
                 "classnames": list(classnames)},
                prefixed=False,
                position=position,
            )

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

    # Every id must exist before the fingerprint is taken, and item ids are
    # assigned here. Built into a local first for that reason alone: with the
    # call left inline in the dict below, Python evaluates the values in order,
    # `data_version` came out of a registry that had locations but no items yet,
    # and the version therefore changed on the second run of an unchanged
    # generator -- a mismatch that pauses checks in game and reads as data
    # corruption rather than as a bug in this file.
    items = build_items(chapters, registry)

    # What this build actually ships, so that dropping a location moves the
    # version even though the append-only registry keeps its id forever.
    live = (
        [f"L{location['id']}" for location in builder.locations]
        + [f"I{item['id']}" for item in items]
    )

    return {
        "data_version": registry.fingerprint(live),
        "goal_chapter": GOAL_CHAPTER,
        # The scene-setting mission `exclude_intro_missions` drops.
        "intro_chapter": INTRO_CHAPTER,
        "chapters": [
            {
                "key": chapter["key"],
                "name": chapter["name"],
                "maps": chapter["maps"],
                "index": chapter["index"],
                "is_goal": chapter["key"] == GOAL_CHAPTER,
                "gates": CHAPTER_GATES.get(chapter["key"], {}),
                # How the game knows this mission is over.
                #
                # Normally: the player walks on into the next mission, and that
                # transition is intercepted. Arriving on the mission's last map
                # is *not* the same thing -- `c1a1d` is the last map of
                # Unforeseen Consequences only because it is the furthest from
                # the start, and it is a dead-end side room that the player
                # visits and walks back out of.
                #
                # The exception is the mission with nowhere further to go, which
                # is the finale: nothing changelevels out of `c5a1`, so arriving
                # there is the only signal there is, and it is the right one.
                "complete_on_arrival": not has_forward_exit(
                    chapter, chapters, entities
                ),
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

    # Traps replace a share of the filler, set by `trap_percentage`. Each is a
    # nuisance rather than a punishment: nothing here can cost a run.
    for name, weight in (
        ("Scientist Trap", 34),
        ("Headcrab Trap", 33),
        ("Butterfingers Trap", 33),
    ):
        add(name, "trap", group="trap", weight=weight)

    return items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--maps",
        type=Path,
        required=True,
        help="path to the Half-Life valve/maps directory",
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
