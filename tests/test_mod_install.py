"""Installing the `hlap` mod folder.

The rule this suite exists for: the player's own Half-Life is never written to.
Everything lands in our own folder next to `valve`, and uninstalling leaves the
install exactly as it was found.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
WORLD = REPO / "apworld" / "half_life"
sys.path.insert(0, str(WORLD))

import mod  # noqa: E402
from client.bridge import MOD_DIR, STORE_SUBDIR, find_store_dir  # noqa: E402


@pytest.fixture
def install(tmp_path: Path) -> Path:
    """A plausible Half-Life install: a `valve` folder with a campaign map."""
    maps = tmp_path / "valve" / "maps"
    maps.mkdir(parents=True)
    (maps / "c0a0.bsp").write_bytes(b"")
    return tmp_path


def test_the_two_definitions_of_the_mod_folder_agree() -> None:
    """`bridge.py` spells these out so it can stay dependency-free.

    Two definitions of one path is a drift risk, and this is the guard: the
    bridge would otherwise write to a directory the game never reads.
    """
    assert mod.MOD_DIR == MOD_DIR
    assert mod.STORE_SUBDIR == STORE_SUBDIR


def test_install_writes_only_inside_the_mod_folder(install: Path) -> None:
    before = sorted(p.relative_to(install) for p in (install / "valve").rglob("*"))

    written, _ = mod.install(install)

    assert written >= len(mod.MOD_FILES)
    assert (install / MOD_DIR / "liblist.gam").is_file()
    # Nothing under valve/ moved.
    after = sorted(p.relative_to(install) for p in (install / "valve").rglob("*"))
    assert after == before


def test_install_puts_checkdata_where_the_bridge_looks(install: Path) -> None:
    mod.install(install)
    assert (find_store_dir(install) / "checkdata.txt").is_file()


def test_liblist_falls_back_to_valve(install: Path) -> None:
    """This is what lets the mod folder hold no maps, models or sounds."""
    mod.install(install)
    text = (install / MOD_DIR / "liblist.gam").read_text(encoding="utf-8")
    assert 'fallback_dir "valve"' in text
    assert 'gamedll "dlls\\hl.dll"' in text


def test_install_accepts_the_valve_folder_too(install: Path) -> None:
    mod.install(install / "valve")
    assert (install / MOD_DIR / "liblist.gam").is_file()


def test_install_rejects_a_folder_that_is_not_the_game(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        mod.install(tmp_path)


def test_not_installed_without_the_dll(install: Path) -> None:
    """A manifest with no dll is exactly the half-installed state to report."""
    mod.install(install)
    assert not mod.is_installed(install)

    dll = install / MOD_DIR / mod.DLL_NAME
    dll.parent.mkdir(parents=True, exist_ok=True)
    dll.write_bytes(b"")
    assert mod.is_installed(install)


def test_uninstall_leaves_the_game_as_it_was(install: Path) -> None:
    before = sorted(p.relative_to(install) for p in install.rglob("*"))

    mod.install(install)
    removed = mod.uninstall(install)

    assert removed >= len(mod.MOD_FILES)
    assert not (install / MOD_DIR).exists()
    assert sorted(p.relative_to(install) for p in install.rglob("*")) == before


def test_uninstall_takes_the_live_bridge_files(install: Path) -> None:
    """A stale ap_out.txt next to no mod gets mistaken for a live bridge."""
    mod.install(install)
    store = find_store_dir(install)
    (store / "ap_out.txt").write_text("CHECK|1\n", encoding="utf-8")
    (store / "ap_in.txt").write_text("connected=0\n", encoding="utf-8")

    mod.uninstall(install)

    assert not store.exists()


def test_uninstall_keeps_what_the_player_put_there(install: Path) -> None:
    """Their file, their folder. We only ever remove what we wrote."""
    mod.install(install)
    theirs = install / MOD_DIR / "notes.txt"
    theirs.write_text("mine", encoding="utf-8")

    mod.uninstall(install)

    assert theirs.is_file()


def test_uninstall_is_a_no_op_when_nothing_is_installed(install: Path) -> None:
    assert mod.uninstall(install) == 0
