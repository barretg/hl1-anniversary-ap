"""Extract the entity lump from GoldSrc (BSP v30) maps.

Half-Life's own campaign maps are the authoritative source for what actually
exists in each level: monster classnames, their origins, item pickups, and the
changelevel targets that chain the maps together. Rather than hand-authoring the
Archipelago location table from memory, we read it straight out of the shipped BSPs.

By default the CLI projects each entity down to classname, targetname and origin,
which is all the campaign data needs. Investigating an unfamiliar map usually needs
the rest: `--full` keeps every keyvalue, `--targetname` and `--grep` narrow the dump,
and `--raw` prints the lump verbatim. That is how the lobby map's buttons were read.

Usage:
    python tools/bsp_entities.py <bsp-or-directory> [--classname monster_*] [--json out.json]
    python tools/bsp_entities.py ap_lobby_alpha.bsp --classname func_button --full
    python tools/bsp_entities.py ap_lobby_alpha.bsp --targetname "chapter_*" --full
    python tools/bsp_entities.py ap_lobby_alpha.bsp --raw > entities.txt
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import struct
import sys
from pathlib import Path

LUMP_ENTITIES = 0
LUMP_COUNT = 15
HEADER_FMT = "<i" + "ii" * LUMP_COUNT


def read_entity_lump(bsp_path: Path) -> str:
    """Return the raw entity lump text of a GoldSrc BSP."""
    with bsp_path.open("rb") as handle:
        header = handle.read(struct.calcsize(HEADER_FMT))
        if len(header) < struct.calcsize(HEADER_FMT):
            raise ValueError(f"{bsp_path.name}: file too short to be a BSP")
        fields = struct.unpack(HEADER_FMT, header)
        version = fields[0]
        if version != 30:
            raise ValueError(f"{bsp_path.name}: unsupported BSP version {version}")
        offset = fields[1 + LUMP_ENTITIES * 2]
        length = fields[2 + LUMP_ENTITIES * 2]
        handle.seek(offset)
        raw = handle.read(length)
    return raw.split(b"\x00", 1)[0].decode("latin-1")


def parse_entities(text: str) -> list[dict[str, str]]:
    """Parse the `{ "key" "value" ... }` entity blocks into dicts.

    Keys can legitimately repeat within one entity, but none of the keys we care
    about do, so last-wins is fine here.
    """
    entities: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            current = {}
        elif line.startswith("}"):
            if current is not None:
                entities.append(current)
            current = None
        elif current is not None and line.startswith('"'):
            # "key" "value" -- values may contain spaces but not unescaped quotes.
            parts = line.split('"')
            if len(parts) >= 5:
                current[parts[1]] = parts[3]
    return entities


def load_map(bsp_path: Path) -> list[dict[str, str]]:
    return parse_entities(read_entity_lump(bsp_path))


LUMP_MODELS = 14
MODEL_STRUCT_SIZE = 64


def brush_model_bounds(
    bsp_path: Path,
) -> dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]]:
    """`*N` -> the (mins, maxs) the compiler recorded for that brush model.

    The bounding box rather than its centre, for the cases where the extent is
    the point: a trigger volume a player has to be standing inside, or a button
    whose face has to be told apart from the wall it is set into.
    """
    with bsp_path.open("rb") as handle:
        header = handle.read(struct.calcsize(HEADER_FMT))
        fields = struct.unpack(HEADER_FMT, header)
        if fields[0] != 30:
            raise ValueError(f"{bsp_path.name}: unsupported BSP version {fields[0]}")
        offset = fields[1 + LUMP_MODELS * 2]
        length = fields[2 + LUMP_MODELS * 2]
        handle.seek(offset)
        raw = handle.read(length)

    bounds: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {}
    for index in range(length // MODEL_STRUCT_SIZE):
        base = index * MODEL_STRUCT_SIZE
        mins = struct.unpack_from("<3f", raw, base)
        maxs = struct.unpack_from("<3f", raw, base + 12)
        bounds[f"*{index}"] = (mins, maxs)
    return bounds


def brush_model_centres(bsp_path: Path) -> dict[str, tuple[float, float, float]]:
    """`*N` -> the centre of that brush model's bounding box.

    Brush entities are where a position is otherwise unavailable: a
    `func_healthcharger` has no `origin` key at all, so the only way to say where
    one is in the world is to read the bounding box the compiler recorded for its
    model. Returned keyed the way the entity refers to it, `*79`.
    """
    with bsp_path.open("rb") as handle:
        header = handle.read(struct.calcsize(HEADER_FMT))
        fields = struct.unpack(HEADER_FMT, header)
        if fields[0] != 30:
            raise ValueError(f"{bsp_path.name}: unsupported BSP version {fields[0]}")
        offset = fields[1 + LUMP_MODELS * 2]
        length = fields[2 + LUMP_MODELS * 2]
        handle.seek(offset)
        raw = handle.read(length)

    centres: dict[str, tuple[float, float, float]] = {}
    for index in range(length // MODEL_STRUCT_SIZE):
        base = index * MODEL_STRUCT_SIZE
        mins = struct.unpack_from("<3f", raw, base)
        maxs = struct.unpack_from("<3f", raw, base + 12)
        centres[f"*{index}"] = tuple((mins[i] + maxs[i]) / 2 for i in range(3))
    return centres


LUMP_PLANES = 1
LUMP_CLIPNODES = 9

PLANE_STRUCT_SIZE = 20
CLIPNODE_STRUCT_SIZE = 8

CONTENTS_EMPTY = -1
CONTENTS_SOLID = -2

# Hulls 1 and 2 are the standing and crouching player. Hull 0 is a point, which
# is not what a player is: a point can sit in a gap no body fits through.
HULL_STANDING = 1
HULL_CROUCHING = 3


class ClipHull:
    """Where a player-sized body can and cannot be, read out of a BSP.

    GoldSrc does not trace the world geometry against the player's bounding box
    at runtime. The compiler precomputes one collision tree per player size --
    the clip hulls -- with every surface pushed outward by half the body, so a
    collision test is a point walked down a BSP of planes. That is cheap enough
    to do a few thousand times per charger from Python, and it is the *same*
    answer the engine gives, not an approximation of it.

    Used here to ask the one question the entity lump cannot answer: is there
    anywhere a player could stand and reach this thing.
    """

    def __init__(self, bsp_path: Path) -> None:
        with bsp_path.open("rb") as handle:
            header = handle.read(struct.calcsize(HEADER_FMT))
            fields = struct.unpack(HEADER_FMT, header)
            if fields[0] != 30:
                raise ValueError(
                    f"{bsp_path.name}: unsupported BSP version {fields[0]}"
                )

            def lump(index: int) -> bytes:
                handle.seek(fields[1 + index * 2])
                return handle.read(fields[2 + index * 2])

            planes_raw = lump(LUMP_PLANES)
            clipnodes_raw = lump(LUMP_CLIPNODES)
            models_raw = lump(LUMP_MODELS)

        self.planes: list[tuple[tuple[float, float, float], float]] = []
        for index in range(len(planes_raw) // PLANE_STRUCT_SIZE):
            base = index * PLANE_STRUCT_SIZE
            normal = struct.unpack_from("<3f", planes_raw, base)
            distance = struct.unpack_from("<f", planes_raw, base + 12)[0]
            self.planes.append((normal, distance))

        self.clipnodes: list[tuple[int, int, int]] = []
        for index in range(len(clipnodes_raw) // CLIPNODE_STRUCT_SIZE):
            base = index * CLIPNODE_STRUCT_SIZE
            self.clipnodes.append(struct.unpack_from("<ihh", clipnodes_raw, base))

        # Model 0 is the world. Its four headnodes are the point hull and the
        # three player hulls; a negative child is a contents value rather than
        # another node, which is what ends the walk.
        self.headnodes = struct.unpack_from("<4i", models_raw, 36)

    def contents(
        self, point: tuple[float, float, float], hull: int = HULL_STANDING
    ) -> int:
        node = self.headnodes[hull]
        while node >= 0:
            plane_number, front, back = self.clipnodes[node]
            normal, distance = self.planes[plane_number]
            side = (
                normal[0] * point[0]
                + normal[1] * point[1]
                + normal[2] * point[2]
                - distance
            )
            node = front if side >= 0 else back
        return node


def origin_of(entity: dict[str, str]) -> tuple[float, float, float] | None:
    raw = entity.get("origin")
    if not raw:
        return None
    try:
        x, y, z = (float(part) for part in raw.split()[:3])
    except ValueError:
        return None
    return (x, y, z)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="a .bsp file or a directory of them")
    parser.add_argument(
        "--classname",
        action="append",
        default=[],
        help="glob to filter classnames (repeatable); default: all",
    )
    parser.add_argument(
        "--targetname",
        action="append",
        default=[],
        help="glob to filter targetnames (repeatable); default: all",
    )
    parser.add_argument(
        "--grep",
        action="append",
        default=[],
        help=(
            "keep entities where this substring appears in any key or value, "
            "case-insensitive (repeatable, OR'd)"
        ),
    )
    parser.add_argument("--json", type=Path, help="write results as JSON to this path")
    parser.add_argument(
        "--counts",
        action="store_true",
        help="print per-map classname counts instead of individual entities",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="keep every keyvalue rather than classname/targetname/origin",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="print the entity lump verbatim and exit; ignores every filter",
    )
    args = parser.parse_args(argv)

    if args.target.is_dir():
        bsps = sorted(args.target.glob("*.bsp"))
    else:
        bsps = [args.target]

    if args.raw:
        for bsp in bsps:
            if len(bsps) > 1:
                print(f"\n=== {bsp.stem} ===")
            print(read_entity_lump(bsp))
        return 0

    def globbed(value: str, patterns: list[str]) -> bool:
        if not patterns:
            return True
        return any(fnmatch.fnmatch(value, pattern) for pattern in patterns)

    needles = [needle.lower() for needle in args.grep]

    def grepped(entity: dict[str, str]) -> bool:
        if not needles:
            return True
        blob = " ".join(f"{key} {value}" for key, value in entity.items()).lower()
        return any(needle in blob for needle in needles)

    def keep(entity: dict[str, str]) -> bool:
        return (
            globbed(entity.get("classname", ""), args.classname)
            and globbed(entity.get("targetname", ""), args.targetname)
            and grepped(entity)
        )

    result: dict[str, list[dict[str, object]]] = {}
    for bsp in bsps:
        try:
            entities = load_map(bsp)
        except ValueError as exc:
            print(f"skipping {bsp.name}: {exc}", file=sys.stderr)
            continue
        kept: list[dict[str, object]] = []
        for entity in entities:
            if not keep(entity):
                continue
            if args.full:
                # `origin` stays parsed so --full is a superset of the default shape.
                kept.append({**entity, "origin": origin_of(entity)})
            else:
                kept.append(
                    {
                        "classname": entity.get("classname", ""),
                        "targetname": entity.get("targetname", ""),
                        "origin": origin_of(entity),
                    }
                )
        result[bsp.stem] = kept

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(f"wrote {args.json} ({sum(len(v) for v in result.values())} entities)")
        return 0

    for map_name, entities in result.items():
        if args.counts:
            counts: dict[str, int] = {}
            for entity in entities:
                counts[str(entity["classname"])] = counts.get(str(entity["classname"]), 0) + 1
            print(f"\n=== {map_name} ({len(entities)}) ===")
            for classname, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
                print(f"  {count:4d}  {classname}")
        elif args.full:
            print(f"\n=== {map_name} ({len(entities)}) ===")
            for entity in entities:
                print(f"\n  {entity.get('classname', '')}")
                for key, value in entity.items():
                    if key != "classname":
                        print(f"    {key:28} {value}")
        else:
            print(f"\n=== {map_name} ({len(entities)}) ===")
            for entity in entities:
                print(f"  {entity['classname']:32} {entity['targetname']:24} {entity['origin']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
