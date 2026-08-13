"""Universal Tracker support.

UT re-runs this world's generation locally to work out what is in logic. One of
our decisions is rolled rather than derived -- which mission the run opens with
-- so UT is handed the real seed's answer through `interpret_slot_data` and reads
it back out of `multiworld.re_gen_passthrough`.

The failure mode these guard against is silent: a passthrough read whose key was
never put into slot data just falls back to a fresh roll, and UT's logic view
drifts from the server's with nothing to show for it.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORLD = (REPO / "apworld" / "half_life" / "__init__.py").read_text(encoding="utf-8")
CLIENT = (
    REPO / "apworld" / "half_life" / "client" / "launcher.py"
).read_text(encoding="utf-8")


def slot_data_keys() -> set[str]:
    body = WORLD.split("def fill_slot_data", 1)[1]
    return set(re.findall(r'^\s{12}"([a-z_]+)":', body, re.M))


def passthrough_keys() -> set[str]:
    return set(re.findall(r'passthrough(?:\s*or\s*\{\})?\)?\.get\(\s*"([a-z_]+)"', WORLD))


def test_the_world_offers_the_tracker_hook() -> None:
    assert "def interpret_slot_data" in WORLD
    assert "re_gen_passthrough" in WORLD


def test_every_passthrough_key_is_actually_in_slot_data() -> None:
    """Reading a key nobody sends silently falls back to a fresh roll."""
    missing = passthrough_keys() - slot_data_keys()
    assert not missing, f"read from passthrough but never sent: {sorted(missing)}"


def test_the_rolled_decision_is_covered() -> None:
    """The one thing UT cannot re-derive, by name, so it is not dropped."""
    assert "starting_chapters" in passthrough_keys()


def test_the_client_falls_back_without_the_tracker_apworld() -> None:
    """Most players will not have UT installed; the client must not care."""
    assert "except ModuleNotFoundError" in CLIENT
    assert "SuperContext = CommonContext" in CLIENT
    # UT's context tags the connection as a tracker; this is a game client.
    assert 'tags = {"AP"}' in CLIENT


def test_the_client_names_its_own_window() -> None:
    assert "def make_gui" in CLIENT
    assert "base_title" in CLIENT
    # Via super(), so UT's UI (and its Tracker tab) is what gets renamed.
    body = CLIENT.split("def make_gui", 1)[1]
    assert "super().make_gui()" in body


def test_on_package_reaches_the_base_context() -> None:
    """UT does its work there; skipping the call leaves its tab empty."""
    body = CLIENT.split("def on_package", 1)[1]
    assert "super().on_package(cmd, args)" in body
