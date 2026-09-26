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
CHAPTER_GATES: dict[str, dict[str, list[str]]] = {
    "of2a1": _RANGED,
    "of2a4": _RANGED,
    "of3a1": _RANGED,
    "of3a4": _RANGED,
    "of4a1": _RANGED,
    # The grapple lies in `of4a3`, the end of Vicarious Reality, and from Pit
    # Worm's Nest on progress needs it (confirmed in play).
    "of4a4": _HEAVY,
    "of5a1": _HEAVY,
    "of6a1": _HEAVY,
    "of6a4b": _HEAVY,
}

WEAPON_ITEMS: dict[str, list[str]] = {
    "Desert Eagle": ["weapon_eagle"],
    "M249": ["weapon_m249"],
    "Sniper Rifle": ["weapon_sniperrifle"],
    "Displacer": ["weapon_displacer"],
    "Spore Launcher": ["weapon_sporelauncher"],
    "Barnacle": ["weapon_grapple"],
    "Shock Roach": ["weapon_shockrifle"],
}

# Additions to the shared logic groups, applied only when this campaign is in
# the build so a Half-Life-only seed's groups are unchanged.
REQUIREMENT_GROUPS: dict[str, list[str]] = {
    "ranged": ["Desert Eagle", "M249", "Sniper Rifle", "Shock Roach",
               "Spore Launcher", "Displacer"],
    "heavy": ["Desert Eagle", "M249", "Sniper Rifle"],
    "explosives": ["Spore Launcher"],
    "underwater": ["Desert Eagle"],
    "barnacle_grapple": ["Barnacle"],
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
}

# The Shock Roach is never placed; it is dropped by a dying shock trooper. The
# first map placing one, `of1a5b`, has a single trooper that waits for a script
# (spawnflags 128) rather than a fight, so the anchor is the first real one, in
# Vicarious Reality. To confirm in play.
WEAPON_ANCHORS: dict[str, str] = {
    "Shock Roach": "of4a1",
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
    weapons=WEAPON_ITEMS,
    groups=REQUIREMENT_GROUPS,
    optional_items=OPTIONAL_ITEMS,
    unrandomised_weapons=UNRANDOMISED_WEAPON_LOCATIONS,
    melee=["weapon_knife", "weapon_pipewrench"],
    weapon_anchors=WEAPON_ANCHORS,
    # Boot camp: the training course, left out like Half-Life's hazard course.
    excluded_maps=frozenset({"ofboot0", "ofboot1", "ofboot2", "ofboot3", "ofboot4"}),
    hub_button_prefix="of_",
    armour_item="PCV",
    short="of",
)
