"""The level transition table transitions mode is built on.

See .claude/TRANSITION_RANDO.md, 3.1 and 3.2. The BSP count test reads the
real install and skips without one; point `HL_GAME_ROOT` elsewhere if needed.
"""

from __future__ import annotations

import collections
import json
import math
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

from bsp_entities import load_map  # noqa: E402
from campaigns import CAMPAIGNS  # noqa: E402
from transitions_data import KINDS  # noqa: E402

CAMPAIGN_PATH = REPO / "apworld" / "half_life" / "data" / "campaign.json"
IDS_PATH = REPO / "apworld" / "half_life" / "data" / "ids.json"
CHECKDATA_PATH = (
    REPO / "apworld" / "half_life" / "mod" / "files" / "archipelago" / "checkdata.txt"
)
GAME_ROOT = Path(os.environ.get(
    "HL_GAME_ROOT", "/games/SteamLibrary/steamapps/common/Half-Life"
))

# The engine's MAX_LEVEL_CONNECTIONS. In transitions mode every transition
# gets its own synthetic landmark, and a backtrack orb and the hub teleporter
# can add two more.
MAX_LEVEL_CONNECTIONS = 16
RESERVED_CONNECTIONS = 2


@pytest.fixture(scope="module")
def transitions() -> list[dict]:
    return json.loads(CAMPAIGN_PATH.read_text(encoding="utf-8"))["transitions"]


@pytest.fixture(scope="module")
def by_id(transitions: list[dict]) -> dict[str, dict]:
    return {t["id"]: t for t in transitions}


def test_ids_are_unique_and_ordered(transitions: list[dict]) -> None:
    seen: dict[str, int] = collections.defaultdict(int)
    for t in transitions:
        assert t["id"] == f"{t['map']}:{seen[t['map']]}"
        seen[t["map"]] += 1


@pytest.mark.parametrize("campaign", CAMPAIGNS, ids=lambda c: c.key)
def test_one_record_per_changelevel_entity(campaign, transitions: list[dict]) -> None:
    if not (GAME_ROOT / campaign.detect).is_file():
        pytest.skip(f"{campaign.name} not installed under {GAME_ROOT}")
    counts = collections.Counter(t["map"] for t in transitions)
    for map_name in campaign.maps:
        ents = load_map(GAME_ROOT / campaign.game_dir / "maps" / f"{map_name}.bsp")
        expected = sum(1 for e in ents if e.get("classname") == "trigger_changelevel")
        assert counts[map_name] == expected, map_name


def test_partners_pair_back(by_id: dict[str, dict]) -> None:
    for t in by_id.values():
        if not t["partner"]:
            continue
        other = by_id[t["partner"]]
        assert other["partner"] == t["id"], t["id"]
        assert other["map"] == t["to"] and other["to"] == t["map"], t["id"]
        assert other["landmark"] == t["landmark"], t["id"]


def test_several_triggers_into_one_neighbour_each_get_their_own(by_id: dict) -> None:
    """Blast Pit's three doors between `c1a4b` and `c1a4i` share no landmark,
    and Unforeseen Consequences' two between `c1a1c` and `c1a1d` share a map
    pair: each must pair with its own counterpart, not all with one."""
    for here, there in (("c1a4b", "c1a4i"), ("c1a1c", "c1a1d")):
        ours = [t for t in by_id.values() if t["map"] == here and t["to"] == there]
        assert len(ours) > 1
        partners = [t["partner"] for t in ours]
        assert all(partners) and len(set(partners)) == len(partners), here


def test_frames_are_sane(transitions: list[dict]) -> None:
    for t in transitions:
        frame = t["frame"]
        assert 0 <= frame["yaw"] < 360, t["id"]
        # The crossing direction is a unit vector by construction; a slab's
        # is one of the four axis directions.
        direction = (math.cos(math.radians(frame["yaw"])),
                     math.sin(math.radians(frame["yaw"])))
        assert math.isclose(math.hypot(*direction), 1.0)
        if "horizontal" not in t.get("flags", ()):
            assert frame["yaw"] in (0.0, 90.0, 180.0, 270.0), t["id"]
        assert frame["width"] >= 0 and frame["height"] >= 0, t["id"]
        assert len(frame["origin"]) == 3
        assert t["kind"] in KINDS, t["id"]


def test_level_connection_limit(transitions: list[dict]) -> None:
    per_map = collections.Counter(t["map"] for t in transitions)
    for map_name, count in per_map.items():
        assert count + RESERVED_CONNECTIONS <= MAX_LEVEL_CONNECTIONS, map_name


def test_overrides_name_real_transitions(by_id: dict[str, dict]) -> None:
    for campaign in CAMPAIGNS:
        for transition_id in campaign.transition_overrides:
            assert transition_id in by_id, transition_id


def test_ids_are_pinned(transitions: list[dict]) -> None:
    """A renumbered map fails the build; this catches a committed table that
    was built without the registry."""
    pinned = json.loads(IDS_PATH.read_text(encoding="utf-8"))["transitions"]
    for t in transitions:
        signature = "{}|{}|{}".format(t["to"], t["landmark"],
                                      " ".join(str(v) for v in t["at"]))
        assert pinned.get(t["id"]) == signature, t["id"]


def test_boss_exits_are_transitions(by_id: dict[str, dict]) -> None:
    for campaign in CAMPAIGNS:
        boss, ending = campaign.boss_exit
        assert any(t["map"] == boss and t["to"] == ending for t in by_id.values()), \
            campaign.key


def test_checkdata_carries_every_transition(transitions: list[dict]) -> None:
    lines = [line.split("|") for line in
             CHECKDATA_PATH.read_text(encoding="utf-8").splitlines()
             if line.startswith("E|")]
    assert [f[1] for f in lines] == [t["id"] for t in transitions]
    assert all(len(f) == 14 for f in lines)
