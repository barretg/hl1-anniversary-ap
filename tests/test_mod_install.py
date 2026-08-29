"""Installing the `hlap` mod folder.

The rule this suite exists for: the player's own Half-Life is never written to.
Everything lands in our own folder next to `valve`, and uninstalling leaves the
install exactly as it was found.
"""

from __future__ import annotations

import json
import re
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


def test_install_ships_command_binds(install: Path) -> None:
    """The console pauses the game, so the commands need keys as well."""
    mod.install(install)

    binds = (install / MOD_DIR / "apbinds.cfg").read_text(encoding="utf-8")
    assert "ap_hub" in binds
    assert "ap_warps" in binds
    # K is Half-Life's own voice chat key. Binding over it takes something the
    # player already had, which is not ours to do.
    assert 'bind "k"' not in binds.lower()

    autoexec = (install / MOD_DIR / "autoexec.cfg").read_text(encoding="utf-8")
    assert "exec apbinds.cfg" in autoexec


def test_reinstalling_keeps_the_players_own_binds(install: Path) -> None:
    """A player edits these. An update that rebound their keys would be a bug."""
    mod.install(install)

    binds = install / MOD_DIR / "apbinds.cfg"
    binds.write_text('bind "F5" "ap_hub"\n', encoding="utf-8")

    mod.install(install)
    assert binds.read_text(encoding="utf-8") == 'bind "F5" "ap_hub"\n'

    # And uninstalling still takes them, because uninstalling means gone.
    mod.uninstall(install)
    assert not binds.exists()


def test_install_puts_checkdata_where_the_bridge_looks(install: Path) -> None:
    mod.install(install)
    assert (find_store_dir(install) / "checkdata.txt").is_file()


def test_liblist_falls_back_to_valve(install: Path) -> None:
    """This is what lets the mod folder hold no maps, models or sounds."""
    mod.install(install)
    text = (install / MOD_DIR / "liblist.gam").read_text(encoding="utf-8")
    assert 'fallback_dir "valve"' in text
    assert 'gamedll "dlls\\hl.dll"' in text


def test_new_game_starts_in_the_hub() -> None:
    """`startmap` and the game side's hub map have to be the same map.

    New Game goes wherever `startmap` says. If that were a campaign map, the
    player would be handed one mission for free and its arrival check would fire
    before the run had begun; if it were a *different* map from the one `ap_hub`
    returns to, the run would have two homes.

    The two live in different languages, so this is the only thing that can hold
    them together.
    """
    liblist = (WORLD / "mod" / "files" / "liblist.gam").read_text(encoding="utf-8")
    hub_source = (REPO / "game" / "src" / "ap_hub.cpp").read_text(encoding="utf-8")

    start = re.search(r'^\s*startmap\s+"([^"]+)"', liblist, re.M)
    hub = re.search(r'kHubMap\s*=\s*"([^"]+)"', hub_source)

    assert start is not None, "liblist.gam has no startmap"
    assert hub is not None, "ap_hub.cpp no longer defines kHubMap"
    assert start.group(1) == hub.group(1)


def test_install_ships_the_lobby_map(install: Path) -> None:
    """The one map the mod folder carries.

    Everything else is inherited from `valve` through the fallback, but no
    Half-Life install has this one, so an install that skipped it would drop the
    player into `startmap` with nothing to load.
    """
    mod.install(install)
    liblist = (install / MOD_DIR / "liblist.gam").read_text(encoding="utf-8")
    start = re.search(r'^\s*startmap\s+"([^"]+)"', liblist, re.M)
    assert start is not None
    assert (install / MOD_DIR / "maps" / f"{start.group(1)}.bsp").is_file()


def test_the_hub_map_is_named_the_same_in_all_three_places() -> None:
    """`startmap`, `kHubMap` and the data's `hub_map` are one map.

    `test_new_game_starts_in_the_hub` ties the first two together. The third is
    what the `P` records were generated against, so a drift there would ship
    panels keyed to a lobby nobody loads.
    """
    campaign = json.loads(
        (WORLD / "data" / "campaign.json").read_text(encoding="utf-8")
    )
    liblist = (WORLD / "mod" / "files" / "liblist.gam").read_text(encoding="utf-8")
    start = re.search(r'^\s*startmap\s+"([^"]+)"', liblist, re.M)

    assert start is not None
    assert campaign["hub_map"] == start.group(1)


def test_the_hub_is_not_a_campaign_map() -> None:
    """A check firing in the hub would be a check for standing still."""
    campaign = json.loads(
        (WORLD / "data" / "campaign.json").read_text(encoding="utf-8")
    )
    maps = {m for chapter in campaign["chapters"] for m in chapter["maps"]}

    liblist = (WORLD / "mod" / "files" / "liblist.gam").read_text(encoding="utf-8")
    start = re.search(r'^\s*startmap\s+"([^"]+)"', liblist, re.M)
    assert start is not None
    assert start.group(1) not in maps


def test_install_accepts_the_valve_folder_too(install: Path) -> None:
    mod.install(install / "valve")
    assert (install / MOD_DIR / "liblist.gam").is_file()


def test_install_rejects_a_folder_that_is_not_the_game(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        mod.install(tmp_path)


def test_not_installed_without_the_dll(install: Path) -> None:
    """A manifest with no dll is exactly the half-installed state to report.

    Which of the two states a fresh `install()` lands in depends on whether this
    checkout has a built dll in `mod/files/dlls/`, so the test makes both states
    rather than assuming either.
    """
    mod.install(install)
    dll = install / MOD_DIR / mod.DLL_NAME

    if dll.is_file():
        dll.unlink()
    assert not mod.is_installed(install)

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
