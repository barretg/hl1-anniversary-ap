"""The level transitions table for transitions mode.

One record per `trigger_changelevel` entity in every campaign map: where it
is, which way it faces, what kind of crossing it is, and which transition on
the other side is its vanilla partner. The apworld shuffles these and the dll
rewrites the changelevels to match. See `.claude/TRANSITION_RANDO.md`, 3.1
and 3.2.

Kinds are detected heuristically and corrected per chapter by the campaign
modules' `transition_overrides`, which each chapter's audit writes:

  ride      a scripted train ride's changelevel: both maps hold an
            uncontrollable train under the same globalname
  drivable  driven through on a player train: both maps hold a controllable
            train under the same globalname, and its track runs through the
            trigger
  lift      the trigger sits on something that moves vertically
  teleport  a portal sprite beside it, or a teleport manager fires it
  fall      no floor under it: the player arrives airborne
  scripted  use-only, fired by a script rather than walked into
  walk      everything else
"""

from __future__ import annotations

import itertools
import math
from pathlib import Path

from bsp_entities import CONTENTS_SOLID, HULL_CROUCHING, HULL_STANDING, ClipHull, origin_of

Vec = tuple[float, float, float]
Bounds = tuple[Vec, Vec]

KINDS = ("walk", "lift", "ride", "drivable", "fall", "teleport", "scripted")
OVERRIDE_FIELDS = {"kind", "partner", "two_way", "frame", "orb_at", "fixed"}

# `trigger_changelevel` spawnflag: fired by a target only, never by touch.
SF_CHANGELEVEL_USEONLY = 2
# `func_tracktrain` spawnflag: the player cannot drive it.
SF_TRACKTRAIN_NOCONTROL = 2

# A standing player's origin is this far above their feet.
STAND_HEIGHT = 36
DUCK_HEIGHT = 18
# How far under a trigger to look for a floor before calling it a fall.
FLOOR_SEARCH = 256
# A track point this close to the trigger means the train drives through it.
TRACK_NEAR = 96
PORTAL_SPRITES = ("portal", "exit1", "xflare")
PORTAL_NEAR = 200
VERTICAL_MOVERS = ("func_plat", "func_platrot", "func_train")


def bounds_centre(bounds: Bounds) -> Vec:
    mins, maxs = bounds
    return tuple((mins[i] + maxs[i]) / 2 for i in range(3))


def overlaps(a: Bounds, b: Bounds, pad: float = 0.0) -> bool:
    return all(a[0][i] - pad <= b[1][i] and b[0][i] - pad <= a[1][i] for i in range(3))


def fired_names(entity: dict[str, str]) -> set[str]:
    """Every targetname this entity can fire."""
    names = {entity.get("target", ""), entity.get("killtarget", "")}
    classname = entity.get("classname", "")
    if classname == "path_track":
        names.add(entity.get("message", ""))
    if classname == "multi_manager":
        names.update(key.split("#")[0] for key in entity
                     if key not in ("classname", "targetname", "origin", "spawnflags",
                                    "wait"))
    names.discard("")
    return names


def firers(ents: list[dict[str, str]], name: str) -> list[dict[str, str]]:
    return [e for e in ents if name and name in fired_names(e)]


def trains(ents: list[dict[str, str]]) -> dict[str, bool]:
    """`{globalname: controllable}` for this map's named tracktrains."""
    return {
        e["globalname"]: not int(e.get("spawnflags", "0") or 0) & SF_TRACKTRAIN_NOCONTROL
        for e in ents
        if e.get("classname") == "func_tracktrain" and e.get("globalname")
    }


def vertical_mover(entity: dict[str, str]) -> bool:
    classname = entity.get("classname", "")
    if classname in VERTICAL_MOVERS:
        return True
    # A door whose move direction is straight up (-1) or down (-2).
    return classname == "func_door" and entity.get("angle", "") in ("-1", "-2")


# Sideways steps tried, along the crossing axis, when the column through a
# trigger's centre has no room for a body: a slab set into a door frame.
PROBE_STEPS = (0, 8, -8, 16, -16, 24, -24, 32, -32, 48, -48, 64, -64)


def floor_under(
    hull: ClipHull, centre: Vec, bounds: Bounds, axis: str,
) -> tuple[Vec, str]:
    """Where a player stands at a trigger, and what was found there.

    Walks down from the top of the brush with the standing hull to its first
    open point, then on down to the first solid one. A column with no room is
    retried a step to either side along the crossing axis, then crouched.
    Returns the floor point and `floor`, `none` (open all the way down: a
    fall) or `solid` (nowhere a body fits).
    """
    top, bottom = bounds[1][2], bounds[0][2]
    for hull_number, height in ((HULL_STANDING, STAND_HEIGHT), (HULL_CROUCHING, DUCK_HEIGHT)):
        for step in PROBE_STEPS:
            x = centre[0] + (step if axis == "x" else 0)
            y = centre[1] + (step if axis == "y" else 0)
            z = top + height
            while z >= bottom and hull.contents((x, y, z), hull_number) == CONTENTS_SOLID:
                z -= 4
            if z < bottom:
                continue
            limit = bottom - FLOOR_SEARCH
            while z > limit and hull.contents((x, y, z - 1), hull_number) != CONTENTS_SOLID:
                z -= 1
            if z <= limit:
                return (x, y, bottom), "none"
            return (x, y, z - height), "floor"
    return (centre[0], centre[1], bottom), "solid"


def normal_axis(bounds: Bounds) -> str:
    """`x` or `y`, the axis a player crosses this slab on, or `z` for a
    horizontal slab (a floor or ceiling trigger)."""
    mins, maxs = bounds
    ex, ey, ez = (maxs[i] - mins[i] for i in range(3))
    if min(ex, ey) >= 32 and min(ex, ey) > 3 * ez:
        return "z"
    return "x" if ex <= ey else "y"


def build_transitions(
    maps: list[str],
    entities: dict[str, list[dict[str, str]]],
    bounds: dict[str, dict[str, Bounds]],
    bsp_paths: dict[str, Path],
    overrides: dict[str, dict],
) -> list[dict]:
    """Every `trigger_changelevel` in `maps`, in map then entity order."""
    in_campaign = set(maps)
    records: list[dict] = []
    by_map: dict[str, list[dict]] = {}

    for map_name in maps:
        ents = entities[map_name]
        hull = ClipHull(bsp_paths[map_name])
        here_trains = trains(ents)
        landmarks = {
            e["targetname"].lower(): origin_of(e) for e in ents
            if e.get("classname") == "info_landmark" and e.get("targetname")
        }
        n = 0
        for entity in ents:
            if entity.get("classname") != "trigger_changelevel":
                continue
            transition_id = f"{map_name}:{n}"
            n += 1
            to = entity.get("map", "").lower()
            landmark = entity.get("landmark", "").lower()
            targetname = entity.get("targetname", "")
            model = entity.get("model", "")
            own = bounds[map_name][model]
            use_only = bool(int(entity.get("spawnflags", "0") or 0) & SF_CHANGELEVEL_USEONLY)
            fired_by = firers(ents, targetname)
            # A use-only changelevel fired straight from a brush trigger is
            # crossed where that trigger is.
            firing = next((e for e in fired_by
                           if e.get("classname", "").startswith("trigger_")
                           and e.get("model", "") in bounds[map_name]), None)
            frame_bounds = bounds[map_name][firing["model"]] if firing else own
            centre = bounds_centre(frame_bounds)
            axis = normal_axis(frame_bounds)
            stand, found = floor_under(hull, centre, frame_bounds, axis)

            kind = "walk"
            there_trains = trains(entities[to]) if to in in_campaign else {}
            shared = {g: c for g, c in here_trains.items() if g in there_trains}
            track = [origin_of(e) for e in ents if e.get("classname") == "path_track"]
            if any(not c for c in shared.values()):
                kind = "ride"
            elif any(shared.values()) and any(
                    p and overlaps((p, p), frame_bounds, TRACK_NEAR) for p in track):
                kind = "drivable"
            elif any(vertical_mover(e) and e.get("model", "") in bounds[map_name]
                     and overlaps(bounds[map_name][e["model"]], frame_bounds, 8)
                     for e in ents):
                kind = "lift"
            elif any(
                    e.get("classname") == "env_sprite"
                    and any(s in e.get("model", "").lower() for s in PORTAL_SPRITES)
                    and (o := origin_of(e)) and math.dist(o, centre) < PORTAL_NEAR
                    for e in ents) or any(
                    "tele" in e.get("targetname", "").lower() for e in fired_by
                    if e.get("classname") == "multi_manager"):
                kind = "teleport"
            elif fired_by and not firing or use_only and not firing:
                kind = "scripted"
            elif found == "none":
                kind = "fall"

            mins, maxs = frame_bounds
            extent = [maxs[i] - mins[i] for i in range(3)]
            record = {
                "id": transition_id,
                "map": map_name,
                "to": to,
                "landmark": landmark,
                "targetname": targetname,
                "model": model,
                # Where the dll finds this entity again: its own brush's
                # centre, which survives a recompile that renumbers models.
                "at": [int(round(v)) for v in bounds_centre(own)],
                "use_only": use_only,
                "kind": kind,
                "frame": {
                    "origin": [round(v, 1) for v in stand],
                    "yaw": 0.0,
                    "width": round(extent[1] if axis == "x" else extent[0], 1),
                    "height": round(extent[2], 1),
                },
                "partner": "",
                "two_way": False,
                "fixed": False,
                "_axis": axis,
                "_centre": centre,
                "_landmark_at": landmarks.get(landmark),
            }
            if entity.get("changetarget"):
                record["changetarget"] = entity["changetarget"]
            if firing:
                record["fired_by"] = firing["model"]
            flags = (["horizontal"] if axis == "z" else []) + (
                ["no_stand"] if found == "solid" else [])
            if flags:
                record["flags"] = flags
            records.append(record)
            by_map.setdefault(map_name, []).append(record)

    match_partners(records, by_map)
    for record in records:
        set_yaw(record, by_map)

    by_id = {r["id"]: r for r in records}
    for transition_id, fields in overrides.items():
        if transition_id not in by_id:
            raise SystemExit(f"transition override names {transition_id!r}, "
                             "which is no transition")
        unknown = set(fields) - OVERRIDE_FIELDS
        if unknown:
            raise SystemExit(f"{transition_id}: unknown override fields {sorted(unknown)}")
        record = by_id[transition_id]
        for key, value in fields.items():
            if key == "frame":
                record["frame"].update(value)
            else:
                record[key] = value
        record.setdefault("flags", []).append("override")
    for record in records:
        if record["kind"] not in KINDS:
            raise SystemExit(f"{record['id']}: unknown kind {record['kind']!r}")
        partner = record["partner"]
        if partner and by_id.get(partner, {}).get("partner") != record["id"]:
            raise SystemExit(f"{record['id']}: partner {partner} does not pair back")
        for key in ("_axis", "_centre", "_landmark_at"):
            del record[key]
    return records


def match_partners(records: list[dict], by_map: dict[str, list[dict]]) -> None:
    """Pair each transition with the one on the other side of its seam.

    Candidates lead back to this map through the same landmark. Where several
    share it (`c1a4b`'s three doors into `c1a4i`), each side's brushes are
    carried across through the two landmarks and matched to minimise the total
    distance between them. A transition with no counterpart is one-way.
    """
    done: set[tuple[str, str, str]] = set()
    for record in records:
        here, there, landmark = record["map"], record["to"], record["landmark"]
        if (here, there, landmark) in done or there not in by_map:
            continue
        done.add((here, there, landmark))
        done.add((there, here, landmark))
        ours = [r for r in by_map[here] if r["to"] == there and r["landmark"] == landmark]
        theirs = [r for r in by_map[there] if r["to"] == here and r["landmark"] == landmark]
        if not ours or not theirs:
            continue
        a, b = ours[0]["_landmark_at"], theirs[0]["_landmark_at"]
        if a is None or b is None:
            continue
        shift = [b[i] - a[i] for i in range(3)]

        def cost(pairs) -> float:
            return sum(
                math.dist([o["_centre"][i] + shift[i] for i in range(3)], t["_centre"])
                for o, t in pairs)

        if len(ours) <= len(theirs):
            options = (list(zip(ours, perm))
                       for perm in itertools.permutations(theirs, len(ours)))
        else:
            options = (list(zip(perm, theirs))
                       for perm in itertools.permutations(ours, len(theirs)))
        for o, t in min(options, key=cost):
            o["partner"], t["partner"] = t["id"], o["id"]
            o["two_way"] = t["two_way"] = True


def set_yaw(record: dict, by_map: dict[str, list[dict]]) -> None:
    """The outward direction: the way a player faces walking out through it.

    The partner's brush, carried into this map through the landmarks, lies on
    the inside: a player arrives where they crossed it, and this map's own
    trigger must sit beyond that spot, or they would cross it straight back.
    Without a partner, the map's other ways in (its other transitions and
    player starts) are taken to be on the inside. Anything that falls back
    that far is flagged for the audit.
    """
    centre = record["_centre"]
    axis = record["_axis"]
    candidates: list[list[float]] = []
    partner = next((r for r in by_map.get(record["to"], ())
                    if r["id"] == record["partner"]), None)
    if partner and record["_landmark_at"] and partner["_landmark_at"]:
        shift = [record["_landmark_at"][i] - partner["_landmark_at"][i] for i in range(3)]
        carried = [partner["_centre"][i] + shift[i] for i in range(3)]
        candidates.append([centre[0] - carried[0], centre[1] - carried[1]])
    others = [r["_centre"] for r in by_map[record["map"]] if r is not record]
    if others:
        mean = [sum(p[i] for p in others) / len(others) for i in range(2)]
        candidates.append([centre[0] - mean[0], centre[1] - mean[1]])

    def along(v: list[float]) -> list[float]:
        if axis == "x":
            return [v[0], 0.0]
        if axis == "y":
            return [0.0, v[1]]
        return v

    outward = next((along(v) for v in candidates if math.hypot(*along(v)) >= 1), None)
    if outward is None or not candidates or outward != along(candidates[0]) or not partner:
        record.setdefault("flags", []).append("yaw_guess")
    if outward is None:
        outward = along([1.0, 1.0])
    yaw = math.degrees(math.atan2(outward[1], outward[0])) % 360
    record["frame"]["yaw"] = round(yaw, 1)
