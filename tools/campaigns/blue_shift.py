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

# Duty Calls: past its first health charger and the crowbars, the way on is
# opened by shooting an explosive barrel. Nothing melee reaches it, so from
# `ba_canal1b` on the mission needs a ranged weapon or the RPG at any logic
# difficulty.
#
# Captive Freight: part 3 on is dark enough that strict logic wants the
# flashlight.
MAP_GATES: dict[str, dict[str, list[str]]] = {
    "ba_canal1b": {"always": ["barrel_shooter"]},
    "ba_yard3a": {"strict": ["flashlight"]},
}

# Focal Point part 2: the snarks are in the chumtoad cave at the bottom of the
# pit, too dark to find at any logic difficulty without the flashlight.
WEAPON_SOURCE_GATES: dict[str, dict[str, dict[str, list[str]]]] = {
    "ba_xen2": {"Snarks": {"always": ["flashlight"]}},
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

# Copies confirmed reachable in play that the flood fill could not prove.
CONFIRMED_COPIES: dict[str, list[str]] = {
    # The guard hands it over. The rest from the scenario harness, 2026-09-30.
    "Glock": ["ba_security2", "ba_security1@-864 2544 480"],
    "MP5": ["ba_yard1@676 -964 0", "ba_teleport2@624 644 272"],
    "Shotgun": ["ba_yard1@768 -832 0", "ba_power1@952 128 -480"],
}

# Copies that do not count toward their weapon's check, from the scenario
# harness, 2026-09-30.
UNREACHABLE_COPIES: dict[str, list[str]] = {
    # Cutscene guards on the intro mission.
    "Glock": ["ba_tram1@-2844 916 64", "ba_tram2@3488 -672 2272",
              "ba_tram3@1600 3680 541",
              # The guard at the start of Duty Calls; he drops nothing.
              "ba_canal1@1928 208 24"],
    # Unarmed when met; a grunt earlier in the mission drops one.
    "Shotgun": ["ba_teleport2@-1456 -816 0"],
}

# Pickups no player can reach, as `{map: {(classname, (x, y, z))}}`.
UNREACHABLE_PICKUPS: dict[str, set[tuple[str, tuple[int, int, int]]]] = {
    # Power Struggle part 2: 9mm Clip 2, confirmed out of reach in play.
    "ba_power1": {("ammo_9mmclip", (635, 943, -479))},
}

# Scientists and barneys that cannot be killed, as `{map: {(classname, (x, y,
# z))}}`.
UNKILLABLE_NPCS: dict[str, set[tuple[str, tuple[int, int, int]]]] = {
    # Living Quarters Outbound part 1: the guard at the game table, out of
    # sight of the tram.
    "ba_tram1": {("monster_barney", (-2844, 916, 64))},
    # Insecurity part 2: the three walkers seen only on the security cameras.
    "ba_security2": {
        ("monster_scientist", (-1088, -1456, -240)),
        ("monster_scientist", (-144, -1392, -240)),
        ("monster_scientist", (-864, -2192, -240)),
    },
}

# NPCs the automatic exclusions drop that play shows count, same form.
KILLABLE_NPCS: dict[str, set[tuple[str, tuple[int, int, int]]]] = {
    # Living Quarters Outbound part 3: all four on the platform can be shot
    # from the tram, though the line-of-sight test missed them.
    "ba_tram3": {
        ("monster_scientist", (2080, 3704, 541)),
        ("monster_scientist", (1296, 3760, 541)),
        ("monster_barney", (1600, 3680, 541)),
        ("monster_scientist", (1684, 3680, 541)),
    },
    # Insecurity part 4: the scientist who flees the elevator crash; the
    # killtarget only clears him away once he is out of sight.
    "ba_elevator": {("monster_scientist", (32, 2392, 1556))},
}

# Listed `monster_generic` stand-ins that count, as `{map: {(kind, (x, y, z))}}`.
GENERIC_NPCS: dict[str, set[tuple[str, tuple[int, int, int]]]] = {
    # Insecurity part 2: the guard who hands over the pistol, and the invisible
    # stand-in for the one seated at the front desk. Hurting either fails the
    # mission.
    "ba_security2": {("barney", (648, 1684, 484)), ("barney", (-656, 1128, 244))},
    # Insecurity part 4: the two scientists in the falling elevator.
    "ba_elevator": {("scientist", (-344, 1408, 3204)), ("scientist", (-232, 1348, 3204))},
    # Duty Calls part 1: the scientist sitting above with the flashlight.
    "ba_canal1": {("scientist", (744, -1404, 180))},
}

# NPCs whose deletion by the map is their death.
REMOVAL_DEATHS: dict[str, set[tuple[str, tuple[int, int, int]]]] = {
    # Insecurity part 4: the scientist the vortigaunt takes behind the window,
    # and the one who flees the crash, whose run ends out of sight.
    "ba_elevator": {("monster_scientist", (-612, 1760, 1664)),
                    ("monster_scientist", (32, 2392, 1556))},
    # Power Struggle part 2: the guard and scientist the opening attack
    # kills; their scripts end in a killtarget.
    "ba_power1": {("monster_barney", (-188, 268, -252)),
                  ("monster_scientist", (-232, 184, -252))},
}

# The front desk guard sits as a non-solid puppet (`controls_barney`) while an
# invisible copy (`inviso_barney`) takes the hits: one check, either tagged.
SWAPPED_NPCS = {
    "ba_security2": {
        ("monster_generic", (-656, 1128, 244)): (
            ("monster_generic", (-656, 1168, 244)), "Front Desk Guard",
            "The seated guard at the front desk; an invisible stand-in takes "
            "his hits, and hurting him fails the mission."),
    },
}

# NPCs whose check names a later part than their map, because the player
# reaches them from there: `{map: {(classname, (x, y, z)): part map}}`.
NPC_PARTS = {
    # Living Quarters Outbound: placed in part 2's map, seen from part 3's tram.
    "ba_tram2": {("monster_barney", (3488, -672, 2272)): "ba_tram3"},
}


BLUE_SHIFT = Campaign(
    key="blue_shift",
    name="Blue Shift",
    game_dir="bshift",
    detect="bshift/maps/ba_tram1.bsp",
    chapters=CHAPTERS,
    goal_chapter="ba_teleport2",
    intro_chapter="ba_tram1",
    intro_trains={m: "barney_tram" for m in ("ba_tram1", "ba_tram2", "ba_tram3")},
    gates=CHAPTER_GATES,
    map_gates=MAP_GATES,
    weapon_source_gates=WEAPON_SOURCE_GATES,
    optional_items=OPTIONAL_ITEMS,
    unrandomised_weapons=UNRANDOMISED_WEAPON_LOCATIONS,
    confirmed_copies=CONFIRMED_COPIES,
    unreachable_copies=UNREACHABLE_COPIES,
    unreachable_pickups=UNREACHABLE_PICKUPS,
    unkillable_npcs=UNKILLABLE_NPCS,
    killable_npcs=KILLABLE_NPCS,
    generic_npcs=GENERIC_NPCS,
    removal_deaths=REMOVAL_DEATHS,
    swapped_npcs=SWAPPED_NPCS,
    npc_parts=NPC_PARTS,
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
