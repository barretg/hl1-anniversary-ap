"""Loader for the generated campaign data.

`campaign.json` is produced by `tools/build_campaign_data.py` straight from the
Sven Co-op BSPs. Everything downstream -- the world, the client, and the
AngelScript plugin's `checkdata.json` -- reads it, so there is exactly one place
where a location id is defined.
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
STARTING_WEAPONS: list[str] = CAMPAIGN["starting_weapons"]

GOAL_CHAPTER: dict[str, Any] = next(c for c in CHAPTERS if c["is_goal"])
UNLOCKABLE_CHAPTERS: list[dict[str, Any]] = [c for c in CHAPTERS if not c["is_goal"]]

CHAPTERS_BY_KEY: dict[str, dict[str, Any]] = {c["key"]: c for c in CHAPTERS}

# Items that only enter the pool when the matching YAML toggle is on.
OPTIONAL_ITEM_NAMES = {"HEV Suit": "shuffle_hev_suit", "Long Jump Module": "shuffle_longjump"}

MISSION_COMPLETE = "Mission Complete"
VICTORY = "Victory"
