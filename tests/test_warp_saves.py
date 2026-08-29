"""Warp point savegames: the key both halves compute, and the sweep.

The game writes these files and the client deletes them, which is two programs
agreeing on a filename. The key is the agreement, and `test_the_key_is_stable`
is what fails if either side is changed alone -- the C++ copy lives in
`game/src/ap_warpsave.cpp` and is the same four lines of FNV-1a.

The sweep matters for a different reason: `<Half-Life>/hlap/SAVE` is also where
the player's own quicksave lives, so anything here that deleted too much would
be deleting somebody's game.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
WORLD = REPO / "apworld" / "half_life"
sys.path.insert(0, str(WORLD))

import mod  # noqa: E402
from client.bridge import warp_save_key  # noqa: E402


@pytest.fixture
def install(tmp_path: Path) -> Path:
    maps = tmp_path / "valve" / "maps"
    maps.mkdir(parents=True)
    (maps / "c0a0.bsp").write_bytes(b"")
    return tmp_path


def test_the_key_is_stable() -> None:
    """FNV-1a over `<seed>:<slot>`, eight hex digits.

    Pinned rather than recomputed: the point is that this exact string keeps
    producing this exact digest, because a savegame written by a previous
    release has to still be found by this one.
    """
    assert warp_save_key("ABCD1234:Freeman") == "e123a65d"
    assert warp_save_key("") == ""


def test_two_slots_do_not_share_warp_points() -> None:
    assert warp_save_key("seed:one") != warp_save_key("seed:two")
    assert warp_save_key("one:slot") != warp_save_key("two:slot")


def make_saves(install: Path) -> Path:
    directory = mod.save_dir(install)
    directory.mkdir(parents=True)
    for name in (
        "ap00000001_mc1a2.sav",
        "ap00000001_mc1a2.tga",
        "ap00000001_ulab_c2a5.sav",
        "ap0000002f_mc4a1.sav",
        "quick.sav",
        "half-life.sav",
        "apocalypse.sav",  # a player's own save that starts with the prefix
    ):
        (directory / name).write_bytes(b"")
    return directory


def test_one_key_is_swept_and_nothing_else_is(install: Path) -> None:
    directory = make_saves(install)

    assert mod.clear_warp_saves(install, "00000001") == 3
    assert sorted(p.name for p in directory.iterdir()) == [
        "ap0000002f_mc4a1.sav",
        "apocalypse.sav",
        "half-life.sav",
        "quick.sav",
    ]


def test_no_key_sweeps_every_run(install: Path) -> None:
    directory = make_saves(install)

    assert mod.clear_warp_saves(install) == 4
    assert sorted(p.name for p in directory.iterdir()) == [
        "apocalypse.sav",
        "half-life.sav",
        "quick.sav",
    ]


def test_sweeping_an_install_with_no_saves_is_not_an_error(install: Path) -> None:
    assert mod.clear_warp_saves(install) == 0


def test_uninstall_takes_the_warp_points_and_leaves_the_players_saves(
    install: Path,
) -> None:
    mod.install(install)
    directory = make_saves(install)

    mod.uninstall(install)

    assert sorted(p.name for p in directory.iterdir()) == [
        "apocalypse.sav",
        "half-life.sav",
        "quick.sav",
    ]
