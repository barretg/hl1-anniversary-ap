"""The Sven Co-op server plugin, and installing it.

The AngelScript sources live inside the world package so that a zipped
`.apworld` carries everything needed to set the game up. That means they cannot
be read with plain filesystem calls, so every read goes through
`pkgutil.get_data`, which works identically for a folder world and a zipped one.

The tree under `plugins/` mirrors `<Sven Co-op>/svencoop/scripts/`, so installing
is a straight copy with the paths preserved.

Both the client's `/install` command and `tools/install_plugin.py` call in here,
so there is one implementation of what installing means.
"""

from __future__ import annotations

import os
import pkgutil
from pathlib import Path

# Every file that gets copied into the game, relative to this package and to
# `svencoop/scripts/`. `tests/test_plugin_manifest.py` fails if this drifts from
# what is actually on disk, since a missing entry would silently half-install.
PLUGIN_FILES = (
    "plugins/archipelago/ap_bridge.as",
    "plugins/archipelago/ap_deathlink.as",
    "plugins/archipelago/ap_hub.as",
    "plugins/archipelago/ap_items.as",
    "plugins/archipelago/ap_locations.as",
    "plugins/archipelago/ap_main.as",
    "plugins/archipelago/ap_state.as",
    "plugins/store/archipelago/checkdata.txt",
)

# Files the game writes; never removed on uninstall, since ap_out.txt and
# ap_in.txt are the player's live session and checkdata.txt is cheap to restore.
STORE_SUBDIR = "plugins/store/archipelago"

PLUGIN_ENTRY = """	"plugin"
	{
		"name" "Archipelago"
		"script" "archipelago/ap_main"
	}
"""

PLUGIN_SCRIPT_KEY = '"archipelago/ap_main"'


def read_plugin_file(relative_path: str) -> bytes:
    data = pkgutil.get_data(__name__, relative_path)
    if data is None:
        raise FileNotFoundError(f"{__name__}/{relative_path} is missing from the world package")
    return data


def resolve_svencoop(game_dir: str | os.PathLike[str]) -> Path:
    """Accept either the install root or the `svencoop` folder itself."""
    root = Path(game_dir)
    if (root / "svencoop").is_dir():
        return root / "svencoop"
    if root.name.lower() == "svencoop":
        return root
    raise ValueError(f"{root} does not look like a Sven Co-op installation")


def install(game_dir: str | os.PathLike[str]) -> tuple[int, bool]:
    """Copy the plugin in and register it.

    Returns (files written, whether default_plugins.txt was changed).
    """
    svencoop = resolve_svencoop(game_dir)
    scripts = svencoop / "scripts"

    for relative_path in PLUGIN_FILES:
        target = scripts / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(read_plugin_file(relative_path))

    return len(PLUGIN_FILES), register(svencoop)


def register(svencoop: Path) -> bool:
    """Add the plugin block to default_plugins.txt. True if it changed."""
    config = svencoop / "default_plugins.txt"
    if not config.is_file():
        raise FileNotFoundError(f"{config} not found")

    text = config.read_text(encoding="utf-8")
    if PLUGIN_SCRIPT_KEY in text:
        return False

    # The file is one `"plugins" { ... }` block; insert before its final closing
    # brace rather than appending, which would land outside the block.
    index = text.rstrip().rfind("}")
    if index < 0:
        raise ValueError(f"unexpected format in {config}")

    config.with_suffix(".txt.ap-backup").write_text(text, encoding="utf-8")
    config.write_text(text[:index] + PLUGIN_ENTRY + text[index:], encoding="utf-8")
    return True


def uninstall(game_dir: str | os.PathLike[str]) -> tuple[int, bool]:
    """Remove the plugin scripts and deregister it.

    The store folder is deliberately left alone: it holds the live bridge files.
    Returns (files removed, whether default_plugins.txt was changed).
    """
    svencoop = resolve_svencoop(game_dir)
    scripts = svencoop / "scripts"

    removed = 0
    for relative_path in PLUGIN_FILES:
        if relative_path.startswith(STORE_SUBDIR):
            continue
        target = scripts / relative_path
        if target.is_file():
            target.unlink()
            removed += 1

    plugin_dir = scripts / "plugins" / "archipelago"
    if plugin_dir.is_dir() and not any(plugin_dir.iterdir()):
        plugin_dir.rmdir()

    return removed, deregister(svencoop)


def deregister(svencoop: Path) -> bool:
    config = svencoop / "default_plugins.txt"
    if not config.is_file():
        return False
    text = config.read_text(encoding="utf-8")
    if PLUGIN_ENTRY not in text:
        return False
    config.write_text(text.replace(PLUGIN_ENTRY, ""), encoding="utf-8")
    return True


def is_installed(game_dir: str | os.PathLike[str]) -> bool:
    try:
        svencoop = resolve_svencoop(game_dir)
    except ValueError:
        return False
    config = svencoop / "default_plugins.txt"
    if not config.is_file():
        return False
    registered = PLUGIN_SCRIPT_KEY in config.read_text(encoding="utf-8")
    present = (svencoop / "scripts" / "plugins" / "archipelago" / "ap_main.as").is_file()
    return registered and present
