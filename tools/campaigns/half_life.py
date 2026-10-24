"""Half-Life: the campaign this world was built for.

Target: retail Half-Life on Steam, the 25th anniversary build, `valve/maps`.
Moved here verbatim from `campaign_layout.py` when the tooling learned about
more than one game; the constants keep their names because other code and the
tests import them.
"""

from __future__ import annotations

from .base import Campaign

# --- Chapters -------------------------------------------------------------
#
# Retail Half-Life is one continuous game rather than a set of missions, so the
# mission boundaries here are the game's own chapter boundaries: a map that
# carries a `chaptertitle` key on its `worldspawn` starts a chapter, and every
# map after it belongs to that chapter until the next one does. The names are
# the strings those keys resolve to in `valve/titles.txt`, so a mission is called
# what the game calls it when you arrive.
#
# Map order inside a chapter is the forward walk of the `trigger_changelevel`
# graph, with side branches placed after the map they hang off. It decides
# nothing but the `Part N` labels and the order the regions chain in, since every
# map of a mission sits behind the same unlock.
#
# Chapter keys are the first map of the chapter. Permanent: `data/ids.json` keys
# every location by chapter, so renaming a key renumbers a location. Names are
# free to change; keys are not.
#
# Two editorial calls:
#
# - `c5a1` (Endgame) is folded into Nihilanth rather than being a mission of its
#   own. It is the G-Man's speech with the player's weapons stripped, and
#   arriving on it is exactly the moment Nihilanth dies -- which is also what
#   makes the goal mission complete on `map_reached` like any other.
# - The hazard course (`t0a0*`) is left out entirely. It is a training course
#   rather than part of the campaign, nothing changelevels into it, and Valve's
#   own chapter list does not contain it. Its 7 maps and their chargers are
#   simply not in this world.

CHAPTERS: list[tuple[str, str, list[str]]] = [
    ("c0a0", "Black Mesa Inbound",
     ["c0a0", "c0a0a", "c0a0b", "c0a0c", "c0a0d", "c0a0e"]),
    ("c1a0", "Anomalous Materials",
     ["c1a0", "c1a0d", "c1a0a", "c1a0b", "c1a0e"]),
    ("c1a0c", "Unforeseen Consequences",
     ["c1a0c", "c1a1", "c1a1a", "c1a1f", "c1a1b", "c1a1c", "c1a1d"]),
    ("c1a2", "Office Complex",
     ["c1a2", "c1a2a", "c1a2b", "c1a2c", "c1a2d"]),
    ("c1a3", "We've Got Hostiles",
     ["c1a3", "c1a3d", "c1a3a", "c1a3b", "c1a3c"]),
    ("c1a4", "Blast Pit",
     ["c1a4", "c1a4k", "c1a4b", "c1a4d", "c1a4e", "c1a4f", "c1a4i", "c1a4g",
      "c1a4j"]),
    ("c2a1", "Power Up", ["c2a1", "c2a1b", "c2a1a"]),
    ("c2a2", "On A Rail",
     ["c2a2", "c2a2a", "c2a2b1", "c2a2b2", "c2a2c", "c2a2d", "c2a2e", "c2a2f",
      "c2a2g", "c2a2h"]),
    ("c2a3", "Apprehension",
     ["c2a3", "c2a3a", "c2a3b", "c2a3c", "c2a3d", "c2a3e"]),
    ("c2a4", "Residue Processing", ["c2a4", "c2a4a", "c2a4b", "c2a4c"]),
    ("c2a4d", "Questionable Ethics", ["c2a4d", "c2a4e", "c2a4f", "c2a4g"]),
    ("c2a5", "Surface Tension",
     ["c2a5", "c2a5w", "c2a5x", "c2a5a", "c2a5b", "c2a5c", "c2a5d", "c2a5e",
      "c2a5f", "c2a5g"]),
    ("c3a1", "Forget About Freeman", ["c3a1", "c3a1a", "c3a1b"]),
    ("c3a2e", "Lambda Core",
     ["c3a2e", "c3a2", "c3a2a", "c3a2b", "c3a2c", "c3a2f", "c3a2d"]),
    ("c4a1", "Xen", ["c4a1"]),
    ("c4a2", "Gonarch's Lair", ["c4a2", "c4a2a", "c4a2b"]),
    ("c4a1a", "Interloper",
     ["c4a1a", "c4a1b", "c4a1c", "c4a1d", "c4a1e", "c4a1f"]),
    ("c4a3", "Nihilanth", ["c4a3", "c5a1"]),
]

CHAPTER_KEYS: list[str] = [key for key, _, _ in CHAPTERS]

CHAPTER_NAMES: dict[str, str] = {key: name for key, name, _ in CHAPTERS}

# The finale. Never unlocked by an item: it opens once `missions_required` other
# missions are done, and finishing it wins the seed.
GOAL_CHAPTER = "c4a3"

# The tram ride in: no weapons, no enemies, minutes of riding and listening.
# Dropped by `exclude_intro_missions`.
INTRO_CHAPTER = "c0a0"

# --- Chapter gates --------------------------------------------------------
#
# Mission entry requirements, as `{chapter key: {"strict": [group, ...]}}`.
# `always` gates apply at every difficulty and name equipment rather than a
# weapon tier.

# Three tiers, and the step between them is where the game stops being about
# headcrabs.
#
# `ranged` is a deliberately low bar and has to be read as one: the Hivehand and
# the Snarks are both in it, so a seed can satisfy it with two weapons that
# cannot kill an armoured target between them. That is fine early and wrong for
# everything past the middle of the game, which is what playing Questionable
# Ethics on a Hivehand proved. From Power Up onward the bar is a *heavy* weapon
# and an explosive: a gate naming two groups requires one item from each.
# Each group is checked on its own, so the RPG alone would satisfy both;
# `not_rpg` on those gates asks for a second weapon alongside it.
#
# Blast Pit sits between the two. Its explosive is about the tentacle rather than
# about the difficulty tier, so it asks for one without yet asking for a heavy
# weapon.
#
# Xen keeps its own gate, which is stricter again and names its weapons by hand.
CHAPTER_GATES: dict[str, dict[str, list[str]]] = {
    # From here on you are fighting armed marines, not headcrabs.
    "c1a3": {"strict": ["ranged"]},
    # The tentacle in the silo is the level, and a seed that dropped the player
    # in with a pistol had them working around it rather than through it. Still
    # only `ranged`: the tentacle wants something thrown at it, not a firefight.
    "c1a4": {"strict": ["ranged", "explosives"]},
    "c2a1": {"strict": ["heavy", "explosives", "not_rpg"]},
    "c2a2": {"strict": ["heavy", "explosives", "not_rpg"]},
    "c2a3": {"strict": ["heavy", "explosives", "not_rpg"]},
    "c2a4": {"strict": ["heavy", "explosives", "not_rpg"]},
    # The lab is full of alien grunts, which are armoured and shrug off hornets,
    # and its corridors are strung with tripmines that want detonating from a
    # distance rather than by throwing squeakers at them.
    "c2a4d": {"strict": ["heavy", "explosives", "not_rpg"]},
    "c2a5": {"strict": ["heavy", "explosives", "not_rpg"]},
    "c3a1": {"strict": ["heavy", "explosives", "not_rpg"]},
    "c3a2e": {"strict": ["heavy", "explosives", "not_rpg"]},
    # Xen onward: the long jump module is standard equipment from here, and the
    # suit is what powers it. Strict logic names the two weapons by hand rather
    # than a tier -- the alien grunt and Gonarch fights are not something to walk
    # into with a shotgun -- so both the Tau cannon and the RPG are required.
    "c4a1": {"strict": ["tau_cannon", "rpg"], "always": ["longjump", "suit"]},
    "c4a2": {"strict": ["tau_cannon", "rpg"], "always": ["longjump", "suit"]},
    "c4a1a": {"strict": ["tau_cannon", "rpg"], "always": ["longjump", "suit"]},
    "c4a3": {"strict": ["tau_cannon", "rpg"], "always": ["longjump", "suit"]},
}

# Gates from a later map of a mission on, `{map: gates}`.
MAP_GATES: dict[str, dict[str, list[str]]] = {
    # From here On A Rail's way on is blocked by crates only an explosive
    # clears. Loose logic takes the MP5's grenade launcher as well; strict asks
    # for a grenade or a satchel charge.
    "c2a2e": {"always": ["crate_breaker"], "strict": ["thrown_explosives"]},
}

# Copies that do not count toward their weapon's check, `{item: [maps]}`.
UNREACHABLE_COPIES: dict[str, list[str]] = {
    # The guard waving at the tram, which the player never leaves. The rest
    # from the scenario harness, 2026-09-30.
    "Glock": [
        "c0a0",
        "c0a0b@2070 632 -2312",  # out of bounds
        "c1a0@-132 -1083 -216",  # carries no Glock
        # Not this guard: the first to drop one opens the door after the suit.
        "c1a0@-184 408 -222",
        "c1a0c@1348 -216 -360",  # unconscious; a later guard in the mission has one
        "c1a3@35 1047 0",  # part of a cutscene, drops nothing
        "c2a1@-472 46 96",  # hands over the .357, has no Glock
        "c2a5c@-688 400 -272",  # carries a shotgun
    ],
    "MP5": [
        "c2a4d@384 560 16",  # a maker that spawns conditionally; others here drop
    ],
    # Lambda Core's suit never spawns in.
    "HEV Suit": ["c3a2d"],
}

# Copies confirmed reachable in play that the flood fill could not prove.
CONFIRMED_COPIES: dict[str, list[str]] = {
    # The Lambda Core armoury, beside the Tau Cannon the fill does reach.
    "Tripmine": ["c3a2d"],
    # The rest from the scenario harness, 2026-09-30.
    "Glock": [
        "c0a0d@-2017 -458 -221", "c1a0d@-2579 -706 -272", "c1a1@1168 1968 728",
        "c2a5d@-640 864 -1152", "c1a2a@-716 -60 -256", "c1a4i@-826 -479 -744", "c2a2@-1532 -2800 -1352",
        "c2a3d@976 -1224 788", "c2a4a@-232 -1008 0", "c2a4d@144 32 16", "c2a5e",
        "c3a1@480 -884 576", "c3a2a@-2316 576 -1",
    ],
    "MP5": [
        "c2a1@-92 320 -1", "c2a4e@-560 -96 224", "c2a2b1@-3352 -716 368", "c2a3@-481 -416 1524",
        "c2a5@1679 319 64", "c3a1a@-3400 168 304",
    ],
    "Shotgun": [
        "c2a2b2@2304 420 -8",
        "c2a4e@-80 -496 128",  # roams; met nearby rather than at this spot
        "c2a5@2016 320 32",
    ],
    "Satchel Charge": ["c2a5e", "c4a3"],
    "Hand Grenade": ["c2a5e"],
}

# --- Weapons --------------------------------------------------------------
#
# One Archipelago item can cover several engine classnames, because retail ships
# two spellings for a few weapons and its maps use both: `weapon_glock` and
# `weapon_9mmhandgun` are the same pistol, `weapon_mp5` and `weapon_9mmAR` the
# same submachine gun. Both spellings unlock together, and both are refused
# together until the item arrives.

WEAPON_ITEMS: dict[str, list[str]] = {
    "Glock": ["weapon_glock", "weapon_9mmhandgun"],
    ".357 Magnum": ["weapon_357", "weapon_python"],
    "MP5": ["weapon_mp5", "weapon_9mmAR"],
    "Shotgun": ["weapon_shotgun"],
    "Crossbow": ["weapon_crossbow"],
    "RPG": ["weapon_rpg"],
    "Tau Cannon": ["weapon_gauss"],
    "Gluon Gun": ["weapon_egon"],
    "Hivehand": ["weapon_hornetgun"],
    "Satchel Charge": ["weapon_satchel"],
    "Tripmine": ["weapon_tripmine"],
    "Snarks": ["weapon_snark"],
    "Hand Grenade": ["weapon_handgrenade"],
}

# What the run opens with, always. Retail has exactly one melee weapon, so
# unlike the Sven Co-op world there is nothing here to randomise.
STARTING_WEAPONS = ["weapon_crowbar"]

# Weapons that are a check but never an item. Walking up to the crowbar in the
# freezer is a moment in the run even though you are already holding one.
UNRANDOMISED_WEAPON_LOCATIONS: dict[str, list[str]] = {
    "Crowbar": ["weapon_crowbar"],
}

# Optional items, controlled by YAML toggles.
OPTIONAL_ITEMS: dict[str, list[str]] = {
    "HEV Suit": ["item_suit"],
    "Long Jump Module": ["item_longjump"],
    # No pickup: the item lets impulse 100 turn the flashlight on, on Half-Life's
    # and Blue Shift's maps. Newest, so after the others.
    "Flashlight": [],
}

# Chargers no player can reach without noclip that the automatic checks in
# `build_campaign_data` (seam twins, somewhere to stand, walled in behind a
# transition) do not catch, as `{map: {(classname, rounded position)}}`. The
# position is the charger's key, the `at` of its trigger in campaign.json.
# Empty for Half-Life: its one entry, We've Got Hostiles' Part 2 charger, is
# now found by `pocketed_chargers`.
UNREACHABLE_CHARGERS: dict[str, set[tuple[str, tuple[int, int, int]]]] = {}

# Gates on single pickup checks, `{map: {"classname@x y z": gates}}`.
# Office Complex part 5: these sit where only something with range gets them,
# confirmed in play.
_ANY_RANGED = {"always": ["any_ranged"]}
LOCATION_GATES: dict[str, dict[str, dict[str, list[str]]]] = {
    "c1a2d": {
        "item_healthkit@262 -2332 -537": _ANY_RANGED,
        "ammo_glockclip@95 -2318 -533": _ANY_RANGED,
        "ammo_glockclip@95 -2350 -533": _ANY_RANGED,
        "ammo_buckshot@354 -2078 -525": _ANY_RANGED,
        "ammo_buckshot@113 -2221 -525": _ANY_RANGED,
        "ammo_buckshot@110 -2233 -525": _ANY_RANGED,
        "ammo_buckshot@113 -2253 -525": _ANY_RANGED,
    },
}

# Pickups no player can reach, as `{map: {(classname, (x, y, z))}}`: the origin
# for a placed one, the crate and its key position for one a crate drops. All
# confirmed out of reach in play.
UNREACHABLE_PICKUPS: dict[str, set[tuple[str, tuple[int, int, int]]]] = {
    # On A Rail part 3.
    "c2a2b1": {
        ("weapon_handgrenade", (-1972, 756, 124)),
        ("weapon_handgrenade", (-1956, 724, 124)),
    },
    # On A Rail part 4.
    "c2a2b2": {("item_healthkit", (1360, -1512, 227))},
    # On A Rail part 5: part 3's crates c2a2b1box1 and c2a2b1box15, carried
    # over by globalname. They count in part 3.
    "c2a2c": {
        ("func_breakable", (-1464, -3096, 1244)),
        ("func_breakable", (-1256, -2976, 1244)),
    },
    # Apprehension part 5: crates c2a3crate1 and c2a3crate2.
    "c2a3d": {
        ("func_breakable", (1904, 480, 224)),
        ("func_breakable", (1656, 480, 224)),
    },
    # Surface Tension part 5.
    "c2a5b": {("item_battery", (784, -1176, 88))},
    # Surface Tension part 7: crate c2a5d_5.
    "c2a5d": {("func_breakable", (-184, -752, -288))},
    # Lambda Core part 5: stuck under shelves.
    "c3a2c": {
        ("item_battery", (-340, 916, -2174)),
        ("ammo_357", (-304, 916, -2174)),
        ("ammo_ARgrenades", (-266, 916, -2174)),
        ("item_battery", (-680, 892, -1024)),
    },
    # Lambda Core part 7: under the rubble, the box and the lower shelf.
    "c3a2d": {
        ("item_battery", (752, -1104, -768)),
        ("ammo_357", (1304, -320, -208)),
        ("weapon_tripmine", (1528, -640, -248)),
        ("weapon_tripmine", (1528, -600, -248)),
        ("item_battery", (1688, -600, -256)),
        ("ammo_gaussclip", (1688, -640, -256)),
        ("ammo_gaussclip", (1688, -680, -256)),
        ("item_battery", (1688, -744, -256)),
        ("ammo_gaussclip", (1432, -744, -256)),
    },
}

# Scientists and guards that do not count, as `{map: {(classname, (x, y, z))}}`.
# `monster_generic` stand-ins that count, as `{map: {(kind, (x, y, z))}}`.
GENERIC_NPCS: dict[str, set[tuple[str, tuple[int, int, int]]]] = {
    # Black Mesa Inbound part 5: the scientist on the G-Man's train. Confirmed
    # killable in play.
    "c0a0d": {("scientist", (1680, 1024, -210))},
}

# NPCs the automatic exclusions drop that play shows count, same form as
# `UNKILLABLE_NPCS`.
KILLABLE_NPCS: dict[str, set[tuple[str, tuple[int, int, int]]]] = {
    # The G-Man's train scientist: the line-of-sight test misses it from the
    # ride, but it can be shot.
    "c0a0d": {("monster_generic", (1680, 1024, -210))},
    # Unforeseen Consequences part 5: the scientist pulled into the vent. A
    # killtarget removes him after the scene, which the player watches.
    "c1a1b": {("monster_scientist", (-508, -592, -182))},
    # Apprehension part 2: the scientist the ichthyosaur takes. A killtarget
    # removes him after the scene, which the player watches.
    "c2a3a": {("monster_scientist", (1384, 928, 848))},
}

# NPCs whose death softlocks the run, same form.
CRITICAL_NPCS: dict[str, set[tuple[str, tuple[int, int, int]]]] = {
    # Black Mesa Inbound: the guard placed in part 5 rides on into part 6, where
    # his scripts open the train door. Dead, he leaves the player on the train.
    "c0a0d": {("monster_barney", (-2017, -458, -221))},
    # Anomalous Materials part 5: the two at the retinal scanners, whose scans
    # open the test chamber. A killtarget deletes them once its door closes
    # behind the player.
    "c1a0e": {
        ("monster_scientist", (1692, -32, -320)),
        ("monster_scientist", (1640, -32, -320)),
    },
}

UNKILLABLE_NPCS: dict[str, set[tuple[str, tuple[int, int, int]]]] = {
    # Black Mesa Inbound part 1: the group at the start of the ride, passed
    # before a player can shoot. Confirmed in play.
    "c0a0": {
        ("monster_scientist", (2720, 3704, 567)),
        ("monster_scientist", (2324, 3680, 567)),
        ("monster_scientist", (1936, 3760, 567)),
        ("monster_barney", (2276, 3680, 567)),
    },
    # Office Complex part 2: a vortigaunt kills him before a player can reach
    # him. Confirmed in play.
    "c1a2a": {("monster_scientist", (28, -1024, -232))},
}

# NPCs named for a later part than the map they stand in, because the player
# only reaches them from there: `{map: {(classname, (x, y, z)): part map}}`.
NPC_PARTS: dict[str, dict[tuple[str, tuple[int, int, int]], str]] = {
    # Surface Tension: placed in part 6's map, reached coming back from part 7.
    "c2a5c": {("monster_scientist", (-64, -768, -336)): "c2a5d"},
}

# Logic for single NPCs, `{map: {(classname, (x, y, z)): gates}}`.
NPC_GATES = {
    # Unforeseen Consequences part 5: the scientist hiding in the dumpster. The
    # lid keeps a melee swing from reaching him.
    "c1a1b": {("monster_scientist", (1284, -1024, -268)): _ANY_RANGED},
}

# The break room microwave. Five buttons share its panel, each mastered by the
# multisource the one before fired, so only the fifth press reaches
# `microwavepopmm1`: the multi_manager that bursts the casserole. The first
# press alone only beeps.
#
# Questionable Ethics part 3: the scientist and guard testing the tau cannon
# behind the wall. They are only voices and gibs, no monsters, so their deaths
# are the blast that ends the scene: `taublast2_mm` fires the gibs.
FIRED_CHECKS: dict[str, list[tuple[str, str, str]]] = {
    "c1a0d": [("microwave", "microwavepopmm1", "Microwave")],
    "c2a4f": [
        ("scientist", "taublast2_mm", "Tau Test Scientist (Part 3)"),
        ("barney", "taublast2_mm", "Tau Test Security Guard (Part 3)"),
    ],
}


HALF_LIFE = Campaign(
    key="half_life",
    name="Half-Life",
    game_dir="valve",
    detect="valve/maps/c0a0.bsp",
    chapters=CHAPTERS,
    goal_chapter=GOAL_CHAPTER,
    intro_chapter=INTRO_CHAPTER,
    intro_trains={m: "train" for m in ("c0a0", "c0a0a", "c0a0b", "c0a0c", "c0a0d", "c0a0e")},
    gates=CHAPTER_GATES,
    map_gates=MAP_GATES,
    unreachable_copies=UNREACHABLE_COPIES,
    confirmed_copies=CONFIRMED_COPIES,
    weapons=WEAPON_ITEMS,
    optional_items=OPTIONAL_ITEMS,
    unrandomised_weapons=UNRANDOMISED_WEAPON_LOCATIONS,
    melee=STARTING_WEAPONS,
    unreachable=UNREACHABLE_CHARGERS,
    unreachable_pickups=UNREACHABLE_PICKUPS,
    location_gates=LOCATION_GATES,
    unkillable_npcs=UNKILLABLE_NPCS,
    generic_npcs=GENERIC_NPCS,
    killable_npcs=KILLABLE_NPCS,
    critical_npcs=CRITICAL_NPCS,
    npc_parts=NPC_PARTS,
    npc_gates=NPC_GATES,
    fired_checks=FIRED_CHECKS,
    # Office Complex leaves for We've Got Hostiles from part 3; parts 4 and 5
    # are a loop back round to the start.
    complete_maps={"c1a2": "c1a2b"},
    # The hazard course: a training course rather than part of the campaign.
    # Then the Uplink demo and `lambda_bunker`, which ship in `valve/maps` and
    # look single-player (no deathmatch spawns) without being campaign maps.
    excluded_maps=frozenset(
        {"t0a0", "t0a0a", "t0a0b", "t0a0b1", "t0a0b2", "t0a0c", "t0a0d",
         "hldemo1", "hldemo2", "hldemo3", "lambda_bunker"}
    ),
    armour_item="HEV Suit",
    short="hl",
    legacy=True,
)
