"""Facts shared by every campaign: the hub, charger rules, logic groups, ids.

Moved here verbatim from `campaign_layout.py`. Per-game facts live in that
game's module; see `base.Campaign`.
"""

from __future__ import annotations

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

# What a mission's entrance may be. The name is still `_button` either way, so
# converting a panel to a walk-in volume is a change to the map alone.
HUB_ENTRANCE_CLASSNAMES = ("func_button", "trigger_once", "trigger_multiple")


def hub_button_index(targetname: str, campaign_prefix: str = "") -> int | None:
    """The mission index a lobby button is for, or None if it is not one.

    The map has other buttons in it -- doors, the joke pit -- and they are not
    ours. Only `chapter_<n>_button` with a genuine number in the middle counts.
    A campaign other than Half-Life puts its `hub_button_prefix` in front, and
    `n` then counts that campaign's missions.
    """
    prefix = campaign_prefix + HUB_BUTTON_PREFIX
    if not targetname.startswith(prefix):
        return None
    if not targetname.endswith(HUB_BUTTON_SUFFIX):
        return None
    middle = targetname[len(prefix):-len(HUB_BUTTON_SUFFIX)]
    if not middle.isdigit():
        return None
    return int(middle)

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
