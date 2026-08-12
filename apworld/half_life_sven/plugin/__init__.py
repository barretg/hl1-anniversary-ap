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
    "plugins/archipelago/ap_traps.as",
    "plugins/store/archipelago/checkdata.txt",
)

# Where the plugin reads and writes at runtime: the generated checkdata.txt plus
# whatever the last session left in ap_in.txt, ap_out.txt, ap_pending.txt and
# ap_amnesty.txt. All of it goes on uninstall. Leaving it behind was the old
# behaviour and it is worse than useless: nothing but this plugin reads any of
# it, /install puts checkdata.txt straight back, and a stale ap_out.txt sitting
# next to no plugin is exactly the thing that gets mistaken for a live bridge.
STORE_SUBDIR = "plugins/store/archipelago"

# Everything the plugin owns inside `scripts/`, and the only two directories
# uninstall will empty.
PLUGIN_SUBDIR = "plugins/archipelago"

CONFIG_NAME = "default_plugins.txt"
BACKUP_NAME = "default_plugins.txt.ap-backup"

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
    config = svencoop / CONFIG_NAME
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

    (svencoop / BACKUP_NAME).write_text(text, encoding="utf-8")
    config.write_text(text[:index] + PLUGIN_ENTRY + text[index:], encoding="utf-8")
    return True


def uninstall(game_dir: str | os.PathLike[str]) -> tuple[int, bool]:
    """Remove everything the plugin put in the game, and deregister it.

    Swept by directory rather than by `PLUGIN_FILES`, because the manifest only
    describes the *current* version: a script that was renamed or dropped between
    releases would otherwise be left behind for the compiler to pick up, which
    fails in a way that looks like the new version being broken.

    Returns (files removed, whether default_plugins.txt was changed).
    """
    svencoop = resolve_svencoop(game_dir)
    scripts = svencoop / "scripts"

    removed = 0

    # Scripts. Limited to `.as` so that anything the player put here by hand
    # survives -- and if something did, the directory is left in place too.
    removed += sweep(scripts / PLUGIN_SUBDIR, "*.as")

    # The bridge directory, generated data and live session files alike.
    removed += sweep(scripts / STORE_SUBDIR, "*")

    # Our own backup of their config. deregister() has just put that file back
    # the way it was, so the copy has nothing left to protect.
    backup = svencoop / BACKUP_NAME
    if backup.is_file():
        backup.unlink()
        removed += 1

    return removed, deregister(svencoop)


def sweep(directory: Path, pattern: str) -> int:
    """Delete matching files, then the directory if that emptied it."""
    if not directory.is_dir():
        return 0

    removed = 0
    for path in sorted(directory.glob(pattern)):
        if path.is_file():
            path.unlink()
            removed += 1

    if not any(directory.iterdir()):
        directory.rmdir()

    return removed


def deregister(svencoop: Path) -> bool:
    config = svencoop / CONFIG_NAME
    if not config.is_file():
        return False

    text = config.read_text(encoding="utf-8")
    stripped = remove_plugin_block(text)
    if stripped == text:
        return False

    config.write_text(stripped, encoding="utf-8")
    return True


def remove_plugin_block(text: str) -> str:
    """Cut the `"plugin" { ... }` block that points at our script.

    Found by matching braces around the script key rather than by looking for the
    exact text `install` wrote. The old version did the latter, so a config that
    had been reindented, reformatted by another tool, or edited by hand kept the
    entry forever -- and the game then tried to load a plugin whose files had just
    been deleted.
    """
    key = text.find(PLUGIN_SCRIPT_KEY)
    if key < 0:
        return text

    open_brace = text.rfind("{", 0, key)
    if open_brace < 0:
        return text

    depth = 0
    end = -1
    for index in range(open_brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break

    if end < 0:
        return text  # unbalanced braces; leave the file alone

    # Take the `"plugin"` label that introduces the block, and the whitespace
    # either side of the whole thing, so no blank line is left behind.
    start = text.rfind('"plugin"', 0, open_brace)
    if start < 0:
        start = open_brace

    while start > 0 and text[start - 1] in " \t":
        start -= 1
    while end < len(text) and text[end] in " \t":
        end += 1
    if text.startswith("\r\n", end):
        end += 2
    elif end < len(text) and text[end] == "\n":
        end += 1

    return text[:start] + text[end:]


def is_installed(game_dir: str | os.PathLike[str]) -> bool:
    try:
        svencoop = resolve_svencoop(game_dir)
    except ValueError:
        return False
    config = svencoop / CONFIG_NAME
    if not config.is_file():
        return False
    registered = PLUGIN_SCRIPT_KEY in config.read_text(encoding="utf-8")
    present = (svencoop / "scripts" / PLUGIN_SUBDIR / "ap_main.as").is_file()
    return registered and present
