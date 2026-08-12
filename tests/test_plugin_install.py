"""Plugin packaging and installation.

The manifest test is the important one: `PLUGIN_FILES` is what a zipped
`.apworld` copies into the game, and a file missing from it would install a
plugin that silently fails to compile.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "apworld" / "half_life_sven"))

import plugin  # noqa: E402

PLUGIN_ROOT = REPO / "apworld" / "half_life_sven" / "plugin"

DEFAULT_PLUGINS = '''"plugins"
{
	"plugin"
	{
		"name" "PlayerManagement"
		"script" "admin/PlayerManagement"
	}
}
'''


@pytest.fixture
def game(tmp_path: Path) -> Path:
    svencoop = tmp_path / "svencoop"
    (svencoop / "maps").mkdir(parents=True)
    (svencoop / "default_plugins.txt").write_text(DEFAULT_PLUGINS, encoding="utf-8")
    return tmp_path


def test_manifest_matches_disk() -> None:
    on_disk = {
        p.relative_to(PLUGIN_ROOT).as_posix()
        for p in PLUGIN_ROOT.rglob("*")
        if p.is_file() and p.suffix != ".py" and "__pycache__" not in p.parts
    }
    assert on_disk == set(plugin.PLUGIN_FILES)


def test_every_manifest_file_is_readable() -> None:
    for relative_path in plugin.PLUGIN_FILES:
        assert plugin.read_plugin_file(relative_path)


def test_manifest_paths_are_relative_and_posix() -> None:
    for relative_path in plugin.PLUGIN_FILES:
        assert not relative_path.startswith("/")
        assert "\\" not in relative_path


def test_entry_point_is_in_the_manifest() -> None:
    assert "plugins/archipelago/ap_main.as" in plugin.PLUGIN_FILES


def test_install_copies_and_registers(game: Path) -> None:
    written, registered = plugin.install(game)

    assert written == len(plugin.PLUGIN_FILES)
    assert registered is True
    assert plugin.is_installed(game)

    scripts = game / "svencoop" / "scripts"
    assert (scripts / "plugins" / "archipelago" / "ap_main.as").is_file()
    assert (scripts / "plugins" / "store" / "archipelago" / "checkdata.txt").is_file()

    config = (game / "svencoop" / "default_plugins.txt").read_text(encoding="utf-8")
    assert plugin.PLUGIN_SCRIPT_KEY in config
    # The entry must land inside the "plugins" block, not after it.
    assert config.rstrip().endswith("}")
    assert config.index(plugin.PLUGIN_SCRIPT_KEY) < config.rstrip().rfind("}")
    # The pre-existing plugin survives.
    assert "PlayerManagement" in config


def test_install_is_idempotent(game: Path) -> None:
    plugin.install(game)
    _, registered = plugin.install(game)

    assert registered is False
    config = (game / "svencoop" / "default_plugins.txt").read_text(encoding="utf-8")
    assert config.count(plugin.PLUGIN_SCRIPT_KEY) == 1


def test_install_backs_up_the_config(game: Path) -> None:
    plugin.install(game)
    backup = game / "svencoop" / "default_plugins.txt.ap-backup"
    assert backup.is_file()
    assert plugin.PLUGIN_SCRIPT_KEY not in backup.read_text(encoding="utf-8")


def test_install_accepts_the_svencoop_folder(game: Path) -> None:
    plugin.install(game / "svencoop")
    assert plugin.is_installed(game)


def test_uninstall_leaves_nothing_behind(game: Path) -> None:
    plugin.install(game)
    scripts = game / "svencoop" / "scripts"
    store = scripts / "plugins" / "store" / "archipelago"
    (store / "ap_out.txt").write_text("CHECK|7720001\n", encoding="utf-8")
    (store / "ap_in.txt").write_text("connected=1\n", encoding="utf-8")

    removed, deregistered = plugin.uninstall(game)

    assert removed > 0
    assert deregistered is True
    assert not plugin.is_installed(game)
    assert not (scripts / "plugins" / "archipelago").exists()
    assert not store.exists()
    assert not (game / "svencoop" / "default_plugins.txt.ap-backup").exists()


def test_uninstall_removes_scripts_from_older_versions(game: Path) -> None:
    """The manifest describes this version; a leftover .as still gets compiled."""
    plugin.install(game)
    stale = game / "svencoop" / "scripts" / "plugins" / "archipelago" / "ap_gone.as"
    stale.write_text("// from a previous release\n", encoding="utf-8")

    plugin.uninstall(game)

    assert not stale.exists()


def test_uninstall_keeps_files_it_does_not_own(game: Path) -> None:
    plugin.install(game)
    plugin_dir = game / "svencoop" / "scripts" / "plugins" / "archipelago"
    theirs = plugin_dir / "notes.txt"
    theirs.write_text("mine\n", encoding="utf-8")

    plugin.uninstall(game)

    assert theirs.read_text(encoding="utf-8") == "mine\n"
    assert not (plugin_dir / "ap_main.as").exists()


def test_uninstall_deregisters_a_reformatted_entry(game: Path) -> None:
    """A config touched by another tool must still be cleaned up."""
    plugin.install(game)
    config = game / "svencoop" / "default_plugins.txt"
    config.write_text(
        config.read_text(encoding="utf-8").replace("\t", "  "), encoding="utf-8"
    )

    _, deregistered = plugin.uninstall(game)

    assert deregistered is True
    text = config.read_text(encoding="utf-8")
    assert plugin.PLUGIN_SCRIPT_KEY not in text
    assert "PlayerManagement" in text
    assert text.rstrip().endswith("}")


def test_deregister_leaves_the_rest_of_the_config_intact(game: Path) -> None:
    original = (game / "svencoop" / "default_plugins.txt").read_text(encoding="utf-8")
    plugin.install(game)
    plugin.uninstall(game)

    assert (game / "svencoop" / "default_plugins.txt").read_text(
        encoding="utf-8"
    ) == original


def test_uninstall_when_not_installed_is_harmless(game: Path) -> None:
    removed, deregistered = plugin.uninstall(game)
    assert removed == 0
    assert deregistered is False


def test_reinstall_after_uninstall(game: Path) -> None:
    plugin.install(game)
    plugin.uninstall(game)
    plugin.install(game)
    assert plugin.is_installed(game)


def test_rejects_a_non_install_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        plugin.install(tmp_path)


def test_is_installed_false_when_only_registered(game: Path) -> None:
    """Registering without the scripts present is a broken install, not a good one."""
    plugin.register(game / "svencoop")
    assert not plugin.is_installed(game)
