"""The `hlap` game folder, and installing it.

The game side of this project is a server dll built from Valve's Half-Life SDK,
shipped as its own mod folder next to `valve` rather than as a patch to the
player's install. Nothing under `valve` is ever written to: `liblist.gam` carries
`fallback_dir "valve"`, so every map, model and sound is inherited from the
player's own copy of the game and the mod folder holds only what is ours.

    <Half-Life>/
      valve/            untouched
      hlap/
        liblist.gam     the mod manifest, with the fallback
        dlls/hl.dll     the server dll built from game/
        archipelago/    the file bridge, and checkdata.txt

The files bundled here live inside the world package so that a zipped `.apworld`
carries everything needed to set the game up. That means they cannot be read with
plain filesystem calls, so every read goes through `pkgutil.get_data`, which
works identically for a folder world and a zipped one.

Both the client's `/install` command and `tools/install_mod.py` call in here, so
there is one implementation of what installing means.
"""

from __future__ import annotations

import os
import pkgutil
from pathlib import Path

# The mod folder's name, which is also what the player passes to `-game`.
MOD_DIR = "hlap"

# Where the bridge and the generated data live, under the mod folder.
STORE_SUBDIR = "archipelago"

# The server dll, relative to the mod folder. Built from `game/`, not committed:
# a build drops it here and packaging picks it up, so a released `.apworld`
# installs a working mod and a development checkout installs everything but the
# dll and says so.
DLL_NAME = "dlls/hl.dll"

# Files bundled in this package, as (path inside the package, path inside the mod
# folder). The dll is looked up separately because it may legitimately be absent.
MOD_FILES = (
    ("files/liblist.gam", "liblist.gam"),
    ("files/archipelago/checkdata.txt", "archipelago/checkdata.txt"),
)

# Everything install writes and uninstall may remove, plus whatever the last
# session left in the store: ap_in.txt, ap_out.txt and friends. All of it goes on
# uninstall. Nothing but this mod reads any of it, `/install` puts checkdata.txt
# straight back, and a stale ap_out.txt sitting next to no mod is exactly the
# thing that gets mistaken for a live bridge.


def read_mod_file(relative_path: str) -> bytes | None:
    """A bundled file's bytes, or None if it is not in this package."""
    try:
        return pkgutil.get_data(__name__, relative_path)
    except (FileNotFoundError, OSError):
        return None


def resolve_game_root(game_dir: str | os.PathLike[str]) -> Path:
    """Accept either the install root or the `valve` folder itself."""
    root = Path(game_dir)
    if (root / "valve").is_dir():
        return root
    if root.name.lower() == "valve" and root.parent.is_dir():
        return root.parent
    raise ValueError(f"{root} does not look like a Half-Life installation")


def mod_dir(game_dir: str | os.PathLike[str]) -> Path:
    return resolve_game_root(game_dir) / MOD_DIR


def install(game_dir: str | os.PathLike[str]) -> tuple[int, bool]:
    """Create the mod folder and fill it in.

    Returns (files written, whether the server dll was among them). A False there
    is not a failure: it means this build of the world ships no dll, and the
    caller should say where one comes from.
    """
    target_root = mod_dir(game_dir)

    written = 0
    for source, relative in MOD_FILES:
        data = read_mod_file(source)
        if data is None:
            raise FileNotFoundError(f"{__name__}/{source} is missing from the world package")
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written += 1

    dll = read_mod_file(f"files/{DLL_NAME}")
    if dll is not None:
        target = target_root / DLL_NAME
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(dll)
        written += 1

    return written, dll is not None


def uninstall(game_dir: str | os.PathLike[str]) -> int:
    """Remove the whole mod folder. Returns the number of files removed.

    Swept by directory rather than by `MOD_FILES`, because the manifest only
    describes the *current* version: a file that was renamed or dropped between
    releases would otherwise be left behind, which fails in a way that looks like
    the new version being broken.

    Anything the player put in the folder by hand survives, and so does the
    folder itself in that case.
    """
    return sweep(mod_dir(game_dir))


def sweep(directory: Path) -> int:
    """Delete the files this mod owns, then any directory that emptied."""
    if not directory.is_dir():
        return 0

    owned = {relative for _, relative in MOD_FILES} | {DLL_NAME}
    removed = 0
    for relative in sorted(owned):
        path = directory / relative
        if path.is_file():
            path.unlink()
            removed += 1

    # The bridge directory, live session files and all.
    store = directory / STORE_SUBDIR
    if store.is_dir():
        for path in sorted(store.iterdir()):
            if path.is_file():
                path.unlink()
                removed += 1

    for path in sorted(directory.rglob("*"), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    if not any(directory.iterdir()):
        directory.rmdir()

    return removed


def is_installed(game_dir: str | os.PathLike[str]) -> bool:
    """Is there a mod folder with a dll in it?

    The dll rather than `liblist.gam`, because a folder with a manifest and no
    dll is exactly the half-installed state worth reporting as not installed.
    """
    try:
        root = mod_dir(game_dir)
    except ValueError:
        return False
    return (root / "liblist.gam").is_file() and (root / DLL_NAME).is_file()
