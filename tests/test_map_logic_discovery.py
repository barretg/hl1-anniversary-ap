"""Map logic discovery (TRANSITION_RANDO.md section 8), without the game.

* `aptest.py --maplogic` builds four scenarios per chapter, in rollout order,
  from the shipped `checkdata.txt`: forward, backward from forward's save,
  backward fresh, forward from that save. Transitions are labelled.
* The harness keeps `!give` / `!take` in order and writes them as the 8th
  results field; a `maplogic` note stays in the scenario and is no verdict.
* `tools/map_logic_report.py` reads that back into a draft `MAP_LOGIC`.
"""

from __future__ import annotations

import json
import shutil
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CHECKDATA = REPO / "apworld" / "half_life" / "mod" / "files" / "archipelago" / "checkdata.txt"
CAMPAIGN = REPO / "apworld" / "half_life" / "data" / "campaign.json"

sys.path.insert(0, str(REPO / "tests" / "aptest"))
sys.path.insert(0, str(REPO / "tools"))
import aptest  # noqa: E402
import map_logic_report  # noqa: E402


@pytest.fixture(scope="module")
def data() -> aptest.CheckData:
    return aptest.read_checkdata(CHECKDATA)


def test_every_transition_record_is_read(data) -> None:
    built = json.loads(CAMPAIGN.read_text(encoding="utf-8"))["transitions"]
    assert [t.id for t in data.transitions] == [t["id"] for t in built]


def test_maplogic_is_four_passes_per_chapter(data) -> None:
    chapter = aptest.pick_chapters(data, ["c1a2"])[0]
    one, two, three, four = aptest.maplogic_scenarios(data, [chapter])
    titles = [s.title for s in (one, two, three, four)]
    assert len(set(titles)) == 4, "verdicts are recorded by title"
    assert all(map_logic_report.CHAPTER_TITLE.match(t) for t in titles)
    # 1 and 3 start fresh, crowbar only, at the chapter's way in and way out.
    assert one.map == chapter.maps[0] and one.holds == [] and not one.load
    assert one.entry == aptest.chapter_entry(data, chapter).id
    assert three.holds == [] and not three.load
    assert three.entry == aptest.chapter_exit(data, chapter).id
    assert len(one.pos.split()) == 3 and len(three.pos.split()) == 3
    # 2 and 4 carry on from the save and holdings of the one before.
    assert two.load == one.save_as and two.inherit == one.title
    assert four.load == three.save_as and four.inherit == three.title
    assert one.save_as != three.save_as


def test_rollout_order(data) -> None:
    keys = [c.key for c in aptest.rollout_order(data)]
    assert keys[:3] == ["c1a0", "c4a3", "c1a0c"]
    assert keys[-4:] == ["of1a5", "c0a0", "of0a0", "ba_tram1"]
    assert sorted(keys) == sorted(c.key for c in data.chapters)


def test_maplogic_without_chapters_is_every_chapter_in_rollout_order(data, tmp_path) -> None:
    scenarios = aptest.select_scenarios("maplogic", data, tmp_path, tmp_path)
    assert len(scenarios) == 4 * len(data.chapters)
    assert scenarios[4].title.startswith("Map logic: Nihilanth 1")
    picked = aptest.select_scenarios("maplogic", data, tmp_path, tmp_path,
                                     chapters=["c1a2", "c1a0"])
    assert [s.title for s in picked[::4]] == [
        "Map logic: Anomalous Materials 1 (forward)", "Map logic: Office Complex 1 (forward)"]


def test_pick_chapters_takes_keys_or_names_in_data_order(data) -> None:
    picked = aptest.pick_chapters(data, ["c1a2", "Anomalous Materials"])
    assert [c.key for c in picked] == ["c1a0", "c1a2"]
    with pytest.raises(SystemExit):
        aptest.pick_chapters(data, ["nowhere"])


class FakeBridge:
    def __init__(self, store) -> None:
        self.snapshots: list[dict] = []

    def reset_cursor(self) -> None:
        pass

    def write_snapshot(self, **fields) -> None:
        self.snapshots.append(fields)


def harness(tmp_path, scenarios, group="maplogic") -> aptest.Harness:
    shutil.copy(CHECKDATA, tmp_path / "checkdata.txt")
    return aptest.Harness(tmp_path, types.SimpleNamespace(Bridge=FakeBridge), group,
                          scenarios)


def test_given_is_recorded_and_notes_stay(data, tmp_path) -> None:
    scenarios = aptest.maplogic_scenarios(data, aptest.pick_chapters(data, ["c1a2"]))
    h = harness(tmp_path, scenarios)
    h.start(0)
    assert h.bridge.snapshots[-1]["items"] == []
    assert any(line.startswith("yaw=") for line in h.go_path.read_text().splitlines())
    assert f"entry={scenarios[0].entry}" in h.go_path.read_text().splitlines()
    h.command("give", "mp5")
    h.command("give", "Hand Grenade")
    h.command("take", "Hand Grenade")
    h.command("note", "T1 needs MP5")
    assert h.current == 0, "a maplogic note stays in the scenario"
    h.command("note", "oneway drop")  # typed here: no spot, so refused
    h.command("note", "oneway drop", where="10 20 30 90 c1a2a")
    assert f"save={scenarios[0].save_as}" in h.go_path.read_text().splitlines()
    h.command("pass", "")
    assert h.current == 1

    lines = h.results_path.read_text(encoding="utf-8").splitlines()
    fields = [line.split("|") for line in lines]
    assert [f[3] for f in fields] == ["note", "note", "pass"]
    assert all(len(f) == 8 and f[6] == "maplogic" for f in fields)
    assert fields[0][7] == "MP5;Hand Grenade;-Hand Grenade"
    assert fields[1][4] == "[c1a2a] oneway drop @10 20 30 90"
    assert h.latest_verdicts() == {scenarios[0].title: "pass"}

    # Scenario 2 loads 1's save and holds what 1 ended with.
    go = h.go_path.read_text().splitlines()
    assert f"load={scenarios[0].save_as}" in go
    assert h.bridge.snapshots[-1]["items"] == ["MP5"]
    assert h.given == ["MP5", "Hand Grenade", "-Hand Grenade"]


def test_a_note_elsewhere_is_still_a_verdict(data, tmp_path) -> None:
    scenarios = aptest.maplogic_scenarios(data, aptest.pick_chapters(data, ["c1a2"]))
    h = harness(tmp_path, scenarios, group="transition")
    h.start(0)
    h.command("note", "something")
    assert h.current == 1
    assert h.latest_verdicts() == {scenarios[0].title: "note"}


def test_seven_field_lines_still_clear(tmp_path) -> None:
    results = tmp_path / "aptest_results.txt"
    results.write_text("t|0|Map logic: a from a:0 (vanilla entry)|pass|||maplogic|MP5\n"
                       "t|1|Source: d|pass||1|sources\n", encoding="utf-8")
    assert aptest.clear_results(results, "maplogic", set()) == 1
    assert results.read_text(encoding="utf-8") == "t|1|Source: d|pass||1|sources\n"


def test_report_drafts_gates_and_returns() -> None:
    transitions = [{"id": "m:0", "map": "m"}, {"id": "m:1", "map": "m"},
                   {"id": "m:2", "map": "m"}]
    groups = {"ranged": ["Glock", "MP5", "Shotgun"], "crate_breaker": ["MP5", "Hand Grenade"],
              "explosives": ["Hand Grenade"]}
    title = "Map logic: m from m:0 (vanilla entry)"
    lines = [
        # An earlier attempt, superseded by the one after it.
        f"t|0|{title}|note|T2 needs Shotgun||maplogic|Shotgun",
        f"t|0|{title}|fail|x||maplogic|Shotgun",
        f"t|0|{title}|note|T2 needs MP5||maplogic|MP5",
        f"t|0|{title}|note|oneway drop @1 2 3 450||maplogic|MP5",
        f"t|0|{title}|note|oneway gap item longjump @4 5 6 180||maplogic|MP5",
        f"t|0|{title}|note|T3 one-way lift||maplogic|MP5",
        f"t|0|{title}|pass|||maplogic|MP5",
        # Another group's line with the same shape is not read.
        f"t|0|{title}|note|T3 needs RPG||transition|RPG",
        # An old 7-field line.
        "t|1|Map logic: m from m:2 (back transition)|pass|||maplogic",
    ]
    attempts = map_logic_report.read_attempts(lines)
    assert len(attempts) == 2
    draft = map_logic_report.draft_map("m", list(attempts.values()), transitions, groups)
    body = map_logic_report.fragment(draft)
    assert body["segments"] == ["start", "to_1"]
    assert body["transitions"] == {"m:0": "start", "m:1": "to_1", "m:2": "start"}
    assert {"from": "start", "to": "to_1", "always": ["crate_breaker"]} in body["edges"]
    returns = [e for e in body["edges"] if e.get("one_way")]
    assert returns == [
        {"from": "?", "to": "?", "one_way": True, "way_back": "tp",
         "return": {"at": [1, 2, 3], "yaw": 90, "to": "?", "kind": "drop"}},
        # Sent at the lip: the spot is the lip's, and the far side is to fill in.
        {"from": "?", "to": "?", "one_way": True, "way_back": "item", "back": ["longjump"],
         "lip": {"at": [4, 5, 6], "yaw": 180}, "return": {"at": "?", "yaw": "?", "kind": "gap"}},
    ]
    assert any("m:2 one-way lift" in c for c in draft.comments)
    rendered = map_logic_report.render(draft)
    compile("MAP_LOGIC = {\n" + rendered + "\n}", "<draft>", "exec")
    assert "(or: ranged)" in rendered


def test_candidates_are_narrowest_first() -> None:
    groups = {"ranged": ["Glock", "MP5", "Shotgun"], "crate_breaker": ["MP5", "Hand Grenade"]}
    assert map_logic_report.candidates("MP5", ["MP5"], groups) == ["crate_breaker", "ranged"]
    assert map_logic_report.candidates("ranged", [], groups) == ["ranged"]
    assert map_logic_report.candidates("a key card", [], groups) == []


def test_report_files_chapter_notes_under_their_maps() -> None:
    transitions = [{"id": "a:0", "map": "a"}, {"id": "a:1", "map": "a"},
                   {"id": "b:0", "map": "b"}, {"id": "b:1", "map": "b"}]
    groups = {"crate_breaker": ["MP5", "Hand Grenade"]}
    title = "Map logic: Somewhere 1 (forward)"
    lines = [
        f"t|0|{title}|note|[a] T2 needs MP5||maplogic|MP5",
        f"t|0|{title}|note|[b] oneway lift @4 5 6 180||maplogic|MP5",
        f"t|0|{title}|pass|||maplogic|MP5",
    ]
    grouped = map_logic_report.by_map(list(map_logic_report.read_attempts(lines).values()))
    assert sorted(grouped) == ["a", "b"]
    a = map_logic_report.fragment(map_logic_report.draft_map("a", grouped["a"], transitions,
                                                             groups))
    assert a["transitions"] == {"a:0": "start", "a:1": "to_1"}
    b = map_logic_report.fragment(map_logic_report.draft_map("b", grouped["b"], transitions,
                                                             groups))
    assert [e["return"]["at"] for e in b["edges"] if e.get("one_way")] == [[4, 5, 6]]


def test_seed_scenario_publishes_its_slot_data(data, tmp_path) -> None:
    seed = aptest.load_seed("first_step_area")
    ids = {t.id for t in data.transitions}
    named = ([t for pair in seed["transition_pairs"] for t in pair] + seed["inert_transitions"]
             + [t for kv in seed["one_way_transitions"].items() for t in kv]
             + [t for kv in seed["backtrack_orbs"].items() for t in kv])
    assert set(named) <= ids
    scenario = aptest.Scenario(title="s", map=seed["start_map"], entry="", seed=seed)
    h = harness(tmp_path, [scenario], group="transition")
    h.start(0)
    snap = h.bridge.snapshots[-1]
    # The seed, plus the workshop's teleporters and door openers.
    assert {k: v for k, v in snap["transitions"].items()
            if k not in ("teleporters", "door_openers")} == seed
    assert "teleporters" in snap["transitions"] and "door_openers" in snap["transitions"]
    assert snap["chapters"] == seed["transition_chapters"]


def test_workshop_orb_and_door_are_kept_and_published(data, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(aptest, "WORKSHOP", tmp_path / "workshop.json")
    seed = aptest.load_seed("first_step_area")
    h = harness(tmp_path, [aptest.Scenario(title="s", map=seed["start_map"], entry="",
                                           seed=seed)], group="maplogic")
    h.start(0)
    h.command("orb", "from Up", "10 20 30 90 c1a0e")
    h.command("orb", "to", "40 50 60 180 c1a0b")
    h.command("door", "*12 func_door door1", "1 2 3 0 c1a0e")
    snap = h.bridge.snapshots[-1]["transitions"]
    assert snap["teleporters"] == [{"map": "c1a0e", "at": [10.0, 20.0, 30.0], "label": "Up",
                                    "to_map": "c1a0b", "to": [40.0, 50.0, 60.0, 180.0]}]
    assert [(d["map"], d["model"]) for d in snap["door_openers"]] == [("c1a0e", "*12")]
    h.command("orb", "drop", "")
    assert aptest.load_workshop()["teleporters"] == []


def test_plain_chat_is_kept_without_a_verdict(data, tmp_path) -> None:
    scenarios = aptest.transition_feel_scenarios(data)
    h = harness(tmp_path, scenarios, "transitionfeel")
    h.start(0)
    h.command("chat", "arrived in the wall here", where="1 2 3 90 c1a2b")
    assert h.current == 0, "chat never ends a scenario"
    line = h.results_path.read_text(encoding="utf-8").splitlines()[-1].split("|")
    assert line[3:5] == ["remark", "[c1a2b] arrived in the wall here @1 2 3 90"]
    assert h.latest_verdicts() == {}, "a remark is not a verdict"
    h.command("pass", "")
    assert h.latest_verdicts() == {scenarios[0].title: "pass"}
