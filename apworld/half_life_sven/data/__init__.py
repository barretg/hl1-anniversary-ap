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

# --- Campaigns ------------------------------------------------------------
#
# Sven Co-op ships four single-player conversions behind one hub, and a YAML
# toggle decides which of them a seed contains. Each is a self-contained run: its
# own missions, its own starting mission, and its own finale, which is one of the
# seed's goal conditions.

CAMPAIGNS: list[dict[str, Any]] = CAMPAIGN["campaigns"]
CAMPAIGNS_BY_KEY: dict[str, dict[str, Any]] = {c["key"]: c for c in CAMPAIGNS}

# The one a seed falls back on when a YAML manages to switch everything off.
DEFAULT_CAMPAIGN: str = CAMPAIGNS[0]["key"]

CAMPAIGN_OPTIONS: dict[str, str] = {c["key"]: c["option"] for c in CAMPAIGNS}

# Melee weapons each campaign could open a run with, as display name ->
# classnames. `random_starting_weapon` picks one from the campaigns in the seed,
# which is how you end up starting an Opposing Force run with a pipe wrench.
MELEE_STARTERS: dict[str, dict[str, list[str]]] = {
    c["key"]: c.get("melee", {}) for c in CAMPAIGNS
}

# Whatever else changes, you always get the medkit. The melee half is the part a
# seed may replace, so it is not in here.
FIXED_STARTING_WEAPONS: list[str] = [
    classname for classname in STARTING_WEAPONS
    if classname not in {
        name
        for melee in MELEE_STARTERS.values()
        for classnames in melee.values()
        for name in classnames
    }
]


def melee_starters_for(campaign_keys: list[str]) -> dict[str, list[str]]:
    """Every melee weapon the campaigns in a seed could start you with."""
    starters: dict[str, list[str]] = {}
    for key in campaign_keys:
        starters.update(MELEE_STARTERS.get(key, {}))
    return starters

# Each campaign's own `missions_required`. Independent settings, so a seed with
# several campaigns has several of these and none of them affect each other.
CAMPAIGN_MISSION_OPTIONS: dict[str, str] = {
    c["key"]: c["missions_option"] for c in CAMPAIGNS
}

GOAL_CHAPTERS: list[dict[str, Any]] = [c for c in CHAPTERS if c["is_goal"]]
UNLOCKABLE_CHAPTERS: list[dict[str, Any]] = [c for c in CHAPTERS if not c["is_goal"]]

CHAPTERS_BY_KEY: dict[str, dict[str, Any]] = {c["key"]: c for c in CHAPTERS}


def chapters_of(campaign_key: str) -> list[dict[str, Any]]:
    return [c for c in CHAPTERS if c["campaign"] == campaign_key]


def unlockable_chapters_of(campaign_key: str) -> list[dict[str, Any]]:
    """A campaign's missions minus its finale, which no item ever unlocks."""
    return [c for c in chapters_of(campaign_key) if not c["is_goal"]]


# The largest `missions_required` any single campaign could satisfy. The option's
# range has to cover the biggest campaign; a value past the end of a smaller one
# is clamped per campaign at generation time.
MAX_MISSIONS_IN_A_CAMPAIGN: int = max(
    len(unlockable_chapters_of(c["key"])) for c in CAMPAIGNS
)

# Mission 0, Black Mesa Inbound: the tram ride. It has no console in the campaign
# portal, so `!warp 0` is the only way in, and it is the one mission a YAML can
# drop from the seed entirely.
INTRO_CHAPTER: str = CHAPTERS[0]["key"]

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
# One pair per campaign, because both are counted and the counts must not run
# together. `missions_required` asks how much of *this* campaign you have
# finished, so Opposing Force progress cannot unseal Nihilanth; and the win
# condition asks for every enabled campaign's finale, which needs one name each
# rather than one name held several times.
#
# Events carry no id and never reach the datapackage, so their names are free to
# change without touching an existing seed.

MISSION_COMPLETE = "Mission Complete"
VICTORY = "Victory"


def mission_complete_event(campaign_key: str) -> str:
    return f"{CAMPAIGNS_BY_KEY[campaign_key]['name']} {MISSION_COMPLETE}"


def victory_event(campaign_key: str) -> str:
    return f"{VICTORY} ({CAMPAIGNS_BY_KEY[campaign_key]['name']})"


EVENT_ITEM_NAMES: frozenset[str] = frozenset(
    [mission_complete_event(c["key"]) for c in CAMPAIGNS]
    + [victory_event(c["key"]) for c in CAMPAIGNS]
)
