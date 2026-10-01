"""Checks behind the Sven parity work that need no game.

* `aptest.py --parity` builds its scenarios from the shipped `checkdata.txt`,
  so a renamed mission key or a missing map would only show up in front of
  someone who had already launched the game.
* `game/sdk.patch` has had hunks added by hand. A hunk header whose counts or
  offsets disagree with its body fails `git apply` against a fresh SDK, which
  is a long way from where the mistake was made.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHECKDATA = REPO / "apworld" / "half_life" / "mod" / "files" / "archipelago" / "checkdata.txt"

sys.path.insert(0, str(REPO / "tests" / "aptest"))
import aptest  # noqa: E402


def test_parity_scenarios_build_from_the_shipped_data() -> None:
    data = aptest.read_checkdata(CHECKDATA)
    scenarios = aptest.parity_scenarios(data)

    titles = [s.title for s in scenarios]
    assert len(titles) == len(set(titles)), "verdicts are recorded by title"
    maps = {m for c in data.chapters for m in c.maps}
    for scenario in scenarios:
        assert scenario.map in maps, scenario.title
        for location_id in scenario.checked:
            assert data.locations[location_id].kind == "map_reached", scenario.title
    # One death scenario per game, each naming its own protagonist.
    deaths = [t for t in titles if t.startswith("Parity O14")]
    assert any("Freeman" in t for t in deaths)
    assert any("Shephard" in t for t in deaths)
    assert any("Barney" in t for t in deaths)


HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def test_sdk_patch_hunks_add_up() -> None:
    lines = (REPO / "game" / "sdk.patch").read_text(encoding="utf-8").split("\n")
    problems = []
    delta = 0
    current = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("+++ "):
            current = line[4:]
            delta = 0
            i += 1
            continue
        match = HUNK.match(line)
        if not match:
            i += 1
            continue
        old_start, old_count, new_start, new_count = (
            int(match.group(1)), int(match.group(2) or 1),
            int(match.group(3)), int(match.group(4) or 1))
        # A new file's hunk starts from line 0 of nothing.
        if old_count and new_start - old_start != delta:
            problems.append(f"{current} {line}: starts {new_start - old_start:+} "
                            f"from the old file, expected {delta:+}")
        old_seen = new_seen = 0
        i += 1
        while i < len(lines) and (old_seen < old_count or new_seen < new_count):
            body = lines[i]
            if body.startswith("\\"):
                i += 1
                continue
            if body.startswith("-"):
                old_seen += 1
            elif body.startswith("+"):
                new_seen += 1
            else:
                old_seen += 1
                new_seen += 1
            i += 1
        if (old_seen, new_seen) != (old_count, new_count):
            problems.append(f"{current} {line}: body has {old_seen}/{new_seen} lines")
        delta += new_count - old_count
    assert not problems, "\n".join(problems)
