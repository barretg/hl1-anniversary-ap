"""Hand-authored campaign facts that cannot be derived from the BSPs.

Everything that *can* be read out of the maps (which weapons exist where, which
monsters are present, where the chargers are) is derived in
`build_campaign_data.py`. This module holds only the editorial decisions:
chapter grouping and names, which weapon pickups map to which Archipelago item,
and the logic gates.

This is the file to edit when tuning logic. Nothing else hard-codes these facts.

Target: retail Half-Life on Steam, the 25th anniversary build. One campaign, one
game directory, `valve/maps`.
"""

from __future__ import annotations

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

# --- The hub ---------------------------------------------------------------

# The lobby map. Authored for this project and shipped inside the mod folder
# rather than inherited from `valve`, so it is also `startmap` in `liblist.gam`
# and `kHubMap` in `game/src/ap_hub.cpp`. All three have to name the same map.
HUB_MAP = "ap_lobby_alpha"

# One button per mission, named by that mission's index: `chapter_0_button` is
# the first mission in the `C` records, `chapter_17_button` the last.
#
# Derived from the map rather than hand-authored, which is the point. A button
# renamed or renumbered in the BSP moves its record with it, and a button naming
# a mission that does not exist fails the build instead of becoming a dead panel
# somebody finds by pressing it. The Sven Co-op world listed these by hand and
# had to keep the list and the map in step.
HUB_BUTTON_PREFIX = "chapter_"
HUB_BUTTON_SUFFIX = "_button"


def hub_button_index(targetname: str) -> int | None:
    """The mission index a lobby button is for, or None if it is not one.

    The map has other buttons in it -- doors, the joke pit -- and they are not
    ours. Only `chapter_<n>_button` with a genuine number in the middle counts.
    """
    if not targetname.startswith(HUB_BUTTON_PREFIX):
        return None
    if not targetname.endswith(HUB_BUTTON_SUFFIX):
        return None
    middle = targetname[len(HUB_BUTTON_PREFIX):-len(HUB_BUTTON_SUFFIX)]
    if not middle.isdigit():
        return None
    return int(middle)

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

# Every classname the game must refuse until the matching item arrives.
#
# The crowbar is in here despite never being an item. It is also in
# STARTING_WEAPONS, and starting weapons are checked first, so in practice it is
# always allowed -- the entry exists so that the table is the single answer to
# "is this pickup gated", with no classname falling through it unlisted.
CLASSNAME_TO_ITEM: dict[str, str] = {
    classname: item
    for table in (WEAPON_ITEMS, OPTIONAL_ITEMS, UNRANDOMISED_WEAPON_LOCATIONS)
    for item, classnames in table.items()
    for classname in classnames
}

# --- Chargers -------------------------------------------------------------
#
# The wall-mounted health and HEV units. Every one placed in a map is a check:
# they are fixed, obvious, and spread through the levels, so finding one is a
# real piece of exploration rather than an arbitrary milestone.

CHARGER_CLASSNAMES: dict[str, str] = {
    "func_healthcharger": "Health Charger",
    "func_recharge": "HEV Charger",
}

# Xen's healing pools, which are checks for the same reason the wall units are:
# fixed, obvious, and the only place on Xen that gives health back.
#
# They are not equipment and there is nothing to press. A pool is a `trigger_hurt`
# with *negative* damage -- `CBaseTrigger::HurtTouch` calls `TakeHealth` instead
# of `TakeDamage` when `dmg` is below zero -- so the entity is the same one Valve
# uses for lava, and only the sign tells them apart. Every other `trigger_hurt`
# in the campaign is left alone.
#
# Checked on touch rather than on use, and therefore exempt from the "somewhere
# to stand within the use radius" test that drops decorative wall units: standing
# in the pool is the whole interaction.
HEALING_POOL_CLASSNAMES: dict[str, str] = {
    "trigger_hurt": "Healing Pool",
}

# How coarsely a charger's world-space centre is rounded before it becomes part
# of that charger's identity, in map units.
#
# Identity is position, not brush model index, and this is the reason: the
# anniversary update recompiled single-player maps, and a recompile can renumber
# brush models, which would silently repoint every charger id in a map. Position
# survives any recompile that does not physically move the unit.
#
# The grid exists so that reading the same map twice gives the same id, not so
# that the game can rebuild the key: the game matches by nearest unit instead,
# which is what makes the pair robust to a recompile that nudges a brush and
# removes any need for two languages to round a float identically. 4 units is
# well inside the ~16-unit body of a charger, so two distinct units can never
# round together.
CHARGER_POSITION_GRID = 4

# --- Logic groups ---------------------------------------------------------

RANGED_WEAPONS = [
    "Glock",
    ".357 Magnum",
    "MP5",
    "Shotgun",
    "Crossbow",
    "RPG",
    "Tau Cannon",
    "Gluon Gun",
    "Hivehand",
    "Snarks",
]

# Enough punch to kill an armoured target in reasonable time.
HEAVY_WEAPONS = [
    "RPG",
    "Tau Cannon",
    "Gluon Gun",
    "Crossbow",
    ".357 Magnum",
    "Shotgun",
    "MP5",
]

EXPLOSIVES = ["RPG", "Hand Grenade", "Satchel Charge", "Tripmine"]

# Usable while swimming -- the crowbar is, but ichthyosaurs realistically are not
# a melee fight, and grenades/tripmines do not work underwater.
UNDERWATER_WEAPONS = [
    "Glock", ".357 Magnum", "MP5", "Crossbow", "Tau Cannon", "Gluon Gun",
    "Hivehand",
]

# Single-weapon groups. A gate naming several groups requires one item from each,
# so a group of one is how "this exact weapon" is expressed.
REQUIREMENT_GROUPS: dict[str, list[str]] = {
    "ranged": RANGED_WEAPONS,
    "heavy": HEAVY_WEAPONS,
    "explosives": EXPLOSIVES,
    "underwater": UNDERWATER_WEAPONS,
    "tau_cannon": ["Tau Cannon"],
    "rpg": ["RPG"],
}

# --- Monster locations ----------------------------------------------------
#
# `(display name, requirement group or None)`. A monster only becomes a location
# in maps where the BSP actually contains one. Requirements are attached to the
# kill itself, which is how "you need a real weapon for this part of the level"
# is expressed without inventing sub-regions.
#
# Not generated today -- see ENABLED_LOCATION_TYPES.

NOTABLE_MONSTERS: dict[str, tuple[str, str | None]] = {
    "monster_gargantua": ("Gargantua", "explosives"),
    "monster_bigmomma": ("Gonarch", "heavy"),
    "monster_nihilanth": ("Nihilanth", "heavy"),
    "monster_tentacle": ("Tentacle", None),
    "monster_ichthyosaur": ("Ichthyosaur", "underwater"),
    "monster_apache": ("Apache", "heavy"),
    "monster_osprey": ("Osprey", "heavy"),
    "monster_alien_grunt": ("Alien Grunt", "ranged"),
    "monster_alien_controller": ("Alien Controller", "ranged"),
    "monster_human_assassin": ("Assassin", "ranged"),
    "monster_sentry": ("Sentry Turret", "ranged"),
    "monster_turret": ("Ceiling Turret", "ranged"),
    "monster_miniturret": ("Mini Turret", "ranged"),
}

# --- Which location types to generate -------------------------------------
#
# The entity-derived types (individual weapon pickups, "first kill of a
# gargantua", kill-count milestones) produced a lot of checks that read as
# arbitrary in play: the apache and tentacle at the start of Surface Tension are
# scenery you run past, not objectives.
#
# So a location is one of three things:
#   - "you got to this part of the campaign": one per map, plus one per mission
#     for finishing it.
#   - "you found a charger": one per health or HEV unit placed in a map.
#   - "you found a weapon for the first time": one per weapon, for the whole
#     campaign rather than per map. The same shotgun in three levels is one
#     discovery, which is what made the old per-map `pickup` type feel arbitrary.
#
# The generators for the other types are still here and still correct. Add the
# names back to re-enable them once we have worked out which ones earn a check.
ENABLED_LOCATION_TYPES = {
    "map_reached",
    "chapter_complete",
    "charger",
    "weapon_pickup",
    # "pickup",  # the per-map variant, superseded by weapon_pickup
    # "kill",
    # "kill_count",
}

# --- Sizing ---------------------------------------------------------------

# Maps that end up with fewer locations than this get topped up with kill-count
# milestones, so sparse maps still carry checks. Only consulted when the
# entity-derived types above are switched on.
MIN_LOCATIONS_PER_MAP = 4

# Kill-count milestone thresholds, as a fraction of the map's placed monster count.
KILL_MILESTONE_FRACTIONS = [0.25, 0.5, 0.75]

# Monsters that are scenery or non-hostile and should not count toward anything.
IGNORED_MONSTERS = {
    "monster_scientist_dead",
    "monster_barney_dead",
    "monster_hgrunt_dead",
    "monster_hevsuit_dead",
    "monster_sitting_scientist",
    "monster_cockroach",
    "monster_rat",
    "monster_furniture",
    "monster_gman",
    "monster_generic",
    "monster_flyer_flock",
    "monster_leech",
}

# --- ID space -------------------------------------------------------------
#
# Deliberately clear of the Sven Co-op world's 7_710_000 / 7_720_000. The two
# worlds are separate games with separate datapackages, so an overlap would not
# actually break anything, but keeping them apart means an id seen in a log
# belongs to exactly one project.

ITEM_ID_BASE = 7_750_000
LOCATION_ID_BASE = 7_760_000
