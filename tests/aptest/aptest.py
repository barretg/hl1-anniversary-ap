"""APTest: an in-game scenario harness for the retail world.

Stands in for the Python client, and is driven entirely from the game. Start it
in a terminal and leave it: each scenario writes the snapshot the client would
(`ap_in.txt`, every mission open and every item held unless the scenario takes
one away), and the game loads the scenario's map and puts you at its spot on
its own. What the harness has to say appears on screen. Verdicts and every
check the game sends go to `aptest_results.txt`.

Needs the test build of the dll (`cmake --build build/game-test`), the only one
that answers these. The harness swaps it into the installed mod on start and
puts the original back when it stops, so start it before the game. Close the
real client first: both write `ap_in.txt`.

In game, in chat (or `testing_aptest <verb>` in the console):
    !next              start the first untested scenario, then the one after
    !pass [note]       record a verdict; the next untested scenario loads
    !fail <note>
    !note <text>       a finding that is not pass or fail
    !redo / !prev / !go <n>
    !tp                back to the scenario's spot
    !info / !status / !list [text]
    !give <item> / !take <item>    change what the snapshot holds

The same verbs, without the `!`, can be typed into the terminal.

Scenarios come from the installed `checkdata.txt`, so they track the data:

* Source: every `F` record, one per mission's first copy of each weapon. You are
  put at the copy with that weapon locked, so touching it sends the check and
  leaves it on the floor. Pass if a player could walk there from the mission
  start with only the mission's own requirements; fail naming what else it
  needs, which becomes a `weapon_source_gates` or `unreachable_copies` entry.
  For a drop, you are put where the monster that carries it starts: kill it
  and touch what it drops.
* Gated: every check whose data says it needs an item.
* Crates: On A Rail from `c2a2e`, with each explosive in turn.

`--unproven` keeps only the weapon sources the maps cannot prove reachable (see
`unproven_sources`), each saying why it is on the list.

`--find` runs only the `!find` scenarios (see `find_scenarios`).

`--trace` runs only the `!trace` scenarios, in each game (see `trace_scenarios`):
the line's colour and route, the fallback where a map has no nodes, toggling
off, retargeting, a target off the map, and the chat colour.

`--parity` runs only the Sven parity scenarios (see `parity_scenarios`): the
behaviour this game was brought in line with the Sven Co-op plugin on. They
use three more verbs, standing in for what the real client would deliver:
    !item <name>       a filler item arrives (Ammo Cache, Medkit, ...)
    !trap <name>       a trap arrives (Scientist Trap, Bot Swarm Trap, ...)
    !deathlink         somebody else's DeathLink arrives
and the harness shows every DEATH and CHAT the game sends.

Usage:
    python tests/aptest/aptest.py --game-root "<Half-Life>" [--unproven | --find | --trace | --parity]
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Equipment every scenario holds unless it takes it away. Weapons come from the
# `K` records.
EQUIPMENT = ["HEV Suit", "Long Jump Module", "Flashlight", "PCV",
             "Night Vision Goggles", "Security Armor", "Melee Throw"]

# The test build of the server dll, which is the only one that answers the
# harness. Swapped into the installed mod for as long as the harness runs.
TEST_DLL = REPO / "build" / "game-test" / "hl.dll"
# Something only the test build carries, to tell the two apart.
TEST_DLL_MARKER = b"testing_aptest"

CRATE_MAP = "c2a2e"

# Cells a source's flood fill may visit before it is left unproven.
UNPROVEN_FILL_LIMIT = 1_500_000
EXPLOSIVES = ["Hand Grenade", "Satchel Charge", "MP5", "RPG", "Tripmine"]


def load_bridge():
    """The client's own bridge module, loaded by path: the world package
    imports Archipelago, which this script has no need of."""
    path = REPO / "apworld" / "half_life" / "client" / "bridge.py"
    spec = importlib.util.spec_from_file_location("aptest_bridge", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# -------------------------------------------------------------- checkdata


@dataclass
class Chapter:
    key: str
    name: str
    maps: list[str]
    campaign: str = ""


@dataclass
class Location:
    id: int
    map: str
    kind: str
    arg: str
    name: str
    pos: str = ""
    needs: str = ""


@dataclass
class Source:
    id: int
    map: str
    pos: str
    needs: str
    drop: str


@dataclass
class CheckData:
    data_version: str = ""
    chapters: list[Chapter] = field(default_factory=list)
    locations: dict[int, Location] = field(default_factory=dict)
    sources: list[Source] = field(default_factory=list)
    gated: dict[str, str] = field(default_factory=dict)  # classname -> item

    def chapter_of(self, map_name: str) -> Chapter | None:
        return next((c for c in self.chapters if map_name in c.maps), None)

    def by_name(self, name: str) -> Location | None:
        return next((l for l in self.locations.values() if l.name == name), None)


def read_checkdata(path: Path) -> CheckData:
    data = CheckData()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        f = line.split("|")
        if f[0] == "D":
            data.data_version = f[1]
        elif f[0] == "C" and len(f) >= 6:
            data.chapters.append(Chapter(f[2], f[3], f[4].split(","),
                                         f[7] if len(f) > 7 else ""))
        elif f[0] == "L" and len(f) >= 6:
            data.locations[int(f[1])] = Location(
                int(f[1]), f[2], f[3], f[4], f[5],
                f[6] if len(f) > 6 else "", f[7] if len(f) > 7 else "",
            )
        elif f[0] == "F" and len(f) >= 5:
            data.sources.append(Source(int(f[1]), f[2], f[3], f[4],
                                       f[5] if len(f) > 5 else ""))
        elif f[0] == "K" and len(f) >= 3:
            data.gated[f[1]] = f[2]
    return data


# -------------------------------------------------------------- scenarios


@dataclass
class Scenario:
    title: str
    map: str
    pos: str = ""
    take: list[str] = field(default_factory=list)
    expect: list[int] = field(default_factory=list)
    steps: str = ""
    # Missions locked for this scenario, and the seed's `ally_weapon_drops`.
    closed: list[str] = field(default_factory=list)
    ally_drops: bool = True
    # Locations the server already has, such as a part's arrival, so a part
    # warp to it is allowed.
    checked: list[int] = field(default_factory=list)


def cache_key(data: CheckData) -> str:
    """What the cached verdicts depend on: the data and the confirmed list."""
    import hashlib
    confirmed = (REPO / "tools" / "campaigns").glob("*.py")
    digest = hashlib.sha1(b"".join(p.read_bytes() for p in sorted(confirmed)))
    return f"{data.data_version}:{digest.hexdigest()[:8]}"


def unproven_sources(data: CheckData, game_root: Path,
                     cache: Path) -> dict[tuple[int, str], str]:
    """`{(location id, map): why}` for every source the maps cannot prove.

    Proven means a copy lying in the map, needing nothing beyond its mission,
    whose flood fill (the generator's, a crouched player ignoring gravity)
    reaches the map's start or a landmark. Everything else needs a player:

    * a drop: the monster has to die somewhere its weapon can be reached;
    * a copy handed over, which has no position to test;
    * a copy behind a gate, which someone set by hand from play;
    * a copy whose fill never reaches an entry (sealed, or out of bounds), or
      runs past the cell limit first.

    Slow (a fill per copy), so cached beside the results, keyed on the data
    version.
    """
    if cache.is_file():
        lines = cache.read_text(encoding="utf-8").splitlines()
        if lines and lines[0] == cache_key(data):
            found = {}
            for line in lines[1:]:
                location_id, map_name, why = line.split("|", 2)
                found[(int(location_id), map_name)] = why
            return found

    sys.path.insert(0, str(REPO / "tools"))
    from bsp_entities import ClipHull, load_map
    from build_campaign_data import fill_reaches_entry, map_entries, point_seeds
    from campaigns import KNOWN_CAMPAIGNS

    game_dir = {m: c.game_dir for c in KNOWN_CAMPAIGNS for m in c.maps}
    # Already settled in play: `confirmed_copies` in tools/campaigns.
    # A map, or one copy as `map@x y z`.
    confirmed = {
        (f"{c.display('First ' + item)}", key)
        for c in KNOWN_CAMPAIGNS for item, keys in c.confirmed_copies.items()
        for key in keys
    }
    found: dict[tuple[int, str], str] = {}
    for source in data.sources:
        key = (source.id, source.map)
        name = data.locations[source.id].name
        if ((name, source.map) in confirmed
                or (name, f"{source.map}@{source.pos}") in confirmed):
            continue
        if source.drop:
            found[key] = f"dropped by an {source.drop}" if source.drop == "ally" \
                else f"dropped by a {source.drop}"
            continue
        if not source.pos:
            found[key] = "handed over; nothing to test"
            continue
        if source.needs:
            found[key] = f"behind a gate on {source.needs}, set by hand"
            continue
        bsp = game_root / game_dir[source.map] / "maps" / f"{source.map}.bsp"
        position = tuple(float(v) for v in source.pos.split())
        print(f"  filling from {data.locations[source.id].name} on {source.map}"
              " (cached after the first run) ...", flush=True)
        # Well past the generator's limit for pools: a weapon in open level
        # is often a long way from any way in. Settles all but a handful.
        verdict = fill_reaches_entry(ClipHull(bsp), map_entries(load_map(bsp)),
                                     point_seeds(position), limit=UNPROVEN_FILL_LIMIT)
        if verdict is False:
            found[key] = "sealed: its fill never reaches a way into the map"
        elif verdict is None:
            found[key] = "its fill ran out of cells before reaching a way in"

    cache.write_text("\n".join([cache_key(data)] + [
        f"{i}|{m}|{why}" for (i, m), why in found.items()
    ]) + "\n", encoding="utf-8")
    return found


def find_scenarios(data: CheckData) -> list[Scenario]:
    """`!find` for a weapon with no copy on the current map: the earliest copy
    the player can reach, or the earliest at all when none can be.

    Mirrors `EarliestSource` in ap_locations.cpp: campaign order, ally drops
    left out (as the seed's default), a copy available when its mission is open
    and its `needs` are held.
    """
    order = {c.key: i for i, c in enumerate(data.chapters)}

    def rank(source: Source) -> tuple[int, int]:
        chapter = data.chapter_of(source.map)
        return order[chapter.key], chapter.maps.index(source.map)

    def where(source: Source) -> str:
        chapter = data.chapter_of(source.map)
        part = chapter.maps.index(source.map) + 1
        return f"{chapter.name}, part {part} ({source.map})"

    # A weapon with copies in at least three missions, so locking the earliest
    # still leaves a later one to fall back to.
    by_id: dict[int, list[Source]] = {}
    for source in data.sources:
        if source.drop != "ally" and data.chapter_of(source.map) is not None:
            by_id.setdefault(source.id, []).append(source)
    # `!find` matches by substring, and "First Glock" is inside "Blue Shift:
    # First Glock", so only a name nothing else contains answers by itself.
    names = [l.name.lower() for l in data.locations.values()]

    def unique(name: str) -> bool:
        return sum(name.lower() in n for n in names) == 1

    candidates = []
    for id_, sources in by_id.items():
        if not unique(data.locations[id_].name):
            continue
        sources.sort(key=rank)
        chapters = {data.chapter_of(s.map).key for s in sources}
        if len(chapters) >= 3 and not sources[0].needs:
            candidates.append((len(chapters), id_))
    _, weapon_id = max(candidates)
    sources = by_id[weapon_id]
    location = data.locations[weapon_id]
    first = data.chapter_of(sources[0].map)
    second = next(s for s in sources if data.chapter_of(s.map) is not first)
    # Somewhere to stand with no copy of it.
    copy_maps = {s.map for s in data.sources if s.id == weapon_id}
    stand = next(m for c in data.chapters for m in c.maps if m not in copy_maps)
    query = location.name.lower()
    every = sorted({data.chapter_of(s.map).key for s in sources})

    def scenario(title: str, closed: list[str], expect: list[str]) -> Scenario:
        return Scenario(
            title=f"Find: {title}", map=stand, closed=closed, ally_drops=False,
            steps="\n".join([f"Type !find {query} and expect:", *expect,
                              "!pass if it matches, else !fail <what it said>."]),
        )

    out = [
        scenario(f"{location.name}, every mission open", [], [
            "  '...the earliest available is in:'",
            f"  In {where(sources[0])}, with an ap_warp line.",
        ]),
        scenario(f"{location.name}, {first.name} locked", [first.key], [
            "  '...the earliest available is in:'",
            f"  In {where(second)}, with an ap_warp line.",
        ]),
        scenario(f"{location.name}, every copy's mission locked", every, [
            "  '...the earliest is in a locked map:'",
            f"  In {where(sources[0])}, and no ap_warp line.",
        ]),
    ]

    # A copy behind an item: skipped while the item is missing.
    gated = [(rank(s), s) for s in data.sources
             if s.needs and s.drop != "ally" and data.chapter_of(s.map) is not None
             and unique(data.locations[s.id].name)
             and all(rank(o) >= rank(s) for o in data.sources
                     if o.id == s.id and o.drop != "ally"
                     and data.chapter_of(o.map) is not None)]
    if gated:
        _, source = min(gated, key=lambda g: g[0])
        location = data.locations[source.id]
        others = [o for o in data.sources if o.id == source.id and o is not source
                  and o.drop != "ally" and data.chapter_of(o.map) is not None]
        item = source.needs.split(" or ")[0]
        query = location.name.lower()
        copy_maps = {o.map for o in data.sources if o.id == source.id}
        stand = next(m for c in data.chapters for m in c.maps if m not in copy_maps)
        nxt = min(others, key=rank) if others else None
        out.append(Scenario(
            title=f"Find: {location.name} without the {item}",
            map=stand, take=[item], ally_drops=False,
            steps="\n".join([
                f"Its earliest copy, {where(source)}, needs the {item}, which you",
                f"do not hold. Type !find {query} and expect:",
                *([f"  '...the earliest available is in:' {where(nxt)}."] if nxt else
                  [f"  '...the earliest needs the {source.needs}, which you do not have:'",
                   f"  In {where(source)}, with an ap_warp line."]),
                f"Then !give {item}, !find {query} again, and expect {where(source)}",
                f"after '...the earliest available is in:', with 'Needs the {source.needs} to reach.'",
                "!pass if both match, else !fail <what it said>.",
            ]),
        ))
    return out


# What chat should look like in each game: the HUD colour.
CHAT_COLOUR = {
    "half_life": "Half-Life's usual orange-yellow",
    "opposing_force": "green, like Opposing Force's HUD",
    "blue_shift": "blue, like Blue Shift's HUD",
}
CAMPAIGN_NAME = {"half_life": "Half-Life", "opposing_force": "Opposing Force",
                 "blue_shift": "Blue Shift"}
# A map with at least this many nodes has a graph worth routing along.
TRACE_RICH_NODES = 30


def node_counts(data: CheckData, game_root: Path) -> dict[str, int]:
    """`info_node`s per campaign map: what `!trace` has to route along."""
    sys.path.insert(0, str(REPO / "tools"))
    from bsp_entities import load_map
    from campaigns import KNOWN_CAMPAIGNS

    game_dir = {m: c.game_dir for c in KNOWN_CAMPAIGNS for m in c.maps}
    counts: dict[str, int] = {}
    for chapter in data.chapters:
        for map_name in chapter.maps:
            bsp = game_root / game_dir.get(map_name, "valve") / "maps" / f"{map_name}.bsp"
            if bsp.is_file():
                counts[map_name] = sum(e.get("classname") == "info_node"
                                       for e in load_map(bsp))
    return counts


def trace_scenarios(data: CheckData, nodes: dict[str, int]) -> list[Scenario]:
    """`!trace` in each game: one scenario per line colour on the best-noded map
    that has one, standing on the check, a map with no nodes, `!trace` with no
    text, and once overall a target off the map and a map change mid-trace.

    The line is red to health (wall units and Xen's pools), orange to HEV
    chargers, blue to weapons. Mirrors `LineColour` in ap_locations.cpp.
    """
    # Every positioned check on a map: (location, map, pos, colour).
    def colour(location: Location) -> str:
        if location.kind == "weapon_pickup":
            return "BLUE"
        return "ORANGE" if location.arg.startswith("func_recharge") else "RED"

    spots: list[tuple[Location, str, str, str]] = []
    for location in data.locations.values():
        if location.kind == "charger" and location.pos and not location.needs:
            spots.append((location, location.map, location.pos, colour(location)))
    for source in data.sources:
        if source.pos and not source.drop and not source.needs:
            location = data.locations[source.id]
            spots.append((location, source.map, source.pos, "BLUE"))

    def campaign_of(map_name: str) -> str:
        chapter = data.chapter_of(map_name)
        return chapter.campaign if chapter else ""

    def query(location: Location) -> str:
        return location.name.lower()

    off = "Then !trace alone: the line is gone within a second, nothing printed."
    verdict = "!pass, or !fail <what was wrong>."
    out: list[Scenario] = []
    campaigns = list(dict.fromkeys(c.campaign for c in data.chapters if c.campaign))
    for campaign in campaigns:
        game = CAMPAIGN_NAME.get(campaign, campaign)
        chat = f"Chat text (these lines) should be {CHAT_COLOUR.get(campaign, 'unchanged')}."
        mine = [s for s in spots if campaign_of(s[1]) == campaign]
        rich = sorted((s for s in mine if nodes.get(s[1], 0) >= TRACE_RICH_NODES),
                      key=lambda s: -nodes[s[1]])

        def first(want: str):
            return next((s for s in rich if s[3] == want
                         and not (want == "RED" and s[0].arg.startswith("trigger_hurt"))),
                        None)

        for want, what in (("RED", "health charger"), ("ORANGE", "HEV charger"),
                           ("BLUE", "weapon")):
            spot = first(want)
            if spot is None:
                continue
            location, map_name, _, _ = spot
            # Another check on the same map, to retarget to.
            other = next((s for s in mine if s[1] == map_name and s[0] is not location), None)
            steps = [
                f"{game}, {map_name} ({nodes[map_name]} nodes), from the map's start.",
                f"Type !trace {query(location)}. Expect the !find answer, then a",
                f"line in {want} from you along the walkable route to it.",
                "Walk it: the line is redrawn from you each second.",
            ]
            if other is not None:
                steps.append(f"With it on, !trace {query(other[0])}: it switches to a "
                             f"line in {other[3]} to that one, after its !find answer.")
            steps += [off, chat, verdict]
            out.append(Scenario(title=f"Trace: {game} {what} on {map_name} from the start",
                                map=map_name, steps="\n".join(steps)))

        # Standing on it: one short line, no fallback message.
        if rich:
            location, map_name, pos, want = rich[0]
            out.append(Scenario(
                title=f"Trace: {game} standing at {location.name}",
                map=map_name, pos=pos, steps="\n".join([
                    f"You are next to it. !trace {query(location)}: a short line in {want}",
                    "straight to it, and no 'No walking route' line.",
                    "Then collect it (use the charger, take the weapon): the line",
                    "goes away by itself, with nothing printed but the check itself.",
                    "!trace it again: a line, which collecting it again does not end.",
                    off, verdict,
                ])))

        # No graph, or next to none: the straight-line fallback.
        sparse = sorted(mine, key=lambda s: nodes.get(s[1], 0))
        if sparse and nodes.get(sparse[0][1], 0) < TRACE_RICH_NODES:
            location, map_name, _, want = sparse[0]
            out.append(Scenario(
                title=f"Trace: {game} fallback on {map_name} "
                      f"({nodes.get(map_name, 0)} nodes) to {location.name}",
                map=map_name, steps="\n".join([
                    f"{map_name} has {nodes.get(map_name, 0)} nodes. From the start,",
                    f"!trace {query(location)}. Out of sight of it, expect once",
                    "'No walking route known from here; the line points straight",
                    f"at it.' and a straight line in {want}; in sight, a straight line and",
                    "no message. Nothing should hang or stutter.",
                    off, verdict,
                ])))

        # No text: the nearest unfound check.
        if rich:
            map_name = rich[0][1]
            out.append(Scenario(
                title=f"Trace: {game} nearest check on {map_name}",
                map=map_name, steps="\n".join([
                    "!trace with nothing after it. Expect the same answer as !find",
                    "with nothing after it, and a line to that check in its colour",
                    "(red health, orange HEV, blue weapon).",
                    off, chat, verdict,
                ])))

    # Once: Xen's healing pools are red like the wall units.
    pool = next((s for s in spots if s[0].arg.startswith("trigger_hurt")
                 and nodes.get(s[1], 0) >= TRACE_RICH_NODES), None)
    if pool is not None:
        location, map_name, _, _ = pool
        out.append(Scenario(
            title=f"Trace: healing pool {location.name}", map=map_name,
            steps="\n".join([
                f"!trace {query(location)}: a RED line to the pool, ending at the",
                "water rather than stopping well short of it.", off, verdict,
            ])))

    # Once: a target on another map, and the map changing under a trace.
    here = next((s for s in spots if nodes.get(s[1], 0) >= TRACE_RICH_NODES), None)
    away = next((s for s in spots if here is not None and s[1] != here[1]), None)
    if here is not None and away is not None:
        out.append(Scenario(
            title=f"Trace: off the map, and a map change, from {here[1]}",
            map=here[1], steps="\n".join([
                f"!trace {query(away[0])}: the !find answer (where it is, how to get",
                "there), then 'Nothing on this map to trace to.' and no line.",
                f"Then !trace {query(here[0])} (a line), then !hub. In the hub: no line.",
                "!trace there starts a new trace rather than stopping the old one.",
                verdict,
            ])))
    return out


# The longest line the chat area shows whole.
STEP_WIDTH = 150


def reflow(steps: str) -> list[str]:
    """A scenario's steps as whole sentences, one message each.

    The steps are written wrapped to fit the source, and each line sent on its
    own reads as a string of fragments in the chat area. Lines are joined until
    one ends a sentence, and a sentence longer than the chat area is broken
    between words.
    """
    sentences: list[str] = []
    current = ""
    for line in steps.splitlines():
        line = line.strip()
        if not line:
            continue
        current = f"{current} {line}".strip()
        if current.rstrip("'\")").endswith((".", "!", "?", ":")):
            sentences.append(current)
            current = ""
    if current:
        sentences.append(current)
    out: list[str] = []
    for sentence in sentences:
        while len(sentence) > STEP_WIDTH:
            cut = sentence.rfind(" ", 0, STEP_WIDTH)
            if cut <= 0:
                break
            out.append(sentence[:cut])
            sentence = sentence[cut + 1:]
        out.append(sentence)
    return out


# What `!item` and `!trap` can send: the names `GrantFiller` and `SpringNow`
# in the game answer to.
FILLER = ("Medkit", "Health Charge", "Armor Battery", "Ammo Cache")
TRAPS = ("Scientist Trap", "Headcrab Trap", "Bot Swarm Trap", "Butterfingers Trap")


def parity_scenarios(data: CheckData) -> list[Scenario]:
    """The behaviour brought in line with the Sven Co-op plugin, one scenario
    per change (the ids are `.claude/sven-parity-handoff.md`'s).

    Missions are looked up by key, so the scenarios follow the data.
    """
    by_key = {c.key: c for c in data.chapters}
    index = {c.key: i for i, c in enumerate(data.chapters)}

    def reached(key: str) -> list[int]:
        """Every part of a mission arrived at, so each can be part-warped to."""
        maps = set(by_key[key].maps)
        return [l.id for l in data.locations.values()
                if l.kind == "map_reached" and l.map in maps]

    office = by_key["c1a2"]
    verdict = "!pass, or !fail <what was different>."
    out = [
        Scenario(
            title="Parity B1/B5: !find wording and old-style names",
            map=office.maps[0], steps="\n".join([
                f"!find {office.name.lower()} - health charger 1 (part 1), then",
                f"!find {office.name.lower()}: health charger 1 (part 1).",
                f"Both name '{office.name}: Health Charger 1 (Part 1)' and answer in",
                "two lines: '<direction>, <height>, about N units away.' (the height",
                "as 'level with you', 'a little above you', 'well below you' ...),",
                "then 'You have a clear line to it.' or 'Something solid is in the way.'",
                f"Then !find {office.name.lower()}: health charger 1 (part 2): it is off",
                "this map, and the last line says 'Get there with !warp ...'.",
                verdict,
            ])),
        Scenario(
            title="Parity B2: melee throw does four times a swing",
            map=office.maps[0], steps="\n".join([
                "Find a zombie (later in this map). Throw the crowbar at it",
                "(the throw key): a zombie on Normal dies in two throws, where",
                "it takes five swings.",
                verdict,
            ])),
        Scenario(
            title="Parity O4/O11: !ap numbers and the new !warp forms",
            map=office.maps[0], checked=reached(office.key), steps="\n".join([
                "!ap: each line ends '(hl N)', '(of N)' or '(bs N)' before its status,",
                f"{office.name} as '(hl {sum(1 for c in data.chapters[:index[office.key]] if c.campaign == office.campaign)})'.",
                "!warp hl <that number> goes there. Every part is marked reached, so",
                f"each of these goes to {office.name} part 2: !warp office 2,",
                "!warp office p2, !warp office part 2, !warp office pt 2,",
                f"and !warp {office.maps[1]} (the map name).",
                f"!warp {by_key['c2a3'].maps[2]}: refused, part 3 of a mission not reached.",
                verdict,
            ])),
        Scenario(
            title="Parity O6/O12: renamed weapons and the tracker's weapon blocks",
            map=office.maps[0], steps="\n".join([
                "!find displacer cannon and !find barnacle grapple each name",
                "'Opposing Force: First Displacer Cannon' / '... First Barnacle Grapple'.",
                "!tracker weapons: one 'Half-Life: Weapons (f/t)' block per game, the",
                "weapon checks under it and no longer under any map.",
                "!tracker opposing: Opposing Force's missions and its weapons block.",
                verdict,
            ])),
        Scenario(
            title="Parity O8: grenades once per mission load",
            map=office.maps[0], steps="\n".join([
                "Throw every hand grenade (and use up satchels, tripmines, snarks).",
                "!take Flashlight then !give Flashlight (a new snapshot): none come back.",
                "Walk on into part 2: still none. Die and reload: still none.",
                "!redo (a mission load): they are back.",
                verdict,
            ])),
        Scenario(
            title="Parity O9: the flashlight key without the flashlight",
            map=office.maps[0], take=["Flashlight"], steps="\n".join([
                "Press the flashlight key: 'You have not found the Flashlight yet.'",
                "Hold it down or mash it: at most once a second.",
                "!give Flashlight: the key works.",
                verdict,
            ])),
        Scenario(
            title="Parity O9: the night vision key without the goggles",
            map=by_key["of1a1"].maps[0], take=["Night Vision Goggles"],
            steps="\n".join([
                "Press the flashlight key: 'You have not found the Night Vision",
                "Goggles yet.' At most once a second.",
                verdict,
            ])),
        Scenario(
            title="Parity O10/O15: Ammo Cache and trap messages",
            map=office.maps[0], steps="\n".join([
                "Fire off some of several weapons' ammo, then !item Ammo Cache:",
                "every weapon you carry is topped up, not only the one in your hands",
                "(two clips' worth; 20 for grenades and the like; 2 RPG rockets).",
                "!trap Scientist Trap: 'Someone called for a science team.'",
                "!trap Headcrab Trap: 'What remarkable specimen!'",
                verdict,
            ])),
        Scenario(
            title="Parity O13: plain chat goes out, commands do not",
            map=office.maps[0], steps="\n".join([
                "Say 'hello' in chat: the harness shows 'CHAT: <your name> | hello',",
                "and the line still shows in game. !ap: no CHAT for it.",
                verdict,
            ])),
    ]

    for key, name in (("c1a2", "Freeman"), ("of1a1", "Shephard"),
                      ("ba_security1", "Barney")):
        chapter = by_key.get(key)
        if chapter is None:
            continue
        out.append(Scenario(
            title=f"Parity O14: a death in {chapter.name} is {name}'s",
            map=chapter.maps[0], steps="\n".join([
                f"kill in the console: the harness shows 'DEATH: {name} | ...'.",
                "!deathlink: you die, and the harness shows no DEATH for it",
                "(within 2 seconds it is the DeathLink's, not yours).",
                verdict,
            ])))

    out += [
        Scenario(
            title="Parity O16: !menu warp pages",
            map=office.maps[0], checked=reached(office.key), steps="\n".join([
                "!menu: 'Archipelago' with Warp to a mission, Tracker, Nearest check",
                "here, Return to the hub, and 0. Exit. The number keys pick, not weapons.",
                "1 (Warp), then Half-Life: its missions as '<n>. <name> [status]'.",
                "9 shows the next 7, 8 comes back. Pick Office Complex: Start and",
                "every part, each with its map; pick Part 3: you warp there.",
                "!menu, 1, then a locked or sealed mission: refused as !warp refuses it.",
                verdict,
            ])),
        Scenario(
            title="Parity O16: !menu tracker, nearest, warp points, hub, exit",
            map=office.maps[0], steps="\n".join([
                "!setwarp here, then !menu: Warp points is listed; it warps to it.",
                "!menu, 2 (Tracker), a game: Weapons f/t first, then missions with",
                "counts. Pick Office Complex: unfound first, found greyed '[done]'.",
                "Picking one gives the !find answer for it.",
                "!menu, 3: the !find answer for the nearest check.",
                "!menu, 0: it closes and number keys pick weapons again.",
                "!menu, Return to the hub: you go to the hub.",
                verdict,
            ])),
    ]
    return out


def build_scenarios(data: CheckData,
                    only: dict[tuple[int, str], str] | None = None) -> list[Scenario]:
    """Appended to, never reordered: results are recorded by title, but a
    stable order keeps `go <n>` meaning the same thing between runs.

    With `only`, just the sources it names, each saying why it is there.
    """
    scenarios: list[Scenario] = []

    for source in data.sources:
        location = data.locations.get(source.id)
        if location is None:
            continue
        why = None
        if only is not None:
            why = only.get((source.id, source.map))
            if why is None:
                continue
        chapter = data.chapter_of(source.map)
        where = f"{chapter.name if chapter else source.map} ({source.map})"
        item = data.gated.get(location.arg.split(",")[0])
        drop = f" [{source.drop} drop]" if source.drop else ""
        if source.drop:
            how = (f"The {source.drop} carrying it is near you. Kill it and touch "
                   f"the weapon it drops: expect '{location.name}'.")
        elif source.pos:
            how = f"You are at the copy. Touch it: expect '{location.name}'."
        else:
            how = (f"Handed over on {source.map}, not left lying: play to it: "
                   f"expect '{location.name}'.")
        scenarios.append(Scenario(
            # The position tells two carriers on one map apart, so one
            # replacing another is a new scenario, not an old verdict.
            title=f"Source: {location.name} in {where}"
                  + (f" at {source.pos}" if source.pos else "") + drop,
            map=source.map, pos=source.pos,
            take=[item] if item else [], expect=[location.id],
            steps="\n".join(filter(None, [
                f"Unproven: {why}." if why else "",
                how,
                f"Data says it needs: {source.needs}." if source.needs else "",
                "Could a player walk here from the mission start with only its own",
                "requirements" + (" and the item above" if source.needs else "")
                + "? !pass, or !fail <what else it needs>.",
            ])),
        ))

    if only is not None:
        return scenarios

    for location in data.locations.values():
        if not location.needs:
            continue
        chapter = data.chapter_of(location.map)
        where = f"{chapter.name if chapter else location.map} ({location.map})"
        scenarios.append(Scenario(
            title=f"Gated: {location.name} needs {location.needs}",
            map=location.map, expect=[location.id],
            steps="\n".join([
                f"You start at the map's spawn holding {location.needs}.",
                f"Reach '{location.name}' in {where}"
                + (f" (at {location.pos})" if location.pos else "") + ".",
                f"Then !take {location.needs.split(' or ')[0]} and confirm it cannot be",
                "reached without it. !pass if both hold, else !fail <what you found>.",
            ]),
        ))

    for explosive in [None, *EXPLOSIVES]:
        held = f"only the {explosive}" if explosive else "no explosive at all"
        scenarios.append(Scenario(
            title=f"Crates: On A Rail ({CRATE_MAP}) with {held}",
            map=CRATE_MAP,
            take=[e for e in EXPLOSIVES if e != explosive],
            steps="\n".join([
                f"Holding {held}. Ride on to the crates that block the track.",
                "Can you clear them and carry on? !note <yes/no, and how>.",
                "Logic: loose takes Hand Grenade, Satchel Charge or the MP5's",
                "grenades; strict only Hand Grenade or Satchel Charge.",
            ]),
        ))

    return scenarios


# -------------------------------------------------------------- the dll


class DllSwap:
    """The installed `hl.dll` swapped for the test build, and back.

    The original is moved aside beside it, never copied, so it comes back byte
    for byte. A backup already there means an earlier run never got to restore
    it, and is kept: it is the real one, and what is installed is a test dll.
    Every move is a rename within the folder, so a running game keeps the dll
    it loaded and sees the other one on its next launch.
    """

    def __init__(self, installed: Path, test_dll: Path) -> None:
        self.installed = installed
        self.test_dll = test_dll
        self.backup = installed.with_name(installed.name + ".aptest-original")

    def check(self) -> str | None:
        """Why the swap cannot go ahead, or None."""
        if not self.test_dll.is_file():
            return f"{self.test_dll} not found; cmake --build build/game-test first"
        if TEST_DLL_MARKER not in self.test_dll.read_bytes():
            return f"{self.test_dll} is not a test build (HLAP_TEST_BUILD off)"
        if not self.installed.is_file() and not self.backup.is_file():
            return f"{self.installed} not found; install the mod first"
        return None

    def stale(self) -> list[Path]:
        """Game sources newer than the test dll: it may not be what you think."""
        built = self.test_dll.stat().st_mtime
        return sorted(p for p in (REPO / "game" / "src").rglob("*")
                      if p.is_file() and p.stat().st_mtime > built)

    def swap_in(self) -> None:
        if self.backup.is_file():
            print(f"Keeping {self.backup.name}, left by a run that did not finish.")
        else:
            os.replace(self.installed, self.backup)
        temp = self.installed.with_name(self.installed.name + ".aptest-tmp")
        shutil.copy2(self.test_dll, temp)
        os.replace(temp, self.installed)
        print(f"Test dll in place: {self.installed}")

    def restore(self) -> None:
        if self.backup.is_file():
            os.replace(self.backup, self.installed)
            print(f"Original dll restored: {self.installed}")


# -------------------------------------------------------------- the harness


class Harness:
    def __init__(self, store: Path, bridge_module, find: bool,
                 game_root: Path | None = None,
                 trace_root: Path | None = None, parity: bool = False) -> None:
        self.store = store
        self.data = read_checkdata(store / "checkdata.txt")
        only = None
        if game_root is not None:
            only = unproven_sources(self.data, game_root, store / "aptest_unproven.txt")
        if parity:
            self.scenarios = parity_scenarios(self.data)
        elif trace_root is not None:
            self.scenarios = trace_scenarios(self.data, node_counts(self.data, trace_root))
        elif find:
            self.scenarios = find_scenarios(self.data)
        else:
            self.scenarios = build_scenarios(self.data, only)
        self.bridge = bridge_module.Bridge(store)
        self.bridge.reset_cursor()
        self.results_path = store / "aptest_results.txt"
        self.go_path = store / "aptest_go.txt"
        self.say_path = store / "aptest_say.txt"
        self.say_path.write_text("", encoding="utf-8")
        self.seq = self.last_seq()
        self.current = -1
        self.items: set[str] = self.base_items()
        self.seen: set[int] = set()
        # Re-entrant: a verdict from the game arrives inside the poll and
        # starts the next scenario, which takes the lock again.
        self.lock = threading.RLock()
        self.running = True

    # Talking to the player, in game and here.

    def tell(self, text: str, hud: bool = True) -> None:
        print(text)
        with self.say_path.open("a", encoding="utf-8") as handle:
            for line in text.strip("\n").splitlines():
                handle.write(("hud|" if hud else "con|") + line.strip() + "\n")

    def last_seq(self) -> int:
        """The sequence number of the scenario the game last saw, so a
        restarted harness never repeats one the game would ignore."""
        if self.go_path.is_file():
            for line in self.go_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("seq="):
                    return int(line[4:] or 0)
        return 0

    # The snapshot.

    def base_items(self) -> set[str]:
        return set(EQUIPMENT) | set(self.data.gated.values())

    def publish(self, force: bool = False) -> None:
        s = self.scenario()
        self.bridge.write_snapshot(
            connected=True,
            chapters=[c.key for c in self.data.chapters
                      if s is None or c.key not in s.closed],
            items=sorted(self.items),
            goal_open=True,
            death_link=False,
            # Ally drops are among the scenarios, so `!find` should show them.
            ally_weapon_drops=s.ally_drops if s is not None else True,
            excluded=[],
            ungated=[],
            starting=["weapon_crowbar"],
            checked=sorted(s.checked) if s is not None else [],
            missing=sorted(set(self.data.locations) - set(s.checked if s else [])),
            data_version=self.data.data_version,
            slot="aptest:1",
            force=force,
        )

    # Scenarios.

    def scenario(self) -> Scenario | None:
        if 0 <= self.current < len(self.scenarios):
            return self.scenarios[self.current]
        return None

    def start(self, index: int) -> None:
        if not 0 <= index < len(self.scenarios):
            self.tell(f"[aptest] No scenario {index}; there are {len(self.scenarios)}.")
            return
        with self.lock:
            self.current = index
            s = self.scenarios[index]
            self.items = self.base_items() - set(s.take)
            self.seen = set()
            self.publish(force=True)
            # The game loads the map when the sequence number moves, so a
            # redo of the same scenario reloads it too.
            self.seq += 1
            go = [f"seq={self.seq}", f"map={s.map}"] + ([f"pos={s.pos}"] if s.pos else [])
            self.go_path.write_text("\n".join(go) + "\n", encoding="utf-8")
            self.tell(f"[aptest] {index}/{len(self.scenarios) - 1}: {s.title}")
            if s.take:
                self.tell(f"[aptest] Without: {', '.join(s.take)}")
            self.info()

    def info(self) -> None:
        s = self.scenario()
        if s is None:
            self.tell("[aptest] No scenario running. !next starts the first untested.")
            return
        for number, line in enumerate(reflow(s.steps), 1):
            self.tell(f"{number}. {line}")

    def first_untested(self, after: int = -1) -> int | None:
        verdicts = self.latest_verdicts()
        return next((i for i, s in enumerate(self.scenarios)
                     if i > after and s.title not in verdicts), None)

    def record(self, verdict: str, note: str) -> None:
        s = self.scenario()
        if s is None:
            self.tell("[aptest] No scenario running.")
            return
        sent = ",".join(str(i) for i in sorted(self.seen))
        line = "|".join([time.strftime("%Y-%m-%d %H:%M:%S"), str(self.current),
                         s.title, verdict, note.replace("|", "/"), sent])
        with self.results_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        self.tell(f"[aptest] Recorded {verdict}.")
        following = self.first_untested(self.current)
        if following is None:
            self.tell("[aptest] That was the last untested scenario.")
            self.status()
        else:
            self.start(following)

    def latest_verdicts(self) -> dict[str, str]:
        verdicts: dict[str, str] = {}
        if self.results_path.exists():
            for line in self.results_path.read_text(encoding="utf-8").splitlines():
                parts = line.split("|")
                if len(parts) >= 4:
                    verdicts[parts[2]] = parts[3]
        return verdicts

    def status(self) -> None:
        verdicts = self.latest_verdicts()
        counts: dict[str, int] = {}
        for s in self.scenarios:
            verdict = verdicts.get(s.title, "untested")
            counts[verdict] = counts.get(verdict, 0) + 1
        self.tell("[aptest] " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        first = self.first_untested()
        if first is not None:
            self.tell(f"[aptest] First untested: {first} {self.scenarios[first].title}")

    def list(self, text: str) -> None:
        verdicts = self.latest_verdicts()
        shown = 0
        for index, s in enumerate(self.scenarios):
            if text.lower() in s.title.lower():
                mark = verdicts.get(s.title, "")
                self.tell(f"{index:4} {('[' + mark + '] ') if mark else ''}{s.title}",
                          hud=False)
                shown += 1
        self.tell(f"[aptest] {shown} listed in the console (~).")

    def command(self, verb: str, arg: str) -> None:
        """One verb, from the game (`!pass`) or typed here (`pass`)."""
        with self.lock:
            if verb == "pass":
                self.record("pass", arg)
            elif verb in ("fail", "note"):
                if arg:
                    self.record(verb, arg)
                else:
                    self.tell(f"[aptest] !{verb} needs a note.")
            elif verb == "next":
                if self.current < 0:
                    first = self.first_untested()
                    self.start(0 if first is None else first)
                else:
                    self.start(self.current + 1)
            elif verb == "prev":
                self.start(self.current - 1)
            elif verb == "redo":
                if self.current < 0:
                    self.tell("[aptest] Nothing to redo. !next starts the first untested.")
                else:
                    self.start(self.current)
            elif verb == "go" and arg.isdigit():
                self.start(int(arg))
            elif verb == "info":
                self.info()
            elif verb == "status":
                self.status()
            elif verb == "list":
                self.list(arg)
            elif verb in ("item", "trap") and arg:
                # The game ignores a name it does not know, so check it here
                # and say what would have worked. Chat is not careful about case.
                known = FILLER if verb == "item" else TRAPS
                name = next((n for n in known if n.lower() == arg.lower()), None)
                if name is None:
                    self.tell(f"[aptest] No {verb} '{arg}'. Try: {', '.join(known)}.")
                    return
                arg = name
                self.bridge.queue_event(verb.upper(), arg)
                self.publish()
                self.tell(f"[aptest] {verb} sent: {arg}")
            elif verb == "deathlink":
                self.bridge.queue_event("DEATHLINK", "APTest~a test DeathLink")
                self.publish()
                self.tell("[aptest] DeathLink sent.")
            elif verb in ("give", "take") and arg:
                # Chat is not careful about case; the snapshot is.
                arg = next((n for n in self.base_items() if n.lower() == arg.lower()), arg)
                (self.items.add if verb == "give" else self.items.discard)(arg)
                self.publish()
                self.tell(f"[aptest] {verb}: {arg}")
            else:
                self.tell("[aptest] !pass !fail !note !next !prev !redo !go <n> !info "
                          "!status !list !give !take !tp !item !trap !deathlink")

    # Game to us.

    def judge(self, location_id: int) -> None:
        s = self.scenario()
        location = self.data.locations.get(location_id)
        name = location.name if location else f"id {location_id}"
        if location is not None and location.kind == "map_reached":
            return  # every arrival sends one; noise here
        if s is not None and location_id in s.expect:
            if location_id not in self.seen:
                self.tell(f"[aptest] Expected check arrived: {name}. !pass if reachable.")
        else:
            self.tell(f"[aptest] Other check: {name}")
        self.seen.add(location_id)

    def poll(self) -> None:
        while self.running:
            try:
                events = self.bridge.read_events()
            except OSError:
                events = []
            with self.lock:
                for event in events:
                    if event.kind == "CHECK":
                        self.judge(int(event.arg))
                    elif event.kind == "ACK":
                        self.bridge.acknowledge(int(event.arg))
                    elif event.kind in ("DEATH", "CHAT"):
                        self.tell(f"[aptest] {event.kind}: " + " | ".join(event.args))
                    elif event.kind == "HELLO":
                        self.publish(force=True)
                    elif event.kind == "APTEST" and event.args:
                        verb = event.args[0]
                        arg = event.args[1] if len(event.args) > 1 else ""
                        print(f"(from game) {verb} {arg}".rstrip())
                        self.command(verb, arg.strip())
                self.publish()
            time.sleep(0.2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-root", type=Path,
                        default=os.environ.get("HL_ROOT"),
                        help="the Half-Life install (or set HL_ROOT)")
    parser.add_argument("--test-dll", type=Path, default=TEST_DLL,
                        help="the test build of hl.dll to swap in (default: %(default)s)")
    parser.add_argument("--unproven", action="store_true",
                        help="only the weapon sources the maps cannot prove reachable")
    parser.add_argument("--find", action="store_true",
                        help="only the !find scenarios")
    parser.add_argument("--trace", action="store_true",
                        help="only the !trace scenarios, in each game")
    parser.add_argument("--parity", action="store_true",
                        help="only the Sven parity scenarios")
    args = parser.parse_args(argv)
    if args.game_root is None:
        parser.error("--game-root is required")

    bridge_module = load_bridge()
    store = bridge_module.find_store_dir(args.game_root)
    if not (store / "checkdata.txt").is_file():
        parser.error(f"{store / 'checkdata.txt'} not found; install the mod first")

    swap = DllSwap(store.parent / "dlls" / "hl.dll", args.test_dll)
    problem = swap.check()
    if problem:
        parser.error(problem)
    newer = swap.stale()
    if newer:
        print(f"Warning: {len(newer)} game source file(s) are newer than the test dll, "
              f"e.g. {newer[0].relative_to(REPO)}. Rebuild with "
              "cmake --build build/game-test.")

    # A closed terminal or a kill still puts the real dll back.
    def stop(signum, frame):
        raise KeyboardInterrupt
    for name in ("SIGTERM", "SIGHUP"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), stop)

    # Two harnesses on one store both append to `aptest_say.txt` and both answer
    # every event, which reads in game as each line twice, interleaved.
    lock = store / "aptest.lock"
    other = running_harness(lock)
    if other is not None:
        parser.error(f"another harness is already running (pid {other}); stop it first")
    lock.write_text(str(os.getpid()), encoding="utf-8")

    swap.swap_in()
    try:
        return run(args, store, bridge_module)
    finally:
        swap.restore()
        lock.unlink(missing_ok=True)


def running_harness(lock: Path) -> int | None:
    """The pid of a live harness holding `lock`, or None. A lock left by one
    that was killed is stale and ignored."""
    try:
        pid = int(lock.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    if pid == os.getpid():
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except (PermissionError, OSError):
        pass  # alive but not ours, or a platform that cannot tell; assume alive
    return pid


def run(args: argparse.Namespace, store: Path, bridge_module) -> int:
    print("Launch Half-Life now (or restart it if it is running) so it loads the "
          "test dll.")
    harness = Harness(store, bridge_module, args.find,
                      args.game_root if args.unproven else None,
                      args.game_root if args.trace else None, args.parity)
    harness.publish(force=True)
    print(f"{len(harness.scenarios)} scenarios from {store / 'checkdata.txt'}.")
    print("Drive it from the game: !next to begin, !pass / !fail <note> / !note <text>.")
    harness.status()
    threading.Thread(target=harness.poll, daemon=True).start()

    # The same verbs here, for whoever is at the terminal anyway.
    while True:
        try:
            line = input().strip()
        except KeyboardInterrupt:
            break
        except EOFError:
            # No terminal to read: run on, driven from the game, until ^C.
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                break
        verb, _, arg = line.partition(" ")
        if verb in ("quit", "exit"):
            break
        if verb:
            harness.command(verb, arg.strip())
    harness.running = False
    # A game started later must not load a scenario nobody is running.
    harness.go_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
