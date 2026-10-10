"""The precache sweep's reading of `ap_boot.txt`: what makes a map pass, warn or
fail. The sweep itself needs the game; this is the part that does not."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests" / "aptest"))
import aptest  # noqa: E402


def load(map_name: str, *body: str, models: int = 400, sounds: int = 150) -> list[str]:
    return [f"precache begins on {map_name} (half_life)", *body,
            f"slots on {map_name}: models {models} of 511, sounds {sounds} of 511"]


def test_unfinished_load_is_not_read():
    lines = load("c1a0")[:-1]
    assert aptest.read_sweep(lines, "c1a0") is None


def test_roomy_map_passes():
    result = aptest.read_sweep(load("c1a0", models=365, sounds=140), "c1a0")
    assert (result.verdict, result.models, result.sounds) == ("pass", 365, 140)


def test_close_to_either_limit_warns():
    near = 511 - aptest.SWEEP_MARGIN + 1
    assert aptest.read_sweep(load("c1a0", models=near), "c1a0").verdict == "warn"
    assert aptest.read_sweep(load("c1a0", sounds=near), "c1a0").verdict == "warn"


def test_texture_drops_warn():
    result = aptest.read_sweep(load(
        "of4a4",
        "precache texture models: 3 precached, 12 dropped: +3 models, +0 sounds "
        "(now 400 models, 150 sounds, of 511 each)"), "of4a4")
    assert result.verdict == "warn"
    assert "texture models: 3 precached, 12 dropped" in result.notes


def test_texture_models_all_precached_is_quiet():
    result = aptest.read_sweep(load(
        "c1a0", "precache texture models: 10 precached, 0 dropped: +10 models, "
        "+0 sounds (now 400 models, 150 sounds, of 511 each)"), "c1a0")
    assert result.verdict == "pass"


def test_reads_only_the_latest_load():
    lines = load("c1a0", models=505) + load("c1a0")
    assert aptest.read_sweep(lines, "c1a0").verdict == "pass"
