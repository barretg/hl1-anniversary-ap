"""Extract the entity lump from GoldSrc (BSP v30) maps.

Sven Co-op's Half-Life campaign maps are the authoritative source for what actually
exists in each level: monster classnames, their origins, item pickups, and the
changelevel targets that chain the maps together. Rather than hand-authoring the
Archipelago location table from memory, we read it straight out of the shipped BSPs.

Usage:
    python tools/bsp_entities.py <bsp-or-directory> [--classname monster_*] [--json out.json]
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
    parser.add_argument("--json", type=Path, help="write results as JSON to this path")
    parser.add_argument(
        "--counts",
        action="store_true",
        help="print per-map classname counts instead of individual entities",
    )
    args = parser.parse_args(argv)

    if args.target.is_dir():
        bsps = sorted(args.target.glob("*.bsp"))
    else:
        bsps = [args.target]

    def matches(classname: str) -> bool:
        if not args.classname:
            return True
        return any(fnmatch.fnmatch(classname, pattern) for pattern in args.classname)

    result: dict[str, list[dict[str, object]]] = {}
    for bsp in bsps:
        try:
            entities = load_map(bsp)
        except ValueError as exc:
            print(f"skipping {bsp.name}: {exc}", file=sys.stderr)
            continue
        kept: list[dict[str, object]] = []
        for entity in entities:
            classname = entity.get("classname", "")
            if not matches(classname):
                continue
            kept.append(
                {
                    "classname": classname,
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
        else:
            print(f"\n=== {map_name} ({len(entities)}) ===")
            for entity in entities:
                print(f"  {entity['classname']:32} {entity['targetname']:24} {entity['origin']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
