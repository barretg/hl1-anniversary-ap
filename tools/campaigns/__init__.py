"""Every campaign this world can include, and the facts they share.

`CAMPAIGNS` is the registry, in the order their missions are numbered: Half-Life
first, so its chapter indices stay 0..17 and `ap_warp <n>` means what it always
has. A new game is a module that builds a `Campaign` and a line here.
"""

from __future__ import annotations

from .base import COMPLETE_ON, Campaign
from .half_life import HALF_LIFE
from .shared import (  # re-exported: the facts every campaign shares
    CHARGER_CLASSNAMES,
    CHARGER_POSITION_GRID,
    ENABLED_LOCATION_TYPES,
    EXPLOSIVES,
    HEALING_POOL_CLASSNAMES,
    HEAVY_WEAPONS,
    HUB_BUTTON_PREFIX,
    HUB_BUTTON_SUFFIX,
    HUB_ENTRANCE_CLASSNAMES,
    HUB_MAP,
    IGNORED_MONSTERS,
    ITEM_ID_BASE,
    KILL_MILESTONE_FRACTIONS,
    LOCATION_ID_BASE,
    MIN_LOCATIONS_PER_MAP,
    NOTABLE_MONSTERS,
    RANGED_WEAPONS,
    REQUIREMENT_GROUPS,
    UNDERWATER_WEAPONS,
    hub_button_index,
)

CAMPAIGNS: list[Campaign] = [HALF_LIFE]

CAMPAIGNS_BY_KEY: dict[str, Campaign] = {c.key: c for c in CAMPAIGNS}


def weapon_items(campaigns: list[Campaign] = CAMPAIGNS) -> dict[str, list[str]]:
    """Every weapon item the given campaigns bring, in registry order."""
    return {name: cls for c in campaigns for name, cls in c.weapons.items()}


# Every classname the game must refuse until the matching item arrives.
#
# The crowbar is in here despite never being an item. It is also in
# STARTING_WEAPONS, and starting weapons are checked first, so in practice it is
# always allowed -- the entry exists so that the table is the single answer to
# "is this pickup gated", with no classname falling through it unlisted.
CLASSNAME_TO_ITEM: dict[str, str] = {
    classname: item
    for campaign in CAMPAIGNS
    for table in (campaign.weapons, campaign.optional_items,
                  campaign.unrandomised_weapons)
    for item, classnames in table.items()
    for classname in classnames
}
