"""Consistency between the generated campaign data and the plugin's data file.

The whole point of generating both from one source is that the AngelScript side
and the apworld can never disagree about a location id. These tests fail loudly
if someone edits one without regenerating the other.
"""

from __future__ import annotations

import json
import re
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

        # Consoles are positional and in campaign order: the Nth console opens
        # the Nth mission that has one. Ordered by the number in the name, not
        # the name -- Half-Life's are unpadded, so `hl_ch10` sorts before
        # `hl_ch2` as text.
        def console_number(name: str) -> int:
            digits = re.search(r"(\d+)$", name)
            return int(digits.group(1)) if digits else -1

        wired = set(entry["consoles"].values())
        ordered = [key for key in entry["chapters"] if key in wired]
        by_console = [
            entry["consoles"][c] for c in sorted(entry["consoles"], key=console_number)
        ]
        assert by_console == ordered, entry["key"]


def test_no_console_opens_an_intro_mission(campaign: dict) -> None:
    """The hub has no panel for a campaign's intro; `!warp` is the only way in.

    Half-Life's hub starts at Anomalous Materials, and Opposing Force's and Blue
    Shift's start one past their intro the same way. Wiring the consoles as
    though they covered the intro too put every panel one mission early, so the
    one labelled Welcome To Black Mesa dropped you into boot camp.
    """
    for entry in campaign["campaigns"]:
        intro = entry.get("intro_chapter")
        if not intro:
            continue
        assert intro not in entry["consoles"].values(), entry["key"]


def test_a_campaign_never_claims_more_consoles_than_the_hub_has(
    campaign: dict,
) -> None:
    """Missions may lack a console; consoles may never lack a mission.

    An intro has none by design, and Opposing Force's Crush Depth has none either
    -- the hub simply has no `of_ch06`. What must never happen is a console
    listed twice or pointing past the end of the mission list, which is how the
    panels came to be off by one.
    """
    counts = {"half_life": 17, "opposing_force": 10, "blue_shift": 6, "they_hunger": 3}

    for entry in campaign["campaigns"]:
        assert len(entry["consoles"]) == counts[entry["key"]], entry["key"]
        assert len(set(entry["consoles"].values())) == len(entry["consoles"])
        assert set(entry["consoles"].values()) <= set(entry["chapters"])


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
    """Two locations the plugin cannot tell apart would strand the second.

    Identity is the brush model, plus the origin when a mapper has reused one
    brush for two units -- `ba_canal1` builds a second health charger from
    `*196` and shifts it 80 units across.
    """
    seen: set[tuple[str, str, str]] = set()
    for entry in campaign["locations"]:
        trigger = entry["trigger"]
        if trigger["type"] != "charger":
            continue
        key = (entry["map"], trigger["model"], trigger.get("origin", ""))
        assert key not in seen, entry["name"]
        seen.add(key)


def test_a_shared_charger_brush_is_split_by_origin(campaign: dict) -> None:
    """Both units on a reused brush are real, so both are checks."""
    canal = [
        entry for entry in campaign["locations"]
        if entry["map"] == "ba_canal1" and entry["trigger"]["type"] == "charger"
    ]
    assert len(canal) == 2, "ba_canal1 has two health chargers on one brush"
    assert {e["trigger"]["model"] for e in canal} == {"*196"}
    # Exactly one carries the offset: the un-shifted one keeps the plain key it
    # has always had, so its id never moved.
    origins = sorted(e["trigger"].get("origin", "") for e in canal)
    assert origins == ["", "0 80 0"]


def test_only_shared_brushes_carry_an_origin(campaign: dict) -> None:
    """Adding it anywhere else would renumber a location that already existed."""
    by_map: dict[tuple[str, str], list[dict]] = {}
    for entry in campaign["locations"]:
        trigger = entry["trigger"]
        if trigger["type"] == "charger":
            by_map.setdefault((entry["map"], trigger["model"]), []).append(trigger)

    for (map_name, model), triggers in by_map.items():
        if len(triggers) == 1:
            assert not triggers[0].get("origin"), f"{map_name} {model}"


def test_checkdata_charger_args_are_classname_and_model(
    campaign: dict, checkdata: list[list[str]]
) -> None:
    """Exactly what the plugin builds from the entity a player pressed +use on."""
    generated = {int(r[1]): r[4] for r in checkdata if r[0] == "L" and r[3] == "charger"}
    expected = {}
    for entry in campaign["locations"]:
        trigger = entry["trigger"]
        if trigger["type"] != "charger":
            continue
        arg = f"{trigger['classname']}:{trigger['model']}"
        if trigger.get("origin"):
            arg += f"@{trigger['origin']}"
        expected[entry["id"]] = arg
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


def test_a_group_holding_a_restricted_weapon_only_gates_its_own_campaign(
    campaign: dict,
) -> None:
    """A weapon you cannot carry into a mission cannot satisfy its gate.

    They Hunger's guns are real logic inside They Hunger and useless outside it,
    so they live in a group of their own that only its episodes name. Putting one
    in plain `ranged` would let strict logic expect you to enter We've Got
    Hostiles holding a tommy gun the engine will not give you there.
    """
    restricted = campaign["restricted_classnames"]
    campaign_of = {c["key"]: c["campaign"] for c in campaign["chapters"]}

    # Group -> the campaigns whose weapons in it cannot travel.
    confined: dict[str, set[str]] = {}
    for entry in campaign["items"]:
        if entry.get("group") != "weapon":
            continue
        owners = {
            owner
            for classname in entry["classnames"]
            for owner in restricted.get(classname, ())
        }
        if not owners:
            continue
        for group, members in campaign["requirement_groups"].items():
            if entry["name"] in members:
                confined.setdefault(group, set()).update(owners)

    assert confined, "expected at least one campaign-confined group"

    for chapter in campaign["chapters"]:
        for group in chapter["gates"].get("strict", []):
            if group in confined:
                assert campaign_of[chapter["key"]] in confined[group], (
                    f"{chapter['key']} gates on {group}, which counts weapons it "
                    f"cannot be given"
                )


def test_they_hunger_expects_a_gun_after_its_first_episode(campaign: dict) -> None:
    """Its own or another campaign's, but not a melee weapon alone."""
    gates = {c["key"]: c["gates"] for c in campaign["chapters"]}

    assert not gates["th_episode_1"].get("strict")
    for key in ("th_episode_2", "th_episode_3"):
        assert gates[key]["strict"] == ["ranged_they_hunger"], key

    group = campaign["requirement_groups"]["ranged_they_hunger"]
    # Both halves: its own guns, and the ones that travel.
    assert "Tommy Gun" in group
    assert "Shotgun" in group
    # And never a melee weapon, which is the whole point of the gate.
    for melee in ("Spanner", "Pipe Wrench", "Crowbar"):
        assert melee not in group


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


def test_placeable_locations_carry_a_position(campaign: dict) -> None:
    """`!find` can only point at a check that knows where it is.

    Chargers and weapon pickups are somewhere; reaching a map or finishing a
    mission is not a place, so those carry nothing and `!find` says so.
    """
    from campaign_layout import WEAPON_ANCHORS

    # A weapon handed over by an NPC has no entity to stand next to, so its check
    # is anchored by hand and carries no position. Everything else must have one.
    handed_over = {
        name for anchors in WEAPON_ANCHORS.values() for name in anchors
    }

    for entry in campaign["locations"]:
        kind = entry["trigger"]["type"]
        if kind == "charger" or (
            kind == "weapon_pickup"
            and not any(entry["name"].endswith(f"First {n}") for n in handed_over)
        ):
            assert "position" in entry, entry["name"]
            assert len(entry["position"]) == 3, entry["name"]
            assert all(isinstance(v, int) for v in entry["position"]), entry["name"]
        elif kind not in ("charger", "weapon_pickup"):
            assert "position" not in entry, entry["name"]


def test_a_shared_brush_gives_its_two_chargers_different_places(
    campaign: dict,
) -> None:
    """Otherwise `!find` would point at the same spot for both."""
    canal = [
        entry for entry in campaign["locations"]
        if entry["map"] == "ba_canal1" and entry["trigger"]["type"] == "charger"
    ]
    positions = [tuple(entry["position"]) for entry in canal]
    assert len(set(positions)) == 2, positions
    # 80 units apart on Y, which is the offset the mapper gave the copy.
    (ax, ay, az), (bx, by, bz) = sorted(positions)
    assert (ax, az) == (bx, bz)
    assert abs(by - ay) == 80


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


def test_every_campaign_can_be_started_without_a_gun(campaign: dict) -> None:
    """Each campaign needs a mission you may enter holding only a melee weapon.

    The starting mission is picked from these. With none, generation falls back
    to any mission at all and hands out one that logic then refuses to enter --
    which is exactly what happened to Opposing Force once its every mission was
    gated and `exclude_intro_missions` removed the one that was not.
    """
    gates = {c["key"]: c["gates"] for c in campaign["chapters"]}

    for entry in campaign["campaigns"]:
        startable = [
            key for key in entry["chapters"]
            if key != entry["goal_chapter"] and not gates[key].get("strict")
        ]
        assert startable, f"{entry['key']} has no mission enterable with melee alone"


def test_a_campaign_survives_excluding_its_intro(campaign: dict) -> None:
    """`exclude_intro_missions` must not take a campaign's only legal start."""
    gates = {c["key"]: c["gates"] for c in campaign["chapters"]}

    for entry in campaign["campaigns"]:
        intro = entry.get("intro_chapter")
        startable = [
            key for key in entry["chapters"]
            if key != entry["goal_chapter"]
            and key != intro
            and not gates[key].get("strict")
        ]
        assert startable, (
            f"{entry['key']} has no legal start once its intro is excluded"
        )
