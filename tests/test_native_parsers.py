"""The dll's engine-free parsers, built for the host and run against what the
client writes and what the build ships. Skipped without a host C++ compiler."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "game" / "src"
CHECKDATA = ROOT / "apworld" / "half_life" / "mod" / "files" / "archipelago" / "checkdata.txt"
CAMPAIGN = ROOT / "apworld" / "half_life" / "data" / "campaign.json"

sys.path.insert(0, str(ROOT / "apworld" / "half_life"))

from client.bridge import Bridge  # noqa: E402

COMPILER = shutil.which("clang++") or shutil.which("g++")
pytestmark = pytest.mark.skipif(COMPILER is None, reason="no host C++ compiler")


@pytest.fixture(scope="module")
def driver(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("native") / "parse_driver"
    subprocess.run(
        [COMPILER, "-std=c++17", "-O0", f"-I{SRC}", "-o", str(out),
         str(ROOT / "tests" / "native" / "parse_driver.cpp"),
         str(SRC / "ap_bridge.cpp"), str(SRC / "ap_checkdata.cpp"), str(SRC / "ap_text.cpp")],
        check=True, capture_output=True)
    return out


def run(driver: Path, *args: str) -> dict[str, str]:
    result = subprocess.run([str(driver), *args], capture_output=True, text=True, check=True)
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


SLOT_DATA = {
    "progression_mode": "transitions",
    "map_shuffle": "total",
    "start_map": "c1a0",
    "transition_chapters": ["c1a0", "c4a3"],
    "transition_pairs": [["c1a0:1", "c4a3:0"], ["c1a0d:0", "c4a3a:2"]],
    "inert_transitions": ["c1a0:0"],
    "one_way_transitions": {"c4a3b:1": "c1a0d:1"},
    "backtrack_orbs": {"c1a0d:1": "c4a3b:1"},
    "transition_hub": True,
    "ending_map": "c5a1",
    "final_boss": "c4a3",
    "boss_exits": {"half_life": "c4a3"},
}


def write(tmp_path: Path, transitions: dict | None) -> None:
    Bridge(tmp_path).write_snapshot(connected=True, chapters=["c1a0", "c4a3"], items=[],
                                    goal_open=False, death_link=False,
                                    transitions=transitions)


def test_a_transitions_snapshot_parses(driver: Path, tmp_path: Path) -> None:
    write(tmp_path, SLOT_DATA)
    got = run(driver, "bridge", str(tmp_path))
    assert got["transitions_mode"] == "1"
    assert got["map_shuffle"] == "total"
    assert got["start_map"] == "c1a0"
    assert got["ending_map"] == "c5a1"
    assert got["final_boss"] == "c4a3"
    assert got["transition_hub"] == "1"
    assert got["transition_chapters"] == "2"
    assert got["boss_maps"] == "1"
    assert got["inert"] == "1"
    assert got["pairs"] == "c1a0:1>c4a3:0;c1a0d:0>c4a3a:2;"
    assert got["one_way"] == "c4a3b:1>c1a0d:1;"
    assert got["orbs"] == "c1a0d:1>c4a3b:1;"


def test_a_hub_snapshot_has_no_transitions(driver: Path, tmp_path: Path) -> None:
    write(tmp_path, None)
    got = run(driver, "bridge", str(tmp_path))
    assert got["transitions_mode"] == "0"
    assert got["pairs"] == "" and got["inert"] == "0"
    assert "progression_mode" not in (tmp_path / "ap_in.txt").read_text(encoding="utf-8")


def test_the_shipped_checkdata_carries_every_transition(driver: Path) -> None:
    transitions = json.loads(CAMPAIGN.read_text(encoding="utf-8"))["transitions"]
    sample = next(t for t in transitions if t["partner"] and t["two_way"])
    got = run(driver, "checkdata", str(CHECKDATA), sample["id"])
    assert int(got["transitions"]) == len(transitions)
    line = (subprocess.run([str(driver), "checkdata", str(CHECKDATA), sample["id"]],
                           capture_output=True, text=True, check=True).stdout.splitlines()[1])
    fields = line.split("|")
    assert fields[:6] == [sample["id"], sample["map"], sample["to"], sample["landmark"],
                          sample["kind"], sample["partner"]]
    assert fields[6] == "1"


COUNT_DRIVER = """
#include <cstdio>
#include "ap_checkdata.h"
int main(int argc, char** argv) {
    ap::CheckData data;
    if (!data.Load(argv[1])) { std::printf("load failed\\n"); return 1; }
    std::printf("locations=%zu\\nchapters=%zu\\n", data.locations.size(), data.chapters.size());
    return 0;
}
"""


def last_release() -> str | None:
    tags = subprocess.run(["git", "-C", str(ROOT), "tag", "--sort=-creatordate"],
                          capture_output=True, text=True).stdout.split()
    return next((t for t in tags if t.startswith("v")), None)


def build_counter(src: Path, out: Path) -> Path:
    (out.parent / "count.cpp").write_text(COUNT_DRIVER, encoding="utf-8")
    subprocess.run([COMPILER, "-std=c++17", f"-I{src}", "-o", str(out), str(out.parent / "count.cpp"),
                    str(src / "ap_checkdata.cpp"), str(src / "ap_text.cpp")],
                   check=True, capture_output=True)
    return out


def test_the_last_release_reads_the_new_checkdata(tmp_path: Path) -> None:
    """Backwards compatibility: a released dll meeting this checkdata.txt (the
    `E` records it has never heard of) loads it and sees the same locations."""
    tag = last_release()
    if tag is None:
        pytest.skip("no release tag")
    old = tmp_path / "old"
    old.mkdir()
    for name in ("ap_checkdata.cpp", "ap_checkdata.h", "ap_text.cpp", "ap_text.h"):
        shown = subprocess.run(["git", "-C", str(ROOT), "show", f"{tag}:game/src/{name}"],
                               capture_output=True, text=True)
        if shown.returncode != 0:
            pytest.skip(f"{tag} has no {name}")
        (old / name).write_text(shown.stdout, encoding="utf-8")
    (tmp_path / "new").mkdir()
    then = run(build_counter(old, old / "count"), str(CHECKDATA))
    now = run(build_counter(SRC, tmp_path / "new" / "count"), str(CHECKDATA))
    assert int(then["locations"]) > 0
    assert then == now


def test_transition_ids_survive_the_snapshot_format() -> None:
    """Pairs are `a,b` joined with `;`, on a `key=value` line."""
    transitions = json.loads(CAMPAIGN.read_text(encoding="utf-8"))["transitions"]
    for t in transitions:
        assert not set(t["id"]) & set(",;=|\n "), t["id"]
