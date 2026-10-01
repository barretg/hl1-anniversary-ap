from __future__ import annotations

from dataclasses import dataclass

from Options import (
    Choice,
    DeathLink,
    DefaultOnToggle,
    PerGameCommonOptions,
    Range,
    StartInventoryPool,
    Toggle,
    Visibility,
)

from .data import MAX_MISSIONS, MAX_MISSIONS_BY_CAMPAIGN


class MissionsRequired(Range):
    """How many Half-Life missions open Nihilanth.

    Nihilanth is never unlocked by an item -- it becomes available once this many
    other missions have been finished. The default is every one of them.
    """

    display_name = "Missions Required"
    range_start = 1
    range_end = MAX_MISSIONS
    default = MAX_MISSIONS


class IncludeHalfLife(DefaultOnToggle):
    """Include Half-Life's missions.

    Turning every game off turns this one back on: a seed needs something to
    play.
    """

    display_name = "Include Half-Life"


class IncludeOpposingForce(Toggle):
    """Include Opposing Force's missions, and its weapons.

    Needs Opposing Force installed alongside Half-Life, and `/install` run after
    it was, so its maps and content are linked into the mod. Its finale, Worlds
    Collide, becomes part of the goal.
    """

    display_name = "Include Opposing Force"


class IncludeBlueShift(Toggle):
    """Include Blue Shift's missions.

    Needs Blue Shift installed alongside Half-Life, and `/install` run after it
    was. Its finale, Power Struggle (with A Leap Of Faith), becomes part of the
    goal.
    """

    display_name = "Include Blue Shift"


class OpposingForceMissionsRequired(Range):
    """How many Opposing Force missions open Worlds Collide. Ignored unless
    Opposing Force is included."""

    display_name = "Opposing Force Missions Required"
    range_start = 1
    range_end = MAX_MISSIONS_BY_CAMPAIGN.get("opposing_force", 1)
    default = range_end


class BlueShiftMissionsRequired(Range):
    """How many Blue Shift missions open Power Struggle. Ignored unless Blue
    Shift is included."""

    display_name = "Blue Shift Missions Required"
    range_start = 1
    range_end = MAX_MISSIONS_BY_CAMPAIGN.get("blue_shift", 1)
    default = range_end


class RandomStartingWeapon(DefaultOnToggle):
    """EXPERIMENTAL. Start with a random melee weapon from the included games.

    Half-Life and Blue Shift bring the crowbar, Opposing Force the combat knife
    and the pipe wrench. The ones you do not start with become items. With only
    Half-Life or Blue Shift included there is nothing to choose, and you start
    with the crowbar as always. Off: the first included game's own (the crowbar,
    or the knife for an Opposing Force-only seed).
    """

    display_name = "Random Starting Weapon"


class ViewmodelStyle(Choice):
    """EXPERIMENTAL. Whose hands hold the weapons in Opposing Force and Blue
    Shift.

    per_campaign: Shephard's on Opposing Force's maps, Barney's on Blue Shift's,
    Gordon's on Half-Life's, as each game shipped. always_gordon: Gordon's
    everywhere. Presentation only; nothing about the seed changes.
    """

    display_name = "Viewmodel Style"
    option_per_campaign = 0
    option_always_gordon = 1
    default = 0


class LogicDifficulty(Choice):
    """How much firepower logic assumes you need to clear a mission.

    strict: a mission is only expected of you once you own weapons suited to it.
    In Half-Life that means a firearm from We've Got Hostiles, explosives from
    Blast Pit, and heavier weapons with explosives from Power Up on; Xen wants the
    Tau cannon and the RPG, plus the long jump module and HEV suit when those are
    shuffled. Opposing Force and Blue Shift ask for a firearm, then heavier
    weapons, as their fights grow. Safe for anyone, and the default.
    loose: weapon requirements are dropped, so the generator may expect you to
    clear Surface Tension with a crowbar. What a mission cannot be crossed without
    still applies at any difficulty: the Xen equipment, Opposing Force's grapple,
    and the firearm Duty Calls needs to get past its barrel.

    Gates are per mission, not per part: being in logic means the mission is
    enterable, not that every corner of it is comfortable.
    """

    display_name = "Logic Difficulty"
    option_strict = 0
    option_loose = 1
    default = 0


class Chargesanity(DefaultOnToggle):
    """Every health charger and HEV charge panel is a check.

    111 of them, spread through the campaign, sent the moment you press use on
    one -- an empty charger counts, so this is about finding them rather than
    needing them. Turn it off and the seed drops to the 96 map checks, the 18
    mission checks and the 15 weapon checks, which makes for a much shorter run
    with far less filler.
    """

    display_name = "Chargesanity"


class ExcludeIntroMissions(DefaultOnToggle):
    """Leave each included game's opening ride out of the seed.

    Black Mesa Inbound, Incoming and Living Quarters Outbound: minutes of riding
    and listening with nothing to fight. Turned on they go entirely (no
    regions, no checks, no unlock item) and they stop counting toward the
    missions required.
    """

    display_name = "Exclude Intro Missions"


class ShuffleHevSuit(Toggle):
    """Shuffle the HEV suit into the item pool.

    What the item controls is armour: until it arrives, armour is held at zero
    from every source -- the campaign's own loadout, batteries, charge panels and
    filler grants alike. You keep the suit itself throughout, because in GoldSrc
    it is the suit that draws the weapon HUD and a player without one cannot
    change weapons at all.

    The Xen missions expect it either way, because the long jump module runs off
    suit power.
    """

    display_name = "Shuffle HEV Suit"


class ShuffleLongJump(Toggle):
    """Shuffle the long jump module into the item pool.

    When on, the Xen missions expect it in logic, and you cannot long jump until
    the item arrives however many modules the campaign puts in front of you.

    When off, the module stays where the campaign hands it over, in Forget About
    Freeman: picking it up there sends it to you like any other item, so you keep
    it into Xen however you get there.
    """

    display_name = "Shuffle Long Jump Module"


class ShuffleFlashlight(Toggle):
    """Shuffle the flashlight into the item pool.

    Until the Flashlight arrives, the flashlight key does nothing on Half-Life's
    and Blue Shift's maps. With Opposing Force in the seed, its night vision is
    a separate item, the Night Vision Goggles, needed on its maps. The hub is
    always lit.

    When off, you have both from the start, as in the retail games.
    """

    display_name = "Shuffle Flashlight"


class MeleeThrow(Toggle):
    """Add Melee Throw to the item pool.

    Once it arrives, secondary fire throws the crowbar or the knife. It hits four
    times as hard as a swing and lands on the floor; walk over it to pick it back
    up, or it returns to you by itself after ten seconds.

    When off, there is no throw at all.
    """

    display_name = "Add Melee Throw"


class AllyWeaponDrops(Toggle):
    """Let logic expect weapons dropped by allies you kill.

    A security guard drops his Glock when he dies, and Opposing Force's marines
    drop theirs. With this on, killing a friendly for their weapon counts as a
    way to a "First ..." weapon check. Weapons dropped by enemies always count.
    """

    display_name = "Ally Weapon Drops"


class DeathLinkAmnesty(Range):
    """How many deaths are forgiven before one is sent to the multiworld.

    Only outgoing DeathLinks are affected: an incoming one always kills you. The
    death message says how much amnesty is left. Once the allowance runs out the
    next death goes out to the multiworld and the allowance starts again.

    0 sends every death. The default forgives four.
    """

    display_name = "DeathLink Amnesty"
    range_start = 0
    range_end = 20
    default = 4


class AmmoRelief(Toggle):
    """Removed. Kept only so YAMLs that still set it load; it has no effect."""

    display_name = "Ammo Relief"
    visibility = Visibility.none


class TrapPercentage(Range):
    """Percentage of your filler items replaced by traps.

    Four exist, all nuisances rather than punishments -- none can cost you a run:

    - Scientist Trap: four scientists appear around you and start following you
      about.
    - Headcrab Trap: four headcrabs, same idea, considerably less friendly.
    - Butterfingers Trap: you drop the weapon you are holding. The suit reissues
      it after half a minute if you cannot find it again.
    - Bot Swarm Trap: six crowbar-wielding bots appear around you, run about
      crouch-jumping over things, and swing at whatever they bump into --
      you included.
    """

    display_name = "Trap Percentage"
    range_start = 0
    range_end = 100
    default = 15


@dataclass
class HalfLifeOptions(PerGameCommonOptions):
    include_half_life: IncludeHalfLife
    include_opposing_force: IncludeOpposingForce
    include_blue_shift: IncludeBlueShift
    missions_required: MissionsRequired
    opposing_force_missions_required: OpposingForceMissionsRequired
    blue_shift_missions_required: BlueShiftMissionsRequired
    random_starting_weapon: RandomStartingWeapon
    viewmodel_style: ViewmodelStyle
    logic_difficulty: LogicDifficulty
    exclude_intro_missions: ExcludeIntroMissions
    chargesanity: Chargesanity
    shuffle_hev_suit: ShuffleHevSuit
    shuffle_longjump: ShuffleLongJump
    shuffle_flashlight: ShuffleFlashlight
    melee_throw: MeleeThrow
    ally_weapon_drops: AllyWeaponDrops
    ammo_relief: AmmoRelief
    trap_percentage: TrapPercentage
    start_inventory_from_pool: StartInventoryPool
    death_link: DeathLink
    death_link_amnesty: DeathLinkAmnesty
