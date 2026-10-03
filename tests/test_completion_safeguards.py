"""The two completion safeguards, and the harness group they are played in.

* The game sends a mission's `COMPLETE` only when its checks could go too: the
  client counts it toward the finale's seal, and a mission left while the client
  was disconnected used to count with nothing on the server.
* The client forgets one slot's finished missions when it connects to another,
  then takes the new slot's from what the server has checked.

The client imports Archipelago, which these tests run without, so its methods
are lifted out of `launcher.py` and run on a stand-in for the context.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CHECKDATA = REPO / "apworld" / "half_life" / "mod" / "files" / "archipelago" / "checkdata.txt"
CAMPAIGN = REPO / "apworld" / "half_life" / "data" / "campaign.json"
LAUNCHER = REPO / "apworld" / "half_life" / "client" / "launcher.py"
LOCATIONS_CPP = REPO / "game" / "src" / "ap_locations.cpp"
DEFAULT_GAME_ROOT = Path("/mnt/win/f/SteamLibrary/steamapps/common/Half-Life")

sys.path.insert(0, str(REPO / "tests" / "aptest"))
import aptest  # noqa: E402


# ------------------------------------------------------------------ the game


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    depth = 0
    for i in range(source.index("{", start), len(source)):
        depth += {"{": 1, "}": -1}.get(source[i], 0)
        if depth == 0:
            return source[start:i + 1]
    raise AssertionError(f"unterminated {signature}")


def test_complete_waits_for_the_same_guards_as_a_check() -> None:
    body = function_body(LOCATIONS_CPP.read_text(encoding="utf-8"),
                         "bool SendChapterComplete(const Chapter& chapter)")
    guard = re.search(r"if \(!Live\(\) \|\| !g_map_authorised\) \{\s*return false;", body)
    assert guard, "SendChapterComplete must refuse when not live or not authorised"
    assert guard.start() < body.index('Wire().Send("COMPLETE"'), "the guard comes first"


# ------------------------------------------------------------------ the client


def lifted_context():
    """`HalfLifeContext`'s slot methods on a class of their own."""
    tree = ast.parse(LAUNCHER.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "HalfLifeContext")
    wanted = {"forget_other_slot", "sync_completed_missions", "slot_identity",
              "is_mission_complete", "chapter_for_location"}
    methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    assert {m.name for m in methods} == wanted
    stand_in = ast.ClassDef(name="Context", bases=[], keywords=[], body=methods,
                            decorator_list=[], type_params=[])
    module = ast.Module(body=[stand_in], type_ignores=[])
    ast.fix_missing_locations(module)
    scope = {"logger": logging.getLogger("test")}
    exec(compile(module, str(LAUNCHER), "exec"), scope)

    ctx = scope["Context"]()
    ctx.campaign = json.loads(CAMPAIGN.read_text(encoding="utf-8"))
    ctx.completed_missions = set()
    ctx.legacy_sent = set()
    ctx.goal_sent = False
    ctx.state_slot = ""
    ctx.checked_locations = set()
    return ctx


def completion_id(chapter: str) -> int:
    campaign = json.loads(CAMPAIGN.read_text(encoding="utf-8"))
    return next(e["id"] for e in campaign["locations"]
                if e["trigger"]["type"] == "chapter_complete" and e["chapter"] == chapter)


@pytest.fixture
def ctx():
    ctx = lifted_context()
    ctx.seed_name, ctx.slot = "seed-a", 1
    ctx.forget_other_slot()
    ctx.completed_missions |= {"c1a2", "c1a3"}
    ctx.legacy_sent.add(7760052)
    ctx.goal_sent = True
    return ctx


def test_a_reconnect_to_the_same_slot_keeps_everything(ctx) -> None:
    ctx.forget_other_slot()
    assert ctx.completed_missions == {"c1a2", "c1a3"}
    assert ctx.legacy_sent == {7760052}
    assert ctx.goal_sent


@pytest.mark.parametrize("change", ["slot", "seed"])
def test_another_slot_starts_from_its_own_completions(ctx, change) -> None:
    if change == "slot":
        ctx.slot = 2
    else:
        ctx.seed_name = "seed-b"
    # The new slot has Xen's completion checked, by whatever route; a collect
    # counts like any other.
    ctx.checked_locations = {completion_id("c4a1")}
    ctx.forget_other_slot()
    assert ctx.completed_missions == {"c4a1"}
    assert ctx.legacy_sent == set()
    assert not ctx.goal_sent


def test_the_reset_runs_before_the_connect_sync() -> None:
    """`Connected` resets, then syncs: the other way round would wipe the new
    slot's completions as soon as they were counted."""
    source = LAUNCHER.read_text(encoding="utf-8")
    handler = source[source.index("def on_package"):]
    assert handler.index("self.forget_other_slot()") < handler.index(
        "self.sync_completed_missions()")


# ------------------------------------------------------------------ the harness


def test_completion_scenarios_build_from_the_shipped_data() -> None:
    data = aptest.read_checkdata(CHECKDATA)
    assert data.goal_chapter
    first = data.chapters[1]
    exits = {first.key: (first.maps[-1], "1 2 3")}
    scenarios = aptest.completion_scenarios(data, exits)

    titles = [s.title for s in scenarios]
    assert len(titles) == len(set(titles)), "verdicts are recorded by title"
    connected, disconnected, finale = scenarios
    assert connected.connected and connected.expect_complete == [first.key]
    assert not disconnected.connected and not disconnected.expect_complete
    assert not disconnected.expect
    assert (connected.map, connected.pos) == (disconnected.map, disconnected.pos)

    goal = next(c for c in data.chapters if c.key == data.goal_chapter)
    assert finale.map == goal.maps[-1] and not finale.connected
    assert finale.expect_complete == [goal.key]


def test_mission_exits_are_walk_in_triggers_into_a_later_mission() -> None:
    root = Path(os.environ.get("HL_ROOT", DEFAULT_GAME_ROOT))
    if not (root / "valve" / "maps").is_dir():
        pytest.skip("no Half-Life install")
    data = aptest.read_checkdata(CHECKDATA)
    exits = aptest.mission_exits(data, root)
    by_key = {c.key: c for c in data.chapters}
    assert exits, "no exits found"
    for key, (map_name, pos) in exits.items():
        assert map_name in by_key[key].maps
        assert len(pos.split()) == 3


def test_clear_drops_one_group_and_keeps_a_copy(tmp_path) -> None:
    results = tmp_path / "aptest_results.txt"
    results.write_text("\n".join([
        "t|0|Completion: a|pass||1|completion",
        "t|1|Parity B2: b|fail|x||parity",
        # Written before verdicts named their group: matched by title.
        "t|2|Completion: c|pass||",
        "t|3|Source: d|pass||",
    ]) + "\n", encoding="utf-8")

    count = aptest.clear_results(results, "completion", {"Completion: c"})

    assert count == 2
    assert results.read_text(encoding="utf-8").splitlines() == [
        "t|1|Parity B2: b|fail|x||parity",
        "t|3|Source: d|pass||",
    ]
    cleared = (tmp_path / "aptest_results_cleared.txt").read_text(encoding="utf-8")
    assert "Completion: a" in cleared and "Completion: c" in cleared


def test_clear_with_nothing_to_drop_leaves_the_file_alone(tmp_path) -> None:
    results = tmp_path / "aptest_results.txt"
    assert aptest.clear_results(results, "completion", set()) == 0
    assert not results.exists()
    assert not (tmp_path / "aptest_results_cleared.txt").exists()


def test_every_group_the_harness_names_can_be_selected() -> None:
    source = (REPO / "tests" / "aptest" / "aptest.py").read_text(encoding="utf-8")
    for group in aptest.GROUPS:
        if group != "sources":
            assert f'"--{group}"' in source, group
