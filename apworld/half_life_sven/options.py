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

from .data import UNLOCKABLE_CHAPTERS

MAX_MISSIONS = len(UNLOCKABLE_CHAPTERS)


class MissionsRequired(Range):
    """How many missions must be completed before the Nihilanth mission opens.

    Nihilanth is never unlocked by an item -- it becomes available once this many
    other missions have been finished. The default is every other mission in the
    campaign.
    """

    display_name = "Missions Required"
    range_start = 1
    range_end = MAX_MISSIONS
    default = MAX_MISSIONS


class LogicDifficulty(Choice):
    """How much firepower logic assumes you need to clear a mission.

    strict: later missions expect a real gun, and the late game expects something
    heavier than a pistol. Safe for anyone.
    loose: only hard requirements (long jump module, HEV suit) are enforced, so
    the generator may expect you to clear Surface Tension with a crowbar.
    """

    display_name = "Logic Difficulty"
    option_strict = 0
    option_loose = 1
    default = 0


class IncludeBlackMesaInbound(DefaultOnToggle):
    """Include mission 0, Black Mesa Inbound, in the seed.

    The tram ride: no weapons, no enemies, two checks. Turn it off and the mission,
    its unlock item and its checks are left out of the seed entirely, and it stops
    counting toward Missions Required.

    Note that the campaign portal has no console for mission 0 — Valve's hub room
    starts at Anomalous Materials. When it is included, `!warp 0` in Sven Co-op
    chat is the only way to travel there.
    """

    display_name = "Include Black Mesa Inbound"


class ShuffleHevSuit(Toggle):
    """Shuffle the HEV suit into the item pool.

    While you do not have it you keep the suit's HUD but lose armour pickups, and
    the Xen missions expect it because the long jump module runs off suit power.
    """

    display_name = "Shuffle HEV Suit"


class ShuffleLongJump(Toggle):
    """Shuffle the long jump module into the item pool.

    When on, the Xen missions expect it in logic.
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
    """Percentage of filler items replaced by traps.

    Traps are not implemented yet; this is reserved so seeds generated now stay
    compatible. Leave at 0.
    """

    display_name = "Trap Percentage"
    range_start = 0
    range_end = 0
    default = 0


@dataclass
class HalfLifeSvenOptions(PerGameCommonOptions):
    missions_required: MissionsRequired
    logic_difficulty: LogicDifficulty
    include_black_mesa_inbound: IncludeBlackMesaInbound
    shuffle_hev_suit: ShuffleHevSuit
    shuffle_longjump: ShuffleLongJump
    trap_percentage: TrapPercentage
    start_inventory_from_pool: StartInventoryPool
    death_link: DeathLink
    death_link_amnesty: DeathLinkAmnesty
