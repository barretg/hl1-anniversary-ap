"""Location and item ids must never come to mean something else.

Ids used to be positional, so toggling which location types are generated
reassigned all of them. An existing seed then resolved a check to whatever
location had moved into that slot, which looks exactly like the plugin sending
random checks on level change.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

from build_campaign_data import IdRegistry, location_key  # noqa: E402

CAMPAIGN_PATH = REPO / "apworld" / "half_life_sven" / "data" / "campaign.json"
IDS_PATH = REPO / "apworld" / "half_life_sven" / "data" / "ids.json"
CHECKDATA_PATH = (
    REPO / "apworld" / "half_life_sven" / "plugin"
    / "plugins" / "store" / "archipelago" / "checkdata.txt"
)


@pytest.fixture(scope="module")
def campaign() -> dict:
    return json.loads(CAMPAIGN_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def registry_data() -> dict:
    return json.loads(IDS_PATH.read_text(encoding="utf-8"))


def test_registry_is_committed() -> None:
    """Without this file checked in, a rebuild would renumber everything."""
    assert IDS_PATH.is_file()


def test_every_location_id_comes_from_the_registry(campaign: dict, registry_data: dict) -> None:
    table = registry_data["locations"]
    for entry in campaign["locations"]:
        key = location_key(entry["chapter"], entry["map"], entry["trigger"])
        assert key in table, key
        assert table[key] == entry["id"], key


def test_every_item_id_comes_from_the_registry(campaign: dict, registry_data: dict) -> None:
    table = registry_data["items"]
    for entry in campaign["items"]:
        assert table.get(entry["name"]) == entry["id"], entry["name"]


def test_registry_ids_are_unique(registry_data: dict) -> None:
    for kind in ("locations", "items"):
        ids = list(registry_data[kind].values())
        assert len(ids) == len(set(ids)), kind


def test_ids_are_stable_across_a_location_set_change(tmp_path: Path) -> None:
    """The exact regression: enabling a location type must not renumber the rest."""
    path = tmp_path / "ids.json"
    registry = IdRegistry(path)

    reached = location_key("office_complex", "hl_c03", {"type": "map_reached"})
    complete = location_key(
        "office_complex", "hl_c03", {"type": "chapter_complete", "chapter": "office_complex"}
    )
    before = (registry.get("locations", reached, 1000), registry.get("locations", complete, 1000))
    registry.save()

    # A later build turns pickups back on, generating them *before* the others.
    reloaded = IdRegistry(path)
    pickup = location_key(
        "office_complex", "hl_c03", {"type": "pickup", "classnames": ["weapon_shotgun"]}
    )
    reloaded.get("locations", pickup, 1000)
    after = (
        reloaded.get("locations", reached, 1000),
        reloaded.get("locations", complete, 1000),
    )

    assert after == before


def test_new_keys_get_fresh_ids(tmp_path: Path) -> None:
    registry = IdRegistry(tmp_path / "ids.json")
    first = registry.get("locations", "a", 1000)
    second = registry.get("locations", "b", 1000)
    assert first != second


def test_fingerprint_changes_when_ids_change(tmp_path: Path) -> None:
    registry = IdRegistry(tmp_path / "ids.json")
    registry.get("locations", "a", 1000)
    before = registry.fingerprint()

    registry.get("locations", "b", 1000)
    assert registry.fingerprint() != before


def test_fingerprint_is_stable_for_the_same_ids(tmp_path: Path) -> None:
    path = tmp_path / "ids.json"
    registry = IdRegistry(path)
    registry.get("locations", "a", 1000)
    registry.save()

    assert IdRegistry(path).fingerprint() == registry.fingerprint()


def test_data_version_is_published_to_both_sides(campaign: dict) -> None:
    """The plugin pauses checks unless these agree."""
    version = campaign["data_version"]
    assert version

    records = [
        line.split("|") for line in CHECKDATA_PATH.read_text(encoding="utf-8").splitlines()
        if line.startswith("D|")
    ]
    assert records == [["D", version]], "run: python tools/gen_checkdata.py"
