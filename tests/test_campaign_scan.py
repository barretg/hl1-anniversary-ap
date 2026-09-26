"""Checks of every known campaign's tables against the retail BSPs.

These read the real install, so they skip without one. Point `HL_GAME_ROOT` at
the Half-Life folder (the one holding `valve`, `gearbox`, `bshift`); the default
is the development machine's library. A game that is not installed skips.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import build_campaign_data  # noqa: E402
from bsp_entities import load_map  # noqa: E402
from campaigns import (  # noqa: E402
    KNOWN_CAMPAIGNS,
    Campaign,
    requirement_groups,
)

GAME_ROOT = Path(os.environ.get(
    "HL_GAME_ROOT", "/mnt/win/f/SteamLibrary/steamapps/common/Half-Life"
))


def installed(campaign: Campaign) -> Path:
    if not (GAME_ROOT / campaign.detect).is_file():
        pytest.skip(f"{campaign.name} not installed under {GAME_ROOT}")
    return GAME_ROOT / campaign.game_dir / "maps"


_ENTITIES: dict[Path, list[dict[str, str]]] = {}


def entities(path: Path) -> list[dict[str, str]]:
    if path not in _ENTITIES:
        _ENTITIES[path] = load_map(path)
    return _ENTITIES[path]


def classnames(path: Path) -> set[str]:
    return {e.get("classname", "") for e in entities(path)}


@pytest.fixture(params=KNOWN_CAMPAIGNS, ids=lambda c: c.key)
def campaign(request) -> Campaign:
    return request.param


def test_every_single_player_map_is_placed_or_excluded(campaign: Campaign) -> None:
    """A map nobody decided about is a map the world silently leaves out.

    Multiplayer maps are told apart by their deathmatch spawns and the lack of
    any transition; everything else is a campaign map or listed as excluded.
    """
    maps_dir = installed(campaign)
    placed = set(campaign.maps) | campaign.excluded_maps
    undecided = []
    for bsp in sorted(maps_dir.glob("*.bsp")):
        found = classnames(bsp)
        multiplayer = ("info_player_deathmatch" in found
                       and "trigger_changelevel" not in found)
        if not multiplayer and bsp.stem.lower() not in placed:
            undecided.append(bsp.stem)
    assert not undecided


def test_every_chapter_map_is_reachable_within_its_chapter(campaign: Campaign) -> None:
    """Warping into a mission lands on its first map; every other map of it has
    to be walkable from there without leaving the mission. Use-only
    transitions count: they are how OF's displacer trips are taken."""
    maps_dir = installed(campaign)
    for key, _, maps in campaign.chapters:
        seen = {maps[0]}
        frontier = [maps[0]]
        while frontier:
            here = frontier.pop()
            for target in build_campaign_data.changelevel_targets(
                entities(maps_dir / f"{here}.bsp")
            ):
                if target in maps and target not in seen:
                    seen.add(target)
                    frontier.append(target)
        assert seen == set(maps), f"{key}: unreachable {set(maps) - seen}"


def test_every_mission_but_the_finale_has_a_forward_exit(campaign: Campaign) -> None:
    maps_dir = installed(campaign)
    chapters = [
        {"key": key, "maps": maps, "index": index, "campaign": campaign.key}
        for index, (key, _, maps) in enumerate(campaign.chapters)
    ]
    loaded = {m: entities(maps_dir / f"{m}.bsp") for m in campaign.maps}
    for chapter in chapters:
        forward = build_campaign_data.has_forward_exit(chapter, chapters, loaded)
        assert forward == (chapter["key"] != campaign.goal_chapter), chapter["key"]


def test_endsection_finales_have_one(campaign: Campaign) -> None:
    maps_dir = installed(campaign)
    for key, mode in campaign.complete_on.items():
        if mode != "endsection":
            continue
        maps = dict((k, m) for k, _, m in campaign.chapters)[key]
        assert "trigger_endsection" in classnames(maps_dir / f"{maps[-1]}.bsp")


def test_weapon_anchors_hold_what_drops_the_weapon(campaign: Campaign) -> None:
    """The Shock Roach is dropped by shock troopers, so its anchor map must
    place one."""
    maps_dir = installed(campaign)
    droppers = {"Shock Roach": "monster_shocktrooper"}
    for item, map_name in campaign.weapon_anchors.items():
        assert droppers[item] in classnames(maps_dir / f"{map_name}.bsp")


def test_blue_shift_has_no_usable_hev_chargers() -> None:
    """Its HEV-style wall units are scenery. If a patch ever made one a
    `func_recharge`, it would need a decision, not a silent check."""
    from campaigns.blue_shift import BLUE_SHIFT

    maps_dir = installed(BLUE_SHIFT)
    for map_name in BLUE_SHIFT.maps:
        assert "func_recharge" not in classnames(maps_dir / f"{map_name}.bsp")


def test_gate_groups_exist() -> None:
    groups = requirement_groups(KNOWN_CAMPAIGNS)
    for campaign in KNOWN_CAMPAIGNS:
        for table in (*campaign.gates.values(), *campaign.map_gates.values()):
            for group in table.get("strict", []):
                assert group in groups, (campaign.key, group)
            for group in table.get("always", []):
                assert group in groups or group in ("longjump", "suit"), (
                    campaign.key, group)


def test_a_seam_twin_pair_is_never_dropped_on_both_sides() -> None:
    """`of4a2` and `of4a3` are joined by two transitions, and each finds the
    other's copy of their shared pair of health chargers behind one of them.
    One copy of each must survive."""
    from bsp_entities import brush_model_bounds, brush_model_centres
    from campaigns.opposing_force import OPPOSING_FORCE

    maps_dir = installed(OPPOSING_FORCE)
    maps = ["of4a1", "of4a2", "of4a3"]
    chapters = [{"key": "of4a1", "maps": maps, "index": 0,
                 "campaign": OPPOSING_FORCE.key}]
    paths = {m: maps_dir / f"{m}.bsp" for m in maps}
    sealed = build_campaign_data.sealed_seam_chargers(
        chapters,
        {m: entities(p) for m, p in paths.items()},
        {m: brush_model_centres(p) for m, p in paths.items()},
        {m: brush_model_bounds(p) for m, p in paths.items()},
    )
    assert "of4a2" not in sealed
    assert sealed["of4a3"] == {"func_healthcharger:*137", "func_healthcharger:*138"}


def test_healing_volumes_in_sealed_rooms_are_dropped_and_real_pools_kept() -> None:
    """`of5a1` carries a healing volume in a prefab room nothing leads into;
    Xen's first pool is the real thing."""
    from bsp_entities import brush_model_bounds
    from campaigns.half_life import HALF_LIFE
    from campaigns.opposing_force import OPPOSING_FORCE

    found = {}
    for campaign, map_name in ((OPPOSING_FORCE, "of5a1"), (HALF_LIFE, "c4a1")):
        path = installed(campaign) / f"{map_name}.bsp"
        chapters = [{"key": map_name, "maps": [map_name], "index": 0,
                     "campaign": campaign.key}]
        found.update(build_campaign_data.isolated_healing_pools(
            chapters,
            {map_name: [build_campaign_data.resolve_world_item(e) for e in entities(path)]},
            {map_name: brush_model_bounds(path)},
            {map_name: path},
        ))
    assert set(found) == {"of5a1"}
