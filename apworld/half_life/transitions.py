"""Transitions mode: one contiguous world built from shuffled level transitions.

See `.claude/TRANSITION_RANDO.md`, section 6. In outline:

* One region per map segment (`"<map>"`, or `"<map>/<segment>"` for a map
  `MAP_LOGIC` splits). A map not in `MAP_LOGIC` is one segment, gated by its
  chapter's existing gates.
* Every transition is an exit and an arrival (a GER target) of the same name
  in its segment, so GER's coupled mode pairs them 1:1 for the whole seed.
* A map's gates sit on everything inside it (its locations and its exits)
  rather than on the way in, since the way in is only known once GER has run.
  Reaching a map without its items therefore opens nothing.
* A spine, the forward route, is drawn first and pre-connected; GER pairs what
  is left in `connect_entrances`.
* The ending scenes are cut: no regions, no locations, and the changelevels
  into and out of them are not transitions here. Each boss chapter grants
  `Victory` in its boss map, and the final boss's chapter is sealed until the
  others are won.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from BaseClasses import CollectionState, Entrance, EntranceType, Region
from Options import OptionError

from .data import (
    CAMPAIGNS, CAMPAIGNS_BY_KEY, CHAPTERS, CHAPTERS_BY_KEY, LOCATIONS, MAP_LOGIC,
    TRANSITIONS, VICTORY, campaign_of, mission_complete_event, trigger_excluded,
)
from .locations import HalfLifeLocation, location_table, locations_by_map, weapon_sources
from .options import GenerationDifficulty, LogicDifficulty, MapShuffle
from .rules import all_of, always_items, gate_conditions, group_items, location_rule

if TYPE_CHECKING:
    from . import HalfLifeWorld

MENU = "Menu"

TRANSITIONS_BY_ID: dict[str, dict[str, Any]] = {t["id"]: t for t in TRANSITIONS}
ENDING_MAPS: frozenset[str] = frozenset(
    c["ending_map"] for c in CAMPAIGNS if c.get("ending_map"))
MAP_CHAPTER: dict[str, str] = {m: c["key"] for c in CHAPTERS for m in c["maps"]}
MAP_ORDER: dict[str, int] = {m: i for i, m in enumerate(m for c in CHAPTERS for m in c["maps"])}

# Blue Shift's leap needs the generators (`ba_power2`) and the battery sent up
# (`ba_power1`) first (3.4). Both are ordinary maps anywhere in the world.
BOSS_NEEDS_MAPS: dict[str, tuple[str, ...]] = {"ba_teleport2": ("ba_power1", "ba_power2")}

# Section 6.3: a map one tier out of place is a tenth as likely as one in it.
TIER_FALLOFF = math.log(10)

# GER randomization groups.
GROUP_DEFAULT = 0


def chapter_tier(chapter: dict) -> int:
    """How deep into a run a chapter belongs, from its old chapter gates, until
    discovery gives its maps their own (3.3)."""
    gates = chapter.get("gates", {})
    strict, always = set(gates.get("strict", [])), set(gates.get("always", []))
    if always & {"longjump", "suit"}:
        return 5
    if "heavy" in strict or "tau_cannon" in strict:
        return 4
    if "explosives" in strict or always - {"longjump", "suit"}:
        return 3
    if strict:
        return 2
    return 1


def map_tier(map_name: str) -> int:
    logic = MAP_LOGIC.get(map_name, {})
    if "tier" in logic:
        return int(logic["tier"])
    return chapter_tier(CHAPTERS_BY_KEY[MAP_CHAPTER[map_name]])


def segments_of(map_name: str) -> list[str]:
    return list(MAP_LOGIC.get(map_name, {}).get("segments", [])) or [""]


def region_name(map_name: str, segment: str = "") -> str:
    return f"{map_name}/{segment}" if segment else map_name


def transition_region(tid: str) -> str:
    t = TRANSITIONS_BY_ID[tid]
    logic = MAP_LOGIC.get(t["map"])
    if logic:
        return region_name(t["map"], logic["transitions"][tid])
    return t["map"]


def weight(tier: float, target: float) -> float:
    distance = abs(tier - target)
    return 1.0 if distance <= 0.5 else math.exp(-TIER_FALLOFF * (distance - 0.5))


@dataclass
class Plan:
    """What `create_regions` decided, for `connect_entrances` and slot data."""
    maps: list[str] = field(default_factory=list)
    pool: list[str] = field(default_factory=list)
    inert: list[str] = field(default_factory=list)
    start_map: str = ""
    bosses: list[str] = field(default_factory=list)       # boss chapter keys
    final_boss: str = ""
    ending_map: str = ""
    spine: list[str] = field(default_factory=list)        # node names
    fixed: list[tuple[str, str]] = field(default_factory=list)
    # Transitions GER pairs, by group.
    groups: dict[str, int] = field(default_factory=dict)
    # Pairs once everything is connected, both orders listed once.
    pairs: list[tuple[str, str]] = field(default_factory=list)
    # A transition left over in an odd group: one way into another's arrival.
    one_way: dict[str, str] = field(default_factory=dict)
    backtrack_orbs: dict[str, str] = field(default_factory=dict)
    # Route nodes (maps, or chapter keys) played end to start (allow_reverse).
    reversed: list[str] = field(default_factory=list)


# -- helpers on the transition table -------------------------------------------


def vanilla_partner(tid: str) -> str:
    return TRANSITIONS_BY_ID[tid].get("partner", "")


def is_forward(t: dict) -> bool:
    """Leads to a map later in the campaigns' order."""
    return MAP_ORDER.get(t["to"], -1) > MAP_ORDER[t["map"]]


def entered_reversed(plan: Plan, node_of: Callable[[str], str]) -> list[str]:
    """Route nodes entered through a way forwards: played end to start."""
    into = {node_of(b): is_forward(TRANSITIONS_BY_ID[b]) for _, b in plan.fixed}
    return [n for n in plan.spine[1:] if into.get(n)]


def cross_chapter(t: dict) -> bool:
    return MAP_CHAPTER.get(t["to"]) != MAP_CHAPTER[t["map"]]


# -- the plan --------------------------------------------------------------------


def make_plan(world: "HalfLifeWorld") -> Plan:
    """Which maps and transitions make the world, the start, the bosses and the
    spine. Under the tracker, all of it from the seed's slot data."""
    plan = Plan()
    passthrough = world.tracker_passthrough or {}
    chapters = [CHAPTERS_BY_KEY[k] for k in world.transition_chapters]
    plan.maps = [m for c in chapters for m in c["maps"] if m not in ENDING_MAPS]
    in_world = set(plan.maps)
    # A dead transition (one nothing fires and no one reaches) stays vanilla.
    plan.pool = [t["id"] for t in TRANSITIONS
                 if t["map"] in in_world and t["to"] not in ENDING_MAPS and not t.get("dead")]
    plan.bosses = [c["key"] for c in chapters if c["is_goal"]]

    if passthrough.get("progression_mode") == "transitions":
        plan.start_map = passthrough["start_map"]
        plan.final_boss = passthrough.get("final_boss", "")
        plan.ending_map = passthrough.get("ending_map", "")
        plan.inert = list(passthrough.get("inert_transitions", []))
        plan.one_way = dict(passthrough.get("one_way_transitions", {}))
        plan.backtrack_orbs = dict(passthrough.get("backtrack_orbs", {}))
        plan.reversed = list(passthrough.get("reversed", []))
        listed = {a for pair in passthrough.get("transition_pairs", []) for a in pair}
        plan.fixed = [tuple(p) for p in passthrough.get("transition_pairs", [])]
        # A transition the seed left at its vanilla partner is not listed.
        for tid in plan.pool:
            partner = vanilla_partner(tid)
            if (tid not in listed and tid not in plan.inert and tid not in plan.one_way
                    and partner in plan.pool and partner not in listed and tid < partner):
                plan.fixed.append((tid, partner))
        return plan

    rng = world.random
    standard = world.options.generation_difficulty == GenerationDifficulty.option_standard
    plan.final_boss = rng.choice(plan.bosses)
    endings = [CAMPAIGNS_BY_KEY[k]["ending_map"] for k in world.campaigns
               if CAMPAIGNS_BY_KEY[k].get("ending_map")]
    plan.ending_map = rng.choice(endings) if endings else ""
    plan.start_map = pick_start(world, chapters, standard)

    # The start's way back into an excluded intro does nothing (section 1).
    if standard and world.options.exclude_intro_missions:
        intro_maps = {m for k in world.campaigns
                      for m in CHAPTERS_BY_KEY[CAMPAIGNS_BY_KEY[k]["intro_chapter"]]["maps"]}
        plan.inert = [tid for tid in plan.pool if TRANSITIONS_BY_ID[tid]["map"] == plan.start_map
                      and TRANSITIONS_BY_ID[tid]["to"] in intro_maps]
    live = [tid for tid in plan.pool if tid not in plan.inert]

    shuffle = world.options.map_shuffle.value
    if shuffle == MapShuffle.option_total:
        plan_total(world, plan, live, standard)
    else:
        plan_chapters(world, plan, chapters, live, standard, shuffle)
    return plan


# A chaotic start needs this many checks open with nothing in hand in its own
# map: fill puts the first items there, and a start of one leaves it nowhere.
MIN_START_LOCATIONS = 4


def startable(world: "HalfLifeWorld", map_name: str, roomy: bool = False) -> bool:
    """A start whose own gates are empty, so sphere one is not (6.4)."""
    if region_gate(world, map_name, seal=False):
        return False
    if not roomy:
        return True
    free = [e for e in locations_by_map.get(map_name, [])
            if "sources" not in e and not trigger_excluded(e, world.excluded_triggers)
            and location_rule(world, e) is None]
    return len(free) >= MIN_START_LOCATIONS


def pick_start(world: "HalfLifeWorld", chapters: list[dict], standard: bool) -> str:
    rng = world.random
    if standard:
        firsts = []
        for key in world.campaigns:
            mine = [c for c in chapters if campaign_of(c) == key and not c["is_goal"]]
            if mine and startable(world, mine[0]["maps"][0]):
                firsts.append(mine[0]["maps"][0])
        if firsts:
            return rng.choice(firsts)
    candidates = [m for c in chapters if not c["is_goal"] for m in c["maps"]
                  if m not in ENDING_MAPS and startable(world, m, roomy=True)]
    candidates = candidates or [m for c in chapters if not c["is_goal"] for m in c["maps"]
                                if m not in ENDING_MAPS and startable(world, m)]
    if not candidates:
        raise OptionError(f"{world.player_name}: no included map can be started with "
                          "nothing in hand; include an earlier chapter")
    return rng.choice(candidates)


def locked_needs(world: "HalfLifeWorld", map_name: str) -> list[set[str]]:
    """For each of a map's gates only a locked item satisfies (equipment left
    at its vanilla spot), the maps holding that item's copies. The map can only
    come after one of them."""
    locked: dict[str, set[str]] = {}
    for item, location in world.vanilla_placements.items():
        entry = location_table[location]
        sources = weapon_sources(entry, world.excluded_chapters, world.ally_weapon_drops)
        locked[item] = {s["map"] for s in sources} or {entry["map"]}
    chapter = CHAPTERS_BY_KEY[MAP_CHAPTER[map_name]]
    needs: list[set[str]] = []
    for gates in (chapter["gates"], chapter.get("map_gates", {}).get(map_name, {})):
        keys = [("always", k) for k in gates.get("always", [])]
        if world.options.logic_difficulty.value == LogicDifficulty.option_strict:
            keys += [("strict", k) for k in gates.get("strict", [])]
        for kind, key in keys:
            items = always_items(world, key) if kind == "always" else group_items(world, key)
            if items and all(i in locked for i in items):
                needs.append(set().union(*(locked[i] for i in items)))
    return needs


def spine_valid(world: "HalfLifeWorld", order: list[list[str]], outside: set[str]) -> bool:
    """Every node's locked-item needs met by a node before it, or by a map
    off the spine that GER will place with logic."""
    seen = set(outside)
    for maps in order:
        for map_name in maps:
            if any(not (need & seen) for need in locked_needs(world, map_name)):
                return False
        seen.update(maps)
    return True


def draw_spine(world: "HalfLifeWorld", nodes: list[str], tier: Callable[[str], float],
               late: set[str], standard: bool, maps_of: Callable[[str], list[str]],
               start: str, final: str, outside: set[str] = frozenset()) -> list[str]:
    """`draw_order`, drawn again until the order is one the locked items allow."""
    for _ in range(200):
        order = draw_order(world, nodes, tier, late, standard)
        if spine_valid(world, [maps_of(n) for n in [start, *order, final]], set(outside)):
            return order
    raise OptionError(f"{world.player_name}: no route through the included chapters "
                      "reaches each one after the equipment it needs; shuffle that "
                      "equipment or include the chapters that hold it")


def draw_order(world: "HalfLifeWorld", nodes: list[str], tier: Callable[[str], float],
               late: set[str], standard: bool) -> list[str]:
    """Spine positions 1..n for `nodes` (6.3): weighted by tier under standard,
    uniform under chaotic. Nodes in `late` only go in the second half."""
    rng = world.random
    remaining = list(nodes)
    order: list[str] = []
    total = len(nodes) + 2  # the start before, the final boss after
    top = max([tier(n) for n in nodes] + [1.0])
    for position in range(1, total - 1):
        slots_left = total - 1 - position
        late_left = [n for n in remaining if n in late]
        if len(late_left) >= slots_left:
            pool = late_left
        else:
            pool = [n for n in remaining if n not in late or position >= total / 2]
        if not standard:
            choice = rng.choice(pool)
        else:
            target = 1 + (top - 1) * position / max(total - 1, 1)
            choice = rng.choices(pool, weights=[weight(tier(n), target) for n in pool])[0]
        remaining.remove(choice)
        order.append(choice)
    return order


def plan_chapters(world: "HalfLifeWorld", plan: Plan, chapters: list[dict], live: list[str],
                  standard: bool, shuffle: int) -> None:
    """off, area and chapter_maps: chapters keep their own maps in order, and
    the transitions between chapters make the route."""
    by_chapter: dict[str, list[str]] = {}
    internal: dict[str, list[str]] = {}
    for tid in live:
        t = TRANSITIONS_BY_ID[tid]
        if cross_chapter(t):
            by_chapter.setdefault(MAP_CHAPTER[t["map"]], []).append(tid)
        else:
            internal.setdefault(MAP_CHAPTER[t["map"]], []).append(tid)

    start = MAP_CHAPTER[plan.start_map]
    others = [c["key"] for c in chapters if c["key"] not in (start, plan.final_boss)]
    middle_bosses = {k for k in others if CHAPTERS_BY_KEY[k]["is_goal"]}
    def maps_of(key: str) -> list[str]:
        return [m for m in CHAPTERS_BY_KEY[key]["maps"] if m in plan.maps]

    if shuffle == MapShuffle.option_off:
        order = others  # vanilla order across the included games
    else:
        order = draw_spine(world, others, lambda k: chapter_tier(CHAPTERS_BY_KEY[k]),
                           middle_bosses if standard else set(), standard, maps_of,
                           start, plan.final_boss)
    plan.spine = [start, *order, plan.final_boss]

    # Ways in and out of each chapter, preferring the vanilla ones: in through
    # a transition back to an earlier map, out through one forward.
    spare: dict[str, list[str]] = {k: list(v) for k, v in by_chapter.items()}

    chain = [k for k in plan.spine if k not in middle_bosses]
    # Out forwards and in backwards, as the chapters are made to be played;
    # with allow_reverse, any way at all, each as likely. Not with nothing
    # shuffled.
    any_way = bool(world.options.allow_reverse) and shuffle != MapShuffle.option_off

    def take(chapter: str, forward: bool) -> str | None:
        ends = spare.get(chapter, [])
        if not ends:
            return None
        if any_way:
            tid = world.random.choice(ends)
        else:
            preferred = [tid for tid in ends if is_forward(TRANSITIONS_BY_ID[tid]) == forward]
            tid = (preferred or ends)[0]
        ends.remove(tid)
        return tid

    for here, there in zip(chain, chain[1:]):
        out, into = take(here, True), take(there, False)
        if out is None or into is None:
            raise OptionError(
                f"{world.player_name}: {CHAPTERS_BY_KEY[here]['name']} and "
                f"{CHAPTERS_BY_KEY[there]['name']} cannot be joined: one has no way "
                "left between chapters. Try map_shuffle total.")
        plan.fixed.append((out, into))
    plan.reversed = entered_reversed(plan, lambda tid: MAP_CHAPTER[TRANSITIONS_BY_ID[tid]["map"]])
    # A boss other than the final one is a dead end; it hangs off a chapter
    # with a way to spare, as late on the route as there is one.
    for boss in [k for k in plan.spine if k in middle_bosses]:
        into = take(boss, False)
        position = plan.spine.index(boss)
        hosts = sorted((k for k in chain if spare.get(k)),
                       key=lambda k: (abs(plan.spine.index(k) - position),
                                      plan.spine.index(k) > position))
        if into is None or not hosts:
            raise OptionError(
                f"{world.player_name}: {CHAPTERS_BY_KEY[boss]['name']} cannot be "
                "reached: no chapter on the route has a spare way to another chapter, "
                "and only one boss can end it. Try map_shuffle total, or leave a goal "
                "chapter out.")
        plan.fixed.append((take(hosts[0], True), into))

    left_cross = [tid for ends in spare.values() for tid in ends]
    if shuffle == MapShuffle.option_off:
        # Nothing shuffles: the internal pairs are the vanilla ones, and a way
        # between chapters the route did not use leads nowhere.
        fix_vanilla(plan, [tid for ends in internal.values() for tid in ends])
        plan.inert += left_cross
        return
    for tid in left_cross:
        plan.groups[tid] = GROUP_DEFAULT
    if shuffle == MapShuffle.option_area:
        fix_vanilla(plan, [tid for ends in internal.values() for tid in ends])
    else:
        for index, key in enumerate(plan.spine, 1):
            for tid in internal.get(key, []):
                plan.groups[tid] = index


def fix_vanilla(plan: Plan, tids: list[str]) -> None:
    """Keep these at their vanilla partners. One with no partner here leads
    one way to where it always did."""
    here = set(tids)
    for tid in tids:
        partner = vanilla_partner(tid)
        if partner in here:
            if tid < partner:
                plan.fixed.append((tid, partner))
        elif TRANSITIONS_BY_ID[tid]["to"] in plan.maps:
            arrival = next((t["id"] for t in TRANSITIONS if t["map"] == TRANSITIONS_BY_ID[tid]["to"]
                            and t["id"] in plan.pool), "")
            if arrival:
                plan.one_way[tid] = arrival
            else:
                plan.inert.append(tid)
        else:
            plan.inert.append(tid)


def plan_total(world: "HalfLifeWorld", plan: Plan, live: list[str], standard: bool) -> None:
    """total: every transition can lead to any other. The spine runs through
    every map with a way in and a way out; the rest is GER's."""
    by_map: dict[str, list[str]] = {}
    for tid in live:
        by_map.setdefault(TRANSITIONS_BY_ID[tid]["map"], []).append(tid)
    final_maps = [m for m in CHAPTERS_BY_KEY[plan.final_boss]["maps"] if m in by_map]
    boss_maps = {CAMPAIGNS_BY_KEY[campaign_of(CHAPTERS_BY_KEY[k])]["boss_map"]
                 for k in plan.bosses if k != plan.final_boss}
    middle = [m for m in plan.maps if m != plan.start_map and m not in final_maps
              and len(by_map.get(m, [])) >= 2]
    off_spine = set(plan.maps) - set(middle) - {plan.start_map} - set(final_maps)
    order = draw_spine(world, middle, map_tier, boss_maps & set(middle) if standard else set(),
                       standard, lambda m: [m], plan.start_map, final_maps[0], off_spine)
    plan.spine = [plan.start_map, *order, *final_maps]
    spare = {m: list(v) for m, v in by_map.items()}
    rng = world.random

    # Out forwards and in backwards, as the maps are made to be played; with
    # allow_reverse, any way at all, each as likely.
    any_way = bool(world.options.allow_reverse)

    def take(map_name: str, forward: bool) -> str:
        ends = spare[map_name]
        preferred = [tid for tid in ends if is_forward(TRANSITIONS_BY_ID[tid]) == forward]
        tid = rng.choice(ends if any_way else preferred or ends)
        ends.remove(tid)
        return tid

    for here, there in zip(plan.spine, plan.spine[1:]):
        if not spare.get(here) or not spare.get(there):
            raise OptionError(f"{world.player_name}: {here} cannot lead on to {there}")
        plan.fixed.append((take(here, True), take(there, False)))
    plan.reversed = entered_reversed(plan, lambda tid: TRANSITIONS_BY_ID[tid]["map"])
    for ends in spare.values():
        for tid in ends:
            plan.groups[tid] = GROUP_DEFAULT


# -- rules -----------------------------------------------------------------------


def region_gate(world: "HalfLifeWorld", map_name: str,
                seal: bool = True) -> Callable[[CollectionState], bool] | None:
    """What everything in a map needs: its chapter's gates and its own, and,
    in the final boss's chapter, every other boss beaten (7.7)."""
    chapter = CHAPTERS_BY_KEY[MAP_CHAPTER[map_name]]
    conditions = gate_conditions(world, chapter["gates"])
    conditions += gate_conditions(world, chapter.get("map_gates", {}).get(map_name, {}))
    plan = getattr(world, "transition_plan", None)
    if seal and plan is not None and chapter["key"] == plan.final_boss and len(plan.bosses) > 1:
        needed, player = len(plan.bosses) - 1, world.player
        conditions.append(lambda state: state.has(VICTORY, player, needed))
    return all_of(conditions)


def both(a: Callable | None, b: Callable | None) -> Callable | None:
    if a is None:
        return b
    if b is None:
        return a
    return lambda state: a(state) and b(state)


# -- regions ---------------------------------------------------------------------


def way_back_rule(world: "HalfLifeWorld", edge: dict) -> Callable | None | bool:
    """The reverse of a one-way edge (3.3): free with a return teleporter (`tp`),
    absent when another route back exists (`alt`), and gated on its items for
    `item`. Crossing without them is the player's choice after a warning, never
    something logic expects. False means no reverse edge, which is also what an
    `item` edge gets when its items are not in this pool: nothing in logic
    crosses back."""
    way = edge.get("way_back", "tp")
    if way == "alt":
        return False
    if way == "tp":
        return None
    conditions = gate_conditions(world, {"always": edge["back"]})
    if len(conditions) < len(edge["back"]):
        return False
    return all_of(conditions)


def create_transition_regions(world: "HalfLifeWorld") -> None:
    multiworld, player = world.multiworld, world.player
    plan = make_plan(world)
    world.transition_plan = plan

    menu = Region(MENU, player, multiworld)
    multiworld.regions.append(menu)
    regions: dict[str, Region] = {}
    gates: dict[str, Callable | None] = {}
    for map_name in plan.maps:
        gates[map_name] = region_gate(world, map_name)
        for segment in segments_of(map_name):
            region = Region(region_name(map_name, segment), player, multiworld)
            regions[region.name] = region
            multiworld.regions.append(region)
    menu.connect(regions[region_name(plan.start_map, segments_of(plan.start_map)[0])], "Start")

    # Segment edges (3.3).
    for map_name in plan.maps:
        for edge in MAP_LOGIC.get(map_name, {}).get("edges", []):
            source = regions[region_name(map_name, edge["from"])]
            target = regions[region_name(map_name, edge["to"])]
            rule = both(gates[map_name], all_of(gate_conditions(world, edge)))
            source.connect(target, f"{map_name}: {edge['from']} to {edge['to']}", rule)
            if edge.get("one_way"):
                back = way_back_rule(world, edge)
                if back is not False:
                    target.connect(source, f"{map_name}: {edge['to']} back to {edge['from']}",
                                   both(gates[map_name], back))

    add_locations(world, plan, regions, gates)

    # Transitions: an exit and a same-named arrival in the transition's own
    # segment. The fixed ones are joined now; the rest wait for GER.
    exits: dict[str, Entrance] = {}
    for tid in plan.pool:
        if tid in plan.inert:
            continue
        t = TRANSITIONS_BY_ID[tid]
        region = regions[transition_region(tid)]
        exit_ = region.create_exit(tid)
        exit_.access_rule = gates[t["map"]] or (lambda state: True)
        exit_.randomization_type = (EntranceType.ONE_WAY if tid in plan.one_way
                                    else EntranceType.TWO_WAY)
        exit_.randomization_group = plan.groups.get(tid, GROUP_DEFAULT)
        exits[tid] = exit_
    for a, b in plan.fixed:
        exits[a].connect(regions[transition_region(b)])
        exits[b].connect(regions[transition_region(a)])
        plan.pairs.append((a, b))
    for a, b in plan.one_way.items():
        exits[a].connect(regions[transition_region(b)])
        plan.backtrack_orbs.setdefault(b, a)
    # An odd group leaves one over: it leads one way into an arrival already
    # paired, which gains a backtrack orb back to it (6.2).
    by_group: dict[int, list[str]] = {}
    for tid, group in plan.groups.items():
        by_group.setdefault(group, []).append(tid)
    for group, tids in sorted(by_group.items()):
        if len(tids) % 2:
            # Never a map's only way in within its group: nothing would arrive
            # there until the route had already passed it.
            in_map: dict[str, int] = {}
            for t in tids:
                in_map[TRANSITIONS_BY_ID[t]["map"]] = in_map.get(TRANSITIONS_BY_ID[t]["map"], 0) + 1
            choices = [t for t in sorted(tids) if in_map[TRANSITIONS_BY_ID[t]["map"]] > 1]
            odd = world.random.choice(choices or sorted(tids))
            del plan.groups[odd]
            exits[odd].randomization_type = EntranceType.ONE_WAY
            world.transition_odd.append(odd)
    for tid in sorted(plan.groups):
        region = regions[transition_region(tid)]
        target = region.create_er_target(tid)
        target.randomization_type = EntranceType.TWO_WAY
        target.randomization_group = plan.groups[tid]
    world.transition_exits = exits
    world.transition_regions = regions


def add_locations(world: "HalfLifeWorld", plan: Plan, regions: dict[str, Region],
                  gates: dict[str, Callable | None]) -> None:
    player = world.player
    for map_name in plan.maps:
        first = regions[region_name(map_name, segments_of(map_name)[0])]
        for entry in locations_by_map.get(map_name, []):
            if trigger_excluded(entry, world.excluded_triggers) or "sources" in entry:
                continue
            region = regions.get(region_name(map_name, entry.get("segment", "")), first)
            location = HalfLifeLocation(player, entry["name"], entry["id"], region)
            rule = both(gates[map_name], location_rule(world, entry))
            if rule is not None:
                location.access_rule = rule
            region.locations.append(location)

    for key in world.transition_chapters:
        chapter = CHAPTERS_BY_KEY[key]
        campaign = CAMPAIGNS_BY_KEY[campaign_of(chapter)]
        if chapter["is_goal"]:
            boss = campaign["boss_map"]
            region = regions[region_name(boss, segments_of(boss)[0])]
            rule = gates[boss]
            for needed in BOSS_NEEDS_MAPS.get(boss, ()):
                if needed in gates:
                    rule = both(rule, lambda state, n=needed: state.can_reach_region(n, player))
            # The chapter's completion moves from arriving in the ending scene
            # to the boss exit firing (3.5).
            for entry in LOCATIONS:
                if (entry["chapter"] == key and entry["trigger"]["type"] == "chapter_complete"
                        and not trigger_excluded(entry, world.excluded_triggers)):
                    location = HalfLifeLocation(player, entry["name"], entry["id"], region)
                    if rule is not None:
                        location.access_rule = rule
                    region.locations.append(location)
            event, name = VICTORY, f"{chapter['name']}: Boss Defeated"
        else:
            last = [m for m in chapter["maps"] if m not in ENDING_MAPS][-1]
            region = regions[region_name(last, segments_of(last)[0])]
            rule = gates[last]
            event, name = mission_complete_event(campaign["key"]), f"{chapter['name']}: Mission Cleared"
        location = HalfLifeLocation(player, name, None, region)
        if rule is not None:
            location.access_rule = rule
        location.place_locked_item(world.create_item(event))
        region.locations.append(location)

    add_weapon_checks(world, plan, regions, gates)


def add_weapon_checks(world: "HalfLifeWorld", plan: Plan, regions: dict[str, Region],
                      gates: dict[str, Callable | None]) -> None:
    """Every "First ..." check, hung on the start, reachable through any
    included copy's map and that map's gates. Mission sources stand in for the
    per-map ones until `map_sources` (3.8) is built."""
    player = world.player
    start = regions[region_name(plan.start_map, segments_of(plan.start_map)[0])]
    for entry in LOCATIONS:
        if "sources" not in entry or trigger_excluded(entry, world.excluded_triggers):
            continue
        sources = [s for s in weapon_sources(entry, world.excluded_chapters,
                                             world.ally_weapon_drops)
                   if s["map"] in gates]
        if not sources:
            continue
        ways = [(region_name(s["map"], segments_of(s["map"])[0]),
                 both(gates[s["map"]], all_of(gate_conditions(world, s.get("gates", {})))))
                for s in sources]
        base = location_rule(world, entry)

        def rule(state: CollectionState, ways=ways, base=base) -> bool:
            if base is not None and not base(state):
                return False
            return any(state.can_reach_region(r, player) and (x is None or x(state))
                       for r, x in ways)

        location = HalfLifeLocation(player, entry["name"], entry["id"], start)
        location.access_rule = rule
        start.locations.append(location)


# -- GER -------------------------------------------------------------------------


def connect_transitions(world: "HalfLifeWorld") -> None:
    """Pair what the spine left with GER, then lead each odd one out into an
    arrival already placed in its group."""
    from entrance_rando import randomize_entrances

    plan: Plan = world.transition_plan
    # One group at a time, in route order: a chapter's maps are only reachable
    # once the chapters before it are joined up inside.
    for group in sorted(set(plan.groups.values())):
        tids = sorted(t for t, g in plan.groups.items() if g == group)
        # Named, not discovered: an odd one out is an exit with no target yet.
        exits = [world.transition_exits[tid] for tid in tids]
        targets = sorted((e for r in world.transition_regions.values() for e in r.entrances
                          if e.parent_region is None and e.name in set(tids)),
                         key=lambda e: e.name)
        state = randomize_entrances(world, True, {group: [group]}, er_targets=targets,
                                    exits=exits)
        seen: set[str] = set()
        for source, target in state.pairings:
            if source not in seen and target not in seen:
                plan.pairs.append((source, target))
                seen.update((source, target))
    paired = [b for pair in plan.pairs for b in pair]
    for odd in world.transition_odd:
        same_map = [b for b in paired
                    if TRANSITIONS_BY_ID[b]["map"] != TRANSITIONS_BY_ID[odd]["map"]]
        arrival = world.random.choice(sorted(same_map or paired))
        world.transition_exits[odd].connect(world.transition_regions[transition_region(arrival)])
        plan.one_way[odd] = arrival
        plan.backtrack_orbs.setdefault(arrival, odd)


def transition_slot_data(world: "HalfLifeWorld") -> dict[str, Any]:
    plan: Plan = world.transition_plan
    shuffle = world.options.map_shuffle.current_key
    return {
        "progression_mode": "transitions",
        "map_shuffle": shuffle,
        "start_map": plan.start_map,
        "transition_chapters": list(world.transition_chapters),
        # Every pair that is not the vanilla one; anything unlisted in the
        # world keeps its vanilla partner.
        "transition_pairs": sorted(
            sorted(pair) for pair in plan.pairs if vanilla_partner(pair[0]) != pair[1]),
        "inert_transitions": sorted(plan.inert),
        "one_way_transitions": dict(sorted(plan.one_way.items())),
        "backtrack_orbs": dict(sorted(plan.backtrack_orbs.items())),
        "transition_hub": bool(world.options.transition_hub),
        "ending_map": plan.ending_map,
        "final_boss": plan.final_boss,
        "generation_difficulty": world.options.generation_difficulty.current_key,
        # Route nodes played end to start: maps in total, chapter keys else.
        "reversed": list(plan.reversed),
        "boss_exits": {campaign_of(CHAPTERS_BY_KEY[k]): CAMPAIGNS_BY_KEY[
            campaign_of(CHAPTERS_BY_KEY[k])]["boss_map"] for k in plan.bosses},
    }
