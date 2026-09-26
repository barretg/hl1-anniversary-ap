"""Blue Shift: Calhoun's campaign, `bshift/maps`.

Chapters come from the retail BSPs the same way Half-Life's do, named from
`bshift/titles.txt`. Its maps are stored with two header lumps swapped;
`bsp_entities` reads both layouts.
"""

from __future__ import annotations

from .base import Campaign

# Blue Shift is not linear at the end. The real route is `xen6 -> teleport2 ->
# power1 -> power2 -> power1 -> teleport2 -> outro`: `teleport2` is visited
# twice, the second time showing "A Leap Of Faith" from an `env_message` rather
# than a `chaptertitle`. Power Struggle and A Leap Of Faith are therefore one
# finale mission keyed by its first map, so every transition after Focal Point's
# exit happens inside it and carries state exactly as retail does.
#
# `ba_canal3` is a dead-end branch off `ba_canal2`, placed after it.
CHAPTERS: list[tuple[str, str, list[str]]] = [
    ("ba_tram1", "Living Quarters Outbound", ["ba_tram1", "ba_tram2", "ba_tram3"]),
    ("ba_security1", "Insecurity",
     ["ba_security1", "ba_security2", "ba_maint", "ba_elevator"]),
    ("ba_canal1", "Duty Calls", ["ba_canal1", "ba_canal1b", "ba_canal2", "ba_canal3"]),
    ("ba_yard1", "Captive Freight",
     ["ba_yard1", "ba_yard2", "ba_yard3a", "ba_yard3b", "ba_yard3", "ba_yard4",
      "ba_yard4a", "ba_yard5", "ba_yard5a", "ba_teleport1"]),
    ("ba_xen1", "Focal Point",
     ["ba_xen1", "ba_xen2", "ba_xen3", "ba_xen4", "ba_xen5", "ba_xen6"]),
    ("ba_teleport2", "Power Struggle",
     ["ba_teleport2", "ba_power1", "ba_power2", "ba_outro"]),
]

_RANGED = {"strict": ["ranged"]}
CHAPTER_GATES: dict[str, dict[str, list[str]]] = {
    "ba_yard1": _RANGED,
    "ba_xen1": _RANGED,
    "ba_teleport2": _RANGED,
}

# Barney's armour: the vest and helmet, gating armour on BS maps. Blue Shift's
# `item_suit` in `ba_tram1` is not armour (it only turns the HUD on) and is not
# a check.
OPTIONAL_ITEMS: dict[str, list[str]] = {
    "Security Armor": ["item_armorvest", "item_helmet"],
}

# The six crowbars in `ba_canal1`. A check, never an item, like Half-Life's.
UNRANDOMISED_WEAPON_LOCATIONS: dict[str, list[str]] = {
    "Crowbar": ["weapon_crowbar"],
}

BLUE_SHIFT = Campaign(
    key="blue_shift",
    name="Blue Shift",
    game_dir="bshift",
    detect="bshift/maps/ba_tram1.bsp",
    chapters=CHAPTERS,
    goal_chapter="ba_teleport2",
    intro_chapter="ba_tram1",
    gates=CHAPTER_GATES,
    optional_items=OPTIONAL_ITEMS,
    unrandomised_weapons=UNRANDOMISED_WEAPON_LOCATIONS,
    melee=["weapon_crowbar"],
    # Its HEV-style wall units are scenery: none is a `func_recharge`, and a
    # test keeps it that way.
    charger_classnames=("func_healthcharger",),
    # The hazard course.
    excluded_maps=frozenset({f"ba_hazard{n}" for n in range(1, 7)}),
    # `ba_outro` ends on `trigger_endsection`, with nowhere further to go;
    # arriving there is the doorstep, not the end.
    complete_on={"ba_teleport2": "endsection"},
    hub_button_prefix="bs_",
    armour_item="Security Armor",
    short="bs",
)
