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
    "c2a1": {"strict": ["heavy", "explosives"]},
    "c2a2": {"strict": ["heavy", "explosives"]},
    "c2a3": {"strict": ["heavy", "explosives"]},
    "c2a4": {"strict": ["heavy", "explosives"]},
    # The lab is full of alien grunts, which are armoured and shrug off hornets,
    # and its corridors are strung with tripmines that want detonating from a
    # distance rather than by throwing squeakers at them.
    "c2a4d": {"strict": ["heavy", "explosives"]},
    "c2a5": {"strict": ["heavy", "explosives"]},
    "c3a1": {"strict": ["heavy", "explosives"]},
    "c3a2e": {"strict": ["heavy", "explosives"]},
    # Xen onward: the long jump module is standard equipment from here, and the
    # suit is what powers it. Strict logic names the two weapons by hand rather
    # than a tier -- the alien grunt and Gonarch fights are not something to walk
    # into with a shotgun -- so both the Tau cannon and the RPG are required.
    "c4a1": {"strict": ["tau_cannon", "rpg"], "always": ["longjump", "suit"]},
    "c4a2": {"strict": ["tau_cannon", "rpg"], "always": ["longjump", "suit"]},
    "c4a1a": {"strict": ["tau_cannon", "rpg"], "always": ["longjump", "suit"]},
    "c4a3": {"strict": ["tau_cannon", "rpg"], "always": ["longjump", "suit"]},
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
}

# Chargers no player can reach without noclip that the automatic checks in
# `build_campaign_data` (seam twins, somewhere to stand, walled in behind a
# transition) do not catch, as `{map: {(classname, rounded position)}}`. The
# position is the charger's key, the `at` of its trigger in campaign.json.
# Empty for Half-Life: its one entry, We've Got Hostiles' Part 2 charger, is
# now found by `pocketed_chargers`.
UNREACHABLE_CHARGERS: dict[str, set[tuple[str, tuple[int, int, int]]]] = {}


HALF_LIFE = Campaign(
    key="half_life",
    name="Half-Life",
    game_dir="valve",
    detect="valve/maps/c0a0.bsp",
    chapters=CHAPTERS,
    goal_chapter=GOAL_CHAPTER,
    intro_chapter=INTRO_CHAPTER,
    gates=CHAPTER_GATES,
    weapons=WEAPON_ITEMS,
    optional_items=OPTIONAL_ITEMS,
    unrandomised_weapons=UNRANDOMISED_WEAPON_LOCATIONS,
    melee=STARTING_WEAPONS,
    unreachable=UNREACHABLE_CHARGERS,
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
