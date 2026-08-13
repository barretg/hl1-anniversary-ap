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

# Missions an item can open: everything but the finale. This is the list the
# unlock items are built from, so a mission leaving it is a mission with no item
# anywhere in the pool.
UNLOCKABLE_CHAPTERS: list[dict[str, Any]] = [
    c for c in CHAPTERS if not c["is_goal"]
]

# The ceiling for `missions_required`: the missions that can be finished before
# the finale's seal opens, which is every mission except the finale itself.
MAX_MISSIONS: int = len(UNLOCKABLE_CHAPTERS)

# Items that only enter the pool when the matching YAML toggle is on.
OPTIONAL_ITEM_NAMES = {"HEV Suit": "shuffle_hev_suit", "Long Jump Module": "shuffle_longjump"}

# Of those, the ones that go back to behaving exactly as Half-Life does when the
# toggle is off, rather than being handed over at the start of the run.
#
# The two are not alike. Nothing but the HEV Suit item ever turns armour on, so an
# unshuffled suit has to be granted up front or the player has no armour for the
# whole run. The long jump module is different: the campaign gives it out itself,
# in Forget About Freeman and everything after it, so leaving it entirely alone is
# both possible and what "not shuffled" ought to mean. Granting it up front put a
# module in the player's legs ten missions before Half-Life would have.
VANILLA_WHEN_UNSHUFFLED = frozenset({"Long Jump Module"})

# Trigger type of the health / HEV charger checks, switched off by `chargesanity`.
CHARGER_TRIGGER = "charger"

# --- Event items ----------------------------------------------------------
#
# Events carry no id and never reach the datapackage, so their names are free to
# change without touching an existing seed.

MISSION_COMPLETE = "Mission Complete"
VICTORY = "Victory"

EVENT_ITEM_NAMES: frozenset[str] = frozenset([MISSION_COMPLETE, VICTORY])
