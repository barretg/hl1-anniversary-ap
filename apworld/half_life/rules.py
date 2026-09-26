"""Access rules.

Two kinds of gate exist:

* **Mission unlocks** -- entering a mission needs its unlock item, except for the
  finale, which opens once `missions_required` other missions are done.
* **Weapon gates** -- expressed as "any one of this group of weapons". They are
  attached either to a mission entrance (everything in the mission inherits it)
  or to an individual location, which is how a check that sits past the point
  where a weapon becomes necessary carries that requirement.

The groups themselves live in `tools/campaigns/shared.py` and are baked into
`data/campaign.json`; this module only turns them into callables.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from BaseClasses import CollectionState

from .data import REQUIREMENT_GROUPS, campaign_of, mission_complete_event
from .options import LogicDifficulty

if TYPE_CHECKING:
    from . import HalfLifeWorld

# Gate keys used by `gates["always"]` in the campaign data. Anything else there
# is a requirement group, needed at every logic difficulty: Opposing Force's
# `barnacle_grapple`, without which Pit Worm's Nest cannot be crossed at all.
EQUIPMENT_GATES = {"longjump": "Long Jump Module", "suit": "HEV Suit"}


def always_items(world: "HalfLifeWorld", key: str) -> list[str]:
    """The items in this pool that satisfy one `always` gate."""
    if key in EQUIPMENT_GATES:
        name = EQUIPMENT_GATES[key]
        return [name] if name in world.available_item_names else []
    return group_items(world, key)


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
        if always_items(world, key):
            return False

    return True


def gate_conditions(
    world: "HalfLifeWorld", gates: dict
) -> list[Callable[[CollectionState], bool]]:
    """One condition per `strict` / `always` requirement in a gates record."""
    player = world.player
    conditions: list[Callable[[CollectionState], bool]] = []
    if world.options.logic_difficulty.value == LogicDifficulty.option_strict:
        strict = any_of(world, gates.get("strict", []))
        if strict is not None:
            conditions.append(strict)
    for key in gates.get("always", []):
        names = always_items(world, key)
        if names:
            conditions.append(
                lambda state, names=names: state.has_any(names, player)
            )
    return conditions


def all_of(
    conditions: list[Callable[[CollectionState], bool]]
) -> Callable[[CollectionState], bool] | None:
    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]

    def rule(state: CollectionState) -> bool:
        return all(condition(state) for condition in conditions)

    return rule


def map_entry_rule(
    world: "HalfLifeWorld", chapter: dict, map_name: str
) -> Callable[[CollectionState], bool] | None:
    """Rule for walking on into one of a mission's later maps."""
    return all_of(gate_conditions(world, chapter.get("map_gates", {}).get(map_name, {})))


def chapter_entry_rule(
    world: "HalfLifeWorld", chapter: dict
) -> Callable[[CollectionState], bool] | None:
    """Rule for the Hub -> first map of a mission entrance."""
    player = world.player
    conditions = gate_conditions(world, chapter["gates"])

    if chapter["is_goal"]:
        # The seal: no item opens the finale, only finished missions of its own
        # game do.
        campaign = campaign_of(chapter)
        required = world.missions_required_by_campaign[campaign]
        event = mission_complete_event(campaign)
        conditions.append(
            lambda state, count=required, event=event: state.has(event, player, count)
        )
    else:
        unlock = world.unlock_item_for_chapter[chapter["key"]]
        conditions.append(lambda state, name=unlock: state.has(name, player))

    return all_of(conditions)


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
