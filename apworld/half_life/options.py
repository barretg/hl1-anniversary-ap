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
    """EXPERIMENTAL. Include Opposing Force's missions, and its weapons.

    Needs Opposing Force installed alongside Half-Life, and `/install` run after
    it was, so its maps and content are linked into the mod. Its finale, Worlds
    Collide, becomes part of the goal.
    """

    display_name = "Include Opposing Force"


class IncludeBlueShift(Toggle):
    """EXPERIMENTAL. Include Blue Shift's missions.

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

    strict: a mission is only expected of you once you own a weapon suited to it.
    Anything from We've Got Hostiles onward wants a firearm; Forget About Freeman
    and Lambda Core want something heavier than a pistol; Xen onward wants the Tau
    cannon and the RPG by name, plus the long jump module and HEV suit when those
    are shuffled. Safe for anyone, and the default.
    loose: weapon requirements are dropped entirely, so the generator may expect
    you to clear Surface Tension with a crowbar and will happily place your only
    gun behind a mission that assumes you already have one. The equipment gates on
    Xen still apply.

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
    """EXPERIMENTAL AND BUGGY. Refill a gun the level has no ammo for.

    A shuffled seed can hand you the crossbow in a map that holds no bolts, and
    Half-Life will never give you any: the weapon is dead weight until the next
    map. With this on, a gun that runs dry on ammo the level does not stock is
    announced, and the suit synthesises more five minutes later. If it is empty
    again within ten seconds of a refill you get one more for free, which covers
    dying and reloading a save from just before it arrived.

    Known rough edges: what a level stocks is read from the entities placed in
    it, so ammo that only exists inside a breakable crate is not counted and the
    game may offer you a refill you did not need. Loading a save or leaving the
    mission restarts the wait from the beginning. Expect the timing to be wrong
    occasionally rather than the run to be broken -- nothing here can take
    anything away from you, it only ever adds ammo.

    Off by default, and it is a comfort valve rather than part of the balance:
    with it on a patient player is never truly out of ammo.
    """

    display_name = "Ammo Relief"


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
    ammo_relief: AmmoRelief
    trap_percentage: TrapPercentage
    start_inventory_from_pool: StartInventoryPool
    death_link: DeathLink
    death_link_amnesty: DeathLinkAmnesty
