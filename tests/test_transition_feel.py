"""The transform's harness group (TRANSITION_RANDO.md 9.2 step 4), without the
game: the pairs it plays name real, trusted walk transitions, and a scenario
hands its pairs to the dll through the go file."""

from __future__ import annotations

import json
import shutil
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHECKDATA = REPO / "apworld" / "half_life" / "mod" / "files" / "archipelago" / "checkdata.txt"
CAMPAIGN = REPO / "apworld" / "half_life" / "data" / "campaign.json"
TRIGGERS_PATCH = REPO / "game" / "sdk.patch"

sys.path.insert(0, str(REPO / "tests" / "aptest"))
import aptest  # noqa: E402


def test_feel_pairs_are_trusted_walk_transitions() -> None:
    built = {t["id"]: t for t in json.loads(CAMPAIGN.read_text(encoding="utf-8"))["transitions"]}
    for a, b, _ in aptest.TRANSITION_FEEL_PAIRS:
        for tid in (a, b):
            t = built[tid]
            assert t["kind"] == "walk" and t["partner"] and not t.get("flags"), tid
        assert a != b and built[a]["partner"] != b, "a vanilla pair would not be rewritten"
    data = aptest.read_checkdata(CHECKDATA)
    assert len(aptest.transition_feel_scenarios(data)) == len(aptest.TRANSITION_FEEL_PAIRS)


class FakeBridge:
    def __init__(self, store) -> None:
        pass

    def reset_cursor(self) -> None:
        pass

    def write_snapshot(self, **fields) -> None:
        pass


def test_a_feel_scenario_writes_its_pair(tmp_path) -> None:
    shutil.copy(CHECKDATA, tmp_path / "checkdata.txt")
    data = aptest.read_checkdata(CHECKDATA)
    scenarios = aptest.transition_feel_scenarios(data)
    h = aptest.Harness(tmp_path, types.SimpleNamespace(Bridge=FakeBridge), "transitionfeel",
                       scenarios)
    h.start(0)
    a, b, _ = aptest.TRANSITION_FEEL_PAIRS[0]
    go = h.go_path.read_text(encoding="utf-8").splitlines()
    assert f"pair={a} {b}" in go
    assert f"map={a.split(':')[0]}" in go


def test_the_sdk_patch_carries_the_transition_hooks() -> None:
    patch = TRIGGERS_PATCH.read_text(encoding="utf-8-sig")
    for hook in ("ap::OnChangeLevelSpawned( this );", "ap::OnTransition( this );",
                 "ap::BeforeChangeLevel( this, pPlayer );",
                 "void SetChangeLevelDestination("):
        assert hook in patch, hook
