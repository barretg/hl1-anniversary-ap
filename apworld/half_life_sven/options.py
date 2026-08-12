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

from .data import unlockable_chapters_of

# Each campaign's own ceiling: its missions, minus the finale that no number of
# them can be spent on.
_MAX = {
    key: len(unlockable_chapters_of(key))
    for key in ("half_life", "opposing_force", "blue_shift", "they_hunger")
}

MAX_MISSIONS = _MAX["half_life"]


class MissionsRequired(Range):
    """How many Half-Life missions open Nihilanth.

    Nihilanth is never unlocked by an item -- it becomes available once this many
    other Half-Life missions have been finished. The default is every one of them.

    Each campaign has its own version of this setting and they are completely
    independent: Opposing Force progress does nothing for Nihilanth, and
    Half-Life progress does nothing for Worlds Collide.
    """

    display_name = "Missions Required"
    range_start = 1
    range_end = _MAX["half_life"]
    default = _MAX["half_life"]


class OpposingForceMissionsRequired(Range):
    """How many Opposing Force missions open Worlds Collide.

    Independent of every other campaign's setting. Ignored unless Opposing Force
    is in the seed.
    """

    display_name = "Opposing Force Missions Required"
    range_start = 1
    range_end = _MAX["opposing_force"]
    default = _MAX["opposing_force"]


class BlueShiftMissionsRequired(Range):
    """How many Blue Shift missions open Power Struggle.

    Independent of every other campaign's setting. Ignored unless Blue Shift is
    in the seed.
    """

    display_name = "Blue Shift Missions Required"
    range_start = 1
    range_end = _MAX["blue_shift"]
    default = _MAX["blue_shift"]


class TheyHungerMissionsRequired(Range):
    """How many They Hunger episodes open Episode 3.

    Independent of every other campaign's setting. Ignored unless They Hunger is
    in the seed. There are only two other episodes, so this is 1 or 2.
    """

    display_name = "They Hunger Missions Required"
    range_start = 1
    range_end = _MAX["they_hunger"]
    default = _MAX["they_hunger"]


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

    107 of them, spread through the campaign, sent the moment you press use on
    one — an empty charger counts, so this is about finding them rather than
    needing them. Turn it off and the seed drops to the 48 mission checks plus
    the 13 weapon checks, which makes for a much shorter run with far less filler.
    """

    display_name = "Chargesanity"


class IncludeHalfLife(DefaultOnToggle):
    """Include the Half-Life campaign in the seed.

    18 missions, ending at Nihilanth. Turn every campaign off and this one comes
    back on regardless, because a seed has to contain something.
    """

    display_name = "Include Half-Life"


class IncludeOpposingForce(Toggle):
    """Include the Opposing Force campaign in the seed.

    10 missions, ending at Worlds Collide, and nine weapons Half-Life does not
    have: the SAW, the sniper rifle, the displacer, the spore launcher, the
    barnacle grapple and the rest. They join one shared pool, so enabling this
    puts Opposing Force weapons in Half-Life's missions and the other way round.
    """

    display_name = "Include Opposing Force"


class IncludeBlueShift(Toggle):
    """Include the Blue Shift campaign in the seed.

    6 missions, ending at Power Struggle. It brings no weapons of its own -- in
    Sven Co-op it uses Half-Life's, down to the crowbar -- so it is the campaign
    that most wants another one enabled alongside it for variety.
    """

    display_name = "Include Blue Shift"


class IncludeTheyHunger(Toggle):
    """Include the They Hunger campaign in the seed.

    3 missions across 19 maps, ending at Episode 3, and nine weapons of its own
    from the tommy gun to the tesla gun.

    Under strict logic, Episode 1 is enterable with a melee weapon and everything
    after it expects a gun -- its own or one that travels, since Half-Life's and
    Opposing Force's work here too. Loose logic drops that as it drops every
    weapon gate.

    Its check placement has not had a pass yet. It has only three chargers in the
    whole campaign, so chargesanity barely touches it and almost all of its checks
    come from reaching maps.
    """

    display_name = "Include They Hunger"


class ExcludeIntroMissions(DefaultOnToggle):
    """Leave every campaign's scene-setting mission out of the seed.

    One per campaign that has one, dropped together:

    - **Black Mesa Inbound** (Half-Life) — the tram ride in.
    - **Incoming** (Opposing Force) — the osprey ride in.
    - **Living Quarters Outbound** (Blue Shift) — the tram ride the other way.

    They Hunger has none; it opens on Episode 1 proper. Opposing Force's Boot
    Camp is the training course rather than the intro and is not included in the 
    apworld.

    These are minutes of riding and listening with nothing to fight. Turned on,
    each one goes entirely: no regions, no checks, no unlock item, and it stops
    counting toward that campaign's Missions Required.

    Note that the campaign portal has no console for Black Mesa Inbound — Valve's
    hub room starts at Anomalous Materials — so when it is included, `!warp 0` is
    the only way to travel there. The other two have consoles like any mission.
    """

    display_name = "Exclude Intro Missions"


class IncludeBlackMesaInbound(Toggle):
    """Deprecated: use `exclude_intro_missions`.

    Kept so a YAML written before the other campaigns existed still generates the
    seed it always did. Setting it to false still drops Black Mesa Inbound, and
    only Black Mesa Inbound; `exclude_intro_missions` is the one that covers
    Opposing Force's and Blue Shift's as well.

    Hidden rather than removed: it no longer appears in the options creator or in
    a generated template, so nobody picks it up by accident, but an existing YAML
    that sets it still works instead of failing to generate.
    """

    display_name = "Include Black Mesa Inbound (deprecated)"
    visibility = Visibility.none


class RandomStartingWeapon(Toggle):
    """Start with a random melee weapon instead of the crowbar.

    Picked from the campaigns in your seed, so an Opposing Force run can open
    with its pipe wrench or combat knife and They Hunger with its spanner. With
    only Half-Life or Blue Shift enabled there is nothing but the crowbar to pick,
    and the setting changes nothing.

    Whatever it lands on replaces the crowbar completely: the crowbar is then
    refused for the rest of the run the way any ungranted weapon is, and if the
    weapon it chose was an item that item leaves the pool. You always keep the
    medkit.
    """

    display_name = "Random Starting Weapon"


class AllowRestrictedStartingWeapon(Toggle):
    """Let `random_starting_weapon` also roll a campaign's own melee weapon.

    Today that means exactly one thing: They Hunger's spanner, and only when They
    Hunger is in the seed. It is a weapon its maps register themselves rather
    than one the game ships, so it does not exist anywhere else -- start with it
    and you are empty-handed in every other campaign until a real weapon arrives.

    Logic does not model that. Anything past the point you would have picked up
    your first melee weapon is technically out of logic until you are given
    something, so this is off unless you want the rough edge.

    Nothing to do with the umbrella, the shovel or the combat knife: those are
    Half-Life's crowbar and pipe wrench wearing local models, and they travel
    everywhere.
    """

    display_name = "Allow Restricted Starting Weapon"


class ShuffleHevSuit(Toggle):
    """Shuffle the HEV suit into the item pool.

    What the item controls is armour: until it arrives, armour is held at zero
    from every source — the campaign's own loadout, batteries, charge panels and
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
    """How many deaths the lobby is forgiven before one is sent to the multiworld.

    Only outgoing DeathLinks are affected. Inside Sven Co-op the rule never
    changes: any death still gibs the whole lobby, and the death message says how
    much amnesty is left. Once the allowance runs out the next death goes out to
    the multiworld and the allowance starts again.

    0 sends every death. The default forgives four.
    """

    display_name = "DeathLink Amnesty"
    range_start = 0
    range_end = 20
    default = 4


class TrapPercentage(Range):
    """Percentage of your filler items replaced by traps.

    Three exist, all of them the whole lobby's problem, and all nuisances rather
    than punishments — none can cost you a run:

    - Scientist Trap: four scientists, one of each variant, appear around every
      player and start following them about.
    - Headcrab Trap: four headcrabs each, same idea, considerably less friendly.
    - Butterfingers Trap: everyone drops the weapon they are holding. The suit
      reissues it after half a minute if you cannot find it again.
    """

    display_name = "Trap Percentage"
    range_start = 0
    range_end = 100
    default = 0


@dataclass
class HalfLifeSvenOptions(PerGameCommonOptions):
    include_half_life: IncludeHalfLife
    include_opposing_force: IncludeOpposingForce
    include_blue_shift: IncludeBlueShift
    include_they_hunger: IncludeTheyHunger
    missions_required: MissionsRequired
    opposing_force_missions_required: OpposingForceMissionsRequired
    blue_shift_missions_required: BlueShiftMissionsRequired
    they_hunger_missions_required: TheyHungerMissionsRequired
    logic_difficulty: LogicDifficulty
    exclude_intro_missions: ExcludeIntroMissions
    include_black_mesa_inbound: IncludeBlackMesaInbound
    chargesanity: Chargesanity
    random_starting_weapon: RandomStartingWeapon
    allow_restricted_starting_weapon: AllowRestrictedStartingWeapon
    shuffle_hev_suit: ShuffleHevSuit
    shuffle_longjump: ShuffleLongJump
    trap_percentage: TrapPercentage
    start_inventory_from_pool: StartInventoryPool
    death_link: DeathLink
    death_link_amnesty: DeathLinkAmnesty
