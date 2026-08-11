"""Persistent client settings.

Just the chosen Sven Co-op folder, for now. This deliberately owns its own small
JSON file rather than using Archipelago's persistent storage helpers: those are
not part of the documented world API and their names have moved between
versions, and a silently failing save here means the user gets asked for their
install path on every single launch.

Writes are atomic and every failure path is reported to the caller, so "it did
not stick" can never happen quietly.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

FILENAME = "half_life_sven_client.json"


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
