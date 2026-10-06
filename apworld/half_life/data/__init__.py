"""Loader for the generated campaign data.

`campaign.json` is produced by `tools/build_campaign_data.py` straight from the
retail Half-Life BSPs. Everything downstream -- the world, the client, and the
mod's `checkdata.txt` -- reads it, so there is exactly one place where a location
id is defined.
"""

from __future__ import annotations

import json
import pkgutil
from typing import Any

DATA_FILE = "campaign.json"


def load_campaign() -> dict[str, Any]:
    """Read campaign.json.

    `pkgutil.get_data` rather than a filesystem read: when the world is shipped
    as a zipped `.apworld`, `__file__` points inside the archive and `open()`
    fails.
    """
    raw = pkgutil.get_data(__name__, DATA_FILE)
    if raw is None:
        raise FileNotFoundError(f"{__name__}/{DATA_FILE} is missing from the world package")
    return json.loads(raw.decode("utf-8"))


CAMPAIGN: dict[str, Any] = load_campaign()

CHAPTERS: list[dict[str, Any]] = CAMPAIGN["chapters"]
ITEMS: list[dict[str, Any]] = CAMPAIGN["items"]
LOCATIONS: list[dict[str, Any]] = CAMPAIGN["locations"]
REQUIREMENT_GROUPS: dict[str, list[str]] = CAMPAIGN["requirement_groups"]

# What the run opens with, and what the game must therefore never take away.
# Retail has one melee weapon, so this is a constant rather than a per-seed roll.
STARTING_WEAPONS: list[str] = CAMPAIGN["starting_weapons"]

CHAPTERS_BY_KEY: dict[str, dict[str, Any]] = {c["key"]: c for c in CHAPTERS}

# The finale. No item unlocks it: it opens once `missions_required` other
# missions are done, and finishing it wins the seed.
GOAL_CHAPTER: str = CAMPAIGN["goal_chapter"]

# The tram ride in, dropped by `exclude_intro_missions`.
INTRO_CHAPTER: str = CAMPAIGN["intro_chapter"]

# The games this world can include, in mission-numbering order: Half-Life
# first. Data built before there was more than one has no list, and is
# Half-Life alone.
HALF_LIFE = "half_life"
CAMPAIGNS: list[dict[str, Any]] = CAMPAIGN.get("campaigns") or [{
    "key": HALF_LIFE, "name": "Half-Life", "goal_chapter": GOAL_CHAPTER,
    "intro_chapter": INTRO_CHAPTER, "short": "hl", "armour_item": "HEV Suit",
    "melee": list(STARTING_WEAPONS),
}]
CAMPAIGNS_BY_KEY: dict[str, dict[str, Any]] = {c["key"]: c for c in CAMPAIGNS}


def campaign_of(entry: dict[str, Any]) -> str:
    """The game a chapter or item belongs to. Absent means Half-Life."""
    return entry.get("campaign", HALF_LIFE)


# Missions an item can open: everything but the finales. This is the list the
# unlock items are built from, so a mission leaving it is a mission with no item
# anywhere in the pool.
UNLOCKABLE_CHAPTERS: list[dict[str, Any]] = [
    c for c in CHAPTERS if not c["is_goal"]
]

# The ceiling for each game's `missions_required`: the missions that can be
# finished before its finale's seal opens.
MAX_MISSIONS_BY_CAMPAIGN: dict[str, int] = {
    c["key"]: len([ch for ch in UNLOCKABLE_CHAPTERS if campaign_of(ch) == c["key"]])
    for c in CAMPAIGNS
}

# Half-Life's, which is what `missions_required` has always meant.
MAX_MISSIONS: int = MAX_MISSIONS_BY_CAMPAIGN[HALF_LIFE]

# Items that only enter the pool when the matching YAML toggle is on. Each
# game's armour item follows the HEV suit's toggle, and only exists in a seed
# that includes its game.
OPTIONAL_ITEM_NAMES = {
    "HEV Suit": "shuffle_hev_suit",
    "Long Jump Module": "shuffle_longjump",
    "PCV": "shuffle_hev_suit",
    "Security Armor": "shuffle_hev_suit",
    "Flashlight": "shuffle_flashlight",
    "Night Vision Goggles": "shuffle_flashlight",
}

# Optional items used on more than their own game's maps: the flashlight is
# Half-Life's and Blue Shift's both, so either game brings it.
OPTIONAL_ITEM_CAMPAIGNS: dict[str, tuple[str, ...]] = {
    "Flashlight": ("half_life", "blue_shift"),
}

# Abilities that only exist when their YAML toggle is on. Unlike the equipment
# above, off means the ability is absent, not granted.
ABILITY_ITEM_NAMES: dict[str, str] = {"Melee Throw": "melee_throw"}

# Several copies, each a step up `sv_airaccelerate`. Not in the table above,
# which places one copy of each.
AIR_ACCELERATE_ITEM = "Progressive Air Acceleration"
# Past this, more air acceleration buys next to nothing.
AIR_ACCELERATE_CAP = 150


def _air_accelerate_ladder() -> list[int]:
    """Every value the items can stop at, 0 to the cap: steps of 2 at first,
    each about a tenth longer than the last."""
    ladder = [0]
    step = 2.0
    while ladder[-1] < AIR_ACCELERATE_CAP:
        ladder.append(min(ladder[-1] + round(step), AIR_ACCELERATE_CAP))
        step *= 1.1
    return ladder


AIR_ACCELERATE_LADDER: list[int] = _air_accelerate_ladder()


def air_accelerate_bounds(minimum: int, maximum: int) -> tuple[int, int]:
    """The two options clamped to 0..cap, swapped if given the wrong way round."""
    low, high = (max(0, min(int(v), AIR_ACCELERATE_CAP)) for v in (minimum, maximum))
    return min(low, high), max(low, high)


def air_accelerate_steps(minimum: int, maximum: int) -> list[int]:
    """What each item raises air acceleration to, in order, from the minimum.

    The ladder values strictly between the bounds, then the maximum itself: the
    count rounds up to the ladder, and the last item lands exactly on the
    maximum rather than on the ladder value past it. Equal bounds need no items.
    """
    low, high = air_accelerate_bounds(minimum, maximum)
    if low == high:
        return []
    return [v for v in AIR_ACCELERATE_LADDER if low < v < high] + [high]


def air_accelerate_value(minimum: int, maximum: int, received: int) -> int:
    """Air acceleration with `received` items: the minimum with none, the
    maximum once every item the seed placed has arrived."""
    steps = air_accelerate_steps(minimum, maximum)
    if received <= 0 or not steps:
        return air_accelerate_bounds(minimum, maximum)[0]
    return steps[min(received, len(steps)) - 1]

# Of those, the ones that stay where Half-Life puts them when the toggle is off,
# rather than being handed over at the start of the run: item -> the location it
# is locked to.
#
# The two are not alike. Nothing but the HEV Suit item ever turns armour on, so an
# unshuffled suit has to be granted up front or the player has no armour for the
# whole run. The long jump module the campaign hands out itself, in Forget About
# Freeman, so granting it up front would put it in the player's legs ten missions
# early. It is still a real item sent back by the server, though, not a pickup
# left to the game: every mission starts from the hub, so a module that only ever
# existed in one playthrough's inventory was gone again by Xen.
VANILLA_WHEN_UNSHUFFLED: dict[str, str] = {"Long Jump Module": "First Long Jump Module"}

# Trigger type of the health / HEV charger checks, switched off by `chargesanity`.
CHARGER_TRIGGER = "charger"

# Trigger type of the Anomalous Materials microwave check, switched on by
# `include_microwave`.
MICROWAVE_TRIGGER = "microwave"

# --- Event items ----------------------------------------------------------
#
# Events carry no id and never reach the datapackage, so their names are free to
# change without touching an existing seed.

MISSION_COMPLETE = "Mission Complete"
VICTORY = "Victory"


def mission_complete_event(campaign: str) -> str:
    """What finishing one of this game's missions grants. Each finale counts
    only its own game's missions, so each game has its own event."""
    if campaign == HALF_LIFE:
        return MISSION_COMPLETE
    return f"{CAMPAIGNS_BY_KEY[campaign]['name']}: {MISSION_COMPLETE}"


EVENT_ITEM_NAMES: frozenset[str] = frozenset(
    [VICTORY, *(mission_complete_event(c["key"]) for c in CAMPAIGNS)]
)
