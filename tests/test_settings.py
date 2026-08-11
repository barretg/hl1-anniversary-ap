"""Persistent client settings.

The failure this guards against is the quiet one: the game folder appearing to
save, then the picker reappearing on the next launch.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apworld" / "half_life_sven"))

from client import settings  # noqa: E402


@pytest.fixture
def store(tmp_path: Path) -> Path:
    return tmp_path / "settings.json"


def test_round_trip(store: Path) -> None:
    settings.set_value("game_dir", r"F:\Games\Sven Co-op", store)
    assert settings.get("game_dir", path=store) == r"F:\Games\Sven Co-op"


def test_survives_a_fresh_read(store: Path) -> None:
    """Nothing is cached in memory, so a new session sees the saved value."""
    settings.set_value("game_dir", "/games/sven", store)
    assert settings.load(store) == {"game_dir": "/games/sven"}


def test_missing_file_reads_empty(store: Path) -> None:
    assert settings.load(store) == {}
    assert settings.get("game_dir", "fallback", store) == "fallback"


def test_corrupt_file_reads_empty_rather_than_raising(store: Path) -> None:
    store.write_text("{not json", encoding="utf-8")
    assert settings.load(store) == {}


def test_non_dict_file_reads_empty(store: Path) -> None:
    store.write_text("[1, 2, 3]", encoding="utf-8")
    assert settings.load(store) == {}


def test_setting_one_key_preserves_others(store: Path) -> None:
    settings.save({"game_dir": "/a", "other": 1}, store)
    settings.set_value("game_dir", "/b", store)
    assert settings.load(store) == {"game_dir": "/b", "other": 1}


def test_overwrite_replaces_the_value(store: Path) -> None:
    settings.set_value("game_dir", "/first", store)
    settings.set_value("game_dir", "/second", store)
    assert settings.get("game_dir", path=store) == "/second"


def test_write_is_atomic(store: Path) -> None:
    settings.set_value("game_dir", "/games/sven", store)
    assert not list(store.parent.glob("*.tmp"))


def test_creates_missing_parent_directories(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "deeper" / "settings.json"
    settings.set_value("game_dir", "/games/sven", nested)
    assert nested.is_file()


def test_save_failure_raises(tmp_path: Path) -> None:
    """The launcher relies on this to warn instead of failing silently."""
    blocked = tmp_path / "settings.json"
    blocked.mkdir()
    with pytest.raises(OSError):
        settings.save({"game_dir": "/x"}, blocked)


def test_settings_path_is_absolute_and_named() -> None:
    path = settings.settings_path()
    assert path.is_absolute()
    assert path.name.endswith(".json")
