"""APTest: an in-game scenario harness for the retail world.

Stands in for the Python client. Each scenario writes the snapshot the client
would (`ap_in.txt`, every mission open and every item held unless the scenario
takes one away) and the destination for the game (`aptest_go.txt`). In game,
`ap_test_go` loads the map and drops you at the spot; this script then watches
`ap_out.txt` and marks every check the game sends as expected or not.

Needs the test build of the dll (`cmake --build build/game-test`), which is the
only one with the `ap_test_*` commands. Close the real client first: both write
`ap_in.txt`, and the real one rewrites it when it next connects.

Scenarios come from the installed `checkdata.txt`, so they track the data:

* Source: every `F` record, one per mission's first copy of each weapon. You are
  put at the copy with that weapon locked, so touching it sends the check and
  leaves it on the floor. Pass if a player could walk there from the mission
  start with only the mission's own requirements; fail naming what else it
  needs, which becomes a `weapon_source_gates` or `unreachable_copies` entry.
  For a drop, the monster that carries it is there instead: kill it and touch
  what it drops.
* Gated: every check whose data says it needs an item. You start at the map's
  spawn holding everything. Pass if it is reached with the item and not
  without it.
* Crates: On A Rail from `c2a2e`, with each explosive in turn.

Commands:
    list [text]        scenarios, filtered by title
    go <n>             start scenario n (then `ap_test_go` in game)
    next / prev / redo
    info               the current scenario's steps again
    pass [note]        record a pass and move to the next
    fail <note>        record a failure and move to the next
    note <text>        record a finding without a verdict and move on
    status             verdict counts and the first untested scenario
    give <item> / take <item>   change what the snapshot holds
    quit

Usage:
    python tests/aptest/aptest.py --game-root "<Half-Life>"
    python tests/aptest/aptest.py --game-root "<Half-Life>" --unproven

`--unproven` keeps only the weapon sources the maps cannot prove reachable (see
`unproven_sources`), each saying why it is on the list.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
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
            data.chapters.append(Chapter(f[2], f[3], f[4].split(",")))
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
    confirmed = {
        (f"{c.display('First ' + item)}", m)
        for c in KNOWN_CAMPAIGNS for item, maps in c.confirmed_copies.items()
        for m in maps
    }
    found: dict[tuple[int, str], str] = {}
    for source in data.sources:
        key = (source.id, source.map)
        if (data.locations[source.id].name, source.map) in confirmed:
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
            title=f"Source: {location.name} in {where}{drop}",
            map=source.map, pos=source.pos,
            take=[item] if item else [], expect=[location.id],
            steps="\n".join(filter(None, [
                f"Unproven: {why}." if why else "",
                how,
                f"Data says it needs: {source.needs}." if source.needs else "",
                "Could a player walk here from the mission start with only its own",
                "requirements" + (" and the item above" if source.needs else "")
                + "? pass, or fail <what else it needs>.",
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
                f"Then `take {location.needs.split(' or ')[0]}` and confirm it cannot be",
                "reached without it. pass if both hold, else fail <what you found>.",
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
                "Can you clear them and carry on? note <yes/no, and how>.",
                "Logic: loose takes Hand Grenade, Satchel Charge or the MP5's",
                "grenades; strict only Hand Grenade or Satchel Charge.",
            ]),
        ))

    return scenarios


# -------------------------------------------------------------- the harness


class Harness:
    def __init__(self, store: Path, bridge_module,
                 game_root: Path | None = None) -> None:
        self.store = store
        self.data = read_checkdata(store / "checkdata.txt")
        only = None
        if game_root is not None:
            only = unproven_sources(self.data, game_root, store / "aptest_unproven.txt")
        self.scenarios = build_scenarios(self.data, only)
        self.bridge = bridge_module.Bridge(store)
        self.bridge.reset_cursor()
        self.results_path = store / "aptest_results.txt"
        self.current = -1
        self.items: set[str] = set()
        self.seen: set[int] = set()
        self.lock = threading.Lock()
        self.running = True

    # The snapshot.

    def base_items(self) -> set[str]:
        return set(EQUIPMENT) | set(self.data.gated.values())

    def publish(self, force: bool = False) -> None:
        all_ids = sorted(self.data.locations)
        self.bridge.write_snapshot(
            connected=True,
            chapters=[c.key for c in self.data.chapters],
            items=sorted(self.items),
            goal_open=True,
            death_link=False,
            excluded=[],
            ungated=[],
            starting=["weapon_crowbar"],
            checked=[],
            missing=all_ids,
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
            print(f"no scenario {index}; `list` shows them.")
            return
        with self.lock:
            self.current = index
            s = self.scenarios[index]
            self.items = self.base_items() - set(s.take)
            self.seen = set()
            self.publish(force=True)
            go = [f"map={s.map}"] + ([f"pos={s.pos}"] if s.pos else [])
            (self.store / "aptest_go.txt").write_text("\n".join(go) + "\n",
                                                      encoding="utf-8")
        print(f"\nScenario {index}: {s.title}")
        if s.take:
            print(f"  without: {', '.join(s.take)}")
        print("  In game: ap_test_go   (ap_test_tp puts you back at the spot)")
        self.info()

    def info(self) -> None:
        s = self.scenario()
        if s is None:
            print("no scenario running.")
            return
        for line in s.steps.splitlines():
            print(f"  {line}")

    def record(self, verdict: str, note: str) -> None:
        s = self.scenario()
        if s is None:
            print("no scenario running.")
            return
        sent = ",".join(str(i) for i in sorted(self.seen))
        line = "|".join([time.strftime("%Y-%m-%d %H:%M:%S"), str(self.current),
                         s.title, verdict, note.replace("|", "/"), sent])
        with self.results_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        print(f"recorded {verdict}: {s.title}")
        if self.current + 1 < len(self.scenarios):
            self.start(self.current + 1)

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
        first = None
        for index, s in enumerate(self.scenarios):
            verdict = verdicts.get(s.title, "untested")
            counts[verdict] = counts.get(verdict, 0) + 1
            if verdict == "untested" and first is None:
                first = index
        print(", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        if first is not None:
            print(f"first untested: {first} {self.scenarios[first].title}")

    def list(self, text: str) -> None:
        verdicts = self.latest_verdicts()
        for index, s in enumerate(self.scenarios):
            if text.lower() in s.title.lower():
                mark = verdicts.get(s.title, "")
                print(f"{index:4} {('[' + mark + '] ') if mark else ''}{s.title}")

    # Game to us.

    def judge(self, location_id: int) -> None:
        s = self.scenario()
        location = self.data.locations.get(location_id)
        name = location.name if location else f"id {location_id}"
        if location is not None and location.kind == "map_reached":
            return  # every arrival sends one; noise here
        if s is not None and location_id in s.expect:
            if location_id not in self.seen:
                print(f"\n  PASS: check '{name}' arrived.")
        else:
            print(f"\n  note: other check '{name}'")
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
                    elif event.kind == "HELLO":
                        self.publish(force=True)
                if self.current >= 0:
                    self.publish()
            time.sleep(0.2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-root", type=Path,
                        default=os.environ.get("HL_ROOT"),
                        help="the Half-Life install (or set HL_ROOT)")
    parser.add_argument("--unproven", action="store_true",
                        help="only the weapon sources the maps cannot prove reachable")
    args = parser.parse_args(argv)
    if args.game_root is None:
        parser.error("--game-root is required")

    bridge_module = load_bridge()
    store = bridge_module.find_store_dir(args.game_root)
    if not (store / "checkdata.txt").is_file():
        parser.error(f"{store / 'checkdata.txt'} not found; install the mod first")

    harness = Harness(store, bridge_module,
                      args.game_root if args.unproven else None)
    print(f"{len(harness.scenarios)} scenarios from {store / 'checkdata.txt'}.")
    harness.status()
    threading.Thread(target=harness.poll, daemon=True).start()

    commands = {
        "next": lambda a: harness.start(harness.current + 1),
        "prev": lambda a: harness.start(harness.current - 1),
        "redo": lambda a: harness.start(harness.current),
        "info": lambda a: harness.info(),
        "status": lambda a: harness.status(),
        "list": lambda a: harness.list(a),
        "pass": lambda a: harness.record("pass", a),
        "fail": lambda a: harness.record("fail", a) if a else print("fail <note>"),
        "note": lambda a: harness.record("note", a) if a else print("note <text>"),
    }
    while True:
        try:
            line = input("aptest> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        verb, _, arg = line.partition(" ")
        arg = arg.strip()
        if verb in ("quit", "exit"):
            break
        if verb == "go" and arg.isdigit():
            harness.start(int(arg))
        elif verb in ("give", "take") and arg:
            with harness.lock:
                (harness.items.add if verb == "give" else harness.items.discard)(arg)
                harness.publish()
            print(f"{verb}: {arg}")
        elif verb in commands:
            commands[verb](arg)
        elif verb:
            print("commands: list go next prev redo info pass fail note status "
                  "give take quit")
    harness.running = False
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
