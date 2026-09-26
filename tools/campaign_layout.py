"""Hand-authored campaign facts that cannot be derived from the BSPs.

Everything that *can* be read out of the maps (which weapons exist where, which
monsters are present, where the chargers are) is derived in
`build_campaign_data.py`. The editorial decisions -- chapter grouping and names,
which weapon pickups map to which Archipelago item, and the logic gates -- live
in the `campaigns` package, one module per game plus the facts they share.

This module re-exports Half-Life's names from there, for the code and tests that
imported them before there was more than one campaign. Edit the package, not
this file.
"""

from __future__ import annotations

from campaigns import *  # noqa: F401,F403
from campaigns import CLASSNAME_TO_ITEM  # noqa: F401
from campaigns.half_life import (  # noqa: F401
    CHAPTER_GATES,
    CHAPTER_KEYS,
    CHAPTER_NAMES,
    CHAPTERS,
    GOAL_CHAPTER,
    INTRO_CHAPTER,
    OPTIONAL_ITEMS,
    STARTING_WEAPONS,
    UNRANDOMISED_WEAPON_LOCATIONS,
    UNREACHABLE_CHARGERS,
    WEAPON_ITEMS,
)
