"""The multi-campaign tooling: BSP layouts, the campaign registry, and the
fields `campaign.json` gained for it.

None of this needs a game install. The BSPs are synthetic, built here to the
two layouts retail ships.
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import bsp_entities  # noqa: E402
import build_campaign_data  # noqa: E402
from campaigns import CAMPAIGNS, CAMPAIGNS_BY_KEY, Campaign, hub_button_index  # noqa: E402

CAMPAIGN_PATH = REPO / "apworld" / "half_life" / "data" / "campaign.json"

ENTITY_TEXT = b'{\n"classname" "worldspawn"\n}\n{\n"classname" "item_suit"\n}\n\x00'
PLANES = struct.pack("<3ffi", 0.0, 0.0, 1.0, 64.0, 2) * 3


def synthetic_bsp(path: Path, swapped: bool) -> Path:
    """A v30 header plus an entity lump and a plane lump, in either order.

    Blue Shift stores planes in lump 0 and entities in lump 1; every other
    GoldSrc game the other way round.
    """
    lumps = [b""] * bsp_entities.LUMP_COUNT
    first, second = (PLANES, ENTITY_TEXT) if swapped else (ENTITY_TEXT, PLANES)
    lumps[0], lumps[1] = first, second
    offset = struct.calcsize(bsp_entities.HEADER_FMT)
    table: list[int] = []
    body = b""
    for lump in lumps:
        table += [offset + len(body), len(lump)]
        body += lump
    path.write_bytes(struct.pack(bsp_entities.HEADER_FMT, 30, *table) + body)
    return path


@pytest.mark.parametrize("swapped", [False, True], ids=["standard", "blue_shift"])
def test_entities_and_planes_are_found_in_either_layout(
    tmp_path: Path, swapped: bool
) -> None:
    bsp = synthetic_bsp(tmp_path / "map.bsp", swapped)
    assert [e["classname"] for e in bsp_entities.load_map(bsp)] == [
        "worldspawn", "item_suit",
    ]
    assert bsp_entities.read_lump(bsp, bsp_entities.LUMP_PLANES) == PLANES


def test_registry_starts_with_half_life() -> None:
    """Half-Life first keeps its chapter indices 0..17 and `ap_warp <n>`."""
    from campaigns.half_life import CHAPTERS

    assert CAMPAIGNS[0].key == "half_life"
    assert CAMPAIGNS[0].legacy
    assert CAMPAIGNS[0].chapters == CHAPTERS
    assert [c for c in CAMPAIGNS if c.legacy] == [CAMPAIGNS[0]]


def test_chapter_keys_and_maps_are_unique_across_campaigns() -> None:
    """Location keys start with the chapter key, and the game finds a mission
    by map name, so neither may be shared between two games."""
    keys = [key for c in CAMPAIGNS for key in c.chapter_keys]
    maps = [m for c in CAMPAIGNS for m in c.maps]
    assert len(keys) == len(set(keys))
    assert len(maps) == len(set(maps))


def test_campaign_rejects_a_goal_it_does_not_have() -> None:
    with pytest.raises(ValueError):
        Campaign(key="x", name="X", game_dir="x", detect="x/maps/a.bsp",
                 chapters=[("a", "A", ["a"])], goal_chapter="b", intro_chapter="a")


def test_hub_buttons_are_counted_per_campaign() -> None:
    assert hub_button_index("chapter_3_button") == 3
    assert hub_button_index("of_chapter_3_button") is None
    assert hub_button_index("of_chapter_3_button", "of_") == 3
    assert hub_button_index("chapter_3_button", "of_") is None


def test_weapon_checks_are_scoped_per_campaign() -> None:
    """Half-Life keeps the `*` keys it published; later games use their key."""
    trigger = {"type": "weapon_pickup", "classnames": ["weapon_shotgun"]}
    assert build_campaign_data.location_key("c1a0", "c1a0", trigger) == (
        "*|*|weapon_pickup|weapon_shotgun"
    )
    assert build_campaign_data.location_key("of1a1", "of1a1", trigger, "of") == (
        "of|*|weapon_pickup|weapon_shotgun"
    )


@pytest.fixture(scope="module")
def campaign() -> dict:
    return json.loads(CAMPAIGN_PATH.read_text(encoding="utf-8"))


def test_campaign_json_lists_every_registered_campaign(campaign: dict) -> None:
    assert [c["key"] for c in campaign["campaigns"]] == [c.key for c in CAMPAIGNS]
    first = campaign["campaigns"][0]
    assert first["goal_chapter"] == campaign["goal_chapter"]
    assert first["intro_chapter"] == campaign["intro_chapter"]


def test_every_chapter_names_its_campaign_and_completion(campaign: dict) -> None:
    for chapter in campaign["chapters"]:
        owner = CAMPAIGNS_BY_KEY[chapter["campaign"]]
        assert chapter["key"] in owner.chapter_keys
        assert chapter["complete_on"] in ("arrival", "forward_exit", "endsection")
        # The older boolean says the same thing, for readers that predate it.
        assert chapter["complete_on_arrival"] == (chapter["complete_on"] == "arrival")


def test_charger_checks_only_for_units_the_game_lets_you_use(campaign: dict) -> None:
    """Blue Shift's HEV-style wall units are scenery. A check on one could
    never fire, so a campaign that does not list a charger classname must
    never produce a check for it."""
    from campaigns import CHARGER_CLASSNAMES

    owner = {c["key"]: c["campaign"] for c in campaign["chapters"]}
    for location in campaign["locations"]:
        classname = location["trigger"].get("classname")
        if location["trigger"]["type"] != "charger" or classname not in CHARGER_CLASSNAMES:
            continue
        assert classname in CAMPAIGNS_BY_KEY[owner[location["chapter"]]].charger_classnames


def test_partial_build_refuses_to_overwrite_the_committed_file(tmp_path: Path) -> None:
    if len(CAMPAIGNS) == 1:
        pytest.skip("only one campaign registered; nothing can be partial")
    with pytest.raises(SystemExit):
        build_campaign_data.main(["--maps", str(tmp_path)])
