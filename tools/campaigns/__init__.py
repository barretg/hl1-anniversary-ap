"""Every campaign this world can include, and the facts they share.

`CAMPAIGNS` is the registry, in the order their missions are numbered: Half-Life
first, so its chapter indices stay 0..17 and `ap_warp <n>` means what it always
has. A new game is a module that builds a `Campaign` and a line here.
"""

from __future__ import annotations

from .base import COMPLETE_ON, Campaign
from .blue_shift import BLUE_SHIFT
from .half_life import HALF_LIFE
from .opposing_force import OPPOSING_FORCE
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

CAMPAIGNS: list[Campaign] = [HALF_LIFE, OPPOSING_FORCE, BLUE_SHIFT]

CAMPAIGNS_BY_KEY: dict[str, Campaign] = {c.key: c for c in CAMPAIGNS}

# Every campaign the tools know. The same as CAMPAIGNS today; kept as its own
# name so a game can be scanned and built with `--only ... --out` before it is
# added to the committed data.
KNOWN_CAMPAIGNS: list[Campaign] = CAMPAIGNS

KNOWN_CAMPAIGNS_BY_KEY: dict[str, Campaign] = {c.key: c for c in KNOWN_CAMPAIGNS}


def weapon_items(campaigns: list[Campaign] = CAMPAIGNS) -> dict[str, list[str]]:
    """Every weapon item the given campaigns bring, in registry order."""
    return {name: cls for c in campaigns for name, cls in c.weapons.items()}


def requirement_groups(campaigns: list[Campaign] = CAMPAIGNS) -> dict[str, list[str]]:
    """The shared logic groups plus what the given campaigns add to them."""
    groups = {name: list(items) for name, items in REQUIREMENT_GROUPS.items()}
    for campaign in campaigns:
        for name, items in campaign.groups.items():
            members = groups.setdefault(name, [])
            members.extend(item for item in items if item not in members)
    return groups


# Every classname the game must refuse until the matching item arrives.
#
# The melee weapons are in here too. Whichever one starts the run is always
# allowed, because starting weapons are checked first; the others are items and
# are refused until they arrive.
CLASSNAME_TO_ITEM: dict[str, str] = {}
for _campaign in CAMPAIGNS:
    for _table in (_campaign.weapons, _campaign.optional_items,
                   _campaign.unrandomised_weapons):
        for _item, _classnames in _table.items():
            for _classname in _classnames:
                # First campaign wins. `item_suit` is the HEV Suit to Half-Life
                # and the PCV to Opposing Force; the game never gates the suit
                # pickup itself (it gates armour per campaign), so the older
                # meaning stays in the table.
                CLASSNAME_TO_ITEM.setdefault(_classname, _item)

# Every starting-melee candidate, `{item name: classname}`, in registry order:
# the crowbar, then Shephard's knife and wrench. One of them starts the run; the
# rest are items, gated like any weapon.
MELEE_ITEMS: dict[str, str] = {}
for _campaign in CAMPAIGNS:
    for _item, _classnames in _campaign.unrandomised_weapons.items():
        for _classname in _classnames:
            if _classname in _campaign.melee:
                MELEE_ITEMS.setdefault(_item, _classname)
