"""Generate a transitions mode seed over a range of chapters and play it.

    python tools/seed_run.py --chapters 1:2

Chapters are numbered in campaign order, Black Mesa Inbound being 0, so 1:2 is
Anomalous Materials and Unforeseen Consequences. The goal chapter (Nihilanth)
is always added. Chapters need not be marked supported yet: the generator's
check is lifted for the run.

Each run gets its own `tests/out/<runid>/` (untracked), holding:

  players/half_life.yaml  the options generated with
  AP_<seed>.zip           Archipelago's output
  AP_<seed>_Spoiler.txt   Archipelago's spoiler, taken out of the zip
  slot_data.json          the seed's slot data, as the client gets it
  transitions.txt         the transition spoiler: every pairing, where each end is

Then the aptest harness hosts one scenario that plays the seed (`--seed-file`),
unless `--no-host`. Generation runs in the Archipelago source checkout's venv.
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import zipfile
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "tests" / "out"
AP_SRC = Path("/games/Projects/Archipelago-src")
AP_PYTHON = AP_SRC / ".venv" / "bin" / "python"
GAME_ROOT = Path("/games/SteamLibrary/steamapps/common/Half-Life")
CAMPAIGN = REPO / "apworld" / "half_life" / "data" / "campaign.json"
SHUFFLES = ("area", "chapter_maps", "total")


def half_life_chapters(data: dict) -> list[dict]:
    return [c for c in data["chapters"] if c.get("campaign", "half_life") == "half_life"]


def pick(data: dict, spec: str) -> list[str]:
    """Chapter names for `A:B` (inclusive) or `N`, plus the goal chapter."""
    chapters = half_life_chapters(data)
    first, _, last = spec.partition(":")
    lo, hi = int(first), int(last or first)
    if not 0 <= lo <= hi < len(chapters):
        raise SystemExit(f"--chapters {spec}: chapters run 0 to {len(chapters) - 1}")
    names = [c["name"] for c in chapters[lo:hi + 1]]
    goal = next(c["name"] for c in chapters if c["is_goal"])
    return names if goal in names else names + [goal]


def write_yaml(path: Path, chapters: list[str], shuffle: str, difficulty: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    listed = "".join(f"      - {json.dumps(name)}\n" for name in chapters)
    path.write_text(
        "name: Tester\n"
        "game: Half-Life\n"
        "Half-Life:\n"
        "  progression_mode: transitions\n"
        f"  map_shuffle: {shuffle}\n"
        f"  generation_difficulty: {difficulty}\n"
        "  half_life_chapters:\n" + listed,
        encoding="utf-8")


def generate(out: Path, seed: int | None) -> None:
    """Run in the Archipelago venv: Generate and Main, with the supported
    chapter check lifted, and the slot data kept as `slot_data.json`."""
    sys.path.insert(0, str(AP_SRC))
    import worlds  # noqa: F401  (registers every world)
    from worlds.half_life import HalfLifeWorld
    from worlds.half_life import options
    from worlds.half_life.data import CHAPTERS, SUPPORTED_CHAPTER_NAMES, campaign_of

    names = [c["name"] for c in CHAPTERS if campaign_of(c) == "half_life"]
    SUPPORTED_CHAPTER_NAMES["half_life"] = names
    options.HalfLifeChapters._valid_keys = frozenset(names)

    kept: dict = {}
    fill = HalfLifeWorld.fill_slot_data

    def keep(self):
        kept.update(fill(self))
        return kept

    HalfLifeWorld.fill_slot_data = keep

    import Generate
    from Main import main as ap_main
    sys.argv = ["Generate.py", "--player_files_path", str(out / "players"),
                "--outputpath", str(out), "--spoiler", "2"]
    if seed is not None:
        sys.argv += ["--seed", str(seed)]
    args, seed_number = Generate.main()
    ap_main(args, seed_number)
    (out / "slot_data.json").write_text(json.dumps(kept, indent=1, sort_keys=True),
                                        encoding="utf-8")


def labels(transitions: list[dict]) -> dict[str, str]:
    """`T<n>` per transition, numbered per map by id, as the harness labels."""
    out: dict[str, str] = {}
    by_map: dict[str, list[dict]] = {}
    for t in transitions:
        by_map.setdefault(t["map"], []).append(t)
    for ts in by_map.values():
        for n, t in enumerate(sorted(ts, key=lambda t: int(t["id"].split(":")[1])), 1):
            out[t["id"]] = f"T{n}"
    return out


def write_spoiler(out: Path, slot: dict, data: dict, chapters: list[str]) -> Path:
    by_id = {t["id"]: t for t in data["transitions"]}
    label = labels(data["transitions"])

    def where(tid: str) -> str:
        t = by_id.get(tid)
        if t is None:
            return f"{tid} (unknown)"
        at = " ".join(str(v) for v in t["at"])
        return (f"{tid:<14} {t['map']} {label[tid]:<4} {t['kind']:<9} at {at:<18}"
                f" vanilla to {t['to']}")

    lines = [f"Chapters: {', '.join(chapters)}",
             f"Shuffle: {slot.get('map_shuffle')}",
             f"Start map: {slot.get('start_map')}",
             f"Final boss: {slot.get('final_boss')}",
             "", "Pairs (either way):"]
    for a, b in slot.get("transition_pairs", []):
        lines += [f"  {where(a)}", f"    <> {where(b)}"]
    lines += ["", "One way (exit > arrival):"]
    for a, b in sorted(slot.get("one_way_transitions", {}).items()):
        lines += [f"  {where(a)}", f"    >  {where(b)}"]
    lines += ["", "Backtrack orbs (at > leads to):"]
    for a, b in sorted(slot.get("backtrack_orbs", {}).items()):
        lines += [f"  {where(a)}", f"    >  {where(b)}"]
    lines += ["", "Inert (does nothing):"]
    lines += [f"  {where(t)}" for t in slot.get("inert_transitions", [])]
    path = out / "transitions.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--chapters", required=True, metavar="A:B",
                        help="chapter range, inclusive, Black Mesa Inbound being 0")
    parser.add_argument("--shuffle", choices=SHUFFLES, default="area")
    parser.add_argument("--difficulty", choices=("standard", "chaotic"), default="standard")
    parser.add_argument("--seed", type=int, help="Archipelago seed number")
    parser.add_argument("--game-root", type=Path, default=GAME_ROOT)
    parser.add_argument("--no-host", action="store_true",
                        help="generate and write the spoiler only")
    parser.add_argument("--generate", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.generate is not None:  # the venv side
        generate(args.generate, args.seed)
        return 0

    data = json.loads(CAMPAIGN.read_text(encoding="utf-8"))
    chapters = pick(data, args.chapters)
    runid = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = OUT / runid
    write_yaml(out / "players" / "half_life.yaml", chapters, args.shuffle, args.difficulty)
    command = [str(AP_PYTHON), str(Path(__file__).resolve()), "--chapters", args.chapters,
               "--generate", str(out)]
    if args.seed is not None:
        command += ["--seed", str(args.seed)]
    if subprocess.run(command, cwd=AP_SRC).returncode != 0:
        print(f"Generation failed; see {out}.")
        return 1
    for archive in out.glob("AP_*.zip"):
        with zipfile.ZipFile(archive) as zf:
            for name in zf.namelist():
                if name.endswith("_Spoiler.txt"):
                    (out / name).write_bytes(zf.read(name))
    slot = json.loads((out / "slot_data.json").read_text(encoding="utf-8"))
    spoiler = write_spoiler(out, slot, data, chapters)
    print(f"Run {runid}: {spoiler}")
    if args.no_host:
        return 0
    return subprocess.run([sys.executable, str(REPO / "tests" / "aptest" / "aptest.py"),
                           "--game-root", str(args.game_root),
                           "--seed-file", str(out / "slot_data.json")]).returncode


if __name__ == "__main__":
    sys.exit(main())
