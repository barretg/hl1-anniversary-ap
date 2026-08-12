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


def test_traps_exist_and_are_classified_as_traps(campaign: dict) -> None:
    traps = [item for item in campaign["items"] if item.get("group") == "trap"]
    assert {item["name"] for item in traps} == {
        "Scientist Trap", "Headcrab Trap", "Butterfingers Trap"
    }
    for item in traps:
        assert item["classification"] == "trap", item["name"]
        assert item.get("weight", 0) > 0, item["name"]


def test_traps_are_handled_by_the_plugin(campaign: dict) -> None:
    """A trap the plugin does not know about arrives as a silent no-op."""
    source = (
        REPO / "apworld" / "half_life_sven" / "plugin" / "plugins"
        / "archipelago" / "ap_traps.as"
    ).read_text(encoding="utf-8")

    for item in campaign["items"]:
        if item.get("group") == "trap":
            assert f'"{item["name"]}"' in source, item["name"]


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


def test_some_mission_is_enterable_with_nothing(campaign: dict) -> None:
    """There must always be a legal starting mission.

    One mission is precollected, and every location in the game sits behind a
    mission entrance. If the only open mission were gated on a weapon or on the
    long jump module, sphere one would be empty and fill would have nowhere to
    put its first item. The world picks the starting mission from the ungated
    ones; this fails if a `CHAPTER_GATES` edit leaves none.
    """
    ungated = [
        chapter for chapter in campaign["chapters"]
        if not chapter["is_goal"]
        and not chapter["gates"].get("strict")
        and not chapter["gates"].get("always")
    ]
    assert ungated, "every mission is gated; no seed can start"


def test_charger_triggers_name_a_brush_model(campaign: dict) -> None:
    """`*N` is the only identity the BSP and the running game share."""
    chargers = [e for e in campaign["locations"] if e["trigger"]["type"] == "charger"]
    assert chargers

    for entry in chargers:
        trigger = entry["trigger"]
        assert trigger["classname"] in ("func_healthcharger", "func_recharge")
        assert trigger["model"].startswith("*")
        assert trigger["model"][1:].isdigit(), entry["name"]


def test_chargers_are_unique_within_a_map(campaign: dict) -> None:
    """Two locations on one model would make the second unreachable."""
    seen: set[tuple[str, str]] = set()
    for entry in campaign["locations"]:
        trigger = entry["trigger"]
        if trigger["type"] != "charger":
            continue
        key = (entry["map"], trigger["model"])
        assert key not in seen, entry["name"]
        seen.add(key)


def test_checkdata_charger_args_are_classname_and_model(
    campaign: dict, checkdata: list[list[str]]
) -> None:
    """Exactly what the plugin builds from the entity a player pressed +use on."""
    generated = {int(r[1]): r[4] for r in checkdata if r[0] == "L" and r[3] == "charger"}
    expected = {
        entry["id"]: f"{entry['trigger']['classname']}:{entry['trigger']['model']}"
        for entry in campaign["locations"]
        if entry["trigger"]["type"] == "charger"
    }
    assert generated == expected, "run: python tools/gen_checkdata.py"


def test_every_weapon_has_exactly_one_first_pickup(campaign: dict) -> None:
    """One check per weapon, at its vanilla first location -- not one per copy."""
    from campaign_layout import UNRANDOMISED_WEAPON_LOCATIONS, WEAPON_ITEMS

    expected_items = {**WEAPON_ITEMS, **UNRANDOMISED_WEAPON_LOCATIONS}
    weapon_locations = [
        entry for entry in campaign["locations"]
        if entry["trigger"]["type"] == "weapon_pickup"
    ]
    assert len(weapon_locations) == len(expected_items)

    covered = {
        classname
        for entry in weapon_locations
        for classname in entry["trigger"]["classnames"]
    }
    assert covered == {c for classnames in expected_items.values() for c in classnames}


def test_the_crowbar_is_a_location_but_never_an_item(campaign: dict) -> None:
    """You start with one; finding Half-Life's own is still worth a check."""
    names = [
        entry["name"] for entry in campaign["locations"]
        if entry["trigger"]["type"] == "weapon_pickup"
        and "weapon_crowbar" in entry["trigger"]["classnames"]
    ]
    assert names == ["First Crowbar"]
    assert "Crowbar" not in {item["name"] for item in campaign["items"]}


def test_first_pickups_are_at_the_earliest_map_holding_the_weapon(
    campaign: dict,
) -> None:
    """"Vanilla first location" is the whole point; a later map is a bug."""
    order = {
        map_name: (chapter["index"], position)
        for chapter in campaign["chapters"]
        for position, map_name in enumerate(chapter["maps"])
    }
    anchors = {
        entry["name"]: order[entry["map"]]
        for entry in campaign["locations"]
        if entry["trigger"]["type"] == "weapon_pickup"
    }
    # The crowbar and the glock are Half-Life's first two weapons, and nothing
    # should be anchored earlier than the mission that hands them out.
    assert anchors["First Crowbar"] <= anchors["First Glock"]
    assert anchors["First Shotgun"] < anchors["First RPG"]


def test_first_pickup_is_anchored_to_a_map_that_has_one(campaign: dict) -> None:
    """Logic hangs the check on this map, so a weapon had better be in it."""
    maps_by_chapter = {c["key"]: c["maps"] for c in campaign["chapters"]}

    for entry in campaign["locations"]:
        if entry["trigger"]["type"] != "weapon_pickup":
            continue
        # The anchor is the earliest map in campaign order holding the weapon, so
        # it must at least belong to the chapter the location was filed under.
        assert entry["map"] in maps_by_chapter[entry["chapter"]], entry["name"]
        assert entry["trigger"]["map"] == entry["map"], entry["name"]


def test_pickup_triggers_have_classnames(campaign: dict) -> None:
    for entry in campaign["locations"]:
        trigger = entry["trigger"]
        if trigger["type"] == "pickup":
            assert trigger["classnames"], entry["name"]


def test_optional_equipment_carries_the_classnames_it_gates(campaign: dict) -> None:
    """The client resolves item name -> classnames out of this data.

    `shuffle_longjump: false` is delivered to the plugin as the *classname* it
    should stop gating, not as an item the player owns, so the mapping has to be
    in campaign.json rather than assumed on either side.
    """
    optional = {
        entry["name"]: entry.get("classnames", ())
        for entry in campaign["items"]
        if entry.get("group") == "optional"
    }

    assert optional, "no optional equipment in the campaign data"
    for name, classnames in optional.items():
        assert classnames, name


def test_optional_equipment_is_gated_by_classname(
    campaign: dict, checkdata: list[list[str]]
) -> None:
    """Ungating can only cancel a gate that exists in the first place."""
    gated = {record[1] for record in checkdata if record[0] == "K"}

    for entry in campaign["items"]:
        if entry.get("group") != "optional":
            continue
        for classname in entry["classnames"]:
            assert classname in gated, classname
