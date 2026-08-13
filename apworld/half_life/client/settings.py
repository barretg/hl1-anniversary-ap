"""Where the client remembers the Half-Life install path.

The real home is Archipelago's `host.yaml`, under this world's own section, so
the path sits with every other per-game setting and can be edited by hand:

    half_life_settings:
      game_folder: F:/SteamLibrary/steamapps/common/Half-Life

A small JSON file is kept as a fallback for when the settings machinery is not
available (running the client outside Archipelago, or a build where the API has
moved). Earlier versions stored the path only in that file, so it is still read
and is migrated into `host.yaml` on the next save.

Every failure path is reported to the caller rather than swallowed: a save that
quietly does nothing means being asked for the install path on every launch.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# The `host.yaml` section, and the World's `settings_key`.
SETTINGS_KEY = "half_life_settings"
GAME_FOLDER_KEY = "game_folder"

FILENAME = "half_life_client.json"


def settings_path() -> Path:
    """Where to keep the settings file.

    Archipelago's user directory when we can find it, so the file sits with the
    rest of the user's Archipelago data, otherwise the home directory.
    """
    try:
        import Utils

        return Path(Utils.user_path(FILENAME))
    except Exception:
        return Path.home() / f".archipelago_{FILENAME}"


def load(path: Path | None = None) -> dict[str, Any]:
    """Read the settings. A missing or corrupt file reads as empty."""
    target = path or settings_path()
    try:
        with target.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(data: dict[str, Any], path: Path | None = None) -> None:
    """Write the settings atomically. Raises OSError if it could not be stored."""
    target = path or settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    os.replace(temp, target)


def get(key: str, default: Any = None, path: Path | None = None) -> Any:
    return load(path).get(key, default)


def set_value(key: str, value: Any, path: Path | None = None) -> None:
    """Update one key, preserving everything else in the file."""
    data = load(path)
    data[key] = value
    save(data, path)


# -- host.yaml -------------------------------------------------------------


def _group():
    """This world's `host.yaml` section. Raises if settings are unavailable."""
    import settings as ap_settings

    return getattr(ap_settings.get_settings(), SETTINGS_KEY)


def _read_group_value(group) -> str:
    """`settings.Group` is attribute-based, but tolerate mappings too."""
    try:
        return str(getattr(group, GAME_FOLDER_KEY) or "")
    except AttributeError:
        return str(group[GAME_FOLDER_KEY] or "")


def _write_group_value(group, path: str) -> None:
    try:
        setattr(group, GAME_FOLDER_KEY, path)
    except (AttributeError, TypeError):
        group[GAME_FOLDER_KEY] = path


def read_game_dir() -> str:
    """The saved install path: `host.yaml` first, then the legacy JSON file."""
    try:
        value = _read_group_value(_group())
        if value:
            return value
    except Exception:
        pass
    return str(get(GAME_FOLDER_KEY, "") or "")


def write_game_dir(path: str) -> str:
    """Save the install path, preferring `host.yaml`.

    Returns a short description of where it landed, for logging. Raises OSError
    only if nothing could be written anywhere, so a failure that would cause the
    picker to reappear next launch is always visible to the caller.
    """
    destinations: list[str] = []

    try:
        import settings as ap_settings

        group = _group()
        _write_group_value(group, path)
        ap_settings.get_settings().save()
        destinations.append("host.yaml")
    except Exception:
        # No settings machinery, or the API has moved. The file below covers us.
        pass

    try:
        set_value(GAME_FOLDER_KEY, path)
        destinations.append(str(settings_path()))
    except OSError:
        if not destinations:
            raise

    return " and ".join(destinations)

