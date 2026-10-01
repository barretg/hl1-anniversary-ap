"""Opposing Force: Shephard's campaign, `gearbox/maps`.

Chapters come from the retail BSPs the same way Half-Life's do: a map carrying
`chaptertitle` starts one, named from `gearbox/titles.txt`, and map order is the
forward walk of the changelevel graph. Where that rule is wrong the table says
so below.
"""

from __future__ import annotations

from .base import Campaign

# Three departures from the pure title rule:
#
# - `of0a0` (the Osprey ride in) carries no `chaptertitle`; its name is the one
#   `OF1A1TITLE` gives, "Incoming".
# - `of1a1` carries `OF1A3TITLE`, so the game's own first chapter title lands on
#   its first playable map. The title and the map agree; only the key differs.
# - `of3a1b` carries `C4A1TITLE` ("Xen"): the displacer side trip out of
#   `of3a1`, reached by a use-only changelevel and returning to it. Folded into
#   We Are Not Alone rather than made a one-map mission.
#
# `of4a5` is reached from `of4a4` by a use-only changelevel (the displacer trip)
# and is part of Pit Worm's Nest for the same reason. `of7a0` is the ending,
# folded into the finale like Half-Life's `c5a1`.
#
# The two quoted titles ("WE ARE PULLING OUT", "THE PACKAGE") lose their quotes:
# the names end up in item names, which players type.
CHAPTERS: list[tuple[str, str, list[str]]] = [
    ("of0a0", "Incoming", ["of0a0"]),
    ("of1a1", "Welcome To Black Mesa",
     ["of1a1", "of1a2", "of1a3", "of1a4", "of1a4b"]),
    ("of1a5", "We Are Pulling Out", ["of1a5", "of1a5b", "of1a6"]),
    ("of2a1", "Missing In Action", ["of2a1", "of2a1b", "of2a2", "of2a3"]),
    ("of2a4", "Friendly Fire", ["of2a4", "of2a5", "of2a6"]),
    ("of3a1", "We Are Not Alone", ["of3a1", "of3a1b", "of3a2"]),
    ("of3a4", "Crush Depth", ["of3a4", "of3a5", "of3a6"]),
    ("of4a1", "Vicarious Reality", ["of4a1", "of4a2", "of4a3"]),
    ("of4a4", "Pit Worm's Nest", ["of4a4", "of4a5"]),
    ("of5a1", "Foxtrot Uniform", ["of5a1", "of5a2", "of5a3", "of5a4"]),
    ("of6a1", "The Package", ["of6a1", "of6a2", "of6a3", "of6a4"]),
    ("of6a4b", "Worlds Collide", ["of6a4b", "of6a5", "of7a0"]),
]

# Ported from the Sven world's gates, re-keyed to retail chapters. The first
# three are ungated so a seed that drops the intro still has a mission a melee
# weapon can enter.
_RANGED = {"strict": ["ranged"]}
_HEAVY = {"strict": ["heavy"], "always": ["barnacle_grapple"]}
# Vicarious Reality Part 2 can be reached without the grapple but not finished:
# arriving there is in logic, everything else in it and on from Part 3 (where
# the grapple lies) needs it at any logic difficulty (confirmed in play). Its
# First Barnacle check is behind the item too.
_GRAPPLE = {"always": ["barnacle_grapple"]}
MAP_CHECK_GATES: dict[str, dict[str, list[str]]] = {"of4a2": _GRAPPLE}
MAP_GATES: dict[str, dict[str, list[str]]] = {"of4a3": _GRAPPLE}

CHAPTER_GATES: dict[str, dict[str, list[str]]] = {
    "of2a1": _RANGED,
    "of2a4": _RANGED,
    "of3a1": _RANGED,
    "of3a4": _RANGED,
    "of4a1": _RANGED,
    "of4a4": _HEAVY,
    "of5a1": _HEAVY,
    "of6a1": _HEAVY,
    "of6a4b": _HEAVY,
}

WEAPON_ITEMS: dict[str, list[str]] = {
    "Desert Eagle": ["weapon_eagle"],
    "M249": ["weapon_m249"],
    "Sniper Rifle": ["weapon_sniperrifle"],
    "Displacer Cannon": ["weapon_displacer"],
    "Spore Launcher": ["weapon_sporelauncher"],
    "Barnacle Grapple": ["weapon_grapple"],
    "Shock Roach": ["weapon_shockrifle"],
}

# Additions to the shared logic groups, applied only when this campaign is in
# the build so a Half-Life-only seed's groups are unchanged.
_RANGED_WEAPONS = ["Desert Eagle", "M249", "Sniper Rifle", "Shock Roach",
                   "Spore Launcher", "Displacer Cannon"]
REQUIREMENT_GROUPS: dict[str, list[str]] = {
    "ranged": _RANGED_WEAPONS,
    "barrel_shooter": _RANGED_WEAPONS,
    # The Desert Eagle is a pistol: ranged, not heavy.
    "heavy": ["M249", "Sniper Rifle"],
    "explosives": ["Spore Launcher"],
    "underwater": ["Desert Eagle"],
    "barnacle_grapple": ["Barnacle Grapple"],
    "displacer": ["Displacer Cannon"],
}

# Shephard's melee weapons: a `First` check each, and starting-melee candidates
# (see `MELEE_ITEMS`). Whichever does not start the run is an item.
UNRANDOMISED_WEAPON_LOCATIONS: dict[str, list[str]] = {
    "Pipe Wrench": ["weapon_pipewrench"],
    "Combat Knife": ["weapon_knife"],
}

# The PCV is `item_suit` in `of1a1`: Shephard's armour, gating armour on OF maps
# the way the HEV Suit does on Half-Life's.
OPTIONAL_ITEMS: dict[str, list[str]] = {
    "PCV": ["item_suit"],
    # Opposing Force's flashlight: impulse 100 on its maps. No pickup.
    "Night Vision Goggles": [],
}

# Copies that do not count toward their weapon's check, from play in Sven Co-op
# (hl1-sven-ap, 2026-09-30), whose maps are retail's: each is the same entity at
# the same position here. To confirm in retail with the scenario harness.
UNREACHABLE_COPIES: dict[str, list[str]] = {
    # Both in the room behind the skylight, reachable only by stacking players.
    "Tripmine": ["of2a4"],
    "Shotgun": ["of2a4", "of0a0"],
    # Out of bounds; We Are Pulling Out's source moves on to its next map.
    # Also the Osprey ride in, whose marines nobody can reach.
    "Glock": [
        "of1a5", "of0a0",
        "of1a1@688 -1047 0",  # shut in with the G-Man
    ],
    "MP5": ["of0a0"],
    "Desert Eagle": [
        "of0a0",
        "of1a5@1560 -3424 1339",  # a preview of the next map, past the changelevel
        "of1a5b@112 -2096 1344",  # drops nothing
        "of5a3@-712 -960 80",  # holds the blowtorch, not a gun
        "of6a3@1408 2508 -160",  # unarmed
    ],
    # Props: the only real displacer is the one handed over going into Xen
    # for the first time, of3a2's maker.
    "Displacer Cannon": ["of3a5", "of4a5"],
    # The one shock trooper here waits for a script rather than a fight (see
    # `WEAPON_ANCHORS`).
    "Shock Roach": [
        "of1a5b",
        "of6a2@-354 -1200 90",  # this maker never spawned one
    ],
}

# Copies confirmed reachable in play that the flood fill could not prove.
CONFIRMED_COPIES: dict[str, list[str]] = {
    # Only ever in one place.
    "Barnacle Grapple": ["of4a3"],
    # Handed over going into Xen for the first time.
    "Displacer Cannon": ["of3a2"],
    # The rest from the scenario harness, 2026-09-30. of3a2's shotgun and
    # of6a2's grenades with the Displacer, as gated.
    "Glock": ["of5a3@-632 -944 80", "of6a4@672 2044 32", "of6a4b@-1976 -1064 -488"],
    "MP5": [
        "of1a5b@-1408 -2992 2204", "of2a5@320 -1408 1176", "of5a1@-3419 1024 16",
        "of6a1@1328 960 128", "of6a4b@-2067 2560 -576",
    ],
    "Shotgun": ["of3a2", "of5a1@-928 40 112"],
    "RPG": ["of6a3"],
    "Satchel Charge": ["of1a6"],
    "Snarks": ["of4a2"],
    "Hand Grenade": ["of1a6", "of6a2"],
    "Desert Eagle": [
        "of1a2", "of1a1@-1328 -136 -128", "of2a3@-976 1104 2", "of2a6",
        "of3a4@-944 8 112",
    ],
    "M249": ["of1a6@-272 112 -144", "of2a6@-352 432 -440"],
    "Spore Launcher": ["of4a2"],
    "Shock Roach": ["of4a1", "of3a6@-2154 1238 -288", "of6a2@-370 -1440 90",
                    # Boxed troopers, judged where their script lands them.
                    "of5a2@1864 1400 192", "of6a4b@-3216 560 -624"],
}

# Copies past a displacer teleport, from the same play.
_DISPLACER = {"always": ["displacer"]}
WEAPON_SOURCE_GATES: dict[str, dict[str, dict[str, list[str]]]] = {
    "of3a2": {"Shotgun": _DISPLACER},
    "of6a2": {"Hand Grenade": _DISPLACER},
}

# Checks only the displacer's self-teleport reaches. The pools are its Xen
# room, a prefab compiled into each map near its `info_displacer_xen_target`:
# a flood fill from the player start cannot see a teleport, so they once read
# as sealed. Confirmed reachable in Sven Co-op, whose maps are these.
LOCATION_GATES: dict[str, dict[str, dict[str, list[str]]]] = {
    "of3a2": {"func_healthcharger:*78": _DISPLACER},
    "of3a4": {"trigger_hurt:*247": _DISPLACER},
    "of4a1": {"trigger_hurt:*10": _DISPLACER},
    "of5a1": {"trigger_hurt:*160": _DISPLACER},
    "of5a2": {"trigger_hurt:*101": _DISPLACER},
    "of6a1": {"trigger_hurt:*45": _DISPLACER},
    "of6a4": {"trigger_hurt:*78": _DISPLACER},
    "of6a4b": {"trigger_hurt:*115": _DISPLACER},
}

# The Shock Roach is never placed; it is dropped by a dying shock trooper. The
# first map placing one, `of1a5b`, has a single trooper that waits for a script
# (spawnflags 128) rather than a fight, so the anchor is the first real one, in
# Vicarious Reality. To confirm in play.
WEAPON_ANCHORS: dict[str, str] = {
    "Shock Roach": "of4a1",
}

# Chargers no player can reach, as `{map: {(classname, key position)}}`.
UNREACHABLE_CHARGERS: dict[str, set[tuple[str, tuple[int, int, int]]]] = {
    # We Are Not Alone part 2: a healing pool there is no way into.
    "of3a1b": {("trigger_hurt", (-632, -548, -124))},
}


OPPOSING_FORCE = Campaign(
    key="opposing_force",
    name="Opposing Force",
    game_dir="gearbox",
    detect="gearbox/maps/of1a1.bsp",
    chapters=CHAPTERS,
    goal_chapter="of6a4b",
    intro_chapter="of0a0",
    gates=CHAPTER_GATES,
    map_gates=MAP_GATES,
    map_check_gates=MAP_CHECK_GATES,
    weapons=WEAPON_ITEMS,
    groups=REQUIREMENT_GROUPS,
    optional_items=OPTIONAL_ITEMS,
    unrandomised_weapons=UNRANDOMISED_WEAPON_LOCATIONS,
    melee=["weapon_knife", "weapon_pipewrench"],
    weapon_anchors=WEAPON_ANCHORS,
    unreachable_copies=UNREACHABLE_COPIES,
    confirmed_copies=CONFIRMED_COPIES,
    unreachable=UNREACHABLE_CHARGERS,
    weapon_source_gates=WEAPON_SOURCE_GATES,
    location_gates=LOCATION_GATES,
    # Boot camp: the training course, left out like Half-Life's hazard course.
    excluded_maps=frozenset({"ofboot0", "ofboot1", "ofboot2", "ofboot3", "ofboot4"}),
    hub_button_prefix="of_",
    armour_item="PCV",
    short="of",
)
