"""Hand-authored campaign facts that cannot be derived from the BSPs.

Everything that *can* be read out of the maps (which weapons exist where, which
monsters are present, how the maps chain together) is derived in
`build_campaign_data.py`. This module holds only the editorial decisions:
chapter grouping and names, which weapon pickups map to which Archipelago item,
and the logic gates.

This is the file to edit when tuning logic. Nothing else hard-codes these facts.
"""

from __future__ import annotations

# --- Chapters -------------------------------------------------------------
#
# Names come from the `## Chapter NN:` header in each map's shipped .cfg. The
# spelling "Unforeseen Consequences" is corrected here (Valve's cfg misspells it
# "Unforseen"), and hl_c18's cfg header is a copy-paste of chapter 11's -- it is
# really the endgame, so it is folded into the Nihilanth chapter.

CHAPTERS: list[tuple[str, str, list[str]]] = [
    ("black_mesa_inbound", "Black Mesa Inbound", ["hl_c00"]),
    ("anomalous_materials", "Anomalous Materials", ["hl_c01_a1", "hl_c01_a2"]),
    ("unforeseen_consequences", "Unforeseen Consequences", ["hl_c02_a1", "hl_c02_a2"]),
    ("office_complex", "Office Complex", ["hl_c03"]),
    ("weve_got_hostiles", "We've Got Hostiles", ["hl_c04"]),
    ("blast_pit", "Blast Pit", ["hl_c05_a1", "hl_c05_a2", "hl_c05_a3"]),
    ("power_up", "Power Up", ["hl_c06"]),
    ("on_a_rail", "On A Rail", ["hl_c07_a1", "hl_c07_a2"]),
    ("apprehension", "Apprehension", ["hl_c08_a1", "hl_c08_a2"]),
    ("residue_processing", "Residue Processing", ["hl_c09"]),
    ("questionable_ethics", "Questionable Ethics", ["hl_c10"]),
    (
        "surface_tension",
        "Surface Tension",
        ["hl_c11_a1", "hl_c11_a2", "hl_c11_a3", "hl_c11_a4", "hl_c11_a5"],
    ),
    ("forget_about_freeman", "Forget About Freeman", ["hl_c12"]),
    ("lambda_core", "Lambda Core", ["hl_c13_a1", "hl_c13_a2", "hl_c13_a3", "hl_c13_a4"]),
    ("xen", "Xen", ["hl_c14"]),
    ("gonarchs_lair", "Gonarch's Lair", ["hl_c15"]),
    ("interloper", "Interloper", ["hl_c16_a1", "hl_c16_a2", "hl_c16_a3", "hl_c16_a4"]),
    ("nihilanth", "Nihilanth", ["hl_c17", "hl_c18"]),
]

# The final chapter is never unlocked by an item -- it opens once the player has
# completed `missions_required` other chapters.
GOAL_CHAPTER = "nihilanth"

# --- Weapons --------------------------------------------------------------
#
# One Archipelago item can cover several engine classnames. Sven Co-op splits the
# MP5 into weapon_9mmAR and its own weapon_m16 (HLSPClassicMode.as maps m16 ->
# 9mmAR when Classic Mode is on), and the Glock exists under both its Half-Life
# and Sven names, so both spellings unlock together.

WEAPON_ITEMS: dict[str, list[str]] = {
    "Glock": ["weapon_glock", "weapon_9mmhandgun"],
    ".357 Magnum": ["weapon_357"],
    "MP5": ["weapon_9mmAR", "weapon_m16"],
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

# Always granted, never randomised.
STARTING_WEAPONS = ["weapon_crowbar", "weapon_medkit"]

# Optional items, controlled by YAML toggles.
OPTIONAL_ITEMS: dict[str, list[str]] = {
    "HEV Suit": ["item_suit"],
    "Long Jump Module": ["item_longjump"],
}

CLASSNAME_TO_ITEM: dict[str, str] = {
    classname: item
    for table in (WEAPON_ITEMS, OPTIONAL_ITEMS)
    for item, classnames in table.items()
    for classname in classnames
}

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
HEAVY_WEAPONS = ["RPG", "Tau Cannon", "Gluon Gun", "Crossbow", ".357 Magnum", "Shotgun", "MP5"]

EXPLOSIVES = ["RPG", "Hand Grenade", "Satchel Charge", "Tripmine"]

# Usable while swimming -- the crowbar is, but ichthyosaurs realistically are not
# a melee fight, and grenades/tripmines do not work underwater.
UNDERWATER_WEAPONS = ["Glock", ".357 Magnum", "MP5", "Crossbow", "Tau Cannon", "Gluon Gun", "Hivehand"]

# --- Monster locations ----------------------------------------------------
#
# `(display name, requirement group or None)`. A monster only becomes a location
# in maps where the BSP actually contains one. Requirements are attached to the
# kill itself, which is how "you need a real weapon for this part of the level"
# is expressed without inventing sub-regions.

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

REQUIREMENT_GROUPS: dict[str, list[str]] = {
    "ranged": RANGED_WEAPONS,
    "heavy": HEAVY_WEAPONS,
    "explosives": EXPLOSIVES,
    "underwater": UNDERWATER_WEAPONS,
}

# --- Chapter entry gates --------------------------------------------------
#
# Applied to the chapter's region entrance, so every location in the chapter
# inherits them. `strict` gates are dropped when logic_difficulty is `loose`.
# Suit/long jump gates only apply when the matching YAML toggle shuffles them.

CHAPTER_GATES: dict[str, dict[str, list[str]]] = {
    # From here on you are fighting armed marines, not headcrabs.
    "weve_got_hostiles": {"strict": ["ranged"]},
    "blast_pit": {"strict": ["ranged"]},
    "power_up": {"strict": ["ranged"]},
    "on_a_rail": {"strict": ["ranged"]},
    "apprehension": {"strict": ["ranged"]},
    "residue_processing": {"strict": ["ranged"]},
    "questionable_ethics": {"strict": ["ranged"]},
    "surface_tension": {"strict": ["ranged"]},
    "forget_about_freeman": {"strict": ["heavy"]},
    "lambda_core": {"strict": ["heavy"]},
    # Xen: the long jump module is standard equipment from here on, and the suit
    # is what powers it.
    "xen": {"strict": ["heavy"], "always": ["longjump", "suit"]},
    "gonarchs_lair": {"strict": ["heavy"], "always": ["longjump", "suit"]},
    "interloper": {"strict": ["heavy"], "always": ["longjump", "suit"]},
    "nihilanth": {"strict": ["heavy"], "always": ["longjump", "suit"]},
}

# --- Which location types to generate -------------------------------------
#
# The entity-derived types (individual weapon pickups, "first kill of a
# gargantua", kill-count milestones) produced a lot of checks that read as
# arbitrary in play: the apache and tentacle at the start of Surface Tension are
# scenery you run past, not objectives.
#
# So for now a location is simply "you got to this part of the campaign": one
# per map, plus one per mission for finishing it. That is 53 checks against at
# most 32 progression items, which is enough to place everything.
#
# The generators for the other types are still here and still correct. Add the
# names back to re-enable them once we have worked out which ones earn a check.
ENABLED_LOCATION_TYPES = {
    "map_reached",
    "chapter_complete",
    # "pickup",
    # "kill",
    # "kill_count",
}

# --- Sizing ---------------------------------------------------------------

# Maps that end up with fewer locations than this get topped up with kill-count
# milestones, so sparse maps (most of Xen) still carry checks.
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

ITEM_ID_BASE = 7_710_000
LOCATION_ID_BASE = 7_720_000
