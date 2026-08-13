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

from .data import MAX_MISSIONS


class MissionsRequired(Range):
    """How many missions open Nihilanth.

    Nihilanth is never unlocked by an item -- it becomes available once this many
    other missions have been finished. The default is every one of them.
    """

    display_name = "Missions Required"
    range_start = 1
    range_end = MAX_MISSIONS
    default = MAX_MISSIONS


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
    """Leave Black Mesa Inbound out of the seed.

    The tram ride in: minutes of riding and listening with nothing to fight.
    Turned on it goes entirely -- no regions, no checks, no unlock item -- and it
    stops counting toward Missions Required.
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

    When off, the module is left to Half-Life entirely: no long jump early on,
    and you pick it up where the campaign hands it over, in Forget About Freeman
    and everything after it.
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


class TrapPercentage(Range):
    """Percentage of your filler items replaced by traps.

    Three exist, all nuisances rather than punishments -- none can cost you a run:

    - Scientist Trap: four scientists appear around you and start following you
      about.
    - Headcrab Trap: four headcrabs, same idea, considerably less friendly.
    - Butterfingers Trap: you drop the weapon you are holding. The suit reissues
      it after half a minute if you cannot find it again.
    """

    display_name = "Trap Percentage"
    range_start = 0
    range_end = 100
    default = 15


@dataclass
class HalfLifeOptions(PerGameCommonOptions):
    missions_required: MissionsRequired
    logic_difficulty: LogicDifficulty
    exclude_intro_missions: ExcludeIntroMissions
    chargesanity: Chargesanity
    shuffle_hev_suit: ShuffleHevSuit
    shuffle_longjump: ShuffleLongJump
    trap_percentage: TrapPercentage
    start_inventory_from_pool: StartInventoryPool
    death_link: DeathLink
    death_link_amnesty: DeathLinkAmnesty
