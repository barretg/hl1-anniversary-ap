"""Consistency between the generated campaign data and the game's data file.

The whole point of generating both from one source is that the game side and the
apworld can never disagree about a location id. These tests fail loudly if
someone edits one without regenerating the other.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

CAMPAIGN_PATH = REPO / "apworld" / "half_life" / "data" / "campaign.json"
CHECKDATA_PATH = (
    REPO / "apworld" / "half_life" / "mod" / "files"
    / "archipelago" / "checkdata.txt"
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
    goals = [c["key"] for c in campaign["chapters"] if c["is_goal"]]
    assert goals == [campaign["goal_chapter"]]


def test_the_goal_chapter_has_no_unlock_item(campaign: dict) -> None:
    """Nothing unlocks the finale; finishing missions does."""
    chapter_items = [i for i in campaign["items"] if i.get("group") == "chapter"]
    assert campaign["goal_chapter"] not in {item["chapter"] for item in chapter_items}
    # Every other mission does have one.
    assert len(chapter_items) == len(campaign["chapters"]) - 1


def test_only_the_finale_completes_on_arrival(campaign: dict) -> None:
    """Every other mission is finished by walking on out of it.

    Arriving on a mission's last map is not finishing it: the map list is in
    reach order, and the last entry is often a dead end the player walks back out
    of -- `c1a1d` in Unforeseen Consequences is a side room, and treating arrival
    there as completion handed the mission over halfway through.

    The finale is the exception because nothing changelevels out of `c5a1`, so
    arriving is the only signal there is. If this ever fails for another chapter,
    that chapter has no forward exit and the map table is wrong.
    """
    arrival = [c["key"] for c in campaign["chapters"] if c["complete_on_arrival"]]
    assert arrival == [campaign["goal_chapter"]]


def test_checkdata_carries_the_completion_rule(
    campaign: dict, checkdata: list[list[str]]
) -> None:
    """The game reads this off the `C` record and has no other way to know."""
    generated = {r[2]: r[6] for r in checkdata if r[0] == "C" and len(r) >= 7}
    expected = {
        c["key"]: "1" if c["complete_on_arrival"] else "0"
        for c in campaign["chapters"]
    }
    assert generated == expected, "run: python tools/gen_checkdata.py"


def test_the_data_version_covers_item_ids(campaign: dict) -> None:
    """The fingerprint has to be taken after every id is assigned.

    It was not: `data_version` was computed while the registry held locations but
    no items, so an unchanged generator produced a different version on its
    second run. In game that reads as the apworld and the mod being different
    builds, and checks stop.
    """
    import json as _json
    from build_campaign_data import IdRegistry

    registry = IdRegistry(REPO / "apworld" / "half_life" / "data" / "ids.json")
    assert campaign["data_version"] == registry.fingerprint()

    # And the registry really does contain the item ids, so the test above is
    # not passing on an empty coincidence.
    ids = _json.loads(
        (REPO / "apworld" / "half_life" / "data" / "ids.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(ids["items"]) == len(campaign["items"])


def test_the_intro_chapter_is_a_real_mission(campaign: dict) -> None:
    """`exclude_intro_missions` drops it by key, so a stale key drops nothing."""
    keys = {c["key"] for c in campaign["chapters"]}
    assert campaign["intro_chapter"] in keys
    assert campaign["intro_chapter"] != campaign["goal_chapter"]


def test_maps_belong_to_exactly_one_chapter(campaign: dict) -> None:
    """A map in two missions would give one arrival two owners."""
    seen: set[str] = set()
    for chapter in campaign["chapters"]:
        for map_name in chapter["maps"]:
            assert map_name not in seen, map_name
            seen.add(map_name)


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


def test_checkdata_names_the_goal_chapter(campaign: dict, checkdata: list[list[str]]) -> None:
    """The game seals it on a count rather than on an item, so it has to know."""
    goals = [r[1] for r in checkdata if r[0] == "G"]
    assert goals == [campaign["goal_chapter"]], "run: python tools/gen_checkdata.py"


def test_checkdata_locked_classnames_map_to_real_items(
    campaign: dict, checkdata: list[list[str]]
) -> None:
    """Every gate names an item that can arrive, bar the deliberate exception."""
    from campaign_layout import UNRANDOMISED_WEAPON_LOCATIONS

    names = {item["name"] for item in campaign["items"]}
    unreachable = set(UNRANDOMISED_WEAPON_LOCATIONS)
    locked = [(r[1], r[2]) for r in checkdata if r[0] == "K"]
    assert locked
    for classname, item_name in locked:
        assert item_name in names or item_name in unreachable, classname


def test_the_crowbar_is_gated_but_starts_unlocked(
    campaign: dict, checkdata: list[list[str]]
) -> None:
    """Both, and that pair is the mechanism rather than a contradiction.

    Starting weapons are checked before gates, so the crowbar is always yours.
    The gate exists so that the table is the single answer to "is this pickup
    gated", with no classname falling through it unlisted.
    """
    starting = {r[1] for r in checkdata if r[0] == "S"}
    locked = {r[1]: r[2] for r in checkdata if r[0] == "K"}

    assert "weapon_crowbar" in starting
    assert locked.get("weapon_crowbar") == "Crowbar"
    assert "Crowbar" not in {item["name"] for item in campaign["items"]}


def test_every_map_has_a_reached_location(campaign: dict) -> None:
    """One check per map is the backbone of the location set."""
    reached = {
        entry["map"] for entry in campaign["locations"]
        if entry["trigger"]["type"] == "map_reached"
    }
    all_maps = {m for chapter in campaign["chapters"] for m in chapter["maps"]}
    assert reached == all_maps


def test_checkdata_fields_contain_no_delimiters(checkdata: list[list[str]]) -> None:
    """A '|' inside a name would desync the parser on the game side."""
    for record in checkdata:
        assert all("|" not in field for field in record)


def test_some_mission_is_enterable_with_nothing(campaign: dict) -> None:
    """There must always be a legal starting mission.

    One mission is precollected, and every location in the game sits behind a
    mission entrance. If the only open mission were gated on a weapon or on the
    long jump module, sphere one would be empty and fill would have nowhere to
    put its first item.
    """
    ungated = [
        chapter for chapter in campaign["chapters"]
        if not chapter["is_goal"]
        and not chapter["gates"].get("strict")
        and not chapter["gates"].get("always")
    ]
    assert ungated, "every mission is gated; no seed can start"


def test_a_mission_survives_excluding_the_intro(campaign: dict) -> None:
    """`exclude_intro_missions` must not take the only legal start."""
    ungated = [
        chapter for chapter in campaign["chapters"]
        if not chapter["is_goal"]
        and chapter["key"] != campaign["intro_chapter"]
        and not chapter["gates"].get("strict")
        and not chapter["gates"].get("always")
    ]
    assert ungated, "no legal start once the intro is excluded"


# --- chargers -------------------------------------------------------------


def test_charger_triggers_are_keyed_by_position(campaign: dict) -> None:
    """Position, never brush model index.

    Valve recompiles single-player maps from time to time -- the anniversary
    update edited several -- and a recompile renumbers brush models, which would
    silently repoint every charger id in that map. The failure mode is chargers
    that quietly never fire, which is the hardest class of bug to notice.
    """
    chargers = [e for e in campaign["locations"] if e["trigger"]["type"] == "charger"]
    assert chargers

    for entry in chargers:
        trigger = entry["trigger"]
        assert trigger["classname"] in ("func_healthcharger", "func_recharge")
        assert "model" not in trigger, entry["name"]
        parts = trigger["at"].split()
        assert len(parts) == 3, entry["name"]
        for value in parts:
            assert value.lstrip("-").isdigit(), entry["name"]


def test_charger_keys_are_snapped_to_the_agreed_grid(campaign: dict) -> None:
    """Both halves round the same way or nothing ever matches."""
    from campaign_layout import CHARGER_POSITION_GRID

    for entry in campaign["locations"]:
        trigger = entry["trigger"]
        if trigger["type"] != "charger":
            continue
        for value in trigger["at"].split():
            assert int(value) % CHARGER_POSITION_GRID == 0, entry["name"]


def test_chargers_are_unique_within_a_map(campaign: dict) -> None:
    """Two units the game cannot tell apart would strand the second."""
    seen: set[tuple[str, str, str]] = set()
    for entry in campaign["locations"]:
        trigger = entry["trigger"]
        if trigger["type"] != "charger":
            continue
        key = (entry["map"], trigger["classname"], trigger["at"])
        assert key not in seen, entry["name"]
        seen.add(key)


def test_a_charger_key_is_near_its_own_position(campaign: dict) -> None:
    """The rounded key has to be the same unit the position points at."""
    from campaign_layout import CHARGER_POSITION_GRID

    for entry in campaign["locations"]:
        trigger = entry["trigger"]
        if trigger["type"] != "charger":
            continue
        at = [int(v) for v in trigger["at"].split()]
        for rounded, exact in zip(at, entry["position"]):
            assert abs(rounded - exact) <= CHARGER_POSITION_GRID, entry["name"]


def test_checkdata_charger_args_are_classname_and_position(
    campaign: dict, checkdata: list[list[str]]
) -> None:
    """Exactly what the game builds from the entity a player pressed +use on."""
    generated = {int(r[1]): r[4] for r in checkdata if r[0] == "L" and r[3] == "charger"}
    expected = {
        entry["id"]: f"{entry['trigger']['classname']}@{entry['trigger']['at']}"
        for entry in campaign["locations"]
        if entry["trigger"]["type"] == "charger"
    }
    assert generated == expected, "run: python tools/gen_checkdata.py"


# --- weapons --------------------------------------------------------------


def test_every_weapon_has_exactly_one_first_pickup(campaign: dict) -> None:
    """One check per weapon for the whole run, at its earliest copy."""
    seen: set[str] = set()
    for entry in campaign["locations"]:
        if entry["trigger"]["type"] != "weapon_pickup":
            continue
        key = ",".join(sorted(entry["trigger"]["classnames"]))
        assert key not in seen, entry["name"]
        seen.add(key)


def test_the_crowbar_is_a_location_but_never_an_item(campaign: dict) -> None:
    """You start with one; finding the campaign's own is still worth a check."""
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
    # The crowbar and the glock are the first two weapons Half-Life hands over,
    # and the heavy weapons come much later.
    assert anchors["First Crowbar"] <= anchors["First Glock"]
    assert anchors["First Shotgun"] < anchors["First RPG"]
    assert anchors["First Glock"] < anchors["First Gluon Gun"]


def test_first_pickup_is_anchored_to_a_map_that_has_one(campaign: dict) -> None:
    """Logic hangs the check on this map, so a weapon had better be in it."""
    maps_by_chapter = {c["key"]: c["maps"] for c in campaign["chapters"]}

    for entry in campaign["locations"]:
        if entry["trigger"]["type"] != "weapon_pickup":
            continue
        assert entry["map"] in maps_by_chapter[entry["chapter"]], entry["name"]
        assert entry["trigger"]["map"] == entry["map"], entry["name"]


def test_both_spellings_of_a_weapon_unlock_together(campaign: dict) -> None:
    """Retail ships two classnames for a few weapons and its maps use both.

    Gating one spelling and not the other would leave half the pistols in the
    game refused for the whole run, or half of them free.
    """
    by_name = {entry["name"]: entry for entry in campaign["items"]}

    assert set(by_name["Glock"]["classnames"]) == {"weapon_glock", "weapon_9mmhandgun"}
    assert set(by_name["MP5"]["classnames"]) == {"weapon_mp5", "weapon_9mmAR"}
    assert set(by_name[".357 Magnum"]["classnames"]) == {"weapon_357", "weapon_python"}


def test_no_sven_only_weapon_survived_the_port(campaign: dict) -> None:
    """Sven Co-op's own spellings do not exist in retail and could never fire."""
    absent = {"weapon_m16", "weapon_medkit", "weapon_pipewrench", "weapon_spanner"}

    for entry in campaign["items"]:
        assert not absent & set(entry.get("classnames", ())), entry["name"]
    for entry in campaign["locations"]:
        assert not absent & set(entry["trigger"].get("classnames", ())), entry["name"]


def test_optional_equipment_carries_the_classnames_it_gates(campaign: dict) -> None:
    """The client resolves item name -> classnames out of this data.

    `shuffle_longjump: false` is delivered to the game as the *classname* it
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


# --- positions ------------------------------------------------------------


def test_placeable_locations_carry_a_position(campaign: dict) -> None:
    """`ap_find` can only point at a check that knows where it is.

    Chargers and weapon pickups are somewhere; reaching a map or finishing a
    mission is not a place, so those carry nothing and `ap_find` says so.
    """
    for entry in campaign["locations"]:
        kind = entry["trigger"]["type"]
        if kind in ("charger", "weapon_pickup"):
            assert "position" in entry, entry["name"]
            assert len(entry["position"]) == 3, entry["name"]
            assert all(isinstance(v, int) for v in entry["position"]), entry["name"]
        else:
            assert "position" not in entry, entry["name"]


def test_checkdata_carries_the_same_positions(
    campaign: dict, checkdata: list[list[str]]
) -> None:
    generated = {
        int(r[1]): r[6] for r in checkdata if r[0] == "L" and len(r) >= 7
    }
    expected = {
        entry["id"]: " ".join(str(v) for v in entry["position"])
        for entry in campaign["locations"]
        if "position" in entry
    }
    assert generated == expected, "run: python tools/gen_checkdata.py"


def test_positions_are_inside_their_map(campaign: dict) -> None:
    """A charger at the origin usually means the brush lookup silently failed."""
    at_origin = [
        entry["name"] for entry in campaign["locations"]
        if entry.get("position") == [0, 0, 0]
    ]
    assert not at_origin, at_origin


# --- the shape of the campaign -------------------------------------------


def test_the_campaign_is_retail_half_life(campaign: dict) -> None:
    """Retail map names, not the Sven Co-op conversion's.

    A stray `hl_c07_a1` would mean the layout table was half-ported, and the
    generator would happily produce a world for maps this game does not have.
    """
    maps = [m for chapter in campaign["chapters"] for m in chapter["maps"]]
    assert maps[0] == "c0a0"
    assert maps[-1] == "c5a1"
    for map_name in maps:
        assert not map_name.startswith("hl_"), map_name


def test_the_hazard_course_is_not_in_the_campaign(campaign: dict) -> None:
    """A training course rather than a mission, and nothing changelevels to it."""
    maps = {m for chapter in campaign["chapters"] for m in chapter["maps"]}
    assert not any(m.startswith("t0a0") for m in maps)
