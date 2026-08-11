"""Consistency between the generated campaign data and the plugin's data file.

The whole point of generating both from one source is that the AngelScript side
and the apworld can never disagree about a location id. These tests fail loudly
if someone edits one without regenerating the other.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

CAMPAIGN_PATH = REPO / "apworld" / "half_life_sven" / "data" / "campaign.json"
CHECKDATA_PATH = (
    REPO / "apworld" / "half_life_sven" / "plugin"
    / "plugins" / "store" / "archipelago" / "checkdata.txt"
)


@pytest.fixture(scope="module")
def campaign() -> dict:
    return json.loads(CAMPAIGN_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def checkdata() -> list[list[str]]:
    records = []
    for line in CHECKDATA_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            records.append(line.split("|"))
    return records


def test_location_ids_are_unique(campaign: dict) -> None:
    ids = [entry["id"] for entry in campaign["locations"]]
    assert len(ids) == len(set(ids))


def test_location_names_are_unique(campaign: dict) -> None:
    names = [entry["name"] for entry in campaign["locations"]]
    assert len(names) == len(set(names))


def test_item_ids_and_names_are_unique(campaign: dict) -> None:
    ids = [entry["id"] for entry in campaign["items"]]
    names = [entry["name"] for entry in campaign["items"]]
    assert len(ids) == len(set(ids))
    assert len(names) == len(set(names))


def test_item_and_location_id_spaces_do_not_overlap(campaign: dict) -> None:
    item_ids = {entry["id"] for entry in campaign["items"]}
    location_ids = {entry["id"] for entry in campaign["locations"]}
    assert not item_ids & location_ids


def test_exactly_one_goal_chapter(campaign: dict) -> None:
    assert sum(1 for chapter in campaign["chapters"] if chapter["is_goal"]) == 1


def test_goal_chapter_has_no_unlock_item(campaign: dict) -> None:
    goal = next(c["key"] for c in campaign["chapters"] if c["is_goal"])
    chapter_items = [i for i in campaign["items"] if i.get("group") == "chapter"]
    assert goal not in {item["chapter"] for item in chapter_items}
    # Every other chapter does have one.
    assert len(chapter_items) == len(campaign["chapters"]) - 1


def test_every_chapter_has_a_completion_location(campaign: dict) -> None:
    completions = {
        entry["trigger"]["chapter"]
        for entry in campaign["locations"]
        if entry["trigger"]["type"] == "chapter_complete"
    }
    assert completions == {chapter["key"] for chapter in campaign["chapters"]}


def test_every_location_belongs_to_a_map_of_its_chapter(campaign: dict) -> None:
    maps_by_chapter = {c["key"]: set(c["maps"]) for c in campaign["chapters"]}
    for entry in campaign["locations"]:
        assert entry["map"] in maps_by_chapter[entry["chapter"]], entry["name"]


def test_locations_outnumber_progression_items(campaign: dict) -> None:
    progression = [i for i in campaign["items"] if i["classification"] == "progression"]
    assert len(campaign["locations"]) > len(progression)


def test_requirement_groups_reference_real_items(campaign: dict) -> None:
    names = {item["name"] for item in campaign["items"]}
    for group, members in campaign["requirement_groups"].items():
        assert set(members) <= names, group


def test_location_requirements_reference_real_groups(campaign: dict) -> None:
    groups = set(campaign["requirement_groups"])
    for entry in campaign["locations"]:
        if "requires" in entry:
            assert entry["requires"] in groups, entry["name"]


def test_chapter_gates_reference_real_groups(campaign: dict) -> None:
    groups = set(campaign["requirement_groups"])
    for chapter in campaign["chapters"]:
        for name in chapter["gates"].get("strict", []):
            assert name in groups, chapter["key"]
        for name in chapter["gates"].get("always", []):
            assert name in ("longjump", "suit"), chapter["key"]


# --- checkdata.txt must mirror campaign.json ------------------------------


def test_checkdata_has_every_location(campaign: dict, checkdata: list[list[str]]) -> None:
    generated = {int(r[1]): r[5] for r in checkdata if r[0] == "L"}
    expected = {entry["id"]: entry["name"] for entry in campaign["locations"]}
    assert generated == expected, "run: python tools/gen_checkdata.py"


def test_checkdata_has_every_chapter(campaign: dict, checkdata: list[list[str]]) -> None:
    generated = {r[2]: r[4].split(",") for r in checkdata if r[0] == "C"}
    expected = {chapter["key"]: chapter["maps"] for chapter in campaign["chapters"]}
    assert generated == expected, "run: python tools/gen_checkdata.py"


def test_checkdata_locked_classnames_map_to_real_items(
    campaign: dict, checkdata: list[list[str]]
) -> None:
    names = {item["name"] for item in campaign["items"]}
    locked = [(r[1], r[2]) for r in checkdata if r[0] == "K"]
    assert locked
    for classname, item_name in locked:
        assert item_name in names, classname


def test_crowbar_is_never_randomised(checkdata: list[list[str]]) -> None:
    starting = {r[1] for r in checkdata if r[0] == "S"}
    locked = {r[1] for r in checkdata if r[0] == "K"}

    assert "weapon_crowbar" in starting
    assert "weapon_crowbar" not in locked


def test_every_map_has_a_reached_location(campaign: dict) -> None:
    """One check per map division is the whole location set right now."""
    reached = {
        entry["map"] for entry in campaign["locations"]
        if entry["trigger"]["type"] == "map_reached"
    }
    all_maps = {m for chapter in campaign["chapters"] for m in chapter["maps"]}
    assert reached == all_maps


def test_checkdata_fields_contain_no_delimiters(checkdata: list[list[str]]) -> None:
    """A '|' inside a name would desync the AngelScript parser."""
    for record in checkdata:
        assert all("|" not in field for field in record)


def test_pickup_triggers_have_classnames(campaign: dict) -> None:
    for entry in campaign["locations"]:
        trigger = entry["trigger"]
        if trigger["type"] == "pickup":
            assert trigger["classnames"], entry["name"]
