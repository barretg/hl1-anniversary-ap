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

# The RPG is left out: it counts as heavy and as an explosive, not as a
# day-to-day firearm.
RANGED_WEAPONS = [
    "Glock",
    ".357 Magnum",
    "MP5",
    "Shotgun",
    "Crossbow",
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
    # Anything that can detonate a barrel from a distance: the ranged weapons
    # bar the Hivehand, whose hornets do not set one off, plus the RPG, which
    # `ranged` leaves out, and the thrown explosives. Not the tripmine, which
    # cannot be placed to reach it.
    "barrel_shooter": [w for w in RANGED_WEAPONS if w != "Hivehand"]
                      + ["RPG", "Hand Grenade", "Satchel Charge"],
    # What clears On A Rail's crates. The MP5's grenade launcher does too, but
    # only loose logic counts on it.
    "crate_breaker": ["Hand Grenade", "Satchel Charge", "MP5"],
    "thrown_explosives": ["Hand Grenade", "Satchel Charge"],
    "flashlight": ["Flashlight"],
}

# --- Weapon drops ---------------------------------------------------------
#
# Monsters that drop a weapon when they die, and which one. A drop is a weapon
# lying in the world like any other, so picking it up sends the weapon check,
# and the map holding the monster is another source for it.
#
# Read from the SDK and the Opposing Force port (`DropItem` in each monster's
# `Killed`/`GibMonster`, and the `weapons` default in its `Spawn`). The bit
# values are each monster's own `weapons` flags. The `*_repel` makers hand
# their `weapons` on to the monster they drop in, so they read the same way.


def _flags(entity: dict[str, str]) -> int:
    try:
        return int(entity.get("weapons", "0") or 0)
    except ValueError:
        return 0


def _hgrunt(entity: dict[str, str]) -> str | None:
    # Always armed: no shotgun bit means the MP5 (the default when 0).
    return "weapon_shotgun" if _flags(entity) & 8 else "weapon_9mmAR"


def _grunt_ally(entity: dict[str, str]) -> str | None:
    flags = _flags(entity)
    if not flags & (1 | 8 | 16):
        return None  # unarmed; no default
    if flags & 8:
        return "weapon_shotgun"
    if flags & 16:
        return "weapon_m249"
    return "weapon_9mmAR"


def _medic_ally(entity: dict[str, str]) -> str | None:
    flags = _flags(entity) or 2  # 0 means the Glock
    if flags & 2:
        return "weapon_9mmhandgun"
    if flags & 1:
        return "weapon_eagle"
    return None  # the needle alone


def _torch_ally(entity: dict[str, str]) -> str | None:
    return "weapon_eagle" if (_flags(entity) or 1) & 1 else None


def _male_assassin(entity: dict[str, str]) -> str | None:
    flags = _flags(entity) or 1  # 0 means the MP5
    if flags & 1:
        return "weapon_9mmAR"
    if flags & 8:
        return "weapon_sniperrifle"
    return None


def _barney(entity: dict[str, str]) -> str | None:
    # `body` 2 is the holster with no gun in it.
    try:
        body = int(entity.get("body", "0") or 0)
    except ValueError:
        body = 0
    return "weapon_9mmhandgun" if body < 2 else None


# `{classname: (what it drops, ally)}`. Allies count only when the seed asks
# for them (`ally_weapon_drops`): killing a friendly is never otherwise needed.
# The shock trooper drops a live shock roach, which hands over the Shock Roach
# when touched. Otis draws his Desert Eagle when he fights, so he always has it
# by the time he dies.
WEAPON_DROPPERS: dict[str, tuple] = {
    "monster_human_grunt": (_hgrunt, False),
    "monster_grunt_repel": (_hgrunt, False),
    "monster_male_assassin": (_male_assassin, False),
    "monster_assassin_repel": (_male_assassin, False),
    "monster_shocktrooper": (lambda e: "weapon_shockrifle", False),
    "monster_shocktrooper_repel": (lambda e: "weapon_shockrifle", False),
    "monster_barney": (_barney, True),
    "monster_otis": (lambda e: "weapon_eagle", True),
    "monster_human_grunt_ally": (_grunt_ally, True),
    "monster_grunt_ally_repel": (_grunt_ally, True),
    "monster_human_medic_ally": (_medic_ally, True),
    "monster_medic_ally_repel": (_medic_ally, True),
    "monster_human_torch_ally": (_torch_ally, True),
    "monster_torch_ally_repel": (_torch_ally, True),
}


def dropped_weapon(entity: dict[str, str]) -> tuple[str, bool] | None:
    """`(weapon classname, ally)` this entity drops when killed, or None.

    A `monstermaker` drops what its monster would with no keyvalues set, since
    it passes none on.
    """
    classname = entity.get("classname", "")
    if classname == "monstermaker":
        rule = WEAPON_DROPPERS.get(entity.get("monstertype", ""))
        entity = {}
    else:
        rule = WEAPON_DROPPERS.get(classname)
    if rule is None:
        return None
    weapon = rule[0](entity)
    return (weapon, rule[1]) if weapon else None


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
    "microwave",
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
