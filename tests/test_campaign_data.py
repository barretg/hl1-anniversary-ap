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


def test_exactly_one_goal_chapter_per_campaign(campaign: dict) -> None:
    """Each campaign ends in its own finale, and each finale is a goal."""
    goals = {c["key"] for c in campaign["chapters"] if c["is_goal"]}
    declared = {c["goal_chapter"] for c in campaign["campaigns"]}
    assert goals == declared
    assert len(goals) == len(campaign["campaigns"])


def test_goal_chapters_have_no_unlock_item(campaign: dict) -> None:
    goals = {c["key"] for c in campaign["chapters"] if c["is_goal"]}
    chapter_items = [i for i in campaign["items"] if i.get("group") == "chapter"]
    assert not goals & {item["chapter"] for item in chapter_items}
    # Every other chapter does have one.
    assert len(chapter_items) == len(campaign["chapters"]) - len(goals)


def test_every_chapter_belongs_to_a_declared_campaign(campaign: dict) -> None:
    keys = {c["key"] for c in campaign["campaigns"]}
    listed = {k for c in campaign["campaigns"] for k in c["chapters"]}
    assert listed == {c["key"] for c in campaign["chapters"]}
    for chapter in campaign["chapters"]:
        assert chapter["campaign"] in keys, chapter["key"]


def test_portal_consoles_point_at_chapters_of_their_own_campaign(
    campaign: dict,
) -> None:
    """The plugin warps on a console press, so a wrong entry is a wrong mission."""
    campaign_of = {c["key"]: c["campaign"] for c in campaign["chapters"]}
    seen: set[str] = set()

    for entry in campaign["campaigns"]:
        for console, chapter_key in entry["consoles"].items():
            assert chapter_key in campaign_of, console
            assert campaign_of[chapter_key] == entry["key"], console
            # One console cannot open two missions.
            assert console not in seen, console
            seen.add(console)

        # Consoles are positional: the Nth console is the Nth mission.
        ordered = [
            key for key in entry["chapters"]
            if key in set(entry["consoles"].values())
        ]
        by_console = [entry["consoles"][c] for c in sorted(entry["consoles"])]
        assert sorted(by_console) == sorted(ordered), entry["key"]


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
    """Every gate names an item that can arrive, bar the deliberate exception.

    The crowbar is gated on an item name the pool never contains, which is what
    makes a `random_starting_weapon` seed able to take it away: see
    `test_the_crowbar_is_gated_but_starts_unlocked`.
    """
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

    Starting weapons are checked before gates, so by default the crowbar is
    yours. A seed that starts you with a wrench instead simply leaves it out of
    the starting list, and the gate then refuses it for the rest of the run
    because no item named "Crowbar" is ever in the pool.
    """
    starting = {r[1] for r in checkdata if r[0] == "S"}
    locked = {r[1]: r[2] for r in checkdata if r[0] == "K"}

    assert "weapon_crowbar" in starting
    assert locked.get("weapon_crowbar") == "Crowbar"
    assert "Crowbar" not in {item["name"] for item in campaign["items"]}


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


def test_every_weapon_has_one_first_pickup_per_campaign(campaign: dict) -> None:
    """One check per weapon per campaign, at that campaign's earliest copy.

    Not one across the whole seed: a campaign that ships a shotgun has a "first
    shotgun" of its own, or leaving Half-Life out would strand the check in a map
    the seed does not contain.
    """
    campaign_of = {c["key"]: c["campaign"] for c in campaign["chapters"]}
    seen: set[tuple[str, str]] = set()

    for entry in campaign["locations"]:
        if entry["trigger"]["type"] != "weapon_pickup":
            continue
        key = (campaign_of[entry["chapter"]], ",".join(sorted(entry["trigger"]["classnames"])))
        assert key not in seen, entry["name"]
        seen.add(key)


def test_the_crowbar_is_a_location_but_never_an_item(campaign: dict) -> None:
    """You start with one; finding the campaign's own is still worth a check."""
    names = [
        entry["name"] for entry in campaign["locations"]
        if entry["trigger"]["type"] == "weapon_pickup"
        and "weapon_crowbar" in entry["trigger"]["classnames"]
    ]
    # Half-Life's keeps its original wording; the rest name their campaign.
    assert "First Crowbar" in names
    assert len(names) == len(set(names))
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


def test_melee_starters_exist_in_their_campaigns_maps(campaign: dict) -> None:
    """`random_starting_weapon` picks from these, so they have to be real.

    A campaign that could open you with a weapon its own maps never contain would
    be handing out something the engine may not have loaded.
    """
    maps_by_campaign: dict[str, set[str]] = {}
    for chapter in campaign["chapters"]:
        maps_by_campaign.setdefault(chapter["campaign"], set()).update(chapter["maps"])

    weapon_maps = {
        classname: {
            entry["map"] for entry in campaign["locations"]
            if entry["trigger"]["type"] == "weapon_pickup"
            and classname in entry["trigger"]["classnames"]
        }
        for entry in campaign["campaigns"]
        for classnames in entry["melee"].values()
        for classname in classnames
    }

    for entry in campaign["campaigns"]:
        assert entry["melee"], entry["key"]
        for name, classnames in entry["melee"].items():
            anchored = set().union(*(weapon_maps[c] for c in classnames))
            assert anchored & maps_by_campaign[entry["key"]], f"{entry['key']}: {name}"


def test_shared_weapons_are_available_in_every_campaign_holding_them(
    campaign: dict,
) -> None:
    """Attributing a weapon to one campaign stranded it in the others.

    The shotgun is Half-Life's by declaration and everywhere by placement, so a
    seed without Half-Life still needs the item or every shotgun in it is refused
    for the whole run.
    """
    by_name = {entry["name"]: entry for entry in campaign["items"]}

    shotgun = by_name["Shotgun"]
    assert {"opposing_force", "blue_shift"} <= set(shotgun["campaigns"])
    # And a weapon only one campaign ships stays that campaign's alone.
    assert by_name["Displacer Cannon"]["campaigns"] == ["opposing_force"]
    # They Hunger carries Opposing Force's wrench, so it needs that item too.
    assert "they_hunger" in by_name["Pipe Wrench"]["campaigns"]


def test_script_registered_weapons_are_restricted_to_their_campaign(
    campaign: dict, checkdata: list[list[str]]
) -> None:
    """They Hunger's arsenal only exists while its own map script is running.

    Its weapons are custom entities registered by `scripts/maps/hunger/weapons/`
    rather than weapons the game ships, so `GiveNamedItem` on any other
    campaign's map has nothing to build. Every one of them must carry a rule
    saying where it may be handed over.
    """
    restricted = {r[1]: r[2].split(",") for r in checkdata if r[0] == "R"}
    assert restricted, "no restrictions emitted"

    hunger_classnames = {
        classname
        for entry in campaign["items"]
        if entry.get("group") == "weapon" and entry.get("campaign") == "they_hunger"
        for classname in entry["classnames"]
    }
    assert hunger_classnames <= set(restricted)
    for classname in hunger_classnames:
        assert restricted[classname] == ["they_hunger"], classname


def test_restricted_weapons_are_absent_from_every_logic_group(campaign: dict) -> None:
    """A weapon you cannot carry into a mission cannot satisfy its gate.

    Counting a tommy gun as "you have a gun" would let strict logic expect you to
    enter We've Got Hostiles holding something the engine will not give you there.
    """
    restricted = set(campaign["restricted_classnames"])
    grouped = {
        name for names in campaign["requirement_groups"].values() for name in names
    }

    for entry in campaign["items"]:
        if entry.get("group") != "weapon":
            continue
        if set(entry["classnames"]) & restricted:
            assert entry["name"] not in grouped, entry["name"]


def test_a_script_registered_melee_starter_belongs_to_its_own_campaign(
    campaign: dict,
) -> None:
    """They Hunger may open you with its spanner; nobody else may.

    A script-registered weapon does not exist outside its own maps, so starting
    with one means empty hands everywhere else. That is accepted for the campaign
    that owns the weapon -- it is only reachable when that campaign is in the
    seed -- but offering it from anywhere else would be a plain bug.
    """
    restricted = campaign["restricted_classnames"]

    for entry in campaign["campaigns"]:
        for name, classnames in entry["melee"].items():
            for classname in classnames:
                if classname in restricted:
                    assert restricted[classname] == [entry["key"]], f"{entry['key']}: {name}"


def test_every_campaign_can_open_with_a_weapon_that_works_everywhere(
    campaign: dict,
) -> None:
    """However the roll goes, a seed must be able to arm you across all of it."""
    restricted = set(campaign["restricted_classnames"])

    for entry in campaign["campaigns"]:
        portable = [
            name for name, classnames in entry["melee"].items()
            if not set(classnames) & restricted
        ]
        assert portable, entry["key"]


def test_no_item_or_check_exists_for_a_weapon_the_game_lacks(campaign: dict) -> None:
    """`weapon_knife` is placed in Opposing Force's maps but does not exist.

    It is in neither server.dll nor any map script in this build, so those
    entities never spawn. An item for it could never be granted and a check for it
    could never fire, which is exactly where fill would hide progression.
    """
    absent = "weapon_knife"

    for entry in campaign["items"]:
        assert absent not in entry.get("classnames", ()), entry["name"]

    for entry in campaign["locations"]:
        assert absent not in entry["trigger"].get("classnames", ()), entry["name"]
