"""Hand-authored campaign facts that cannot be derived from the BSPs.

Everything that *can* be read out of the maps (which weapons exist where, which
monsters are present, how the maps chain together) is derived in
`build_campaign_data.py`. This module holds only the editorial decisions:
which campaigns exist, chapter grouping and names, which weapon pickups map to
which Archipelago item, and the logic gates.

This is the file to edit when tuning logic. Nothing else hard-codes these facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- Campaigns ------------------------------------------------------------
#
# Sven Co-op ships four single-player conversions and one hub map that fronts
# all of them, `-sp_campaign_portal`. Each campaign is an independent run with
# its own missions, its own starting mission and its own finale, and a YAML
# toggle decides which of them are in a seed.
#
# Two facts about the hub drive the shape of this file.
#
# Its consoles are numbered, not named: the sign on each is a texture
# (`hl_ch01`, `of_ch07`, `ba_ch03`, and so on), so console N is simply "this
# campaign's Nth mission" and the mission *names* below are ours to choose. The
# numbering is not uniform, though. Half-Life's consoles are unpadded and start
# at 1 because its mission 0 has no console at all, Opposing Force's are padded
# and skip 06, and the rest run 01 upward. That is why `consoles` is an explicit
# list parallel to `chapters` rather than anything computed: the plugin gets a
# generated lookup table and never does arithmetic on a targetname.
#
# Chapter keys are permanent. `data/ids.json` keys every location by chapter,
# so renaming a key renumbers a location and breaks existing seeds. Names are
# free to change; keys are not. The Half-Life keys below are unchanged from when
# it was the only campaign, which is what keeps its ids stable.


@dataclass(frozen=True)
class Campaign:
    key: str
    name: str
    # YAML toggle that includes this campaign in a seed.
    option: str
    # YAML range deciding how many of this campaign's missions open its finale.
    # One per campaign and entirely independent: a seed with three campaigns has
    # three of these, and finishing missions in one never opens another's finale.
    # Half-Life's keeps the name it had when it was the only campaign.
    missions_option: str
    # (chapter key, display name, maps in campaign order).
    chapters: list[tuple[str, str, list[str]]]
    # Portal console for each chapter, positionally. None where the hub has no
    # console for that mission and `!warp` is the only way in.
    consoles: list[str | None]
    # The finale. Never unlocked by an item: it opens once `missions_required`
    # of this campaign's other missions are done, and finishing it is one of the
    # seed's goal conditions.
    goal_chapter: str
    # Weapons this campaign brings to the pool that no earlier one has. Shared
    # weapons (every campaign has a crowbar) are declared once, by Half-Life.
    #
    # Which campaigns a weapon is *available* in is not this: that is read out of
    # the maps at build time, so an Opposing Force seed can still be given a
    # shotgun even though Half-Life is the campaign that declared it.
    weapons: dict[str, list[str]] = field(default_factory=dict)
    # What this campaign can hand you to swing at things with. One of these
    # replaces the crowbar when `random_starting_weapon` is on, so every entry
    # has to be a melee weapon the campaign's own maps actually contain *and* one
    # the engine knows about everywhere -- see `script_weapons`.
    melee: dict[str, list[str]] = field(default_factory=dict)
    # What a shared weapon is called *here*, when this campaign reskins it into
    # something else. Sven Co-op does that with a `globalmodellist` in the map
    # .cfg: They Hunger's maps swap the pipe wrench's models for a shovel and the
    # hand grenade's for a stick of TNT, so a check reading "First Pipe Wrench"
    # names something the player never sees. Display only -- the item, the
    # classname and the location id are all unchanged.
    weapon_aliases: dict[str, str] = field(default_factory=dict)
    # True when this campaign's weapons are custom entities its own map scripts
    # register (`g_CustomEntityFuncs.RegisterCustomEntity`) rather than weapons
    # built into the game. Those classnames only exist while one of its maps is
    # running, so they can be shuffled within the campaign but never handed over
    # anywhere else: `GiveNamedItem` on another campaign's map has nothing to make.
    script_weapons: bool = False
    # Mission entry gates, as `{chapter key: {"strict": [group, ...]}}`.
    gates: dict[str, dict[str, list[str]]] = field(default_factory=dict)


HALF_LIFE = Campaign(
    key="half_life",
    name="Half-Life",
    option="include_half_life",
    missions_option="missions_required",
    # Names come from the `## Chapter NN:` header in each map's shipped .cfg. The
    # spelling "Unforeseen Consequences" is corrected here (Valve's cfg misspells
    # it "Unforseen"), and hl_c18's cfg header is a copy-paste of chapter 11's --
    # it is really the endgame, so it is folded into the Nihilanth chapter.
    chapters=[
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
    ],
    # Mission 0 is the tram ride and the hub has no console for it.
    consoles=[None] + [f"hl_ch{n}" for n in range(1, 18)],
    goal_chapter="nihilanth",
    weapons={
        # One Archipelago item can cover several engine classnames. Sven Co-op
        # splits the MP5 into weapon_9mmAR and its own weapon_m16
        # (HLSPClassicMode.as maps m16 -> 9mmAR when Classic Mode is on), and the
        # Glock exists under both its Half-Life and Sven names, so both spellings
        # unlock together.
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
    },
    melee={"Crowbar": ["weapon_crowbar"]},
    gates={
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
        # Xen: the long jump module is standard equipment from here on, and the
        # suit is what powers it. Strict logic names the two weapons by hand
        # rather than a tier -- the alien grunt and Gonarch fights are not
        # something to walk into with a shotgun, so both the Tau cannon and the
        # RPG are required outright.
        "xen": {"strict": ["tau_cannon", "rpg"], "always": ["longjump", "suit"]},
        "gonarchs_lair": {"strict": ["tau_cannon", "rpg"], "always": ["longjump", "suit"]},
        "interloper": {"strict": ["tau_cannon", "rpg"], "always": ["longjump", "suit"]},
        "nihilanth": {"strict": ["tau_cannon", "rpg"], "always": ["longjump", "suit"]},
    },
)

# Ten consoles for 35 maps, so the grouping below is ours: it follows the map
# names' own act/sub-act structure, which is how the conversion divided them, and
# borrows Opposing Force's chapter titles where the split lines up. `of4a5` is
# left out deliberately -- nothing in any shipped map changelevels to it, so a
# check there could never fire and an item placed on it would be lost.
OPPOSING_FORCE = Campaign(
    key="opposing_force",
    name="Opposing Force",
    option="include_opposing_force",
    missions_option="opposing_force_missions_required",
    chapters=[
        ("of_boot_camp", "Boot Camp", ["of0a0"]),
        ("of_welcome_to_black_mesa", "Welcome To Black Mesa", ["of1a1", "of1a2"]),
        ("of_we_are_not_alone", "We Are Not Alone", ["of1a3", "of1a4", "of1a4b"]),
        ("of_missing_in_action", "Missing In Action", ["of1a5", "of1a5b", "of1a6"]),
        ("of_friendly_fire", "Friendly Fire", ["of2a1", "of2a1b", "of2a2"]),
        ("of_we_are_pulling_out", "We Are Pulling Out", ["of2a4", "of2a5", "of2a6"]),
        ("of_crush_depth", "Crush Depth", ["of3a1", "of3a2"]),
        ("of_vicarious_reality", "Vicarious Reality", ["of3a4", "of3a5", "of3a6"]),
        ("of_pit_worms_nest", "Pit Worm's Nest", ["of4a1", "of4a2", "of4a3", "of4a4"]),
        (
            "of_worlds_collide",
            "Worlds Collide",
            ["of5a1", "of5a2", "of5a3", "of5a4",
             "of6a1", "of6a2", "of6a3", "of6a4", "of6a4b", "of6a5"],
        ),
    ],
    # The hub has no `of_ch06`; its ten consoles run 01-05 and 07-11.
    consoles=[f"of_ch{n:02d}" for n in (1, 2, 3, 4, 5, 7, 8, 9, 10, 11)],
    goal_chapter="of_worlds_collide",
    weapons={
        "Desert Eagle": ["weapon_eagle"],
        "SAW": ["weapon_m249", "weapon_saw"],
        "Sniper Rifle": ["weapon_sniperrifle"],
        "Displacer Cannon": ["weapon_displacer"],
        "Spore Launcher": ["weapon_sporelauncher"],
        "Barnacle Grapple": ["weapon_grapple"],
        "Pipe Wrench": ["weapon_pipewrench"],
        "Minigun": ["weapon_minigun"],
        # No combat knife. Opposing Force's maps still place `weapon_knife`, but
        # this build of Sven Co-op has no such weapon -- it is in neither
        # server.dll nor any map script -- so those entities never spawn. As an
        # item it could never be granted and as a check it could never fire,
        # which is exactly the sort of location fill will hide progression behind.
    },
    # From `maps/ofglobal.gmr`, read out of the models it names. Most of that
    # list is the same weapon with soldier's hands and a nicer mesh, but the
    # crowbar is replaced outright: `v_crowbar.mdl` becomes `v_knife.mdl`, skin
    # `knife_blade.BMP`. Shephard carries a combat knife, not a crowbar.
    #
    # `weapon_knife` was its own entity once and is unsupported in this build --
    # Opposing Force's maps still place a few, and those never spawn -- so the
    # knife reaches players the only way it can, as the crowbar's local face.
    weapon_aliases={"Crowbar": "Combat Knife"},
    melee={
        "Crowbar": ["weapon_crowbar"],
        "Pipe Wrench": ["weapon_pipewrench"],
    },
    gates={
        # Boot camp is a firing range and the first two missions are the escape
        # from it; the shooting starts once you are back in Black Mesa proper.
        "of_we_are_not_alone": {"strict": ["ranged"]},
        "of_missing_in_action": {"strict": ["ranged"]},
        "of_friendly_fire": {"strict": ["ranged"]},
        "of_we_are_pulling_out": {"strict": ["ranged"]},
        "of_crush_depth": {"strict": ["ranged"]},
        "of_vicarious_reality": {"strict": ["ranged"]},
        # The pit worm and the gene worm are both damage races.
        "of_pit_worms_nest": {"strict": ["heavy"]},
        "of_worlds_collide": {"strict": ["heavy"]},
    },
)

# Six consoles and six chapters, which is Blue Shift's own structure exactly.
# It brings no weapons of its own: in Sven Co-op it uses Half-Life's, down to the
# crowbar. Its only unique pickups are the armour vest and helmet, which are
# armour top-ups rather than items.
BLUE_SHIFT = Campaign(
    key="blue_shift",
    name="Blue Shift",
    option="include_blue_shift",
    missions_option="blue_shift_missions_required",
    chapters=[
        ("bs_living_quarters", "Living Quarters Outbound", ["ba_tram1", "ba_tram2", "ba_tram3"]),
        ("bs_insecurity", "Insecurity",
         ["ba_security1", "ba_security2", "ba_maint", "ba_elevator"]),
        ("bs_duty_calls", "Duty Calls",
         ["ba_canal1", "ba_canal1b", "ba_canal2", "ba_canal3"]),
        ("bs_captive_freight", "Captive Freight",
         ["ba_yard1", "ba_yard2", "ba_yard3", "ba_yard3a", "ba_yard3b",
          "ba_yard4", "ba_yard4a", "ba_yard5", "ba_yard5a"]),
        ("bs_focal_point", "Focal Point",
         ["ba_teleport1", "ba_xen1", "ba_xen2", "ba_xen3", "ba_xen4", "ba_xen5", "ba_xen6"]),
        ("bs_power_struggle", "Power Struggle",
         ["ba_teleport2", "ba_power1", "ba_power2", "ba_outro"]),
    ],
    consoles=[f"bs_ch{n:02d}" for n in range(1, 7)],
    goal_chapter="bs_power_struggle",
    # Barney swings the same crowbar Gordon does.
    melee={"Crowbar": ["weapon_crowbar"]},
    gates={
        "bs_duty_calls": {"strict": ["ranged"]},
        "bs_captive_freight": {"strict": ["ranged"]},
        "bs_focal_point": {"strict": ["ranged"]},
        "bs_power_struggle": {"strict": ["ranged"]},
    },
)

# Three consoles, three episodes. Its check placement is still the plain shape
# every campaign gets for free -- a check per map, per mission, per charger and
# per weapon -- and the only logic it asserts is that you do not walk into
# Episode 2 or 3 with nothing but a melee weapon. `th_escape` is a standalone
# bonus map rather than part of any episode, so it is left out.
THEY_HUNGER = Campaign(
    key="they_hunger",
    name="They Hunger",
    option="include_they_hunger",
    missions_option="they_hunger_missions_required",
    chapters=[
        ("th_episode_1", "They Hunger: Episode 1",
         ["th_ep1_00", "th_ep1_01", "th_ep1_02", "th_ep1_03", "th_ep1_04", "th_ep1_05"]),
        ("th_episode_2", "They Hunger: Episode 2",
         ["th_ep2_00", "th_ep2_01", "th_ep2_02", "th_ep2_03", "th_ep2_04"]),
        ("th_episode_3", "They Hunger: Episode 3",
         ["th_ep3_00", "th_ep3_01", "th_ep3_02", "th_ep3_03", "th_ep3_04",
          "th_ep3_05", "th_ep3_06", "th_ep3_07"]),
    ],
    consoles=[f"th_ep{n:02d}" for n in range(1, 4)],
    goal_chapter="th_episode_3",
    weapons={
        "Colt 1911": ["weapon_colt1911"],
        "Taurus": ["weapon_th_taurus"],
        "Sawed-Off Shotgun": ["weapon_sawedoff"],
        "Grease Gun": ["weapon_greasegun"],
        "Tommy Gun": ["weapon_tommygun"],
        "M14": ["weapon_m14"],
        "M16A1": ["weapon_m16a1"],
        "Tesla Gun": ["weapon_teslagun"],
        "Spanner": ["weapon_spanner"],
    },
    # From `models/hunger/hungerglobal.txt`, the model replacement list its maps
    # load -- and read out of the models themselves, because the replacement
    # *filenames* lie: `v_hungercrowbar.mdl` is internally `v_umbrella.mdl` and
    # skinned `Umbrella_Base.bmp`. They Hunger's melee weapon is the umbrella.
    #
    # Only the three that stop being recognisable are renamed. Its .357 is a
    # detective's revolver and its crossbow is a crossbow, so those keep their
    # names; a shovel is not a pipe wrench, a stick of dynamite is not a hand
    # grenade, and an umbrella is certainly not a crowbar.
    weapon_aliases={
        "Crowbar": "Umbrella",
        "Pipe Wrench": "Shovel",
        "Hand Grenade": "TNT",
    },
    # Every one of these is a custom entity registered by They Hunger's own map
    # scripts (`scripts/maps/hunger/weapons/`), not a weapon the game ships, so
    # none of them can be handed over outside its maps.
    script_weapons=True,
    # The crowbar and the wrench are built into the game, so they exist
    # everywhere -- they just look like an umbrella and a shovel while you are
    # here, which is the whole charm of opening a They Hunger run with one.
    #
    # The spanner is the deliberate rough edge. It is script-registered, so a
    # seed that starts you with it leaves you empty-handed on any map that is not
    # They Hunger's, and logic does not model that: everything past the point you
    # would have found your first melee weapon is technically out of logic until
    # a real weapon arrives. Offered anyway, because it is only reachable when
    # They Hunger is in the seed and it is that campaign's own weapon.
    melee={
        "Crowbar": ["weapon_crowbar"],
        "Pipe Wrench": ["weapon_pipewrench"],
        "Spanner": ["weapon_spanner"],
    },
    # Episode 1 is where you find your first guns, so it stays enterable with a
    # melee weapon and is the only episode that can be handed out at the start.
    # Everything after it expects you to be armed with something that shoots --
    # its own or another campaign's, since this group covers both.
    gates={
        "th_episode_2": {"strict": ["ranged_they_hunger"]},
        "th_episode_3": {"strict": ["ranged_they_hunger"]},
    },
)

CAMPAIGNS: list[Campaign] = [HALF_LIFE, OPPOSING_FORCE, BLUE_SHIFT, THEY_HUNGER]

# The campaign that is always safe to fall back on when a YAML disables
# everything. Also the one whose data predates the others, hence its ids.
DEFAULT_CAMPAIGN = HALF_LIFE.key

CAMPAIGN_BY_KEY: dict[str, Campaign] = {c.key: c for c in CAMPAIGNS}

# --- Derived tables -------------------------------------------------------
#
# Everything below is assembled from CAMPAIGNS. Nothing here is editorial.

CHAPTERS: list[tuple[str, str, list[str]]] = [
    chapter for campaign in CAMPAIGNS for chapter in campaign.chapters
]

CAMPAIGN_OF_CHAPTER: dict[str, str] = {
    key: campaign.key for campaign in CAMPAIGNS for key, _, _ in campaign.chapters
}

GOAL_CHAPTERS: dict[str, str] = {c.goal_chapter: c.key for c in CAMPAIGNS}

CHAPTER_GATES: dict[str, dict[str, list[str]]] = {
    key: gates for campaign in CAMPAIGNS for key, gates in campaign.gates.items()
}

# Console targetname base -> chapter key, for every console the hub has.
PORTAL_CONSOLES: dict[str, str] = {
    console: key
    for campaign in CAMPAIGNS
    for console, (key, _, _) in zip(campaign.consoles, campaign.chapters)
    if console is not None
}

# --- Weapons --------------------------------------------------------------

WEAPON_ITEMS: dict[str, list[str]] = {
    name: classnames
    for campaign in CAMPAIGNS
    for name, classnames in campaign.weapons.items()
}

WEAPON_CAMPAIGN: dict[str, str] = {
    name: campaign.key
    for campaign in CAMPAIGNS
    for name in campaign.weapons
}

# Weapons that may only be handed over on their own campaign's maps, as
# classname -> the campaigns whose scripts define them.
#
# They Hunger's whole arsenal is like this: the spanner, the tommy gun, the tesla
# gun and the rest are custom entities its map scripts register, so on any other
# campaign's map the classname does not exist and `GiveNamedItem` has nothing to
# make. They still shuffle inside a They Hunger seed; they just cannot travel.
# Everything Half-Life and Opposing Force ship is in server.dll and travels fine.
RESTRICTED_CLASSNAMES: dict[str, list[str]] = {
    classname: [campaign.key]
    for campaign in CAMPAIGNS
    if campaign.script_weapons
    for classnames in campaign.weapons.values()
    for classname in classnames
}

# What you start with when nothing randomises it: the crowbar, as it always was.
# `random_starting_weapon` replaces the melee half with one of MELEE_STARTERS,
# chosen per seed and sent through the snapshot rather than living here.
STARTING_WEAPONS = ["weapon_crowbar", "weapon_medkit"]

# Always yours whatever else changes.
FIXED_STARTING_WEAPONS = ["weapon_medkit"]

# Every melee weapon any campaign could open you with, as display name ->
# classnames. Names that are also weapon items (the wrench, the knife, the
# spanner) drop out of the pool for the seed that starts you with them.
MELEE_STARTERS: dict[str, list[str]] = {
    name: classnames
    for campaign in CAMPAIGNS
    for name, classnames in campaign.melee.items()
}

# campaign key -> {item name: what that campaign calls it}. Display only.
WEAPON_ALIASES: dict[str, dict[str, str]] = {
    campaign.key: campaign.weapon_aliases
    for campaign in CAMPAIGNS
    if campaign.weapon_aliases
}

MELEE_CAMPAIGNS: dict[str, list[str]] = {}
for _campaign in CAMPAIGNS:
    for _name in _campaign.melee:
        MELEE_CAMPAIGNS.setdefault(_name, []).append(_campaign.key)

# Weapons that are a check but never an item. Walking up to the one the campaign
# actually gives you is a moment in the run whether or not you started with it.
UNRANDOMISED_WEAPON_LOCATIONS: dict[str, list[str]] = {
    "Crowbar": ["weapon_crowbar"],
}

# Optional items, controlled by YAML toggles.
OPTIONAL_ITEMS: dict[str, list[str]] = {
    "HEV Suit": ["item_suit"],
    "Long Jump Module": ["item_longjump"],
}

# The crowbar is in here despite never being an item, and that is what stops you
# picking one up in a seed that started you with a wrench instead: the classname
# is gated on an item name the pool never contains, so it is refused unless it is
# also one of the seed's starting weapons -- and starting weapons are checked
# first. In a seed that does start you with a crowbar, nothing changes.
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

# --- Logic groups ---------------------------------------------------------

# Deliberately no They Hunger weapons in any of these groups. They cannot be
# carried outside its maps, so counting a tommy gun as "you have a gun" would let
# strict logic expect you to walk into We've Got Hostiles armed with something the
# engine will not give you there. They Hunger's own missions have no gates, so the
# groups lose nothing by leaving them out.

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
    # Opposing Force
    "Desert Eagle",
    "SAW",
    "Sniper Rifle",
    "Displacer Cannon",
    "Spore Launcher",
    "Minigun",
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
    "SAW",
    "Displacer Cannon",
    "Spore Launcher",
    "Minigun",
    "Sniper Rifle",
]

# The same question asked inside They Hunger, where its own guns count.
#
# It needs a group of its own because its weapons are script-registered and
# cannot be carried anywhere else: putting a tommy gun in `ranged` would let
# strict logic send you into We've Got Hostiles holding something the engine will
# not give you there. Half-Life's and Opposing Force's weapons are built into the
# game, so they work here as well and are included.
RANGED_WEAPONS_THEY_HUNGER = RANGED_WEAPONS + [
    "Colt 1911",
    "Taurus",
    "Sawed-Off Shotgun",
    "Grease Gun",
    "Tommy Gun",
    "M14",
    "M16A1",
    "Tesla Gun",
]

EXPLOSIVES = ["RPG", "Hand Grenade", "Satchel Charge", "Tripmine", "Spore Launcher"]

# Usable while swimming -- the crowbar is, but ichthyosaurs realistically are not
# a melee fight, and grenades/tripmines do not work underwater.
UNDERWATER_WEAPONS = [
    "Glock", ".357 Magnum", "MP5", "Crossbow", "Tau Cannon", "Gluon Gun", "Hivehand",
    "Desert Eagle",
]

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

# Single-weapon groups. A gate naming several groups requires one item from each,
# so a group of one is how "this exact weapon" is expressed.
REQUIREMENT_GROUPS: dict[str, list[str]] = {
    "ranged": RANGED_WEAPONS,
    "ranged_they_hunger": RANGED_WEAPONS_THEY_HUNGER,
    "heavy": HEAVY_WEAPONS,
    "explosives": EXPLOSIVES,
    "underwater": UNDERWATER_WEAPONS,
    "tau_cannon": ["Tau Cannon"],
    "rpg": ["RPG"],
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
