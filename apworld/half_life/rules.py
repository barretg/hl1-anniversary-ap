"""Access rules.

Two kinds of gate exist:

* **Mission unlocks** -- entering a mission needs its unlock item, except for the
  finale, which opens once `missions_required` other missions are done.
* **Weapon gates** -- expressed as "any one of this group of weapons". They are
  attached either to a mission entrance (everything in the mission inherits it)
  or to an individual location, which is how a check that sits past the point
  where a weapon becomes necessary carries that requirement.

The groups themselves live in `tools/campaign_layout.py` and are baked into
`data/campaign.json`; this module only turns them into callables.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from BaseClasses import CollectionState

from .data import MISSION_COMPLETE, REQUIREMENT_GROUPS
from .options import LogicDifficulty

if TYPE_CHECKING:
    from . import HalfLifeWorld

# Gate keys used by `gates["always"]` in the campaign data.
EQUIPMENT_GATES = {"longjump": "Long Jump Module", "suit": "HEV Suit"}


def group_items(world: "HalfLifeWorld", group: str) -> list[str]:
    """The items satisfying a requirement group that are actually in this pool."""
    return [name for name in REQUIREMENT_GROUPS[group] if name in world.available_item_names]


def any_of(
    world: "HalfLifeWorld", groups: list[str]
) -> Callable[[CollectionState], bool] | None:
    """Require at least one item from each named group."""
    requirements = [group_items(world, group) for group in groups]
    requirements = [names for names in requirements if names]
    if not requirements:
        return None
    player = world.player

    def rule(state: CollectionState) -> bool:
        return all(state.has_any(names, player) for names in requirements)

    return rule


def chapter_is_startable(world: "HalfLifeWorld", chapter: dict) -> bool:
    """Can this mission be entered with nothing but its own unlock item?

    The mission handed out at the start has to be one of these. Every location in
    the game sits behind a mission entrance, so if the one open mission also
    demands a real weapon or the long jump module, *nothing* is reachable in
    sphere one: fill has no legal spot for the item that would open sphere two,
    burns its swap budget, and dies with "no more spots to place N items.
    Remaining locations are invalid".

    Called before the pool is built, so it reads `available_item_names` -- a gate
    naming equipment nobody will ever receive is not a gate.
    """
    gates = chapter["gates"]

    if world.options.logic_difficulty.value == LogicDifficulty.option_strict:
        if any(group_items(world, group) for group in gates.get("strict", [])):
            return False

    for key in gates.get("always", []):
        if EQUIPMENT_GATES[key] in world.available_item_names:
            return False

    return True


def chapter_entry_rule(
    world: "HalfLifeWorld", chapter: dict
) -> Callable[[CollectionState], bool] | None:
    """Rule for the Hub -> first map of a mission entrance."""
    player = world.player
    conditions: list[Callable[[CollectionState], bool]] = []

    gates = chapter["gates"]
    if world.options.logic_difficulty.value == LogicDifficulty.option_strict:
        strict = any_of(world, gates.get("strict", []))
        if strict is not None:
            conditions.append(strict)

    for key in gates.get("always", []):
        item_name = EQUIPMENT_GATES[key]
        if item_name in world.available_item_names:
            conditions.append(lambda state, name=item_name: state.has(name, player))

    if chapter["is_goal"]:
        # The seal: no item opens the finale, only finished missions do.
        required = world.missions_required
        conditions.append(
            lambda state, count=required: state.has(MISSION_COMPLETE, player, count)
        )
    else:
        unlock = world.unlock_item_for_chapter[chapter["key"]]
        conditions.append(lambda state, name=unlock: state.has(name, player))

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]

    def rule(state: CollectionState) -> bool:
        return all(condition(state) for condition in conditions)

    return rule


def location_rule(
    world: "HalfLifeWorld", entry: dict
) -> Callable[[CollectionState], bool] | None:
    """Extra requirement on a single location, e.g. a boss that needs real damage."""
    requirement = entry.get("requires")
    if not requirement:
        return None
    if world.options.logic_difficulty.value != LogicDifficulty.option_strict:
        return None  # loose logic drops soft weapon gates
    return any_of(world, [requirement])
